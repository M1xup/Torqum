import os

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
DOMAIN = os.getenv("DOMAIN", "")
PUBLIC_URL = f"https://{DOMAIN}" if DOMAIN else "https://ваш-бот.bothost.ru"

ADMIN_USERNAMES = [
    u.strip().lstrip("@").lower()
    for u in os.getenv("ADMIN_USERNAMES", "M1xup,unclued").split(",")
    if u.strip()
]

# Контакт поддержки: показывается в Mini App, на страницах /policy и /terms
SUPPORT_CONTACT = os.getenv("SUPPORT_CONTACT", "torqumbot@gmail.com")

# RollyPay (заполняется позже, когда будет касса)
ROLLYPAY_API_KEY = os.getenv("ROLLYPAY_API_KEY", "")
ROLLYPAY_SIGNING_SECRET = os.getenv("ROLLYPAY_SIGNING_SECRET", "")
ROLLYPAY_TEST_MODE = os.getenv("ROLLYPAY_TEST_MODE", "true").lower() in ("1", "true", "yes")
ROLLYPAY_API_URL = "https://rollypay.io/api/v1"

WEBHOOK_PATH = "/webhooks/rollypay"

# БД в постоянной папке data/ — не обнуляется при пересборке и redeploy
DB_PATH = os.getenv("DB_PATH", "data/torqum.db")
os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
