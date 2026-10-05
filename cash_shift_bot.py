"""Kassir kunlik smena nazorati — bot komandalari.

``services/cash_shift.py`` va ``services/cash_expense.py`` biznes
logikani ushlab turadi, bu modul faqat Telegram interfeysi.
``config.VISION_EXTRACTION_ENABLED`` yoqilgan bo'lsa, savdo/kassa
rasmlaridan asosiy summalar ``providers/vision_extraction_provider.py``
orqali avtomatik o'qiladi — kassir faqat AI tushunmagan qatorni qo'lda
kiritadi. O'chirilgan bo'lsa yoki AI xato/timeout bersa, avvalgi to'liq
qo'lda kiritish oqimi o'zgarishsiz ishlayveradi.
"""

import asyncio
import base64
import re
import time
import uuid

import company_time
from aiogram import Dispatcher, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from openai import AsyncOpenAI

from config import FOUNDER_ID
from employees import STATUS_APPROVED, get_profile, list_approved_by_branch
from providers.file_storage import get_file_storage_provider
from providers.vision_extraction_provider import (
    CASH_SHIFT_CASH_REPORT,
    CASH_SHIFT_SALES_REPORT,
    get_vision_extraction_provider,
)
from roles import get_role, is_e2e_tester
from services import (
    cash_expense,
    cash_shift,
    chat_cleanup,
    deficiency_list_ai,
    e2e_test_access,
    latency_probe,
    permissions,
    shift_daily_report,
    shift_deficiency,
)

_CLOSESHIFT_WORKFLOW = "cash_shift_close"

_SKIP_TEXT = "➖ O'tkazib yuborish"

# ``_finish_expense``/``closeshift_amount_confirmed`` FSM holatni
# tozalaydi va keyin ``await state.get_data()``/keyingi qadamlar orqali
# yozadi — ikkalasida ham DB darajasida tabiiy UNIQUE kalit yo'q (bir
# xodim bir kunda bir nechta HAQIQIY xarajat yozishi yoki bir necha
# marta yopishga urinishi mumkin). Shu bilan bir vaqtda bitta
# foydalanuvchidan deyarli bir vaqtda kelgan ikkinchi xabar/tugma
# (masalan ikki marta bosilgan tugma) xuddi shu yozuvni ikki marta
# yozib yubormasligi uchun — ``discipline_bot.py``dagi
# ``_PENDING_PENALTY_APPLICATIONS`` bilan bir xil uslubda, jarayon-ichi
# himoya (foydalanuvchi ID bo'yicha).
_PENDING_EXPENSE_SUBMISSIONS: set[int] = set()
_PENDING_CLOSE_SUBMISSIONS: set[int] = set()
# aiogram yangilanishlarni HAR BIRINI alohida asyncio task sifatida
# concurrent ishga tushiradi (ketma-ket EMAS) — shuning uchun bitta
# foydalanuvchidan deyarli bir vaqtda kelgan ikkita "✅ Tasdiqlash"
# bosilishi (ikki marta bosish yoki Telegram qayta yuborishi) ikkalasi
# ham ``await state.get_data()``dagi tekshiruvdan hali biri ro'yxatni
# tozalamasdan turib o'tib ketishi mumkin edi — natijada ro'yxat ikki
# marta yozilardi va/yoki allaqachon olib tashlangan tugmani ikkinchi
# marta o'chirishga urinish Telegram'ning "message is not modified"
# xatosini chiqarardi (``⚠️ Kutilmagan xatolik``). Yuqoridagi ikkita
# to'plam bilan bir xil uslub — sinxron tekshir+qo'sh (awaitdan OLDIN).
_PENDING_DEFICIENCY_LIST_CONFIRMATIONS: set[int] = set()

_CATEGORY_LABELS = {
    "taxi": "🚕 Taxi",
    "delivery": "📦 Yetkazib berish",
    "transport": "🚌 Transport",
    "mayda_xarajat": "💵 Mayda xarajat",
    "service": "🔧 Servis",
    "purchase_related": "🛒 Xarid bilan bog'liq",
    "other": "➖ Boshqa",
}
_LABEL_TO_CATEGORY = {label: key for key, label in _CATEGORY_LABELS.items()}

_STATUS_LABELS = {
    cash_shift.STATUS_CLEAN_CLOSED: "🟢 Toza yopildi",
    cash_shift.STATUS_WITHIN_TOLERANCE: "🟡 Tolerance ichida yopildi",
    cash_shift.STATUS_PENDING_HANDOVER: "🟡 Topshirish jarayonida (qabul qiluvchi tasdiqlashi kutilmoqda)",
    cash_shift.STATUS_RECHECK_REQUIRED: "🔴 Qayta tekshirish kerak",
    cash_shift.STATUS_NEEDS_SUPERVISOR_APPROVAL: "🔴 Nazoratchi/Founder tekshiruvida",
    cash_shift.STATUS_APPROVED_BY_SUPERVISOR: "✅ Nazoratchi/Founder tasdiqladi",
    cash_shift.STATUS_REJECTED_BY_SUPERVISOR: "❌ Rad etildi",
}


def _kb(*rows: list[str]) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=text) for text in row] for row in rows],
        resize_keyboard=True,
    )


_SKIP_KB = _kb([_SKIP_TEXT])
_CATEGORY_KB = _kb(*[[label] for label in _CATEGORY_LABELS.values()])


def _review_keyboard(shift_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"cashshift_approve:{shift_id}"),
                InlineKeyboardButton(text="❌ Rad etish", callback_data=f"cashshift_reject:{shift_id}"),
            ],
            [InlineKeyboardButton(text="🔁 Qayta tekshiruvga qaytarish", callback_data=f"cashshift_recheck:{shift_id}")],
        ]
    )


def _employee_name(user_id: int) -> str:
    profile = get_profile(user_id)
    if profile is None:
        return str(user_id)

    full_name = " ".join(part for part in (profile.get("familiya"), profile.get("ism")) if part)
    return full_name or str(user_id)


def _format_shift_summary(shift: dict, include_money: bool = True) -> str:
    if not include_money:
        return _format_shift_summary_no_money(shift)

    lines = [
        "💰 KASSA — KUN YAKUNI",
        "",
        f"Kassir: {_employee_name(shift['employee_id'])}",
        f"Sana: {shift['shift_date']}",
        "",
        f"Jami savdo: {shift['total_sales']}",
        f"  Naqd: {shift['cash_sales']}",
        f"  Karta: {shift['card_sales']}",
        f"  Boshqa: {shift['other_payments']}",
        "",
        f"Kechadan opening balance: {shift['opening_balance']}",
        f"Bugungi naqd xarajat: {shift['cash_expenses']}",
        "",
        f"Kutilayotgan naqd: {shift['expected_cash_balance']}",
        f"Real kassadagi naqd: {shift['actual_cash_balance']}",
        f"Farq: {shift['difference']}",
        f"Tolerance: {shift['tolerance']}",
        "",
        f"Status: {_STATUS_LABELS.get(shift['status'], shift['status'])}",
    ]
    return "\n".join(lines)


def _format_shift_summary_no_money(shift: dict) -> str:
    """Pulsiz variant (nazoratchi uchun): kassir, filial, sana, status va "tafovut bor"
    belgisi — savdo, qoldiq, xarajat va farq SUMMALARI yo'q."""
    needs_review = shift.get("status") == cash_shift.STATUS_NEEDS_SUPERVISOR_APPROVAL
    has_difference = bool(shift.get("difference"))
    lines = [
        "💰 KASSA — TEKSHIRUV",
        "",
        f"Kassir: {_employee_name(shift['employee_id'])}",
        f"Filial: {shift.get('branch') or '-'}",
        f"Sana: {shift['shift_date']}",
        f"Status: {_STATUS_LABELS.get(shift['status'], shift['status'])}",
    ]
    if has_difference:
        lines.append("⚠️ Tafovut bor")
    if needs_review:
        lines.append("🔎 Tekshiruv kerak")
    return "\n".join(lines)


def _can_see_cash_money(user_id: int) -> bool:
    """Pul summalarini to'liq ko'rish: Founder (bypass) va ``ACTION_VIEW_CASH_SUMMARY``
    (moliyachi). Nazoratchi pul tafsilotini ko'rmaydi."""
    return permissions.has_permission(user_id, permissions.ACTION_VIEW_CASH_SUMMARY)


class OpenShiftStates(StatesGroup):
    manual_opening_balance = State()
    confirm_previous_balance = State()
    counted_cash_balance = State()
    confirm_counted_balance = State()
    discrepancy_choice = State()
    discrepancy_preset_reason = State()
    discrepancy_reason = State()


class CloseShiftStates(StatesGroup):
    sales_photo = State()
    cash_photo = State()
    cash_sales = State()
    card_sales = State()
    other_payments = State()
    confirm_handover_start = State()
    actual_cash_balance = State()
    confirm_actual_balance = State()
    ai_unclear_field = State()
    ledger_total_choice = State()


class ExpenseStates(StatesGroup):
    category = State()
    amount = State()
    anomaly_reason = State()
    description = State()


class DeficiencyStates(StatesGroup):
    item_name = State()
    item_amount = State()
    yesterday_missing_numbers = State()
    list_clarify = State()


class DailyReportStates(StatesGroup):
    no_prixod_custom = State()
    staff_complaint_note = State()


def _parse_amount(text: str) -> int | None:
    # Kassirlar pulni ko'pincha "50.000", "50 000", "50,000" yoki
    # "2067000 naqd pul" deb yozadi. So'mda kasr kerak emas, shuning uchun
    # nuqta/vergul faqat minglik ajratgich sifatida qabul qilinadi.
    text = text.strip().lower()
    if not text:
        return None

    match = re.match(r"^-?[\d\s.,']+", text)
    if match is None:
        return None

    raw_number = match.group(0).strip()
    compact = raw_number.replace(" ", "").replace("'", "")
    if "." in compact or "," in compact:
        if not re.fullmatch(r"-?\d{1,3}([.,]\d{3})+", compact):
            return None

    cleaned = compact.replace(",", "").replace(".", "")
    if not cleaned.lstrip("-").isdigit():
        return None
    return int(cleaned)


def _format_signed_amount(value: int) -> str:
    sign = "+" if value > 0 else ""
    return f"{sign}{value:,}".replace(",", " ")


def _format_amount(value: int) -> str:
    return f"{value:,}".replace(",", " ")


# AI orqali oldindan to'ldirilishi mumkin bo'lgan aynan shu 4 ta maydon —
# mavjud qo'lda kiritish zanjiridagi bilan bir xil kalitlar
# (``closeshift_cash_sales``/``card_sales``/``other_payments``/
# ``actual_cash_balance``), shuning uchun ``submit_close_attempt``
# chaqiruvi o'zgarishsiz qoladi.
_AI_FIELD_ORDER = ["cash_sales", "card_sales", "other_payments", "actual_cash_balance"]
_AI_FIELD_LABELS = {
    "cash_sales": "Bugungi naqd savdo",
    "card_sales": "Bugungi karta savdo",
    "other_payments": "Boshqa to'lovlar",
    "actual_cash_balance": "Kassadagi haqiqiy naqd qoldiq",
}
_VISION_EXTRACTION_TIMEOUT_SECONDS = 60


def _ai_summary_confirm_kb() -> InlineKeyboardMarkup:
    # Aynan ``csui_close_amount_ok``/``csui_close_amount_retry`` — mavjud
    # ``closeshift_amount_confirmed``/``closeshift_amount_retry``
    # handlerlarini o'zgarishsiz qayta ishlatish uchun, faqat tugma matni
    # AI-xulosa ekraniga mos ("Tasdiqlash"/"Tuzatish").
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Tasdiqlash", callback_data="csui_close_amount_ok"),
            InlineKeyboardButton(text="✏️ Tuzatish", callback_data="csui_close_amount_retry"),
        ],
        [InlineKeyboardButton(text="📸 Rasmlarni qayta yuborish", callback_data="csui_close_restart")],
    ])


async def _download_photo_data_uri(bot, file_id: str) -> str | None:
    """Telegram ``file_id``ni vision API tushunadigan ``data:`` URI'ga
    aylantiradi — shunda ``VisionExtractionProvider`` Telegramdan
    butunlay mustaqil qoladi (faqat rasm manzili sifatida qabul qiladi)."""
    try:
        file = await bot.get_file(file_id)
        buffer = await bot.download_file(file.file_path)
        encoded = base64.b64encode(buffer.read()).decode("ascii")
    except Exception as error:  # noqa: BLE001
        print(f"Rasm yuklab olishda xato (vision extraction): {error!r}")
        return None
    return f"data:image/jpeg;base64,{encoded}"


def _log_vision_fallback(reason: str, shift_id: int | None, started: float) -> None:
    """Qo'lda kiritishga o'tish sababini logga yozadi: sabab kodi (timeout, download, disabled,
    no_sales_ref, both_unconfident, exception), smena ID va sarflangan vaqt. Kalit, rasm yoki
    AI javobi YOZILMAYDI."""
    print(f"cash_vision_fallback reason={reason} shift_id={shift_id} elapsed={time.monotonic() - started:.1f}s")


async def _extract_cash_shift_fields(
    bot, openai_client: AsyncOpenAI, sales_file_id: str, cash_file_id: str, shift_id: int | None = None
) -> dict | None:
    """AI o'qishga urinadi. ``None`` — AI butunlay ishlamadi/o'chirilgan
    (chaqiruvchi mavjud qo'lda kiritish oqimidan foydalanishi kerak,
    PHASE2 #11; sabab ``cash_vision_fallback`` logida). Bo'sh yoki to'liq bo'lmagan dict — AI
    ishladi, lekin ba'zi/barcha maydonlarni "unclear" deb hisoblади (chaqiruvchi faqat
    o'sha maydonlarni so'raydi, PHASE2 #9/#10)."""
    started = time.monotonic()
    provider = get_vision_extraction_provider(openai_client)
    if not provider.is_enabled():
        _log_vision_fallback("disabled", shift_id, started)
        return None

    try:
        sales_uri = await _download_photo_data_uri(bot, sales_file_id)
        cash_uri = await _download_photo_data_uri(bot, cash_file_id)
        if sales_uri is None or cash_uri is None:
            _log_vision_fallback("download", shift_id, started)
            return None

        sales_result, cash_result = await asyncio.wait_for(
            asyncio.gather(
                provider.extract(sales_uri, CASH_SHIFT_SALES_REPORT),
                provider.extract(cash_uri, CASH_SHIFT_CASH_REPORT),
            ),
            timeout=_VISION_EXTRACTION_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        _log_vision_fallback("timeout", shift_id, started)
        return None
    except Exception as error:  # noqa: BLE001
        print(f"Vision extraction xatosi (cash_shift): {error!r}")
        _log_vision_fallback("exception", shift_id, started)
        return None

    if not sales_result.confident and not cash_result.confident:
        _log_vision_fallback("both_unconfident", shift_id, started)
        return None

    # Ikki rasm orasida bog'liq qiymat ziddiyati (PHASE2 #9, oxirgi
    # shart) — bir xil maydon ikkala rasmdan turlicha o'qilsa, ikkalasi
    # ham unclear hisoblanadi.
    merged: dict[str, str] = {}
    conflicts: set[str] = set()
    for result in (sales_result, cash_result):
        for key, value in result.values.items():
            if key in merged and merged[key] != value:
                conflicts.add(key)
            else:
                merged[key] = value
    for key in conflicts:
        merged.pop(key, None)

    clear_fields: dict[str, int] = {}
    for field in _AI_FIELD_ORDER:
        if field not in merged:
            continue
        amount = _parse_amount(merged[field])
        if amount is not None and amount >= 0:
            clear_fields[field] = amount

    # Daftardagi xarajat qatorlari (nom + summa) DBga YOZILMAYDI — kassir "Tasdiqlash"
    # bosguncha FSM'da vaqtincha turadi (``closeshift_amount_confirmed``). ``None`` —
    # daftar o'qilmadi (DBga tegilmaydi); ``[]`` — o'qildi, qator yo'q (tasdiqda eskilari tozalanadi).
    ledger_items = list(cash_result.expense_items) if cash_result.confident else None
    written_total = cash_result.written_expense_total
    items_sum = cash_result.expense_items_sum
    if ledger_items is None:
        ledger_status = None
    elif cash_result.expense_total_mismatch and ledger_items and items_sum is not None and written_total:
        ledger_status = _LEDGER_MISMATCH_UNRESOLVED  # kassir qaysi raqam to'g'riligini tanlaguncha yozilmaydi
    elif items_sum is not None and written_total and items_sum == int(written_total):
        ledger_status = cash_expense.LEDGER_STATUS_MATCHED
    else:
        ledger_status = cash_expense.LEDGER_STATUS_UNVERIFIED
    clear_fields["ledger_expense_items"] = ledger_items
    clear_fields["ledger_written_total"] = written_total
    clear_fields["ledger_total_mismatch"] = ledger_status == _LEDGER_MISMATCH_UNRESOLVED
    clear_fields["ledger_items_sum"] = items_sum
    clear_fields["ledger_total_status"] = ledger_status

    return clear_fields


_LEDGER_MISMATCH_UNRESOLVED = "mismatch_unresolved"
_LEDGER_SAVABLE_STATUSES = {
    cash_expense.LEDGER_STATUS_MATCHED, cash_expense.LEDGER_STATUS_UNVERIFIED,
    cash_expense.LEDGER_STATUS_ACCEPTED_ITEMS_SUM, cash_expense.LEDGER_STATUS_ACCEPTED_WRITTEN_TOTAL,
}
_LEDGER_CLEARED = {
    "ledger_expense_items": None, "ledger_written_total": None, "ledger_total_mismatch": False,
    "ledger_items_sum": None, "ledger_total_status": None,
}


def _ledger_choice_text(extracted: dict) -> str:
    return (
        "⚠️ Xarajatlar jami mos kelmadi.\n"
        f"Men qatorlarni sanasam: {_format_amount(extracted['ledger_items_sum'])} so'm\n"
        f"Daftardagi ‘Jami xarajat’: {_format_amount(int(extracted['ledger_written_total']))} so'm\n\n"
        "Qaysi biri to'g'ri?"
    )


def _ledger_choice_kb(extracted: dict) -> InlineKeyboardMarkup:
    items_sum = _format_amount(extracted["ledger_items_sum"])
    written = _format_amount(int(extracted["ledger_written_total"]))
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"✅ {items_sum} to'g'ri", callback_data="csui_ledger_items")],
        [InlineKeyboardButton(text=f"✏️ {written} to'g'ri", callback_data="csui_ledger_written")],
        [InlineKeyboardButton(text="🔁 Qayta rasm yuborish", callback_data="csui_ledger_resend")],
    ])


async def _ask_next_ai_field_or_summary(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    queue = list(data.get("_ai_unclear_queue") or [])

    if queue:
        await state.set_state(CloseShiftStates.ai_unclear_field)
        field = queue[0]
        sent = await message.answer(
            f"⚠️ {_AI_FIELD_LABELS[field]} summasini tushunmadim. Faqat shu summani yozing."
        )
        chat_cleanup.track(_CLOSESHIFT_WORKFLOW, str(data["shift_id"]), sent)
        return

    await state.set_state(CloseShiftStates.confirm_actual_balance)
    data = await state.get_data()
    summary = "\n".join(
        f"• {_AI_FIELD_LABELS[field]}: {_format_amount(data[field])} so'm" for field in _AI_FIELD_ORDER
    )
    sent = await message.answer(
        f"🤖 AI o'qigan qiymatlar:\n\n{summary}\n\nTo'g'rimi?",
        reply_markup=_ai_summary_confirm_kb(),
    )
    chat_cleanup.track(_CLOSESHIFT_WORKFLOW, str(data["shift_id"]), sent)


def _confirm_handover_start_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Ha, topshiraman", callback_data="csui_close_start_yes"),
            InlineKeyboardButton(text="❌ Orqaga", callback_data="csui_close_start_back"),
        ],
        [InlineKeyboardButton(text="📸 Rasmlarni qayta yuborish", callback_data="csui_close_restart")],
    ])


def _close_restart_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📸 Rasmlarni qayta yuborish", callback_data="csui_close_restart"),
    ]])


def _confirm_close_amount_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ To'g'ri", callback_data="csui_close_amount_ok"),
            InlineKeyboardButton(text="🔄 Qayta yozaman", callback_data="csui_close_amount_retry"),
        ],
        [InlineKeyboardButton(text="📸 Rasmlarni qayta yuborish", callback_data="csui_close_restart")],
    ])


def _confirm_previous_balance_kb(token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Ha, mos", callback_data=f"csui_open_prev_ok:{token}"),
        InlineKeyboardButton(text="❗ Farq bor", callback_data=f"csui_open_prev_diff:{token}"),
    ]])


_STALE_PREVIOUS_BALANCE_BUTTON = "Bu tugma eskirgan. Oxirgi xabardagi tugmani bosing"


def _confirm_received_amount_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ To'g'ri", callback_data="csui_recv_amount_ok"),
        InlineKeyboardButton(text="🔄 Yana sanayman", callback_data="csui_recv_amount_retry"),
    ]])


def _discrepancy_choice_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🔄 Yana sanayman", callback_data="csui_disc_retry"),
        InlineKeyboardButton(text="📝 Sababini yozaman", callback_data="csui_disc_reason"),
    ]])


_DISCREPANCY_PRESET_REASONS = {
    "qaytim": "💵 Qaytimda xato",
    "xarajat": "🧾 Xarajat bo'lgan",
    "tolov": "💳 To'lovda xato",
    "bilmayman": "❓ Bilmayman",
}


def _discrepancy_preset_reason_kb() -> InlineKeyboardMarkup:
    preset_buttons = [
        InlineKeyboardButton(text=label, callback_data=f"csui_reason:{key}")
        for key, label in _DISCREPANCY_PRESET_REASONS.items()
    ]
    rows = [preset_buttons[i:i + 2] for i in range(0, len(preset_buttons), 2)]
    rows.append([InlineKeyboardButton(text="✍️ Boshqa sabab", callback_data="csui_reason:other")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _discrepancy_supervisor_kb(shift_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Qabul qilish", callback_data=f"csui_disc_approve:{shift_id}"),
        InlineKeyboardButton(text="🔄 Qayta sanash", callback_data=f"csui_disc_recount:{shift_id}"),
    ]])


async def _send_shift_for_review(message: Message, shift: dict) -> None:
    header = "🔴 Smena farqi tolerance/retry chegarasidan oshdi — Nazoratchi/Founder tekshiruvi kerak.\n\n"
    full_text = header + _format_shift_summary(shift)
    masked_text = header + _format_shift_summary(shift, include_money=False)

    recipients = {FOUNDER_ID}
    profile = get_profile(shift["employee_id"])
    # Nazoratchi bitta va filialga bog'lanmagan (single-slot rol) —
    # roles.find_user_by_role orqali topiladi.
    from roles import find_user_by_role

    nazoratchi_id = find_user_by_role("nazoratchi")
    if nazoratchi_id is not None:
        recipients.add(nazoratchi_id)

    for recipient_id in recipients:
        text = full_text if _can_see_cash_money(recipient_id) else masked_text
        await message.bot.send_message(recipient_id, text, reply_markup=_review_keyboard(shift["id"]))


async def _notify_branch_shortage(message: Message, shift: dict) -> None:
    """QARORLAR #1/#2 (Founder tasdig'i): oddiy kamomad
    ``cash_shift.tolerance``dan oshsa — FAQAT shu kamomad chiqqan
    filialga biriktirilgan ``savdo_boshligi`` va global ``moliyachi``
    xabardor qilinadi. Founder/nazoratchi bu yerga UMUMAN kirmaydi —
    ular faqat retry tugab ``NEEDS_SUPERVISOR_APPROVAL`` bo'lganda,
    mavjud ``_send_shift_for_review`` orqali (QARORLAR #5)."""
    card = _format_shift_summary(shift)
    text = "🟠 Kassa farqi tolerance'dan oshdi — filial rahbari tekshiruvi kerak.\n\n" + card

    recipients: set[int] = set()
    for employee in list_approved_by_branch(shift["branch"]):
        if employee.get("role_key") == "savdo_boshligi":
            recipients.add(employee["user_id"])

    from roles import find_user_by_role

    moliyachi_id = find_user_by_role("moliyachi")
    if moliyachi_id is not None:
        recipients.add(moliyachi_id)

    for recipient_id in recipients:
        await message.bot.send_message(recipient_id, text)


async def _send_discrepancy_alert(
    message: Message, shift: dict, handed_over_employee_id: int | None, reason: str
) -> None:
    """Topshirish/qabul qilish kassa tafovuti — mavjud Founder/Nazoratchi
    kanaliga (``_send_shift_for_review`` bilan bir xil qabul qiluvchilar)
    yuboriladi, ostida "✅ Qabul qilish"/"🔄 Qayta sanash" tugmalari bilan
    (qarang ``handle_discrepancy_approve``/``handle_discrepancy_recount``).
    """
    difference = shift["received_cash_balance"] - shift["opening_balance"]
    topshiruvchi = _employee_name(handed_over_employee_id) if handed_over_employee_id is not None else "-"
    base_lines = [
        "⚠️ KASSA TAFOVUTI",
        "",
        f"Filial: {shift.get('branch') or '-'}",
        f"Topshiruvchi kassir: {topshiruvchi}",
        f"Qabul qiluvchi kassir: {_employee_name(shift['employee_id'])}",
    ]
    full_text = "\n".join(base_lines + [
        f"Topshirilgan summa: {shift['opening_balance']} so'm",
        f"Qabul qilingan summa: {shift['received_cash_balance']} so'm",
        f"Tafovut: {_format_signed_amount(difference)} so'm",
        f"Sabab: {reason}",
    ])
    # Nazoratchi pulsiz variantni oladi: tafovut BORligi aytiladi, summalar yo'q. Kassir yozgan
    # sabab matni ham ko'rsatilmaydi (ichida pul summasi bo'lishi mumkin) — faqat umumiy eslatma.
    masked_text = "\n".join(base_lines + [
        "⚠️ Tafovut bor", "Sabab kiritilgan. Tafsilot Founder/Moliyachi uchun.",
    ])

    recipients = {FOUNDER_ID}
    # Nazoratchi bitta va filialga bog'lanmagan (single-slot rol) —
    # roles.find_user_by_role orqali topiladi.
    from roles import find_user_by_role

    nazoratchi_id = find_user_by_role("nazoratchi")
    if nazoratchi_id is not None:
        recipients.add(nazoratchi_id)

    for recipient_id in recipients:
        text = full_text if _can_see_cash_money(recipient_id) else masked_text
        await message.bot.send_message(recipient_id, text, reply_markup=_discrepancy_supervisor_kb(shift["id"]))


# --------------------------------------------------------- kamchilik hisoboti --

_QUANTITY_UNIT_RE = re.compile(
    r"^\s*(\d+(?:[.,]\d+)?)\s*(" + "|".join(shift_deficiency.KNOWN_UNITS) + r")\s*$", re.IGNORECASE
)

_DEFICIENCY_NONE_LABELS = {
    shift_deficiency.CATEGORY_MARKET: "🚫 Bugun bozor kamchiligi yo'q",
    shift_deficiency.CATEGORY_COMPANY: "🚫 Bugun firma zakazi yo'q",
}


def _parse_quantity_unit(text: str) -> tuple[float, str] | None:
    match = _QUANTITY_UNIT_RE.match(text or "")
    if not match:
        return None

    quantity = float(match.group(1).replace(",", "."))
    if quantity <= 0:
        return None
    return quantity, match.group(2).lower()


def _parse_number_list(text: str, max_number: int) -> list[int] | None:
    cleaned = (text or "").strip()
    if cleaned == "0":
        return []

    parts = [part.strip() for part in cleaned.replace(" ", ",").split(",") if part.strip()]
    if not parts:
        return None

    numbers: list[int] = []
    for part in parts:
        if not part.isdigit():
            return None
        number = int(part)
        if number < 1 or number > max_number:
            return None
        numbers.append(number)
    return numbers


def _deficiency_start_kb(category: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=_DEFICIENCY_NONE_LABELS[category], callback_data="csdef_none"),
    ]])


def _deficiency_more_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="➕ Yana qo'shish", callback_data="csdef_add_more"),
        InlineKeyboardButton(text="✅ Tugatish", callback_data="csdef_done"),
    ]])


def _deficiency_list_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Tasdiqlash", callback_data="csdef_list_confirm"),
        InlineKeyboardButton(text="✏️ Tuzatish", callback_data="csdef_list_edit"),
    ]])


def _format_deficiency_qty(value: float) -> str:
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return text or "0"


async def _advance_deficiency_list(reply_target: Message, state: FSMContext, shift_id: int) -> None:
    """Ro'yxatdagi keyingi noaniq qatorni so'raydi; barcha qatorlar
    aniq bo'lsa, yakuniy tasdiqlash xulosasini ko'rsatadi."""
    data = await state.get_data()
    items = data.get("deficiency_list_items") or []
    pending = [i for i, item in enumerate(items) if item["parsed"] is None]

    if not pending:
        await state.set_state(None)
        lines = [
            f"{i + 1}. {item['parsed']['product_name']} — "
            f"{_format_deficiency_qty(item['parsed']['quantity'])} {item['parsed']['unit']}"
            for i, item in enumerate(items)
        ]
        with latency_probe.time_telegram_send():
            sent = await reply_target.answer(
                "📋 Ro'yxat tayyor:\n\n" + "\n".join(lines) + "\n\nTasdiqlaysizmi?",
                reply_markup=_deficiency_list_confirm_kb(),
            )
        chat_cleanup.track(_CLOSESHIFT_WORKFLOW, str(shift_id), sent)
        return

    await state.set_state(DeficiencyStates.list_clarify)
    sent = await reply_target.answer(_deficiency_clarify_text(items, pending))
    chat_cleanup.track(_CLOSESHIFT_WORKFLOW, str(shift_id), sent)


def _name_without_typo_quantity(raw_name: str, quantity: float) -> str:
    """"Kola 2litr 20blol" + javobdagi 20 -> "Kola 2 litr": oxirgi token javob
    miqdori bilan boshlanib harflar bilan davom etsa (xato yozilgan miqdor/birlik)
    nomdan olib tashlanadi; boshqa hech narsa taxmin qilinmaydi."""
    tokens = raw_name.split()
    qty_text = _format_deficiency_qty(quantity)
    if len(tokens) > 1 and re.match(rf"^{re.escape(qty_text)}[^\W\d_]+$", tokens[-1]):
        tokens = tokens[:-1]
    return deficiency_list_ai.normalize_name_words(" ".join(tokens))


def _same_product_name(left: str, right: str) -> bool:
    def _key(name: str) -> str:
        return " ".join(deficiency_list_ai.normalize_name_words(name).lower().split())

    return _key(left) == _key(right)


def _followup_items(raw_name: str, results: list[dict]) -> list[dict]:
    """Miqdor so'ralgandan keyingi to'liq qator. Eski nomdan xato miqdor tokeni
    tozalanib, hajm/imlo normallashtirilgach TO'LIQ nom solishtiriladi: teng bo'lsa —
    tuzatilgan qator sifatida qabul qilinadi; farq qilsa (masalan "tuz Russ" -> "tuz Orzu")
    mavjud almashtirish taklifi (ha/yo'q), tasdiqsiz yozilmaydi."""
    if len(results) != 1:
        return results

    new = results[0]["parsed"]
    old_name = _name_without_typo_quantity(raw_name, new["quantity"])
    if not old_name or _same_product_name(old_name, new["product_name"]):
        return results

    return [{
        "raw_line": raw_name,
        "parsed": None,
        "partial": {
            "product_name": old_name, "quantity": None, "unit": None,
            "replace_proposal": {
                "product_name": new["product_name"], "quantity": new["quantity"], "unit": new["unit"],
            },
        },
    }]


async def _partial_followup_item(openai_client, raw_name: str, text: str) -> dict | None:
    """Javobda faqat qisman ma'lumot bor ("20", "blok", "2 pishgan", "20 blk"): aniq
    miqdor/birlik saqlanadi, mavjud partial/clarify oqimi faqat yetishmaganini so'raydi.
    Tushunilmagan so'z TASHLANMAYDI: mavjud AI uni sifat yoki boshqa mahsulot deb ajratadi;
    AI xato bersa/noaniq bo'lsa so'z ``unresolved`` da qoladi (sifat deb qabul qilinmaydi)
    va kassir "almashtirish / tavsif / yo'q" deb aniq tanlaydi."""
    short = deficiency_list_ai.parse_short_answer(text)
    if short is None or (short["quantity"] is None and short["unit"] is None):
        return None

    quantity = short["quantity"]
    name = (
        _name_without_typo_quantity(raw_name, quantity)
        if quantity is not None else deficiency_list_ai.normalize_name_words(raw_name)
    )
    item = {"raw_line": raw_name, "parsed": None, "partial": {"product_name": name, "quantity": None, "unit": None}}

    extra_quality = other_product = None
    if short["unknown"]:
        verdict = await deficiency_list_ai.classify_answer_words(
            openai_client, name, _deficiency_need(item), short["unknown"]
        )
        extra_quality, other_product = verdict["quality"], verdict["product"]
    ok = deficiency_list_ai.apply_short_answer(item, text, extra_quality=extra_quality, other_product=other_product)
    return item if ok else None


def _deficiency_need(item: dict) -> str:
    partial = item.get("partial") or {}
    quantity, unit = partial.get("quantity"), partial.get("unit")
    if quantity is not None and unit is not None:
        need = f"{_format_deficiency_qty(quantity)} {unit} qabul qilindi"
    elif quantity is not None:
        need = f"birlik kerak (miqdor: {_format_deficiency_qty(quantity)})"
    elif unit is not None:
        need = f"miqdor kerak (birlik: {unit})"
    else:
        need = "miqdor va birlik kerak"
    unresolved = partial.get("unresolved")
    if unresolved:
        need += (
            f"; “{' '.join(unresolved)}” — mahsulotni almashtirishmi yoki tavsif qo'shishmi? "
            "(almashtirish / tavsif; yo'q — so'zni tashlab ketish)"
        )
    proposal = partial.get("replace_proposal")
    if proposal:
        given = " ".join(
            part for part in (
                _format_deficiency_qty(proposal["quantity"]) if proposal["quantity"] is not None else "",
                proposal["unit"] or "",
            ) if part
        )
        need = (
            deficiency_list_ai.replace_question(partial.get("product_name") or "", proposal["product_name"])
            + (f" ({proposal['product_name']} — {given})" if given else "")
            + f" ha: almashtirish, yo'q: “{partial.get('product_name')}” qoladi"
        )
    return need


def _deficiency_examples(items: list[dict], pending: list[int]) -> list[str]:
    """Har bir qatorning yetishmagan ma'lumotiga mos misollar (miqdor
    ma'lum bo'lsa qayta miqdor yozish ko'rsatilmaydi)."""
    examples = []
    for index in pending:
        partial = items[index].get("partial") or {}
        number = index + 1
        quantity, unit = partial.get("quantity"), partial.get("unit")
        if quantity is None and unit is None:
            examples.append(f"{number}. 2 kg")
        elif quantity is None:
            examples.append(f"{number}. 2")
        elif unit is None:
            examples.append(f"{number}. kg")
        if partial.get("replace_proposal"):
            examples = [e for e in examples if not e.startswith(f"{number}. ")]
            examples.append(f"{number}. ha / {number}. yo'q")
        elif partial.get("unresolved"):
            examples.append(f"{number}. almashtirish / {number}. tavsif")
    return examples


def _deficiency_clarify_text(items: list[dict], pending: list[int]) -> str:
    # Savol raqami DOIMIY — ro'yxatdagi o'rni (index + 1); qisman javobdan
    # keyin ham o'zgarmaydi, eski xabardagi raqam aynan o'sha mahsulotga tegishli.
    lines = []
    for index in pending:
        item = items[index]
        name = (item.get("partial") or {}).get("product_name") or item["raw_line"]
        lines.append(f"{index + 1}. {name} — {_deficiency_need(item)}")

    return (
        "❓ Bu qatorlarni to'liq tushunmadim:\n\n" + "\n".join(lines) +
        "\n\nHar biriga o'z raqami bilan javob yozing (ro'yxatni qayta yozish shart emas), masalan:\n"
        + "\n".join(_deficiency_examples(items, pending)) +
        f"\n\nMahsulotni almashtirish kerak bo'lsa: {pending[0] + 1}. yangi: Karam 2 dona"
    )


async def _process_deficiency_list(
    message: Message, state: FSMContext, openai_client: AsyncOpenAI, lines: list[str]
) -> None:
    data = await state.get_data()
    results = await deficiency_list_ai.parse_shopping_list(openai_client, "\n".join(lines))
    await state.update_data(deficiency_list_items=results)
    await _advance_deficiency_list(message, state, data["shift_id"])


def _deficiency_yesterday_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Ha", callback_data="csdef_yesterday_confirm"),
        InlineKeyboardButton(text="✏️ Qayta tanlash", callback_data="csdef_yesterday_retry"),
    ]])


async def _enter_close_shift_photo_flow(reply_target: Message, state: FSMContext, shift: dict) -> None:
    if shift.get("sales_report_photo_ref") and shift.get("cash_report_photo_ref"):
        # Qayta urinish — rasmlar allaqachon yuborilgan, qayta so'ralmaydi.
        await state.set_state(CloseShiftStates.cash_sales)
        sent = await reply_target.answer(
            "🔁 Qayta tekshiring. Bugungi naqd savdo summasini kiriting:",
            reply_markup=ReplyKeyboardRemove(),
        )
        chat_cleanup.track(_CLOSESHIFT_WORKFLOW, str(shift["id"]), sent)
        return

    await state.set_state(CloseShiftStates.sales_photo)
    sent = await reply_target.answer(
        "📸 Kompyuterdagi kunlik savdo hisobotining rasmini yuboring:",
        reply_markup=ReplyKeyboardRemove(),
    )
    chat_cleanup.track(_CLOSESHIFT_WORKFLOW, str(shift["id"]), sent)


async def _enter_yesterday_review(reply_target: Message, state: FSMContext, shift: dict) -> None:
    items = shift_deficiency.get_yesterday_open_items(shift["id"])
    if not items:
        shift_deficiency.mark_yesterday_step_done(shift["id"])
        await _enter_deficiency_step(reply_target, state, shift)
        return

    await state.update_data(
        deficiency_yesterday_items=[{"id": item["id"], "product_name": item["product_name"]} for item in items]
    )
    await state.set_state(DeficiencyStates.yesterday_missing_numbers)
    lines = [f"{index + 1} — {item['product_name']}" for index, item in enumerate(items)]
    sent = await reply_target.answer(
        "📋 Kechagi kelmagan mahsulotlar:\n\n" + "\n".join(lines) +
        "\n\nFaqat hali kelmagan raqamlarni yozing (masalan: 1, 3). Hammasi kelgan bo'lsa, 0 yozing."
    )
    chat_cleanup.track(_CLOSESHIFT_WORKFLOW, str(shift["id"]), sent)


async def _enter_deficiency_step(reply_target: Message, state: FSMContext, shift: dict) -> None:
    step = shift_deficiency.get_next_step(shift["id"])

    if step == shift_deficiency.STEP_MARKET:
        await state.update_data(deficiency_category=shift_deficiency.CATEGORY_MARKET)
        await state.set_state(DeficiencyStates.item_name)
        sent = await reply_target.answer(
            "🛒 Bozor uchun: bugun bozor orqali olinadigan kamchilik mahsuloti bo'lsa, nomini yozing.",
            reply_markup=_deficiency_start_kb(shift_deficiency.CATEGORY_MARKET),
        )
        chat_cleanup.track(_CLOSESHIFT_WORKFLOW, str(shift["id"]), sent)
        return

    if step == shift_deficiency.STEP_COMPANY:
        await state.update_data(deficiency_category=shift_deficiency.CATEGORY_COMPANY)
        await state.set_state(DeficiencyStates.item_name)
        sent = await reply_target.answer(
            "🏢 Firmaga zakaz: firma/zavod orqali keladigan mahsulot bo'lsa, nomini yozing.",
            reply_markup=_deficiency_start_kb(shift_deficiency.CATEGORY_COMPANY),
        )
        chat_cleanup.track(_CLOSESHIFT_WORKFLOW, str(shift["id"]), sent)
        return

    if step == shift_deficiency.STEP_YESTERDAY:
        await _enter_yesterday_review(reply_target, state, shift)
        return

    await _enter_daily_report_step(reply_target, state, shift)


# ------------------------------------------------------- kunlik hisobot (V1) --

_NO_PRIXOD_BUTTON_VALUES = ["0", "1", "2", "3", "4", "5", "6plus"]
_NO_PRIXOD_BUTTON_LABELS = {
    "0": "Yo'q", "1": "1", "2": "2", "3": "3", "4": "4", "5": "5", "6plus": "6+",
}

_PRICE_COMPLAINT_BUTTON_LABELS = {
    "0": "Yo'q, bo'lmadi", "1": "1", "2": "2", "3": "3", "4": "4", "5": "5",
    "6-10": "6–10", "10+": "10+",
}

_COMPLAINT_TYPE_LABELS = {
    shift_daily_report.COMPLAINT_TYPE_RUDE: "😠 Qo'pol muomala",
    shift_daily_report.COMPLAINT_TYPE_INATTENTIVE: "😐 E'tiborsizlik",
    shift_daily_report.COMPLAINT_TYPE_SLOW: "🐢 Sekin xizmat",
    shift_daily_report.COMPLAINT_TYPE_WRONG_INFO: "❌ Noto'g'ri ma'lumot",
    shift_daily_report.COMPLAINT_TYPE_PRODUCT_NOT_FOUND: "🔍 Bor mahsulotni topib bera olmadi",
    shift_daily_report.COMPLAINT_TYPE_INDIFFERENT: "😶 Loqaydlik",
    shift_daily_report.COMPLAINT_TYPE_OTHER: "📝 Boshqa",
}


def _daily_report_no_prixod_kb() -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(text=_NO_PRIXOD_BUTTON_LABELS[value], callback_data=f"csdr_prixod:{value}")
        for value in _NO_PRIXOD_BUTTON_VALUES
    ]
    rows = [buttons[i:i + 4] for i in range(0, len(buttons), 4)]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _daily_report_price_kb() -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(text=label, callback_data=f"csdr_price:{value}")
        for value, label in _PRICE_COMPLAINT_BUTTON_LABELS.items()
    ]
    rows = [buttons[i:i + 4] for i in range(0, len(buttons), 4)]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _daily_report_staff_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Yo'q, bo'lmadi", callback_data="csdr_staff_no"),
        InlineKeyboardButton(text="Bo'ldi", callback_data="csdr_staff_yes"),
    ]])


def _daily_report_employee_kb(employee_profiles: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for profile in employee_profiles:
        full_name = " ".join(part for part in (profile.get("familiya"), profile.get("ism")) if part)
        rows.append(
            [InlineKeyboardButton(text=full_name or str(profile["user_id"]), callback_data=f"csdr_staff_emp:{profile['user_id']}")]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _daily_report_complaint_type_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label, callback_data=f"csdr_staff_type:{key}")]
            for key, label in _COMPLAINT_TYPE_LABELS.items()
        ]
    )


async def _send_no_prixod_signal(bot, shift: dict, count: int) -> None:
    text = (
        "🔴 KO'P PRIXODSIZ TOVAR\n\n"
        f"Kassir: {_employee_name(shift['employee_id'])}\n"
        f"Filial: {shift.get('branch') or '-'}\n"
        f"Bugun prixodi chiqmagan tovar: {count} ta"
    )

    from roles import find_user_by_role

    recipients = {FOUNDER_ID}
    nazoratchi_id = find_user_by_role("nazoratchi")
    if nazoratchi_id is not None:
        recipients.add(nazoratchi_id)

    for recipient_id in recipients:
        await bot.send_message(recipient_id, text)


async def _enter_daily_report_step(reply_target: Message, state: FSMContext, shift: dict) -> None:
    step = shift_daily_report.get_next_step(shift["id"])

    if step == shift_daily_report.STEP_NO_PRIXOD:
        sent = await reply_target.answer(
            "📦 Bugun prixodi chiqmagan tovarlar nechta bo'ldi?",
            reply_markup=_daily_report_no_prixod_kb(),
        )
        chat_cleanup.track(_CLOSESHIFT_WORKFLOW, str(shift["id"]), sent)
        return

    if step == shift_daily_report.STEP_PRICE_COMPLAINT:
        sent = await reply_target.answer(
            "💰 Bugun \"narxi qimmat\" degan mijozlar bo'ldimi?",
            reply_markup=_daily_report_price_kb(),
        )
        chat_cleanup.track(_CLOSESHIFT_WORKFLOW, str(shift["id"]), sent)
        return

    if step == shift_daily_report.STEP_STAFF_COMPLAINT:
        sent = await reply_target.answer(
            "🗣 Bugun xodimlarning muomalasi bo'yicha xaridor shikoyat qildimi?",
            reply_markup=_daily_report_staff_kb(),
        )
        chat_cleanup.track(_CLOSESHIFT_WORKFLOW, str(shift["id"]), sent)
        return

    await _enter_close_shift_photo_flow(reply_target, state, shift)


_EXPENSE_NOT_FOR_KASSIR = "Xarajat kiritish sizga ochilmagan. Xarajatni rahbar yoki moliyachi kiritadi."
_EXPENSE_SHIFT_INVALID = "⚠️ Ochiq smena topilmadi. Avval 🟢 Smenani boshlash tugmasini bosing."


def _current_branch(user_id: int) -> str | None:
    profile = get_profile(user_id)
    return profile.get("branch") if profile else None


def _is_own_real_shift(shift: dict | None, user_id: int, branch: str | None) -> bool:
    return (
        shift is not None
        and shift["employee_id"] == user_id
        and shift["branch"] == branch
        and not shift["is_test"]
    )


def _find_working_shift(user_id: int) -> dict | None:
    """Avval xodimning joriy filialdagi REAL ochiq (hali topshirilmagan)
    smenasi — sanadan qat'i nazar, shunda yarim tundan keyin ham o'sha
    smena yopiladi/xarajat yoziladi, uning asl ``shift_date``i va ID'si
    o'zgarmaydi. Topilmasa — bugungi o'z real smenasi (pending/approval/
    yopilgan holat xabarlari chaqiruvchida)."""
    branch = _current_branch(user_id)
    unclosed = cash_shift.get_unclosed_real_shift(user_id, branch)
    if unclosed is not None:
        return unclosed
    shift = cash_shift.get_open_shift(user_id, company_time.today().isoformat())
    return shift if _is_own_real_shift(shift, user_id, branch) else None


def _expense_shift(data: dict, user_id: int) -> dict | None:
    """Xarajat oqimi boshida tanlangan smena (ID bo'yicha). ID yaroqsiz
    (boshqa xodim/filial, test yoki yopilgan smena) bo'lsa ``None`` —
    hech qachon boshqa smenaga yozilmaydi. FSM'da ID umuman yo'q bo'lsa
    (eski holat) joriy ishchi smenaga qaytadi."""
    shift_id = data.get("expense_shift_id")
    if shift_id is None:
        return _find_working_shift(user_id)
    shift = cash_shift.get_shift(shift_id)
    if _is_own_real_shift(shift, user_id, _current_branch(user_id)) and shift["status"] == "open":
        return shift
    return None


def register(dp: Dispatcher, openai_client: AsyncOpenAI) -> None:

    # ---------------------------------------------------------- /openshift --

    @dp.message(Command("openshift"))
    async def openshift_handler(message: Message, state: FSMContext) -> None:
        if not await permissions.ensure_permission(message, permissions.ACTION_OPEN_CASH_SHIFT):
            return

        user_id = message.from_user.id
        today = company_time.today().isoformat()

        existing = cash_shift.get_open_shift(user_id, today)
        if existing is not None:
            await message.answer("ℹ️ Bugungi smena allaqachon ochilgan.")
            return

        profile = get_profile(user_id)
        branch = profile.get("branch") if profile else None

        if cash_shift.get_unclosed_real_shift(user_id, branch) is not None:
            await message.answer("⚠️ Avval ochiq smenangizni topshiring.")
            return

        if cash_shift.is_first_ever_shift(branch):
            await state.set_state(OpenShiftStates.manual_opening_balance)
            await message.answer(
                "👋 Bu sizning birinchi smenangiz.\n"
                "💵 Kassadagi pulni sanab, summani yozing. Pul bo'lmasa 0 yozing."
            )
            return

        from repositories import cash_shifts as cash_shifts_repo

        previous = cash_shifts_repo.get_last_closed_shift(branch)
        if previous is not None and previous["actual_cash_balance"] is not None:
            await _ask_previous_balance(message, state, previous)
            return

        await state.set_state(OpenShiftStates.counted_cash_balance)
        await message.answer("💵 Kassadagi pulni o'zingiz sanang.")
        await message.answer("Sanagan summangizni yozing:")

    async def _ask_previous_balance(message: Message, state: FSMContext, previous: dict) -> None:
        # Har bir so'rov o'z tokenini oladi — eski xabardagi tugma (shu
        # smena uchun takroriy /openshift'dan keyin ham) rad etiladi.
        token = uuid.uuid4().hex[:12]
        await state.update_data(
            previous_balance=previous["actual_cash_balance"],
            previous_shift_id=previous["id"],
            prev_token=token,
        )
        await state.set_state(OpenShiftStates.confirm_previous_balance)
        await message.answer(
            f"Oldingi smenadan qoldiq: {_format_amount(previous['actual_cash_balance'])} so'm. "
            "Pulni sanang. Mosmi?",
            reply_markup=_confirm_previous_balance_kb(token),
        )

    @dp.callback_query(F.data.startswith("csui_open_prev_ok:"), StateFilter(OpenShiftStates.confirm_previous_balance))
    async def openshift_previous_balance_ok(callback: CallbackQuery, state: FSMContext) -> None:
        data = await state.get_data()
        if callback.data.split(":", 1)[1] != data.get("prev_token"):
            await callback.answer(_STALE_PREVIOUS_BALANCE_BUTTON, show_alert=True)
            return

        from repositories import cash_shifts as cash_shifts_repo

        profile = get_profile(callback.from_user.id)
        branch = profile.get("branch") if profile else None
        latest = cash_shifts_repo.get_last_closed_shift(branch)
        if (
            latest is None
            or latest["actual_cash_balance"] is None
            or latest["id"] != data.get("previous_shift_id")
            or latest["actual_cash_balance"] != data.get("previous_balance")
        ):
            # Oldingi smena almashgan: eski tasdiq qabul qilinmaydi, yangi
            # qoldiq yangi token bilan qayta ko'rsatiladi.
            await callback.message.edit_reply_markup(reply_markup=None)
            if latest is None or latest["actual_cash_balance"] is None:
                await state.clear()
                await callback.message.answer("Oldingi qoldiq o'zgardi. /openshift ni qayta yuboring.")
            else:
                await _ask_previous_balance(callback.message, state, latest)
            await callback.answer()
            return

        # Holat darhol almashadi — takroriy bosish bu handlerga qayta tushmaydi.
        await state.update_data(counted_amount=data["previous_balance"])
        await state.set_state(OpenShiftStates.confirm_counted_balance)
        await openshift_counted_balance_confirmed(callback, state)

    @dp.callback_query(F.data.startswith("csui_open_prev_diff:"), StateFilter(OpenShiftStates.confirm_previous_balance))
    async def openshift_previous_balance_diff(callback: CallbackQuery, state: FSMContext) -> None:
        data = await state.get_data()
        if callback.data.split(":", 1)[1] != data.get("prev_token"):
            await callback.answer(_STALE_PREVIOUS_BALANCE_BUTTON, show_alert=True)
            return

        await state.set_state(OpenShiftStates.counted_cash_balance)
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer("Sanagan summangizni yozing:")
        await callback.answer()

    @dp.message(StateFilter(OpenShiftStates.manual_opening_balance))
    async def openshift_manual_balance(message: Message, state: FSMContext) -> None:
        amount = _parse_amount(message.text or "")
        if amount is None or amount < 0:
            await message.answer("❌ Faqat musbat raqam kiriting.", reply_markup=_close_restart_kb())
            return

        await state.clear()
        user_id = message.from_user.id
        profile = get_profile(user_id)
        branch = profile.get("branch") if profile else None
        shift = cash_shift.open_shift_for_today(
            user_id, branch, company_time.today().isoformat(),
            manual_opening_balance=amount, received_cash_balance=amount,
        )
        await message.answer(f"✅ Smena ochildi.\nBoshlang'ich qoldiq: {shift['opening_balance']} so'm.")

    @dp.message(StateFilter(OpenShiftStates.counted_cash_balance))
    async def openshift_counted_balance(message: Message, state: FSMContext) -> None:
        amount = _parse_amount(message.text or "")
        if amount is None or amount < 0:
            await message.answer("❌ Faqat musbat raqam kiriting.", reply_markup=_close_restart_kb())
            return

        await state.update_data(counted_amount=amount)
        await state.set_state(OpenShiftStates.confirm_counted_balance)
        await message.answer(
            f"Siz sanadingiz: {_format_amount(amount)} so'm", reply_markup=_confirm_received_amount_kb()
        )

    @dp.callback_query(F.data == "csui_recv_amount_retry", StateFilter(OpenShiftStates.confirm_counted_balance))
    async def openshift_counted_balance_retry(callback: CallbackQuery, state: FSMContext) -> None:
        await state.set_state(OpenShiftStates.counted_cash_balance)
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer("Sanagan summangizni yozing:")
        await callback.answer()

    @dp.callback_query(F.data == "csui_recv_amount_ok", StateFilter(OpenShiftStates.confirm_counted_balance))
    async def openshift_counted_balance_confirmed(callback: CallbackQuery, state: FSMContext) -> None:
        data = await state.get_data()
        amount = data["counted_amount"]
        user_id = callback.from_user.id
        profile = get_profile(user_id)
        branch = profile.get("branch") if profile else None
        today = company_time.today().isoformat()

        from repositories import cash_shifts as cash_shifts_repo

        # ``opening_balance`` shu smenaning ``actual_cash_balance``idan
        # olinadi (topshiruvchi kassir, hali ``PENDING_HANDOVER`` holatida
        # — closeshift'da darhol yopilmagan). Solishtirishdan oldin
        # topib olinadi, chunki mos kelsa aynan shu smenani yopish kerak.
        handed_over_shift = cash_shifts_repo.get_last_closed_shift(branch)

        # "🔄 Yana sanayman" bilan qayta urinishda smena qatori
        # allaqachon mavjud — ``open_shift_for_today`` uni qayta
        # yaratmasdan aynan shu qatorni qaytaradi, shuning uchun
        # ``received_cash_balance`` shu holatda alohida yangilanadi.
        existing_shift = cash_shift.get_open_shift(user_id, today)
        if existing_shift is None:
            shift = cash_shift.open_shift_for_today(user_id, branch, today, received_cash_balance=amount)
        else:
            cash_shifts_repo.set_received_cash_balance(existing_shift["id"], amount)
            shift = cash_shift.get_shift(existing_shift["id"])

        await callback.message.edit_reply_markup(reply_markup=None)

        # Qabul qiluvchi mustaqil sanagan summa (``received_cash_balance``)
        # topshiruvchining real summasi (``opening_balance``) bilan
        # solishtiriladi. Tafovut bo'lsa smena hozircha yakunlanmaydi —
        # sabab/jarima/formula qo'shilmaydi, faqat ogohlantirish chiqadi.
        if shift["received_cash_balance"] == shift["opening_balance"]:
            if handed_over_shift is not None:
                cash_shift.confirm_handover(handed_over_shift["id"])

            await state.clear()
            await callback.message.answer("✅ Kassa mos.")
            await callback.message.answer("Smena topshirildi.")
            await callback.answer()
            return

        difference = shift["received_cash_balance"] - shift["opening_balance"]

        await state.update_data(
            shift_id=shift["id"],
            handed_over_employee_id=handed_over_shift["employee_id"] if handed_over_shift else None,
        )
        await state.set_state(OpenShiftStates.discrepancy_choice)
        await callback.message.answer(f"⚠️ Kassa farqi: {_format_signed_amount(difference)} so'm")
        await callback.message.answer("Nima qilamiz?", reply_markup=_discrepancy_choice_kb())
        await callback.answer()

    @dp.callback_query(F.data == "csui_disc_retry", StateFilter(OpenShiftStates.discrepancy_choice))
    async def openshift_discrepancy_retry(callback: CallbackQuery, state: FSMContext) -> None:
        await state.set_state(OpenShiftStates.counted_cash_balance)
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer("Sanagan summangizni yozing:")
        await callback.answer()

    @dp.callback_query(F.data == "csui_disc_reason", StateFilter(OpenShiftStates.discrepancy_choice))
    async def openshift_discrepancy_choose_reason(callback: CallbackQuery, state: FSMContext) -> None:
        await state.set_state(OpenShiftStates.discrepancy_preset_reason)
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer("Sababni tanlang:", reply_markup=_discrepancy_preset_reason_kb())
        await callback.answer()

    @dp.callback_query(
        F.data.startswith("csui_reason:"), StateFilter(OpenShiftStates.discrepancy_preset_reason)
    )
    async def openshift_discrepancy_preset_reason(callback: CallbackQuery, state: FSMContext) -> None:
        key = callback.data.split(":", 1)[1]
        await callback.message.edit_reply_markup(reply_markup=None)

        if key == "other":
            await state.set_state(OpenShiftStates.discrepancy_reason)
            await callback.message.answer("Sababini qisqa yozing:")
            await callback.answer()
            return

        label = _DISCREPANCY_PRESET_REASONS[key]
        data = await state.get_data()
        await state.clear()
        from repositories import cash_shifts as cash_shifts_repo

        cash_shifts_repo.set_discrepancy_reason(data["shift_id"], label)
        await callback.message.answer("✅ Sabab saqlandi.")

        shift = cash_shifts_repo.get_shift(data["shift_id"])
        await _send_discrepancy_alert(callback.message, shift, data.get("handed_over_employee_id"), label)
        await callback.answer()

    @dp.message(StateFilter(OpenShiftStates.discrepancy_reason))
    async def openshift_discrepancy_reason(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        if not text:
            await message.answer("❌ Iltimos, sababini qisqacha yozing.")
            return

        data = await state.get_data()
        await state.clear()
        from repositories import cash_shifts as cash_shifts_repo

        cash_shifts_repo.set_discrepancy_reason(data["shift_id"], text)
        await message.answer("✅ Sabab saqlandi.")

        shift = cash_shifts_repo.get_shift(data["shift_id"])
        await _send_discrepancy_alert(message, shift, data.get("handed_over_employee_id"), text)

    # ------------------------------------------- Nazoratchi: kassa tafovuti --

    @dp.callback_query(F.data.startswith("csui_disc_approve:"))
    async def handle_discrepancy_approve(callback: CallbackQuery) -> None:
        if not await permissions.ensure_permission(callback, permissions.ACTION_REVIEW_CASH_SHIFT):
            return

        shift_id = int(callback.data.split(":", 1)[1])
        shift = cash_shift.get_shift(shift_id)
        if shift is None:
            await callback.answer("Smena topilmadi.", show_alert=True)
            return

        from repositories import cash_shifts as cash_shifts_repo

        # Yopilishi kerak bo'lgan smena — topshiruvchi kassirning (hali
        # ``PENDING_HANDOVER``dagi) smenasi, qabul qiluvchining YANGI
        # smenasi emas (u ochiq qolib, oddiy ishlashda davom etadi).
        handed_over_shift = cash_shifts_repo.get_last_closed_shift(shift.get("branch"))
        if handed_over_shift is None or handed_over_shift["status"] != cash_shift.STATUS_PENDING_HANDOVER:
            await callback.answer("Bu tafovut allaqachon hal qilingan.", show_alert=True)
            return

        confirmed = cash_shift.confirm_handover(handed_over_shift["id"])
        if not confirmed:
            # Boshqa so'rov (masalan ikki marta bosilgan tugma) shu
            # smenani allaqachon yopib ulgurgan — qayta approval yozuvi
            # qo'shilmaydi (qarang ``set_shift_status_if``).
            if callback.message:
                await callback.message.edit_reply_markup(reply_markup=None)
            await callback.answer("Bu tafovut allaqachon hal qilingan.", show_alert=True)
            return

        cash_shifts_repo.record_shift_approval(
            handed_over_shift["id"], callback.from_user.id, "discrepancy_accepted",
            shift.get("discrepancy_reason_text"),
        )

        if callback.message:
            await callback.message.edit_reply_markup(reply_markup=None)

        await callback.answer("✅ Kassa tafovuti qabul qilindi.")

    @dp.callback_query(F.data.startswith("csui_disc_recount:"))
    async def handle_discrepancy_recount(callback: CallbackQuery) -> None:
        if not await permissions.ensure_permission(callback, permissions.ACTION_REVIEW_CASH_SHIFT):
            return

        shift_id = int(callback.data.split(":", 1)[1])
        shift = cash_shift.get_shift(shift_id)
        if shift is None:
            await callback.answer("Smena topilmadi.", show_alert=True)
            return

        if callback.message:
            await callback.message.edit_reply_markup(reply_markup=None)

        # Topshiruvchi kassirning smenasi (``PENDING_HANDOVER``) tegilmaydi
        # — faqat qabul qiluvchi kassir mavjud "summani qayta kiritish"
        # bosqichiga qaytariladi (xuddi "🔄 Yana sanayman" tugmasidagidek).
        kassir_id = shift["employee_id"]
        from aiogram.fsm.storage.base import StorageKey

        kassir_state = FSMContext(
            storage=dp.storage, key=StorageKey(bot_id=callback.bot.id, chat_id=kassir_id, user_id=kassir_id)
        )
        await kassir_state.set_state(OpenShiftStates.counted_cash_balance)

        await callback.bot.send_message(kassir_id, "🔄 Kassani yana bir marta sanang.")
        await callback.answer("🔄 Kassirga qayta sanash so'raldi.")

    # -------------------------------------------------------------- /expense --

    @dp.message(Command("expense"))
    async def expense_start(message: Message, state: FSMContext) -> None:
        user_id = message.from_user.id
        if get_role(user_id) == "kassir" and not permissions.has_permission(
            user_id, permissions.ACTION_LOG_CASH_EXPENSE
        ):
            # Eski klaviaturadagi "Xarajat kiritish" tugmasi: kategoriya chiqmaydi.
            await state.clear()
            await message.answer(_EXPENSE_NOT_FOR_KASSIR)
            return

        if not await permissions.ensure_permission(message, permissions.ACTION_LOG_CASH_EXPENSE):
            return

        today_shift = _find_working_shift(message.from_user.id)
        if today_shift is None:
            await message.answer("⚠️ Avval 🟢 Smenani boshlash tugmasini bosing.")
            return

        await state.update_data(expense_shift_id=today_shift["id"])
        await state.set_state(ExpenseStates.category)
        await message.answer("Xarajat kategoriyasini tanlang:", reply_markup=_CATEGORY_KB)

    @dp.message(StateFilter(ExpenseStates.category))
    async def expense_category(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        category = _LABEL_TO_CATEGORY.get(text)
        if category is None:
            await message.answer("Iltimos, tugmalardan birini tanlang.", reply_markup=_CATEGORY_KB)
            return

        await state.update_data(category=category)
        await state.set_state(ExpenseStates.amount)
        await message.answer("Summasini kiriting (so'm):", reply_markup=ReplyKeyboardRemove())

    @dp.message(StateFilter(ExpenseStates.amount))
    async def expense_amount(message: Message, state: FSMContext) -> None:
        amount = _parse_amount(message.text or "")
        if amount is None or amount <= 0:
            await message.answer("❌ Faqat musbat raqam kiriting.")
            return

        data = await state.update_data(amount=amount)
        user_id = message.from_user.id
        expense_shift = _expense_shift(data, user_id)
        if expense_shift is None:
            await state.clear()
            await message.answer(_EXPENSE_SHIFT_INVALID, reply_markup=ReplyKeyboardRemove())
            return
        is_anomaly, baseline_average = cash_expense.check_anomaly(
            user_id, data["category"], amount, expense_shift["shift_date"]
        )

        if is_anomaly:
            await state.set_state(ExpenseStates.anomaly_reason)
            await message.answer(
                f"⚠️ {_CATEGORY_LABELS[data['category']]} xarajati odatdagidan sezilarli yuqori.\n"
                f"Bugungi: {amount} so'm (odatdagi o'rtacha: {round(baseline_average)} so'm).\n\n"
                "Sababini qisqacha yozing:"
            )
            return

        await state.set_state(ExpenseStates.description)
        await message.answer("Izoh (bo'lmasa o'tkazib yuboring):", reply_markup=_SKIP_KB)

    @dp.message(StateFilter(ExpenseStates.anomaly_reason))
    async def expense_anomaly_reason(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        if not text:
            await message.answer("❌ Iltimos, sababini qisqacha yozing.")
            return

        await _finish_expense(message, state, description=f"Sabab: {text}")

    @dp.message(StateFilter(ExpenseStates.description))
    async def expense_description(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        description = None if text == _SKIP_TEXT else text
        await _finish_expense(message, state, description=description)

    async def _finish_expense(message: Message, state: FSMContext, description: str | None) -> None:
        user_id = message.from_user.id
        # Atomic band qilish: awaitdan OLDIN, sinxron tekshir+qo'sh — shu
        # foydalanuvchidan deyarli bir vaqtda kelgan ikkinchi xabar bir
        # xarajatni ikki marta yozib yubormasligi uchun (qarang
        # ``_PENDING_EXPENSE_SUBMISSIONS`` izohi).
        if user_id in _PENDING_EXPENSE_SUBMISSIONS:
            return
        _PENDING_EXPENSE_SUBMISSIONS.add(user_id)

        try:
            data = await state.get_data()
            await state.clear()

            today_shift = _expense_shift(data, user_id)
            if today_shift is None:
                await message.answer(_EXPENSE_SHIFT_INVALID, reply_markup=ReplyKeyboardRemove())
                return
            branch = _current_branch(user_id)

            cash_expense.log_expense(
                today_shift["id"], user_id, branch, data["category"], data["amount"],
                description, today_shift["shift_date"],
            )
            await message.answer(
                f"✅ Xarajat qayd etildi: {_CATEGORY_LABELS[data['category']]} — {data['amount']} so'm.",
                reply_markup=ReplyKeyboardRemove(),
            )
        finally:
            _PENDING_EXPENSE_SUBMISSIONS.discard(user_id)

    # ----------------------------------------------------------- /closeshift --

    @dp.message(Command("closeshift"))
    async def closeshift_start(message: Message, state: FSMContext) -> None:
        if not await permissions.ensure_permission(message, permissions.ACTION_CLOSE_CASH_SHIFT):
            return

        user_id = message.from_user.id
        shift = _find_working_shift(user_id)
        if shift is None:
            await message.answer("⚠️ Avval 🟢 Smenani boshlash tugmasini bosing.")
            return

        if shift["status"] == cash_shift.STATUS_NEEDS_SUPERVISOR_APPROVAL:
            await message.answer("⏳ Smenangiz hozir Nazoratchi/Founder tekshiruvida. Javobni kuting.")
            return

        if shift["status"] == cash_shift.STATUS_PENDING_HANDOVER:
            await message.answer(
                "⏳ Smenangiz allaqachon topshirilgan — qabul qiluvchi kassir tasdiqlashini kutmoqda."
            )
            return

        if shift["status"] in (
            cash_shift.STATUS_CLEAN_CLOSED, cash_shift.STATUS_WITHIN_TOLERANCE,
            cash_shift.STATUS_APPROVED_BY_SUPERVISOR, cash_shift.STATUS_REJECTED_BY_SUPERVISOR,
        ):
            await message.answer("ℹ️ Bugungi smena allaqachon yopilgan.")
            return

        await state.update_data(shift_id=shift["id"])
        await _enter_deficiency_step(message, state, shift)

    # ------------------------------------------------ kamchilik hisoboti (V1) --

    @dp.message(StateFilter(DeficiencyStates.item_name))
    async def deficiency_item_name(message: Message, state: FSMContext) -> None:
        latency_probe.mark_handler_entry("market_list_submit")
        text = message.text or ""
        lines = deficiency_list_ai.split_lines(text)

        if len(lines) >= 2:
            # Ko'p qatorli bozor ro'yxati — mavjud bitta-mahsulot oqimi
            # o'zgarmaydi, bu faqat qo'shimcha yo'l.
            await _process_deficiency_list(message, state, openai_client, lines)
            return

        name = text.strip()
        if not name:
            await message.answer("❌ Mahsulot nomini yozing.")
            return

        # Bitta qator ham ko'p qatorli xabar kabi parse_shopping_list'dan
        # o'tadi (deterministik, tushunmasa mavjud AI fallback). Raqamsiz
        # oddiy nom AI'ga yuborilmaydi. Aniqlanmasa — eski bosqichli oqim.
        results = await deficiency_list_ai.parse_shopping_list(
            openai_client if deficiency_list_ai.has_quantity_hint(name) else None, name
        )
        if results and results[0]["parsed"] is not None:
            data = await state.get_data()
            await state.update_data(deficiency_list_items=results)
            await _advance_deficiency_list(message, state, data["shift_id"])
            return

        await state.update_data(deficiency_item_name=name)
        await state.set_state(DeficiencyStates.item_amount)
        data = await state.get_data()
        sent = await message.answer("Miqdorini kiriting (masalan: 10 kg). Birliklar: kg, dona, litr, quti.")
        chat_cleanup.track(_CLOSESHIFT_WORKFLOW, str(data["shift_id"]), sent)

    @dp.message(StateFilter(DeficiencyStates.list_clarify))
    async def deficiency_list_clarify(message: Message, state: FSMContext) -> None:
        data = await state.get_data()
        items = data.get("deficiency_list_items") or []
        pending = [i for i, item in enumerate(items) if item["parsed"] is None]
        if not pending:
            await state.clear()
            await message.answer("❌ Bekor qilindi.")
            return

        text = message.text or ""
        numbered, stray = deficiency_list_ai.split_numbered_answers(text)
        if not numbered:
            # Raqamsiz javob faqat bitta noaniq qator bo'lganda va aniq
            # bitta qatordan iborat bo'lsa ishonchli — aks holda taxmin qilinmaydi.
            if len(pending) == 1 and len(stray) == 1:
                numbered, stray = [(pending[0] + 1, stray[0])], []
            else:
                await message.answer(
                    "❌ Qaysi mahsulotga tegishli ekani noaniq. Raqam bilan yozing, "
                    f"masalan: {pending[0] + 1}. 2 blok"
                )
                return

        understood = 0
        seen: set[int] = set()
        problems = [f"“{line}” — raqamsiz, qaysi mahsulotga tegishli ekani noaniq" for line in stray]
        for number, answer in numbered:
            if not 1 <= number <= len(items):
                problems.append(f"{number}-raqamli qator yo'q")
            elif number in seen:
                problems.append(f"{number}-raqam takrorlandi — birinchi javob qabul qilingan")
            elif items[number - 1]["parsed"] is not None:
                problems.append(f"{number}-qator allaqachon yakunlangan — o'zgartirilmadi")
            else:
                seen.add(number)
                item = items[number - 1]
                # Ixtiyoriy aniq tahrir ("yangi: ...") va kassirning aniq tanlovi.
                if deficiency_list_ai.parse_explicit_edit(answer) is not None:
                    deficiency_list_ai.apply_explicit_edit(item, answer)
                    understood += 1
                    continue
                if deficiency_list_ai.resolve_unresolved_by_choice(item, answer):
                    understood += 1
                    continue
                if (item.get("partial") or {}).get("replace_proposal"):
                    problems.append(f"{number}-qator: avval almashtirish savoliga «ha» yoki «yo'q» deb javob bering")
                    continue
                extra_quality = other_product = None
                unknown = deficiency_list_ai.unknown_answer_words(answer)
                if unknown:
                    # Kod o'qiy olmagan so'zni mavjud AI savol kontekstida ajratadi: shu mahsulotning
                    # sifati yoki BOSHQA mahsulot nomi. Xato/noaniq bo'lsa ikkalasi None — so'z nomga
                    # qo'shilmaydi, kassir aniq tanlaydi (almashtirish / tavsif).
                    verdict = await deficiency_list_ai.classify_answer_words(
                        openai_client,
                        (item.get("partial") or {}).get("product_name") or item["raw_line"],
                        _deficiency_need(item),
                        unknown,
                    )
                    extra_quality, other_product = verdict["quality"], verdict["product"]
                if deficiency_list_ai.apply_short_answer(
                    item, answer, extra_quality=extra_quality, other_product=other_product
                ):
                    understood += 1
                else:
                    problems.append(f"{number}. “{answer}” — javobni tushunmadim")

        if understood == 0:
            await message.answer(
                f"❌ Javobni tushunmadim. Raqam bilan yozing, masalan: {pending[0] + 1}. 2 blok\n"
                + "\n".join(problems)
            )
            return

        await state.update_data(deficiency_list_items=items)
        if problems:
            await message.answer("⚠️ Qabul qilinmadi:\n" + "\n".join(problems))
        await _advance_deficiency_list(message, state, data["shift_id"])

    @dp.callback_query(F.data == "csdef_list_confirm")
    async def deficiency_list_confirm(callback: CallbackQuery, state: FSMContext) -> None:
        # 1-band: callback DARHOL, boshqa hech qanday ish (DB o'qish/
        # yozishdan) OLDIN tasdiqlanadi. Telegram ``answerCallbackQuery``
        # ni kech chaqirsangiz "query is too old and response timeout
        # expired or query ID is invalid" (``TelegramBadRequest``) bilan
        # rad etadi — production'da DB saqlash (potentsial sekin
        # so'rov) tugagandan KEYIN chaqirilganda sodir bo'lgan haqiqiy
        # xato aynan shu edi. Bu tasdiqlash HECH QACHON muvaffaqiyat
        # xabari sifatida ishlatilmaydi — faqat Telegram mijozining
        # "yuklanmoqda" indikatorini to'xtatadi; allaqachon eskirgan
        # bo'lsa ham global xato handleriga chiqmasligi kerak.
        latency_probe.mark_handler_entry("list_confirm")
        try:
            with latency_probe.time_telegram_send():
                await callback.answer()
        except TelegramBadRequest:
            pass

        user_id = callback.from_user.id
        # Atomic band qilish: awaitdan OLDIN, sinxron tekshir+qo'sh (qarang
        # ``_PENDING_DEFICIENCY_LIST_CONFIRMATIONS`` izohi) — bir vaqtda
        # kelgan ikkinchi confirm shu yerda darhol to'xtaydi.
        if user_id in _PENDING_DEFICIENCY_LIST_CONFIRMATIONS:
            return
        _PENDING_DEFICIENCY_LIST_CONFIRMATIONS.add(user_id)

        try:
            data = await state.get_data()
            items = data.get("deficiency_list_items")
            shift = cash_shift.get_shift(data.get("shift_id"))
            category = data.get("deficiency_category")
            if not items or shift is None or category not in shift_deficiency.KNOWN_CATEGORIES:
                return

            parsed_items = [item["parsed"] for item in items]

            # E2E test (Sinovchi) izolyatsiyasi: FAQAT
            # ``roles.E2E_TESTER_TELEGRAM_ID`` uchun, va FAQAT
            # ``/sinovsmena`` shu state'ga yozgan ``e2e_test_run_id``
            # mavjud bo'lsa — real kassir tasdiqlashi bundan hech qanday
            # ta'sirlanmaydi (test_run_id har doim ``None``/bo'sh).
            test_run_id = data.get("e2e_test_run_id") if is_e2e_tester(user_id) else None

            try:
                added_ids = shift_deficiency.add_items_bulk(
                    shift["id"], user_id, category, parsed_items,
                    is_test=bool(test_run_id), test_run_id=test_run_id,
                )
            except Exception as error:  # noqa: BLE001
                print(f"Bozor ro'yxatini saqlashda xato (shift_id={shift['id']}): {error!r}")
                added_ids = None

            # ``callback.message`` real Telegramda har doim to'liq
            # ``Message`` bo'lavermaydi — Bot API uni ``None`` yoki
            # ``InaccessibleMessage`` qilib ham qaytarishi mumkin
            # (``aiogram.types.CallbackQuery.message`` rasman
            # ``Optional[Message | InaccessibleMessage]``), ikkalasida
            # ham ``edit_reply_markup`` yo'q.
            message = callback.message
            message_available = isinstance(message, Message)

            if not added_ids:
                # 5-band: DB yozuvi muvaffaqiyatsiz bo'lsa, hech qachon
                # muvaffaqiyat xabari ko'rsatilmaydi — ro'yxat va
                # tugmalar SAQLANIB QOLADI (kassir qayta urinib ko'ra
                # oladi). Callback allaqachon (1-bandda) tasdiqlangani
                # uchun bu yerda ``message.answer`` (oddiy xabar,
                # eskirish muddati yo'q) ishlatiladi.
                if message_available:
                    with latency_probe.time_telegram_send():
                        await message.answer("❌ Saqlashda xatolik, qayta urinib ko'ring.")
                return

            # FSM ro'yxati va tugmalar FAQAT DB tranzaksiyasi
            # MUVAFFAQIYATLI tugagandan KEYIN tozalanadi/olib tashlanadi.
            await state.update_data(deficiency_list_items=None)

            if message_available:
                try:
                    with latency_probe.time_telegram_send():
                        await message.edit_reply_markup(reply_markup=None)
                except TelegramBadRequest:
                    pass

            if test_run_id:
                # Test tasdiqlash hech kimga (Founder/Nazoratchi/xodim/
                # ta'minotchi) bildirishnoma yubormaydi — muvaffaqiyat
                # xabari oddiy ``message.answer`` orqali, real "Yana
                # qo'shish/Tugatish" ketma-ketligiga kirmaydi.
                if message_available:
                    with latency_probe.time_telegram_send():
                        await message.answer(f"✅ TEST: {len(added_ids)} ta mahsulot qo'shildi.")
                return

            if message_available:
                with latency_probe.time_telegram_send():
                    sent = await message.answer(
                        f"✅ {len(added_ids)} ta mahsulot qo'shildi.", reply_markup=_deficiency_more_kb()
                    )
                chat_cleanup.track(_CLOSESHIFT_WORKFLOW, str(shift["id"]), sent)
        finally:
            _PENDING_DEFICIENCY_LIST_CONFIRMATIONS.discard(user_id)

    @dp.callback_query(F.data == "csdef_list_edit")
    async def deficiency_list_edit(callback: CallbackQuery, state: FSMContext) -> None:
        data = await state.get_data()
        if data.get("deficiency_category") not in shift_deficiency.KNOWN_CATEGORIES:
            await callback.answer()
            return

        await state.update_data(deficiency_list_items=None)
        await state.set_state(DeficiencyStates.item_name)
        await callback.message.edit_reply_markup(reply_markup=None)
        sent = await callback.message.answer("✏️ Ro'yxatni qaytadan yozing:")
        chat_cleanup.track(_CLOSESHIFT_WORKFLOW, str(data["shift_id"]), sent)
        await callback.answer()

    # ----------------------------------------------- E2E test (Sinovchi) --
    # Faqat ``roles.E2E_TESTER_TELEGRAM_ID`` uchun — boshqa hech kim
    # (Founder ham) ``ACTION_E2E_*`` ruxsatiga ega emas (qarang
    # ``services/permissions.py``). Bu ikkita buyruq HECH QANDAY o'z
    # parser/tasdiqlash mantig'ini takrorlamaydi — FSM holatini aynan
    # REAL ``DeficiencyStates.item_name`` oqimi kutgan shartnoma
    # (``shift_id``, ``deficiency_category``) bilan to'ldiradi, xolos.
    # Shundan keyingi BARCHA ishlov (parse/aniqlashtirish/tasdiqlash)
    # yuqoridagi o'zgarishsiz real handlerlar orqali ketadi — qarang
    # ``deficiency_item_name``, ``_process_deficiency_list``,
    # ``_advance_deficiency_list``, ``deficiency_list_clarify``,
    # ``deficiency_list_confirm``, ``deficiency_list_edit``. Izolyatsiya
    # (``is_test``/``test_run_id``) ``deficiency_list_confirm`` ichida
    # qo'shilgan (qarang shu handlerdagi izoh).

    @dp.message(Command("sinovsmena"))
    async def e2e_test_start_shift(message: Message, state: FSMContext) -> None:
        latency_probe.mark_handler_entry("sinovsmena")
        if not await permissions.ensure_permission(message, permissions.ACTION_E2E_TEST_CASH_SHIFT):
            return

        # DB — yagona haqiqat manbai: ``start_test_shift`` har doim
        # BUGUNGI ochiq TEST smenani DB'dan qidiradi va topilsa ANIQ
        # o'sha shift_id/test_run_id'ni qaytaradi (FSM yo'qolgan bo'lsa
        # ham) — hech qachon yangi, "yetim" test_run_id yaratmaydi.
        try:
            result = e2e_test_access.start_test_shift(message.from_user.id)
        except e2e_test_access.TestRunStateError as error:
            with latency_probe.time_telegram_send():
                await message.answer(f"❌ TEST xatosi: {error}")
            return
        if result is None:
            return
        shift, test_run_id = result

        await state.update_data(
            shift_id=shift["id"],
            deficiency_category=shift_deficiency.CATEGORY_MARKET,
            e2e_test_run_id=test_run_id,
        )
        await state.set_state(DeficiencyStates.item_name)
        with latency_probe.time_telegram_send():
            await message.answer(
                "🧪 TEST smena boshlandi (real ma'lumotga ta'sir qilmaydi).\n"
                "Bozor ro'yxatini yozing (bir yoki bir necha qator):"
            )

    @dp.message(Command("sinovtugat"))
    async def e2e_test_finish(message: Message, state: FSMContext) -> None:
        latency_probe.mark_handler_entry("sinovtugat")
        if not await permissions.ensure_permission(message, permissions.ACTION_E2E_TEST_CASH_SHIFT):
            return

        tester_id = message.from_user.id
        # FSM'ga umuman tayanmaydi — DB'dagi bugungi ochiq TEST
        # smenani to'g'ridan-to'g'ri topib yakunlaydi/tozalaydi, shuning
        # uchun bot qayta ishga tushgan yoki FSM tozalangan holatda ham
        # ishlaydi. FSM faqat DB tozalash MUVAFFAQIYATLI tugagandan
        # keyin tozalanadi.
        try:
            result = e2e_test_access.finish_active_test_run(tester_id)
        except e2e_test_access.TestRunStateError as error:
            with latency_probe.time_telegram_send():
                await message.answer(f"❌ TEST xatosi: {error}")
            return

        await state.clear()

        if not result["found"]:
            with latency_probe.time_telegram_send():
                await message.answer("ℹ️ Faol TEST smena topilmadi.")
            return

        with latency_probe.time_telegram_send():
            await message.answer(
                "🧪 TEST smena yakunlandi va tozalandi "
                f"(o'chirilgan: {result['items_deleted']} pozitsiya, {result['shifts_deleted']} smena)."
            )

    @dp.message(StateFilter(DeficiencyStates.item_amount))
    async def deficiency_item_amount(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        data = await state.get_data()
        raw_name = data.get("deficiency_item_name") or ""

        parsed = _parse_quantity_unit(text)
        if parsed is None:
            # Qisqa "20 blok" emas — to'liq tuzatilgan qator bo'lishi mumkin: mavjud
            # parser, tushunmasa mavjud AI fallback (oldingi mahsulot qatori emas, yangi qator).
            results = await deficiency_list_ai.parse_shopping_list(
                openai_client if deficiency_list_ai.has_quantity_hint(text) else None, text
            ) if text else []
            if results and all(item["parsed"] is not None for item in results):
                items = _followup_items(raw_name, results)
                await state.update_data(deficiency_list_items=items)
                await _advance_deficiency_list(message, state, data["shift_id"])
                return
            partial_item = await _partial_followup_item(openai_client, raw_name, text)
            if partial_item is not None:
                await state.update_data(deficiency_list_items=[partial_item])
                await _advance_deficiency_list(message, state, data["shift_id"])
                return
            await message.answer(
                "❌ Miqdor va birlik kerak — masalan: 20 blok / 10 kg, yoki to'liq tuzatilgan qator "
                "(masalan: Kola 2 litr 20 blok):"
            )
            return

        quantity, unit = parsed
        shift = cash_shift.get_shift(data.get("shift_id"))
        category = data.get("deficiency_category")
        if shift is None or category not in shift_deficiency.KNOWN_CATEGORIES:
            await state.clear()
            await message.answer("❌ Bekor qilindi.")
            return

        # Oldingi qatordagi xato yozilgan miqdor ("20blol") nomda qolmaydi.
        name = _name_without_typo_quantity(raw_name, quantity)
        if category == shift_deficiency.CATEGORY_MARKET:
            shift_deficiency.add_market_item(shift["id"], message.from_user.id, name, quantity, unit)
        else:
            shift_deficiency.add_company_item(shift["id"], message.from_user.id, name, quantity, unit)

        await state.set_state(None)
        sent = await message.answer(
            f"✅ Qo'shildi: {name} — {_format_deficiency_qty(quantity)} {unit}.", reply_markup=_deficiency_more_kb()
        )
        chat_cleanup.track(_CLOSESHIFT_WORKFLOW, str(shift["id"]), sent)

    @dp.callback_query(F.data == "csdef_add_more")
    async def deficiency_add_more(callback: CallbackQuery, state: FSMContext) -> None:
        data = await state.get_data()
        if data.get("deficiency_category") not in shift_deficiency.KNOWN_CATEGORIES:
            await callback.answer()
            return

        await state.set_state(DeficiencyStates.item_name)
        await callback.message.edit_reply_markup(reply_markup=None)
        sent = await callback.message.answer("Mahsulot nomini yozing:")
        chat_cleanup.track(_CLOSESHIFT_WORKFLOW, str(data["shift_id"]), sent)
        await callback.answer()

    @dp.callback_query(F.data.in_({"csdef_done", "csdef_none"}))
    async def deficiency_step_done(callback: CallbackQuery, state: FSMContext) -> None:
        data = await state.get_data()
        shift = cash_shift.get_shift(data.get("shift_id"))
        category = data.get("deficiency_category")
        if shift is None or category not in shift_deficiency.KNOWN_CATEGORIES:
            await callback.answer()
            return

        if category == shift_deficiency.CATEGORY_MARKET:
            shift_deficiency.mark_market_step_done(shift["id"])
        else:
            shift_deficiency.mark_company_step_done(shift["id"])

        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.answer()
        await _enter_deficiency_step(callback.message, state, shift)

    @dp.message(StateFilter(DeficiencyStates.yesterday_missing_numbers))
    async def deficiency_yesterday_numbers(message: Message, state: FSMContext) -> None:
        data = await state.get_data()
        items = data.get("deficiency_yesterday_items") or []
        numbers = _parse_number_list(message.text or "", len(items))
        if numbers is None:
            await message.answer(
                "❌ Faqat ro'yxatdagi raqamlarni vergul bilan yozing (masalan: 1, 3), yoki hammasi kelgan bo'lsa 0:"
            )
            return

        missing = [items[number - 1] for number in numbers]
        names = ", ".join(item["product_name"] for item in missing) or "yo'q"
        await state.update_data(deficiency_yesterday_missing_ids=[item["id"] for item in missing])
        await state.set_state(None)
        sent = await message.answer(
            f"Kelmagan: {names}. To'g'rimi?", reply_markup=_deficiency_yesterday_confirm_kb()
        )
        chat_cleanup.track(_CLOSESHIFT_WORKFLOW, str(data["shift_id"]), sent)

    @dp.callback_query(F.data == "csdef_yesterday_retry")
    async def deficiency_yesterday_retry(callback: CallbackQuery, state: FSMContext) -> None:
        data = await state.get_data()
        if not data.get("deficiency_yesterday_items"):
            await callback.answer()
            return

        await state.set_state(DeficiencyStates.yesterday_missing_numbers)
        await callback.message.edit_reply_markup(reply_markup=None)
        sent = await callback.message.answer(
            "Faqat hali kelmagan raqamlarni qayta yozing (masalan: 1, 3), yoki hammasi kelgan bo'lsa 0:"
        )
        chat_cleanup.track(_CLOSESHIFT_WORKFLOW, str(data["shift_id"]), sent)
        await callback.answer()

    @dp.callback_query(F.data == "csdef_yesterday_confirm")
    async def deficiency_yesterday_confirm(callback: CallbackQuery, state: FSMContext) -> None:
        data = await state.get_data()
        shift = cash_shift.get_shift(data.get("shift_id"))
        if shift is None:
            await state.clear()
            await callback.answer()
            return

        missing_ids = data.get("deficiency_yesterday_missing_ids") or []
        shift_deficiency.confirm_yesterday_review(shift["id"], missing_ids)

        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.answer("✅ Qayd etildi.")
        await _enter_deficiency_step(callback.message, state, shift)

    # -------------------------------------------------- kunlik hisobot (V1) --

    @dp.callback_query(F.data.startswith("csdr_prixod:"))
    async def daily_report_no_prixod_pick(callback: CallbackQuery, state: FSMContext) -> None:
        value = callback.data.split(":", 1)[1]
        data = await state.get_data()
        shift = cash_shift.get_shift(data.get("shift_id"))
        if shift is None:
            await callback.answer()
            return

        if value == "6plus":
            await state.set_state(DailyReportStates.no_prixod_custom)
            await callback.message.edit_reply_markup(reply_markup=None)
            sent = await callback.message.answer("Aniq nechta bo'ldi? (kamida 6, butun son):")
            chat_cleanup.track(_CLOSESHIFT_WORKFLOW, str(shift["id"]), sent)
            await callback.answer()
            return

        count = int(value)
        shift_daily_report.save_no_prixod_count(shift["id"], count)
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.answer()

        if shift_daily_report.is_no_prixod_signal(count):
            await _send_no_prixod_signal(callback.bot, shift, count)

        await _enter_daily_report_step(callback.message, state, shift)

    @dp.message(StateFilter(DailyReportStates.no_prixod_custom))
    async def daily_report_no_prixod_custom(message: Message, state: FSMContext) -> None:
        data = await state.get_data()
        shift = cash_shift.get_shift(data.get("shift_id"))
        if shift is None:
            await state.clear()
            await message.answer("❌ Bekor qilindi.")
            return

        text = (message.text or "").strip()
        if not text.isdigit() or int(text) < 6:
            await message.answer("❌ Faqat 6 yoki undan katta butun son kiriting:")
            return

        count = int(text)
        shift_daily_report.save_no_prixod_count(shift["id"], count)
        await state.set_state(None)

        if shift_daily_report.is_no_prixod_signal(count):
            await _send_no_prixod_signal(message.bot, shift, count)

        await _enter_daily_report_step(message, state, shift)

    @dp.callback_query(F.data.startswith("csdr_price:"))
    async def daily_report_price_pick(callback: CallbackQuery, state: FSMContext) -> None:
        bucket = callback.data.split(":", 1)[1]
        data = await state.get_data()
        shift = cash_shift.get_shift(data.get("shift_id"))
        if shift is None or bucket not in shift_daily_report.PRICE_COMPLAINT_BUCKETS:
            await callback.answer()
            return

        shift_daily_report.save_price_complaint_bucket(shift["id"], bucket)
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.answer()
        await _enter_daily_report_step(callback.message, state, shift)

    @dp.callback_query(F.data == "csdr_staff_no")
    async def daily_report_staff_none(callback: CallbackQuery, state: FSMContext) -> None:
        data = await state.get_data()
        shift = cash_shift.get_shift(data.get("shift_id"))
        if shift is None:
            await callback.answer()
            return

        shift_daily_report.save_staff_complaint_none(shift["id"])
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.answer()
        await _enter_daily_report_step(callback.message, state, shift)

    @dp.callback_query(F.data == "csdr_staff_yes")
    async def daily_report_staff_yes(callback: CallbackQuery, state: FSMContext) -> None:
        data = await state.get_data()
        shift = cash_shift.get_shift(data.get("shift_id"))
        if shift is None:
            await callback.answer()
            return

        employee_profiles = list_approved_by_branch(shift.get("branch"))
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.answer()
        sent = await callback.message.answer(
            "👤 Qaysi xodim ustidan shikoyat qildi?", reply_markup=_daily_report_employee_kb(employee_profiles)
        )
        chat_cleanup.track(_CLOSESHIFT_WORKFLOW, str(shift["id"]), sent)

    @dp.callback_query(F.data.startswith("csdr_staff_emp:"))
    async def daily_report_staff_employee_pick(callback: CallbackQuery, state: FSMContext) -> None:
        employee_id = int(callback.data.split(":", 1)[1])
        data = await state.get_data()
        shift = cash_shift.get_shift(data.get("shift_id"))
        if shift is None:
            await callback.answer()
            return

        profile = get_profile(employee_id)
        if profile is None or profile.get("status") != STATUS_APPROVED:
            await callback.answer("Xodim topilmadi.", show_alert=True)
            return

        await state.update_data(daily_report_complaint_employee_id=employee_id)
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.answer()
        sent = await callback.message.answer(
            "Shikoyat turini tanlang:", reply_markup=_daily_report_complaint_type_kb()
        )
        chat_cleanup.track(_CLOSESHIFT_WORKFLOW, str(shift["id"]), sent)

    @dp.callback_query(F.data.startswith("csdr_staff_type:"))
    async def daily_report_staff_type_pick(callback: CallbackQuery, state: FSMContext) -> None:
        type_key = callback.data.split(":", 1)[1]
        if type_key not in shift_daily_report.KNOWN_COMPLAINT_TYPES:
            await callback.answer()
            return

        data = await state.get_data()
        shift = cash_shift.get_shift(data.get("shift_id"))
        employee_id = data.get("daily_report_complaint_employee_id")
        if shift is None or employee_id is None:
            await callback.answer()
            return

        if type_key == shift_daily_report.COMPLAINT_TYPE_OTHER:
            await state.set_state(DailyReportStates.staff_complaint_note)
            await callback.message.edit_reply_markup(reply_markup=None)
            sent = await callback.message.answer("✍️ Qisqacha yozing:")
            chat_cleanup.track(_CLOSESHIFT_WORKFLOW, str(shift["id"]), sent)
            await callback.answer()
            return

        shift_daily_report.save_staff_complaint(shift["id"], employee_id, type_key)
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.answer()
        await _enter_daily_report_step(callback.message, state, shift)

    @dp.message(StateFilter(DailyReportStates.staff_complaint_note))
    async def daily_report_staff_complaint_note(message: Message, state: FSMContext) -> None:
        data = await state.get_data()
        shift = cash_shift.get_shift(data.get("shift_id"))
        employee_id = data.get("daily_report_complaint_employee_id")
        if shift is None or employee_id is None:
            await state.clear()
            await message.answer("❌ Bekor qilindi.")
            return

        text = (message.text or "").strip()
        if not text:
            await message.answer("❌ Bo'sh matn qabul qilinmaydi. Qisqacha yozing:")
            return

        shift_daily_report.save_staff_complaint(
            shift["id"], employee_id, shift_daily_report.COMPLAINT_TYPE_OTHER, note=text
        )
        await state.set_state(None)
        await _enter_daily_report_step(message, state, shift)

    @dp.message(StateFilter(CloseShiftStates.sales_photo), F.photo)
    async def closeshift_sales_photo(message: Message, state: FSMContext) -> None:
        data = await state.get_data()
        file_id = message.photo[-1].file_id
        get_file_storage_provider().register(file_id, message.from_user.id, "cash_shift_photo")
        cash_shift.get_shift(data["shift_id"])  # mavjudligini tekshirish
        from repositories import cash_shifts as cash_shifts_repo

        cash_shifts_repo.set_sales_report_photo(data["shift_id"], file_id)

        await state.set_state(CloseShiftStates.cash_photo)
        sent = await message.answer("📸 Endi xarajat/kassa daftari rasmini yuboring:")
        chat_cleanup.track(_CLOSESHIFT_WORKFLOW, str(data["shift_id"]), sent)

    @dp.message(StateFilter(CloseShiftStates.sales_photo))
    async def closeshift_sales_photo_missing(message: Message) -> None:
        await message.answer("❌ Iltimos, rasmni surat (photo) sifatida yuboring.")

    @dp.message(StateFilter(CloseShiftStates.cash_photo), F.photo)
    async def closeshift_cash_photo(message: Message, state: FSMContext) -> None:
        data = await state.get_data()
        file_id = message.photo[-1].file_id
        get_file_storage_provider().register(file_id, message.from_user.id, "cash_shift_photo")
        from repositories import cash_shifts as cash_shifts_repo

        cash_shifts_repo.set_cash_report_photo(data["shift_id"], file_id)

        shift = cash_shift.get_shift(data["shift_id"])
        sales_file_id = shift.get("sales_report_photo_ref") if shift else None

        extracted = None
        if not sales_file_id:
            _log_vision_fallback("no_sales_ref", data["shift_id"], time.monotonic())
        else:
            # Tahlil biroz davom etadi — kassir kutayotganini bilsin. Xabar tahlil tugagach
            # (muvaffaqiyat, timeout yoki xato) har holda o'chiriladi.
            wait_message = None
            if get_vision_extraction_provider(openai_client).is_enabled():
                try:
                    wait_message = await message.answer("⏳ Rasmlarni o'qiyapman, biroz kuting…")
                except Exception as error:  # noqa: BLE001
                    print(f"Kutish xabarini yuborishda xato: {error!r}")
            try:
                extracted = await _extract_cash_shift_fields(
                    message.bot, openai_client, sales_file_id, file_id, shift_id=data["shift_id"]
                )
            finally:
                if wait_message is not None:
                    try:
                        await wait_message.delete()
                    except Exception as error:  # noqa: BLE001
                        print(f"Kutish xabarini o'chirishda xato: {error!r}")

        if extracted is None:
            # AI o'chirilgan/butunlay ishlamadi — mavjud qo'lda kiritish
            # oqimi AYNAN o'zgarishsiz davom etadi (PHASE2 #11). Oldingi urinishdan
            # qolgan vaqtinchalik daftar qatorlari tozalanadi (DBga tegilmaydi).
            await state.update_data(**_LEDGER_CLEARED)
            await state.set_state(CloseShiftStates.cash_sales)
            sent = await message.answer("Bugungi naqd savdo summasini kiriting:", reply_markup=_close_restart_kb())
            chat_cleanup.track(_CLOSESHIFT_WORKFLOW, str(data["shift_id"]), sent)
            return

        await state.update_data(**extracted)
        unclear_queue = [field for field in _AI_FIELD_ORDER if field not in extracted]
        await state.update_data(_ai_unclear_queue=unclear_queue)

        if extracted.get("ledger_total_status") == _LEDGER_MISMATCH_UNRESOLVED:
            # Qaysi biri to'g'ri ekani taxmin qilinmaydi: kassir tanlaydi, qatorlar (nomlar)
            # tashlanmaydi — tanlovdan keyin tasdiqda yoziladi. Tanlovgacha davom etilmaydi.
            await state.set_state(CloseShiftStates.ledger_total_choice)
            sent = await message.answer(_ledger_choice_text(extracted), reply_markup=_ledger_choice_kb(extracted))
            chat_cleanup.track(_CLOSESHIFT_WORKFLOW, str(data["shift_id"]), sent)
            return
        await _ask_next_ai_field_or_summary(message, state)

    @dp.callback_query(F.data == "csui_ledger_items", StateFilter(CloseShiftStates.ledger_total_choice))
    async def closeshift_ledger_items_correct(callback: CallbackQuery, state: FSMContext) -> None:
        await state.update_data(ledger_total_status=cash_expense.LEDGER_STATUS_ACCEPTED_ITEMS_SUM)
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.answer()
        await _ask_next_ai_field_or_summary(callback.message, state)

    @dp.callback_query(F.data == "csui_ledger_written", StateFilter(CloseShiftStates.ledger_total_choice))
    async def closeshift_ledger_written_correct(callback: CallbackQuery, state: FSMContext) -> None:
        await state.update_data(ledger_total_status=cash_expense.LEDGER_STATUS_ACCEPTED_WRITTEN_TOTAL)
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.answer()
        await _ask_next_ai_field_or_summary(callback.message, state)

    @dp.callback_query(F.data == "csui_ledger_resend", StateFilter(CloseShiftStates.ledger_total_choice))
    async def closeshift_ledger_resend(callback: CallbackQuery, state: FSMContext) -> None:
        # Vaqtinchalik AI natijalari tozalanadi, DBga hech narsa yozilmaydi; daftar rasmi qayta so'raladi.
        await state.update_data(
            **_LEDGER_CLEARED, cash_sales=None, card_sales=None, other_payments=None,
            actual_cash_balance=None, _ai_unclear_queue=None,
        )
        await state.set_state(CloseShiftStates.cash_photo)
        await callback.message.edit_reply_markup(reply_markup=None)
        data = await state.get_data()
        sent = await callback.message.answer("📸 Xarajat/kassa daftari rasmini qayta yuboring:")
        chat_cleanup.track(_CLOSESHIFT_WORKFLOW, str(data["shift_id"]), sent)
        await callback.answer()

    @dp.message(StateFilter(CloseShiftStates.cash_photo))
    async def closeshift_cash_photo_missing(message: Message) -> None:
        await message.answer("❌ Iltimos, rasmni surat (photo) sifatida yuboring.")

    @dp.message(StateFilter(CloseShiftStates.ai_unclear_field))
    async def closeshift_ai_unclear_field(message: Message, state: FSMContext) -> None:
        amount = _parse_amount(message.text or "")
        if amount is None or amount < 0:
            await message.answer("❌ Faqat musbat raqam kiriting.", reply_markup=_close_restart_kb())
            return

        data = await state.get_data()
        queue = list(data.get("_ai_unclear_queue") or [])
        if not queue:
            await state.set_state(CloseShiftStates.cash_sales)
            return
        field = queue.pop(0)
        await state.update_data(**{field: amount}, _ai_unclear_queue=queue)
        await _ask_next_ai_field_or_summary(message, state)

    @dp.message(StateFilter(CloseShiftStates.cash_sales))
    async def closeshift_cash_sales(message: Message, state: FSMContext) -> None:
        amount = _parse_amount(message.text or "")
        if amount is None or amount < 0:
            await message.answer("❌ Faqat musbat raqam kiriting.", reply_markup=_close_restart_kb())
            return

        await state.update_data(cash_sales=amount)
        await state.set_state(CloseShiftStates.card_sales)
        data = await state.get_data()
        sent = await message.answer("Bugungi karta savdo summasini kiriting:", reply_markup=_close_restart_kb())
        chat_cleanup.track(_CLOSESHIFT_WORKFLOW, str(data["shift_id"]), sent)

    @dp.message(StateFilter(CloseShiftStates.card_sales))
    async def closeshift_card_sales(message: Message, state: FSMContext) -> None:
        amount = _parse_amount(message.text or "")
        if amount is None or amount < 0:
            await message.answer("❌ Faqat musbat raqam kiriting.", reply_markup=_close_restart_kb())
            return

        await state.update_data(card_sales=amount)
        await state.set_state(CloseShiftStates.other_payments)
        data = await state.get_data()
        sent = await message.answer("Boshqa to'lovlar summasini kiriting (bo'lmasa 0 yozing):", reply_markup=_close_restart_kb())
        chat_cleanup.track(_CLOSESHIFT_WORKFLOW, str(data["shift_id"]), sent)

    @dp.message(StateFilter(CloseShiftStates.other_payments))
    async def closeshift_other_payments(message: Message, state: FSMContext) -> None:
        amount = _parse_amount(message.text or "")
        if amount is None or amount < 0:
            await message.answer("❌ Faqat musbat raqam kiriting (bo'lmasa 0).", reply_markup=_close_restart_kb())
            return

        await state.update_data(other_payments=amount)
        await state.set_state(CloseShiftStates.confirm_handover_start)
        data = await state.get_data()
        sent = await message.answer("Smenani topshirasizmi?", reply_markup=_confirm_handover_start_kb())
        chat_cleanup.track(_CLOSESHIFT_WORKFLOW, str(data["shift_id"]), sent)

    @dp.callback_query(F.data == "csui_close_restart")
    async def closeshift_restart(callback: CallbackQuery, state: FSMContext) -> None:
        data = await state.get_data()
        shift_id = data.get("shift_id")
        if not shift_id:
            await state.clear()
            await callback.message.edit_reply_markup(reply_markup=None)
            await callback.message.answer("❌ Bekor qilindi. /closeshift ni qayta bosing.")
            await callback.answer()
            return

        await state.update_data(
            cash_sales=None, card_sales=None, other_payments=None, actual_cash_balance=None,
            _ai_unclear_queue=[], **_LEDGER_CLEARED,
        )
        await state.set_state(CloseShiftStates.sales_photo)
        await callback.message.edit_reply_markup(reply_markup=None)
        sent = await callback.message.answer(
            "📸 Boshidan boshlaymiz. Kompyuterdagi kunlik savdo hisobotining rasmini qayta yuboring:"
        )
        chat_cleanup.track(_CLOSESHIFT_WORKFLOW, str(shift_id), sent)
        await callback.answer()

    @dp.callback_query(F.data == "csui_close_start_yes", StateFilter(CloseShiftStates.confirm_handover_start))
    async def closeshift_start_yes(callback: CallbackQuery, state: FSMContext) -> None:
        await state.set_state(CloseShiftStates.actual_cash_balance)
        await callback.message.edit_reply_markup(reply_markup=None)
        data = await state.get_data()
        sent = await callback.message.answer("💵 Kassadagi pulni sanab, summani yozing.", reply_markup=_close_restart_kb())
        chat_cleanup.track(_CLOSESHIFT_WORKFLOW, str(data["shift_id"]), sent)
        await callback.answer()

    @dp.callback_query(F.data == "csui_close_start_back", StateFilter(CloseShiftStates.confirm_handover_start))
    async def closeshift_start_back(callback: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer("❌ Bekor qilindi.")
        await callback.answer()

    @dp.message(StateFilter(CloseShiftStates.actual_cash_balance))
    async def closeshift_actual_cash_balance(message: Message, state: FSMContext) -> None:
        amount = _parse_amount(message.text or "")
        if amount is None or amount < 0:
            await message.answer("❌ Faqat musbat raqam kiriting.", reply_markup=_close_restart_kb())
            return

        await state.update_data(actual_cash_balance=amount)
        await state.set_state(CloseShiftStates.confirm_actual_balance)
        data = await state.get_data()
        sent = await message.answer(
            f"{_format_amount(amount)} so'm. To'g'rimi?", reply_markup=_confirm_close_amount_kb()
        )
        chat_cleanup.track(_CLOSESHIFT_WORKFLOW, str(data["shift_id"]), sent)

    @dp.callback_query(F.data == "csui_close_amount_retry", StateFilter(CloseShiftStates.confirm_actual_balance))
    async def closeshift_amount_retry(callback: CallbackQuery, state: FSMContext) -> None:
        # "Tuzatish" = AI natijasiga ishonmaslik: vaqtinchalik daftar qatorlari tashlanadi,
        # qo'lda tasdiqlangan oqim DBga eski AI qatorlarini yozmaydi (``None`` — o'qilmagan).
        await state.update_data(**_LEDGER_CLEARED)
        await state.set_state(CloseShiftStates.actual_cash_balance)
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer("💵 Kassadagi pulni sanab, summani yozing.", reply_markup=_close_restart_kb())
        await callback.answer()

    @dp.callback_query(F.data == "csui_close_amount_ok", StateFilter(CloseShiftStates.confirm_actual_balance))
    async def closeshift_amount_confirmed(callback: CallbackQuery, state: FSMContext) -> None:
        user_id = callback.from_user.id
        # Atomic band qilish: awaitdan OLDIN, sinxron tekshir+qo'sh — shu
        # kassirdan deyarli bir vaqtda kelgan ikkinchi bosish
        # ``submit_close_attempt``ni qayta chaqirib, urinish sonini ikki
        # marta oshirib yubormasligi uchun (qarang
        # ``_PENDING_CLOSE_SUBMISSIONS`` izohi).
        if user_id in _PENDING_CLOSE_SUBMISSIONS:
            await callback.answer()
            return
        _PENDING_CLOSE_SUBMISSIONS.add(user_id)

        try:
            data = await state.get_data()
            shift_id = data["shift_id"]
            amount = data["actual_cash_balance"]

            # Daftar xarajat qatorlari FAQAT kassir tasdiqlagach yoziladi (qayta tasdiqda
            # eskilari dublikatsiz almashtiriladi; tasdiqlangan bo'sh ro'yxat eskilarini
            # tozalaydi). ``None`` — daftar o'qilmagan, DBga tegilmaydi. Jami mos kelmasa
            # qatorlar kassir qaysi raqam to'g'riligini tanlagach (status) yoziladi; tanlanmagan
            # (``mismatch_unresolved``) holatda yozilmaydi. Xato smena yopishni to'xtatmaydi.
            ledger_items = data.get("ledger_expense_items")
            ledger_status = data.get("ledger_total_status")
            if ledger_items is not None and ledger_status in _LEDGER_SAVABLE_STATUSES:
                written_total = int(data["ledger_written_total"]) if data.get("ledger_written_total") else None
                accepted_total = (
                    written_total if ledger_status == cash_expense.LEDGER_STATUS_ACCEPTED_WRITTEN_TOTAL else None
                )
                try:
                    cash_expense.save_ledger_items(
                        shift_id, ledger_items, total_status=ledger_status,
                        written_total=written_total, accepted_total=accepted_total,
                    )
                except Exception as error:  # noqa: BLE001
                    print(f"Daftar xarajat qatorlarini saqlashda xato (shift_id={shift_id}): {error!r}")

            cash_expenses = cash_expense.total_expenses_for_shift(shift_id)

            result = cash_shift.submit_close_attempt(
                shift_id, data["cash_sales"], data["card_sales"], data["other_payments"],
                cash_expenses, amount,
            )

            await callback.message.edit_reply_markup(reply_markup=None)

            if result.finalized:
                await state.clear()
                shift = cash_shift.get_shift(shift_id)
                # Yakuniy hisobot xabari ATAYLAB kuzatilmaydi — kassir uchun
                # kunning "cheki" sifatida chatda ko'rinib tursin, faqat
                # oldingi ish-jarayon xabarlari tozalanadi.
                await callback.message.answer(_format_shift_summary(shift))
                await chat_cleanup.cleanup(callback.bot, _CLOSESHIFT_WORKFLOW, str(shift_id))
                await callback.answer()
                return

            shift = cash_shift.get_shift(shift_id)

            if result.needs_supervisor:
                await state.clear()
                sent = await callback.message.answer(
                    "🔴 Farq hali yopilmadi. Smena Nazoratchi/Founder tekshiruviga yuborildi."
                )
                chat_cleanup.track(_CLOSESHIFT_WORKFLOW, str(shift_id), sent)
                await _send_shift_for_review(callback.message, shift)
                await _notify_branch_shortage(callback.message, shift)
                await callback.answer()
                return

            # QARORLAR #2: oddiy kamomad (retry hali qolgan) ham filial
            # rahbari + moliyachini xabardor qiladi — mavjud
            # ``result.finalized``/``needs_supervisor`` (allaqachon
            # hisoblangan) shoxlari asosida, yangi taqqoslash yozilmadi.
            await _notify_branch_shortage(callback.message, shift)

            await state.set_state(CloseShiftStates.cash_sales)
            sent = await callback.message.answer(
                f"🔴 Farq {result.difference} so'm.\n\n"
                "Qayta tekshiring:\n"
                "• naqd savdo\n"
                "• karta/boshqa to'lov\n"
                "• xarajat\n"
                "• opening balance\n\n"
                f"Qolgan urinishlar: {result.retries_left}\n\n"
                "Bugungi naqd savdo summasini qayta kiriting:"
            )
            chat_cleanup.track(_CLOSESHIFT_WORKFLOW, str(shift_id), sent)
            await callback.answer()
        finally:
            _PENDING_CLOSE_SUBMISSIONS.discard(user_id)

    # ------------------------------------------------------- supervisor review --

    @dp.callback_query(F.data.startswith("cashshift_approve:"))
    async def handle_cashshift_approve(callback: CallbackQuery) -> None:
        await _handle_review_decision(callback, "approved", "✅ Smena tasdiqlandi")

    @dp.callback_query(F.data.startswith("cashshift_reject:"))
    async def handle_cashshift_reject(callback: CallbackQuery) -> None:
        await _handle_review_decision(callback, "rejected", "❌ Smena rad etildi")

    @dp.callback_query(F.data.startswith("cashshift_recheck:"))
    async def handle_cashshift_recheck(callback: CallbackQuery) -> None:
        await _handle_review_decision(
            callback, "recheck", "🔁 Kassirga qayta tekshirish uchun qaytarildi"
        )

    async def _handle_review_decision(callback: CallbackQuery, decision: str, ack_text: str) -> None:
        if not await permissions.ensure_permission(callback, permissions.ACTION_REVIEW_CASH_SHIFT):
            return

        shift_id = int(callback.data.split(":", 1)[1])
        shift = cash_shift.get_shift(shift_id)
        if shift is None or shift["status"] != cash_shift.STATUS_NEEDS_SUPERVISOR_APPROVAL:
            await callback.answer("Bu smena hozir tekshiruv kutmayapti.", show_alert=True)
            return

        applied = cash_shift.apply_supervisor_decision(shift_id, callback.from_user.id, decision, comment=None)
        if not applied:
            # Boshqa so'rov (masalan ikki marta bosilgan tugma yoki ikki
            # xil Nazoratchi/Founder) shu smena bo'yicha qarorni
            # allaqachon qo'llab ulgurgan (qarang ``set_shift_status_if``).
            if callback.message:
                await callback.message.edit_reply_markup(reply_markup=None)
            await callback.answer("Bu smena allaqachon boshqa qaror bilan hal qilingan.", show_alert=True)
            return

        if callback.message:
            await callback.message.edit_reply_markup(reply_markup=None)

        if decision == "recheck":
            await callback.bot.send_message(
                shift["employee_id"],
                "🔁 Nazoratchi/Founder smenangizni qayta tekshirishga qaytardi. "
                "🔴 Smenani topshirish tugmasi bilan qayta urining.",
            )
        else:
            # "approved"/"rejected" — smena bo'yicha yakuniy qaror, endi
            # shu smenaning butun /closeshift dialogini kuzatuvdan tozalab
            # tashlash mumkin (yakuniy xabar ATAYLAB kuzatilmagan edi).
            await callback.bot.send_message(shift["employee_id"], f"{ack_text}.")
            await chat_cleanup.cleanup(callback.bot, _CLOSESHIFT_WORKFLOW, str(shift_id))

        await callback.answer(ack_text)

    # ------------------------------------------------------------ /cashsummary --

    @dp.message(Command("cashsummary"))
    async def cashsummary_handler(message: Message) -> None:
        if not message.from_user:
            return

        parts = (message.text or "").split(maxsplit=1)
        target_id = message.from_user.id

        if len(parts) > 1 and parts[1].strip().lstrip("-").isdigit():
            requested_id = int(parts[1].strip())
            if requested_id != message.from_user.id and not permissions.has_any_permission(
                message.from_user.id,
                permissions.ACTION_VIEW_CASH_SUMMARY,
                permissions.ACTION_REVIEW_CASH_SHIFT,
            ):
                await permissions.deny(message, permissions.ACTION_VIEW_CASH_SUMMARY)
                return
            target_id = requested_id
        elif not permissions.has_permission(message.from_user.id, permissions.ACTION_OPEN_CASH_SHIFT):
            await permissions.deny(message, permissions.ACTION_OPEN_CASH_SHIFT)
            return

        shift = cash_shift.get_open_shift(target_id, company_time.today().isoformat())
        if shift is None:
            await message.answer("ℹ️ Bugun uchun smena topilmadi.")
            return

        # O'z smenasi — to'liq; boshqa xodim smenasi — faqat Founder/Moliyachi to'liq,
        # nazoratchi (va boshqalar) pulsiz variant.
        include_money = target_id == message.from_user.id or _can_see_cash_money(message.from_user.id)
        await message.answer(_format_shift_summary(shift, include_money=include_money))
