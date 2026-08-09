import asyncio
import os

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import SimpleEventIsolation
from aiogram.types import (
    ErrorEvent,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from dotenv import load_dotenv
from openai import AsyncOpenAI

import approval
import employees
import invites
import onboarding
import performance_bot
from warehouse_ai import WarehouseAI
from config import FOUNDER_ID
from db import init_db
from roles import (
    ROLES,
    SINGLE_SLOT_ROLES,
    find_user_by_role,
    get_role,
    is_authorized,
    is_single_slot_role,
    list_users,
    remove_user,
    role_name,
    set_role,
)
from storage import SQLiteStorage


load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN .env faylida topilmadi")

if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY .env faylida topilmadi")


init_db()

# events_isolation: bitta foydalanuvchining ketma-ket kelgan xabarlari
# (masalan onboarding savol-javoblari) doim navbat bilan, bir-birini
# bosmasdan qayta ishlansin.
dp = Dispatcher(storage=SQLiteStorage(), events_isolation=SimpleEventIsolation())
openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)

# AI Tahlil rejimiga kirgan foydalanuvchilar
ai_users: set[int] = set()

STRANGER_TEXT = "Hmm… bu bot bilan qiziqib qoldingizmi? 🤨"


async def ensure_authorized(message: Message) -> bool:
    if message.from_user and is_authorized(message.from_user.id):
        return True

    await message.answer(STRANGER_TEXT, reply_markup=ReplyKeyboardRemove())
    return False


menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📊 Hisobot")],
        [KeyboardButton(text="🤖 AI Tahlil")],
        [KeyboardButton(text="📦 Ombor")],
        [KeyboardButton(text="⚙️ Sozlamalar")],
    ],
    resize_keyboard=True,
)

onboarding.register(dp)
approval.register(dp)
performance_bot.register(dp)


@dp.message(CommandStart())
async def start_handler(message: Message, state: FSMContext) -> None:
    if not message.from_user:
        return

    ai_users.discard(message.from_user.id)

    parts = (message.text or "").split(maxsplit=1)
    invite_token = parts[1].strip() if len(parts) > 1 else None

    # Onboarding FAQAT bir martalik invite havolasi orqali boshlanadi —
    # oddiy /start bosgan begona/ruxsatsiz foydalanuvchi bu yerga kirmaydi.
    if invite_token and not is_authorized(message.from_user.id):
        await onboarding.start_onboarding_from_invite(message, state, invite_token)
        return

    if not await ensure_authorized(message):
        return

    if message.from_user.id == FOUNDER_ID:
        greeting = "Assalomu alaykum, Asoschi! 👑\nFokus AI botingiz tayyor!"
    else:
        role = role_name(get_role(message.from_user.id))
        greeting = f"Assalomu alaykum!\nFokus AI botiga xush kelibsiz! 🚀\nRolingiz: {role}"

    await message.answer(greeting, reply_markup=menu)


@dp.message(F.text == "📊 Hisobot")
async def report_handler(message: Message) -> None:
    if not await ensure_authorized(message):
        return

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
    if not await ensure_authorized(message):
        return

    if message.from_user:
        ai_users.add(message.from_user.id)

    await message.answer(
        "🤖 AI Tahlil rejimi yoqildi.\n"
        "Savolingizni yoki tahlil qilinadigan raqamlarni yozing."
    )


@dp.message(F.text == "📦 Ombor")
async def warehouse_handler(message: Message) -> None:
    if not await ensure_authorized(message):
        return

    if message.from_user:
        ai_users.discard(message.from_user.id)

    await message.answer("📦 Ombor nazorati bo‘limi tayyorlanmoqda.")


@dp.message(F.text == "⚙️ Sozlamalar")
async def settings_handler(message: Message) -> None:
    if not await ensure_authorized(message):
        return

    if message.from_user:
        ai_users.discard(message.from_user.id)

    await message.answer("⚙️ Sozlamalar bo‘limi tez orada qo‘shiladi.")


@dp.message(Command("invite"))
async def invite_handler(message: Message) -> None:
    if not message.from_user or message.from_user.id != FOUNDER_ID:
        return

    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 2:
        role_list = "\n".join(f"• {key} — {name}" for key, name in ROLES.items() if key != "founder")
        single_slot_list = ", ".join(sorted(SINGLE_SLOT_ROLES))
        await message.answer(
            "Foydalanish:\n"
            "/invite <role_key> <filial nomi> — filialga biriktirilgan rollar uchun\n"
            f"/invite <role_key> — {single_slot_list} kabi umumiy rollar uchun "
            "(filial so‘ralmaydi, faqat 1 kishi)\n\n"
            "Mavjud rollar:\n" + role_list
        )
        return

    role_key = parts[1].strip()
    if role_key not in ROLES or role_key == "founder":
        await message.answer(f"❌ Noto‘g‘ri rol kaliti: {role_key}")
        return

    if is_single_slot_role(role_key):
        branch = None

        existing_user = find_user_by_role(role_key)
        if existing_user is not None:
            await message.answer(
                f"❌ {role_name(role_key)} lavozimida allaqachon xodim bor "
                f"(user_id: {existing_user}). Bu rol uchun faqat 1 kishi bo‘lishi mumkin."
            )
            return

        if invites.has_pending_invite_for_role(role_key):
            await message.answer(
                f"❌ {role_name(role_key)} uchun allaqachon faol taklif havolasi mavjud. "
                "Avval uni yakunlang yoki muddati tugashini kuting."
            )
            return
    else:
        if len(parts) < 3 or not parts[2].strip():
            await message.answer(f"Foydalanish: /invite {role_key} <filial nomi>")
            return
        branch = parts[2].strip()

    token = invites.create_invite(role_key, branch, created_by=FOUNDER_ID)
    me = await message.bot.get_me()
    link = f"https://t.me/{me.username}?start={token}"
    branch_line = f"Filial: {branch}" if branch else "Filial: Umumiy (barcha filiallar)"

    await message.answer(
        "✅ Taklif havolasi yaratildi (2 soat amal qiladi):\n"
        f"{link}\n\n"
        f"Rol: {role_name(role_key)}\n{branch_line}"
    )


@dp.message(Command("setrole"))
async def set_role_handler(message: Message) -> None:
    if not message.from_user or message.from_user.id != FOUNDER_ID:
        return

    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 3 or not parts[1].strip().lstrip("-").isdigit():
        role_list = "\n".join(f"• {key} — {name}" for key, name in ROLES.items() if key != "founder")
        await message.answer(
            "Foydalanish: /setrole <user_id> <role_key>\n\nMavjud rollar:\n" + role_list
        )
        return

    user_id = int(parts[1].strip())
    role_key = parts[2].strip()

    if role_key not in ROLES or role_key == "founder":
        await message.answer(f"❌ Noto‘g‘ri rol kaliti: {role_key}")
        return

    if is_single_slot_role(role_key):
        existing_user = find_user_by_role(role_key)
        if existing_user is not None and existing_user != user_id:
            await message.answer(
                f"❌ {role_name(role_key)} lavozimida allaqachon xodim bor "
                f"(user_id: {existing_user}). Bu rol uchun faqat 1 kishi bo‘lishi mumkin."
            )
            return

    if set_role(user_id, role_key, set_by=message.from_user.id):
        await message.answer(f"✅ {user_id} uchun rol o‘rnatildi: {role_name(role_key)}")
    else:
        await message.answer("❌ Rol o‘rnatib bo‘lmadi.")


@dp.message(Command("removeuser"))
async def remove_user_handler(message: Message) -> None:
    if not message.from_user or message.from_user.id != FOUNDER_ID:
        return

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip().lstrip("-").isdigit():
        await message.answer("Foydalanish: /removeuser <user_id>")
        return

    user_id = int(parts[1].strip())
    if remove_user(user_id):
        await message.answer(f"✅ {user_id} ruxsat etilganlar ro‘yxatidan o‘chirildi.")
    else:
        await message.answer(f"ℹ️ {user_id} ro‘yxatda topilmadi.")


@dp.message(Command("listusers"))
async def list_users_handler(message: Message) -> None:
    if not message.from_user or message.from_user.id != FOUNDER_ID:
        return

    users = list_users()
    if not users:
        await message.answer(
            "Ro‘yxat bo‘sh — hozircha faqat asoschi (siz) kira oladi."
        )
        return

    lines = "\n".join(
        f"{user_id} — {role_name(info['role'])}" for user_id, info in sorted(users.items())
    )
    await message.answer(f"Ruxsat etilgan foydalanuvchilar:\n{lines}")


@dp.message(Command("profile"))
async def profile_handler(message: Message) -> None:
    if not message.from_user or message.from_user.id != FOUNDER_ID:
        return

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip().lstrip("-").isdigit():
        await message.answer("Foydalanish: /profile <user_id>")
        return

    user_id = int(parts[1].strip())
    card = employees.format_founder_card(user_id)
    if card is None:
        await message.answer(f"ℹ️ {user_id} uchun anketa topilmadi.")
        return

    await message.answer(card)


@dp.message(F.text)
async def ai_message_handler(message: Message) -> None:
    if not message.from_user or message.from_user.id not in ai_users:
        return

    if not await ensure_authorized(message):
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


@dp.errors()
async def error_handler(event: ErrorEvent, bot: Bot) -> None:
    print(f"Bot xatosi: {event.exception!r}")

    update = event.update
    user_id = None
    if update.message and update.message.from_user:
        user_id = update.message.from_user.id
    elif update.callback_query and update.callback_query.from_user:
        user_id = update.callback_query.from_user.id

    if user_id is None:
        return

    try:
        await bot.send_message(
            user_id,
            "⚠️ Kutilmagan xatolik yuz berdi. Iltimos, oxirgi xabaringizni "
            "qayta yuboring yoki /start ni bosing.",
        )
    except Exception as notify_error:
        print(f"Foydalanuvchiga xato haqida xabar berib bo'lmadi: {notify_error!r}")


async def main() -> None:
    bot = Bot(token=BOT_TOKEN)

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
