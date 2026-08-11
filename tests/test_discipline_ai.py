from types import SimpleNamespace

import pytest

from services import discipline_ai

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


class _FakeResponses:
    def __init__(self, output_text=None, error=None):
        self._output_text = output_text
        self._error = error

    async def create(self, **kwargs):
        if self._error:
            raise self._error
        return SimpleNamespace(output_text=self._output_text)


class _FakeClient:
    def __init__(self, output_text=None, error=None):
        self.responses = _FakeResponses(output_text, error)


_RULE = {"rule_number": 5, "title": "Kechikish", "content": "Ishga kechikish taqiqlanadi"}


async def test_confirm_rule_match_returns_ai_text():
    client = _FakeClient(output_text="✅ Nizom mos keladi.")
    note = await discipline_ai.confirm_rule_match(client, "kechikdi", _RULE)
    assert note == "✅ Nizom mos keladi."


async def test_confirm_rule_match_falls_back_when_output_text_empty():
    client = _FakeClient(output_text="")
    note = await discipline_ai.confirm_rule_match(client, "kechikdi", _RULE)
    assert note == "✅ 5-nizom bazada topildi: Kechikish"


async def test_confirm_rule_match_falls_back_when_openai_errors():
    """AI hech qachon jarima oqimini to'xtatmasligi kerak — xato bo'lsa ham
    nizom mavjudligi haqidagi fallback matn bilan davom etadi.
    """
    client = _FakeClient(error=RuntimeError("API xatosi"))
    note = await discipline_ai.confirm_rule_match(client, "kechikdi", _RULE)
    assert note == "✅ 5-nizom bazada topildi: Kechikish"


async def test_prepare_appeal_brief_returns_ai_text():
    client = _FakeClient(output_text="Tavsiya: jarima asosli ko'rinadi.")
    brief = await discipline_ai.prepare_appeal_brief(client, "Ism Familiya", _RULE, 10, "sabab matni")
    assert brief == "Tavsiya: jarima asosli ko'rinadi."


async def test_prepare_appeal_brief_falls_back_when_output_text_empty():
    client = _FakeClient(output_text="")
    brief = await discipline_ai.prepare_appeal_brief(client, "Ism Familiya", _RULE, 10, "sabab matni")
    assert brief == "AI tavsiya matni olinmadi."


async def test_prepare_appeal_brief_falls_back_when_openai_errors_and_keeps_reason():
    client = _FakeClient(error=RuntimeError("API xatosi"))
    brief = await discipline_ai.prepare_appeal_brief(client, "Ism Familiya", _RULE, 10, "sabab matni")

    assert "AI tavsiyasi olinmadi" in brief
    assert "sabab matni" in brief
    assert "5-nizom" in brief
