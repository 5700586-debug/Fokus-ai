from types import SimpleNamespace

import pytest

import saturn_group_bot
from config import FOUNDER_ID
from services import messages as messages_catalog
from services import rules as rules_service
from tests.bot_harness import RecordingBot, send, texts

pytestmark = pytest.mark.anyio

_DENIAL_TEXTS = {
    messages_catalog.GENERIC_DENIAL,
    messages_catalog.CASH_FINANCE_DENIAL,
    messages_catalog.MANAGEMENT_DENIAL,
    messages_catalog.REPEAT_OFFENDER_DENIAL,
}


def _assert_denied(sent) -> None:
    assert len(sent) == 1, sent
    assert sent[0].text in _DENIAL_TEXTS, sent[0].text


@pytest.fixture
def anyio_backend():
    return "asyncio"


class _FakeResponses:
    async def create(self, **kwargs):
        return SimpleNamespace(output_text="AI matni")


class _FakeClient:
    responses = _FakeResponses()


async def test_saturntest_requires_founder(bot_dp):
    main, bot = bot_dp

    sent = await send(main.dp, bot, 999999, text="/saturntest morning")
    _assert_denied(sent)


async def test_saturntest_without_group_id_configured_shows_setup_hint(bot_dp):
    main, bot = bot_dp

    sent = await send(main.dp, bot, FOUNDER_ID, text="/saturntest morning")
    texts_out = [m.text for m in sent]
    assert any("saturn.group_chat_id" in (t or "") for t in texts_out)


async def test_saturntest_sends_requested_post_type(bot_dp, monkeypatch):
    main, bot = bot_dp

    rules_service.set_rule("saturn.group_chat_id", "-100999", updated_by=FOUNDER_ID)
    monkeypatch.setattr(main.openai_client.responses, "create", _FakeResponses().create)

    sent = await send(main.dp, bot, FOUNDER_ID, text="/saturntest tip")
    texts_out = [m.text for m in sent]
    assert any("yuborildi" in (t or "") for t in texts_out)


async def test_saturntest_in_group_auto_captures_chat_id(bot_dp, monkeypatch):
    main, bot = bot_dp
    monkeypatch.setattr(main.openai_client.responses, "create", _FakeResponses().create)

    assert rules_service.get_saturn_group_chat_id() is None

    sent = await send(
        main.dp, bot, FOUNDER_ID, text="/saturntest tip", chat_id=-100555, chat_type="group"
    )

    assert rules_service.get_saturn_group_chat_id() == -100555
    texts_out = [m.text for m in sent]
    assert any("Guruh ID saqlandi: -100555" in (t or "") for t in texts_out)


async def test_saturntest_in_group_without_post_type_still_captures_and_shows_hint(bot_dp):
    main, bot = bot_dp

    sent = await send(main.dp, bot, FOUNDER_ID, text="/saturntest", chat_id=-100555, chat_type="group")

    assert rules_service.get_saturn_group_chat_id() == -100555
    texts_out = [m.text for m in sent]
    assert any("Guruh ID saqlandi: -100555" in (t or "") for t in texts_out)
    assert any("Foydalanish" in (t or "") for t in texts_out)


async def test_saturntest_in_group_does_not_re_announce_capture_when_already_set(bot_dp, monkeypatch):
    main, bot = bot_dp
    monkeypatch.setattr(main.openai_client.responses, "create", _FakeResponses().create)

    rules_service.set_rule("saturn.group_chat_id", "-100555", updated_by=FOUNDER_ID)

    sent = await send(
        main.dp, bot, FOUNDER_ID, text="/saturntest tip", chat_id=-100555, chat_type="group"
    )

    texts_out = [m.text for m in sent]
    assert not any("Guruh ID saqlandi" in (t or "") for t in texts_out)
    assert any("yuborildi" in (t or "") for t in texts_out)


async def test_saturntest_non_founder_in_group_does_not_capture(bot_dp):
    main, bot = bot_dp

    await send(main.dp, bot, 999999, text="/saturntest tip", chat_id=-100555, chat_type="group")

    assert rules_service.get_saturn_group_chat_id() is None


async def test_tick_does_nothing_without_group_chat_id_configured():
    bot = RecordingBot(token="123456:TEST-TOKEN")
    await saturn_group_bot._tick(bot, _FakeClient())
    assert bot.sent == []


async def test_tick_sends_morning_message_once_time_threshold_reached(monkeypatch):
    bot = RecordingBot(token="123456:TEST-TOKEN")
    rules_service.set_rule("saturn.group_chat_id", "-100999", updated_by=FOUNDER_ID)
    rules_service.set_rule("saturn.morning_time", "00:00", updated_by=FOUNDER_ID)
    rules_service.set_rule("saturn.evening_time", "23:59", updated_by=FOUNDER_ID)
    rules_service.set_rule("saturn.tip_time", "23:59", updated_by=FOUNDER_ID)
    rules_service.set_rule("saturn.dashboard_times", "23:59", updated_by=FOUNDER_ID)

    await saturn_group_bot._tick(bot, _FakeClient())

    assert len(bot.sent) == 1  # faqat ertalabki xabar chegarasidan o'tdi
