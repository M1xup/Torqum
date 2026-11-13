import json
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, Response

import config
import db
import payments
from bot import bot, deliver_order
from security import is_admin_username, parse_init_data

log = logging.getLogger("torqum.web")
router = APIRouter()

PUBLIC_SETTINGS = ("home_text", "about_text", "support_contacts", "categories")


async def require_user(request: Request) -> dict:
    init_data = request.headers.get("X-Init-Data", "")
    user = parse_init_data(config.BOT_TOKEN, init_data)
    if not user:
        raise HTTPException(status_code=401, detail="Требуется авторизация через Telegram")
    return user


async def require_admin(request: Request) -> dict:
    user = await require_user(request)
    if not is_admin_username(user.get("username")):
        raise HTTPException(status_code=403, detail="Доступ только для администраторов")
    return user


# ---------- страницы ----------

@router.get("/")
async def index():
    return FileResponse("static/index.html")


@router.get("/admin")
async def admin_page():
    return FileResponse("static/admin.html")


@router.get("/policy")
async def policy_page():
    return FileResponse("static/policy.html")


@router.get("/terms")
async def terms_page():
    return FileResponse("static/terms.html")


@router.get("/favicon.ico")
async def favicon():
    return Response(status_code=204)


# ---------- публичное API ----------

@router.post("/api/user")
async def whoami(request: Request):
    user = await require_user(request)
    return {"ok": True, "user": {k: user.get(k) for k in ("id", "username", "first_name", "last_name") if user.get(k)},
            "is_admin": is_admin_username(user.get("username"))}


@router.get("/api/bootstrap")
async def bootstrap():
    settings = await db.get_settings()
    cats = [c.strip() for c in settings.get("categories", "").split(",") if c.strip()]
    products = await db.list_products(active_only=True)
    return {
        "settings": {k: settings.get(k, "") for k in ("home_text", "about_text", "support_contacts")},
        "categories": cats,
        "products": products,
    }


@router.get("/api/support")
async def public_support():
    settings = await db.get_settings()
    return {"contacts": settings.get("support_contacts", "")}


@router.post("/api/checkout")
async def checkout(request: Request):
    user = await require_user(request)
    body = await request.json()
    items_in = body.get("items") or []

    cleaned, total = [], 0.0
    for it in items_in:
        try:
            pid = int(it.get("product_id", 0))
            qty = max(1, int(it.get("qty", 1)))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Некорректная корзина")
        p = await db.get_product(pid)
        if not p or not p["active"]:
            raise HTTPException(status_code=400, detail=f"Товар недоступен (id {pid})")
        if p["count"] == 0:
            raise HTTPException(status_code=400, detail=f"«{p['title']}» закончился")
        if p["count"] > 0 and qty > p["count"]:
            raise HTTPException(status_code=400, detail=f"«{p['title']}» доступно только {p['count']} шт.")
        total += p["price"] * qty
        cleaned.append({"product_id": p["id"], "title": p["title"], "qty": qty, "price": p["price"]})

    if not cleaned:
        raise HTTPException(status_code=400, detail="Корзина пуста")

    total = round(total, 2)
    order = await db.create_order(user["id"], user.get("username") or "", cleaned, total)
    description = "Заказ TORQUM: " + ", ".join(f"{i['title']} ×{i['qty']}" for i in cleaned)
    try:
        pay = await payments.create_rub_payment(
            total, order["order_id"], description,
            metadata={"order_id": order["order_id"], "items": [i["title"] for i in cleaned]},
        )
    except payments.PaymentError as e:
        await db.update_order_status(order["order_id"], "canceled")
        raise HTTPException(status_code=503, detail=str(e))

    await db.update_order_status(order["order_id"], "pending", pay.get("payment_id", ""))
    return {
        "ok": True,
        "order_id": order["order_id"],
        "total": total,
        "pay_url": pay.get("pay_url"),
        "breakdown": [
            {"title": i["title"], "qty": i["qty"], "price": i["price"], "sum": round(i["price"] * i["qty"], 2)}
            for i in cleaned
        ],
    }


@router.get("/api/purchases")
async def purchases(request: Request):
    user = await require_user(request)
    result = []
    for o in await db.list_orders(user_id=user["id"]):
        if o["status"] != "paid":
            continue
        items = json.loads(o["items"])
        for it in items:
            p = await db.get_product(it["product_id"])
            it["type"] = (p["type"] if p else "text")
            it["content"] = (p["content"] if p else "")
        result.append({"order_id": o["order_id"], "total": o["total"], "created_at": o["created_at"], "items": items})
    return {"orders": result}


# ---------- админ API ----------

@router.get("/api/admin/data")
async def admin_data(request: Request):
    await require_admin(request)
    orders = await db.list_orders()
    return {"products": await db.list_products(), "settings": await db.get_settings(), "orders": orders}


@router.post("/api/admin/product")
async def admin_save_product(request: Request):
    await require_admin(request)
    data = await request.json()
    pid = await db.upsert_product(data)
    return {"ok": True, "id": pid}


@router.post("/api/admin/product/delete")
async def admin_delete_product(request: Request):
    await require_admin(request)
    body = await request.json()
    await db.delete_product(int(body.get("id", 0)))
    return {"ok": True}


@router.post("/api/admin/settings")
async def admin_save_settings(request: Request):
    await require_admin(request)
    body = await request.json()
    await db.set_settings(body)
    return {"ok": True}


# ---------- вебхуки RollyPay ----------

@router.post(config.WEBHOOK_PATH)
async def rollypay_webhook(request: Request):
    raw = await request.body()
    signature = request.headers.get("x-signature", "")
    timestamp = request.headers.get("x-timestamp", "")
    if config.ROLLYPAY_SIGNING_SECRET:
        if not payments.verify_signature(raw, timestamp, signature):
            return {"ok": False, "error": "invalid signature"}
    else:
        log.warning("ROLLYPAY_SIGNING_SECRET не задан — подпись вебхука не проверяется!")
    try:
        data = json.loads(raw)
    except Exception:
        return {"ok": True}

    order = await db.get_order(data.get("order_id", ""))
    if not order:
        return {"ok": True}
    status = data.get("status", "")
    log.info("RollyPay вебхук: %s для заказа %s", status, order["order_id"])

    if status == "paid" and order["status"] != "paid":
        await db.update_order_status(order["order_id"], "paid", data.get("payment_id", ""))
        await db.decrement_stock(json.loads(order["items"]))
        try:
            await deliver_order(order)
        except Exception:
            log.exception("Ошибка выдачи товаров по заказу %s", order["order_id"])
    elif status in ("canceled", "expired", "refunded", "chargeback"):
        await db.update_order_status(order["order_id"], status)
    return {"ok": True}
