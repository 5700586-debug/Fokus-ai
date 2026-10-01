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


class _FakeResponses:
    def __init__(self, output_text: str):
        self._output_text = output_text

    async def create(self, **kwargs):
        return type("R", (), {"output_text": self._output_text})()


class _FakeOpenAI:
    def __init__(self, output_text: str):
        self.responses = _FakeResponses(output_text)


async def _extract_cash_report(monkeypatch, payload: dict):
    import json

    import config
    from providers.vision_extraction_provider import CASH_SHIFT_CASH_REPORT, OpenAIVisionExtractionProvider

    monkeypatch.setattr(config, "VISION_EXTRACTION_ENABLED", True)
    provider = OpenAIVisionExtractionProvider(_FakeOpenAI(json.dumps(payload)))
    return await provider.extract("data:image/jpeg;base64,xx", CASH_SHIFT_CASH_REPORT)


async def test_cash_report_keeps_clear_cash_sales(monkeypatch):
    result = await _extract_cash_report(
        monkeypatch,
        {"cash_sales": "1115000", "actual_cash_balance": "unclear", "expense_lines": [], "written_total": None},
    )

    assert result.values == {"cash_sales": "1115000"}


@pytest.mark.parametrize("payload", [{}, {"cash_sales": "unclear"}, {"cash_sales": None}, {"cash_sales": "taxminan 1 mln"}])
async def test_cash_report_does_not_invent_cash_sales(monkeypatch, payload):
    result = await _extract_cash_report(
        monkeypatch, {**payload, "actual_cash_balance": "unclear", "expense_lines": [], "written_total": None}
    )

    assert "cash_sales" not in result.values
