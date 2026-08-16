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


async def test_start_scheduler_registers_stable_job_id_once_and_can_shutdown():
    """Talab: scheduler bir marta ro'yxatdan o'tishi, barqaror job ID,
    va (APScheduler standart qiymatlari orqali — qarang
    docs/ARCHITECTURE.md §6.5 va yakuniy hisobot) ``max_instances=1``/
    ``coalesce=True`` allaqachon ta'minlangan bo'lishi kerak.
    """
    bot = RecordingBot(token="123456:TEST-TOKEN")
    scheduler = saturn_group_bot.start_scheduler(bot, _FakeClient())
    try:
        job = scheduler.get_job("saturn_group_posts")
        assert job is not None
        assert scheduler.running is True
        assert job.max_instances == 1
        assert job.coalesce is True
    finally:
        scheduler.shutdown(wait=False)


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


async def test_tick_sends_morning_as_photo_not_old_text():
    """Regressiya: 08:00 chegarasidan o'tganda ENDI eski matnli
    ``send_morning_message`` emas, yangi rasmli xabar yuboriladi."""
    from aiogram.methods import SendPhoto

    bot = RecordingBot(token="123456:TEST-TOKEN")
    rules_service.set_rule("saturn.group_chat_id", "-100999", updated_by=FOUNDER_ID)
    rules_service.set_rule("saturn.morning_time", "00:00", updated_by=FOUNDER_ID)
    rules_service.set_rule("saturn.evening_time", "23:59", updated_by=FOUNDER_ID)
    rules_service.set_rule("saturn.tip_time", "23:59", updated_by=FOUNDER_ID)
    rules_service.set_rule("saturn.dashboard_times", "23:59", updated_by=FOUNDER_ID)

    await saturn_group_bot._tick(bot, _FakeClient())

    assert len(bot.sent) == 1
    assert isinstance(bot.sent[0], SendPhoto)


async def test_tick_sends_night_as_photo_not_old_financial_text():
    """Regressiya (talab #9): 21:00 chegarasidan o'tganda eski moliyaviy
    "Kun yakuni" (savdo/reja/o'rtacha chek) ENDI xodimlar guruhiga
    avtomatik ketmaydi — o'rniga moliyasiz rasmli tungi xabar boradi."""
    from aiogram.methods import SendPhoto

    bot = RecordingBot(token="123456:TEST-TOKEN")
    rules_service.set_rule("saturn.group_chat_id", "-100999", updated_by=FOUNDER_ID)
    rules_service.set_rule("saturn.morning_time", "23:59", updated_by=FOUNDER_ID)
    rules_service.set_rule("saturn.evening_time", "00:00", updated_by=FOUNDER_ID)
    rules_service.set_rule("saturn.tip_time", "23:59", updated_by=FOUNDER_ID)
    rules_service.set_rule("saturn.dashboard_times", "23:59", updated_by=FOUNDER_ID)

    await saturn_group_bot._tick(bot, _FakeClient())

    assert len(bot.sent) == 1
    assert isinstance(bot.sent[0], SendPhoto)
    # Xavfsizlik uchun: yuborilgan narsa rasm (caption yo'q/matn emas) —
    # eski "Kun yakuni"/"reja"/"o'rtacha chek" so'zlari umuman yo'q.
    caption = getattr(bot.sent[0], "caption", None) or ""
    assert "reja" not in caption.lower()
    assert "o'rtacha chek" not in caption.lower()


async def test_tick_skips_morning_image_when_disabled_via_rule():
    bot = RecordingBot(token="123456:TEST-TOKEN")
    rules_service.set_rule("saturn.group_chat_id", "-100999", updated_by=FOUNDER_ID)
    rules_service.set_rule("saturn.morning_time", "00:00", updated_by=FOUNDER_ID)
    rules_service.set_rule("saturn.evening_time", "23:59", updated_by=FOUNDER_ID)
    rules_service.set_rule("saturn.tip_time", "23:59", updated_by=FOUNDER_ID)
    rules_service.set_rule("saturn.dashboard_times", "23:59", updated_by=FOUNDER_ID)
    rules_service.set_rule("saturn.morning_image_enabled", "0", updated_by=FOUNDER_ID)

    await saturn_group_bot._tick(bot, _FakeClient())

    assert bot.sent == []


async def test_tick_skips_night_image_when_disabled_via_rule():
    bot = RecordingBot(token="123456:TEST-TOKEN")
    rules_service.set_rule("saturn.group_chat_id", "-100999", updated_by=FOUNDER_ID)
    rules_service.set_rule("saturn.morning_time", "23:59", updated_by=FOUNDER_ID)
    rules_service.set_rule("saturn.evening_time", "00:00", updated_by=FOUNDER_ID)
    rules_service.set_rule("saturn.tip_time", "23:59", updated_by=FOUNDER_ID)
    rules_service.set_rule("saturn.dashboard_times", "23:59", updated_by=FOUNDER_ID)
    rules_service.set_rule("saturn.night_image_enabled", "0", updated_by=FOUNDER_ID)

    await saturn_group_bot._tick(bot, _FakeClient())

    assert bot.sent == []


async def test_tick_sends_both_morning_and_night_when_both_thresholds_reached():
    from aiogram.methods import SendPhoto

    bot = RecordingBot(token="123456:TEST-TOKEN")
    rules_service.set_rule("saturn.group_chat_id", "-100999", updated_by=FOUNDER_ID)
    rules_service.set_rule("saturn.morning_time", "00:00", updated_by=FOUNDER_ID)
    rules_service.set_rule("saturn.evening_time", "00:00", updated_by=FOUNDER_ID)
    rules_service.set_rule("saturn.tip_time", "23:59", updated_by=FOUNDER_ID)
    rules_service.set_rule("saturn.dashboard_times", "23:59", updated_by=FOUNDER_ID)

    await saturn_group_bot._tick(bot, _FakeClient())

    assert len(bot.sent) == 2
    assert all(isinstance(m, SendPhoto) for m in bot.sent)


async def test_saturntest_morning_sends_new_image(bot_dp):
    main, bot = bot_dp
    from aiogram.methods import SendPhoto

    rules_service.set_rule("saturn.group_chat_id", "-100999", updated_by=FOUNDER_ID)

    await send(main.dp, bot, FOUNDER_ID, text="/saturntest morning")

    assert any(isinstance(m, SendPhoto) for m in bot.sent)


async def test_saturntest_night_sends_new_image(bot_dp):
    main, bot = bot_dp
    from aiogram.methods import SendPhoto

    rules_service.set_rule("saturn.group_chat_id", "-100999", updated_by=FOUNDER_ID)

    await send(main.dp, bot, FOUNDER_ID, text="/saturntest night")

    assert any(isinstance(m, SendPhoto) for m in bot.sent)


async def test_saturntest_evening_still_available_for_manual_testing(bot_dp, monkeypatch):
    """Eski moliyaviy "Kun yakuni" funksiyasi o'chirilmagan — endi avtomatik
    yuborilmaydi, lekin qo'lda sinov/rahbarlik ehtiyoji uchun ishlab turadi."""
    main, bot = bot_dp
    monkeypatch.setattr(main.openai_client.responses, "create", _FakeResponses().create)
    rules_service.set_rule("saturn.group_chat_id", "-100999", updated_by=FOUNDER_ID)

    sent = await send(main.dp, bot, FOUNDER_ID, text="/saturntest evening")

    texts_out = [m.text for m in sent]
    assert any("yuborildi" in (t or "") for t in texts_out)
