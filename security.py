import hashlib
import hmac
import json
import logging
import urllib.parse

log = logging.getLogger("torqum.security")


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
        check_items = []
        has_signature = False
        for pair in init_data.split("&"):
            key, _, value = pair.partition("=")
            if key == "hash":
                received_hash = value
            elif key == "signature":
                has_signature = True  # Bot API 8.0+: поле signature в hash не участвует
            else:
                check_items.append((key, value))
        check_items.sort()
        data_check_string = "\n".join(f"{k}={v}" for k, v in check_items)
        secret_key = hmac.new(b"WebAppData", token.strip().strip("\"'").encode(), hashlib.sha256).digest()
        calculated = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        if not received_hash:
            log.warning("AUTH: в initData нет поля hash (поля: %s)", sorted(k for k, _ in check_items))
            return None
        if not hmac.compare_digest(calculated, received_hash):
            log.warning(
                "AUTH: подпись initData не совпала (полей: %d, signature: %s, длина initData: %d, токен начинается с: %s)",
                len(check_items), has_signature, len(init_data), token.split(":", 1)[0],
            )
            return None
        raw_user = dict(check_items).get("user", "{}")
        user = json.loads(urllib.parse.unquote(raw_user))
        return user if isinstance(user, dict) else None
    except Exception as e:
        log.warning("AUTH: не удалось разобрать initData: %r", e)
        return None


def is_admin_username(username) -> bool:
    if not username:
        return False
    return str(username).lstrip("@").lower() in set(__import__("config").ADMIN_USERNAMES)
