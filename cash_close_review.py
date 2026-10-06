"""Kassa yopish (qo'lda): kassir 3 rasm (daftar, programma/POS, cheklar) yuboradi va FAQAT 2 summani
qo'lda yozadi; AI rasmlardan summa o'qimaydi va kassirga hech narsa tasdiqlatmaydi. Hammasi bitta
tekshiruv xabari bilan moliyachiga (bo'lmasa Founderga) ketadi.

Rasmlar DBga YOZILMAYDI: ``file_id``lar faqat FSM holatida turadi va moliyachiga darhol yuboriladi;
qaror (tasdiq/rad) bilan ikkala chatdagi rasm xabarlari o'chiriladi (``chat_cleanup``). Bazada faqat
2 summa va smena/tasdiq holati qoladi. Dasturga avtomatik ulash bu yerda YO'Q."""

from aiogram import Dispatcher, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, ReplyKeyboardRemove

import cash_shift_bot as cash_bot
from config import FOUNDER_ID
from roles import find_user_by_role
from services import cash_shift, chat_cleanup, permissions

REVIEW_WORKFLOW = "cash_close_review"

_PHOTO_STEPS = (
    ("review_notebook", "📒 Daftar rasmini yuboring:"),
    ("review_pos", "🖥 Programma/POS rasmini yuboring:"),
    ("review_receipts", "🧾 Cheklar rasmini yuboring:"),
)
_PHOTO_CAPTIONS = {"review_notebook": "📒 Daftar", "review_pos": "🖥 Programma/POS", "review_receipts": "🧾 Cheklar"}
_CASH_RECEIVED_PROMPT = "💵 Bugun qabul qilgan naqd pulni yozing:"
_CASH_LEFT_PROMPT = "💵 Kassada qoldirayotgan naqd pulni yozing:"


class CloseReviewStates(StatesGroup):
    notebook_photo = State()
    pos_photo = State()
    receipts_photo = State()
    cash_received = State()
    cash_left = State()
    confirm = State()


_PHOTO_STATES = {
    "review_notebook": CloseReviewStates.notebook_photo,
    "review_pos": CloseReviewStates.pos_photo,
    "review_receipts": CloseReviewStates.receipts_photo,
}
_NEXT_AFTER_PHOTO = {"review_notebook": 1, "review_pos": 2, "review_receipts": None}


def _restart_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📸 Rasmlarni qayta yuborish", callback_data="csui_rev_restart"),
    ]])


def _confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Moliyachiga yuborish", callback_data="csui_rev_send"),
            InlineKeyboardButton(text="🔄 Summalarni qayta yozaman", callback_data="csui_rev_retry"),
        ],
        [InlineKeyboardButton(text="📸 Rasmlarni qayta yuborish", callback_data="csui_rev_restart")],
    ])


def _decision_kb(shift_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"cashclose_ok:{shift_id}"),
        InlineKeyboardButton(text="❌ Rad etish", callback_data=f"cashclose_no:{shift_id}"),
    ]])


async def enter_flow(reply_target: Message, state: FSMContext, shift: dict) -> None:
    await state.update_data(
        review_notebook=None, review_pos=None, review_receipts=None, review_cash_received=None, review_cash_left=None,
    )
    await state.set_state(CloseReviewStates.notebook_photo)
    sent = await reply_target.answer(_PHOTO_STEPS[0][1], reply_markup=ReplyKeyboardRemove())
    chat_cleanup.track(cash_bot._CLOSESHIFT_WORKFLOW, str(shift["id"]), sent)


def _review_card(shift: dict, cash_received: int, cash_left: int) -> str:
    return "\n".join([
        "🧾 KASSA YOPISH — TEKSHIRUV",
        "",
        f"Filial: {shift.get('branch') or '-'}",
        f"Kassir: {cash_bot._employee_name(shift['employee_id'])}",
        f"Sana: {shift['shift_date']} (smena #{shift['id']})",
        "",
        f"Bugun qabul qilingan naqd: {cash_bot._format_amount(cash_received)} so'm",
        f"Kassada qoldirilgan naqd: {cash_bot._format_amount(cash_left)} so'm",
        "",
        "Rasmlar yuqorida: daftar, programma/POS, cheklar.",
    ])


def _reviewer_id() -> int:
    return find_user_by_role("moliyachi") or FOUNDER_ID


def register(dp: Dispatcher) -> None:

    async def _track(message: Message | None, shift_id: int) -> None:
        chat_cleanup.track(REVIEW_WORKFLOW, str(shift_id), message)

    @dp.message(
        StateFilter(CloseReviewStates.notebook_photo, CloseReviewStates.pos_photo, CloseReviewStates.receipts_photo),
        F.photo,
    )
    async def review_photo(message: Message, state: FSMContext) -> None:
        data = await state.get_data()
        current = await state.get_state()
        key = next(k for k, st in _PHOTO_STATES.items() if st.state == current)
        await state.update_data(**{key: message.photo[-1].file_id})
        await _track(message, data["shift_id"])  # kassirning o'z rasm xabari qaror bilan o'chiriladi

        following = _NEXT_AFTER_PHOTO[key]
        if following is not None:
            next_key, prompt = _PHOTO_STEPS[following]
            await state.set_state(_PHOTO_STATES[next_key])
            sent = await message.answer(prompt)
        else:
            await state.set_state(CloseReviewStates.cash_received)
            sent = await message.answer(_CASH_RECEIVED_PROMPT, reply_markup=_restart_kb())
        chat_cleanup.track(cash_bot._CLOSESHIFT_WORKFLOW, str(data["shift_id"]), sent)

    @dp.message(
        StateFilter(CloseReviewStates.notebook_photo, CloseReviewStates.pos_photo, CloseReviewStates.receipts_photo)
    )
    async def review_photo_missing(message: Message) -> None:
        await message.answer("❌ Iltimos, rasmni surat (photo) sifatida yuboring.")

    @dp.message(StateFilter(CloseReviewStates.cash_received))
    async def review_cash_received(message: Message, state: FSMContext) -> None:
        amount = cash_bot._parse_amount(message.text or "")
        if amount is None or amount < 0:
            await message.answer("❌ Faqat musbat raqam kiriting.", reply_markup=_restart_kb())
            return

        await state.update_data(review_cash_received=amount)
        await state.set_state(CloseReviewStates.cash_left)
        data = await state.get_data()
        sent = await message.answer(_CASH_LEFT_PROMPT, reply_markup=_restart_kb())
        chat_cleanup.track(cash_bot._CLOSESHIFT_WORKFLOW, str(data["shift_id"]), sent)

    @dp.message(StateFilter(CloseReviewStates.cash_left))
    async def review_cash_left(message: Message, state: FSMContext) -> None:
        amount = cash_bot._parse_amount(message.text or "")
        if amount is None or amount < 0:
            await message.answer("❌ Faqat musbat raqam kiriting.", reply_markup=_restart_kb())
            return

        await state.update_data(review_cash_left=amount)
        await state.set_state(CloseReviewStates.confirm)
        data = await state.get_data()
        sent = await message.answer(
            f"Qabul qilingan naqd: {cash_bot._format_amount(data['review_cash_received'])} so'm\n"
            f"Kassada qoldirilgan naqd: {cash_bot._format_amount(amount)} so'm\n\n"
            "Moliyachiga yuboraymi?",
            reply_markup=_confirm_kb(),
        )
        chat_cleanup.track(cash_bot._CLOSESHIFT_WORKFLOW, str(data["shift_id"]), sent)

    @dp.callback_query(F.data == "csui_rev_retry", StateFilter(CloseReviewStates.confirm))
    async def review_retry(callback: CallbackQuery, state: FSMContext) -> None:
        await state.set_state(CloseReviewStates.cash_received)
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(_CASH_RECEIVED_PROMPT, reply_markup=_restart_kb())
        await callback.answer()

    @dp.callback_query(
        F.data == "csui_rev_restart",
        StateFilter(
            CloseReviewStates.cash_received, CloseReviewStates.cash_left, CloseReviewStates.confirm,
        ),
    )
    async def review_restart(callback: CallbackQuery, state: FSMContext) -> None:
        data = await state.get_data()
        shift = cash_shift.get_shift(data["shift_id"]) if data.get("shift_id") else None
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.answer()
        if shift is None:
            await state.clear()
            await callback.message.answer("❌ Bekor qilindi. 🔴 Smenani topshirish tugmasini qayta bosing.")
            return
        await enter_flow(callback.message, state, shift)

    _pending: set[int] = set()

    @dp.callback_query(F.data == "csui_rev_send", StateFilter(CloseReviewStates.confirm))
    async def review_send(callback: CallbackQuery, state: FSMContext) -> None:
        user_id = callback.from_user.id
        if user_id in _pending:
            await callback.answer()
            return
        _pending.add(user_id)
        try:
            data = await state.get_data()
            shift_id = data["shift_id"]
            photos = [(key, data.get(key)) for key, _ in _PHOTO_STEPS]
            cash_received, cash_left = data.get("review_cash_received"), data.get("review_cash_left")
            if not all(file_id for _, file_id in photos) or cash_received is None or cash_left is None:
                await callback.answer("Ma'lumot to'liq emas. Qaytadan boshlang.", show_alert=True)
                return

            # Avval smena holati (atomik): takroriy bosish ikkinchi marta yubormaydi.
            if not cash_shift.submit_manual_close(shift_id, cash_received, cash_left):
                await state.clear()
                await callback.message.edit_reply_markup(reply_markup=None)
                await callback.answer("Bu smena allaqachon yuborilgan.", show_alert=True)
                return

            shift = cash_shift.get_shift(shift_id)
            reviewer = _reviewer_id()
            for key, file_id in photos:
                sent_photo = await callback.bot.send_photo(reviewer, file_id, caption=_PHOTO_CAPTIONS[key])
                await _track(sent_photo, shift_id)
            await callback.bot.send_message(
                reviewer, _review_card(shift, cash_received, cash_left), reply_markup=_decision_kb(shift_id)
            )

            await state.clear()
            await callback.message.edit_reply_markup(reply_markup=None)
            await chat_cleanup.cleanup(callback.bot, cash_bot._CLOSESHIFT_WORKFLOW, str(shift_id))
            await callback.message.answer("📤 Moliyachiga yuborildi. Tasdiqlashni kuting.")
            await callback.answer()
        finally:
            _pending.discard(user_id)

    async def _decide(callback: CallbackQuery, decision: str, result_text: str) -> None:
        if not await permissions.ensure_permission(callback, permissions.ACTION_REVIEW_CASH_CLOSE):
            return

        shift_id = int(callback.data.split(":", 1)[1])
        shift = cash_shift.get_shift(shift_id)
        if shift is None or shift["status"] != cash_shift.STATUS_NEEDS_FINANCE_REVIEW:
            await callback.answer("Bu smena hozir tekshiruv kutmayapti.", show_alert=True)
            return

        if not cash_shift.apply_finance_decision(shift_id, callback.from_user.id, decision):
            await callback.answer("Bu smena allaqachon hal qilingan.", show_alert=True)
            return

        # Rasm xabarlari ikkala chatdan o'chiriladi; bazada rasm yo'q edi.
        await chat_cleanup.cleanup(callback.bot, REVIEW_WORKFLOW, str(shift_id))
        if callback.message:
            await callback.message.edit_text(f"{callback.message.text}\n\n{result_text}", reply_markup=None)

        if decision == "approved":
            kassir_text = "✅ Moliyachi tasdiqladi. Smena topshirildi — qabul qiluvchi kassir tasdiqlashini kuting."
        else:
            kassir_text = (
                "❌ Moliyachi qaytardi. Rasmlar va summalarni qayta yuboring: 🔴 Smenani topshirish tugmasini bosing."
            )
        try:
            await callback.bot.send_message(shift["employee_id"], kassir_text)
        except Exception as error:  # noqa: BLE001
            print(f"Kassirga qaror xabarini yuborib bo'lmadi ({shift['employee_id']}): {error!r}")
        await callback.answer(result_text)

    @dp.callback_query(F.data.startswith("cashclose_ok:"))
    async def finance_approve(callback: CallbackQuery) -> None:
        await _decide(callback, "approved", "✅ Tasdiqlandi")

    @dp.callback_query(F.data.startswith("cashclose_no:"))
    async def finance_reject(callback: CallbackQuery) -> None:
        await _decide(callback, "rejected", "❌ Rad etildi — kassirdan qayta yuborish so'raldi")
