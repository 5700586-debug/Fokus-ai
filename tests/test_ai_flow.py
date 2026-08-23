import pytest

from config import FOUNDER_ID
from tests.bot_harness import send

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def test_ai_tahlil_button_removed_from_founder_menu(bot_dp):
    main, bot = bot_dp

    sent = await send(main.dp, bot, FOUNDER_ID, text="/start")

    buttons = [btn.text for row in sent[0].reply_markup.keyboard for btn in row]
    assert "🤖 AI Tahlil" not in buttons


async def test_ai_tahlil_text_no_longer_triggers_open_ended_chat(bot_dp):
    main, bot = bot_dp

    sent = await send(main.dp, bot, FOUNDER_ID, text="🤖 AI Tahlil")

    assert not any("AI Tahlil rejimi yoqildi" in (getattr(m, "text", None) or "") for m in sent)
    assert not hasattr(main, "ai_users")
