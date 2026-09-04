import asyncio
import os

from aiogram import BaseMiddleware, Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart, Filter, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import SimpleEventIsolation
from aiogram.types import (
    CallbackQuery,
    ErrorEvent,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
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
import nazoratchi_bot  # noqa: E402
import onboarding  # noqa: E402
import performance_bot  # noqa: E402
import recruiting_bot  # noqa: E402
import saturn_group_bot  # noqa: E402
import supplier_chat_bot  # noqa: E402
from config import ENVIRONMENT, FOUNDER_ID, RECRUITING_BRANCH_ADDRESSES, RECRUITING_BRANCH_NAMES  # noqa: E402
from repositories import recruiting as recruiting_repo  # noqa: E402
from services import founder_today_problems, messages, permissions  # noqa: E402
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

# Markaziy "Saturncha" xabar katalogidan (``services/messages.py``) —
# begona/ro'yxatdan o'tmagan foydalanuvchi uchun ham matn shu yerda
# takrorlanmaydi, bitta manbadan olinadi.
STRANGER_TEXT = messages.GENERIC_DENIAL

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
        state: FSMContext | None = data.get("state")
        current_state = await state.get_state() if state is not None else None

        # Bir martalik onboarding havolasini anketa davomida qayta bosish
        # anketani o'chirmasin. Xodim mavjud FSM ma'lumoti va joriy
        # savol/tugma bilan aynan o'sha nuqtadan davom etadi (invite
        # qayta band qilinmaydi, anketa boshidan boshlanmaydi — qarang
        # ``onboarding.resend_current_step``).
        if (
            message is not None
            and text.startswith("/start")
            and current_state is not None
            and current_state.startswith("OnboardingStates:")
            and state is not None
        ):
            await onboarding.resend_current_step(message, state, current_state)
            return
        # ``_STALE_LABEL_TO_COMMAND``/``_TOP_LEVEL_NAV_TEXTS`` shu modulda
        # pastroqda e'lon qilinadi, lekin bu yerda faqat CHAQIRILGANDA
        # (modul to'liq yuklangandan keyin) o'qiladi — shuning uchun
        # oldindan e'lon qilish shart emas. Kassirning sodda tugmalari
        # ("🟢 Smenani boshlash" va h.k.) va asosiy menyu/bo'lim tugmalari
        # ("💰 Kassa", "👥 Xodimlar" va h.k.) "/" bilan
        # boshlanmaydi, lekin baribir haqiqiy navigatsiya/buyruqqa mos
        # keladi — shuning uchun ular ham "qochish" sifatida hisoblanishi
        # kerak, aks holda eski "qotib qolgan" holat ularni yutib oladi.
        looks_like_escape = (
            text.startswith("/")
            or text in (CANCEL_TEXT, BACK_TEXT)
            or text in _STALE_LABEL_TO_COMMAND
            or text in _TOP_LEVEL_NAV_TEXTS
        )

        if looks_like_escape:
            state: FSMContext | None = data.get("state")
            if state is not None and await state.get_state() is not None:
                await state.clear()
                data["raw_state"] = None

        return await handler(event, data)


_ROLE_TEST_ENTRY_TEXT = "🧪 Rol testi"
_PREVIEW_EXIT_TEXT = "⬅️ Testdan chiqish"
_PREVIEW_BANNER = "⚠️ TEST SANDBOX REJIMI\nBazaga hech narsa yozilmaydi.\n\n"
_PREVIEW_BLOCKED_TEXT = "🧪 Test rejimi — bu amal bazaga yozilmadi."


class _SandboxPreviewMiddleware(BaseMiddleware):
    """Founder uchun '🧪 Rol testi' — boshqa rol menyusini xavfsiz
    ko'rib chiqish, HAQIQIY rol/DB holatiga tegmasdan.

    Shu fayldagi ikkita ``dp.update.outer_middleware``dan (bu va
    ``_ClearStaleStateMiddleware``) BIRINCHI ro'yxatdan o'tadi, shuning
    uchun ular orasida ENG TASHQI qatlam bo'ladi (``MiddlewareManager.
    wrap_middlewares`` ro'yxatni teskari aylanib har birini oldingisiga
    o'raydi — birinchi ro'yxatdan o'tgan birinchi ishlaydi). Aiogram'ning
    o'zining FSM-kontekst middleware'i esa bulardan ham oldin ishlaydi
    (shuning uchun ``data.get("state")`` bu yerda ishonchli mavjud).
    Preview rejimi aktiv bo'lganda bu middleware ``handler(event, data)``ni
    UMUMAN CHAQIRMAYDI — demak hech qanday haqiqiy handler, demak hech
    qanday DB yozuvi ishga tushmaydi (faqat ``_is_sandbox_escape_text``ga
    mos zaxira chiqish holatlari bundan mustasno — pastda qarang). Faqat
    ``ROLES``/``_MENU_ENTRIES``/``permissions.ROLE_PERMISSIONS`` kabi
    MAVJUD, statik konfiguratsiyani o'qiydi — yangi parallel rol/menyu
    tizimi yaratilmagan.
    """

    async def __call__(self, handler, event, data: dict):
        message: Message | None = event.message
        callback = event.callback_query

        user = message.from_user if message is not None else (
            callback.from_user if callback is not None else None
        )
        if user is None:
            return await handler(event, data)

        state: FSMContext | None = data.get("state")
        if state is None:
            return await handler(event, data)

        state_data = await state.get_data()
        preview_role = state_data.get("preview_role")
        preview_picking = state_data.get("preview_picking", False)
        text = message.text if message is not None else None

        if (
            preview_role is None
            and not preview_picking
            and text == _ROLE_TEST_ENTRY_TEXT
            and user.id == FOUNDER_ID
            and ENVIRONMENT == "test"
        ):
            await state.update_data(preview_picking=True)
            await message.answer(
                f"{_PREVIEW_BANNER}Qaysi rolni sinab ko'rmoqchisiz?",
                reply_markup=_preview_role_picker_keyboard(),
            )
            return

        if preview_picking and preview_role is None:
            if callback is not None:
                await callback.answer(_PREVIEW_BLOCKED_TEXT, show_alert=True)
                return
            if text == _PREVIEW_EXIT_TEXT:
                await state.update_data(preview_picking=False)
                await message.answer("Asosiy menyu:", reply_markup=build_menu(user.id))
                return
            if _is_sandbox_escape_text(text):
                await state.clear()
                return await handler(event, data)
            role_key = _PREVIEW_ROLE_NAME_TO_KEY.get(text or "")
            if role_key is None:
                await message.answer(
                    "Iltimos, ro'yxatdagi rollardan birini tanlang.",
                    reply_markup=_preview_role_picker_keyboard(),
                )
                return
            await state.update_data(preview_picking=False, preview_role=role_key, preview_category=None)
            await message.answer(
                f"{_PREVIEW_BANNER}Preview: {ROLES[role_key]} menyusi.",
                reply_markup=_preview_top_menu_keyboard(role_key),
            )
            return

        if preview_role is None:
            return await handler(event, data)

        # Shu nuqtadan boshlab preview_role AKTIV — bu middleware butun
        # UI'ni o'zi boshqaradi, pastdagi haqiqiy handlerlarga umuman
        # o'tkazmaydi.
        if callback is not None:
            await callback.answer(_PREVIEW_BLOCKED_TEXT, show_alert=True)
            return

        if text == _PREVIEW_EXIT_TEXT:
            await state.clear()
            await message.answer("✅ Test rejimidan chiqdingiz.", reply_markup=build_menu(user.id))
            return

        # Zaxira chiqish yo'li: aniq "⬅️ Testdan chiqish" tugmasi
        # bosilmagan bo'lsa ham (masalan eski/keshlangan klaviatura holati
        # tufayli haqiqiy tugma matni yetib bormasa), ``/start`` yoki
        # Founderning o'ziga xos — rol preview'ida HECH QACHON mavjud
        # bo'lmagan — menyu tugmasi baribir sandboxni to'liq tozalab,
        # so'ralgan HAQIQIY amalni bajarishi kerak. Rol kategoriyasi
        # nomlari (masalan "💰 Kassa") bu ro'yxatda YO'Q — ular preview
        # ichida haqiqiy navigatsiya ma'nosiga ega. Boshqa "/" buyruqlar
        # (masalan ``/openshift``) ATAYLAB bu yerga kiritilmagan — sandbox
        # DB-yozuv himoyasi zaiflashtirilmasin.
        if _is_sandbox_escape_text(text):
            await state.clear()
            return await handler(event, data)

        preview_category = state_data.get("preview_category")

        if preview_category is None:
            if text in (BACK_TEXT, CANCEL_TEXT):
                await message.answer(
                    f"{_PREVIEW_BANNER}Preview: {ROLES[preview_role]} menyusi.",
                    reply_markup=_preview_top_menu_keyboard(preview_role),
                )
                return
            if text == _SHARED_CATEGORY_TEXT:
                await state.update_data(preview_category="__shared__")
                await message.answer(
                    f"{_PREVIEW_BANNER}{text}\n\nKerakli buyruqni tanlang:",
                    reply_markup=_preview_category_keyboard(preview_role, "__shared__"),
                )
                return
            category_key = _CATEGORY_LABEL_TO_KEY.get(text or "")
            if category_key is not None and category_key in _visible_categories_for_role(preview_role):
                await state.update_data(preview_category=category_key)
                await message.answer(
                    f"{_PREVIEW_BANNER}{text}\n\nKerakli buyruqni tanlang:",
                    reply_markup=_preview_category_keyboard(preview_role, category_key),
                )
                return
            await message.answer(
                _PREVIEW_BANNER + _PREVIEW_BLOCKED_TEXT,
                reply_markup=_preview_top_menu_keyboard(preview_role),
            )
            return

        if text == BACK_TEXT:
            await state.update_data(preview_category=None)
            await message.answer(
                f"{_PREVIEW_BANNER}Preview: {ROLES[preview_role]} menyusi.",
                reply_markup=_preview_top_menu_keyboard(preview_role),
            )
            return

        await message.answer(
            _PREVIEW_BANNER + _PREVIEW_BLOCKED_TEXT,
            reply_markup=_preview_category_keyboard(preview_role, preview_category),
        )
        return


dp.update.outer_middleware(_SandboxPreviewMiddleware())
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
#
# MUHIM: qaysi tugma ko'rsatilishini rol nomi emas, balki har bir buyruq
# uchun ``services/permissions.has_permission()``ning HAQIQIY natijasi
# hal qiladi (qarang ``_visible_categories``/``_visible_commands``) — shu
# orqali menyu va backenddagi haqiqiy ruxsat hech qachon bir-biridan
# ajralib qolmaydi. Tugma yashirilishi o'zi xavfsizlik EMAS — har bir
# buyruq handleri baribir mustaqil ravishda ``ensure_permission()``/
# ``ensure_any_permission()`` bilan qayta tekshiradi, shuning uchun eski
# tugma/callback/deep-link/qo'lda yozilgan buyruq orqali kirishga
# urinish ham backendda rad etiladi.
# Tartib EKRAN tartibi bilan bir xil (2 ustunli juftlash shu ro'yxat
# bo'yicha hisoblanadi) — qarang ``_SHARED_BUTTON_LABELS``.
_SHARED_COMMANDS = [
    "/mystars — Mening yulduzlarim",
    "/mymaosh — Mening oylik/bonus holatim",
    "/grafik — 📅 Grafikni o'zgartirish (so'rov)",
    "/bugungiporga — Bugungi reyting",
    "/oylikturnir — Oylik reyting",
    "/listnizom — Korxona nizomlari",
    "/apellyatsiya — Ball ayirishga e'tiroz bildirish",
]

_CATEGORY_LABELS: dict[str, str] = {
    "founder": "👑 Asoschi",
    "nazoratchi": "🧑‍💼 Nazoratchi",
    "kassir": "💰 Kassa",
    "savdo_boshligi": "📦 Ombor",
    "haydovchi": "🚚 Haydovchi",
    "taminotchi": "🛒 Ta'minotchi",
    "moliyachi": "💵 Moliyachi",
}
_CATEGORY_LABEL_TO_KEY: dict[str, str] = {label: key for key, label in _CATEGORY_LABELS.items()}

# (bo'lim kaliti, tugma matni, kerakli ACTION_*). Bitta buyruq bir necha
# bo'limda ko'rinishi mumkin (masalan "/inventorysummary" ham ombor, ham
# moliyachi bo'limida) — chunki ikkalasi HAQIQATDA turli ACTION_* orqali
# mustaqil ruxsatlanadi (savdo bo'limi boshlig'i uchun o'z hisoboti,
# moliyachi uchun umumiy ko'rish huquqi).
_MENU_ENTRIES: list[tuple[str, str, str]] = [
    ("founder", "/invite — Yangi xodimga taklif havolasi", permissions.ACTION_MANAGE_INVITES),
    ("founder", "/setrole — Foydalanuvchiga rol berish", permissions.ACTION_MANAGE_ROLES),
    ("founder", "/removeuser — Foydalanuvchini ro'yxatdan o'chirish", permissions.ACTION_REMOVE_USER),
    ("founder", "/listusers — Ro'yxatdagi foydalanuvchilar", permissions.ACTION_LIST_USERS),
    ("founder", "/profile — Xodim anketasi (user_id bilan)", permissions.ACTION_VIEW_PROFILE),
    ("founder", "/addnizom — Yangi korxona nizomi qo'shish", permissions.ACTION_MANAGE_DISCIPLINE_RULES),
    ("founder", "/setnizombahosi — Nizom bandiga standart ball belgilash", permissions.ACTION_MANAGE_DISCIPLINE_RULES),
    ("founder", "/setsalary — Fiks oylik belgilash", permissions.ACTION_SET_SALARY),
    ("founder", "/maosh — Xodim maoshi/bonusini ko'rish", permissions.ACTION_LOOKUP_ANY_SALARY),
    ("founder", "/setrule — Qoida qiymatini o'zgartirish", permissions.ACTION_SET_RULE),
    ("founder", "/listrules — Barcha qoidalarni ko'rish", permissions.ACTION_LIST_RULES),
    ("founder", "/processmonth — Oylik KPI/yulduz hisoblash", permissions.ACTION_PROCESS_MONTH),
    ("founder", "/addvehicle — Yangi mashina qo'shish", permissions.ACTION_MANAGE_VEHICLES),
    ("founder", "/vazifabiriktir — Xodimga doimiy vazifa biriktirish", permissions.ACTION_MANAGE_TASK_ASSIGNMENTS),
    ("founder", "/vazifabekor — Xodimdan doimiy vazifani olib tashlash", permissions.ACTION_MANAGE_TASK_ASSIGNMENTS),
    ("nazoratchi", "/filiallar — Filial bo'yicha xodimlarni ko'rish", permissions.ACTION_EVALUATE_EMPLOYEE),
    ("nazoratchi", "/baholash — Xodimni kunlik baholash/ball ayirish", permissions.ACTION_EVALUATE_EMPLOYEE),
    ("nazoratchi", "/kunniyop — Bugungi kunni yopish", permissions.ACTION_CLOSE_DAY),
    ("nazoratchi", "/score — Xodimga oylik ball qo'yish", permissions.ACTION_SCORE_EMPLOYEE),
    (
        "nazoratchi",
        "/grafiksorov — Grafik o'zgartirish so'rovlari",
        permissions.ACTION_MANAGE_DAILY_SCHEDULE,
    ),
    ("nazoratchi", "/natijam — Ta'minotchi bugungi natijasi", permissions.ACTION_VIEW_SUPPLIER_RESULTS),
    ("kassir", "/openshift — Kassa smenasini ochish", permissions.ACTION_OPEN_CASH_SHIFT),
    ("kassir", "/closeshift — Kassa smenasini yopish", permissions.ACTION_CLOSE_CASH_SHIFT),
    ("kassir", "/expense — Kassa xarajatini kiritish", permissions.ACTION_LOG_CASH_EXPENSE),
    (
        "savdo_boshligi",
        "/invsnapshot — Kunlik ombor hisobotini yuborish",
        permissions.ACTION_SUBMIT_INVENTORY_SNAPSHOT,
    ),
    (
        "savdo_boshligi",
        "/inventorysummary — Ombor hisobotlari xulosasi",
        permissions.ACTION_SUBMIT_INVENTORY_SNAPSHOT,
    ),
    ("savdo_boshligi", "/mealplan — Ovqat rejasini kiritish", permissions.ACTION_ENTER_MEAL_PLAN),
    ("haydovchi", "/drivercheck — Kunlik mashina/servis tekshiruvi", permissions.ACTION_DRIVER_DAILY_CHECK),
    ("taminotchi", "/marketlog — Bozor kuzatuvi qo'shish", permissions.ACTION_LOG_MARKET_OBSERVATION),
    ("taminotchi", "/xarid — Bugungi bozorlikni xarid qilish", permissions.ACTION_RECORD_SUPPLIER_PURCHASE),
    ("taminotchi", "/natijam — Bugungi natijangiz", permissions.ACTION_VIEW_SUPPLIER_RESULTS),
    ("moliyachi", "/cashsummary — Kassa xulosasi", permissions.ACTION_VIEW_CASH_SUMMARY),
    ("moliyachi", "/inventorysummary — Ombor xulosasi", permissions.ACTION_VIEW_INVENTORY_SUMMARY),
]

_SHARED_CATEGORY_TEXT = "⭐ Mening natijalarim"
_ALL_MENU_BUTTON_TEXTS = set(_CATEGORY_LABELS.values()) | {_SHARED_CATEGORY_TEXT}


def _visible_categories(user_id: int) -> list[str]:
    """Foydalanuvchi kamida bitta amalga haqiqatda ruxsatli bo'lgan
    bo'limlar — rol nomidan emas, ``has_permission()``dan hisoblanadi.

    Founder uchun bitta istisno: Founderning ``has_permission()`` bypass'i
    UNIVERSAL (istalgan amalga ``True``), shuning uchun naiv hisoblash
    Founderga BARCHA bo'lim tugmasini (kassir, haydovchi va h.k.) ham
    ko'rsatib yuborardi — bu xavfsizlik emas, sof UX muammosi (Founder
    o'zining "👑 Asoschi" bo'limida barcha o'ziga xos buyruqlarni ko'radi,
    boshqa xodimlarning kundalik menyusi bilan chalkashmasin). Backend
    tekshiruvi (``ensure_permission``) buni cheklamaydi — Founder
    istalgan buyruqni qo'lda yozib ishlata oladi, faqat tugma ko'p
    bo'lim bilan tirband bo'lib qolmasligi uchun menyuda faqat o'z
    bo'limi ko'rsatiladi.
    """
    if get_role(user_id) == "founder":
        return ["founder"] if any(cat == "founder" for cat, _label, _action in _MENU_ENTRIES) else []

    return [
        category_key
        for category_key in _CATEGORY_LABELS
        if any(
            permissions.has_permission(user_id, action)
            for cat, _label, action in _MENU_ENTRIES
            if cat == category_key
        )
    ]


def _visible_commands(user_id: int, category_key: str) -> list[str]:
    return [
        label
        for cat, label, action in _MENU_ENTRIES
        if cat == category_key and permissions.has_permission(user_id, action)
    ]


def _visible_categories_for_role(role_key: str) -> list[str]:
    """``_visible_categories``ning rol-kalitiga asoslangan varianti —
    haqiqiy foydalanuvchi/DB o'rniga to'g'ridan-to'g'ri statik
    ``permissions.ROLE_PERMISSIONS``dan hisoblaydi (🧪 Rol testi preview
    uchun — hech qanday DB so'rovi yubormaydi)."""
    role_actions = permissions.ROLE_PERMISSIONS.get(role_key, set())
    return [
        category_key
        for category_key in _CATEGORY_LABELS
        if category_key != "founder"
        and any(action in role_actions for cat, _label, action in _MENU_ENTRIES if cat == category_key)
    ]


def _visible_commands_for_role(role_key: str, category_key: str) -> list[str]:
    role_actions = permissions.ROLE_PERMISSIONS.get(role_key, set())
    return [
        label
        for cat, label, action in _MENU_ENTRIES
        if cat == category_key and action in role_actions
    ]


_FOUNDER_MENU_LABELS = [
    "👤 Xodim qo'shish",
    "📢 Ishga e'lon berish",
    "👥 Xodimlar",
    "🏬 Do'konlar",
    "💰 Smenalarni ko'rish",
    "🚨 Bugungi muammolar",
    "⚙️ Sozlamalar",
]

# ``_SandboxPreviewMiddleware``ning zaxira chiqish yo'li uchun — rol
# preview'ida HECH QACHON haqiqiy kategoriya nomi bo'lmaydigan,
# Founderga xos menyu tugmalari (qarang shu klass docstringi).
_SANDBOX_ESCAPE_TEXTS = set(_FOUNDER_MENU_LABELS) | {"⚙️ Sozlamalar"}


def _is_sandbox_escape_text(text: str | None) -> bool:
    """``/start`` (deep-link tokeni bilan ham) va Founderga xos real
    menyu tugmalari — sandbox "qotib" qolgan taqdirda ham (masalan
    aniq "⬅️ Testdan chiqish" matni yetib bormasa) xavfsiz zaxira
    chiqish yo'li. ATAYLAB faqat shu ikkitasi — boshqa "/" buyruqlar
    (masalan ``/openshift``) sandbox DB-yozuv himoyasini zaiflashtirib
    qo'ymasligi uchun bu ro'yxatga kiritilmagan.
    """
    if text is None:
        return False
    return text == "/start" or text.startswith("/start ") or text in _SANDBOX_ESCAPE_TEXTS

# Asosiy (top-level) navigatsiya tugmalari — bo'lim tugmalari
# (``_ALL_MENU_BUTTON_TEXTS``), Foundening sodda menyusi va "AI
# Tahlil"/"Sozlamalar" tugmalari. "/" bilan boshlanmaydi, shuning uchun
# ``_ClearStaleStateMiddleware`` ularni ham "qochish" deb tanishi kerak
# (qarang shu klassning docstringi) — aks holda foydalanuvchi ko'p
# bosqichli oqimda (masalan onboarding yoki /expense) qotib qolgan
# holatda shu tugmalardan birini bossa, eski holat uni yutib olishi
# mumkin edi.
_TOP_LEVEL_NAV_TEXTS = _ALL_MENU_BUTTON_TEXTS | set(_FOUNDER_MENU_LABELS) | {"⚙️ Sozlamalar"}


def _paired_keyboard_rows(labels: list[str]) -> list[list[KeyboardButton]]:
    """Matnlarni 2 tadan qatorlab joylashtiradi — oxirida bitta qolsa
    alohida qatorda (mobilda tugmalar siqilib qolmasligi uchun)."""
    return [
        [KeyboardButton(text=label) for label in labels[i:i + 2]]
        for i in range(0, len(labels), 2)
    ]


def build_menu(user_id: int) -> ReplyKeyboardMarkup:
    """Foydalanuvchining HAQIQIY (joriy) ruxsatlariga mos yagona menyu.

    Founder uchun soddalashtirilgan sodda menyu (``_FOUNDER_MENU_LABELS``)
    — boshqa rollar uchun mantiq o'zgarmagan.
    """
    if get_role(user_id) == "founder":
        rows = _paired_keyboard_rows(_FOUNDER_MENU_LABELS)
        if ENVIRONMENT == "test":
            rows.append([KeyboardButton(text=_ROLE_TEST_ENTRY_TEXT)])
        return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, is_persistent=True)

    rows = []

    for category_key in _visible_categories(user_id):
        rows.append([KeyboardButton(text=_CATEGORY_LABELS[category_key])])

    rows.append([KeyboardButton(text=_SHARED_CATEGORY_TEXT)])
    rows.append([KeyboardButton(text="⚙️ Sozlamalar")])

    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, is_persistent=True)


def _bare_command(label: str) -> str:
    """``"/invite — Yangi xodimga taklif havolasi"`` -> ``"/invite"``.

    Reply keyboard tugmasida ko'rsatilgan MATNNING O'ZI bosilganda
    Telegram tomonidan xabar sifatida yuboriladi — agar butun izohli
    yorliq tugma matni sifatida ishlatilsa, "/invite — Yangi xodimga..."
    o'sha holicha ``message.text``ga tushib, ``Command`` filtri buni
    "/invite" + argument ("— Yangi ...") deb noto'g'ri talqin qilib
    qo'yardi (masalan ``/invite`` handleri "— " ni rol kaliti deb
    qabul qilib "Noto'g'ri rol kaliti: —" xatosini chiqargan). Shuning
    uchun tugmaning o'zida FAQAT toza buyruq yuboriladi, to'liq izohli
    matn esa bo'lim xabarining tanasida (o'qish uchun) ko'rsatiladi.
    """
    return label.split(" — ", 1)[0].strip()


# Kassir uchun sodda, emojili tugma matnlari — haqiqiy buyruq
# (``/openshift`` va h.k.) o'zgarmaydi, faqat tugmada ko'rinadigan matn
# almashadi. Haqiqiy marshrutlash ``_STALE_LABEL_TO_COMMAND`` orqali
# (pastda) shu tugma bosilganda asl buyruqqa qaytariladi.
_KASSIR_BUTTON_LABELS: dict[str, str] = {
    "/openshift": "🟢 Smenani boshlash",
    "/closeshift": "🔴 Smenani topshirish",
    "/expense": "💸 Xarajat kiritish",
}

# Nazoratchi uchun sodda tugma matnlari — kassirning yuqoridagi
# patterniga o'xshash: haqiqiy buyruq o'zgarmaydi, faqat tugmada
# ko'rinadigan matn almashadi.
_NAZORATCHI_BUTTON_LABELS: dict[str, str] = {
    "/filiallar": "🏬 Filiallar",
    "/baholash": "📋 Xodimni baholash",
    "/kunniyop": "✅ Kunni yopish",
    "/score": "⭐ Oylik ball qo'yish",
    "/grafiksorov": "📅 Grafik so'rovlari",
    "/natijam": "🏆 Bugungi natija",
}

# Qolgan bo'limlar (Asoschi, ombor, haydovchi, ta'minotchi, moliyachi)
# uchun xuddi shu pattern — tugmada xom "/buyruq" ko'rinmasin.
_OTHER_BUTTON_LABELS: dict[str, str] = {
    "/invite": "👤 Taklif havolasi",
    "/setrole": "🎭 Rol berish",
    "/removeuser": "🚫 Foydalanuvchini o'chirish",
    "/listusers": "👥 Foydalanuvchilar",
    "/profile": "🪪 Xodim anketasi",
    "/addnizom": "📜 Nizom qo'shish",
    "/setnizombahosi": "⚖️ Nizom bahosi",
    "/setsalary": "💵 Oylik belgilash",
    "/maosh": "💰 Xodim maoshi",
    "/setrule": "🛠 Qoidani sozlash",
    "/listrules": "📄 Qoidalar",
    "/processmonth": "📊 Oylik hisob",
    "/addvehicle": "🚗 Mashina qo'shish",
    "/vazifabiriktir": "📌 Vazifa berish",
    "/vazifabekor": "❎ Vazifani olib tashlash",
    "/invsnapshot": "📦 Ombor hisoboti",
    "/inventorysummary": "📈 Ombor xulosasi",
    "/mealplan": "🍽 Ovqat rejasi",
    "/drivercheck": "🚚 Mashina tekshiruvi",
    "/marketlog": "📝 Bozor kuzatuvi",
    "/xarid": "🛒 Bozorlik xaridi",
    "/natijam": "🏆 Bugungi natija",
    "/cashsummary": "💵 Kassa xulosasi",
}


def _category_button_labels(category_key: str) -> dict[str, str]:
    if category_key == "kassir":
        return _KASSIR_BUTTON_LABELS
    if category_key == "nazoratchi":
        return _NAZORATCHI_BUTTON_LABELS
    return _OTHER_BUTTON_LABELS

# "⭐ Mening natijalarim" (umumiy) bo'limi uchun sodda tugma matnlari —
# kassir/nazoratchi bilan bir xil pattern: buyruq o'zgarmaydi, faqat
# tugmada ko'rinadigan matn almashadi.
_SHARED_BUTTON_LABELS: dict[str, str] = {
    "/mystars": "⭐ Yulduzlarim",
    "/mymaosh": "💰 Oyligim",
    "/grafik": "📅 Grafik so'rovi",
    "/bugungiporga": "🏆 Bugungi o'rnim",
    "/oylikturnir": "🏅 Oylik reyting",
    "/listnizom": "📋 Nizomlar",
    "/apellyatsiya": "🙋 E'tirozim bor",
}

# Foydalanuvchi qurilmasida keshlanib qolgan ESKI friendly yorliqlar —
# bosilsa hamon o'z buyrug'iga olib borsin.
_LEGACY_BUTTON_LABELS: dict[str, str] = {
    "⚠️ E'tiroz bildirish": "/apellyatsiya",
}


def build_category_menu(
    commands: list[str],
    *,
    button_labels: dict[str, str] | None = None,
    pair_buttons: bool = False,
    pair_back: bool = False,
) -> ReplyKeyboardMarkup:
    button_texts = [
        (button_labels or {}).get(_bare_command(command), _bare_command(command))
        for command in commands
    ]
    if pair_buttons:
        rows = _paired_keyboard_rows(button_texts)
    else:
        rows = [[KeyboardButton(text=text)] for text in button_texts]
    # ``pair_back`` faqat toq sonli tugmali juftlangan bo'limda (hozir —
    # umumiy "natijalarim") oxirgi yolg'iz tugmani "🔙 Orqaga" bilan bir
    # qatorga qo'yadi; boshqa hamma joyda xulq o'zgarmaydi.
    if pair_back and rows and len(rows[-1]) == 1:
        rows[-1].append(KeyboardButton(text=BACK_TEXT))
    else:
        rows.append([KeyboardButton(text=BACK_TEXT)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, is_persistent=True)


# 🧪 Rol testi (sandbox preview) — rol nomlaridan tanlov klaviaturasi.
# ``ROLES``dan to'g'ridan-to'g'ri olinadi, yangi parallel ro'yxat yo'q.
_PREVIEW_ROLE_NAME_TO_KEY: dict[str, str] = {
    name: key for key, name in ROLES.items() if key != "founder"
}


def _preview_role_picker_keyboard() -> ReplyKeyboardMarkup:
    rows = _paired_keyboard_rows(list(_PREVIEW_ROLE_NAME_TO_KEY))
    rows.append([KeyboardButton(text=_PREVIEW_EXIT_TEXT)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, is_persistent=True)


def _preview_top_menu_keyboard(role_key: str) -> ReplyKeyboardMarkup:
    rows = [[KeyboardButton(text=_CATEGORY_LABELS[cat])] for cat in _visible_categories_for_role(role_key)]
    rows.append([KeyboardButton(text=_SHARED_CATEGORY_TEXT)])
    rows.append([KeyboardButton(text=_PREVIEW_EXIT_TEXT)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, is_persistent=True)


def _preview_category_keyboard(role_key: str, category_key: str) -> ReplyKeyboardMarkup:
    """``build_category_menu``ni qayta ishlatib (kassir/nazoratchi sodda
    yorliqlari va juftlash mantig'i bilan birga) o'sha bo'lim tugmalarini
    ko'rsatadi, ustiga preview'ga xos "Testdan chiqish" qatorini
    qo'shadi."""
    if category_key == "__shared__":
        commands = _SHARED_COMMANDS
        button_labels, pair_buttons, pair_back = _SHARED_BUTTON_LABELS, True, True
    else:
        commands = _visible_commands_for_role(role_key, category_key)
        button_labels = _category_button_labels(category_key)
        pair_buttons = True
        pair_back = False

    category_kb = build_category_menu(
        commands,
        button_labels=button_labels,
        pair_buttons=pair_buttons,
        pair_back=pair_back,
    )
    rows = list(category_kb.keyboard) + [[KeyboardButton(text=_PREVIEW_EXIT_TEXT)]]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, is_persistent=True)


# Foydalanuvchi qurilmasida ESKI, hozirgi bot versiyasidan oldin
# yuborilgan izohli tugma ("/invite — Yangi xodimga taklif havolasi")
# hali ham Telegram klaviaturasida saqlanib qolgan bo'lishi mumkin —
# /start yoki istalgan boshqa buyruq bosilib yangi (toza) klaviatura
# ko'rsatilmaguncha, bosilsa aynan shu to'liq matn xabar sifatida
# yuboriladi. Ro'yxat FAQAT hozirgi menyu ishlab chiqaradigan aniq
# yorliqlardan (``_MENU_ENTRIES``/``_SHARED_COMMANDS``) hisoblanadi —
# umumiy matn ko'r-ko'rona kesilmaydi, shuning uchun foydalanuvchi
# qo'lda yozgan haqiqiy argumentlar ("/setrole 123 sotuvchi",
# "/invite sotuvchi") hech qachon bu bilan aralashmaydi.
_STALE_LABEL_TO_COMMAND: dict[str, str] = {
    label: _bare_command(label) for _category, label, _action in _MENU_ENTRIES
}
_STALE_LABEL_TO_COMMAND.update({label: _bare_command(label) for label in _SHARED_COMMANDS})

# Kassirning yangi sodda tugma matnlari ("🟢 Smenani boshlash" va h.k.)
# ham shu xarita orqali asl buyruqqa ("/openshift") normallashtiriladi —
# stale (eski keshlangan) yorliqlar bilan bir xil mexanizm.
_STALE_LABEL_TO_COMMAND.update({friendly: bare for bare, friendly in _KASSIR_BUTTON_LABELS.items()})
_STALE_LABEL_TO_COMMAND.update({friendly: bare for bare, friendly in _NAZORATCHI_BUTTON_LABELS.items()})
_STALE_LABEL_TO_COMMAND.update({friendly: bare for bare, friendly in _SHARED_BUTTON_LABELS.items()})
_STALE_LABEL_TO_COMMAND.update({friendly: bare for bare, friendly in _OTHER_BUTTON_LABELS.items()})
_STALE_LABEL_TO_COMMAND.update(_LEGACY_BUTTON_LABELS)


class _NormalizeStaleMenuButtonMiddleware(BaseMiddleware):
    """Eski (keshlangan) menyu tugmasidan kelgan to'liq izohli matnni
    ("/invite — Yangi xodimga taklif havolasi") shu buyruqning toza
    shakliga ("/invite") almashtiradi — ``Command`` filtri va
    handlerlar ``message.text``ni to'g'ridan-to'g'ri (entities'ga
    qaramasdan) ``split()`` qilgani uchun, aks holda " — izoh" qismi
    argument sifatida noto'g'ri talqin qilinardi (qarang
    ``_bare_command`` docstringi).

    Faqat ``_STALE_LABEL_TO_COMMAND``dagi ANIQ (to'liq mos keluvchi)
    yorliqlar almashtiriladi — foydalanuvchi qo'lda yozgan buyruqlar
    (masalan "/setrole 123 sotuvchi") bu ro'yxatda yo'q, shuning uchun
    o'zgarishsiz qoladi. ``_ClearStaleStateMiddleware`` bilan bir xil
    sababga ko'ra ENG YUQORI ``dp.update`` darajasida ishlaydi — bu
    marshrutlashdan (filtrlar ishga tushishidan) OLDIN bajarilishi
    shart, aks holda ``Command`` filtri allaqachon eski matndan
    argumentni noto'g'ri ajratib ulgurgan bo'ladi. ``Message``/``Update``
    obyektlari o'zgarmas (frozen) bo'lgani uchun to'g'ridan-to'g'ri
    mutatsiya qilinmaydi — ``model_copy(update=...)`` bilan yangi
    nusxa yaratilib, pastga o'sha nusxa uzatiladi.
    """

    async def __call__(self, handler, event, data: dict):
        message: Message | None = getattr(event, "message", None)
        text = getattr(message, "text", None)

        bare_command = _STALE_LABEL_TO_COMMAND.get(text) if text else None
        if bare_command is not None:
            new_message = message.model_copy(update={"text": bare_command})
            event = event.model_copy(update={"message": new_message})

        return await handler(event, data)


dp.update.outer_middleware(_NormalizeStaleMenuButtonMiddleware())

onboarding.register(dp)
approval.register(dp)
performance_bot.register(dp, openai_client)
cash_shift_bot.register(dp)
inventory_bot.register(dp)
calibration_bot.register(dp)
discipline_bot.register(dp, openai_client)
supplier_chat_bot.register(dp, openai_client)
saturn_group_bot.register(dp, openai_client)
recruiting_bot.register(dp, openai_client)
nazoratchi_bot.register(dp, openai_client)


def greeting_for_user(user_id: int) -> str:
    if user_id == FOUNDER_ID:
        return (
            "Assalomu alaykum, Muhammadiy! 👋\n"
            "Tadbirkorning vaqti qadrli. Ishlarni tez va sodda boshqaramiz."
        )
    profile = employees.get_profile(user_id)
    ism = profile.get("ism") if profile else None
    name_part = f", {ism}" if ism else ""
    return (
        f"Assalomu alaykum{name_part}! 👋\n"
        "Saturn jamoasiga xush kelibsiz!\n"
        f"💼 Lavozimingiz: {role_name(get_role(user_id))}\n"
        "Ishlaringizga omad!"
    )


@dp.message(CommandStart())
async def start_handler(message: Message, state: FSMContext) -> None:
    if not message.from_user:
        return

    parts = (message.text or "").split(maxsplit=1)
    invite_token = parts[1].strip() if len(parts) > 1 else None

    # Fokus HR (rekruting) uchun maxsus, sobit "apply" so'zi — tasodifiy
    # taklif token bilan hech qachon mos kelmaydi (tokenlar tasodifiy
    # generatsiya qilinadi), shuning uchun xodim/ta'minotchi taklif
    # oqimlariga umuman ta'sir qilmaydi. Nomzod ichki menyularga
    # kirmaydi — bu butunlay alohida, RBAC'siz "tashqi" oqim.
    if invite_token == "apply":
        await recruiting_bot.start_application_from_deeplink(message, state)
        return

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

    await message.answer(
        greeting_for_user(message.from_user.id),
        reply_markup=build_menu(message.from_user.id),
    )


@dp.message(F.text == "⚙️ Sozlamalar")
async def settings_handler(message: Message) -> None:
    if not await ensure_authorized(message):
        return

    await message.answer("⚙️ Sozlamalar bo‘limi tez orada qo‘shiladi.")


# Founderning yangi sodda menyusidagi tugmalar — mavjud buyruqlarni faqat
# qayta nomlab ko'rsatadi, yangi funksiya qo'shmaydi (qarang
# ``_FOUNDER_MENU_LABELS``).


class InviteFlowStates(StatesGroup):
    choosing_role = State()
    choosing_branch = State()


_INVITE_BACK_TEXT = "⬅️ Orqaga"
_ROLE_NAME_TO_KEY = {name: key for key, name in ROLES.items() if key != "founder"}


def _invite_role_kb() -> ReplyKeyboardMarkup:
    role_names = [name for key, name in ROLES.items() if key != "founder"]
    rows = _paired_keyboard_rows(role_names)
    rows.append([KeyboardButton(text=_INVITE_BACK_TEXT)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def _invite_branch_kb() -> ReplyKeyboardMarkup:
    rows = _paired_keyboard_rows(RECRUITING_BRANCH_NAMES)
    rows.append([KeyboardButton(text=_INVITE_BACK_TEXT)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


async def _finish_invite_creation(message: Message, role_key: str, branch: str | None) -> None:
    # ``/invite``dagi bilan bir xil mavjud tekshiruvlar (biznes mantiq
    # o'zgartirilmagan) — faqat ko'rinadigan matn soddalashtirilgan.
    if is_single_slot_role(role_key):
        existing_user = find_user_by_role(role_key)
        if existing_user is not None:
            await message.answer(
                f"❌ {role_name(role_key)} lavozimida allaqachon xodim bor.",
                reply_markup=build_menu(message.from_user.id),
            )
            return

    # Pending (muddati o'tmagan active/claimed) havola BARCHA rollar
    # uchun tekshiriladi (avval faqat bir kishilik rollarga xos edi) —
    # Founder hech qachon "allaqachon mavjud" deb qo'l ko'tarib
    # qo'yilmasin, aksincha aynan o'sha ishlaydigan havolani ko'rsin.
    me = await message.bot.get_me()
    pending = invites.get_pending_invite_for_role(role_key)
    if pending is not None and pending["status"] == "claimed":
        link = f"https://t.me/{me.username}?start={pending['token']}"
        await message.answer(
            f"ℹ️ {role_name(role_key)} uchun taklif havolasi allaqachon ochilgan "
            f"va xodim anketani to'ldirmoqda:\n{link}\n\n"
            "Faqat shu havolani ochgan xodimning o'zi davom ettira oladi.",
            reply_markup=build_menu(message.from_user.id),
        )
        return

    token = pending["token"] if pending is not None else invites.create_invite(
        role_key, branch, created_by=FOUNDER_ID
    )
    link = f"https://t.me/{me.username}?start={token}"

    await message.answer(
        f"✅ Link tayyor\n{link}", reply_markup=build_menu(message.from_user.id)
    )


# ------------------------------------------------------- ishga e'lon berish --
# Bu oqim "hali nomzod qidiryapmiz" bosqichi — "👤 Xodim qo'shish"
# (odam ALLAQACHON tanlangan, onboarding) dan ATAYLAB mustaqil.
# Faqat mavjud recruiting_vacancies'dan foydalanadi, yangi lavozim
# o'ylab topmaydi; filial<->headcount ``recruiting_vacancy_branches``ga
# yoziladi (qarang repositories/recruiting.py).


class JobAdStates(StatesGroup):
    choosing_vacancy = State()
    choosing_headcount = State()
    entering_custom_headcount = State()
    choosing_branches = State()
    entering_branch_headcount = State()


_JOB_AD_HEADCOUNT_QUICK = (1, 2, 3, 4, 5)
_JOB_AD_OTHER_TEXT = "➕ Boshqa"
_JOB_AD_ALL_BRANCHES_TEXT = "🌐 Barcha filiallar"
_JOB_AD_DONE_TEXT = "✅ Tanlovni tugatish"
_JOB_AD_ADD_MORE_TEXT = "➕ Yana lavozim qo'shish"
_JOB_AD_FINISH_TEXT = "✅ E'lonni tayyorlash"

_JOB_AD_POSITION_EMOJI = {"kassir": "💳", "sotuvchi": "🛒"}

_JOB_AD_COMPANY_NAME = "Saturn"  # mavjud _CONSENT_TEXT'dagi bilan bir xil (recruiting_bot.py)
_JOB_AD_SALARY_TEXT = "1 800 000 – 3 500 000 so'm"
_JOB_AD_AGE_TEXT = "18–45 yosh | Ayol va erkaklar"
_JOB_AD_SHIFT_TEXT = "08:00–18:00 yoki 14:00–01:00"
_JOB_AD_PHONE_TEXT = "+998 94 740 04 74"


def _job_ad_vacancy_kb(vacancies: list[dict]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=v["title"], callback_data=f"jobad_vac:{v['id']}")] for v in vacancies]
    )


def _job_ad_headcount_kb() -> InlineKeyboardMarkup:
    buttons = [InlineKeyboardButton(text=str(n), callback_data=f"jobad_hc:{n}") for n in _JOB_AD_HEADCOUNT_QUICK]
    rows = [buttons[i:i + 5] for i in range(0, len(buttons), 5)]
    rows.append([InlineKeyboardButton(text=_JOB_AD_OTHER_TEXT, callback_data="jobad_hc_other")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _job_ad_branches_kb(selected: set[str]) -> InlineKeyboardMarkup:
    rows = []
    for index, name in enumerate(RECRUITING_BRANCH_NAMES):
        mark = "✅" if name in selected else "⬜"
        rows.append([InlineKeyboardButton(text=f"{mark} {name}", callback_data=f"jobad_branch:{index}")])
    rows.append([InlineKeyboardButton(text=_JOB_AD_ALL_BRANCHES_TEXT, callback_data="jobad_branch_all")])
    rows.append([InlineKeyboardButton(text=_JOB_AD_DONE_TEXT, callback_data="jobad_branch_done")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _job_ad_next_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=_JOB_AD_ADD_MORE_TEXT, callback_data="jobad_more")],
            [InlineKeyboardButton(text=_JOB_AD_FINISH_TEXT, callback_data="jobad_finish")],
        ]
    )


def _job_ad_build_text(positions: list[dict], bot_username: str) -> str:
    total = sum(sum(p["branches"].values()) for p in positions)
    position_lines = [
        f"{_JOB_AD_POSITION_EMOJI.get(p['position_key'], '👤')} {p['title']} — {sum(p['branches'].values())} ta"
        for p in positions
    ]

    all_branches: list[str] = []
    for p in positions:
        for branch in p["branches"]:
            if branch not in all_branches:
                all_branches.append(branch)

    location_lines = [
        f"{branch} — {RECRUITING_BRANCH_ADDRESSES[branch]}" if branch in RECRUITING_BRANCH_ADDRESSES else branch
        for branch in all_branches
    ]

    return (
        "📢 ISHGA TAKLIF QILAMIZ!\n\n"
        f"🏪 {_JOB_AD_COMPANY_NAME}\n\n"
        f"Bo'sh ish o'rinlari — {total} ta:\n\n"
        + "\n".join(position_lines) + "\n\n"
        f"💰 Oylik: {_JOB_AD_SALARY_TEXT}\n"
        "Tajribali xodim bilan yuqoriroq kelishiladi.\n\n"
        f"👥 {_JOB_AD_AGE_TEXT}\n\n"
        f"⏰ Smena:\n{_JOB_AD_SHIFT_TEXT}\n\n"
        "📍 Ish joylari:\n"
        + "\n".join(location_lines) + "\n\n"
        "✅ Intizomli, halol va o'sishga tayyor insonlarni kutamiz.\n\n"
        "👇 Ishga kirish uchun ariza qoldiring:\n"
        f"https://t.me/{bot_username}?start=apply\n\n"
        f"☎️ {_JOB_AD_PHONE_TEXT}\n\n"
        "Barqaror ish. Kuchli jamoa. O'sish imkoniyati."
    )


async def _job_ad_ask_branches(reply_target: Message, state: FSMContext, headcount: int) -> None:
    await state.update_data(current_total_headcount=headcount, current_selected_branches=[])
    await state.set_state(JobAdStates.choosing_branches)
    await reply_target.answer("Qaysi filial(lar)ga xodim kerak?", reply_markup=_job_ad_branches_kb(set()))


async def _job_ad_finish_position(reply_target: Message, state: FSMContext, position: dict) -> None:
    data = await state.get_data()
    positions = list(data.get("job_ad_positions") or [])
    positions.append(position)

    await state.update_data(
        job_ad_positions=positions,
        current_vacancy_id=None, current_vacancy_title=None, current_vacancy_key=None,
        current_total_headcount=None, current_selected_branches=None,
        current_distribute_queue=None, current_distribute_index=None, current_branch_headcounts=None,
    )
    await state.set_state(None)

    branch_summary = ", ".join(f"{branch} — {count} ta" for branch, count in position["branches"].items())
    await reply_target.answer(
        f"✅ {position['title']}: {branch_summary}\n\nYana lavozim qo'shasizmi?",
        reply_markup=_job_ad_next_kb(),
    )


@dp.message(F.text == "📢 Ishga e'lon berish")
async def founder_job_ad_start(message: Message, state: FSMContext) -> None:
    if not await ensure_authorized(message):
        return

    vacancies = recruiting_repo.list_vacancies(active_only=True)
    if not vacancies:
        await message.answer(
            "Hozircha faol vakansiya mavjud emas.", reply_markup=build_menu(message.from_user.id)
        )
        return

    await state.set_state(JobAdStates.choosing_vacancy)
    await state.update_data(job_ad_positions=[])
    await message.answer("Qaysi lavozimga xodim kerak?", reply_markup=_job_ad_vacancy_kb(vacancies))


@dp.callback_query(F.data.startswith("jobad_vac:"), StateFilter(JobAdStates.choosing_vacancy))
async def job_ad_vacancy_pick(callback: CallbackQuery, state: FSMContext) -> None:
    vacancy_id = int(callback.data.split(":", 1)[1])
    vacancy = recruiting_repo.get_vacancy(vacancy_id)
    if vacancy is None or not vacancy["is_active"]:
        await callback.answer("Bu lavozim endi mavjud emas.", show_alert=True)
        return

    data = await state.get_data()
    already_added = {p["vacancy_id"] for p in (data.get("job_ad_positions") or [])}
    if vacancy_id in already_added:
        await callback.answer("Bu lavozim shu e'longa allaqachon qo'shilgan.", show_alert=True)
        return

    await state.update_data(
        current_vacancy_id=vacancy_id, current_vacancy_title=vacancy["title"],
        current_vacancy_key=vacancy["position_key"],
    )
    await state.set_state(JobAdStates.choosing_headcount)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer()
    await callback.message.answer("Nechta xodim kerak?", reply_markup=_job_ad_headcount_kb())


@dp.callback_query(F.data.startswith("jobad_hc:"), StateFilter(JobAdStates.choosing_headcount))
async def job_ad_headcount_pick(callback: CallbackQuery, state: FSMContext) -> None:
    headcount = int(callback.data.split(":", 1)[1])
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer()
    await _job_ad_ask_branches(callback.message, state, headcount)


@dp.callback_query(F.data == "jobad_hc_other", StateFilter(JobAdStates.choosing_headcount))
async def job_ad_headcount_other(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(JobAdStates.entering_custom_headcount)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer()
    await callback.message.answer("Nechta xodim kerak? Musbat butun son kiriting:")


@dp.message(StateFilter(JobAdStates.entering_custom_headcount))
async def job_ad_headcount_custom(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text.isdigit() or int(text) <= 0:
        await message.answer("❌ Musbat butun son kiriting:")
        return

    await _job_ad_ask_branches(message, state, int(text))


@dp.callback_query(F.data.startswith("jobad_branch:"), StateFilter(JobAdStates.choosing_branches))
async def job_ad_branch_toggle(callback: CallbackQuery, state: FSMContext) -> None:
    index = int(callback.data.split(":", 1)[1])
    if index < 0 or index >= len(RECRUITING_BRANCH_NAMES):
        await callback.answer()
        return

    branch = RECRUITING_BRANCH_NAMES[index]
    data = await state.get_data()
    selected = set(data.get("current_selected_branches") or [])
    if branch in selected:
        selected.discard(branch)
    else:
        selected.add(branch)

    await state.update_data(current_selected_branches=list(selected))
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=_job_ad_branches_kb(selected))


@dp.callback_query(F.data == "jobad_branch_all", StateFilter(JobAdStates.choosing_branches))
async def job_ad_branch_select_all(callback: CallbackQuery, state: FSMContext) -> None:
    selected = set(RECRUITING_BRANCH_NAMES)
    await state.update_data(current_selected_branches=list(selected))
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=_job_ad_branches_kb(selected))


@dp.callback_query(F.data == "jobad_branch_done", StateFilter(JobAdStates.choosing_branches))
async def job_ad_branch_done(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    selected = list(data.get("current_selected_branches") or [])
    if not selected:
        await callback.answer("Kamida 1 ta filial tanlang.", show_alert=True)
        return

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer()

    total = data["current_total_headcount"]
    position = {
        "vacancy_id": data["current_vacancy_id"], "title": data["current_vacancy_title"],
        "position_key": data["current_vacancy_key"],
    }

    if len(selected) == 1:
        position["branches"] = {selected[0]: total}
        await _job_ad_finish_position(callback.message, state, position)
        return

    await state.update_data(
        current_distribute_queue=selected, current_distribute_index=0, current_branch_headcounts={},
    )
    await state.set_state(JobAdStates.entering_branch_headcount)
    await callback.message.answer(f"Jami {data['current_vacancy_title']} — {total} ta\n\n{selected[0]} uchun nechta?")


@dp.message(StateFilter(JobAdStates.entering_branch_headcount))
async def job_ad_branch_headcount(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text.isdigit() or int(text) <= 0:
        await message.answer("❌ Musbat butun son kiriting:")
        return

    data = await state.get_data()
    queue = data.get("current_distribute_queue") or []
    index = data.get("current_distribute_index", 0)
    counts = dict(data.get("current_branch_headcounts") or {})

    if index >= len(queue):
        await state.clear()
        await message.answer("❌ Xatolik yuz berdi. Qaytadan boshlang.", reply_markup=build_menu(message.from_user.id))
        return

    counts[queue[index]] = int(text)
    index += 1

    if index < len(queue):
        await state.update_data(current_branch_headcounts=counts, current_distribute_index=index)
        await message.answer(f"{queue[index]} uchun nechta?")
        return

    total = data["current_total_headcount"]
    if sum(counts.values()) != total:
        await state.update_data(current_branch_headcounts={}, current_distribute_index=0)
        await message.answer(
            f"❌ Filiallarga taqsimlangan son jami {total} ta bo'lishi kerak.\n\n"
            f"Qaytadan: {queue[0]} uchun nechta?"
        )
        return

    position = {
        "vacancy_id": data["current_vacancy_id"], "title": data["current_vacancy_title"],
        "position_key": data["current_vacancy_key"], "branches": counts,
    }
    await _job_ad_finish_position(message, state, position)


@dp.callback_query(F.data == "jobad_more")
async def job_ad_add_more(callback: CallbackQuery, state: FSMContext) -> None:
    vacancies = recruiting_repo.list_vacancies(active_only=True)
    if not vacancies:
        await callback.answer("Hozircha faol vakansiya mavjud emas.", show_alert=True)
        return

    await state.set_state(JobAdStates.choosing_vacancy)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer()
    await callback.message.answer("Qaysi lavozimga xodim kerak?", reply_markup=_job_ad_vacancy_kb(vacancies))


@dp.callback_query(F.data == "jobad_finish")
async def job_ad_finish(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    positions = data.get("job_ad_positions") or []
    if not positions:
        await callback.answer()
        return

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer()

    for position in positions:
        recruiting_repo.clear_vacancy_branches(position["vacancy_id"])
        branches_payload = [
            {"branch_name": branch, "headcount": count} for branch, count in position["branches"].items()
        ]
        recruiting_repo.set_vacancy_branches(position["vacancy_id"], branches_payload)
        recruiting_repo.set_vacancy_active(position["vacancy_id"], True)

    await state.clear()
    me = await callback.bot.get_me()
    ad_text = _job_ad_build_text(positions, me.username)
    await callback.message.answer(ad_text, reply_markup=build_menu(callback.from_user.id))


@dp.message(F.text == "👤 Xodim qo'shish")
async def founder_add_employee_handler(message: Message, state: FSMContext) -> None:
    if not await ensure_authorized(message):
        return

    await state.set_state(InviteFlowStates.choosing_role)
    await message.answer("Kim bo'lib ishlaydi?", reply_markup=_invite_role_kb())


@dp.message(StateFilter(InviteFlowStates.choosing_role), F.text == _INVITE_BACK_TEXT)
async def invite_flow_role_back(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Asosiy menyu.", reply_markup=build_menu(message.from_user.id))


@dp.message(StateFilter(InviteFlowStates.choosing_role))
async def invite_flow_choose_role(message: Message, state: FSMContext) -> None:
    role_key = _ROLE_NAME_TO_KEY.get((message.text or "").strip())
    if role_key is None:
        await message.answer("Iltimos, tugmalardan birini tanlang.", reply_markup=_invite_role_kb())
        return

    if is_single_slot_role(role_key):
        await state.clear()
        await _finish_invite_creation(message, role_key, None)
        return

    await state.update_data(role_key=role_key)
    await state.set_state(InviteFlowStates.choosing_branch)
    await message.answer("Qaysi do'konda ishlaydi?", reply_markup=_invite_branch_kb())


@dp.message(StateFilter(InviteFlowStates.choosing_branch), F.text == _INVITE_BACK_TEXT)
async def invite_flow_branch_back(message: Message, state: FSMContext) -> None:
    await state.set_state(InviteFlowStates.choosing_role)
    await message.answer("Kim bo'lib ishlaydi?", reply_markup=_invite_role_kb())


@dp.message(StateFilter(InviteFlowStates.choosing_branch))
async def invite_flow_choose_branch(message: Message, state: FSMContext) -> None:
    branch = (message.text or "").strip()
    if branch not in RECRUITING_BRANCH_NAMES:
        await message.answer("Iltimos, tugmalardan birini tanlang.", reply_markup=_invite_branch_kb())
        return

    data = await state.get_data()
    await state.clear()
    await _finish_invite_creation(message, data["role_key"], branch)


class _HasViewingBranch(Filter):
    """Founder hozir "🏬 Do'konlar" filial kartasini ko'rayotgan bo'lsagina
    ishlaydi (``viewing_branch`` FSM ma'lumotida saqlanadi) — aks holda
    boshqa (global) "👥 Xodimlar" handleri ishlashda davom etadi. Bir xil
    tugma matni ikki xil kontekstda (asosiy menyu / filial kartasi)
    ishlatilgani uchun kerak.
    """

    async def __call__(self, message: Message, state: FSMContext) -> bool | dict:
        if not message.text:
            return False

        data = await state.get_data()
        branch = data.get("viewing_branch")
        if branch is None:
            return False

        return {"viewing_branch": branch}


@dp.message(F.text == "👥 Xodimlar", _HasViewingBranch())
async def founder_branch_employees_handler(message: Message, viewing_branch: str) -> None:
    if not await ensure_authorized(message):
        return

    await message.answer(
        _store_branch_employees_text(viewing_branch),
        reply_markup=_store_subview_keyboard(),
    )


def _employee_list_keyboard() -> InlineKeyboardMarkup | None:
    """"👥 Xodimlar" tugmasi uchun — har bir xodim F.I.Sh. bilan alohida
    tugma (``user_id`` foydalanuvchiga ko'rsatilmaydi, faqat
    ``callback_data``da yashirin identifikator sifatida). Mavjud
    ``roles.list_users()``/``employees.get_profile()``dan qayta
    ishlatiladi — yangi jadval yo'q."""
    users = list_users()
    if not users:
        return None

    rows = []
    for user_id, info in sorted(users.items()):
        profile = employees.get_profile(user_id)
        full_name = (
            " ".join(part for part in (profile.get("familiya"), profile.get("ism")) if part)
            if profile else None
        ) or "-"
        text = f"👤 {full_name} — {role_name(info.get('role'))}"
        rows.append([InlineKeyboardButton(text=text, callback_data=f"founderux_emp:{user_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@dp.message(F.text == "👥 Xodimlar")
async def founder_employees_handler(message: Message) -> None:
    if not await permissions.ensure_permission(message, permissions.ACTION_LIST_USERS):
        return

    keyboard = _employee_list_keyboard()
    if keyboard is None:
        await message.answer("Ro'yxat bo'sh — hozircha faqat asoschi (siz) kira oladi.")
        return

    await message.answer("👥 Xodimlar:", reply_markup=keyboard)


@dp.callback_query(F.data.startswith("founderux_emp:"))
async def founder_employee_card_callback(callback: CallbackQuery) -> None:
    if not await permissions.ensure_permission(callback, permissions.ACTION_LIST_USERS):
        return

    user_id = int(callback.data.split(":", 1)[1])
    card = employees.format_founder_card(user_id)
    if card is None:
        await callback.answer("Ma'lumot topilmadi.", show_alert=True)
        return

    await callback.message.answer(card)
    await callback.answer()


def _today_problems_section_text(title: str, section: dict) -> list[str]:
    lines = [f"{title}: {section['total']} ta"]
    if not section["items"]:
        lines.append("Ma'lumot yo'q.")
        return lines

    for item in section["items"]:
        lines.append(f"• {item['full_name']} — {item['branch']} — {item['date']}")

    remaining = section["total"] - len(section["items"])
    if remaining > 0:
        lines.append(f"...va yana {remaining} ta")
    return lines


def _founder_today_problems_text(summary: dict) -> str:
    lines = ["🚨 Bugungi muammolar", ""]
    lines.extend(_today_problems_section_text("🟡 Bugungi grafigi kiritilmagan faol xodimlar", summary["missing_schedule"]))
    lines.append("")
    lines.extend(_today_problems_section_text("⏳ Kutilayotgan grafik o'zgartirish so'rovlari", summary["pending_requests"]))
    return "\n".join(lines)


@dp.message(F.text == "🚨 Bugungi muammolar")
async def founder_today_problems_handler(message: Message) -> None:
    if not await permissions.ensure_permission(message, permissions.ACTION_VIEW_FOUNDER_TODAY_PROBLEMS):
        return

    summary = founder_today_problems.build_today_problems_summary()
    await message.answer(_founder_today_problems_text(summary))


_BRANCH_BACK_TEXT = "⬅️ Orqaga"


def _branch_button_text(branch: str) -> str:
    return f"📍 {branch}"


def _branch_list_keyboard() -> ReplyKeyboardMarkup:
    rows = [[KeyboardButton(text=_branch_button_text(name))] for name in RECRUITING_BRANCH_NAMES]
    rows.append([KeyboardButton(text=_BRANCH_BACK_TEXT)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, is_persistent=True)


@dp.message(F.text == "🏬 Do'konlar")
async def founder_branches_handler(message: Message, state: FSMContext) -> None:
    if not await ensure_authorized(message):
        return

    await state.update_data(viewing_branch=None)
    await message.answer("🏬 Do'konlar:", reply_markup=_branch_list_keyboard())


@dp.message(F.text == _BRANCH_BACK_TEXT)
async def founder_branches_back_handler(message: Message, state: FSMContext) -> None:
    if not await ensure_authorized(message):
        return

    await state.update_data(viewing_branch=None)
    await message.answer("🔙 Asosiy menyu.", reply_markup=build_menu(message.from_user.id))


# ------------------------------------------------------ 🏬 filial kartasi --

_STORE_CARD_EMPLOYEES_TEXT = "👥 Xodimlar"
_STORE_CARD_SHIFTS_TEXT = "💰 Smenalar"
_STORE_CARD_BACK_TEXT = "⬅️ Do'konlar"
_STORE_SUBVIEW_BACK_TEXT = "⬅️ Filial"

_BRANCH_BUTTON_TEXT_TO_NAME: dict[str, str] = {
    _branch_button_text(name): name for name in RECRUITING_BRANCH_NAMES
}


def _store_card_keyboard() -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text=_STORE_CARD_EMPLOYEES_TEXT), KeyboardButton(text=_STORE_CARD_SHIFTS_TEXT)],
        [KeyboardButton(text=_STORE_CARD_BACK_TEXT)],
    ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, is_persistent=True)


def _store_subview_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=_STORE_SUBVIEW_BACK_TEXT)]],
        resize_keyboard=True,
        is_persistent=True,
    )


def _store_card_text(branch: str) -> str:
    """Faqat mavjud DB/repository ma'lumotlaridan — yangi jadval yoki
    parallel store-management tizimi yaratmasdan. Ma'lumot topilmasa
    "Ma'lumot yo'q" ko'rsatiladi, hech narsa o'ylab topilmaydi."""
    from repositories import cash_shifts as cash_shifts_repo
    import company_time
    from services import cash_shift

    active_employees = employees.list_approved_by_branch(branch)
    today = company_time.today().isoformat()
    today_shifts = cash_shifts_repo.get_shifts_for_branch_date(branch, today)
    last_closed = cash_shifts_repo.get_last_closed_shift(branch)

    lines = [f"🏬 {branch}", "", f"👥 Aktiv xodimlar: {len(active_employees)} kishi"]

    if today_shifts:
        latest = today_shifts[0]
        if latest["status"] == cash_shift.STATUS_OPEN:
            status_label = "🟢 Smena ochiq"
        else:
            status_label = cash_shift_bot._STATUS_LABELS.get(latest["status"], latest["status"])
        lines.append(f"💰 Bugungi smena: {status_label}")
    else:
        lines.append("💰 Bugungi smena: Ma'lumot yo'q")

    open_issue = next(
        (s for s in today_shifts if s["status"] == cash_shift.STATUS_NEEDS_SUPERVISOR_APPROVAL),
        None,
    )
    if open_issue:
        lines.append(
            f"⚠️ Ochiq muammo: Kassa tafovuti tekshiruv kutmoqda (farq: {open_issue.get('difference', 'N/A')})"
        )
    else:
        lines.append("⚠️ Ochiq muammo: Yo'q")

    if last_closed:
        status_label = cash_shift_bot._STATUS_LABELS.get(last_closed["status"], last_closed["status"])
        lines.append(f"🕒 Oxirgi smena: {last_closed['shift_date']} — {status_label}")
    else:
        lines.append("🕒 Oxirgi smena: Ma'lumot yo'q")

    return "\n".join(lines)


def _store_branch_employees_text(branch: str) -> str:
    active_employees = employees.list_approved_by_branch(branch)
    if not active_employees:
        return f"🏬 {branch}\n\n👥 Xodimlar: Ma'lumot yo'q"

    lines = [f"🏬 {branch}", "", "👥 Xodimlar:"]
    for profile in active_employees:
        full_name = " ".join(
            part for part in (profile.get("familiya"), profile.get("ism")) if part
        ) or "-"
        lines.append(f"👤 {full_name} — {role_name(profile.get('role_key'))}")
    return "\n".join(lines)


def _store_branch_shifts_text(branch: str) -> str:
    from repositories import cash_shifts as cash_shifts_repo
    import company_time
    from services import cash_shift

    today = company_time.today().isoformat()
    today_shifts = cash_shifts_repo.get_shifts_for_branch_date(branch, today)
    if not today_shifts:
        return f"🏬 {branch}\n\n💰 Bugungi smenalar: Ma'lumot yo'q"

    summaries = []
    for shift in today_shifts:
        if shift["status"] == cash_shift.STATUS_OPEN:
            summaries.append(
                f"Kassir: {cash_shift_bot._employee_name(shift['employee_id'])}\n"
                f"Status: 🟢 Smena ochiq — hali yopilmagan"
            )
        else:
            summaries.append(cash_shift_bot._format_shift_summary(shift))

    return f"🏬 {branch}\n\n💰 Bugungi smenalar:\n\n" + "\n\n".join(summaries)


@dp.message(F.text.in_(_BRANCH_BUTTON_TEXT_TO_NAME))
async def founder_branch_card_handler(message: Message, state: FSMContext) -> None:
    if not await ensure_authorized(message):
        return

    branch = _BRANCH_BUTTON_TEXT_TO_NAME[message.text]
    await state.update_data(viewing_branch=branch)
    await message.answer(_store_card_text(branch), reply_markup=_store_card_keyboard())


@dp.message(F.text == _STORE_CARD_BACK_TEXT)
async def founder_store_card_back_handler(message: Message, state: FSMContext) -> None:
    if not await ensure_authorized(message):
        return

    await state.update_data(viewing_branch=None)
    await message.answer("🏬 Do'konlar:", reply_markup=_branch_list_keyboard())


@dp.message(F.text == _STORE_SUBVIEW_BACK_TEXT, _HasViewingBranch())
async def founder_store_subview_back_handler(message: Message, viewing_branch: str) -> None:
    if not await ensure_authorized(message):
        return

    await message.answer(_store_card_text(viewing_branch), reply_markup=_store_card_keyboard())


@dp.message(F.text == _STORE_CARD_SHIFTS_TEXT, _HasViewingBranch())
async def founder_branch_shifts_handler(message: Message, viewing_branch: str) -> None:
    if not await ensure_authorized(message):
        return

    await message.answer(
        _store_branch_shifts_text(viewing_branch),
        reply_markup=_store_subview_keyboard(),
    )


@dp.message(F.text == "💰 Smenalarni ko'rish")
async def founder_shift_summary_handler(message: Message) -> None:
    if not await ensure_authorized(message):
        return

    import company_time
    from services import cash_shift

    shift = cash_shift.get_open_shift(message.from_user.id, company_time.today().isoformat())
    if shift is None:
        await message.answer("ℹ️ Bugun uchun smena topilmadi.")
        return

    await message.answer(cash_shift_bot._format_shift_summary(shift))


@dp.message(F.text.in_(_ALL_MENU_BUTTON_TEXTS))
async def category_menu_handler(message: Message) -> None:
    if not await ensure_authorized(message):
        return

    if message.text == _SHARED_CATEGORY_TEXT:
        category_key = None
        commands = _SHARED_COMMANDS
    else:
        category_key = _CATEGORY_LABEL_TO_KEY[message.text]
        commands = _visible_commands(message.from_user.id, category_key)

    if not commands:
        # Rol o'zgargach yoki ruxsat olib tashlangach, eski (mijozda
        # keshlangan) tugma endi bu foydalanuvchiga hech narsa
        # bermaydi — bo'sh bo'lim o'rniga xushmuomalalik bilan asosiy
        # menyuga qaytariladi (qarang "Rol o'zgargach eski tugma endi
        # ishlamasin" talabi).
        await message.answer(
            f"{messages.GENERIC_DENIAL}\nAsosiy menyu:",
            reply_markup=build_menu(message.from_user.id),
        )
        return

    is_shared = category_key is None
    button_labels = _SHARED_BUTTON_LABELS if is_shared else _category_button_labels(category_key)

    if is_shared:
        # Tugmalarning o'zi allaqachon tushunarli (emojili) — xabar
        # tanasida buyruqlar ro'yxatini takrorlash shart emas.
        body = f"{message.text}\nKerakli bo'limni tanlang:"
    else:
        if button_labels:
            # Xom "/buyruq — izoh" matni tugmalar allaqachon sodda bo'lgan
            # bo'limlarda (kassir/nazoratchi) matn tanasida ham ko'rinmasin —
            # tugma yozuvi bilan bir xil, izohsiz.
            display_lines = [button_labels.get(_bare_command(c), _bare_command(c)) for c in commands]
        else:
            display_lines = commands
        command_list = "\n".join(display_lines)
        body = (
            f"{message.text}\n{command_list}\n\nKerakli buyruqni tanlang (ba'zilari "
            "qo'shimcha ma'lumot so'raydi):"
        )

    await message.answer(
        body,
        reply_markup=build_category_menu(
            commands,
            button_labels=button_labels,
            pair_buttons=True,
            pair_back=is_shared,
        ),
    )


@dp.message(F.text == BACK_TEXT)
async def menu_back_handler(message: Message) -> None:
    if not await ensure_authorized(message):
        return

    await message.answer(
        "🔙 Asosiy menyu.", reply_markup=build_menu(message.from_user.id)
    )


@dp.message(F.text == CANCEL_TEXT)
async def menu_cancel_handler(message: Message) -> None:
    # Eski FSM holati bu xabar handlerlarga yetib borishidan oldin
    # ``_ClearStaleStateMiddleware`` tomonidan allaqachon tozalangan —
    # bu yerda faqat foydalanuvchiga aniq tasdiq va asosiy menyu
    # qaytariladi.
    if not await ensure_authorized(message):
        return

    await message.answer(
        "✅ Amal bekor qilindi.", reply_markup=build_menu(message.from_user.id)
    )


@dp.message(Command("invite"))
async def invite_handler(message: Message) -> None:
    if not await permissions.ensure_permission(message, permissions.ACTION_MANAGE_INVITES):
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
    else:
        if len(parts) < 3 or not parts[2].strip():
            await message.answer(f"Foydalanish: /invite {role_key} <filial nomi>")
            return
        branch = parts[2].strip()

    # Pending (muddati o'tmagan active/claimed) havola BARCHA rollar
    # uchun tekshiriladi (avval faqat bir kishilik rollarga xos edi) —
    # Founder hech qachon "allaqachon mavjud" deb qo'l ko'tarib
    # qo'yilmasin, aksincha aynan o'sha ishlaydigan havolani ko'rsin.
    me = await message.bot.get_me()
    pending = invites.get_pending_invite_for_role(role_key)
    if pending is not None and pending["status"] == "claimed":
        link = f"https://t.me/{me.username}?start={pending['token']}"
        await message.answer(
            f"ℹ️ {role_name(role_key)} uchun taklif havolasi allaqachon ochilgan "
            f"va xodim anketani to'ldirmoqda:\n{link}\n\n"
            "Faqat shu havolani ochgan xodimning o'zi davom ettira oladi."
        )
        return

    token = pending["token"] if pending is not None else invites.create_invite(
        role_key, branch, created_by=FOUNDER_ID
    )
    display_branch = pending["branch"] if pending is not None else branch
    link = f"https://t.me/{me.username}?start={token}"
    branch_line = f"Filial: {display_branch}" if display_branch else "Filial: Umumiy (barcha filiallar)"

    await message.answer(
        "✅ Taklif havolasi yaratildi (2 soat amal qiladi):\n"
        f"{link}\n\n"
        f"Rol: {role_name(role_key)}\n{branch_line}"
    )


@dp.message(Command("setrole"))
async def set_role_handler(message: Message) -> None:
    if not await permissions.ensure_permission(message, permissions.ACTION_MANAGE_ROLES):
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
        try:
            # Faqat OLDINDAN mavjud, yakunlanmagan enrollment bo'lsa
            # davom etadi — bu yerda yangi enrollment yaratilmaydi
            # (qarang ``discipline_bot.start_or_resume_rule_learning``).
            await discipline_bot.start_or_resume_rule_learning(message.bot, user_id)
        except Exception as error:
            print(f"Nizom o'qishni davom ettirishda xato (user_id={user_id}): {error!r}")
    else:
        await message.answer("❌ Rol o‘rnatib bo‘lmadi.")


@dp.message(Command("removeuser"))
async def remove_user_handler(message: Message) -> None:
    if not await permissions.ensure_permission(message, permissions.ACTION_REMOVE_USER):
        return

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip().lstrip("-").isdigit():
        await message.answer("Foydalanish: /removeuser <user_id>")
        return

    user_id = int(parts[1].strip())
    if remove_user(user_id, removed_by=message.from_user.id):
        await message.answer(f"✅ {user_id} ruxsat etilganlar ro‘yxatidan o‘chirildi.")
    else:
        await message.answer(f"ℹ️ {user_id} ro‘yxatda topilmadi.")


@dp.message(Command("listusers"))
async def list_users_handler(message: Message) -> None:
    if not await permissions.ensure_permission(message, permissions.ACTION_LIST_USERS):
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
    if not await permissions.ensure_permission(message, permissions.ACTION_VIEW_PROFILE):
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
    recruiting_retention_scheduler = recruiting_bot.start_scheduler(bot)
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
        recruiting_retention_scheduler.shutdown(wait=False)
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
