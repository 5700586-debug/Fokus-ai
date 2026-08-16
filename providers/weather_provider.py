"""Ob-havo ma'lumoti uchun abstraksiya.

``NullWeatherProvider`` HECH QACHON soxta/random ob-havo yaratmaydi —
faqat "ma'lumot yo'q" holatini qaytaradi. Chaqiruvchi kod (masalan
ertalabki guruh xabari) shu holatni ko'rib, ob-havo qismini xabardan
butunlay tashlab yuborishi kerak.

``OpenMeteoWeatherProvider`` — Open-Meteo (https://open-meteo.com)
orqali haqiqiy ob-havo, ``config.WEATHER_PROVIDER_ENABLED=true``
bo'lganda ishlatiladi (qarang ``get_weather_provider()``). Open-Meteo
BEPUL va KALITSIZ — hech qanday maxfiy API kalit talab qilinmaydi.
So'rovga timeout qo'yilgan, tarmoq/JSON xatosi yoki timeout holatida
``None`` qaytadi (bot hech qachon shu sabab to'xtamaydi).
"""

import logging
from dataclasses import dataclass
from typing import Protocol

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT_SECONDS = 5.0

# WMO ob-havo kodlari (Open-Meteo ``weathercode``) — faqat eng ko'p
# uchraydigan holatlar uchun qisqa o'zbekcha tavsif. Ro'yxatda yo'q kod
# kelsa "Noma'lum" ko'rsatiladi (to'qib chiqarilmaydi).
_WEATHER_CODE_DESCRIPTIONS: dict[int, str] = {
    0: "Ochiq",
    1: "Deyarli ochiq",
    2: "Bulutli oraliq",
    3: "Bulutli",
    45: "Tuman",
    48: "Muzli tuman",
    51: "Mayda yomg'ir",
    53: "Yomg'ir",
    55: "Kuchli yomg'ir",
    56: "Muzli yomg'ir",
    57: "Muzli yomg'ir",
    61: "Yomg'ir",
    63: "Yomg'ir",
    65: "Kuchli yomg'ir",
    66: "Muzli yomg'ir",
    67: "Muzli yomg'ir",
    71: "Qor",
    73: "Qor",
    75: "Kuchli qor",
    77: "Qor donachalari",
    80: "Jala",
    81: "Jala",
    82: "Kuchli jala",
    85: "Qorli jala",
    86: "Qorli jala",
    95: "Momaqaldiroq",
    96: "Momaqaldiroq",
    99: "Momaqaldiroq",
}


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


class OpenMeteoWeatherProvider:
    """Kalitsiz, bepul Open-Meteo API — koordinata konstruktorda
    beriladi (shahar nomi emas, chunki API lat/lon so'raydi). ``location``
    argumenti faqat interfeys moslligi uchun qabul qilinadi, so'rovda
    ishlatilmaydi — chaqiruvchi kod shahar NOMINI ko'rsatish uchun
    alohida (masalan ``config.SATURN_WEATHER_CITY``) saqlaydi.
    """

    def __init__(self, latitude: float, longitude: float, timeout_seconds: float = _REQUEST_TIMEOUT_SECONDS):
        self._latitude = latitude
        self._longitude = longitude
        self._timeout_seconds = timeout_seconds

    def is_enabled(self) -> bool:
        return True

    async def get_today_weather(self, location: str) -> WeatherInfo | None:
        import aiohttp

        params = {
            "latitude": self._latitude,
            "longitude": self._longitude,
            "current_weather": "true",
        }
        timeout = aiohttp.ClientTimeout(total=self._timeout_seconds)

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    "https://api.open-meteo.com/v1/forecast", params=params
                ) as response:
                    if response.status != 200:
                        logger.warning("Open-Meteo HTTP %s", response.status)
                        return None
                    data = await response.json()
        except Exception as error:  # noqa: BLE001 - tarmoq/timeout/JSON xatosi bot'ni to'xtatmasin
            logger.warning("Open-Meteo so'rovida xato: %r", error)
            return None

        current = data.get("current_weather") if isinstance(data, dict) else None
        if not current or current.get("temperature") is None:
            return None

        weather_code = current.get("weathercode")
        description = (
            _WEATHER_CODE_DESCRIPTIONS.get(int(weather_code), "Noma'lum")
            if weather_code is not None
            else "Noma'lum"
        )
        return WeatherInfo(description=description, temperature_c=float(current["temperature"]))


def get_weather_provider() -> WeatherProvider:
    from config import SATURN_WEATHER_LAT, SATURN_WEATHER_LON, WEATHER_PROVIDER_ENABLED

    if not WEATHER_PROVIDER_ENABLED:
        return NullWeatherProvider()
    return OpenMeteoWeatherProvider(latitude=SATURN_WEATHER_LAT, longitude=SATURN_WEATHER_LON)
