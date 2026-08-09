"""Ob-havo ma'lumoti uchun abstraksiya.

Real weather API hali ulanmagan. ``NullWeatherProvider`` HECH QACHON
soxta/random ob-havo yaratmaydi — faqat "ma'lumot yo'q" holatini
qaytaradi. Chaqiruvchi kod (masalan ertalabki guruh xabari) shu holatni
ko'rib, ob-havo qismini xabardan butunlay tashlab yuborishi kerak.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass
class WeatherInfo:
    description: str
    temperature_c: float


class WeatherProvider(Protocol):
    async def get_today_weather(self, location: str) -> WeatherInfo | None:
        """Ma'lumot mavjud bo'lmasa ``None`` qaytaradi — hech qachon
        taxminiy/soxta qiymat emas."""
        ...

    def is_enabled(self) -> bool: ...


class NullWeatherProvider:
    async def get_today_weather(self, location: str) -> WeatherInfo | None:
        return None

    def is_enabled(self) -> bool:
        return False


def get_weather_provider() -> WeatherProvider:
    return NullWeatherProvider()
