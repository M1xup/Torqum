import hashlib
import hmac
import uuid

import httpx

import config


class PaymentError(Exception):
    pass


async def create_rub_payment(amount: float, order_id: str, description: str, metadata: dict = None) -> dict:
    """Создаёт платёж в RollyPay и возвращает ответ с pay_url."""
    if not config.ROLLYPAY_API_KEY:
        raise PaymentError("Касса RollyPay не подключена: задайте ROLLYPAY_API_KEY в переменных окружения.")
    payload = {
        "amount": f"{round(amount, 2):.2f}",
        "payment_currency": "RUB",
        "order_id": order_id,
        "description": description[:200],
        "metadata": metadata or {},
    }
    if config.ROLLYPAY_TEST_MODE:
        payload["test"] = True
    headers = {
        "X-API-Key": config.ROLLYPAY_API_KEY,
        "X-Nonce": str(uuid.uuid4()),
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(config.ROLLYPAY_API_URL + "/payments", json=payload, headers=headers)
        if resp.status_code >= 400:
            raise PaymentError(f"RollyPay вернул ошибку {resp.status_code}: {resp.text[:300]}")
        return resp.json()


def verify_signature(raw_body: bytes, timestamp: str, signature: str) -> bool:
    """Проверка X-Signature вебхука: HMAC-SHA256 от 'timestamp + "." + body'."""
    if not config.ROLLYPAY_SIGNING_SECRET:
        return False
    mac = hmac.new(
        config.ROLLYPAY_SIGNING_SECRET.encode(),
        (str(timestamp) + ".").encode() + raw_body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(mac, (signature or "").strip())
