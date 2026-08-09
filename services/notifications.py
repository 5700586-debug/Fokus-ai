"""Idempotent xabar yuborish — bitta scheduled xabar ikki marta
yuborilib ketmasligi uchun (dedupe key: ``job_key`` + ``target``).

Bugun hech qanday scheduler bu funksiyani chaqirmaydi — bu faqat
kelajakdagi kunlik/oylik job'lar uchun tayyor infratuzilma.
"""

from typing import Any

from aiogram import Bot

from repositories import notifications as notifications_repo


async def send_once(bot: Bot, job_key: str, target: int | str, text: str, **send_kwargs: Any) -> bool:
    """Agar ``job_key``+``target`` uchun xabar allaqachon yuborilgan
    bo'lsa, hech narsa qilmay ``False`` qaytaradi. Yuborish xato bilan
    tugasa, "yuborilgan" deb belgilanmaydi — keyingi urinishda qayta
    yuborish mumkin bo'lib qoladi.
    """
    if notifications_repo.was_sent(job_key, str(target)):
        return False

    await bot.send_message(target, text, **send_kwargs)
    notifications_repo.try_mark_sent(job_key, str(target))
    return True
