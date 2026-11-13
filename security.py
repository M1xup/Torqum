import base64
import hashlib
import hmac
import json
import logging
import urllib.parse

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

log = logging.getLogger("torqum.security")

# Официальные публичные ключи Telegram для проверки подписи Mini App (Bot API 8.0+)
TELEGRAM_PUBLIC_KEYS = {
    "production": "e7bf03a2fa4602af4580703d88dda5bb59f32ed8b02a56c187fe7d34caed242d",
    "test": "40055058a4ee38156a06562e52eece92a771bcd8346a8c4615cb7376eddf72ec",
}


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
        items_dec = []  # значения раскодированные (каноническая схема aiogram)
        items_raw = []  # значения как есть в строке (страховка от нестандартной кодировки)
        for pair in init_data.split("&"):
            key, _, value = pair.partition("=")
            if key == "hash":
                received_hash = value
            elif key == "signature":
                signature_b64 = value  # Bot API 8.0+: исключаются и hash, и signature
            else:
                items_dec.append((key, urllib.parse.unquote(value)))
                items_raw.append((key, value))
        for items in (items_dec, items_raw):
            items.sort()

        # Способ 1: HMAC по токену бота — пробуем обе формы проверочной строки
        secret_key = hmac.new(b"WebAppData", token.strip().strip("\"'").encode(), hashlib.sha256).digest()
        for items in (items_dec, items_raw):
            dcs = "\n".join(f"{k}={v}" for k, v in items)
            calculated = hmac.new(secret_key, dcs.encode(), hashlib.sha256).hexdigest()
            if received_hash and hmac.compare_digest(calculated, received_hash):
                return _extract_user(items)

        # Способ 2: Ed25519-подпись Telegram (не зависит от токена в окружении)
        if signature_b64 and _check_ed25519(token.split(":", 1)[0], init_data, signature_b64):
            log.warning(
                "AUTH: HMAC не совпал, но подпись Telegram валидна — BOT_TOKEN в окружении, "
                "похоже, не совпадает с токеном бота. Возьмите токен заново: @BotFather -> /mybots -> API Token"
            )
            return _extract_user(items_dec)

        dcs_len = len("\n".join(f"{k}={v}" for k, v in items_dec))
        calc_preview = hmac.new(secret_key, "\n".join(f"{k}={v}" for k, v in items_dec).encode(),
                                hashlib.sha256).hexdigest()
        log.warning(
            "AUTH: подпись initData не совпала (полей: %d, длина строки: %d, длина initData: %d, "
            "hash нач.: %s, расчёт нач.: %s, токен id: %s)",
            len(items_dec), dcs_len, len(init_data),
            received_hash[:8], calc_preview[:8], token.split(":", 1)[0],
        )
        return None
    except Exception as e:
        log.warning("AUTH: не удалось разобрать initData: %r", e)
        return None



def _check_ed25519(bot_id: str, init_data: str, signature_b64: str) -> bool:
    """Проверка Ed25519-подписи Telegram: bot_id:WebAppData + поля без hash/signature."""
    try:
        variants = []
        for decode in (True, False):
            items = []
            for pair in init_data.split("&"):
                key, _, value = pair.partition("=")
                if key in ("hash", "signature"):
                    continue
                items.append((key, urllib.parse.unquote(value) if decode else value))
            items.sort()
            fields = "\n".join(f"{k}={v}" for k, v in items)
            variants.append(f"{bot_id}:WebAppData\n{fields}")
        pad = "=" * (-len(signature_b64) % 4)
        sig = base64.urlsafe_b64decode(signature_b64 + pad)
        for key_hex in TELEGRAM_PUBLIC_KEYS.values():
            pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(key_hex))
            for dcs in variants:
                try:
                    pub.verify(sig, dcs.encode())
                    return True
                except Exception:
                    continue
        return False
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
