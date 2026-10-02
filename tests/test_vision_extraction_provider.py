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


_LEDGER_ITEMS = [
    {"raw_name": "abinon", "normalized_name": "Obinon", "amount": "198000"},
    {"raw_name": "Vilka", "normalized_name": "Vilka", "amount": "220000"},
    {"raw_name": "Sadaf", "normalized_name": "Sadaf", "amount": "400000"},
]


async def test_cash_report_returns_expense_items_with_raw_and_normalized_names(monkeypatch):
    result = await _extract_cash_report(
        monkeypatch,
        {"cash_sales": "unclear", "actual_cash_balance": "500000", "expense_items": _LEDGER_ITEMS,
         "written_expense_total": "818000"},
    )

    assert result.expense_items == [
        {"raw_name": "abinon", "normalized_name": "Obinon", "amount": 198000},  # imlo xato: abinon -> Obinon
        {"raw_name": "Vilka", "normalized_name": "Vilka", "amount": 220000},
        {"raw_name": "Sadaf", "normalized_name": "Sadaf", "amount": 400000},
    ]
    assert result.written_expense_total == "818000" and result.expense_total_mismatch is False


async def test_cash_report_items_sum_equal_to_written_total_keeps_actual_cash_balance(monkeypatch):
    result = await _extract_cash_report(
        monkeypatch,
        {"cash_sales": "1115000", "actual_cash_balance": "500000", "expense_items": _LEDGER_ITEMS,
         "written_expense_total": "818000"},
    )

    assert result.values == {"cash_sales": "1115000", "actual_cash_balance": "500000"}


async def test_cash_report_items_sum_not_equal_to_written_total_makes_balance_unclear(monkeypatch):
    result = await _extract_cash_report(
        monkeypatch,
        {"cash_sales": "1115000", "actual_cash_balance": "500000", "expense_items": _LEDGER_ITEMS,
         "written_expense_total": "900000"},
    )

    assert "actual_cash_balance" not in result.values  # mavjud himoya: qoldiq noaniq
    assert result.values == {"cash_sales": "1115000"}  # boshqa maydonlar buzilmadi
    assert result.expense_total_mismatch is True
    assert len(result.expense_items) == 3  # nom + summa baribir saqlash uchun qaytadi


async def test_cash_report_unclear_names_do_not_stop_the_flow_and_amounts_still_count(monkeypatch):
    result = await _extract_cash_report(
        monkeypatch,
        {"actual_cash_balance": "100000", "written_expense_total": "300000", "expense_items": [
            {"raw_name": "xdfgh", "normalized_name": None, "amount": 100000},        # noaniq nom
            {"raw_name": "Cola", "normalized_name": "Cola", "amount": "100000"},       # raw == normalized
            {"raw_name": "", "normalized_name": "Pampers", "amount": 100000},        # raw yo'q
        ]},
    )

    assert [(i["raw_name"], i["normalized_name"]) for i in result.expense_items] == [
        ("xdfgh", "xdfgh"), ("Cola", "Cola"), ("Pampers", "Pampers"),
    ]
    assert result.values["actual_cash_balance"] == "100000"  # jami nomlarga bog'liq emas, summalar mos


async def test_cash_report_invalid_amount_row_is_skipped_and_total_check_is_not_guessed(monkeypatch):
    result = await _extract_cash_report(
        monkeypatch,
        {"actual_cash_balance": "100000", "written_expense_total": "999999", "expense_items": [
            {"raw_name": "Obinon", "normalized_name": "Obinon", "amount": "198000"},
            {"raw_name": "xira yozuv", "normalized_name": None, "amount": "unclear"},
        ]},
    )

    assert [i["raw_name"] for i in result.expense_items] == ["Obinon"]
    assert result.values["actual_cash_balance"] == "100000"  # solishtirib bo'lmadi — qoldiq tashlanmaydi
    assert result.expense_total_mismatch is False


async def test_cash_report_legacy_expense_lines_format_still_guards_balance(monkeypatch):
    result = await _extract_cash_report(
        monkeypatch,
        {"actual_cash_balance": "50000", "expense_lines": [10000, 10000], "written_total": "30000"},
    )

    assert "actual_cash_balance" not in result.values and result.expense_items == []


async def test_sales_report_fields_and_default_result_fields_unchanged():
    from providers.vision_extraction_provider import ExtractionResult

    result = ExtractionResult(confident=True, values={"cash_sales": "1"})
    assert result.expense_items == [] and result.written_expense_total is None and result.expense_total_mismatch is False


async def test_cash_report_returns_items_sum_for_mismatch_and_match(monkeypatch):
    mismatch = await _extract_cash_report(
        monkeypatch,
        {"actual_cash_balance": "500000", "expense_items": _LEDGER_ITEMS, "written_expense_total": "900000"},
    )
    assert mismatch.expense_items_sum == 818000 and mismatch.written_expense_total == "900000"
    assert mismatch.expense_total_mismatch is True

    match = await _extract_cash_report(
        monkeypatch,
        {"actual_cash_balance": "500000", "expense_items": _LEDGER_ITEMS, "written_expense_total": "818000"},
    )
    assert match.expense_items_sum == 818000 and match.expense_total_mismatch is False

    invalid = await _extract_cash_report(
        monkeypatch,
        {"expense_items": [{"raw_name": "x", "amount": "unclear"}], "written_expense_total": "1"},
    )
    assert invalid.expense_items_sum is None  # solishtirib bo'lmadi
