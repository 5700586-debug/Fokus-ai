"""Kassir kunlik smena nazorati — bot komandalari.

``services/cash_shift.py`` va ``services/cash_expense.py`` biznes
logikani ushlab turadi, bu modul faqat Telegram interfeysi. Rasmdan
raqam avtomatik o'qilmaydi (``providers/vision_extraction_provider.py``
hali Null) — kassir savdo/xarajat/qoldiq raqamlarini har doim qo'lda
kiritadi, rasmlar faqat hujjat sifatida ilova qilinadi.
"""

import company_time
from aiogram import Dispatcher, F
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

from config import FOUNDER_ID
from employees import get_profile
from providers.file_storage import get_file_storage_provider
from services import cash_expense, cash_shift, chat_cleanup, permissions

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


def _format_shift_summary(shift: dict) -> str:
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


class OpenShiftStates(StatesGroup):
    manual_opening_balance = State()
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


class ExpenseStates(StatesGroup):
    category = State()
    amount = State()
    anomaly_reason = State()
    description = State()


def _parse_amount(text: str) -> int | None:
    cleaned = text.strip().replace(" ", "").replace("'", "").replace(",", "")
    if not cleaned.lstrip("-").isdigit():
        return None
    return int(cleaned)


def _format_signed_amount(value: int) -> str:
    sign = "+" if value > 0 else ""
    return f"{sign}{value:,}".replace(",", " ")


def _format_amount(value: int) -> str:
    return f"{value:,}".replace(",", " ")


def _confirm_handover_start_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Ha, topshiraman", callback_data="csui_close_start_yes"),
        InlineKeyboardButton(text="❌ Orqaga", callback_data="csui_close_start_back"),
    ]])


def _confirm_close_amount_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ To'g'ri", callback_data="csui_close_amount_ok"),
        InlineKeyboardButton(text="🔄 Qayta yozaman", callback_data="csui_close_amount_retry"),
    ]])


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
    card = _format_shift_summary(shift)
    text = (
        "🔴 Smena farqi tolerance/retry chegarasidan oshdi — Nazoratchi/Founder "
        "tekshiruvi kerak.\n\n" + card
    )

    recipients = {FOUNDER_ID}
    profile = get_profile(shift["employee_id"])
    # Nazoratchi bitta va filialga bog'lanmagan (single-slot rol) —
    # roles.find_user_by_role orqali topiladi.
    from roles import find_user_by_role

    nazoratchi_id = find_user_by_role("nazoratchi")
    if nazoratchi_id is not None:
        recipients.add(nazoratchi_id)

    for recipient_id in recipients:
        await message.bot.send_message(recipient_id, text, reply_markup=_review_keyboard(shift["id"]))


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
    text = (
        "⚠️ KASSA TAFOVUTI\n\n"
        f"Filial: {shift.get('branch') or '-'}\n"
        f"Topshiruvchi kassir: {topshiruvchi}\n"
        f"Qabul qiluvchi kassir: {_employee_name(shift['employee_id'])}\n"
        f"Topshirilgan summa: {shift['opening_balance']} so'm\n"
        f"Qabul qilingan summa: {shift['received_cash_balance']} so'm\n"
        f"Tafovut: {_format_signed_amount(difference)} so'm\n"
        f"Sabab: {reason}"
    )

    recipients = {FOUNDER_ID}
    # Nazoratchi bitta va filialga bog'lanmagan (single-slot rol) —
    # roles.find_user_by_role orqali topiladi.
    from roles import find_user_by_role

    nazoratchi_id = find_user_by_role("nazoratchi")
    if nazoratchi_id is not None:
        recipients.add(nazoratchi_id)

    for recipient_id in recipients:
        await message.bot.send_message(recipient_id, text, reply_markup=_discrepancy_supervisor_kb(shift["id"]))


def register(dp: Dispatcher) -> None:

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

        if cash_shift.is_first_ever_shift(branch):
            await state.set_state(OpenShiftStates.manual_opening_balance)
            await message.answer(
                "👋 Bu sizning birinchi smenangiz.\n"
                "💵 Kassadagi pulni sanab, summani yozing. Pul bo'lmasa 0 yozing."
            )
            return

        # Topshiruvchi kassir sanagan real kassa summasi (avvalgi yopilgan
        # smenaning ``actual_cash_balance``i) qabul qiluvchiga HECH QACHON
        # ko'rsatilmaydi — qabul qiluvchi kassa pulini mustaqil sanab, o'z
        # natijasini kiritadi.
        await state.set_state(OpenShiftStates.counted_cash_balance)
        await message.answer("💵 Kassadagi pulni o'zingiz sanang.")
        await message.answer("Oldingi kassir yozgan summa ko'rinmaydi.")
        await message.answer("Sanagan summangizni yozing:")

    @dp.message(StateFilter(OpenShiftStates.manual_opening_balance))
    async def openshift_manual_balance(message: Message, state: FSMContext) -> None:
        amount = _parse_amount(message.text or "")
        if amount is None or amount < 0:
            await message.answer("❌ Faqat musbat raqam kiriting.")
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
            await message.answer("❌ Faqat musbat raqam kiriting.")
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
        if not await permissions.ensure_permission(message, permissions.ACTION_LOG_CASH_EXPENSE):
            return

        today_shift = cash_shift.get_open_shift(message.from_user.id, company_time.today().isoformat())
        if today_shift is None:
            await message.answer("⚠️ Avval 🟢 Smenani boshlash tugmasini bosing.")
            return

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
        is_anomaly, baseline_average = cash_expense.check_anomaly(
            user_id, data["category"], amount, company_time.today().isoformat()
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

            today_shift = cash_shift.get_open_shift(user_id, company_time.today().isoformat())
            profile = get_profile(user_id)
            branch = profile.get("branch") if profile else None

            cash_expense.log_expense(
                today_shift["id"], user_id, branch, data["category"], data["amount"],
                description, company_time.today().isoformat(),
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
        shift = cash_shift.get_open_shift(user_id, company_time.today().isoformat())
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

        if shift.get("sales_report_photo_ref") and shift.get("cash_report_photo_ref"):
            # Qayta urinish — rasmlar allaqachon yuborilgan, qayta so'ralmaydi.
            await state.set_state(CloseShiftStates.cash_sales)
            sent = await message.answer(
                "🔁 Qayta tekshiring. Bugungi naqd savdo summasini kiriting:",
                reply_markup=ReplyKeyboardRemove(),
            )
            chat_cleanup.track(_CLOSESHIFT_WORKFLOW, str(shift["id"]), sent)
            return

        await state.set_state(CloseShiftStates.sales_photo)
        sent = await message.answer(
            "📸 Kompyuterdagi kunlik savdo hisobotining rasmini yuboring:",
            reply_markup=ReplyKeyboardRemove(),
        )
        chat_cleanup.track(_CLOSESHIFT_WORKFLOW, str(shift["id"]), sent)

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

        await state.set_state(CloseShiftStates.cash_sales)
        sent = await message.answer("Bugungi naqd savdo summasini kiriting:")
        chat_cleanup.track(_CLOSESHIFT_WORKFLOW, str(data["shift_id"]), sent)

    @dp.message(StateFilter(CloseShiftStates.cash_photo))
    async def closeshift_cash_photo_missing(message: Message) -> None:
        await message.answer("❌ Iltimos, rasmni surat (photo) sifatida yuboring.")

    @dp.message(StateFilter(CloseShiftStates.cash_sales))
    async def closeshift_cash_sales(message: Message, state: FSMContext) -> None:
        amount = _parse_amount(message.text or "")
        if amount is None or amount < 0:
            await message.answer("❌ Faqat musbat raqam kiriting.")
            return

        await state.update_data(cash_sales=amount)
        await state.set_state(CloseShiftStates.card_sales)
        data = await state.get_data()
        sent = await message.answer("Bugungi karta savdo summasini kiriting:")
        chat_cleanup.track(_CLOSESHIFT_WORKFLOW, str(data["shift_id"]), sent)

    @dp.message(StateFilter(CloseShiftStates.card_sales))
    async def closeshift_card_sales(message: Message, state: FSMContext) -> None:
        amount = _parse_amount(message.text or "")
        if amount is None or amount < 0:
            await message.answer("❌ Faqat musbat raqam kiriting.")
            return

        await state.update_data(card_sales=amount)
        await state.set_state(CloseShiftStates.other_payments)
        data = await state.get_data()
        sent = await message.answer("Boshqa to'lovlar summasini kiriting (bo'lmasa 0 yozing):")
        chat_cleanup.track(_CLOSESHIFT_WORKFLOW, str(data["shift_id"]), sent)

    @dp.message(StateFilter(CloseShiftStates.other_payments))
    async def closeshift_other_payments(message: Message, state: FSMContext) -> None:
        amount = _parse_amount(message.text or "")
        if amount is None or amount < 0:
            await message.answer("❌ Faqat musbat raqam kiriting (bo'lmasa 0).")
            return

        await state.update_data(other_payments=amount)
        await state.set_state(CloseShiftStates.confirm_handover_start)
        data = await state.get_data()
        sent = await message.answer("Smenani topshirasizmi?", reply_markup=_confirm_handover_start_kb())
        chat_cleanup.track(_CLOSESHIFT_WORKFLOW, str(data["shift_id"]), sent)

    @dp.callback_query(F.data == "csui_close_start_yes", StateFilter(CloseShiftStates.confirm_handover_start))
    async def closeshift_start_yes(callback: CallbackQuery, state: FSMContext) -> None:
        await state.set_state(CloseShiftStates.actual_cash_balance)
        await callback.message.edit_reply_markup(reply_markup=None)
        data = await state.get_data()
        sent = await callback.message.answer("💵 Kassadagi pulni sanab, summani yozing.")
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
            await message.answer("❌ Faqat musbat raqam kiriting.")
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
        await state.set_state(CloseShiftStates.actual_cash_balance)
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer("💵 Kassadagi pulni sanab, summani yozing.")
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

            if result.needs_supervisor:
                await state.clear()
                shift = cash_shift.get_shift(shift_id)
                sent = await callback.message.answer(
                    "🔴 Farq hali yopilmadi. Smena Nazoratchi/Founder tekshiruviga yuborildi."
                )
                chat_cleanup.track(_CLOSESHIFT_WORKFLOW, str(shift_id), sent)
                await _send_shift_for_review(callback.message, shift)
                await callback.answer()
                return

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

        await message.answer(_format_shift_summary(shift))
