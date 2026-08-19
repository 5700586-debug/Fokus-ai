"""Xayrli tong/tun — sodda, 30 kunlik tayyor kontent (AI yo'q, Pillow
render yo'q). Matnlar ``content/daily_greetings/morning_messages.py`` va
``night_messages.py``da, rasmlar (bo'lsa) ``morning.jpg``/``night.jpg``da.

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
MORNING_IMAGE_PATH = _CONTENT_DIR / "morning.jpg"
NIGHT_IMAGE_PATH = _CONTENT_DIR / "night.jpg"


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


def get_morning_image_path() -> Path | None:
    return MORNING_IMAGE_PATH if MORNING_IMAGE_PATH.is_file() else None


def get_night_image_path() -> Path | None:
    return NIGHT_IMAGE_PATH if NIGHT_IMAGE_PATH.is_file() else None
