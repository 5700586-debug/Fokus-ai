"""Nazoratchi kunlik nazorat oqimi: filial -> aktiv xodimlar -> xodim
kartasi. Bosqichlab quriladi (qarang loyihaning "VAZIFA + NAZORATCHI +
BONUS" vazifasi) — bu fayl har bosqichda kengaytiriladi, hozircha
faqat 1-bosqich (filial/xodim ko'rish).

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

import employees
from config import RECRUITING_BRANCH_NAMES
from roles import role_name
from services import permissions

_CB_BRANCHES = "nzr_branches"
_CB_BRANCH_PREFIX = "nzr_branch:"
_CB_EMPLOYEE_PREFIX = "nzr_emp:"


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
    return "\n".join(lines)


def _employee_card_keyboard(branch: str | None) -> InlineKeyboardMarkup:
    back_data = _CB_BRANCHES
    if branch is not None:
        index = _branch_index(branch)
        if index is not None:
            back_data = f"{_CB_BRANCH_PREFIX}{index}"
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Orqaga", callback_data=back_data)]])


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
                reply_markup=_employee_card_keyboard(profile.get("branch")),
            )
        await callback.answer()
