"""Ob-havoni Saturn tonggi rasmidagi vizual "sahna"ga aylantirish.

Open-Meteo WMO ``weathercode``, harorat va shamol tezligini bitta
aniq vizual KATEGORIYAga tushiradi — ``services/saturn_scene.py`` shu
kategoriya bo'yicha tayyor fon kompozitsiyasini tanlaydi.

Muhim: oddiy shamolli kun uchun bo'ron/tornado tasviri ISHLATILMAYDI
(yolg'on xavf tuyg'usi yaratadi) — shamol faqat uchayotgan barglar,
harakatlanuvchi bulutlar va yengil egilgan daraxt bilan ko'rsatiladi
(qarang ``services/saturn_scene.py``dagi ``CATEGORY_WINDY`` sahnasi).

Ustuvorlik tartibi (yuqoridan pastga, birinchi mos kelgani tanlanadi):
momaqaldiroq -> qor -> kuchli yomg'ir -> yomg'ir/mayda yomg'ir -> tuman
-> kuchli shamol -> juda issiq -> ochiq/bulutli -> fasl standart foni.
"""

CATEGORY_THUNDERSTORM = "thunderstorm"
CATEGORY_SNOW = "snow"
CATEGORY_HEAVY_RAIN = "heavy_rain"
CATEGORY_RAIN = "rain"
CATEGORY_DRIZZLE = "drizzle"
CATEGORY_FOG = "fog"
CATEGORY_WINDY = "windy"
CATEGORY_HOT = "hot"
CATEGORY_CLEAR = "clear"
CATEGORY_CLOUDY = "cloudy"
CATEGORY_SEASON_DEFAULT = "season_default"

# Ustuvorlik tartibida — shu ro'yxat tekshirish ketma-ketligini ham
# belgilaydi (testlarda ishlatiladi).
PRIORITY_ORDER: tuple[str, ...] = (
    CATEGORY_THUNDERSTORM,
    CATEGORY_SNOW,
    CATEGORY_HEAVY_RAIN,
    CATEGORY_RAIN,
    CATEGORY_DRIZZLE,
    CATEGORY_FOG,
    CATEGORY_WINDY,
    CATEGORY_HOT,
    CATEGORY_CLEAR,
    CATEGORY_CLOUDY,
    CATEGORY_SEASON_DEFAULT,
)

# WMO weathercode -> kategoriya guruhlari (providers/weather_provider.py
# dagi _WEATHER_CODE_DESCRIPTIONS bilan bir xil kod manbasidan).
_THUNDERSTORM_CODES = {95, 96, 99}
_SNOW_CODES = {71, 73, 75, 77, 85, 86}
_HEAVY_RAIN_CODES = {65, 82}
_RAIN_CODES = {61, 63, 66, 67, 80, 81}
_DRIZZLE_CODES = {51, 53, 55, 56, 57}
_FOG_CODES = {45, 48}
_CLEAR_CODES = {0, 1}
_CLOUDY_CODES = {2, 3}


def weather_category(
    weather_code: int | None,
    temperature_c: float | None,
    wind_speed_kmh: float | None,
    wind_threshold_kmh: float,
    hot_threshold_c: float,
) -> str:
    """Xom ob-havo qiymatlarini bitta vizual kategoriyaga tushiradi.

    Har qanday qiymat ``None`` bo'lishi mumkin (masalan ob-havo API
    ishlamay qolganda) — bu holatda funksiya hech qachon xato
    bermaydi, oxir-oqibat ``CATEGORY_SEASON_DEFAULT`` qaytaradi.
    """
    if weather_code in _THUNDERSTORM_CODES:
        return CATEGORY_THUNDERSTORM
    if weather_code in _SNOW_CODES:
        return CATEGORY_SNOW
    if weather_code in _HEAVY_RAIN_CODES:
        return CATEGORY_HEAVY_RAIN
    if weather_code in _RAIN_CODES:
        return CATEGORY_RAIN
    if weather_code in _DRIZZLE_CODES:
        return CATEGORY_DRIZZLE
    if weather_code in _FOG_CODES:
        return CATEGORY_FOG
    if wind_speed_kmh is not None and wind_speed_kmh >= wind_threshold_kmh:
        return CATEGORY_WINDY
    if temperature_c is not None and temperature_c >= hot_threshold_c:
        return CATEGORY_HOT
    if weather_code in _CLEAR_CODES:
        return CATEGORY_CLEAR
    if weather_code in _CLOUDY_CODES:
        return CATEGORY_CLOUDY
    return CATEGORY_SEASON_DEFAULT


def category_for_weather_info(weather, wind_threshold_kmh: float, hot_threshold_c: float) -> str:
    """``providers.weather_provider.WeatherInfo | None`` qabul qiladi —
    ``None`` bo'lsa (ob-havo mavjud emas) darhol fasl-standart
    kategoriyasini qaytaradi."""
    if weather is None:
        return CATEGORY_SEASON_DEFAULT
    return weather_category(
        weather_code=weather.weather_code,
        temperature_c=weather.temperature_c,
        wind_speed_kmh=weather.wind_speed_kmh,
        wind_threshold_kmh=wind_threshold_kmh,
        hot_threshold_c=hot_threshold_c,
    )
