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


# --------------------- VAZIFA+NAZORATCHI+BONUS V1, 6-bosqich: AI NIZOM MATCH --

_RULES = [
    {"rule_number": 3, "title": "Telefon ishlatdi", "content": "Ish vaqtida telefon ishlatish taqiqlanadi"},
    {"rule_number": 5, "title": "Kechikish", "content": "Ishga kechikish taqiqlanadi"},
]


async def test_match_incident_to_rule_returns_ai_chosen_number():
    client = _FakeClient(output_text="3")
    result = await discipline_ai.match_incident_to_rule(client, "ish vaqtida telefonda o'ynadi", _RULES)
    assert result == 3


async def test_match_incident_to_rule_returns_none_when_ai_says_no_match():
    client = _FakeClient(output_text="YOQ")
    result = await discipline_ai.match_incident_to_rule(client, "mutlaqo aloqasi yo'q holat", _RULES)
    assert result is None


async def test_match_incident_to_rule_ignores_hallucinated_rule_number():
    """AI ro'yxatda YO'Q raqamni qaytarsa (masalan halyutsinatsiya) —
    hech qanday band tanlanmagan deb hisoblanadi, taxmin qilinmaydi."""
    client = _FakeClient(output_text="999")
    result = await discipline_ai.match_incident_to_rule(client, "har qanday matn", _RULES)
    assert result is None


async def test_match_incident_to_rule_ignores_non_numeric_response():
    client = _FakeClient(output_text="Balki 3-nizom bo'lishi mumkin")
    result = await discipline_ai.match_incident_to_rule(client, "noaniq matn", _RULES)
    assert result is None


async def test_match_incident_to_rule_returns_none_on_openai_error():
    client = _FakeClient(error=RuntimeError("API xatosi"))
    result = await discipline_ai.match_incident_to_rule(client, "istalgan matn", _RULES)
    assert result is None


async def test_match_incident_to_rule_returns_none_when_no_eligible_rules():
    client = _FakeClient(output_text="3")
    result = await discipline_ai.match_incident_to_rule(client, "istalgan matn", [])
    assert result is None
