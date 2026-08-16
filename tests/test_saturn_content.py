from types import SimpleNamespace

import pytest

from repositories import saturn_group as saturn_repo
from services import saturn_content

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


class _FakeResponses:
    def __init__(self, output_text: str = "Qayta ifodalangan maslahat."):
        self._output_text = output_text

    async def create(self, **kwargs):
        return SimpleNamespace(output_text=self._output_text)


class _FakeClient:
    def __init__(self, output_text: str = "Qayta ifodalangan maslahat."):
        self.responses = _FakeResponses(output_text)


class _FailingResponses:
    async def create(self, **kwargs):
        raise RuntimeError("OpenAI xatosi")


class _FailingClient:
    responses = _FailingResponses()


# ------------------------------------------------------------------ banklar --


def test_morning_bank_has_at_least_30_unique_entries():
    assert len(saturn_content.MORNING_ADVICE_BANK) >= 30
    keys = [key for key, _text in saturn_content.MORNING_ADVICE_BANK]
    assert len(keys) == len(set(keys))


def test_night_bank_has_at_least_30_unique_entries():
    assert len(saturn_content.NIGHT_ADVICE_BANK) >= 30
    keys = [key for key, _text in saturn_content.NIGHT_ADVICE_BANK]
    assert len(keys) == len(set(keys))


def test_all_bank_entries_are_within_length_limit():
    for _key, text in saturn_content.MORNING_ADVICE_BANK + saturn_content.NIGHT_ADVICE_BANK:
        assert len(text) <= 100, text


def test_all_bank_entries_are_a_single_sentence():
    """Har bir maslahat — bitta amaliy harakat yoki foydali fikr: bitta
    yakunlovchi tinish belgisi (., !, ?) bilan tugaydigan, o'rtada
    qo'shimcha gap ulanmagan matn."""
    for _key, text in saturn_content.MORNING_ADVICE_BANK + saturn_content.NIGHT_ADVICE_BANK:
        stripped = text.rstrip(".!?")
        assert stripped.count(". ") == 0, text
        assert stripped.count("! ") == 0, text
        assert stripped.count("? ") == 0, text


def test_all_bank_entries_avoid_forbidden_topics():
    # Moliyaviy/KPI/jazo mavzusiga xos, kundalik nutqda kamdan-kam
    # tasodifan uchraydigan iboralar (masalan "foyda" so'zi o'z holicha
    # tekshirilmaydi — "ikkalasiga foyda" kabi umumiy ma'noda ham
    # ishlatiladi, moliyaviy emas).
    forbidden_phrases = (
        "savdo summasi", "kunlik reja", "bajarilish foizi", "o'rtacha chek",
        "qolgan reja", "xarajat", "jarima", "kpi",
    )
    for _key, text in saturn_content.MORNING_ADVICE_BANK + saturn_content.NIGHT_ADVICE_BANK:
        lowered = text.lower()
        assert not any(phrase in lowered for phrase in forbidden_phrases), text


# ------------------------------------------------------------ is_valid_advice --


def test_is_valid_advice_rejects_empty():
    assert saturn_content.is_valid_advice("") is False
    assert saturn_content.is_valid_advice(None) is False
    assert saturn_content.is_valid_advice("   ") is False


def test_is_valid_advice_rejects_too_long():
    long_text = "a" * 200
    assert saturn_content.is_valid_advice(long_text) is False


def test_is_valid_advice_accepts_normal_text():
    assert saturn_content.is_valid_advice("Bugun kimgadir yordam bering.") is True


# --------------------------------------------------------------- pick_* --


async def test_pick_morning_advice_uses_bank_text_without_ai_client():
    key, text = await saturn_content.pick_morning_advice(None)

    assert any(key == bank_key and text == bank_text for bank_key, bank_text in saturn_content.MORNING_ADVICE_BANK)


async def test_pick_night_advice_uses_bank_text_without_ai_client():
    key, text = await saturn_content.pick_night_advice(None)

    assert any(key == bank_key and text == bank_text for bank_key, bank_text in saturn_content.NIGHT_ADVICE_BANK)


async def test_pick_morning_advice_uses_ai_rephrase_when_valid(monkeypatch):
    client = _FakeClient(output_text="Yangi qisqa maslahat matni.")

    key, text = await saturn_content.pick_morning_advice(client)

    assert text == "Yangi qisqa maslahat matni."
    assert key in dict(saturn_content.MORNING_ADVICE_BANK)


async def test_pick_morning_advice_falls_back_when_ai_response_too_long():
    client = _FakeClient(output_text="a" * 200)

    key, text = await saturn_content.pick_morning_advice(client)

    original = dict(saturn_content.MORNING_ADVICE_BANK)[key]
    assert text == original


async def test_pick_morning_advice_falls_back_when_ai_response_empty():
    client = _FakeClient(output_text="")

    key, text = await saturn_content.pick_morning_advice(client)

    original = dict(saturn_content.MORNING_ADVICE_BANK)[key]
    assert text == original


async def test_pick_morning_advice_falls_back_when_ai_raises():
    key, text = await saturn_content.pick_morning_advice(_FailingClient())

    original = dict(saturn_content.MORNING_ADVICE_BANK)[key]
    assert text == original


async def test_pick_night_advice_falls_back_when_ai_raises():
    key, text = await saturn_content.pick_night_advice(_FailingClient())

    original = dict(saturn_content.NIGHT_ADVICE_BANK)[key]
    assert text == original


# --------------------------------------------------- 30 kunlik takrorlanmaslik --


async def test_morning_advice_does_not_repeat_within_recent_history():
    seen_keys = []
    for day in range(1, len(saturn_content.MORNING_ADVICE_BANK) + 1):
        key, _text = await saturn_content.pick_morning_advice(None)
        seen_keys.append(key)
        saturn_repo.log_post("morning_advice", f"2026-01-{day:02d}", "matn", tip_key=key)

    assert len(set(seen_keys)) == len(seen_keys)


async def test_night_advice_does_not_repeat_within_recent_history():
    seen_keys = []
    for day in range(1, len(saturn_content.NIGHT_ADVICE_BANK) + 1):
        key, _text = await saturn_content.pick_night_advice(None)
        seen_keys.append(key)
        saturn_repo.log_post("night_advice", f"2026-02-{day:02d}", "matn", tip_key=key)

    assert len(set(seen_keys)) == len(seen_keys)


# --------------------------------------------------- kengaytirilgan bank --


def test_morning_bank_has_at_least_90_entries():
    assert len(saturn_content.MORNING_ADVICE_BANK) >= 90


def test_night_bank_has_at_least_90_entries():
    assert len(saturn_content.NIGHT_ADVICE_BANK) >= 90


def test_morning_and_night_bank_texts_never_overlap():
    morning_texts = {text for _key, text in saturn_content.MORNING_ADVICE_BANK}
    night_texts = {text for _key, text in saturn_content.NIGHT_ADVICE_BANK}
    assert morning_texts.isdisjoint(night_texts)


def test_morning_bank_covers_the_five_core_weekly_categories():
    required = {"xizmat", "tozalik", "jamoa", "intizom", "rivojlanish"}
    present = {saturn_content.morning_category_of(key) for key, _text in saturn_content.MORNING_ADVICE_BANK}
    assert required.issubset(present)


def test_night_bank_covers_the_five_core_weekly_categories():
    required = {"xizmat", "tozalik", "jamoa", "intizom", "rivojlanish"}
    present = {saturn_content.night_category_of(key) for key, _text in saturn_content.NIGHT_ADVICE_BANK}
    assert required.issubset(present)


async def test_morning_advice_same_category_does_not_repeat_on_consecutive_day():
    key1, _ = await saturn_content.pick_morning_advice(None)
    saturn_repo.log_post("morning_advice", "2026-04-01", "matn", tip_key=key1)
    category1 = saturn_content.morning_category_of(key1)

    key2, _ = await saturn_content.pick_morning_advice(None)
    category2 = saturn_content.morning_category_of(key2)

    assert category2 != category1


async def test_night_advice_same_category_does_not_repeat_on_consecutive_day():
    key1, _ = await saturn_content.pick_night_advice(None)
    saturn_repo.log_post("night_advice", "2026-04-01", "matn", tip_key=key1)
    category1 = saturn_content.night_category_of(key1)

    key2, _ = await saturn_content.pick_night_advice(None)
    category2 = saturn_content.night_category_of(key2)

    assert category2 != category1


async def test_morning_advice_does_not_repeat_within_90_days():
    seen_keys = []
    for day in range(1, 91):
        key, _text = await saturn_content.pick_morning_advice(None)
        seen_keys.append(key)
        saturn_repo.log_post("morning_advice", f"2026-{(day // 28) % 12 + 1:02d}-{(day % 28) + 1:02d}", "matn", tip_key=key)

    assert len(set(seen_keys)) == len(seen_keys) == 90


async def test_morning_and_night_advice_histories_are_independent():
    """Tonggi va tungi banklar mustaqil — bittasining tarixi
    ikkinchisining tanlovini cheklamasligi kerak."""
    key, _text = await saturn_content.pick_morning_advice(None)
    saturn_repo.log_post("morning_advice", "2026-03-01", "matn", tip_key=key)

    # Xuddi shu kalit tungi bankda ham mavjud bo'lishi shart emas, lekin
    # tungi tanlov mustaqil ishlashi kerak (xato bermasligi yetarli).
    night_key, night_text = await saturn_content.pick_night_advice(None)
    assert night_key in dict(saturn_content.NIGHT_ADVICE_BANK)
    assert night_text
