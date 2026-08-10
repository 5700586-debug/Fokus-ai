import pytest

from providers.vision_extraction_provider import NullVisionExtractionProvider, get_vision_extraction_provider

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def test_null_provider_never_confident():
    provider = NullVisionExtractionProvider()

    result = await provider.extract("file123", "cash_report")

    assert result.confident is False
    assert result.values == {}
    assert provider.is_enabled() is False


def test_get_vision_extraction_provider_returns_null_by_default():
    provider = get_vision_extraction_provider()
    assert isinstance(provider, NullVisionExtractionProvider)
