"""Saturn umumiy guruhidagi avtomatik postlar — scheduler va Founder-only
qo'lda sinov buyrug'i.

Guruh ID va yuborish vaqtlari kodga yozilmagan — ``/setrule`` orqali
sozlanadi (``services/rules.py``: ``saturn.group_chat_id``,
``saturn.morning_time``, ``saturn.dashboard_times``,
``saturn.evening_time``, ``saturn.tip_time``). ``saturn.group_chat_id``
o'rnatilmagan bo'lsa (standart holat), scheduler hech narsa yubormaydi —
bu xato emas, balki "hali sozlanmagan" holati.

Founder ID'ni qo'lda qidirmasin: ``/saturntest`` buyrug'i to'g'ridan-to'g'ri
Saturn guruhining o'zida yuborilsa, ``message.chat.id`` avtomatik
``saturn.group_chat_id`` sifatida saqlanadi (qarang ``saturn_test_handler``).

Bu modul ta'minotchi bilan HECH QACHON muzokara olib bormaydi —
``supplier_chat_bot.py``dan butunlay mustaqil, faqat guruhga bir
tomonlama ma'lumot yuboradi.
"""

import logging

from aiogram import Dispatcher
from aiogram.filters import Command
from aiogram.types import Message
from openai import AsyncOpenAI

import company_time
from config import FOUNDER_ID
from services import permissions
from services import rules as rules_service
from services import saturn_group

logger = logging.getLogger(__name__)

_TICK_MINUTES = 5


async def _tick(bot, openai_client: AsyncOpenAI) -> None:
    group_chat_id = rules_service.get_saturn_group_chat_id()
    if group_chat_id is None:
        return

    current_hm = company_time.now().strftime("%H:%M")

    try:
        # "Friendly phase": xodimlar guruhiga avtomatik boradigan tonggi/
        # tungi xabar — sodda, 30 kunlik tayyor kontent (qarang
        # ``services/daily_greetings.py`` va
        # ``services/saturn_group.send_daily_greeting_morning``/
        # ``send_daily_greeting_night``), AI/Pillow render yo'q. Eski
        # AI+ob-havo rasmli funksiyalar (``send_morning_image_message``/
        # ``send_night_image_message``) va matnli/moliyaviy
        # ``send_morning_message``/``send_evening_message`` BU YERDAN
        # HECH QACHON chaqirilmaydi — o'zlari olib tashlanmadi, faqat
        # ichki/``/saturntest`` sinov uchun qoldirildi.
        if current_hm >= rules_service.get_saturn_morning_time() and rules_service.get_saturn_morning_image_enabled():
            await saturn_group.send_daily_greeting_morning(bot, group_chat_id)

        if current_hm >= rules_service.get_saturn_evening_time() and rules_service.get_saturn_night_image_enabled():
            await saturn_group.send_daily_greeting_night(bot, group_chat_id)

        if current_hm >= rules_service.get_saturn_tip_time():
            await saturn_group.send_tip_message(bot, group_chat_id)

        for slot_time in rules_service.get_saturn_dashboard_times():
            if current_hm >= slot_time:
                await saturn_group.send_dashboard_message(bot, openai_client, group_chat_id, slot_time)
    except Exception as error:  # noqa: BLE001 - bitta post xatosi butun tickni to'xtatmasin
        logger.error("Saturn guruh postini yuborishda xato: %r", error)
        print(f"Saturn guruh postini yuborishda xato: {error!r}")


def register(dp: Dispatcher, openai_client: AsyncOpenAI) -> None:
    @dp.message(Command("saturntest"))
    async def saturn_test_handler(message: Message) -> None:
        if not await permissions.ensure_permission(message, permissions.ACTION_SATURN_TEST):
            return

        parts = (message.text or "").split(maxsplit=1)

        # Buyruq to'g'ridan-to'g'ri guruhning o'zida yuborilsa, Founder ID
        # qidirishga majbur bo'lmasin — shu guruhning chat_id'si avtomatik
        # ``saturn.group_chat_id`` sifatida saqlanadi (qo'lda /setrule shart
        # emas, lekin hali ham kodga hardcode qilinmaydi).
        captured_now = False
        if message.chat.type in ("group", "supergroup"):
            group_chat_id = message.chat.id
            if rules_service.get_saturn_group_chat_id() != group_chat_id:
                rules_service.set_rule(
                    "saturn.group_chat_id", str(group_chat_id), updated_by=FOUNDER_ID
                )
                captured_now = True
        else:
            group_chat_id = rules_service.get_saturn_group_chat_id()
            if group_chat_id is None:
                await message.answer(
                    "❌ Guruh ID hali sozlanmagan. Bu buyruqni Saturn guruhining "
                    "o'zida yuboring — guruh ID avtomatik saqlanadi. Yoki: "
                    "/setrule saturn.group_chat_id <guruh_chat_id>"
                )
                return

        post_type = parts[1].strip() if len(parts) > 1 else ""
        if post_type not in ("morning", "night", "dashboard", "evening", "tip"):
            captured_line = (
                f"✅ Guruh ID saqlandi: {group_chat_id}\n" if captured_now else ""
            )
            await message.answer(
                f"{captured_line}"
                "Foydalanish: /saturntest <morning|night|dashboard|tip>\n"
                "morning/night (evening — night bilan bir xil) — yangi rasmli, "
                "moliyasiz xabarning ONAYZI — SIZNING shaxsiy chatingizga "
                "yuboriladi, xodimlar guruhiga EMAS va kunlik production "
                "yozuvini band qilmaydi (istagancha qayta sinash mumkin).\n"
                f"Joriy guruh ID: {group_chat_id}"
            )
            return

        # morning/night(evening) — SINOV: natija xodimlar guruhiga emas,
        # buyruq bergan administratorning shaxsiy chatiga yuboriladi va
        # kunlik "yuborildi" yozuvini (idempotency/rotation) band
        # qilmaydi — shuning uchun haqiqiy 08:00/21:00 xabari to'xtab
        # qolmaydi va admin istagancha qayta sinashi mumkin (qarang
        # ``services/saturn_group.send_morning_image_preview``/
        # ``send_night_image_preview``).
        admin_chat_id = message.from_user.id

        if post_type == "morning":
            await saturn_group.send_morning_image_preview(message.bot, openai_client, admin_chat_id)
        elif post_type in ("night", "evening"):
            await saturn_group.send_night_image_preview(message.bot, openai_client, admin_chat_id)
        elif post_type == "tip":
            await saturn_group.send_tip_message(message.bot, group_chat_id)
        else:
            await saturn_group.send_dashboard_message(
                message.bot, openai_client, group_chat_id, "manual"
            )

        captured_line = f"✅ Guruh ID saqlandi: {group_chat_id}\n" if captured_now else ""
        if post_type in ("morning", "night", "evening"):
            await message.answer(f"{captured_line}✅ Sinov posti sizning shaxsiy chatingizga yuborildi.")
        else:
            await message.answer(
                f"{captured_line}✅ '{post_type}' posti guruhga (ID: {group_chat_id}) yuborildi."
            )


def start_scheduler(bot, openai_client: AsyncOpenAI):
    """``main.py`` bot ishga tushganda chaqiradi — mavjud
    ``calibration_bot.start_scheduler``/``discipline_bot.start_scheduler``
    bilan bir xil uslub (mustaqil scheduler, kompaniya vaqt zonasida,
    har ``_TICK_MINUTES`` daqiqada tekshiradi, yuborish ``notifications.send_once``
    orqali idempotent)."""
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    scheduler = AsyncIOScheduler(timezone=company_time.resolve_timezone())
    scheduler.add_job(
        _tick, "interval", minutes=_TICK_MINUTES, args=[bot, openai_client], id="saturn_group_posts"
    )
    scheduler.start()
    return scheduler
