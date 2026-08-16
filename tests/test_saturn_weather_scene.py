from providers.weather_provider import WeatherInfo
from services import saturn_weather_scene as scene

_WIND = 30.0
_HOT = 33.0


def _cat(code=None, temp=None, wind=None):
    return scene.weather_category(code, temp, wind, wind_threshold_kmh=_WIND, hot_threshold_c=_HOT)


def test_thunderstorm_codes_map_to_thunderstorm():
    for code in (95, 96, 99):
        assert _cat(code=code, temp=20, wind=5) == scene.CATEGORY_THUNDERSTORM


def test_snow_codes_map_to_snow():
    for code in (71, 73, 75, 77, 85, 86):
        assert _cat(code=code, temp=-2, wind=5) == scene.CATEGORY_SNOW


def test_heavy_rain_codes_map_to_heavy_rain():
    for code in (65, 82):
        assert _cat(code=code, temp=15, wind=5) == scene.CATEGORY_HEAVY_RAIN


def test_rain_codes_map_to_rain():
    for code in (61, 63, 66, 67, 80, 81):
        assert _cat(code=code, temp=15, wind=5) == scene.CATEGORY_RAIN


def test_drizzle_codes_map_to_drizzle():
    for code in (51, 53, 55, 56, 57):
        assert _cat(code=code, temp=15, wind=5) == scene.CATEGORY_DRIZZLE


def test_fog_codes_map_to_fog():
    for code in (45, 48):
        assert _cat(code=code, temp=10, wind=5) == scene.CATEGORY_FOG


def test_clear_codes_map_to_clear():
    for code in (0, 1):
        assert _cat(code=code, temp=15, wind=5) == scene.CATEGORY_CLEAR


def test_cloudy_codes_map_to_cloudy():
    for code in (2, 3):
        assert _cat(code=code, temp=15, wind=5) == scene.CATEGORY_CLOUDY


def test_strong_wind_with_clear_code_maps_to_windy_not_storm():
    """Oddiy shamolli, boshqa aniq hodisa bo'lmagan kunda bo'ron/tornado
    emas, faqat 'windy' kategoriyasi tanlanadi — yolg'on xavf yaratmaslik
    talabi."""
    result = _cat(code=1, temp=20, wind=45)
    assert result == scene.CATEGORY_WINDY
    assert "storm" not in result
    assert "tornado" not in result


def test_hot_takes_priority_over_clear():
    result = _cat(code=0, temp=38, wind=5)
    assert result == scene.CATEGORY_HOT


def test_priority_thunderstorm_beats_everything_else():
    # Momaqaldiroq kodi bilan birga issiq harorat va kuchli shamol ham
    # bo'lsa ham, ustuvorlik tartibi bo'yicha momaqaldiroq g'alaba qiladi.
    result = _cat(code=95, temp=38, wind=45)
    assert result == scene.CATEGORY_THUNDERSTORM


def test_priority_snow_beats_rain_and_wind():
    result = _cat(code=71, temp=-1, wind=45)
    assert result == scene.CATEGORY_SNOW


def test_priority_rain_beats_wind_and_hot():
    result = _cat(code=61, temp=35, wind=45)
    assert result == scene.CATEGORY_RAIN


def test_priority_fog_beats_wind():
    result = _cat(code=45, temp=15, wind=45)
    assert result == scene.CATEGORY_FOG


def test_priority_wind_beats_hot():
    result = _cat(code=1, temp=38, wind=45)
    assert result == scene.CATEGORY_WINDY


def test_unknown_code_below_threshold_falls_back_to_season_default():
    result = _cat(code=12345, temp=20, wind=5)
    assert result == scene.CATEGORY_SEASON_DEFAULT


def test_all_categories_appear_in_priority_order_constant():
    assert set(scene.PRIORITY_ORDER) == {
        scene.CATEGORY_THUNDERSTORM, scene.CATEGORY_SNOW, scene.CATEGORY_HEAVY_RAIN,
        scene.CATEGORY_RAIN, scene.CATEGORY_DRIZZLE, scene.CATEGORY_FOG, scene.CATEGORY_WINDY,
        scene.CATEGORY_HOT, scene.CATEGORY_CLEAR, scene.CATEGORY_CLOUDY, scene.CATEGORY_SEASON_DEFAULT,
    }


def test_category_for_weather_info_none_falls_back_to_season_default():
    assert scene.category_for_weather_info(None, wind_threshold_kmh=_WIND, hot_threshold_c=_HOT) == (
        scene.CATEGORY_SEASON_DEFAULT
    )


def test_category_for_weather_info_uses_weather_fields():
    weather = WeatherInfo(description="Ochiq", temperature_c=20.0, weather_code=0, wind_speed_kmh=5.0)
    assert scene.category_for_weather_info(weather, wind_threshold_kmh=_WIND, hot_threshold_c=_HOT) == (
        scene.CATEGORY_CLEAR
    )


def test_category_for_weather_info_missing_wind_and_code_falls_back_gracefully():
    weather = WeatherInfo(description="Noma'lum", temperature_c=20.0, weather_code=None, wind_speed_kmh=None)
    assert scene.category_for_weather_info(weather, wind_threshold_kmh=_WIND, hot_threshold_c=_HOT) == (
        scene.CATEGORY_SEASON_DEFAULT
    )
