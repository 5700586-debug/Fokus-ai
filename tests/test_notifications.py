import pytest

from services import notifications

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


class _FakeBot:
    def __init__(self) -> None:
        self.sent: list[tuple[int | str, str]] = []

    async def send_message(self, target, text, **kwargs):
        self.sent.append((target, text))


async def test_send_once_sends_and_marks():
    bot = _FakeBot()

    sent = await notifications.send_once(bot, "job-1", 123, "Salom")

    assert sent is True
    assert bot.sent == [(123, "Salom")]


async def test_send_once_is_idempotent_for_same_job_and_target():
    bot = _FakeBot()

    await notifications.send_once(bot, "job-1", 123, "Salom")
    sent_again = await notifications.send_once(bot, "job-1", 123, "Salom yana")

    assert sent_again is False
    assert bot.sent == [(123, "Salom")]


async def test_send_once_allows_different_targets_for_same_job():
    bot = _FakeBot()

    await notifications.send_once(bot, "job-1", 123, "Salom")
    sent_to_other = await notifications.send_once(bot, "job-1", 456, "Salom")

    assert sent_to_other is True
    assert (456, "Salom") in bot.sent
