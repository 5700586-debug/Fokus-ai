import asyncio
import os

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)
from dotenv import load_dotenv


load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise ValueError("BOT_TOKEN .env faylida topilmadi")


dp = Dispatcher()

menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📊 Hisobot")],
        [KeyboardButton(text="🤖 AI Tahlil")],
        [KeyboardButton(text="📦 Ombor")],
        [KeyboardButton(text="⚙️ Sozlamalar")],
    ],
    resize_keyboard=True,
)


@dp.message(CommandStart())
async def start_handler(message: Message) -> None:
    await message.answer(
        "Assalomu alaykum!\n"
        "Fokus AI botiga xush kelibsiz! 🚀",
        reply_markup=menu,
    )


@dp.message(F.text == "📊 Hisobot")
async def report_handler(message: Message) -> None:
    await message.answer("📊 Hisobot bo‘limi tez orada ishga tushadi.")


@dp.message(F.text == "🤖 AI Tahlil")
async def analysis_handler(message: Message) -> None:
    await message.answer("🤖 AI Tahlil bo‘limi tayyorlanmoqda.")


@dp.message(F.text == "📦 Ombor")
async def warehouse_handler(message: Message) -> None:
    await message.answer("📦 Ombor nazorati bo‘limi tayyorlanmoqda.")


@dp.message(F.text == "⚙️ Sozlamalar")
async def settings_handler(message: Message) -> None:
    await message.answer("⚙️ Sozlamalar bo‘limi tez orada qo‘shiladi.")


async def main() -> None:
    bot = Bot(token=TOKEN)

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())