"""Kassir kunlik smena nazorati — bot komandalari.

``services/cash_shift.py`` va ``services/cash_expense.py`` biznes
logikani ushlab turadi, bu modul faqat Telegram interfeysi. Rasmdan
raqam avtomatik o'qilmaydi (``providers/vision_extraction_provider.py``
hali Null) — kassir savdo/xarajat/qoldiq raqamlarini har doim qo'lda
kiritadi, rasmlar faqat hujjat sifatida ilova qilinadi.
"""

from datetime import date

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
from services import cash_expense, cash_shift, permissions

_SKIP_TEXT = "➖ O'tkazib yuborish"

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


class CloseShiftStates(StatesGroup):
    sales_photo = State()
    cash_photo = State()
    cash_sales = State()
    card_sales = State()
    other_payments = State()
    actual_cash_balance = State()


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


def register(dp: Dispatcher) -> None:

    # ---------------------------------------------------------- /openshift --

    @dp.message(Command("openshift"))
    async def openshift_handler(message: Message, state: FSMContext) -> None:
        if not message.from_user or not permissions.has_permission(
            message.from_user.id, permissions.ACTION_OPEN_CASH_SHIFT
        ):
            return

        user_id = message.from_user.id
        today = date.today().isoformat()

        existing = cash_shift.get_open_shift(user_id, today)
        if existing is not None:
            await message.answer(
                f"ℹ️ Bugungi smena allaqachon ochilgan (boshlang'ich qoldiq: {existing['opening_balance']})."
            )
            return

        if cash_shift.is_first_ever_shift(user_id):
            await state.set_state(OpenShiftStates.manual_opening_balance)
            await message.answer(
                "👋 Bu sizning birinchi smenangiz. Kassadagi boshlang'ich pul qoldig'ini kiriting "
                "(bo'lmasa 0 yozing):"
            )
            return

        profile = get_profile(user_id)
        branch = profile.get("branch") if profile else None
        shift = cash_shift.open_shift_for_today(user_id, branch, today)
        await message.answer(
            f"✅ Smena ochildi.\nBoshlang'ich qoldiq (kechagi kassadan): {shift['opening_balance']} so'm."
        )

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
            user_id, branch, date.today().isoformat(), manual_opening_balance=amount
        )
        await message.answer(f"✅ Smena ochildi.\nBoshlang'ich qoldiq: {shift['opening_balance']} so'm.")

    # -------------------------------------------------------------- /expense --

    @dp.message(Command("expense"))
    async def expense_start(message: Message, state: FSMContext) -> None:
        if not message.from_user or not permissions.has_permission(
            message.from_user.id, permissions.ACTION_LOG_CASH_EXPENSE
        ):
            return

        today_shift = cash_shift.get_open_shift(message.from_user.id, date.today().isoformat())
        if today_shift is None:
            await message.answer("❌ Avval /openshift bilan bugungi smenani oching.")
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
            user_id, data["category"], amount, date.today().isoformat()
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
        data = await state.get_data()
        await state.clear()

        user_id = message.from_user.id
        today_shift = cash_shift.get_open_shift(user_id, date.today().isoformat())
        profile = get_profile(user_id)
        branch = profile.get("branch") if profile else None

        cash_expense.log_expense(
            today_shift["id"], user_id, branch, data["category"], data["amount"],
            description, date.today().isoformat(),
        )
        await message.answer(
            f"✅ Xarajat qayd etildi: {_CATEGORY_LABELS[data['category']]} — {data['amount']} so'm.",
            reply_markup=ReplyKeyboardRemove(),
        )

    # ----------------------------------------------------------- /closeshift --

    @dp.message(Command("closeshift"))
    async def closeshift_start(message: Message, state: FSMContext) -> None:
        if not message.from_user or not permissions.has_permission(
            message.from_user.id, permissions.ACTION_CLOSE_CASH_SHIFT
        ):
            return

        user_id = message.from_user.id
        shift = cash_shift.get_open_shift(user_id, date.today().isoformat())
        if shift is None:
            await message.answer("❌ Avval /openshift bilan bugungi smenani oching.")
            return

        if shift["status"] == cash_shift.STATUS_NEEDS_SUPERVISOR_APPROVAL:
            await message.answer("⏳ Smenangiz hozir Nazoratchi/Founder tekshiruvida. Javobni kuting.")
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
            await message.answer(
                "🔁 Qayta tekshiring. Bugungi naqd savdo summasini kiriting:",
                reply_markup=ReplyKeyboardRemove(),
            )
            return

        await state.set_state(CloseShiftStates.sales_photo)
        await message.answer(
            "📸 Kompyuterdagi kunlik savdo hisobotining rasmini yuboring:",
            reply_markup=ReplyKeyboardRemove(),
        )

    @dp.message(StateFilter(CloseShiftStates.sales_photo), F.photo)
    async def closeshift_sales_photo(message: Message, state: FSMContext) -> None:
        data = await state.get_data()
        file_id = message.photo[-1].file_id
        get_file_storage_provider().register(file_id, message.from_user.id, "cash_shift_photo")
        cash_shift.get_shift(data["shift_id"])  # mavjudligini tekshirish
        from repositories import cash_shifts as cash_shifts_repo

        cash_shifts_repo.set_sales_report_photo(data["shift_id"], file_id)

        await state.set_state(CloseShiftStates.cash_photo)
        await message.answer("📸 Endi xarajat/kassa daftari rasmini yuboring:")

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
        await message.answer("Bugungi naqd savdo summasini kiriting:")

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
        await message.answer("Bugungi karta savdo summasini kiriting:")

    @dp.message(StateFilter(CloseShiftStates.card_sales))
    async def closeshift_card_sales(message: Message, state: FSMContext) -> None:
        amount = _parse_amount(message.text or "")
        if amount is None or amount < 0:
            await message.answer("❌ Faqat musbat raqam kiriting.")
            return

        await state.update_data(card_sales=amount)
        await state.set_state(CloseShiftStates.other_payments)
        await message.answer("Boshqa to'lovlar summasini kiriting (bo'lmasa 0 yozing):")

    @dp.message(StateFilter(CloseShiftStates.other_payments))
    async def closeshift_other_payments(message: Message, state: FSMContext) -> None:
        amount = _parse_amount(message.text or "")
        if amount is None or amount < 0:
            await message.answer("❌ Faqat musbat raqam kiriting (bo'lmasa 0).")
            return

        await state.update_data(other_payments=amount)
        await state.set_state(CloseShiftStates.actual_cash_balance)
        await message.answer("Kassada real qolgan naqd pulni kiriting:")

    @dp.message(StateFilter(CloseShiftStates.actual_cash_balance))
    async def closeshift_actual_cash_balance(message: Message, state: FSMContext) -> None:
        amount = _parse_amount(message.text or "")
        if amount is None or amount < 0:
            await message.answer("❌ Faqat musbat raqam kiriting.")
            return

        data = await state.get_data()
        shift_id = data["shift_id"]
        cash_expenses = cash_expense.total_expenses_for_shift(shift_id)

        result = cash_shift.submit_close_attempt(
            shift_id, data["cash_sales"], data["card_sales"], data["other_payments"],
            cash_expenses, amount,
        )

        if result.finalized:
            await state.clear()
            shift = cash_shift.get_shift(shift_id)
            await message.answer(_format_shift_summary(shift), reply_markup=ReplyKeyboardRemove())
            return

        if result.needs_supervisor:
            await state.clear()
            shift = cash_shift.get_shift(shift_id)
            await message.answer(
                "🔴 Farq hali yopilmadi. Smena Nazoratchi/Founder tekshiruviga yuborildi.",
                reply_markup=ReplyKeyboardRemove(),
            )
            await _send_shift_for_review(message, shift)
            return

        await state.set_state(CloseShiftStates.cash_sales)
        await message.answer(
            f"🔴 Farq {result.difference} so'm.\n\n"
            "Qayta tekshiring:\n"
            "• naqd savdo\n"
            "• karta/boshqa to'lov\n"
            "• xarajat\n"
            "• opening balance\n\n"
            f"Qolgan urinishlar: {result.retries_left}\n\n"
            "Bugungi naqd savdo summasini qayta kiriting:"
        )

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
        if not callback.from_user or not permissions.has_permission(
            callback.from_user.id, permissions.ACTION_REVIEW_CASH_SHIFT
        ):
            await callback.answer()
            return

        shift_id = int(callback.data.split(":", 1)[1])
        shift = cash_shift.get_shift(shift_id)
        if shift is None or shift["status"] != cash_shift.STATUS_NEEDS_SUPERVISOR_APPROVAL:
            await callback.answer("Bu smena hozir tekshiruv kutmayapti.", show_alert=True)
            return

        cash_shift.apply_supervisor_decision(shift_id, callback.from_user.id, decision, comment=None)

        if callback.message:
            await callback.message.edit_reply_markup(reply_markup=None)

        if decision == "recheck":
            await callback.bot.send_message(
                shift["employee_id"],
                "🔁 Nazoratchi/Founder smenangizni qayta tekshirishga qaytardi. /closeshift bilan qayta urining.",
            )
        else:
            await callback.bot.send_message(shift["employee_id"], f"{ack_text}.")

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
            if requested_id != message.from_user.id and not (
                permissions.has_permission(message.from_user.id, permissions.ACTION_VIEW_CASH_SUMMARY)
                or permissions.has_permission(message.from_user.id, permissions.ACTION_REVIEW_CASH_SHIFT)
            ):
                return
            target_id = requested_id
        elif not permissions.has_permission(message.from_user.id, permissions.ACTION_OPEN_CASH_SHIFT):
            return

        shift = cash_shift.get_open_shift(target_id, date.today().isoformat())
        if shift is None:
            await message.answer("ℹ️ Bugun uchun smena topilmadi.")
            return

        await message.answer(_format_shift_summary(shift))
