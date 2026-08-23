"""FOKUS AI ish oqimi (masalan smena ochish/yopish) davomida yuborilgan
vaqtinchalik bot xabarlarini kuzatish va oqim yakunlangach xavfsiz
o'chirish — xodim har yangi ish kunida eski bot yozishmalari bilan
to'lib qolmasin. DB'dagi biznes ma'lumotga (smena, tafovut, xarajat,
kim/qachon tasdiqlagani va h.k.) umuman tegmaydi — faqat Telegram
chatidagi vaqtinchalik dialog xabarlarini tozalaydi.

``track()`` ataylab HECH QACHON exception ko'tarmaydi — kuzatuv
yozuvi muvaffaqiyatsiz bo'lsa ham, asosiy smena/kassa oqimi
to'xtamasligi kerak (bu faqat yordamchi UX tozaligi, biznes mantiq
emas).
"""

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message

from repositories import bot_messages as repo

logger = logging.getLogger(__name__)


def track(workflow: str, workflow_key: str, message: Message | None) -> None:
    if message is None:
        return
    try:
        repo.log_message(workflow, workflow_key, message.chat.id, message.message_id)
    except Exception as error:  # noqa: BLE001
        logger.error(
            "Chat-tozalash uchun xabarni kuzatib bo'lmadi (workflow=%s, key=%s): %r",
            workflow, workflow_key, error,
        )


async def cleanup(bot: Bot, workflow: str, workflow_key: str) -> None:
    """Shu workflow/kalitga tegishli barcha kuzatilgan bot xabarlarini
    o'chiradi. O'chirib bo'lmagan xabar (masalan Telegram'ning 48 soatlik
    cheklovi tufayli) oqimni to'xtatmaydi — jim o'tkazib yuboriladi.
    """
    try:
        rows = repo.pop_messages(workflow, workflow_key)
    except Exception as error:  # noqa: BLE001
        logger.error(
            "Chat-tozalash uchun kuzatilgan xabarlar ro'yxatini olib bo'lmadi "
            "(workflow=%s, key=%s): %r", workflow, workflow_key, error,
        )
        return

    for row in rows:
        try:
            await bot.delete_message(row["chat_id"], row["message_id"])
        except TelegramBadRequest:
            pass
        except Exception as error:  # noqa: BLE001
            logger.error(
                "Eski bot xabarini o'chirib bo'lmadi (chat_id=%s, message_id=%s): %r",
                row["chat_id"], row["message_id"], error,
            )
