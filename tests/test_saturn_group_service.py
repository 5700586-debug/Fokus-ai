from types import SimpleNamespace

import pytest

from providers.sales_data_provider import DailySales
from services import saturn_group
from tests.bot_harness import RecordingBot, texts

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


class _FakeResponses:
    def __init__(self, output_text="AI matni"):
        self._output_text = output_text

    async def create(self, **kwargs):
        return SimpleNamespace(output_text=self._output_text)


class _FakeClient:
    def __init__(self, output_text="AI matni"):
        self.responses = _FakeResponses(output_text)


def _bot():
    return RecordingBot(token="123456:TEST-TOKEN")


def test_render_dashboard_numbers_shows_missing_data_honestly():
    text = saturn_group.render_dashboard_numbers(DailySales())

    assert text.count("Ma'lumot kelmadi") == 7
    assert "0" not in text.replace("Ma'lumot kelmadi", "")


def test_render_dashboard_numbers_computes_derived_fields_when_available():
    sales = DailySales(plan_amount=1_000_000, actual_amount=500_000, receipt_count=100, yesterday_actual_amount=400_000)

    text = saturn_group.render_dashboard_numbers(sales)

    assert "50.0%" in text
    assert "5 000" in text  # o'rtacha chek = 500000/100
    assert "100 000" in text  # kechagiga nisbatan farq


async def test_send_morning_message_is_idempotent_across_restarts():
    bot = _bot()
    client = _FakeClient(output_text="Xayrli tong!")

    sent_first = await saturn_group.send_morning_message(bot, client, group_chat_id=-100111)
    assert len(bot.sent) == 1

    # "Bot qayta ishga tushdi" simulyatsiyasi — xuddi shu kunga yana chaqiriladi.
    await saturn_group.send_morning_message(bot, client, group_chat_id=-100111)
    assert len(bot.sent) == 1  # ikkinchi marta yuborilmadi


async def test_send_dashboard_message_never_fabricates_numbers():
    bot = _bot()
    client = _FakeClient(output_text="Tahlil matni")

    await saturn_group.send_dashboard_message(bot, client, group_chat_id=-100111, slot_label="12:00")

    sent_text = texts(bot.sent)[0]
    assert "Ma'lumot kelmadi" in sent_text


async def test_tip_rotation_avoids_immediate_repeats():
    bot = _bot()
    seen_keys = []

    for day in range(1, 8):
        # Har kuni turli job_key bilan yangi tip yuborilishini simulyatsiya qilamiz.
        key, _text = saturn_group._pick_tip()
        seen_keys.append(key)
        from repositories import saturn_group as saturn_repo

        saturn_repo.log_post("tip", f"2026-01-0{day}", "matn", tip_key=key)

    # Ketma-ket 7 kun ichida hech qanday tip ikki marta takrorlanmasligi kerak
    # (bankda >=7 ta noyob tip borligi sababli).
    assert len(set(seen_keys)) == len(seen_keys)


async def test_send_tip_message_is_idempotent():
    bot = _bot()

    await saturn_group.send_tip_message(bot, group_chat_id=-100111)
    await saturn_group.send_tip_message(bot, group_chat_id=-100111)

    assert len(bot.sent) == 1


async def test_send_evening_message_uses_non_blaming_fallback_when_ai_fails():
    class _FailingResponses:
        async def create(self, **kwargs):
            raise RuntimeError("API xatosi")

    class _FailingClient:
        responses = _FailingResponses()

    bot = _bot()
    await saturn_group.send_evening_message(bot, _FailingClient(), group_chat_id=-100111)

    sent_text = texts(bot.sent)[0]
    assert "rahmat" in sent_text.lower() or "kun yakuni" in sent_text.lower()


# ---------------------------------------------- tonggi/tungi rasmli xabar --


def _last_sent_method(bot):
    from aiogram.methods import SendPhoto

    assert len(bot.sent) == 1
    method = bot.sent[0]
    assert isinstance(method, SendPhoto)
    return method


async def test_send_morning_image_message_sends_a_photo_not_text():
    bot = _bot()

    await saturn_group.send_morning_image_message(bot, None, group_chat_id=-100111)

    _last_sent_method(bot)


async def test_send_night_image_message_sends_a_photo_not_text():
    bot = _bot()

    await saturn_group.send_night_image_message(bot, None, group_chat_id=-100111)

    _last_sent_method(bot)


async def test_send_morning_image_message_is_idempotent_across_restarts():
    bot = _bot()

    await saturn_group.send_morning_image_message(bot, None, group_chat_id=-100111)
    assert len(bot.sent) == 1

    # "Bot qayta ishga tushdi" simulyatsiyasi — xuddi shu kunga qayta chaqiriladi.
    await saturn_group.send_morning_image_message(bot, None, group_chat_id=-100111)
    assert len(bot.sent) == 1


async def test_send_night_image_message_is_idempotent_across_restarts():
    bot = _bot()

    await saturn_group.send_night_image_message(bot, None, group_chat_id=-100111)
    assert len(bot.sent) == 1

    await saturn_group.send_night_image_message(bot, None, group_chat_id=-100111)
    assert len(bot.sent) == 1


async def test_morning_and_night_image_use_separate_job_keys_same_day():
    """Bitta kunda ikkalasi ham (morning va night) yuborilishi kerak —
    ikkalasi alohida ``job_key``ga ega."""
    bot = _bot()

    await saturn_group.send_morning_image_message(bot, None, group_chat_id=-100111)
    await saturn_group.send_night_image_message(bot, None, group_chat_id=-100111)

    from aiogram.methods import SendPhoto

    assert len(bot.sent) == 2
    assert all(isinstance(m, SendPhoto) for m in bot.sent)


async def test_send_morning_image_message_does_not_fail_when_weather_provider_errors(monkeypatch):
    async def _boom(self, location):
        raise ConnectionError("tarmoq xatosi")

    from providers.weather_provider import NullWeatherProvider

    monkeypatch.setattr(NullWeatherProvider, "get_today_weather", _boom)
    monkeypatch.setattr("services.saturn_group.get_weather_provider", lambda: NullWeatherProvider())

    bot = _bot()
    await saturn_group.send_morning_image_message(bot, None, group_chat_id=-100111)

    _last_sent_method(bot)  # baribir yuborildi


async def test_send_morning_image_message_does_not_fail_when_ai_errors():
    class _FailingResponses:
        async def create(self, **kwargs):
            raise RuntimeError("OpenAI xatosi")

    class _FailingClient:
        responses = _FailingResponses()

    bot = _bot()
    await saturn_group.send_morning_image_message(bot, _FailingClient(), group_chat_id=-100111)

    _last_sent_method(bot)


async def test_send_morning_image_message_logs_morning_advice_post():
    from repositories import saturn_group as saturn_repo

    bot = _bot()
    await saturn_group.send_morning_image_message(bot, None, group_chat_id=-100111)

    recent = saturn_repo.get_recent_posts("morning_advice", limit=1)
    assert len(recent) == 1


async def test_send_night_image_message_logs_night_advice_post():
    from repositories import saturn_group as saturn_repo

    bot = _bot()
    await saturn_group.send_night_image_message(bot, None, group_chat_id=-100111)

    recent = saturn_repo.get_recent_posts("night_advice", limit=1)
    assert len(recent) == 1


async def test_send_morning_image_message_second_parallel_call_is_a_no_op(monkeypatch):
    """Reserve-first: birinchi chaqiruv reservatsiyani yutgach, hali
    ``mark_sent`` chaqirilmasdan turib ikkinchi (parallel) chaqiruv
    kelsa ham, hech narsa yubormasligi kerak.
    """
    from services import notifications

    bot = _bot()
    reserved = await notifications.try_reserve("saturn_morning_image_" + saturn_group._today_str(), -100111)
    assert reserved is True  # slot band qilindi (xuddi boshqa chaqiruv band qilgandek)

    await saturn_group.send_morning_image_message(bot, None, group_chat_id=-100111)

    assert bot.sent == []  # ikkinchi chaqiruv hech narsa yubormadi
