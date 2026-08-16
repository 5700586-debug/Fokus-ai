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


# --------------------------------------------- RESERVE-FIRST idempotency --


async def test_try_reserve_succeeds_once():
    reserved = await notifications.try_reserve("job-2", 111)
    assert reserved is True


async def test_try_reserve_blocks_second_parallel_call():
    """Ikkinchi (parallel) chaqiruv reservatsiyani yuta olmasligi kerak —
    hatto birinchisi hali ``mark_sent()`` chaqirmagan bo'lsa ham (qimmat
    ish davom etayotgan holatni simulyatsiya qiladi)."""
    first = await notifications.try_reserve("job-3", 111)
    second = await notifications.try_reserve("job-3", 111)

    assert first is True
    assert second is False


async def test_try_reserve_allows_different_targets():
    first = await notifications.try_reserve("job-4", 111)
    other_target = await notifications.try_reserve("job-4", 222)

    assert first is True
    assert other_target is True


async def test_release_reservation_allows_retry_after_failure():
    """Yuborish xato bilan tugasa (``release_reservation``), keyingi
    urinish qayta reservatsiya qila olishi kerak — imkoniyat butunlay
    yopilib qolmaydi."""
    await notifications.try_reserve("job-5", 111)
    notifications.release_reservation("job-5", 111)

    retried = await notifications.try_reserve("job-5", 111)
    assert retried is True


async def test_mark_sent_does_not_allow_further_reservation():
    await notifications.try_reserve("job-6", 111)
    notifications.mark_sent("job-6", 111)

    again = await notifications.try_reserve("job-6", 111)
    assert again is False
