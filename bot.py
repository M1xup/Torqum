import json
import logging

from aiogram import Bot, Dispatcher
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

import config
import db
from security import is_admin_username

log = logging.getLogger("torqum.bot")

bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher()


def webapp_kb(text: str = "Открыть TORQUM") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=text, web_app=WebAppInfo(url=config.PUBLIC_URL))]]
    )


@dp.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "Добро пожаловать в TORQUM — закрытую цифровую витрину премиальных продуктов.\n\n"
        "Нажмите кнопку ниже, чтобы открыть магазин.\n\n"
        "/purchases — мои покупки\n/admin — панель управления",
        reply_markup=webapp_kb(),
    )


@dp.message(Command("admin"))
async def cmd_admin(message: Message):
    if is_admin_username(message.from_user.username):
        await message.answer("Панель управления TORQUM 👇", reply_markup=webapp_kb("Открыть админ-панель"))
    else:
        await message.answer("Эта команда доступна только разработчикам проекта.")


@dp.message(Command("purchases"))
async def cmd_purchases(message: Message):
    orders = [o for o in await db.list_orders(user_id=message.from_user.id) if o["status"] == "paid"]
    if not orders:
        await message.answer("Покупок пока нет. Откройте каталог в TORQUM 🙂", reply_markup=webapp_kb())
        return
    lines = []
    for o in orders:
        items = json.loads(o["items"])
        lines.append(f"Заказ {o['order_id'][:8]}… — {o['total']:.0f} ₽")
        for it in items:
            lines.append(f"  • {it['title']} × {it['qty']}")
        lines.append("")
    await message.answer("Ваши покупки:\n\n" + "\n".join(lines).strip())


async def deliver_order(order: dict):
    """Отправляет пользователю оплаченные товары: тексты сообщением, файлы документом."""
    items = json.loads(order["items"])
    parts = ["Оплата подтверждена — спасибо за покупку! Ваши товары:\n"]
    for it in items:
        p = await db.get_product(it["product_id"])
        if p is None:
            parts.append(f"• {it.get('title', 'Продукт')} — продукт удалён из каталога, напишите в поддержку.")
            continue
        if p["type"] == "file" and p["content"]:
            try:
                await bot.send_document(order["user_id"], document=p["content"], caption=f"TORQUM · {p['title']}")
                continue
            except Exception:
                log.warning("Не удалось отправить файл по URL, отправляю ссылку: %s", p["content"])
                parts.append(f"• {p['title']} — файл: {p['content']}")
        elif p["type"] == "text" and p["content"]:
            parts.append(f"• {p['title']}\n{p['content']}")
        else:
            parts.append(f"• {p['title']} — содержимое не задано, напишите в поддержку.")
    text = "\n\n".join(parts)
    for i in range(0, len(text), 4000):
        await bot.send_message(order["user_id"], text[i:i + 4000])


async def run_polling():
    await dp.start_polling(bot)
