"""Idempotent xabar yuborish — bitta scheduled xabar ikki marta
yuborilib ketmasligi uchun (dedupe key: ``job_key`` + ``target``,
``notification_log``dagi ``UNIQUE(job_key, target)`` orqali).
``saturn_group.py``dagi kunlik postlar (tonggi/tungi/tip/dashboard)
shu modul orqali ishlaydi.
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


async def try_reserve(job_key: str, target: int | str) -> bool:
    """``job_key``+``target``ni ATOMIK ravishda ``pending`` holatida
    band qiladi — ``True`` qaytarsa, ANIQ shu chaqiruv yuborish
    huquqini yutdi (boshqa parallel chaqiruv/worker ``False`` oladi).

    ``send_once()``dan farqli — bu "avval band qil, keyin qimmat ishni
    (AI, tashqi API, rasm generatsiyasi) bajar" naqshi uchun: ``was_sent``
    tekshiruvi bilan haqiqiy yuborish orasida bir nechta ``await`` nuqtasi
    bo'lsa (masalan rasm tayyorlashda), ikkita parallel chaqiruv ikkalasi
    ham tekshiruvdan "toza" o'tib, ikkalasi ham yuborib yuborishi mumkin
    edi — ATOMIK ``INSERT OR IGNORE`` reservatsiya buni yopadi. Muvaffaqiyatli
    reservatsiyadan keyin ``mark_sent()`` (yuborilgach) yoki
    ``release_reservation()`` (xato bo'lsa, qayta urinish uchun) chaqirilishi
    SHART.
    """
    return notifications_repo.try_reserve(job_key, str(target))


def mark_sent(job_key: str, target: int | str) -> None:
    notifications_repo.mark_status(job_key, str(target), "sent")


def release_reservation(job_key: str, target: int | str) -> None:
    """Yuborish xato bilan tugasa chaqiriladi — ``pending`` band bekor
    qilinadi, shuning uchun keyingi urinish (masalan keyingi scheduler
    tick'i) qayta yuborishga harakat qila oladi (butunlay yopilib
    qolmaydi)."""
    notifications_repo.release_reservation(job_key, str(target))
