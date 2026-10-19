"""AI qidiruviga har bir bandning TO'LIQ asl matni va ball variantlari/shartlari yetib boradi (kesilmaydi)."""

import json
from types import SimpleNamespace

import pytest

from config import FOUNDER_ID
from services import company_rules_import as importer
from services import discipline, discipline_ai

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


class _Client:
    def __init__(self, reply):
        self.calls: list[str] = []
        self.responses = SimpleNamespace(create=self._create)
        self._reply = reply

    async def _create(self, **kwargs):
        self.calls.append(kwargs["input"])
        reply = self._reply(kwargs["input"]) if callable(self._reply) else self._reply
        return SimpleNamespace(output_text=json.dumps(reply))


def _entry(number: int, content: str, options=None) -> dict:
    return {
        "rule_number": number, "title": f"Band {number}", "content": content, "source_name": "Sinov",
        "display_number": None, "section": "nizomlar", "options": options or [], "catalog_kind": "nizom",
    }


async def test_text_after_240th_char_last_condition_and_variants_reach_the_ai():
    importer.run_import(apply=True, created_by=FOUNDER_ID, expected_version=importer.import_version())
    entry = discipline.get_catalog_entry(26)
    assert len(entry["content"]) > 240
    client = _Client([{"id": 26}])

    result = await discipline_ai.suggest_catalog_candidates(client, "qo'pol hazil", discipline.get_catalog_entries())

    sent = "\n".join(client.calls)
    assert entry["content"] in sent  # butun asl matn, jumladan oxirgi shart
    assert "Minus ball dalil, kamera, guvoh yoki aniq tasdiqlangan holat asosida yoziladi." in sent
    for option in entry["options"]:
        assert option["condition_text"] in sent and f"−{option['points']}" in sent
    assert result.rule_numbers == [26]


async def test_every_catalog_entry_reaches_the_ai_in_full():
    importer.run_import(apply=True, created_by=FOUNDER_ID, expected_version=importer.import_version())
    entries = discipline.get_catalog_entries()
    client = _Client([])

    await discipline_ai.suggest_catalog_candidates(client, "biror holat", entries)

    sent = "\n".join(client.calls)
    for entry in entries:
        assert entry["content"] in sent


async def test_large_catalog_and_one_very_long_entry_lose_no_text():
    huge = "UZUN-BAND " + "x" * (discipline_ai.CATALOG_CHARS_PER_CALL * 2) + " OXIRGI-SHART"
    entries = [_entry(n, f"matn {n} " + "y" * 3000 + f" tail{n}") for n in range(1, 41)] + [_entry(500, huge)]
    assert len(discipline_ai._chunk_entries(entries)) > 2
    client = _Client(lambda text: [{"id": int(token.split("]")[0])} for token in text.split("[id ")[1:]][:3])

    result = await discipline_ai.suggest_catalog_candidates(client, "hodisa", entries)

    sent = "\n".join(client.calls)
    assert "OXIRGI-SHART" in sent and all(f"tail{n}" in sent for n in range(1, 41))
    numbers = result.rule_numbers
    assert 1 <= len(numbers) <= 3 and len(numbers) == len(set(numbers))
    assert set(numbers) <= {entry["rule_number"] for entry in entries}


async def test_invalid_duplicate_and_excess_ids_are_rejected_by_the_server():
    entries = [_entry(n, f"matn {n}") for n in range(1, 8)]
    client = _Client([{"id": 2}, {"id": 2}, {"id": 999}, {"id": 3}, {"id": 4}, {"id": 5}])

    result = await discipline_ai.suggest_catalog_candidates(client, "hodisa", entries)

    assert result.rule_numbers == [2, 3, 4]


def _with_options(number: int, option_ids: list[int]) -> dict:
    options = [
        {"id": oid, "points": 6 + index, "condition_text": f"shart {oid}", "gate_text": None, "target": "offender", "apply_allowed": True}
        for index, oid in enumerate(option_ids)
    ]
    return _entry(number, f"matn {number}", options)


async def test_variant_ids_are_shown_to_ai_and_only_own_variants_are_accepted():
    entries = [_with_options(1, [11, 12]), _with_options(2, [21, 22])]
    client = _Client([{"id": 1, "variant": 12}, {"id": 2, "variant": 11}])  # 2-bandga begona variant

    result = await discipline_ai.suggest_catalog_candidates(client, "hodisa", entries)

    assert "Variant #12 −7: shart 12" in client.calls[0]
    assert result.variants == {1: 12, 2: None}


async def test_same_band_with_different_variants_or_missing_variant_stays_undecided():
    entries = [_with_options(1, [11, 12])]
    client = _Client([{"id": 1, "variant": 11}, {"id": 1, "variant": 12}])

    result = await discipline_ai.suggest_catalog_candidates(client, "hodisa", entries)

    assert result.rule_numbers == [1] and result.variants == {1: None}
