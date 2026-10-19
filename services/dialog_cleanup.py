"""Minus va e'tiroz dialogidagi ishchi xabarlarni tozalash — mavjud ``chat_cleanup`` kuzatuvi
(``bot_workflow_messages``) ustida yupqa qatlam. Qoida: avval yangi ekran muvaffaqiyatli ko'rsatiladi, KEYIN
shu dialogga tegishli, ID'si qayd etilgan eski xabarlar o'chiriladi (``keep`` — qoladigan joriy xabar).

Faqat aynan shu chat + shu dialog kalitidagi xabarlar o'chiriladi. O'chirish/tahrirlash xatosi hech qachon
asosiy oqimni to'xtatmaydi. Bazadagi minus/balans/ledger/apellyatsiya yozuvlariga tegilmaydi."""

import logging

from aiogram import Bot
from aiogram.types import Message

from repositories import bot_messages as repo
from services import chat_cleanup

logger = logging.getLogger(__name__)

WORKFLOW = "discipline_dialog"


def minus_key(chat_id: int, dialog_id: str) -> str:
    return f"minus:{chat_id}:{dialog_id}"


def appeal_key(chat_id: int, penalty_id: int) -> str:
    return f"appeal:{chat_id}:{penalty_id}"


def track(key: str, message: Message | None) -> None:
    chat_cleanup.track(WORKFLOW, key, message)


async def sweep(bot: Bot, key: str, keep: tuple[int, int] | None = None) -> None:
    """Kalitdagi barcha kuzatilgan xabarlarni jurnaldan oladi va ``keep``dan tashqarilarini o'chiradi."""
    try:
        rows = repo.pop_messages(WORKFLOW, key)
    except Exception as error:  # noqa: BLE001
        logger.error("Dialog xabarlari ro'yxatini olib bo'lmadi (key=%s): %r", key, error)
        return
    for row in rows:
        if keep is not None and (row["chat_id"], row["message_id"]) == keep:
            continue
        try:
            await bot.delete_message(row["chat_id"], row["message_id"])
        except Exception as error:  # noqa: BLE001
            logger.warning("Eski dialog xabarini o'chirib bo'lmadi (%s/%s): %r", row["chat_id"], row["message_id"], error)
