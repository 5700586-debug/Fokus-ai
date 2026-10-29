"""S2 evidence UI. Telegram file_id only; no downloads or image storage."""

import logging

from aiogram import Dispatcher, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from services import evidence_photo, permissions

logger = logging.getLogger(__name__)

CANCEL = "❌ Bekor qilish"
SKIP = "⏭ O'tkazib yuborish"


class EvidenceStates(StatesGroup):
    waiting_photo = State()
    waiting_optional_grade_photo = State()


def _cancel_keyboard(optional: bool = False) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=CANCEL, callback_data="ev:cancel")]]
    if optional:
        rows.insert(0, [InlineKeyboardButton(text=SKIP, callback_data="ev:skip")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

async def request_penalty_photo(
    target: Message,
    state: FSMContext,
    *,
    employee_id: int,
    supervisor_id: int,
    penalty_date: str,
    amount: int,
    rule_number: int,
    comment: str | None = None,
    ai_note: str | None = None,
    option_id: int | None = None,
) -> None:
    """Stage all original inputs without writing a penalty or touching the ledger."""
    await state.clear()
    await state.update_data(evidence_pending={
        "employee_id": employee_id,
        "supervisor_id": supervisor_id,
        "penalty_date": penalty_date,
        "amount": amount,
        "rule_number": rule_number,
        "comment": comment,
        "ai_note": ai_note,
        "option_id": option_id,
    })
    await state.set_state(EvidenceStates.waiting_photo)
    await target.answer("📷 Minus uchun dalil rasmini yuboring yoki Bekor qiling.", reply_markup=_cancel_keyboard())


async def send_evidence_notice(
    bot, chat_id: int, evidence_file_id: str | None, text: str, *, reply_markup=None
):
    """Keep employee appeal buttons; Telegram photo caption is max 1024 characters."""
    if evidence_file_id:
        return await bot.send_photo(chat_id, evidence_file_id, caption=text[:1024], reply_markup=reply_markup)
    return await bot.send_message(chat_id, text, reply_markup=reply_markup)


def register(dp: Dispatcher) -> None:
    """Register BEFORE all other message handlers so pending photo states win."""
    @dp.callback_query(F.data.in_({"ev:cancel", "ev:skip"}))
    async def evidence_cancel(callback: CallbackQuery, state: FSMContext) -> None:
        current = await state.get_state()
        if current not in (EvidenceStates.waiting_photo.state, EvidenceStates.waiting_optional_grade_photo.state):
            await callback.answer("Bu tugma eskirgan.", show_alert=True)
            return
        if callback.data == "ev:skip" and current != EvidenceStates.waiting_optional_grade_photo.state:
            await callback.answer("Bu tugma bu yerda ishlamaydi.", show_alert=True)
            return
        await state.clear()
        await callback.answer()
        if callback.message:
            await callback.message.answer("✅ Baho saqlangan. Rasm o'tkazib yuborildi." if current == EvidenceStates.waiting_optional_grade_photo.state else "Minus bekor qilindi — rasm yuborilmadi")

    @dp.message(StateFilter(EvidenceStates.waiting_photo))
    async def evidence_penalty_photo(message: Message, state: FSMContext) -> None:
        if message.from_user is None:
            return
        if not message.photo:
            await state.clear()
            await message.answer("Minus bekor qilindi — rasm yuborilmadi")
            return

        actor_id = message.from_user.id
        pending = (await state.get_data()).get("evidence_pending")
        if not pending or not permissions.has_permission(actor_id, permissions.ACTION_EVALUATE_EMPLOYEE):
            await state.clear()
            await message.answer("Ruxsat yoki pending topilmadi. Minus yozilmadi.")
            return

        # Remove FSM state BEFORE applying, to prevent repeat message/callback writes.
        # Existing shared in-process guard is reused; no parallel penalty application.
        import discipline_bot
        if actor_id in discipline_bot._PENDING_PENALTY_APPLICATIONS:
            await message.answer("Avvalgi minus yakunlanmoqda.")
            return
        discipline_bot._PENDING_PENALTY_APPLICATIONS.add(actor_id)
        try:
            await state.clear()
            try:
                result = evidence_photo.apply_pending_penalty(
                    pending, actor_id, message.photo[-1].file_id
                )
            except (ValueError, PermissionError, KeyError) as error:
                await message.answer(f"Minus qo'llanmadi: {error}")
                return
            rule = result["rule"]
            amount = pending["amount"]
            employee_id = pending["employee_id"]
            await message.answer(f"✅ -{amount} ball qayd etildi. Bonus banki: {result['bonus_bank_balance']} ball.")
            from nazoratchi_bot import _employee_notice_keyboard
            notice = (
                f"⚠️ Sizga -{amount} ball ayirildi.\n"
                f"Qoida: {rule['title']}\nSabab: {rule['content']}\n"
                "Rozi bo'lmasangiz apellyatsiya tugmasini bosing."
            )
            try:
                await send_evidence_notice(
                    message.bot, employee_id, message.photo[-1].file_id, notice,
                    reply_markup=_employee_notice_keyboard(result["penalty_id"]),
                )
            except Exception as error:
                logger.warning("Evidence notice delivery failed: %s", type(error).__name__)
        finally:
            discipline_bot._PENDING_PENALTY_APPLICATIONS.discard(actor_id)

    @dp.message(StateFilter(EvidenceStates.waiting_optional_grade_photo))
    async def optional_grade_photo(message: Message, state: FSMContext) -> None:
        if not message.photo:
            await state.clear()
            await message.answer("✅ Baho saqlangan. Dalil rasmi o'tkazib yuborildi.")
            return
        # Grade evidence persistence is wired only with the grade-side guarded repository update.
        # Never claim that a file_id was saved before the grade handlers wire that update.
        await message.answer("Dalilni bog'lash hozircha faol emas. O'tkazib yuboring.", reply_markup=_cancel_keyboard(True))
