from contextlib import asynccontextmanager
import aiosqlite
import time

from config import DB_PATH

_SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    price REAL NOT NULL DEFAULT 0,
    category TEXT NOT NULL DEFAULT '',
    count INTEGER NOT NULL DEFAULT -1,
    type TEXT NOT NULL DEFAULT 'text',
    content TEXT NOT NULL DEFAULT '',
    image_url TEXT NOT NULL DEFAULT '',
    badge TEXT NOT NULL DEFAULT '',
    featured INTEGER NOT NULL DEFAULT 0,
    collection INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    sort INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id TEXT UNIQUE NOT NULL,
    user_id INTEGER NOT NULL,
    username TEXT NOT NULL DEFAULT '',
    items TEXT NOT NULL,
    total REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',
    payment_id TEXT NOT NULL DEFAULT '',
    test INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL DEFAULT 0,
    paid_at INTEGER
);
"""

DEFAULTS = {
    "home_text": "Цифровые продукты, созданные для новых идей и больших задач. Шаблоны, наборы и инструменты — в одном месте.",
    "about_text": "TORQUM — закрытая цифровая витрина премиальных продуктов.\n\nМы отбираем и создаём материалы, которые экономят ваше время: шаблоны, пресеты, наборы для работы и творчества. Каждый продукт проверяется вручную перед публикацией.\n\nПо любым вопросам пишите в службу поддержки — контакты указаны ниже.",
    "support_contacts": "torqumbot@gmail.com — служба поддержки\nОпишите вопрос и укажите номер заказа — ответим в течение рабочего дня.",
    "categories": "Для работы, Для творчества",
}

_SEED_PRODUCTS = [
    ("Workspace OS", "Шаблон для организации работы и личных процессов.", 1900, "Для работы", -1,
     "text", "Демо-контент продукта. Замените его в админ-панели на реальный текст или файл.", "", "Новинка", 1, 0, 1, 1,
     int(time.time())),
    ("Visual Pack", "Набор визуальных материалов для проектов.", 1400, "Для творчества", -1,
     "text", "Демо-контент продукта. Замените его в админ-панели на реальный текст или файл.", "", "", 1, 0, 1, 2,
     int(time.time())),
    ("TORQUM Select Bundle", "Премиальный набор: всё лучшее в одной коллекции.", 4900, "Для творчества", -1,
     "text", "Демо-контент продукта. Замените его в админ-панели на реальный текст или файл.", "", "Select", 0, 1, 1, 3,
     int(time.time())),
]

@asynccontextmanager
async def _connect():
    c = await aiosqlite.connect(DB_PATH)
    c.row_factory = aiosqlite.Row
    try:
        yield c
    finally:
        await c.close()

async def init_db():
    async with _connect() as c:
        await c.executescript(_SCHEMA)
        for key, value in DEFAULTS.items():
            await c.execute("INSERT OR IGNORE INTO settings(key, value) VALUES(?, ?)", (key, value))
        # миграция: в старых базах контактами поддержки был username — заменяем на почту
        cur = await c.execute("SELECT value FROM settings WHERE key = 'support_contacts'")
        row = await cur.fetchone()
        if row and "M1xup" in (row["value"] or ""):
            await c.execute(
                "UPDATE settings SET value = ? WHERE key = 'support_contacts'",
                (DEFAULTS["support_contacts"],),
            )
        cur = await c.execute("SELECT COUNT(*) FROM products")
        (n,) = await cur.fetchone()
        if not n:
            await c.executemany(
                "INSERT INTO products(title, description, price, category, count, type, content,"
                " image_url, badge, featured, collection, active, sort, created_at)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                _SEED_PRODUCTS,
            )
        await c.commit()


# ---------- settings ----------

async def get_settings() -> dict:
    async with _connect() as c:
        cur = await c.execute("SELECT key, value FROM settings")
        return {r["key"]: r["value"] for r in await cur.fetchall()}


async def set_settings(data: dict):
    async with _connect() as c:
        for key in DEFAULTS:
            if key in data:
                await c.execute(
                    "INSERT INTO settings(key, value) VALUES(?, ?)"
                    " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, str(data[key])),
                )
        await c.commit()


# ---------- products ----------

def _row_to_product(r) -> dict:
    return dict(r) if r is not None else None


async def list_products(active_only: bool = False):
    query = "SELECT * FROM products"
    if active_only:
        query += " WHERE active = 1"
    query += " ORDER BY sort ASC, id DESC"
    async with _connect() as c:
        cur = await c.execute(query)
        return [_row_to_product(r) for r in await cur.fetchall()]


async def get_product(pid):
    async with _connect() as c:
        cur = await c.execute("SELECT * FROM products WHERE id = ?", (pid,))
        return _row_to_product(await cur.fetchone())


async def upsert_product(data: dict) -> int:
    fields = ["title", "description", "price", "category", "count", "type", "content",
              "image_url", "badge", "featured", "collection", "active", "sort"]
    values = {}
    for f in fields:
        v = data.get(f)
        if f in ("count", "featured", "collection", "active", "sort"):
            values[f] = int(v) if v not in (None, "") else 0
        elif f == "price":
            values[f] = float(v) if v not in (None, "") else 0.0
        else:
            values[f] = str(v) if v is not None else ""
    values["type"] = "file" if values["type"] == "file" else "text"
    async with _connect() as c:
        pid = data.get("id")
        if pid:
            await c.execute(
                "UPDATE products SET title=?, description=?, price=?, category=?, count=?, type=?,"
                " content=?, image_url=?, badge=?, featured=?, collection=?, active=?, sort=? WHERE id=?",
                (values["title"], values["description"], values["price"], values["category"],
                 values["count"], values["type"], values["content"], values["image_url"],
                 values["badge"], values["featured"], values["collection"], values["active"],
                 values["sort"], int(pid)),
            )
            new_id = int(pid)
        else:
            cur = await c.execute(
                "INSERT INTO products(title, description, price, category, count, type, content,"
                " image_url, badge, featured, collection, active, sort, created_at)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (values["title"], values["description"], values["price"], values["category"],
                 values["count"], values["type"], values["content"], values["image_url"],
                 values["badge"], values["featured"], values["collection"], values["active"],
                 values["sort"], int(__import__("time").time())),
            )
            new_id = cur.lastrowid
        await c.commit()
        return new_id


async def delete_product(pid: int):
    async with _connect() as c:
        await c.execute("DELETE FROM products WHERE id = ?", (pid,))
        await c.commit()


async def decrement_stock(items):
    async with _connect() as c:
        for it in items:
            await c.execute(
                "UPDATE products SET count = count - ? WHERE id = ? AND count > 0",
                (int(it.get("qty", 1)), it["product_id"]),
            )
        await c.commit()


# ---------- orders ----------

async def create_order(user_id: int, username: str, items: list, total: float) -> dict:
    import json as _json
    import time as _time
    import uuid as _uuid

    order = {
        "order_id": _uuid.uuid4().hex,
        "user_id": user_id,
        "username": username or "",
        "items": _json.dumps(items, ensure_ascii=False),
        "total": round(total, 2),
        "created_at": int(_time.time()),
    }
    async with _connect() as c:
        await c.execute(
            "INSERT INTO orders(order_id, user_id, username, items, total, status, created_at)"
            " VALUES(?,?,?,?,?,?,?)",
            (order["order_id"], order["user_id"], order["username"], order["items"],
             order["total"], "pending", order["created_at"]),
        )
        await c.commit()
    return order


async def get_order(order_id: str):
    async with _connect() as c:
        cur = await c.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,))
        r = await cur.fetchone()
        return dict(r) if r else None


async def update_order_status(order_id: str, status: str, payment_id: str = None):
    import time as _time

    async with _connect() as c:
        if status == "paid":
            await c.execute(
                "UPDATE orders SET status = ?, payment_id = COALESCE(?, payment_id), paid_at = ? WHERE order_id = ?",
                (status, payment_id, int(_time.time()), order_id),
            )
        else:
            await c.execute(
                "UPDATE orders SET status = ?, payment_id = COALESCE(?, payment_id) WHERE order_id = ?",
                (status, payment_id, order_id),
            )
        await c.commit()


async def list_orders(user_id: int = None):
    async with _connect() as c:
        if user_id is None:
            cur = await c.execute("SELECT * FROM orders ORDER BY id DESC LIMIT 500")
        else:
            cur = await c.execute("SELECT * FROM orders WHERE user_id = ? ORDER BY id DESC", (user_id,))
        return [dict(r) for r in await cur.fetchall()]
