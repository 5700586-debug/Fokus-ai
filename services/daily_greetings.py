"""Xayrli tong/tun — sodda, 30 kunlik tayyor kontent (AI yo'q, Pillow
render yo'q). Matnlar ``content/daily_greetings/morning_messages.py`` va
``night_messages.py``da. Rasmlar HAR KUNGA ALOHIDA — ``morning_01.jpg``
... ``morning_30.jpg`` va ``night_01.jpg`` ... ``night_30.jpg`` (Founder
tomonidan shu aniq nomlar bilan ``content/daily_greetings/``ga
qo'yiladi). Muayyan kunning rasmi hali qo'yilmagan bo'lsa, tizim
buzilmaydi — o'sha kuni faqat matn yuboriladi.

Kun raqami taqvim sanasidan hisoblanadi (``_START_DATE``dan necha kun
o'tgani). 30-kundan keyin ATAYLAB hech narsa qaytarilmaydi — chaqiruvchi
kod shu holatda xabar yubormaydi (avtomatik boshidan takrorlanmaydi).
"""

from datetime import date
from pathlib import Path

import company_time
from content.daily_greetings.morning_messages import MORNING_MESSAGES
from content.daily_greetings.night_messages import NIGHT_MESSAGES

_START_DATE = date(2026, 8, 20)
_CONTENT_DIR = Path(__file__).resolve().parent.parent / "content" / "daily_greetings"


def _day_index(today: date | None = None) -> int:
    today = today or company_time.today()
    return (today - _START_DATE).days + 1


def get_morning_message(today: date | None = None) -> str | None:
    idx = _day_index(today)
    if idx < 1 or idx > len(MORNING_MESSAGES):
        return None
    return MORNING_MESSAGES[idx - 1]


def get_night_message(today: date | None = None) -> str | None:
    idx = _day_index(today)
    if idx < 1 or idx > len(NIGHT_MESSAGES):
        return None
    return NIGHT_MESSAGES[idx - 1]


def get_morning_image_path(today: date | None = None) -> Path | None:
    idx = _day_index(today)
    if idx < 1 or idx > len(MORNING_MESSAGES):
        return None
    path = _CONTENT_DIR / f"morning_{idx:02d}.jpg"
    return path if path.is_file() else None


def get_night_image_path(today: date | None = None) -> Path | None:
    idx = _day_index(today)
    if idx < 1 or idx > len(NIGHT_MESSAGES):
        return None
    path = _CONTENT_DIR / f"night_{idx:02d}.jpg"
    return path if path.is_file() else None
