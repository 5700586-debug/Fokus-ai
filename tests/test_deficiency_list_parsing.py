import pytest

from services.deficiency_list_ai import parse_line_deterministic


@pytest.mark.parametrize(
    "line, expected",
    [
        ("Cola 2L 10 blok", {"product_name": "Cola 2L", "quantity": 10.0, "unit": "blok"}),
        ("Flesh 1 karobka", {"product_name": "Flesh", "quantity": 1.0, "unit": "karobka"}),
        ("Pomidor 10 kg", {"product_name": "Pomidor", "quantity": 10.0, "unit": "kg"}),
        ("Cola 2 litr 10 blok", {"product_name": "Cola 2 litr", "quantity": 10.0, "unit": "blok"}),
    ],
)
def test_line_is_parsed_with_product_size_kept_in_name(line, expected):
    assert parse_line_deterministic(line) == expected


@pytest.mark.parametrize("line", ["Cola 2L", "Cola 2L 10", "Flesh karobka", "Cola 2L blok"])
def test_missing_quantity_or_unit_is_not_invented(line):
    assert parse_line_deterministic(line) is None


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.parametrize(
    "line, expected",
    [
        ("pomidor 1 yashig", {"product_name": "pomidor", "quantity": 1.0, "unit": "yashik"}),
        ("pomidor 1 yashik", {"product_name": "pomidor", "quantity": 1.0, "unit": "yashik"}),
        ("olma qizil 1karopka", {"product_name": "olma qizil", "quantity": 1.0, "unit": "karobka"}),
        ("tuz bir karobka", {"product_name": "tuz", "quantity": 1.0, "unit": "karobka"}),
        ("olma kotta 5 kg", {"product_name": "olma katta", "quantity": 5.0, "unit": "kg"}),
        ("tuzlangan bodring 3 kg", {"product_name": "tuzlangan bodring", "quantity": 3.0, "unit": "kg"}),
        ("kola 2 litr 5 blok", {"product_name": "kola 2 litr", "quantity": 5.0, "unit": "blok"}),
    ],
)
def test_spelling_variants_and_word_numbers_are_understood(line, expected):
    assert parse_line_deterministic(line) == expected


@pytest.mark.parametrize(
    "line, expected",
    [
        ("tuz 3 karopka", {"product_name": "tuz", "quantity": 3.0, "unit": "karobka"}),
        ("un 5 qop", {"product_name": "un", "quantity": 5.0, "unit": "qop"}),
        ("ukrop 5vog'", {"product_name": "ukrop", "quantity": 5.0, "unit": "bog"}),
        ("rayhon 5bog'", {"product_name": "rayhon", "quantity": 5.0, "unit": "bog"}),
        ("olma 1karopka", {"product_name": "olma", "quantity": 1.0, "unit": "karobka"}),
        ("pomidor 2 yashig", {"product_name": "pomidor", "quantity": 2.0, "unit": "yashik"}),
    ],
)
def test_real_store_units_are_understood(line, expected):
    assert parse_line_deterministic(line) == expected


@pytest.mark.parametrize(
    "written, normalized",
    [
        ("karopka", "karobka"),
        ("karopqa", "karobka"),
        ("korobka", "karobka"),
        ("коробка", "karobka"),
        ("yashig", "yashik"),
        ("yashiq", "yashik"),
        ("yashik", "yashik"),
        ("ящик", "yashik"),
        ("qop", "qop"),
        ("pachka", "pachka"),
        ("пачка", "pachka"),
        ("upakovka", "upakovka"),
        ("упаковка", "upakovka"),
        ("bog", "bog"),
        ("bog'", "bog"),
        ("bog‘", "bog"),
        ("bog’", "bog"),
        ("vog", "bog"),
        ("vog'", "bog"),
        ("vog‘", "bog"),
        ("vog’", "bog"),
        ("vogh", "bog"),
    ],
)
def test_unit_spelling_variants_are_normalized(written, normalized):
    assert parse_line_deterministic(f"rayhon 5 {written}") == {
        "product_name": "rayhon",
        "quantity": 5.0,
        "unit": normalized,
    }
    assert parse_line_deterministic(f"rayhon 5{written}") == {
        "product_name": "rayhon",
        "quantity": 5.0,
        "unit": normalized,
    }


def test_short_answer_understands_glued_store_units():
    from services.deficiency_list_ai import apply_short_answer, parse_line_partial

    item = {"raw_line": "olma", "parsed": None, "partial": parse_line_partial("olma")}
    assert apply_short_answer(item, "1karopka") is True
    assert item["parsed"] == {"product_name": "olma", "quantity": 1.0, "unit": "karobka"}

    item = {"raw_line": "ukrop", "parsed": None, "partial": parse_line_partial("ukrop")}
    assert apply_short_answer(item, "5vog'") is True
    assert item["parsed"] == {"product_name": "ukrop", "quantity": 5.0, "unit": "bog"}


def test_partial_parse_never_invents_missing_quantity_or_unit():
    from services.deficiency_list_ai import parse_line_partial

    assert parse_line_partial("zira") == {"product_name": "zira", "quantity": None, "unit": None}
    assert parse_line_partial("tuz kg") == {"product_name": "tuz", "quantity": None, "unit": "kg"}
    assert parse_line_partial("tuz 5") == {"product_name": "tuz", "quantity": 5.0, "unit": None}
    assert parse_line_partial("Cola 2L") == {"product_name": "Cola 2L", "quantity": None, "unit": None}


def test_short_answers_fill_only_what_was_written_and_keep_quality():
    from services.deficiency_list_ai import apply_short_answer, parse_line_partial

    item = {"raw_line": "olma", "parsed": None, "partial": parse_line_partial("olma")}
    assert apply_short_answer(item, "kotta") is True
    assert item["parsed"] is None and item["partial"]["product_name"] == "olma katta"
    assert apply_short_answer(item, "3") is True
    assert item["parsed"] is None and item["partial"]["quantity"] == 3.0
    assert apply_short_answer(item, "kg") is True
    assert item["parsed"] == {"product_name": "olma katta", "quantity": 3.0, "unit": "kg"}


def test_numbered_answers_are_split_and_unnumbered_lines_reported():
    from services.deficiency_list_ai import split_numbered_answers

    numbered, stray = split_numbered_answers("1. 2 blok\n2) 1 kg\n3: kotta\nbiror narsa")
    assert numbered == [(1, "2 blok"), (2, "1 kg"), (3, "kotta")]
    assert stray == ["biror narsa"]


def test_non_answers_and_plain_ha_are_never_words_to_add():
    from services.deficiency_list_ai import apply_short_answer, parse_line_partial, parse_short_answer, unknown_answer_words

    assert parse_short_answer("bilmayman") is None
    assert parse_short_answer("ha") is None
    assert unknown_answer_words("pishgan") == ["pishgan"] and unknown_answer_words("kotta") == []

    item = {"raw_line": "olma", "parsed": None, "partial": parse_line_partial("olma")}
    assert apply_short_answer(item, "bilmayman") is False and apply_short_answer(item, "ha") is False
    assert apply_short_answer(item, "pishgan") is False  # AI tasdiqlamagan bitta so'z rad etiladi
    assert item["partial"] == {"product_name": "olma", "quantity": None, "unit": None}
    assert apply_short_answer(item, "pishgan", extra_quality="pishgan") is True
    assert item["partial"]["product_name"] == "olma pishgan"


def test_mixed_answer_keeps_clear_part_and_plain_ha_does_not_resolve_unclassified_word():
    from services.deficiency_list_ai import apply_short_answer, parse_line_partial, resolve_unresolved_by_choice

    item = {"raw_line": "olma", "parsed": None, "partial": parse_line_partial("olma")}
    assert apply_short_answer(item, "Karam 2 dona") is True
    assert item["parsed"] is None
    assert item["partial"] == {"product_name": "olma", "quantity": 2.0, "unit": "dona", "unresolved": ["Karam"]}

    assert resolve_unresolved_by_choice(item, "ha") is False  # oddiy "ha" hal qilmaydi
    assert item["parsed"] is None and item["partial"]["product_name"] == "olma"

    assert resolve_unresolved_by_choice(item, "tavsif") is True
    assert item["parsed"] == {"product_name": "olma Karam", "quantity": 2.0, "unit": "dona"}


def test_explicit_choices_replace_describe_or_drop_unclassified_word():
    from services.deficiency_list_ai import apply_short_answer, parse_line_partial, resolve_unresolved_by_choice

    def _item():
        item = {"raw_line": "olma", "parsed": None, "partial": parse_line_partial("olma")}
        apply_short_answer(item, "Karam 2 dona")
        return item

    item = _item()
    assert resolve_unresolved_by_choice(item, "almashtirish") is True
    assert item["parsed"] == {"product_name": "Karam", "quantity": 2.0, "unit": "dona"}

    item = _item()
    assert resolve_unresolved_by_choice(item, "yo'q") is True
    assert item["parsed"] == {"product_name": "olma", "quantity": 2.0, "unit": "dona"}


def test_mixed_answer_with_non_answer_word_keeps_quantity_and_drops_the_word():
    from services.deficiency_list_ai import apply_short_answer, parse_line_partial

    item = {"raw_line": "olma", "parsed": None, "partial": parse_line_partial("olma")}
    assert apply_short_answer(item, "2 kg bilmayman") is True
    assert item["parsed"] == {"product_name": "olma", "quantity": 2.0, "unit": "kg"}


def test_explicit_edit_is_optional_and_needs_prefix():
    from services.deficiency_list_ai import apply_explicit_edit, parse_line_partial

    item = {"raw_line": "olma", "parsed": None, "partial": parse_line_partial("olma")}
    assert apply_explicit_edit(item, "Karam 2 dona") is False and item["parsed"] is None
    assert apply_explicit_edit(item, "yangi: Karam 2 dona") is True
    assert item["parsed"] == {"product_name": "Karam", "quantity": 2.0, "unit": "dona"}


def test_replace_question_uses_natural_suffixes():
    from services.deficiency_list_ai import replace_question

    assert replace_question("olma", "Karam") == "Olmani karamga almashtirasizmi?"
    assert replace_question("pomidor", "Bodring") == "Pomidorni bodringga almashtirasizmi?"
    assert replace_question("olma", "Piyozak") == "Olmani piyozakka almashtirasizmi?"


class _FakeAIClient:
    def __init__(self, output_text=None, error=None):
        self.calls = []
        self.responses = self
        self._output_text, self._error = output_text, error

    async def create(self, **kwargs):
        from types import SimpleNamespace

        self.calls.append(kwargs)
        if self._error:
            raise self._error
        return SimpleNamespace(output_text=self._output_text)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "ai_output, words, expected",
    [
        ('{"quality": "pishgan", "product": null}', ["pishgan"], {"quality": "pishgan", "product": None}),
        ('{"quality": null, "product": "Karam"}', ["Karam"], {"quality": None, "product": "Karam"}),
        ('{"quality": null, "product": "Bodring"}', ["Karam"], {"quality": None, "product": None}),  # to'qilgan
        ('{"quality": "bilmayman", "product": null}', ["bilmayman"], {"quality": None, "product": None}),
        ('{"quality": "Saturn", "product": null}', ["pishgan"], {"quality": None, "product": None}),
        ('{"quality": "pishgan 5 kg", "product": null}', ["pishgan"], {"quality": None, "product": None}),
        ("tushunarsiz matn", ["pishgan"], {"quality": None, "product": None}),
    ],
)
async def test_classify_answer_words_only_accepts_words_the_cashier_wrote(ai_output, words, expected):
    from services.deficiency_list_ai import classify_answer_words

    client = _FakeAIClient(output_text=ai_output)
    assert await classify_answer_words(client, "olma", "miqdor va birlik kerak", words) == expected
    assert "Mahsulot: olma" in client.calls[0]["input"] and "miqdor va birlik kerak" in client.calls[0]["input"]


@pytest.mark.anyio
async def test_classify_answer_words_ai_error_or_no_client_returns_nothing():
    from services.deficiency_list_ai import classify_answer_words, resolve_quality_words

    empty = {"quality": None, "product": None}
    assert await classify_answer_words(_FakeAIClient(error=TimeoutError("x")), "olma", "q", ["pishgan"]) == empty
    assert await classify_answer_words(None, "olma", "q", ["pishgan"]) == empty
    assert await resolve_quality_words(_FakeAIClient(output_text='{"quality": "pishgan"}'), "olma", "q", ["pishgan"]) == "pishgan"


def test_other_product_answer_becomes_a_proposal_not_a_rename():
    from services.deficiency_list_ai import apply_short_answer, parse_line_partial, resolve_unresolved_by_choice

    item = {"raw_line": "olma", "parsed": None, "partial": parse_line_partial("olma")}
    assert apply_short_answer(item, "Karam 2 dona", other_product="Karam") is True
    assert item["parsed"] is None
    assert item["partial"]["product_name"] == "olma" and item["partial"]["quantity"] is None
    assert item["partial"]["replace_proposal"] == {"product_name": "Karam", "quantity": 2.0, "unit": "dona"}

    assert resolve_unresolved_by_choice(item, "yo'q") is True
    assert item["parsed"] is None and item["partial"]["product_name"] == "olma"
    assert "replace_proposal" not in item["partial"]

    assert apply_short_answer(item, "Karam 2 dona", other_product="Karam") is True
    assert resolve_unresolved_by_choice(item, "ha") is True
    assert item["parsed"] == {"product_name": "Karam", "quantity": 2.0, "unit": "dona"}


def test_plain_quantity_unit_answer_does_not_clear_replace_proposal():
    from services.deficiency_list_ai import apply_short_answer, parse_line_partial, resolve_unresolved_by_choice

    item = {"raw_line": "olma", "parsed": None, "partial": parse_line_partial("olma")}
    assert apply_short_answer(item, "Karam 2 dona", other_product="Karam") is True

    assert apply_short_answer(item, "3 dona") is False  # oddiy javob taklifni o'chirmaydi
    assert item["parsed"] is None
    assert item["partial"]["product_name"] == "olma" and item["partial"]["quantity"] is None
    assert item["partial"]["replace_proposal"] == {"product_name": "Karam", "quantity": 2.0, "unit": "dona"}

    assert resolve_unresolved_by_choice(item, "ha") is True
    assert item["parsed"] == {"product_name": "Karam", "quantity": 2.0, "unit": "dona"}
