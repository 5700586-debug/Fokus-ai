import asyncio
import os

from aiogram import BaseMiddleware, Bot, Dispatcher, F
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

# ``load_dotenv()`` va ``init_db()`` boshqa har qanday loyiha modulidan
# OLDIN ishga tushishi shart: ``db.py``, ``roles.py`` kabi modullar
# ``DATABASE_URL``/``FOKUS_DATA_DIR``ni IMPORT vaqtida o'qiydi va (Postgres
# rejimida) ``roles.py`` import vaqtidayoq ``allowed_users`` jadvalidan
# o'qiydi — agar bu quyidagi ``import approval`` va h.k.dan keyin
# chaqirilsa, ``.env``dagi qiymatlar e'tiborga olinmaydi va/yoki sxema
# hali yaratilmagan jadvalga so'rov yuboriladi.
load_dotenv()

from db import init_db  # noqa: E402

try:
    init_db()
except Exception:
    print(
        "❌ init_db() muvaffaqiyatsiz tugadi — bot ishga tushmaydi. "
        "DATABASE_URL to'g'ri ekanini (host/port/foydalanuvchi/parol, "
        "bo'sh joy yoki qator ko'chirishsiz) va Supabase Session Pooler "
        "manzili ishlayotganini tekshiring."
    )
    raise

import approval  # noqa: E402
import calibration_bot  # noqa: E402
import cash_shift_bot  # noqa: E402
import discipline_bot  # noqa: E402
import employees  # noqa: E402
import health_server  # noqa: E402
import inventory_bot  # noqa: E402
import invites  # noqa: E402
import onboarding  # noqa: E402
import performance_bot  # noqa: E402
import saturn_group_bot  # noqa: E402
import supplier_chat_bot  # noqa: E402
from config import ENVIRONMENT, FOUNDER_ID  # noqa: E402
from roles import (  # noqa: E402
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
from storage import SQLiteStorage  # noqa: E402

# ENVIRONMENT=test bo'lsa TEST_BOT_TOKEN o'qiladi, BOT_TOKEN emas — bu ikki
# BUTUNLAY BOSHQA nomli muhit o'zgaruvchi, shuning uchun ikkalasi bir xil
# ``.env``da tursa ham, test jarayoni productionning tokenini hech qachon
# ishlatib qo'ymaydi (va aksincha).
_TOKEN_VAR_NAME = "TEST_BOT_TOKEN" if ENVIRONMENT == "test" else "BOT_TOKEN"
BOT_TOKEN = os.getenv(_TOKEN_VAR_NAME)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not BOT_TOKEN:
    raise ValueError(
        f"{_TOKEN_VAR_NAME} .env faylida topilmadi (ENVIRONMENT={ENVIRONMENT!r})"
    )

if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY .env faylida topilmadi")

# Xavfsiz startup banneri: bot tokenining o'zi HECH QACHON to'liq
# loglanmaydi — faqat ":" dan oldingi raqamli bot ID (bu Telegram
# @username/link orqali ham ochiq, sir emas) va muhit nomi ko'rsatiladi.
# Shu orqali operator loglarda "test" muhitga production tokeni yoki
# aksincha noto'g'ri joylashtirilganini darhol ko'rishi mumkin.
_bot_id_prefix = BOT_TOKEN.split(":", 1)[0] if ":" in BOT_TOKEN else "?"
print(f"🚀 Fokus AI ishga tushmoqda — ENVIRONMENT={ENVIRONMENT}, bot_id={_bot_id_prefix}")

# events_isolation: bitta foydalanuvchining ketma-ket kelgan xabarlari
# (masalan onboarding savol-javoblari) doim navbat bilan, bir-birini
# bosmasdan qayta ishlansin.
dp = Dispatcher(storage=SQLiteStorage(), events_isolation=SimpleEventIsolation())
openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)

# AI Tahlil rejimiga kirgan foydalanuvchilar
ai_users: set[int] = set()

STRANGER_TEXT = "Hmm… bu bot bilan qiziqib qoldingizmi? 🤨"

CANCEL_TEXT = "❌ Bekor qilish"
BACK_TEXT = "🔙 Orqaga"


class _ClearStaleStateMiddleware(BaseMiddleware):
    """Foydalanuvchi biror ko'p-bosqichli oqimda (masalan jarima uchun
    nizom raqami kutilayotgan holatda) "qotib qolgan" bo'lsa, keyingi
    buyruq (``/...``) yoki Orqaga/Bekor qilish tugmasi HAR DOIM ishlashi
    kerak — aks holda eski ``StateFilter``ga tayanadigan handler
    (masalan "nizom raqamini kiriting" kutuvchisi) buyruqni "matn kiritish"
    deb noto'g'ri yutib oladi.

    ``dp.message.outer_middleware`` YETARLI EMAS: aiogram'da outer
    middleware faqat filtrlar ALLAQACHON mos handlerni tanlagandan KEYIN
    ishga tushadi (``TelegramEventObserver.trigger`` avval ``handler.check()``
    bilan mos handlerni topadi, keyin uni middleware bilan o'raydi) — shu
    payt esa allaqachon kech. Shuning uchun bu middleware ENG YUQORI
    ``dp.update`` darajasida ro'yxatdan o'tadi — bu butun marshrutlashdan
    OLDIN ishlaydi. ``StateFilter`` esa storage'ga qayta so'rov
    yubormaydi, ``data["raw_state"]``dagi keshlangan qiymatga tayanadi —
    shuning uchun holatni tozalagandan keyin ``data["raw_state"]``ni ham
    ``None``ga o'rnatish SHART, aks holda kesh eski qiymatni ko'rsatib
    qoladi.
    """

    async def __call__(self, handler, event, data: dict):
        message: Message | None = getattr(event, "message", None)
        text = getattr(message, "text", None) or ""
        looks_like_escape = text.startswith("/") or text in (CANCEL_TEXT, BACK_TEXT)

        if looks_like_escape:
            state: FSMContext | None = data.get("state")
            if state is not None and await state.get_state() is not None:
                await state.clear()
                data["raw_state"] = None

        return await handler(event, data)


dp.update.outer_middleware(_ClearStaleStateMiddleware())


async def ensure_authorized(message: Message) -> bool:
    if message.from_user and is_authorized(message.from_user.id):
        return True

    await message.answer(STRANGER_TEXT, reply_markup=ReplyKeyboardRemove())
    return False


# --------------------------------------------------------------- menyu --

# Har bir bo'lim allaqachon mavjud va testlangan buyruqlarni ko'rsatadi —
# tugma matni doim "/buyruq" bilan boshlanadi, shuning uchun bosilganda
# aynan shu buyruqning o'z (mavjud, o'zgartirilmagan) handleri ishga
# tushadi. Bu yerda yangi biznes mantiq yo'q — faqat navigatsiya.
_SHARED_COMMANDS = [
    "/mystars — Mening yulduzlarim",
    "/mymaosh — Mening oylik/bonus holatim",
    "/apellyatsiya — Jarimaga e'tiroz bildirish",
    "/bugungiporga — Bugungi reyting",
    "/oylikturnir — Oylik reyting",
    "/listnizom — Korxona nizomlari",
]

_ROLE_CATEGORIES: dict[str, tuple[str, list[str]]] = {
    "founder": (
        "👑 Asoschi",
        [
            "/invite — Yangi xodimga taklif havolasi",
            "/setrole — Foydalanuvchiga rol berish",
            "/removeuser — Foydalanuvchini ro'yxatdan o'chirish",
            "/listusers — Ro'yxatdagi foydalanuvchilar",
            "/profile — Xodim anketasi (user_id bilan)",
            "/addnizom — Yangi korxona nizomi qo'shish",
            "/setsalary — Fiks oylik belgilash",
            "/maosh — Xodim maoshi/bonusini ko'rish",
            "/setrule — Qoida qiymatini o'zgartirish",
            "/listrules — Barcha qoidalarni ko'rish",
            "/processmonth — Oylik KPI/yulduz hisoblash",
            "/addvehicle — Yangi mashina qo'shish",
        ],
    ),
    "nazoratchi": (
        "🧑‍💼 Nazoratchi",
        [
            "/baholash — Xodimni kunlik baholash/jarima",
            "/kunniyop — Bugungi kunni yopish",
            "/score — Xodimga oylik ball qo'yish",
        ],
    ),
    "kassir": (
        "💰 Kassa",
        [
            "/openshift — Kassa smenasini ochish",
            "/closeshift — Kassa smenasini yopish",
            "/expense — Kassa xarajatini kiritish",
        ],
    ),
    "savdo_boshligi": (
        "📦 Ombor",
        [
            "/invsnapshot — Kunlik ombor hisobotini yuborish",
            "/inventorysummary — Ombor hisobotlari xulosasi",
            "/mealplan — Ovqat rejasini kiritish",
        ],
    ),
    "haydovchi": (
        "🚚 Haydovchi",
        ["/drivercheck — Kunlik mashina/servis tekshiruvi"],
    ),
    "taminotchi": (
        "🛒 Ta'minotchi",
        ["/marketlog — Bozor kuzatuvi qo'shish"],
    ),
    "moliyachi": (
        "💵 Moliyachi",
        [
            "/cashsummary — Kassa xulosasi",
            "/inventorysummary — Ombor xulosasi",
        ],
    ),
}

_SHARED_CATEGORY_TEXT = "⭐ Mening natijalarim"

# Bo'lim tugmasi matni -> shu bo'limdagi buyruqlar ro'yxati (Orqaga
# bosilganda yoki noto'g'ri matn kelganda ishlatiladi).
_CATEGORY_COMMANDS: dict[str, list[str]] = {label: cmds for label, cmds in _ROLE_CATEGORIES.values()}
_CATEGORY_COMMANDS[_SHARED_CATEGORY_TEXT] = _SHARED_COMMANDS


def build_menu(role_key: str | None) -> ReplyKeyboardMarkup:
    """Foydalanuvchining o'z roliga mos yagona menyu — faqat unga
    tegishli (va ruxsat berilgan) bo'limlarni ko'rsatadi.
    """
    rows = [[KeyboardButton(text="🤖 AI Tahlil")]]

    if role_key in _ROLE_CATEGORIES:
        category_text, _ = _ROLE_CATEGORIES[role_key]
        rows.append([KeyboardButton(text=category_text)])

    rows.append([KeyboardButton(text=_SHARED_CATEGORY_TEXT)])
    rows.append([KeyboardButton(text="⚙️ Sozlamalar")])

    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def build_category_menu(commands: list[str]) -> ReplyKeyboardMarkup:
    rows = [[KeyboardButton(text=command)] for command in commands]
    rows.append([KeyboardButton(text=BACK_TEXT)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

onboarding.register(dp)
approval.register(dp)
performance_bot.register(dp)
cash_shift_bot.register(dp)
inventory_bot.register(dp)
calibration_bot.register(dp)
discipline_bot.register(dp, openai_client)
supplier_chat_bot.register(dp, openai_client)
saturn_group_bot.register(dp, openai_client)


@dp.message(CommandStart())
async def start_handler(message: Message, state: FSMContext) -> None:
    if not message.from_user:
        return

    ai_users.discard(message.from_user.id)

    parts = (message.text or "").split(maxsplit=1)
    invite_token = parts[1].strip() if len(parts) > 1 else None

    # Ta'minotchi (tashqi hamkor) taklifi xodim onboarding'idan butunlay
    # mustaqil oqim — avval shu tekshiriladi, token mos kelmasa (odatiy
    # xodim taklifi bo'lsa) False qaytadi va pastdagi oqim davom etadi.
    if invite_token and await supplier_chat_bot.try_claim_invite(message, invite_token):
        return

    # Onboarding FAQAT bir martalik invite havolasi orqali boshlanadi —
    # oddiy /start bosgan begona/ruxsatsiz foydalanuvchi bu yerga kirmaydi.
    if invite_token and not is_authorized(message.from_user.id):
        await onboarding.start_onboarding_from_invite(message, state, invite_token)
        return

    if not await ensure_authorized(message):
        return

    role = get_role(message.from_user.id)
    if message.from_user.id == FOUNDER_ID:
        greeting = "Assalomu alaykum, Asoschi! 👑\nFokus AI botingiz tayyor!"
    else:
        greeting = f"Assalomu alaykum!\nFokus AI botiga xush kelibsiz! 🚀\nRolingiz: {role_name(role)}"

    await message.answer(greeting, reply_markup=build_menu(role))


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


@dp.message(F.text == "⚙️ Sozlamalar")
async def settings_handler(message: Message) -> None:
    if not await ensure_authorized(message):
        return

    if message.from_user:
        ai_users.discard(message.from_user.id)

    await message.answer("⚙️ Sozlamalar bo‘limi tez orada qo‘shiladi.")


@dp.message(F.text.in_(set(_CATEGORY_COMMANDS.keys())))
async def category_menu_handler(message: Message) -> None:
    if not await ensure_authorized(message):
        return

    if message.from_user:
        ai_users.discard(message.from_user.id)

    commands = _CATEGORY_COMMANDS[message.text]
    await message.answer(
        f"{message.text}\nKerakli buyruqni tanlang (ba'zilari qo'shimcha "
        "ma'lumot so'raydi):",
        reply_markup=build_category_menu(commands),
    )


@dp.message(F.text == BACK_TEXT)
async def menu_back_handler(message: Message) -> None:
    if not await ensure_authorized(message):
        return

    if message.from_user:
        ai_users.discard(message.from_user.id)

    await message.answer(
        "🔙 Asosiy menyu.", reply_markup=build_menu(get_role(message.from_user.id))
    )


@dp.message(F.text == CANCEL_TEXT)
async def menu_cancel_handler(message: Message) -> None:
    # Eski FSM holati bu xabar handlerlarga yetib borishidan oldin
    # ``_ClearStaleStateMiddleware`` tomonidan allaqachon tozalangan —
    # bu yerda faqat foydalanuvchiga aniq tasdiq va asosiy menyu
    # qaytariladi.
    if not await ensure_authorized(message):
        return

    if message.from_user:
        ai_users.discard(message.from_user.id)

    await message.answer(
        "✅ Amal bekor qilindi.", reply_markup=build_menu(get_role(message.from_user.id))
    )


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
    scheduler = inventory_bot.start_scheduler(bot)
    calibration_scheduler = calibration_bot.start_scheduler(bot)
    discipline_scheduler = discipline_bot.start_scheduler(bot)
    saturn_group_scheduler = saturn_group_bot.start_scheduler(bot, openai_client)
    # Render "Web Service" $PORT'ga bog'lanishni kutadi (Free planda
    # Background Worker yo'q) — aks holda deploy "Timed out" bo'ladi,
    # garchi bot polling orqali to'liq ishlab tursa ham.
    health_runner = await health_server.start()

    try:
        await dp.start_polling(bot)
    finally:
        await health_runner.cleanup()
        scheduler.shutdown(wait=False)
        calibration_scheduler.shutdown(wait=False)
        discipline_scheduler.shutdown(wait=False)
        saturn_group_scheduler.shutdown(wait=False)
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
