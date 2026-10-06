"""Kassa dialogining eski vaqtinchalik xabarlarini yoshga qarab tozalash (har 30 daqiqada).

Faqat chatdagi track qilingan xabarlar (``cash_shift_close``, ``cash_close_review``) o'chiriladi.
``cash_shifts``, tasdiqlar, qoldiq summalar va pul tarixiga tegilmaydi. Moliyachi hali qaror
qilmagan (``needs_finance_review``) smenaning rasm xabarlari qoladi. Yakuniy xabarlar ("Smena
yopildi", "Moliyachi tasdiqladi/qaytardi") hech qachon track qilinmagan, shuning uchun tegilmaydi."""

import logging

from services import cash_shift, chat_cleanup

logger = logging.getLogger(__name__)

SWEPT_WORKFLOWS = ("cash_shift_close", "cash_close_review")
STALE_HOURS = 8
INTERVAL_MINUTES = 30


def _awaiting_finance_review(row: dict) -> bool:
    if row["workflow"] != "cash_close_review":
        return False
    try:
        shift = cash_shift.get_shift(int(row["workflow_key"]))
    except (TypeError, ValueError):
        return False
    return shift is not None and shift["status"] == cash_shift.STATUS_NEEDS_FINANCE_REVIEW


async def sweep(bot) -> int:
    return await chat_cleanup.sweep_stale(bot, SWEPT_WORKFLOWS, STALE_HOURS, keep=_awaiting_finance_review)


async def _tick(bot) -> None:
    try:
        await sweep(bot)
    except Exception as error:  # noqa: BLE001
        logger.error("Kassa chat tozalash tick xatosi: %r", error)


def start_scheduler(bot):
    """``main.py`` bot ishga tushganda chaqiradi (``discipline_bot.start_scheduler`` bilan bir xil uslub)."""
    import company_time
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    scheduler = AsyncIOScheduler(timezone=company_time.resolve_timezone())
    scheduler.add_job(_tick, "interval", minutes=INTERVAL_MINUTES, args=[bot], id="cash_chat_sweep")
    scheduler.start()
    return scheduler
