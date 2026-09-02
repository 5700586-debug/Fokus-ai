"""Founder tomonidan yakunlangan onboarding anketalarini ko'rib chiqish.

Xodim anketani tasdiqlagandan so'ng shu yerda tuzilgan karta Founderga
yuboriladi. Faqat Founder "✅ Tasdiqlash"ni bosgandan keyin foydalanuvchi
allowed users ro'yxatiga (roles.py) qo'shiladi va ichki menyu ochiladi.
"""

from aiogram import Bot, Dispatcher, F
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

import calibration_bot
import discipline_bot
import employees
import roles
from config import FOUNDER_ID
from services import permissions
from services import rule_learning


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

        approved_profile = employees.approve_profile(user_id, approved_by=FOUNDER_ID)
        if approved_profile is None:
            # Boshqa so'rov (masalan ikki marta bosilgan tugma yoki
            # parallel ikkinchi chaqiruv) shu nomzodni allaqachon ko'rib
            # chiqib ulgurgan — rol qayta berilmasin, kalibratsiya qayta
            # ishga tushmasin, xabar qayta yuborilmasin (qarang
            # ``employees.approve_profile``).
            if callback.message:
                await callback.message.edit_reply_markup(reply_markup=None)
            await callback.answer("Bu profil allaqachon ko'rib chiqilgan.", show_alert=True)
            return

        try:
            # Nizom auditiga yozib qo'yish rol muvaffaqiyatli
            # berilishidan MUSTAQIL — rol keyinroq (masalan /setrole
            # orqali) berilsa ham, enrollment allaqachon tayyor turadi
            # va shu yerdan davom etadi (idempotent, qarang
            # ``rule_learning.enroll``).
            rule_learning.enroll(user_id)
        except Exception as error:
            print(f"Nizom auditiga yozishda xato (user_id={user_id}): {error!r}")

        role_assigned = roles.set_role(user_id, role_key, set_by=FOUNDER_ID)
        if not role_assigned:
            # DB darajasidagi race (masalan single-slot rolga deyarli bir
            # vaqtdagi ikkinchi urinish) — ilova darajasidagi tekshiruv
            # (62-70 qatorlar) buni ko'ra olmagan bo'lishi mumkin, DB
            # darajasidagi qisman UNIQUE indeks rad etgan (qarang
            # ``roles.set_role``). Xodim "approved" holatida qoladi, lekin
            # rolisiz ishlay olmaydi — shuning uchun muvaffaqiyat xabari/
            # menyu YUBORILMAYDI, Founder holatni ko'rib qo'lda hal qilishi
            # kerak (masalan /setrole orqali).
            if callback.message:
                await callback.message.edit_reply_markup(reply_markup=None)
            await callback.answer(
                f"⚠️ Profil tasdiqlandi, lekin {roles.role_name(role_key)} lavozimi band bo'lib qoldi "
                f"(parallel urinish). /setrole {user_id} orqali qo'lda rol bering.",
                show_alert=True,
            )
            return

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

        try:
            await discipline_bot.start_or_resume_rule_learning(callback.bot, user_id)
        except Exception as error:
            print(f"Nizom o'qishni boshlashda xato (user_id={user_id}): {error!r}")

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
