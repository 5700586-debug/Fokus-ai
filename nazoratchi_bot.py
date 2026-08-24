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
uchun o'zgarishsiz qoladi).

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
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import company_time
import employees
from config import RECRUITING_BRANCH_NAMES
from roles import role_name
from services import discipline, permissions, tasks as tasks_service, time_bonus as time_bonus_service

_CB_BRANCHES = "nzr_branches"
_CB_BRANCH_PREFIX = "nzr_branch:"
_CB_EMPLOYEE_PREFIX = "nzr_emp:"
_CB_TIME_BONUS_PREFIX = "nzr_timebonus:"
_CB_GRADE_PREFIX = "nzr_grade:"

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
    rows.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data=back_data)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def register(dp: Dispatcher) -> None:
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
