from types import SimpleNamespace

import pytest

from config import FOUNDER_ID
from tests.bot_harness import send

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def test_ai_tahlil_flow_with_mocked_openai(bot_dp, monkeypatch):
    main, bot = bot_dp

    sent = await send(main.dp, bot, FOUNDER_ID, text="🤖 AI Tahlil")
    assert "AI Tahlil rejimi yoqildi" in sent[0].text
    assert FOUNDER_ID in main.ai_users

    async def fake_create(**kwargs):
        return SimpleNamespace(output_text="Tahlil natijasi: hammasi yaxshi.")

    monkeypatch.setattr(main.openai_client.responses, "create", fake_create)

    sent = await send(main.dp, bot, FOUNDER_ID, text="100000 so'mlik savdo qildik")
    texts = [getattr(m, "text", None) for m in sent]
    assert "⏳ Tahlil qilinyapti..." in texts
    assert "Tahlil natijasi: hammasi yaxshi." in texts


async def test_ai_tahlil_flow_handles_openai_error(bot_dp, monkeypatch):
    main, bot = bot_dp

    await send(main.dp, bot, FOUNDER_ID, text="🤖 AI Tahlil")

    async def failing_create(**kwargs):
        raise RuntimeError("API xatosi")

    monkeypatch.setattr(main.openai_client.responses, "create", failing_create)

    sent = await send(main.dp, bot, FOUNDER_ID, text="Savol")
    texts = [getattr(m, "text", None) for m in sent]
    assert any("xato yuz berdi" in (t or "") for t in texts)


async def test_switching_to_ombor_exits_ai_mode(bot_dp):
    main, bot = bot_dp

    await send(main.dp, bot, FOUNDER_ID, text="🤖 AI Tahlil")
    assert FOUNDER_ID in main.ai_users

    await send(main.dp, bot, FOUNDER_ID, text="📦 Ombor")
    assert FOUNDER_ID not in main.ai_users
