import base64
import hashlib
import hmac
import json
import logging
import urllib.parse

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

log = logging.getLogger("torqum.security")

# Официальный публичный ключ Telegram для проверки подписи Mini App
TELEGRAM_PUBLIC_KEY = "d0d43f5bab6ed763c7548a3a58d1ce8b2ba4c3a19b31a1300c82ba27b9cfdbb4"


def parse_init_data(token: str, init_data: str):
    """Проверяет подпись Telegram initData и возвращает dict пользователя либо None."""
    if not token:
        log.error("AUTH: BOT_TOKEN пуст на сервере — проверка initData невозможна")
        return None
    if not init_data:
        log.warning("AUTH: заголовок X-Init-Data пуст — приложение открыто не через Telegram")
        return None
    try:
        received_hash = ""
        signature_b64 = ""
        check_items = []
        for pair in init_data.split("&"):
            key, _, value = pair.partition("=")
            if key == "hash":
                received_hash = value
            elif key == "signature":
                signature_b64 = value  # Bot API 8.0+: поле signature в строку проверки не входит
            else:
                # ВАЖНО: в проверочную строку значения входят уже раскодированными
                check_items.append((key, urllib.parse.unquote(value)))
        check_items.sort()
        data_check_string = "\n".join(f"{k}={v}" for k, v in check_items)

        # Способ 1: HMAC по токену бота
        secret_key = hmac.new(b"WebAppData", token.strip().strip("\"'").encode(), hashlib.sha256).digest()
        calculated = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        if received_hash and hmac.compare_digest(calculated, received_hash):
            return _extract_user(check_items)

        # Способ 2: Ed25519-подпись Telegram (не зависит от токена в окружении)
        if signature_b64 and _check_ed25519(data_check_string, signature_b64):
            log.warning("AUTH: HMAC не совпал, но подпись Telegram валидна — похоже, BOT_TOKEN в окружении не совпадает с токеном бота")
            return _extract_user(check_items)

        log.warning(
            "AUTH: подпись initData не совпала (полей: %d, длина строки: %d, длина initData: %d, "
            "hash нач.: %s, расчёт нач.: %s, токен id: %s)",
            len(check_items), len(data_check_string), len(init_data),
            received_hash[:8], calculated[:8], token.split(":", 1)[0],
        )
        return None
    except Exception as e:
        log.warning("AUTH: не удалось разобрать initData: %r", e)
        return None



def _check_ed25519(data_check_string: str, signature_b64: str) -> bool:
    try:
        pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(TELEGRAM_PUBLIC_KEY))
        pad = "=" * (-len(signature_b64) % 4)
        pub.verify(base64.urlsafe_b64decode(signature_b64 + pad), data_check_string.encode())
        return True
    except Exception:
        return False


def _extract_user(check_items) -> dict | None:
    raw_user = dict(check_items).get("user", "{}")
    try:
        user = json.loads(raw_user)
    except json.JSONDecodeError:
        return None
    return user if isinstance(user, dict) else None
    


def is_admin_username(username) -> bool:
    if not username:
        return False
    return str(username).lstrip("@").lower() in set(__import__("config").ADMIN_USERNAMES)
