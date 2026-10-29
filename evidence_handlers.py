"""S2 — rasm-dalil. Faqat Telegram ``file_id`` saqlanadi: rasm yuklab olinmaydi va diskka yozilmaydi.

Minus (ball ayirish) uchun rasm MAJBURIY: minus oqimlari ``request_penalty_photo`` bilan barcha ma'lumotni
FSM'ga qo'yadi (bazaga hech narsa yozilmaydi), nazoratchi rasm yuborgandagina o'sha oqimning "finisher"i
``services.evidence_photo.apply_pending_penalty`` orqali minusni dalil bilan yozadi.

0 ball ("bajarilmagan") uchun rasm IXTIYORIY: baho darhol saqlanadi, keyin ``request_grade_photo``.

``register`` boshqa xabar handlerlaridan OLDIN chaqirilishi kerak (``discipline_bot.register`` boshida).
"""

import logging
import time
from collections.abc import Awaitable, Callable

from aiogram import Dispatcher, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from services import permissions

logger = logging.getLogger(__name__)

CANCEL = "❌ Bekor qilish"
SKIP = "⏭ O'tkazib yuborish"
CB_CANCEL = "ev:cancel"
CB_SKIP = "ev:skip"
# Rasm kutish shu vaqtdan oshsa minus qo'llanmaydi — unutilgan holatga keyinroq boshqa rasm tushib qolmasin.
PENDING_TTL_SECONDS = 15 * 60
CAPTION_LIMIT = 1024

PenaltyFinisher = Callable[[Message, dict, str], Awaitable[None]]
_FINISHERS: dict[str, PenaltyFinisher] = {}


class EvidenceStates(StatesGroup):
    waiting_photo = State()
    waiting_optional_grade_photo = State()


def register_finisher(source: str, finisher: PenaltyFinisher) -> None:
    """Har bir minus oqimi rasm kelgandan keyin minusni yozuvchi va natijani ko'rsatuvchi funksiyasini qayd etadi."""
    _FINISHERS[source] = finisher


def _keyboard(optional: bool = False) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=CANCEL, callback_data=CB_CANCEL)]]
    if optional:
        rows.insert(0, [InlineKeyboardButton(text=SKIP, callback_data=CB_SKIP)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def request_penalty_photo(target: Message, state: FSMContext, *, source: str, supervisor_id: int, **payload) -> None:
    """Minusni YOZMASDAN barcha ma'lumotni FSM'ga qo'yadi va dalil rasmini so'raydi."""
    if source not in _FINISHERS:
        raise ValueError(f"noma'lum minus oqimi: {source}")
    await state.clear()
    await state.update_data(evidence_pending={
        "source": source, "supervisor_id": supervisor_id, "created": time.time(), **payload,
    })
    await state.set_state(EvidenceStates.waiting_photo)
    await target.answer(
        "📷 Minus uchun dalil rasmini yuboring.\nRasmsiz minus yozilmaydi.", reply_markup=_keyboard()
    )


async def request_grade_photo(target: Message, state: FSMContext, *, employee_id: int, supervisor_id: int, eval_date: str) -> None:
    """0 ball bahosi allaqachon saqlangan; ixtiyoriy dalil rasmini taklif qiladi."""
    await state.clear()
    await state.update_data(grade_pending={
        "employee_id": employee_id, "supervisor_id": supervisor_id, "eval_date": eval_date, "created": time.time(),
    })
    await state.set_state(EvidenceStates.waiting_optional_grade_photo)
    await target.answer("📷 Dalil rasmi (ixtiyoriy) — rasm yuboring yoki o'tkazib yuboring.", reply_markup=_keyboard(True))


async def send_evidence_notice(bot, chat_id: int, evidence_file_id: str | None, text: str, *, reply_markup=None):
    """Xodimga xabar: rasm bo'lsa rasm + izoh (Telegram izoh chegarasi 1024), aks holda oddiy matn.
    Mavjud tugmalar (masalan e'tiroz) saqlanadi."""
    if evidence_file_id:
        return await bot.send_photo(chat_id, evidence_file_id, caption=text[:CAPTION_LIMIT], reply_markup=reply_markup)
    return await bot.send_message(chat_id, text, reply_markup=reply_markup)


def _expired(pending: dict) -> bool:
    created = pending.get("created")
    return not isinstance(created, (int, float)) or time.time() - created > PENDING_TTL_SECONDS


def register(dp: Dispatcher) -> None:
    """Boshqa xabar handlerlaridan OLDIN chaqirilsin — rasm kutish holati ustun bo'lsin."""

    @dp.callback_query(F.data.in_({CB_CANCEL, CB_SKIP}))
    async def evidence_buttons(callback: CallbackQuery, state: FSMContext) -> None:
        current = await state.get_state()
        if current == EvidenceStates.waiting_photo.state and callback.data == CB_CANCEL:
            await state.clear()
            text = "❌ Minus bekor qilindi — rasm yuborilmadi, ball ayirilmadi."
        elif current == EvidenceStates.waiting_optional_grade_photo.state:
            await state.clear()
            text = "✅ Baho saqlangan. Dalil rasmi qo'shilmadi."
        else:
            await callback.answer("Bu tugma eskirgan.", show_alert=True)
            return
        await callback.answer()
        if callback.message:
            try:
                await callback.message.edit_text(text, reply_markup=None)
            except Exception:  # noqa: BLE001 - xabar o'zgarmagan/eskirgan bo'lsa yangisini yuboramiz
                await callback.message.answer(text)

    @dp.message(StateFilter(EvidenceStates.waiting_photo))
    async def evidence_penalty_photo(message: Message, state: FSMContext) -> None:
        pending = (await state.get_data()).get("evidence_pending") or {}
        if not message.photo:
            # Menyu tugmasi yoki boshqa matn: minus yozilmaydi, holat yutib yuborilmaydi.
            await state.clear()
            await message.answer("❌ Minus bekor qilindi — rasm yuborilmadi, ball ayirilmadi.")
            return
        actor_id = message.from_user.id if message.from_user else None
        finisher = _FINISHERS.get(pending.get("source"))
        if actor_id is None or finisher is None or pending.get("supervisor_id") != actor_id or _expired(pending):
            await state.clear()
            await message.answer("⌛ Minus tasdig'i eskirgan — ball ayirilmadi. Qaytadan boshlang.")
            return
        if not permissions.has_permission(actor_id, permissions.ACTION_EVALUATE_EMPLOYEE):
            await state.clear()
            await message.answer("Ruxsat yo'q — ball ayirilmadi.")
            return

        import discipline_bot  # aylanma importdan qochish uchun shu yerda

        if actor_id in discipline_bot._PENDING_PENALTY_APPLICATIONS:
            await message.answer("Avvalgi minus yakunlanmoqda, kuting.")
            return
        discipline_bot._PENDING_PENALTY_APPLICATIONS.add(actor_id)
        try:
            # Holat minus yozilishidan OLDIN tozalanadi: takroriy rasm ikkinchi minus yaratmaydi.
            await state.clear()
            await finisher(message, pending, message.photo[-1].file_id)
        finally:
            discipline_bot._PENDING_PENALTY_APPLICATIONS.discard(actor_id)

    @dp.message(StateFilter(EvidenceStates.waiting_optional_grade_photo))
    async def optional_grade_photo(message: Message, state: FSMContext) -> None:
        pending = (await state.get_data()).get("grade_pending") or {}
        await state.clear()
        if not message.photo:
            await message.answer("✅ Baho saqlangan. Dalil rasmi qo'shilmadi.")
            return
        actor_id = message.from_user.id if message.from_user else None
        employee_id, eval_date = pending.get("employee_id"), pending.get("eval_date")
        if (
            actor_id is None or pending.get("supervisor_id") != actor_id or _expired(pending)
            or not permissions.has_permission(actor_id, permissions.ACTION_EVALUATE_EMPLOYEE)
            or not isinstance(employee_id, int) or not isinstance(eval_date, str)
        ):
            await message.answer("Dalil saqlanmadi (eskirgan yoki ruxsat yo'q).")
            return

        import company_time
        from repositories import discipline as discipline_repo
        from services import nazoratchi_day

        if nazoratchi_day.check_active(actor_id, eval_date, company_time.now()) is not None:
            await message.answer("Kun yopilgan — dalil saqlanmadi.")
            return
        file_id = message.photo[-1].file_id
        if discipline_repo.attach_grade_evidence(employee_id, eval_date, file_id) != 1:
            await message.answer("Baho o'zgargan — dalil saqlanmadi.")
            return
        day = f"{eval_date[8:10]}.{eval_date[5:7]}.{eval_date[:4]}"
        try:
            await send_evidence_notice(message.bot, employee_id, file_id, f"📅 {day}: Bajarilmagan (0 ball) — dalil rasmi")
        except Exception as error:  # noqa: BLE001 - dalil saqlangan; yetkazish xatosi bahoni bekor qilmaydi
            logger.warning("Dalil rasmini xodimga yuborib bo'lmadi: %s", type(error).__name__)
            await message.answer("✅ Dalil saqlandi, lekin xodimga yuborib bo'lmadi.")
            return
        await message.answer("✅ Dalil saqlandi va xodimga yuborildi.")
