from types import SimpleNamespace

import pytest

import saturn_group_bot
from config import FOUNDER_ID
from services import rules as rules_service
from tests.bot_harness import RecordingBot, send, texts

pytestmark = pytest.mark.anyio


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
    assert sent == []


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
