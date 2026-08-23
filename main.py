import asyncio
import os

from aiogram import BaseMiddleware, Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
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
import recruiting_bot  # noqa: E402
import saturn_group_bot  # noqa: E402
import supplier_chat_bot  # noqa: E402
from config import ENVIRONMENT, FOUNDER_ID, RECRUITING_BRANCH_NAMES  # noqa: E402
from services import messages, permissions  # noqa: E402
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
_SHARED_COMMANDS = [
    "/mystars — Mening yulduzlarim",
    "/mymaosh — Mening oylik/bonus holatim",
    "/apellyatsiya — Jarimaga e'tiroz bildirish",
    "/bugungiporga — Bugungi reyting",
    "/oylikturnir — Oylik reyting",
    "/listnizom — Korxona nizomlari",
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
    ("founder", "/setsalary — Fiks oylik belgilash", permissions.ACTION_SET_SALARY),
    ("founder", "/maosh — Xodim maoshi/bonusini ko'rish", permissions.ACTION_LOOKUP_ANY_SALARY),
    ("founder", "/setrule — Qoida qiymatini o'zgartirish", permissions.ACTION_SET_RULE),
    ("founder", "/listrules — Barcha qoidalarni ko'rish", permissions.ACTION_LIST_RULES),
    ("founder", "/processmonth — Oylik KPI/yulduz hisoblash", permissions.ACTION_PROCESS_MONTH),
    ("founder", "/addvehicle — Yangi mashina qo'shish", permissions.ACTION_MANAGE_VEHICLES),
    ("nazoratchi", "/baholash — Xodimni kunlik baholash/jarima", permissions.ACTION_EVALUATE_EMPLOYEE),
    ("nazoratchi", "/kunniyop — Bugungi kunni yopish", permissions.ACTION_CLOSE_DAY),
    ("nazoratchi", "/score — Xodimga oylik ball qo'yish", permissions.ACTION_SCORE_EMPLOYEE),
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


_FOUNDER_MENU_LABELS = [
    "👤 Xodim qo'shish",
    "👥 Xodimlar",
    "🏪 Do'konlar",
    "💰 Smenalarni ko'rish",
    "⚙️ Sozlamalar",
]

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


def build_category_menu(
    commands: list[str],
    *,
    button_labels: dict[str, str] | None = None,
    pair_buttons: bool = False,
) -> ReplyKeyboardMarkup:
    button_texts = [
        (button_labels or {}).get(_bare_command(command), _bare_command(command))
        for command in commands
    ]
    if pair_buttons:
        rows = _paired_keyboard_rows(button_texts)
    else:
        rows = [[KeyboardButton(text=text)] for text in button_texts]
    rows.append([KeyboardButton(text=BACK_TEXT)])
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
performance_bot.register(dp)
cash_shift_bot.register(dp)
inventory_bot.register(dp)
calibration_bot.register(dp)
discipline_bot.register(dp, openai_client)
supplier_chat_bot.register(dp, openai_client)
saturn_group_bot.register(dp, openai_client)
recruiting_bot.register(dp, openai_client)


def greeting_for_user(user_id: int) -> str:
    if user_id == FOUNDER_ID:
        return (
            "Assalomu alaykum, Muhammadiy! 👋\n"
            "Tadbirkorning vaqti qadrli. Ishlarni tez va sodda boshqaramiz."
        )
    return f"Assalomu alaykum!\nFokus AI botiga xush kelibsiz! 🚀\nRolingiz: {role_name(get_role(user_id))}"


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

        if invites.has_pending_invite_for_role(role_key):
            await message.answer(
                f"❌ {role_name(role_key)} uchun allaqachon faol havola mavjud.",
                reply_markup=build_menu(message.from_user.id),
            )
            return

    token = invites.create_invite(role_key, branch, created_by=FOUNDER_ID)
    me = await message.bot.get_me()
    link = f"https://t.me/{me.username}?start={token}"

    await message.answer(
        f"✅ Link tayyor\n{link}", reply_markup=build_menu(message.from_user.id)
    )


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


@dp.message(F.text == "👥 Xodimlar")
async def founder_employees_handler(message: Message) -> None:
    if not await ensure_authorized(message):
        return

    await list_users_handler(message)


@dp.message(F.text == "🏪 Do'konlar")
async def founder_branches_handler(message: Message) -> None:
    if not await ensure_authorized(message):
        return

    lines = "\n".join(f"🏪 {name}" for name in RECRUITING_BRANCH_NAMES)
    await message.answer(f"Mavjud do'konlar:\n{lines}")


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

    is_kassir = category_key == "kassir"
    command_list = "\n".join(commands)
    await message.answer(
        f"{message.text}\n{command_list}\n\nKerakli buyruqni tanlang (ba'zilari "
        "qo'shimcha ma'lumot so'raydi):",
        reply_markup=build_category_menu(
            commands,
            button_labels=_KASSIR_BUTTON_LABELS if is_kassir else None,
            pair_buttons=is_kassir,
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
