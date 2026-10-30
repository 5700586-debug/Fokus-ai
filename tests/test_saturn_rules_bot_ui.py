"""/listnizom sahifalari va Founder-only /nizomimport (ko'rik + qo'llash)."""

import pytest
import asyncio
import threading
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendMessage

from config import FOUNDER_ID
from services import company_rules_import as importer
from services import discipline
from tests.bot_harness import send, send_callback

pytestmark = pytest.mark.anyio

READER = 721001


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _import() -> None:
    importer.run_import(apply=True, created_by=FOUNDER_ID, expected_version=importer.import_version())


def _reader() -> None:
    from roles import set_role

    set_role(READER, "nazoratchi", set_by=FOUNDER_ID)


def _buttons(message) -> list:
    return [b for row in (message.reply_markup.inline_keyboard if message.reply_markup else []) for b in row]


def _count_rules() -> int:
    return len(discipline.list_rules())


async def _open(main, bot, data: str):
    sent = await send_callback(main.dp, bot, READER, data=data, target_chat_id=READER)
    return next(m for m in sent if isinstance(m, EditMessageText))


async def test_empty_catalog_keeps_empty_state(bot_dp):
    main, bot = bot_dp
    _reader()
    sent = await send(main.dp, bot, READER, text="/listnizom")
    assert "Hali nizomlar kiritilmagan." in sent[0].text


async def test_listnizom_with_catalog_is_paginated_and_every_message_fits(bot_dp):
    main, bot = bot_dp
    _import()
    _reader()

    sent = await send(main.dp, bot, READER, text="/listnizom")

    assert len(sent) == 1 and len(sent[0].text) <= 4096
    sections = [b.callback_data for b in _buttons(sent[0])]
    assert len(sections) == 11 == len(discipline.list_catalog_sources(discipline.get_catalog_entries(candidates_only=False)))

    seen_titles = set()
    for data in sections:
        section = data.split(":")[2]
        page = 0
        while True:
            listing = await _open(main, bot, f"nzl:l:{section}:{page}")
            assert len(listing.text) <= 4096
            for btn in _buttons(listing):
                if btn.callback_data.startswith("nzl:i:"):
                    item = await _open(main, bot, btn.callback_data)
                    assert len(item.text) <= 4096
                    seen_titles.add(int(btn.callback_data.split(":")[2]))
            if not any(b.text == "➡️" for b in _buttons(listing)):
                break
            page += 1
    assert seen_titles == {e["rule_number"] for e in discipline.get_catalog_entries(candidates_only=False)}


async def test_item_pages_reassemble_the_full_original_text_and_show_metadata(bot_dp):
    main, bot = bot_dp
    _import()
    _reader()
    entries = discipline.get_catalog_entries(candidates_only=False)
    bonus = next(e for e in entries if e.get("catalog_kind") == "bonus_model")
    n26 = next(e for e in entries if e["rule_number"] == 26)
    culture = next(e for e in entries if e.get("catalog_kind") == "culture")

    bonus_screen = await _open(main, bot, f"nzl:i:{bonus['rule_number']}:0")
    assert "Rasmiy raqam" not in bonus_screen.text and bonus["content"][:40] in bonus_screen.text
    assert "Rasmiy raqam: 26" in (await _open(main, bot, "nzl:i:26:0")).text
    assert "Rasmiy raqam" not in (await _open(main, bot, f"nzl:i:{culture['rule_number']}:0")).text

    for entry in entries:
        pages = discipline.split_text_pages(entry["content"])
        assert "\n".join(pages) == entry["content"]  # hech narsa qisqartirilmaydi
    assert n26["display_number"] == 26


async def test_legacy_short_list_is_unchanged_without_catalog(bot_dp):
    main, bot = bot_dp
    _reader()
    discipline.add_rule(1, "Band 1", "Matn 1", created_by=FOUNDER_ID)

    sent = await send(main.dp, bot, READER, text="/listnizom")

    assert "1. Band 1" in sent[0].text and not _buttons(sent[0])


async def test_only_founder_can_preview_or_apply_import(bot_dp):
    main, bot = bot_dp
    _reader()

    sent = await send(main.dp, bot, READER, text="/nizomimport")
    assert not any("Import" in (getattr(m, "text", "") or "") for m in sent)
    sent = await send_callback(main.dp, bot, READER, data=f"rimp:{importer.import_version()}", target_chat_id=READER)
    assert _count_rules() == 0


async def test_founder_preview_writes_nothing_then_apply_imports_once(bot_dp):
    main, bot = bot_dp

    sent = await send(main.dp, bot, FOUNDER_ID, text="/nizomimport")
    assert _count_rules() == 0
    preview = sent[0]
    assert "hech narsa yozilmagan" in preview.text and importer.import_version() in preview.text
    apply_data = next(b.callback_data for b in _buttons(preview) if b.callback_data.startswith("rimp:"))

    await send_callback(main.dp, bot, FOUNDER_ID, data="rimp:xxxx-v1", target_chat_id=FOUNDER_ID)
    assert _count_rules() == 0  # versiya mos emas

    await send_callback(main.dp, bot, FOUNDER_ID, data=apply_data, target_chat_id=FOUNDER_ID)
    after = _count_rules()
    assert after == 102
    await send_callback(main.dp, bot, FOUNDER_ID, data=apply_data, target_chat_id=FOUNDER_ID)
    assert _count_rules() == after


async def test_preview_with_conflict_offers_no_apply_button(bot_dp):
    main, bot = bot_dp
    discipline.add_rule(26, "BOSHQA SARLAVHA", "qo'lda yozilgan matn", created_by=FOUNDER_ID)

    sent = await send(main.dp, bot, FOUNDER_ID, text="/nizomimport")

    assert "Konfliktlar" in sent[0].text
    assert not any(b.callback_data.startswith("rimp:") for b in _buttons(sent[0]))
    assert discipline.get_rule(26)["title"] == "BOSHQA SARLAVHA"


async def test_import_is_never_run_at_startup(bot_dp):
    assert _count_rules() == 0


@pytest.mark.parametrize("expired", [False, True])
async def test_import_acknowledges_before_database_work_and_reports_afterwards(bot_dp, monkeypatch, expired):
    from tests.bot_harness import RecordingBot

    main, bot = bot_dp
    events = []
    original_call = RecordingBot.__call__
    original_import = importer.run_import
    loop_thread = threading.get_ident()

    async def recording(self, method, request_timeout=None):
        if isinstance(method, AnswerCallbackQuery):
            events.append("ack")
            if expired:
                raise TelegramBadRequest(method=method, message="Bad Request: query is too old and response timeout expired or query ID is invalid")
        elif isinstance(method, EditMessageText):
            events.append("result")
        return await original_call(self, method, request_timeout)

    def importing(**kwargs):
        assert events == ["ack"]
        assert threading.get_ident() != loop_thread
        with pytest.raises(RuntimeError):
            asyncio.get_running_loop()
        events.append("import")
        return original_import(**kwargs)

    monkeypatch.setattr(RecordingBot, "__call__", recording)
    monkeypatch.setattr(importer, "run_import", importing)
    sent = await send_callback(main.dp, bot, FOUNDER_ID, data=f"rimp:{importer.import_version()}", target_chat_id=FOUNDER_ID)

    assert events == ["ack", "import", "result"]
    assert _count_rules() == 102
    assert any(isinstance(m, EditMessageText) and "Import bajarildi" in m.text for m in sent)
    assert not any("Kutilmagan" in (getattr(m, "text", "") or "") for m in sent)
