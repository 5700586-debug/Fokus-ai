import pytest

from providers import weather_provider
from providers.weather_provider import NullWeatherProvider, OpenMeteoWeatherProvider, WeatherInfo

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


class _FakeResponse:
    def __init__(self, status: int, json_data: dict):
        self.status = status
        self._json_data = json_data

    async def json(self):
        return self._json_data

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class _FakeSession:
    def __init__(self, response: _FakeResponse | None = None, raise_error: Exception | None = None):
        self._response = response
        self._raise_error = raise_error

    def get(self, url, params=None):
        if self._raise_error:
            raise self._raise_error
        return self._response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


def _patch_session(monkeypatch, session: _FakeSession) -> None:
    import aiohttp

    monkeypatch.setattr(aiohttp, "ClientSession", lambda timeout=None: session)


async def test_null_weather_provider_always_returns_none_and_disabled():
    provider = NullWeatherProvider()

    assert await provider.get_today_weather("Qo'qon") is None
    assert provider.is_enabled() is False


async def test_open_meteo_provider_is_enabled():
    provider = OpenMeteoWeatherProvider(latitude=40.5, longitude=70.9)
    assert provider.is_enabled() is True


async def test_open_meteo_provider_returns_weather_info_on_success(monkeypatch):
    response = _FakeResponse(200, {"current_weather": {"temperature": 18.4, "weathercode": 0}})
    _patch_session(monkeypatch, _FakeSession(response=response))

    provider = OpenMeteoWeatherProvider(latitude=40.5, longitude=70.9)
    weather = await provider.get_today_weather("Qo'qon")

    assert weather == WeatherInfo(description="Ochiq", temperature_c=18.4)


async def test_open_meteo_provider_maps_unknown_weather_code(monkeypatch):
    response = _FakeResponse(200, {"current_weather": {"temperature": 5.0, "weathercode": 12345}})
    _patch_session(monkeypatch, _FakeSession(response=response))

    provider = OpenMeteoWeatherProvider(latitude=40.5, longitude=70.9)
    weather = await provider.get_today_weather("Qo'qon")

    assert weather.description == "Noma'lum"
    assert weather.temperature_c == 5.0


async def test_open_meteo_provider_returns_none_on_non_200(monkeypatch):
    response = _FakeResponse(500, {})
    _patch_session(monkeypatch, _FakeSession(response=response))

    provider = OpenMeteoWeatherProvider(latitude=40.5, longitude=70.9)
    assert await provider.get_today_weather("Qo'qon") is None


async def test_open_meteo_provider_returns_none_on_missing_current_weather(monkeypatch):
    response = _FakeResponse(200, {"hourly": {}})
    _patch_session(monkeypatch, _FakeSession(response=response))

    provider = OpenMeteoWeatherProvider(latitude=40.5, longitude=70.9)
    assert await provider.get_today_weather("Qo'qon") is None


async def test_open_meteo_provider_returns_none_on_network_error(monkeypatch):
    _patch_session(monkeypatch, _FakeSession(raise_error=ConnectionError("tarmoq xatosi")))

    provider = OpenMeteoWeatherProvider(latitude=40.5, longitude=70.9)
    assert await provider.get_today_weather("Qo'qon") is None


async def test_open_meteo_provider_returns_none_on_timeout(monkeypatch):
    import asyncio

    _patch_session(monkeypatch, _FakeSession(raise_error=asyncio.TimeoutError()))

    provider = OpenMeteoWeatherProvider(latitude=40.5, longitude=70.9)
    assert await provider.get_today_weather("Qo'qon") is None


async def test_open_meteo_provider_returns_none_on_malformed_json(monkeypatch):
    class _BrokenResponse(_FakeResponse):
        async def json(self):
            raise ValueError("JSON emas")

    _patch_session(monkeypatch, _FakeSession(response=_BrokenResponse(200, {})))

    provider = OpenMeteoWeatherProvider(latitude=40.5, longitude=70.9)
    assert await provider.get_today_weather("Qo'qon") is None


def test_get_weather_provider_returns_null_when_disabled(monkeypatch):
    import config

    monkeypatch.setattr(config, "WEATHER_PROVIDER_ENABLED", False)
    provider = weather_provider.get_weather_provider()

    assert isinstance(provider, NullWeatherProvider)


def test_get_weather_provider_returns_open_meteo_when_enabled(monkeypatch):
    import config

    monkeypatch.setattr(config, "WEATHER_PROVIDER_ENABLED", True)
    monkeypatch.setattr(config, "SATURN_WEATHER_LAT", 40.5286)
    monkeypatch.setattr(config, "SATURN_WEATHER_LON", 70.9425)

    provider = weather_provider.get_weather_provider()

    assert isinstance(provider, OpenMeteoWeatherProvider)
