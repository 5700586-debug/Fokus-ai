"""Kompaniya vaqt zonasiga bog'liq umumiy yordamchi funksiyalar.

Render kabi hostlar odatda UTC bo'yicha ishlaydi, lekin kunlik chegaralar
(smena, ombor hisobot-kunlari, baholash) COMPANY_TIMEZONE (odatda
Asia/Tashkent, UTC+5) bo'yicha hisoblanishi kerak — aks holda kechqurun
19:00-23:59 UTC oralig'ida (Toshkentda allaqachon 00:00-04:59, ya'ni yangi
kun) yozilgan ma'lumotlar noto'g'ri (kechagi) sanaga tushib qoladi.

``ZoneInfo`` IANA tzdata bazasiga muhtoj — ba'zi minimal Docker
imidjlarida (masalan Render'ning ba'zi Python bazaviy imidjlari) ``tzdata``
paketi yo'q bo'lsa ``ZoneInfoNotFoundError`` ko'taradi. Bu botning butun
ishga tushishini yiqitmasligi kerak — xato bo'lsa UTC'ga (hech qanday
tzdata'ga muhtoj bo'lmagan sof stdlib) qaytiladi va log qilinadi.
"""

import logging
from datetime import date, datetime
from datetime import timezone as dt_timezone
from zoneinfo import ZoneInfo

from config import COMPANY_TIMEZONE

logger = logging.getLogger(__name__)


def resolve_timezone():
    try:
        return ZoneInfo(COMPANY_TIMEZONE)
    except Exception as error:
        message = f"COMPANY_TIMEZONE ({COMPANY_TIMEZONE!r}) yuklanmadi, UTC'ga qaytildi: {error!r}"
        logger.error(message)
        print(message)
        return dt_timezone.utc


def now() -> datetime:
    return datetime.now(resolve_timezone())


def today() -> date:
    return now().date()
