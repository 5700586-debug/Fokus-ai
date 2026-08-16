"""Fasl aniqlash — Saturn tonggi/tungi rasm fonini tanlash uchun.

Bitta markazlashgan funksiya: Asia/Tashkent (``company_time``) mahalliy
sanasiga qarab fasl qaytaradi. Yil raqamidan mustaqil — faqat oy
muhim, shuning uchun yangi yil chegarasida (dekabr -> yanvar) ham,
kabisa yilida (29-fevral) ham bir xil ishlaydi.
"""

from datetime import date

import company_time

SPRING = "bahor"
SUMMER = "yoz"
AUTUMN = "kuz"
WINTER = "qish"

_MONTH_TO_SEASON: dict[int, str] = {
    3: SPRING, 4: SPRING, 5: SPRING,
    6: SUMMER, 7: SUMMER, 8: SUMMER,
    9: AUTUMN, 10: AUTUMN, 11: AUTUMN,
    12: WINTER, 1: WINTER, 2: WINTER,
}


def season_for_date(local_date: date) -> str:
    return _MONTH_TO_SEASON[local_date.month]


def current_season() -> str:
    return season_for_date(company_time.today())
