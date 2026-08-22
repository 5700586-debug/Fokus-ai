"""Founder tomonidan yakunlangan onboarding anketalarini ko'rib chiqish.

Xodim anketani tasdiqlagandan so'ng shu yerda tuzilgan karta Founderga
yuboriladi. Faqat Founder "✅ Tasdiqlash"ni bosgandan keyin foydalanuvchi
allowed users ro'yxatiga (roles.py) qo'shiladi va ichki menyu ochiladi.
"""

from aiogram import Bot, Dispatcher, F
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

import calibration_bot
import employees
import roles
from config import FOUNDER_ID
from services import permissions


def _review_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"approve:{user_id}"),
                InlineKeyboardButton(text="❌ Rad etish", callback_data=f"reject:{user_id}"),
            ],
            [InlineKeyboardButton(text="👤 Batafsil", callback_data=f"detail:{user_id}")],
        ]
    )


async def send_for_review(bot: Bot, user_id: int) -> None:
    card = employees.format_founder_card(user_id)
    if card is None:
        return

    profile = employees.get_profile(user_id)
    photo_file_id = profile.get("photo_file_id") if profile else None

    if photo_file_id:
        await bot.send_photo(
            FOUNDER_ID,
            photo=photo_file_id,
            caption=card,
            reply_markup=_review_keyboard(user_id),
        )
    else:
        await bot.send_message(FOUNDER_ID, card, reply_markup=_review_keyboard(user_id))


def register(dp: Dispatcher) -> None:
    @dp.callback_query(F.data.startswith("approve:"))
    async def handle_approve(callback: CallbackQuery) -> None:
        if not await permissions.ensure_permission(callback, permissions.ACTION_APPROVE_APPLICANT):
            return

        user_id = int(callback.data.split(":", 1)[1])
        profile = employees.get_profile(user_id)
        if profile is None or profile["status"] != "submitted":
            await callback.answer("Profil topilmadi yoki allaqachon ko'rib chiqilgan.", show_alert=True)
            return

        role_key = profile["role_key"]
        if roles.is_single_slot_role(role_key):
            existing = roles.find_user_by_role(role_key)
            if existing is not None and existing != user_id:
                await callback.answer(
                    f"❌ {roles.role_name(role_key)} lavozimida allaqachon boshqa xodim bor "
                    f"(user_id: {existing}). Avval uni bo'shating.",
                    show_alert=True,
                )
                return

        employees.approve_profile(user_id, approved_by=FOUNDER_ID)
        roles.set_role(user_id, role_key, set_by=FOUNDER_ID)

        try:
            calibration_bot.on_employee_approved(user_id, role_key)
        except Exception as error:
            # Kalibratsiya sessiyasi yaratilmasa ham, asosiy approval oqimi
            # (xodimga va Founderga tasdiqlash) hech qachon shu tufayli
            # to'xtab qolmasligi kerak.
            print(f"Kalibratsiya sessiyasini yaratishda xato (user_id={user_id}): {error!r}")

        if callback.message:
            await callback.message.edit_reply_markup(reply_markup=None)

        import main  # funksiya ichida — main approval'ni import qilgani uchun (aylanma import)

        await callback.bot.send_message(
            user_id,
            f"✅ Profilingiz tasdiqlandi!\n\n{main.greeting_for_user(user_id)}",
            reply_markup=main.build_menu(user_id),
        )
        await callback.answer("Tasdiqlandi ✅")

    @dp.callback_query(F.data.startswith("reject:"))
    async def handle_reject(callback: CallbackQuery) -> None:
        if not await permissions.ensure_permission(callback, permissions.ACTION_APPROVE_APPLICANT):
            return

        user_id = int(callback.data.split(":", 1)[1])
        employees.reject_profile(user_id, rejected_by=FOUNDER_ID)

        if callback.message:
            await callback.message.edit_reply_markup(reply_markup=None)

        await callback.bot.send_message(user_id, "❌ Afsuski, arizangiz hozircha rad etildi.")
        await callback.answer("Rad etildi ❌")

    @dp.callback_query(F.data.startswith("detail:"))
    async def handle_detail(callback: CallbackQuery) -> None:
        if not await permissions.ensure_permission(callback, permissions.ACTION_APPROVE_APPLICANT):
            return

        user_id = int(callback.data.split(":", 1)[1])
        profile = employees.get_profile(user_id)
        if profile is None or callback.message is None:
            await callback.answer("Profil topilmadi.", show_alert=True)
            return

        details = (
            f"💬 To'liq motivatsiya:\n{profile.get('motivation') or '-'}\n\n"
            f"📋 To'liq oldingi tajriba:\n{profile.get('prior_experience') or '-'}"
        )
        await callback.message.answer(details)
        await callback.answer()
