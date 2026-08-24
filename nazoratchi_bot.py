"""Nazoratchi kunlik nazorat oqimi: filial -> aktiv xodimlar -> xodim
kartasi. Bosqichlab quriladi (qarang loyihaning "VAZIFA + NAZORATCHI +
BONUS" vazifasi) — bu fayl har bosqichda kengaytiriladi. Hozircha:
1-bosqich (filial/xodim ko'rish), 2-bosqich (kartada doimiy vazifalar,
``/vazifabiriktir``/``/vazifabekor`` orqali Founder boshqaradi, xodim
hech narsa bosmaydi), 3-bosqich (vaqt bonusi — qo'lda fallback
tasdiqlash, ``time_bonus_grants``dagi ``UNIQUE(employee_id,
grant_date)`` orqali duplicate/race-safe; avtomatik davomat manbai
ulanganda ``source=AUTO`` bilan xuddi shu jadvalga yozadi va bu
tugmani ko'rsatishni to'xtatadi — ikkalasi bir-birini bosib
o'tolmaydi) va 4-bosqich (ISH BAHOSI 0/1/2/3 — mavjud
``daily_evaluations``/``record_daily_grade`` qayta ishlatiladi,
faqat yangi "bajarilmagan"=0 daraja qo'shilgan; mavjud
``/baholash``dagi Chala/Norma/A'lo uchtaligi hardcoded bo'lgani
uchun o'zgarishsiz qoladi), 5-bosqich (BALL AYIRISH — faqat Founder
``/setnizombahosi`` bilan miqdor belgilagan nizom bandlari tugma
sifatida chiqadi, xodimga Tushundim/E'tirozim bor tugmali xabar
boradi, E'tiroz mavjud ``discipline_bot.AppealStates``ni qayta
ishlatadi) va 6-bosqich (📝 Boshqa holat — AI
(``services/discipline_ai.match_incident_to_rule``) erkin matnni
FAQAT mavjud, tasdiqlangan nizom bandlari bilan mazmunan
solishtiradi, hech qachon yangi band/miqdor o'ylab topmaydi;
mos topilsa Nazoratchiga albatta tasdiqlatiladi, topilmasa yoki AI
xato bersa 5-bosqichdagi "Founderga to'g'ridan-to'g'ri yuborish"
xatti-harakati o'zgarishsiz davom etadi).

Mavjud naqshlardan qayta foydalanadi: filial nomlari
``RECRUITING_BRANCH_NAMES``dan (config, hardcode emas), aktiv
xodimlar ``employees.list_approved_by_branch()``dan (Founder'ning
"🏬 Do'konlar" filial kartasida ham ishlatiladi). Ruxsat —
``permissions.ACTION_EVALUATE_EMPLOYEE`` (nazoratchi allaqachon shu
amalga ega, ``/baholash`` bilan bir xil ruxsat — yangi ACTION_*
qo'shilmadi).

Founder ham (barcha amallarga ruxsatli bo'lgani uchun) shu oqimni
ishlata oladi — filial-mustaqil ko'rish huquqi
``permissions._CROSS_BRANCH_ROLES``da nazoratchi allaqachon bor."""

from aiogram import Dispatcher, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import company_time
import discipline_bot
import employees
from config import FOUNDER_ID, RECRUITING_BRANCH_NAMES
from roles import role_name
from services import discipline, discipline_ai, permissions, tasks as tasks_service, time_bonus as time_bonus_service


class PenaltyOtherStates(StatesGroup):
    waiting_reason = State()
    confirming_match = State()


_CB_BRANCHES = "nzr_branches"
_CB_BRANCH_PREFIX = "nzr_branch:"
_CB_EMPLOYEE_PREFIX = "nzr_emp:"
_CB_TIME_BONUS_PREFIX = "nzr_timebonus:"
_CB_GRADE_PREFIX = "nzr_grade:"
_CB_PENALTY_PREFIX = "nzr_penalty:"
_CB_PENALTY_APPLY_PREFIX = "nzr_penalty_apply:"
_CB_PENALTY_OTHER_PREFIX = "nzr_penalty_other:"
_CB_ACK_PREFIX = "nzr_ack:"
_CB_APPEAL_PREFIX = "nzr_appeal:"
_CB_MATCH_CONFIRM_PREFIX = "nzr_match_yes:"
_CB_MATCH_REJECT_PREFIX = "nzr_match_no:"

_SOURCE_LABELS = {
    time_bonus_service.SOURCE_AUTO: "AVTO",
    time_bonus_service.SOURCE_MANUAL: "QO'LDA",
}

# Ish bahosi: 0/1/2/3 tugmalari mavjud discipline.GRADE_* darajalarga
# mos keladi ("bajarilmagan" 4-daraja sifatida qo'shilgan — mavjud
# /baholash oqimidagi Chala/Norma/A'lo uchtaligiga TEGILMAGAN, u
# o'zgarishsiz qoladi, bu FAQAT yangi kartaning o'z tugma to'plami).
_GRADE_BUTTONS: tuple[tuple[str, str], ...] = (
    ("0", discipline.GRADE_BAJARILMAGAN),
    ("1", discipline.GRADE_CHALA),
    ("2", discipline.GRADE_NORMA),
    ("3", discipline.GRADE_ALO),
)


def _branches_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"📍 {name}", callback_data=f"{_CB_BRANCH_PREFIX}{i}")]
            for i, name in enumerate(RECRUITING_BRANCH_NAMES)
        ]
    )


def _branch_by_index(index: int) -> str | None:
    if 0 <= index < len(RECRUITING_BRANCH_NAMES):
        return RECRUITING_BRANCH_NAMES[index]
    return None


def _branch_index(branch: str) -> int | None:
    try:
        return RECRUITING_BRANCH_NAMES.index(branch)
    except ValueError:
        return None


def _employee_label(profile: dict) -> str:
    full_name = " ".join(part for part in (profile.get("familiya"), profile.get("ism")) if part) or "-"
    return f"👤 {full_name}"


def _employees_keyboard(branch: str) -> InlineKeyboardMarkup | None:
    """Filialdagi aktiv xodimlar — yonma-yon (2 tadan qatorda), o'qishga
    qulay tartibda (familiya/ism bo'yicha, ``list_approved_by_branch``
    allaqachon shunday saralaydi)."""
    active_employees = employees.list_approved_by_branch(branch)
    if not active_employees:
        return None

    buttons = [
        InlineKeyboardButton(text=_employee_label(profile), callback_data=f"{_CB_EMPLOYEE_PREFIX}{profile['user_id']}")
        for profile in active_employees
    ]
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    rows.append([InlineKeyboardButton(text="⬅️ Filiallar", callback_data=_CB_BRANCHES)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _simple_employee_card_text(profile: dict) -> str:
    full_name = " ".join(part for part in (profile.get("familiya"), profile.get("ism")) if part) or "-"
    lines = [
        f"👤 {full_name}",
        f"🏷 Lavozim: {role_name(profile.get('role_key'))}",
        f"🏬 Filial: {profile.get('branch') or '-'}",
    ]

    assigned_tasks = tasks_service.list_tasks_for_employee(profile["user_id"])
    lines.append("")
    if assigned_tasks:
        lines.append("📌 Doimiy vazifalar:")
        lines.extend(f"  • {title}" for title in assigned_tasks)
    else:
        lines.append("📌 Doimiy vazifalar: Ma'lumot yo'q")

    lines.append("")
    time_bonus = time_bonus_service.get_today_status(profile["user_id"])
    if time_bonus is None:
        lines.append("🕒 Bugungi vaqt bonusi: hali tasdiqlanmagan")
    else:
        source_label = _SOURCE_LABELS.get(time_bonus["source"], time_bonus["source"])
        lines.append(f"🕒 Bugungi vaqt bonusi: ✅ berildi ({source_label})")

    lines.append("")
    today = company_time.today().isoformat()
    grade = discipline.get_daily_grade(profile["user_id"], today)
    if grade is None:
        lines.append("⭐ Bugungi ish bahosi: hali qo'yilmagan")
    else:
        label = discipline.GRADE_LABELS.get(grade["grade_key"], grade["grade_key"])
        lines.append(f"⭐ Bugungi ish bahosi: {grade['grade_points']} ({label})")

    return "\n".join(lines)


def _employee_card_keyboard(branch: str | None, user_id: int, *, show_time_bonus_button: bool) -> InlineKeyboardMarkup:
    back_data = _CB_BRANCHES
    if branch is not None:
        index = _branch_index(branch)
        if index is not None:
            back_data = f"{_CB_BRANCH_PREFIX}{index}"

    rows = []
    if show_time_bonus_button:
        rows.append(
            [InlineKeyboardButton(text="➕ Vaqt bonusini tasdiqlash", callback_data=f"{_CB_TIME_BONUS_PREFIX}{user_id}")]
        )
    rows.append(
        [
            InlineKeyboardButton(text=label, callback_data=f"{_CB_GRADE_PREFIX}{user_id}:{grade_key}")
            for label, grade_key in _GRADE_BUTTONS
        ]
    )
    rows.append([InlineKeyboardButton(text="➖ Ball ayirish", callback_data=f"{_CB_PENALTY_PREFIX}{user_id}")])
    rows.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data=back_data)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _penalty_rule_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Faqat Founder tomonidan ball miqdori belgilangan ("tasdiqlangan")
    nizom bandlari — AI ham, Nazoratchi ham yangi miqdorni o'zi
    o'ylab topmaydi (qarang ``discipline.list_rules_with_penalty_amount``)."""
    rules = discipline.list_rules_with_penalty_amount()
    rows = [
        [
            InlineKeyboardButton(
                text=f"{rule['title']} — -{rule['default_penalty_amount']} ball",
                callback_data=f"{_CB_PENALTY_APPLY_PREFIX}{user_id}:{rule['rule_number']}",
            )
        ]
        for rule in rules
    ]
    rows.append([InlineKeyboardButton(text="📝 Boshqa holat", callback_data=f"{_CB_PENALTY_OTHER_PREFIX}{user_id}")])
    rows.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"{_CB_EMPLOYEE_PREFIX}{user_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _employee_notice_keyboard(penalty_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Tushundim", callback_data=f"{_CB_ACK_PREFIX}{penalty_id}"),
                InlineKeyboardButton(text="✋ E'tirozim bor", callback_data=f"{_CB_APPEAL_PREFIX}{penalty_id}"),
            ]
        ]
    )


def _match_confirm_keyboard(user_id: int, rule_number: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Ha, qo'llash", callback_data=f"{_CB_MATCH_CONFIRM_PREFIX}{user_id}:{rule_number}"
                ),
                InlineKeyboardButton(text="❌ Yo'q, Founderga yubor", callback_data=f"{_CB_MATCH_REJECT_PREFIX}{user_id}"),
            ]
        ]
    )


def register(dp: Dispatcher, openai_client) -> None:
    async def _notify_founder_unmatched(bot, employee_id: int, reported_by: int, text: str) -> None:
        discipline.report_unmatched_incident(employee_id, reported_by, text)
        profile = employees.get_profile(employee_id)
        full_name = (
            " ".join(part for part in (profile.get("familiya"), profile.get("ism")) if part) if profile else None
        ) or f"user_id {employee_id}"
        try:
            await bot.send_message(
                FOUNDER_ID,
                f"📝 Nazoratchi tomonidan yozilgan, tasdiqlangan nizomga mos kelmagan holat:\n\n"
                f"👤 Xodim: {full_name}\n"
                f"✍️ Nazoratchi yozuvi: {text}",
            )
        except Exception as error:  # noqa: BLE001
            print(f"Founderga 'boshqa holat' xabarini yuborib bo'lmadi: {error!r}")

    @dp.message(Command("filiallar"))
    async def filiallar_start(message: Message) -> None:
        if not await permissions.ensure_permission(message, permissions.ACTION_EVALUATE_EMPLOYEE):
            return

        await message.answer("🏬 Filiallar:", reply_markup=_branches_keyboard())

    @dp.callback_query(F.data == _CB_BRANCHES)
    async def branches_back(callback: CallbackQuery) -> None:
        if not await permissions.ensure_permission(callback, permissions.ACTION_EVALUATE_EMPLOYEE):
            return

        if callback.message:
            await callback.message.edit_text("🏬 Filiallar:", reply_markup=_branches_keyboard())
        await callback.answer()

    @dp.callback_query(F.data.startswith(_CB_BRANCH_PREFIX))
    async def branch_pick(callback: CallbackQuery) -> None:
        if not await permissions.ensure_permission(callback, permissions.ACTION_EVALUATE_EMPLOYEE):
            return

        index = int(callback.data.split(":", 1)[1])
        branch = _branch_by_index(index)
        if branch is None:
            await callback.answer("Filial topilmadi.", show_alert=True)
            return

        keyboard = _employees_keyboard(branch)
        if keyboard is None:
            await callback.answer()
            if callback.message:
                await callback.message.edit_text(
                    f"🏬 {branch}\n\n👥 Aktiv xodimlar: Ma'lumot yo'q",
                    reply_markup=InlineKeyboardMarkup(
                        inline_keyboard=[[InlineKeyboardButton(text="⬅️ Filiallar", callback_data=_CB_BRANCHES)]]
                    ),
                )
            return

        if callback.message:
            await callback.message.edit_text(f"🏬 {branch}\n\n👥 Xodimni tanlang:", reply_markup=keyboard)
        await callback.answer()

    @dp.callback_query(F.data.startswith(_CB_EMPLOYEE_PREFIX))
    async def employee_pick(callback: CallbackQuery) -> None:
        if not await permissions.ensure_permission(callback, permissions.ACTION_EVALUATE_EMPLOYEE):
            return

        user_id = int(callback.data.split(":", 1)[1])
        profile = employees.get_profile(user_id)
        if profile is None:
            await callback.answer("Xodim topilmadi.", show_alert=True)
            return

        if callback.message:
            await callback.message.edit_text(
                _simple_employee_card_text(profile),
                reply_markup=_employee_card_keyboard(
                    profile.get("branch"), user_id, show_time_bonus_button=time_bonus_service.get_today_status(user_id) is None
                ),
            )
        await callback.answer()

    @dp.callback_query(F.data.startswith(_CB_TIME_BONUS_PREFIX))
    async def time_bonus_confirm(callback: CallbackQuery) -> None:
        if not await permissions.ensure_permission(callback, permissions.ACTION_EVALUATE_EMPLOYEE):
            return

        user_id = int(callback.data.split(":", 1)[1])
        profile = employees.get_profile(user_id)
        if profile is None:
            await callback.answer("Xodim topilmadi.", show_alert=True)
            return

        granted = time_bonus_service.confirm_manual(user_id, callback.from_user.id)
        await callback.answer("✅ Vaqt bonusi tasdiqlandi." if granted else "ℹ️ Bugun uchun allaqachon tasdiqlangan.")

        if callback.message:
            await callback.message.edit_text(
                _simple_employee_card_text(profile),
                reply_markup=_employee_card_keyboard(profile.get("branch"), user_id, show_time_bonus_button=False),
            )

    @dp.callback_query(F.data.startswith(_CB_GRADE_PREFIX))
    async def grade_pick(callback: CallbackQuery) -> None:
        if not await permissions.ensure_permission(callback, permissions.ACTION_EVALUATE_EMPLOYEE):
            return

        parts = callback.data.split(":", 2)
        if len(parts) != 3:
            await callback.answer()
            return

        user_id = int(parts[1])
        grade_key = parts[2]
        profile = employees.get_profile(user_id)
        if profile is None:
            await callback.answer("Xodim topilmadi.", show_alert=True)
            return

        today = company_time.today().isoformat()
        discipline.record_daily_grade(user_id, callback.from_user.id, today, grade_key)
        await callback.answer(f"✅ Baho qayd etildi: {discipline.GRADE_LABELS[grade_key]}")

        if callback.message:
            await callback.message.edit_text(
                _simple_employee_card_text(profile),
                reply_markup=_employee_card_keyboard(
                    profile.get("branch"), user_id, show_time_bonus_button=time_bonus_service.get_today_status(user_id) is None
                ),
            )

    # --------------------------------------------------------- ball ayirish --

    @dp.callback_query(F.data.startswith(_CB_PENALTY_PREFIX))
    async def penalty_menu(callback: CallbackQuery) -> None:
        if not await permissions.ensure_permission(callback, permissions.ACTION_EVALUATE_EMPLOYEE):
            return

        user_id = int(callback.data.split(":", 1)[1])
        profile = employees.get_profile(user_id)
        if profile is None:
            await callback.answer("Xodim topilmadi.", show_alert=True)
            return

        full_name = " ".join(part for part in (profile.get("familiya"), profile.get("ism")) if part) or "-"
        keyboard = _penalty_rule_keyboard(user_id)
        text = f"👤 {full_name}\n\n➖ Qaysi nizom bandi bo'yicha ball ayiriladi?"
        if len(keyboard.inline_keyboard) <= 2:
            text += "\n\nℹ️ Hozircha tasdiqlangan ball miqdori bilan nizom bandi yo'q — Founder /setnizombahosi orqali belgilashi kerak."

        if callback.message:
            await callback.message.edit_text(text, reply_markup=keyboard)
        await callback.answer()

    @dp.callback_query(F.data.startswith(_CB_PENALTY_APPLY_PREFIX))
    async def penalty_apply(callback: CallbackQuery) -> None:
        if not await permissions.ensure_permission(callback, permissions.ACTION_EVALUATE_EMPLOYEE):
            return

        parts = callback.data.split(":", 2)
        if len(parts) != 3:
            await callback.answer()
            return

        user_id = int(parts[1])
        rule_number = int(parts[2])
        profile = employees.get_profile(user_id)
        rule = discipline.get_rule(rule_number)
        if profile is None or rule is None or rule.get("default_penalty_amount") is None:
            await callback.answer("Xodim yoki nizom bandi topilmadi.", show_alert=True)
            return

        amount = rule["default_penalty_amount"]
        today = company_time.today().isoformat()
        result = discipline.apply_penalty(
            user_id, callback.from_user.id, today, amount, rule_number, comment=None, ai_note=None
        )
        await callback.answer(f"✅ -{amount} ball qayd etildi ({rule['title']}).")

        full_name = " ".join(part for part in (profile.get("familiya"), profile.get("ism")) if part) or "-"
        if callback.message:
            await callback.message.edit_text(
                f"👤 {full_name}\n\n🚫 -{amount} ball ayirildi ({rule['title']}).\n"
                f"💰 Bonus banki: {result['bonus_bank_balance']} ball\n"
                "ℹ️ Fiks oylikka ta'sir qilmaydi.",
                reply_markup=_employee_card_keyboard(
                    profile.get("branch"), user_id, show_time_bonus_button=time_bonus_service.get_today_status(user_id) is None
                ),
            )

        try:
            await callback.bot.send_message(
                user_id,
                f"⚠️ Sizga -{amount} ball ayirildi.\nQoida: {rule['title']}\nSabab: {rule['content']}",
                reply_markup=_employee_notice_keyboard(result["penalty_id"]),
            )
        except Exception as error:  # noqa: BLE001
            print(f"Xodimga ball ayirish xabarini yuborib bo'lmadi ({user_id}): {error!r}")

    @dp.callback_query(F.data.startswith(_CB_PENALTY_OTHER_PREFIX))
    async def penalty_other_start(callback: CallbackQuery, state: FSMContext) -> None:
        if not await permissions.ensure_permission(callback, permissions.ACTION_EVALUATE_EMPLOYEE):
            return

        user_id = int(callback.data.split(":", 1)[1])
        if employees.get_profile(user_id) is None:
            await callback.answer("Xodim topilmadi.", show_alert=True)
            return

        await state.update_data(penalty_other_employee_id=user_id)
        await state.set_state(PenaltyOtherStates.waiting_reason)
        await callback.answer()
        if callback.message:
            await callback.message.answer("✍️ Holatni qisqacha yozing (masalan: \"Nazoratchini haqorat qildi\"):")

    @dp.message(StateFilter(PenaltyOtherStates.waiting_reason))
    async def penalty_other_reason(message: Message, state: FSMContext) -> None:
        data = await state.get_data()
        user_id = data.get("penalty_other_employee_id")

        text = (message.text or "").strip()
        if not text or user_id is None:
            await state.clear()
            await message.answer("❌ Bekor qilindi.")
            return

        # AI faqat MAVJUD, ball miqdori belgilangan ("tasdiqlangan")
        # nizom bandlaridan birini taklif qiladi (yoki hech birini) —
        # yakuniy qo'llashdan oldin Nazoratchiga ALBATTA tasdiqlatiladi
        # (qarang services/discipline_ai.match_incident_to_rule).
        eligible_rules = discipline.list_rules_with_penalty_amount()
        matched_rule_number = await discipline_ai.match_incident_to_rule(openai_client, text, eligible_rules)

        if matched_rule_number is not None:
            rule = discipline.get_rule(matched_rule_number)
            await state.update_data(penalty_other_text=text)
            await state.set_state(PenaltyOtherStates.confirming_match)
            await message.answer(
                f"🤖 Bu holat quyidagi nizom bandiga mos kelishi mumkin:\n"
                f"{matched_rule_number}-nizom: {rule['title']} — -{rule['default_penalty_amount']} ball\n\n"
                "Tasdiqlaysizmi?",
                reply_markup=_match_confirm_keyboard(user_id, matched_rule_number),
            )
            return

        await state.clear()
        await _notify_founder_unmatched(message.bot, user_id, message.from_user.id, text)
        await message.answer(
            "✅ Qabul qilindi — bu holat tasdiqlangan nizom bandiga mos kelmagani uchun "
            "ball ayirilmadi, Founder ko'rib chiqishi uchun yuborildi."
        )

    @dp.callback_query(F.data.startswith(_CB_MATCH_CONFIRM_PREFIX))
    async def match_confirm(callback: CallbackQuery, state: FSMContext) -> None:
        if not await permissions.ensure_permission(callback, permissions.ACTION_EVALUATE_EMPLOYEE):
            return

        parts = callback.data.split(":", 2)
        if len(parts) != 3:
            await callback.answer()
            return

        user_id = int(parts[1])
        rule_number = int(parts[2])
        await state.clear()

        profile = employees.get_profile(user_id)
        rule = discipline.get_rule(rule_number)
        if profile is None or rule is None or rule.get("default_penalty_amount") is None:
            await callback.answer("Xodim yoki nizom bandi topilmadi.", show_alert=True)
            return

        amount = rule["default_penalty_amount"]
        today = company_time.today().isoformat()
        result = discipline.apply_penalty(
            user_id, callback.from_user.id, today, amount, rule_number,
            comment=None, ai_note="AI 'Boshqa holat' matnini shu nizom bandiga mos topdi.",
        )
        await callback.answer(f"✅ -{amount} ball qayd etildi ({rule['title']}).")

        if callback.message:
            await callback.message.edit_text(
                f"✅ {rule['title']} bo'yicha -{amount} ball qayd etildi.\n"
                f"💰 Bonus banki: {result['bonus_bank_balance']} ball",
                reply_markup=None,
            )

        try:
            await callback.bot.send_message(
                user_id,
                f"⚠️ Sizga -{amount} ball ayirildi.\nQoida: {rule['title']}\nSabab: {rule['content']}",
                reply_markup=_employee_notice_keyboard(result["penalty_id"]),
            )
        except Exception as error:  # noqa: BLE001
            print(f"Xodimga ball ayirish xabarini yuborib bo'lmadi ({user_id}): {error!r}")

    @dp.callback_query(F.data.startswith(_CB_MATCH_REJECT_PREFIX))
    async def match_reject(callback: CallbackQuery, state: FSMContext) -> None:
        if not await permissions.ensure_permission(callback, permissions.ACTION_EVALUATE_EMPLOYEE):
            return

        data = await state.get_data()
        user_id = data.get("penalty_other_employee_id")
        text = data.get("penalty_other_text")
        await state.clear()

        if user_id is None or text is None:
            await callback.answer("Ma'lumot topilmadi (eskirgan holat).", show_alert=True)
            return

        await _notify_founder_unmatched(callback.bot, user_id, callback.from_user.id, text)
        await callback.answer("✅ Founderga yuborildi.")
        if callback.message:
            await callback.message.edit_text(
                "✅ Qabul qilindi — ball ayirilmadi, Founder ko'rib chiqishi uchun yuborildi.",
                reply_markup=None,
            )

    @dp.callback_query(F.data.startswith(_CB_ACK_PREFIX))
    async def employee_ack(callback: CallbackQuery) -> None:
        await callback.answer("✅ Qabul qilindi.")
        if callback.message:
            await callback.message.edit_reply_markup(reply_markup=None)

    @dp.callback_query(F.data.startswith(_CB_APPEAL_PREFIX))
    async def employee_appeal_start(callback: CallbackQuery, state: FSMContext) -> None:
        penalty_id = int(callback.data.split(":", 1)[1])
        await state.update_data(appeal_penalty_id=penalty_id)
        await state.set_state(discipline_bot.AppealStates.waiting_reason)
        await callback.answer()
        if callback.message:
            await callback.message.edit_reply_markup(reply_markup=None)
            await callback.message.answer("✍️ Sababingizni matn yoki ovozli xabar sifatida yuboring.")

    # ----------------------------------------------------- vazifa biriktirish --

    @dp.message(Command("vazifabiriktir"))
    async def assign_task_handler(message: Message) -> None:
        if not await permissions.ensure_permission(message, permissions.ACTION_MANAGE_TASK_ASSIGNMENTS):
            return

        parts = (message.text or "").split(maxsplit=2)
        if len(parts) < 3 or not parts[1].isdigit():
            await message.answer(
                "Foydalanish: /vazifabiriktir <user_id> <vazifa nomi>\n"
                "Masalan: /vazifabiriktir 123456789 Ombor"
            )
            return

        employee_id = int(parts[1])
        title = parts[2].strip()
        if employees.get_profile(employee_id) is None:
            await message.answer("❌ Bu user_id bilan xodim topilmadi.")
            return

        task = tasks_service.assign_task_to_employee(title, employee_id, message.from_user.id)
        await message.answer(f"✅ \"{task['title']}\" vazifasi xodimga biriktirildi.")

    @dp.message(Command("vazifabekor"))
    async def unassign_task_handler(message: Message) -> None:
        if not await permissions.ensure_permission(message, permissions.ACTION_MANAGE_TASK_ASSIGNMENTS):
            return

        parts = (message.text or "").split(maxsplit=2)
        if len(parts) < 3 or not parts[1].isdigit():
            await message.answer(
                "Foydalanish: /vazifabekor <user_id> <vazifa nomi>\n"
                "Masalan: /vazifabekor 123456789 Ombor"
            )
            return

        employee_id = int(parts[1])
        title = parts[2].strip()
        if tasks_service.unassign_task_from_employee(title, employee_id):
            await message.answer(f"✅ \"{title}\" vazifasi xodimdan olib tashlandi.")
        else:
            await message.answer("❌ Bu nomdagi vazifa topilmadi.")
