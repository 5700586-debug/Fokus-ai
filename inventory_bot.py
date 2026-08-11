"""Kunlik ombor/qoldiq qiymati nazorati — bot komandalari va kunlik
eslatma scheduler'i.

``services/inventory_snapshot.py`` biznes logikani ushlab turadi.
Rasmdan raqam avtomatik o'qilmaydi (``providers/vision_extraction_provider.py``
hali Null) — Savdo bo'limi boshlig'i jami ombor summasini har doim
qo'lda kiritadi, rasm faqat hujjat sifatida ilova qilinadi.
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
from services import inventory_snapshot as inv
from services import notifications, permissions
from services import rules as rules_service

_YES_TEXT = "Ha"
_NO_TEXT = "Yo'q"
_SKIP_TEXT = "➖ O'tkazib yuborish"

_CAUSE_LABELS = {
    "prixod": "📦 Yangi yuk/prixod",
    "katta_savdo": "💰 Katta savdo",
    "hisobdan_chiqarish": "🗑 Hisobdan chiqarish",
    "qaytarish": "↩️ Qaytarish",
    "narx_correction": "🏷 Narx/korreksiya",
    "kiritish_xatosi": "✍️ Kiritishdagi xato",
    "boshqa": "➖ Boshqa",
}
_LABEL_TO_CAUSE = {label: key for key, label in _CAUSE_LABELS.items()}

_STATUS_LABELS = {
    inv.STATUS_NORMAL: "🟢 Normal",
    inv.STATUS_NEEDS_REVIEW: "🟡 Tekshirish kerak",
    inv.STATUS_URGENT_REVIEW: "🔴 Zudlik bilan tekshirish",
}


def _kb(*rows: list[str]) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=text) for text in row] for row in rows],
        resize_keyboard=True,
    )


_SKIP_KB = _kb([_SKIP_TEXT])
_YES_NO_KB = _kb([_YES_TEXT, _NO_TEXT])
_CAUSE_KB = _kb(*[[label] for label in _CAUSE_LABELS.values()])


def _review_keyboard(snapshot_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Tekshirildi/yopish", callback_data=f"invvariance_resolve:{snapshot_id}"),
                InlineKeyboardButton(text="🔁 Qo'shimcha izoh so'rash", callback_data=f"invvariance_recheck:{snapshot_id}"),
            ],
        ]
    )


def _format_snapshot_summary(snapshot: dict, causes: list[dict]) -> str:
    lines = [
        "📦 OMBOR — KUNLIK NAZORAT",
        "",
        f"Sana: {snapshot['snapshot_date']}",
        f"Filial: {snapshot.get('branch') or 'Umumiy'}",
        "",
        f"Kecha: {snapshot['previous_inventory_value'] if snapshot['previous_inventory_value'] is not None else '-'}",
        f"Bugun: {snapshot['total_inventory_value']}",
        f"Umumiy farq: {snapshot['gross_difference'] if snapshot['gross_difference'] is not None else 0}",
    ]

    if causes:
        lines.append("")
        lines.append("Tasdiqlangan sabablar:")
        for cause in causes:
            lines.append(f"  {_CAUSE_LABELS.get(cause['cause'], cause['cause'])}: {cause['amount']}")

    lines += [
        "",
        f"Tushuntirilgan: {snapshot['explained_variance']}",
        f"Tushuntirilmagan: {snapshot['unexplained_variance'] if snapshot['unexplained_variance'] is not None else 0}",
        "",
        f"Status: {_STATUS_LABELS.get(snapshot['status'], snapshot['status'])}",
    ]
    return "\n".join(lines)


class InventorySnapshotStates(StatesGroup):
    photo = State()
    total_value = State()
    cause_select = State()
    cause_amount = State()
    cause_comment = State()
    add_more = State()


def _parse_amount(text: str) -> int | None:
    cleaned = text.strip().replace(" ", "").replace("'", "").replace(",", "")
    if not cleaned.lstrip("-").isdigit():
        return None
    return int(cleaned)


async def _send_variance_for_review(message: Message, snapshot: dict) -> None:
    causes = inv.get_causes(snapshot["id"])
    text = "Voydod 👀\n\nBugungi ombor hisobotida tushuntirilmagan tafovut chiqdi.\n\n" + _format_snapshot_summary(
        snapshot, causes
    )

    from roles import find_user_by_role

    recipients = {FOUNDER_ID}
    nazoratchi_id = find_user_by_role("nazoratchi")
    if nazoratchi_id is not None:
        recipients.add(nazoratchi_id)

    for recipient_id in recipients:
        await message.bot.send_message(recipient_id, text, reply_markup=_review_keyboard(snapshot["id"]))


def register(dp: Dispatcher) -> None:

    # -------------------------------------------------------- /invsnapshot --

    @dp.message(Command("invsnapshot"))
    async def invsnapshot_start(message: Message, state: FSMContext) -> None:
        if not message.from_user or not permissions.has_permission(
            message.from_user.id, permissions.ACTION_SUBMIT_INVENTORY_SNAPSHOT
        ):
            return

        await state.set_state(InventorySnapshotStates.photo)
        await message.answer(
            "📸 Bugungi ombor/qoldiq hisobotini rasmga olib yuboring:", reply_markup=ReplyKeyboardRemove()
        )

    @dp.message(StateFilter(InventorySnapshotStates.photo), F.photo)
    async def invsnapshot_photo(message: Message, state: FSMContext) -> None:
        file_id = message.photo[-1].file_id
        get_file_storage_provider().register(file_id, message.from_user.id, "inventory_snapshot_photo")

        await state.update_data(photo_reference=file_id)
        await state.set_state(InventorySnapshotStates.total_value)
        await message.answer("Jami ombor/qoldiq summasini kiriting:")

    @dp.message(StateFilter(InventorySnapshotStates.photo))
    async def invsnapshot_photo_missing(message: Message) -> None:
        await message.answer("❌ Iltimos, rasmni surat (photo) sifatida yuboring.")

    @dp.message(StateFilter(InventorySnapshotStates.total_value))
    async def invsnapshot_total_value(message: Message, state: FSMContext) -> None:
        amount = _parse_amount(message.text or "")
        if amount is None or amount < 0:
            await message.answer("❌ Faqat musbat raqam kiriting.")
            return

        data = await state.get_data()
        user_id = message.from_user.id
        profile = get_profile(user_id)
        branch = profile.get("branch") if profile else None

        outcome = inv.create_snapshot_for_today(
            branch, company_time.today().isoformat(), user_id, amount, data.get("photo_reference")
        )

        if outcome.already_existed:
            await state.clear()
            await message.answer(
                "ℹ️ Bugungi ombor hisoboti allaqachon yuborilgan.", reply_markup=ReplyKeyboardRemove()
            )
            return

        if not outcome.needs_cause_explanation:
            await state.clear()
            await message.answer(
                _format_snapshot_summary(outcome.snapshot, []), reply_markup=ReplyKeyboardRemove()
            )
            return

        await state.update_data(snapshot_id=outcome.snapshot["id"])
        await state.set_state(InventorySnapshotStates.cause_select)
        gross = outcome.snapshot["gross_difference"]
        await message.answer(
            f"Bugungi farq: {gross} so'm.\n\nBugungi farqning sababi qaysi?", reply_markup=_CAUSE_KB
        )

    @dp.message(StateFilter(InventorySnapshotStates.cause_select))
    async def invsnapshot_cause_select(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        cause = _LABEL_TO_CAUSE.get(text)
        if cause is None:
            await message.answer("Iltimos, tugmalardan birini tanlang.", reply_markup=_CAUSE_KB)
            return

        await state.update_data(pending_cause=cause)
        await state.set_state(InventorySnapshotStates.cause_amount)
        await message.answer("Shu sabab bo'yicha summani kiriting:", reply_markup=ReplyKeyboardRemove())

    @dp.message(StateFilter(InventorySnapshotStates.cause_amount))
    async def invsnapshot_cause_amount(message: Message, state: FSMContext) -> None:
        amount = _parse_amount(message.text or "")
        if amount is None:
            await message.answer("❌ Faqat raqam kiriting.")
            return

        await state.update_data(pending_amount=amount)
        await state.set_state(InventorySnapshotStates.cause_comment)
        await message.answer("Izoh (bo'lmasa o'tkazib yuboring):", reply_markup=_SKIP_KB)

    @dp.message(StateFilter(InventorySnapshotStates.cause_comment))
    async def invsnapshot_cause_comment(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        comment = None if text == _SKIP_TEXT else text

        data = await state.get_data()
        result = inv.add_cause_and_recompute(data["snapshot_id"], data["pending_cause"], data["pending_amount"], comment)

        await state.update_data(pending_cause=None, pending_amount=None)
        await state.set_state(InventorySnapshotStates.add_more)
        await message.answer(
            f"✅ Sabab qo'shildi.\nTushuntirilgan: {result.explained_variance}\n"
            f"Tushuntirilmagan: {result.unexplained_variance}\n\nYana sabab qo'shasizmi?",
            reply_markup=_YES_NO_KB,
        )

    @dp.message(StateFilter(InventorySnapshotStates.add_more))
    async def invsnapshot_add_more(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        if text not in (_YES_TEXT, _NO_TEXT):
            await message.answer("Iltimos, tugmalardan birini tanlang.", reply_markup=_YES_NO_KB)
            return

        data = await state.get_data()
        snapshot_id = data["snapshot_id"]

        if text == _YES_TEXT:
            await state.set_state(InventorySnapshotStates.cause_select)
            await message.answer("Yana qaysi sabab?", reply_markup=_CAUSE_KB)
            return

        await state.clear()
        snapshot = inv.get_snapshot(snapshot_id)
        causes = inv.get_causes(snapshot_id)
        await message.answer(_format_snapshot_summary(snapshot, causes), reply_markup=ReplyKeyboardRemove())

        if snapshot["status"] == inv.STATUS_URGENT_REVIEW:
            await _send_variance_for_review(message, snapshot)

    # -------------------------------------------------------- supervisor review --

    @dp.callback_query(F.data.startswith("invvariance_resolve:"))
    async def handle_invvariance_resolve(callback: CallbackQuery) -> None:
        await _handle_variance_decision(callback, "resolved", "✅ Tekshirildi va yopildi")

    @dp.callback_query(F.data.startswith("invvariance_recheck:"))
    async def handle_invvariance_recheck(callback: CallbackQuery) -> None:
        await _handle_variance_decision(callback, "recheck", "🔁 Qo'shimcha izoh so'raldi")

    async def _handle_variance_decision(callback: CallbackQuery, decision: str, ack_text: str) -> None:
        if not callback.from_user or not permissions.has_permission(
            callback.from_user.id, permissions.ACTION_REVIEW_INVENTORY_VARIANCE
        ):
            await callback.answer()
            return

        snapshot_id = int(callback.data.split(":", 1)[1])
        snapshot = inv.get_snapshot(snapshot_id)
        if snapshot is None:
            await callback.answer("Snapshot topilmadi.", show_alert=True)
            return

        inv.record_supervisor_review(snapshot_id, callback.from_user.id, decision, comment=None)

        if callback.message:
            await callback.message.edit_reply_markup(reply_markup=None)

        if decision == "recheck":
            await callback.bot.send_message(
                snapshot["reported_by_employee_id"],
                "🔁 Nazoratchi/Founder bugungi ombor tafovuti bo'yicha qo'shimcha izoh so'radi. "
                "/invsnapshot orqali qo'shimcha sabab qo'shishingiz mumkin.",
            )
        else:
            await callback.bot.send_message(
                snapshot["reported_by_employee_id"], "✅ Bugungi ombor tafovuti tekshirildi va yopildi."
            )

        await callback.answer(ack_text)

    # ------------------------------------------------------- /inventorysummary --

    @dp.message(Command("inventorysummary"))
    async def inventorysummary_handler(message: Message) -> None:
        if not message.from_user:
            return

        parts = (message.text or "").split(maxsplit=1)
        branch: str | None

        if len(parts) > 1 and parts[1].strip():
            if not (
                permissions.has_permission(message.from_user.id, permissions.ACTION_VIEW_INVENTORY_SUMMARY)
                or permissions.has_permission(message.from_user.id, permissions.ACTION_REVIEW_INVENTORY_VARIANCE)
            ):
                return
            branch = parts[1].strip()
        elif permissions.has_permission(message.from_user.id, permissions.ACTION_SUBMIT_INVENTORY_SNAPSHOT):
            profile = get_profile(message.from_user.id)
            branch = profile.get("branch") if profile else None
        else:
            return

        from repositories import inventory as inventory_repo

        snapshot = inventory_repo.get_snapshot_for_date(branch, company_time.today().isoformat())
        if snapshot is None:
            await message.answer("ℹ️ Bugun uchun ombor hisoboti topilmadi.")
            return

        causes = inv.get_causes(snapshot["id"])
        await message.answer(_format_snapshot_summary(snapshot, causes))


# --------------------------------------------------------------- scheduler --


async def send_daily_reminders(bot) -> None:
    """Savdo bo'limi boshlig'i rolidagi barcha xodimlarga bugungi
    ombor hisobotini so'rab eslatma yuboradi. ``notifications.send_once``
    orqali idempotent — bir xil kunda bir foydalanuvchiga ikki marta
    yuborilmaydi.
    """
    from roles import list_users

    today = company_time.today().isoformat()
    for user_id, info in list_users().items():
        if info["role"] != "savdo_boshligi":
            continue

        await notifications.send_once(
            bot,
            f"inventory_reminder:{today}:{user_id}",
            user_id,
            "📸 Bugungi ombor/qoldiq hisobotini rasmga olib yuboring. /invsnapshot",
        )


async def _reminder_tick(bot) -> None:
    reminder_time = rules_service.get_inventory_reminder_time()
    current_hm = company_time.now().strftime("%H:%M")
    if current_hm < reminder_time:
        return

    await send_daily_reminders(bot)


def start_scheduler(bot):
    """``main.py`` bot ishga tushganda chaqiradi. Har 5 daqiqada joriy
    vaqtni ``inventory.reminder_time`` qoidasi bilan solishtiradi;
    yetgan bo'lsa (va bugun hali yuborilmagan bo'lsa) eslatma yuboradi.
    """
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    scheduler = AsyncIOScheduler()
    scheduler.add_job(_reminder_tick, "interval", minutes=5, args=[bot], id="inventory_daily_reminder")
    scheduler.start()
    return scheduler
