import hashlib
import hmac
import json
import urllib.parse


def parse_init_data(token: str, init_data: str):
    """Проверяет подпись Telegram initData и возвращает dict пользователя либо None."""
    if not token or not init_data:
        return None
    try:
        received_hash = ""
        check_items = []
        for pair in init_data.split("&"):
            key, _, value = pair.partition("=")
            if key == "hash":
                received_hash = value
            else:
                check_items.append((key, value))
        check_items.sort()
        data_check_string = "\n".join(f"{k}={v}" for k, v in check_items)
        secret_key = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
        calculated = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        if not received_hash or not hmac.compare_digest(calculated, received_hash):
            return None
        raw_user = dict(check_items).get("user", "{}")
        user = json.loads(urllib.parse.unquote(raw_user))
        return user if isinstance(user, dict) else None
    except Exception:
        return None


def is_admin_username(username) -> bool:
    if not username:
        return False
    return str(username).lstrip("@").lower() in set(__import__("config").ADMIN_USERNAMES)
