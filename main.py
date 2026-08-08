import asyncio
import os

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup
from dotenv import load_dotenv
from openai import AsyncOpenAI

from warehouse_ai import WarehouseAI
from config import FOUNDER_ID


load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN .env faylida topilmadi")

if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY .env faylida topilmadi")


dp = Dispatcher()
openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)

# AI Tahlil rejimiga kirgan foydalanuvchilar
ai_users: set[int] = set()


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
    if message.from_user:
        ai_users.discard(message.from_user.id)
        
        if message.from_user.id == FOUNDER_ID:
            greeting = "Assalomu alaykum, Asoschi! 👑\nFokus AI botingiz tayyor!"
        else:
            greeting = "Assalomu alaykum!\nFokus AI botiga xush kelibsiz! 🚀"
            
        await message.answer(greeting, reply_markup=menu)


@dp.message(F.text == "📊 Hisobot")
async def report_handler(message: Message) -> None:
    ai = WarehouseAI()

    result = ai.analyze(
        old_stock=100000,
        new_products=50000,
        expenses=20000,
        computer_stock=125000,
        old_margin=20,
        new_margin=15,
    )

    await message.answer(result)


@dp.message(F.text == "🤖 AI Tahlil")
async def analysis_handler(message: Message) -> None:
    if message.from_user:
        ai_users.add(message.from_user.id)

    await message.answer(
        "🤖 AI Tahlil rejimi yoqildi.\n"
        "Savolingizni yoki tahlil qilinadigan raqamlarni yozing."
    )


@dp.message(F.text == "📦 Ombor")
async def warehouse_handler(message: Message) -> None:
    if message.from_user:
        ai_users.discard(message.from_user.id)

    await message.answer("📦 Ombor nazorati bo‘limi tayyorlanmoqda.")


@dp.message(F.text == "⚙️ Sozlamalar")
async def settings_handler(message: Message) -> None:
    if message.from_user:
        ai_users.discard(message.from_user.id)

    await message.answer("⚙️ Sozlamalar bo‘limi tez orada qo‘shiladi.")


@dp.message(F.text)
async def ai_message_handler(message: Message) -> None:
    if not message.from_user or message.from_user.id not in ai_users:
        return

    user_text = message.text
    if not user_text:
        return

    waiting_message = await message.answer("⏳ Tahlil qilinyapti...")

    try:
        response = await openai_client.responses.create(
            model="gpt-5-mini",
            instructions=(
                "Sen Fokus AI nomli biznes yordamchisisan. "
                "O‘zbek tilida sodda, aniq va amaliy javob ber. "
                "Moliyaviy raqamlarni ehtiyotkorlik bilan tahlil qil. "
                "Ma’lumot yetarli bo‘lmasa, taxmin qilmay, qo‘shimcha "
                "ma’lumot so‘ra."
            ),
            input=user_text,
        )

        answer = response.output_text or "Javob olinmadi."
        await waiting_message.edit_text(answer)

    except Exception as error:
        print(f"OpenAI xatosi: {error}")
        await waiting_message.edit_text(
            "❌ AI bilan bog‘lanishda xato yuz berdi.\n"
            "Terminaldagi xatoni tekshirish kerak."
        )


async def main() -> None:
    bot = Bot(token=BOT_TOKEN)

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
