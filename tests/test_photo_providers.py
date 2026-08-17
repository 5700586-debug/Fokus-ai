"""``providers/pexels_provider.py`` va ``providers/openverse_provider.py``
uchun testlar — HAQIQIY tarmoqqa hech qachon chiqmaydi (aiohttp
monkeypatch qilingan)."""

import pytest

from providers import openverse_provider, pexels_provider

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
    def __init__(self, response=None, raise_error=None):
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


def _patch_session(monkeypatch, session):
    import aiohttp

    monkeypatch.setattr(aiohttp, "ClientSession", lambda *args, **kwargs: session)


# ------------------------------------------------------------------ Pexels --


async def test_pexels_provider_disabled_without_api_key():
    provider = pexels_provider.PexelsProvider(api_key="")
    assert provider.is_enabled() is False


async def test_pexels_search_returns_empty_without_key_and_makes_no_request(monkeypatch):
    calls = []

    def _boom(*args, **kwargs):
        calls.append(1)
        raise AssertionError("Kalitsiz Pexels so'rov yubormasligi kerak")

    import aiohttp

    monkeypatch.setattr(aiohttp, "ClientSession", _boom)
    provider = pexels_provider.PexelsProvider(api_key="")
    results = await provider.search("spring field")
    assert results == []
    assert calls == []


async def test_pexels_search_parses_successful_response(monkeypatch):
    response = _FakeResponse(200, {
        "photos": [{
            "id": 123,
            "photographer": "Test Person",
            "photographer_url": "https://pexels.com/@test",
            "url": "https://pexels.com/photo/123",
            "src": {"large2x": "https://img/large.jpg", "original": "https://img/orig.jpg"},
            "width": 1000,
            "height": 1000,
        }]
    })
    _patch_session(monkeypatch, _FakeSession(response=response))
    provider = pexels_provider.PexelsProvider(api_key="fake-key-for-test")
    results = await provider.search("spring field")
    assert len(results) == 1
    assert results[0].photo_id == "123"
    assert results[0].photographer == "Test Person"


async def test_pexels_search_returns_empty_on_non_200(monkeypatch):
    _patch_session(monkeypatch, _FakeSession(response=_FakeResponse(401, {})))
    provider = pexels_provider.PexelsProvider(api_key="fake-key-for-test")
    assert await provider.search("query") == []


async def test_pexels_search_returns_empty_on_network_error(monkeypatch):
    _patch_session(monkeypatch, _FakeSession(raise_error=ConnectionError("tarmoq xatosi")))
    provider = pexels_provider.PexelsProvider(api_key="fake-key-for-test")
    assert await provider.search("query") == []


def test_get_pexels_provider_reads_config_key(monkeypatch):
    import config

    monkeypatch.setattr(config, "PEXELS_API_KEY", "test-key-value")
    provider = pexels_provider.get_pexels_provider()
    assert provider.is_enabled() is True


def test_get_pexels_provider_disabled_when_key_absent(monkeypatch):
    import config

    monkeypatch.setattr(config, "PEXELS_API_KEY", None)
    provider = pexels_provider.get_pexels_provider()
    assert provider.is_enabled() is False


# ---------------------------------------------------------------- Openverse --


async def test_openverse_provider_is_always_enabled():
    provider = openverse_provider.OpenverseProvider()
    assert provider.is_enabled() is True


async def test_openverse_search_filters_out_non_cc0_pdm_licenses(monkeypatch):
    response = _FakeResponse(200, {
        "results": [
            {
                "id": "a1", "title": "Good", "creator": "X", "creator_url": "",
                "foreign_landing_url": "https://example.com/a", "url": "https://example.com/a.jpg",
                "license": "cc0", "license_version": "1.0", "license_url": "",
                "source": "flickr", "width": 100, "height": 100,
            },
            {
                "id": "a2", "title": "Bad (all rights reserved)", "creator": "Y", "creator_url": "",
                "foreign_landing_url": "https://example.com/b", "url": "https://example.com/b.jpg",
                "license": "by-nc", "license_version": "4.0", "license_url": "",
                "source": "flickr", "width": 100, "height": 100,
            },
        ]
    })
    _patch_session(monkeypatch, _FakeSession(response=response))
    provider = openverse_provider.OpenverseProvider()
    results = await provider.search("nature")
    assert len(results) == 1
    assert results[0].item_id == "a1"


async def test_openverse_search_returns_empty_on_error(monkeypatch):
    _patch_session(monkeypatch, _FakeSession(raise_error=ConnectionError("tarmoq xatosi")))
    provider = openverse_provider.OpenverseProvider()
    assert await provider.search("nature") == []


async def test_openverse_search_returns_empty_on_non_200(monkeypatch):
    _patch_session(monkeypatch, _FakeSession(response=_FakeResponse(500, {})))
    provider = openverse_provider.OpenverseProvider()
    assert await provider.search("nature") == []
