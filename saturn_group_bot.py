"""Saturn umumiy guruhidagi avtomatik postlar — scheduler va Founder-only
qo'lda sinov buyrug'i.

Guruh ID va yuborish vaqtlari kodga yozilmagan — ``/setrule`` orqali
sozlanadi (``services/rules.py``: ``saturn.group_chat_id``,
``saturn.morning_time``, ``saturn.dashboard_times``,
``saturn.evening_time``, ``saturn.tip_time``). ``saturn.group_chat_id``
o'rnatilmagan bo'lsa (standart holat), scheduler hech narsa yubormaydi —
bu xato emas, balki "hali sozlanmagan" holati.

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
        if current_hm >= rules_service.get_saturn_morning_time():
            await saturn_group.send_morning_message(bot, openai_client, group_chat_id)

        if current_hm >= rules_service.get_saturn_evening_time():
            await saturn_group.send_evening_message(bot, openai_client, group_chat_id)

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
        if not message.from_user or message.from_user.id != FOUNDER_ID:
            return

        parts = (message.text or "").split(maxsplit=1)
        group_chat_id = rules_service.get_saturn_group_chat_id()
        if group_chat_id is None:
            await message.answer(
                "❌ Guruh ID hali sozlanmagan. Avval: "
                "/setrule saturn.group_chat_id <guruh_chat_id>"
            )
            return

        post_type = parts[1].strip() if len(parts) > 1 else ""
        if post_type not in ("morning", "dashboard", "evening", "tip"):
            await message.answer(
                "Foydalanish: /saturntest <morning|dashboard|evening|tip>\n"
                f"Joriy guruh ID: {group_chat_id}"
            )
            return

        if post_type == "morning":
            await saturn_group.send_morning_message(message.bot, openai_client, group_chat_id)
        elif post_type == "evening":
            await saturn_group.send_evening_message(message.bot, openai_client, group_chat_id)
        elif post_type == "tip":
            await saturn_group.send_tip_message(message.bot, group_chat_id)
        else:
            await saturn_group.send_dashboard_message(
                message.bot, openai_client, group_chat_id, "manual"
            )

        await message.answer(f"✅ '{post_type}' posti guruhga (ID: {group_chat_id}) yuborildi.")


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
