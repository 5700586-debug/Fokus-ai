from datetime import datetime, timezone as dt_timezone

import pytest

import discipline_bot
from config import FOUNDER_ID

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


class _FakeBot:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, target, text, **kwargs):
        self.sent.append((target, text))


def _make_nazoratchi(user_id: int) -> None:
    from roles import set_role

    set_role(user_id, "nazoratchi", set_by=FOUNDER_ID)


def _pin_now(monkeypatch, hour: int, minute: int) -> None:
    fixed = datetime(2026, 3, 1, hour, minute, tzinfo=dt_timezone.utc)

    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed.astimezone(tz) if tz else fixed

    monkeypatch.setattr(discipline_bot, "datetime", _FixedDatetime)


async def test_day_close_tick_does_nothing_before_deadline(monkeypatch):
    _make_nazoratchi(1)
    _pin_now(monkeypatch, 10, 0)  # deadline standart 20:00

    bot = _FakeBot()
    await discipline_bot._day_close_tick(bot)

    from services import discipline

    assert discipline.get_salary(1)["bonus_bank"] == 0
    assert bot.sent == []


async def test_day_close_tick_penalizes_supervisor_after_deadline(monkeypatch):
    _make_nazoratchi(1)
    _pin_now(monkeypatch, 16, 0)

    bot = _FakeBot()
    await discipline_bot._day_close_tick(bot)

    from services import discipline

    assert discipline.get_salary(1)["bonus_bank"] == -40
    targets = [target for target, _ in bot.sent]
    assert 1 in targets
    assert FOUNDER_ID in targets


async def test_day_close_tick_is_idempotent_same_day(monkeypatch):
    _make_nazoratchi(1)
    _pin_now(monkeypatch, 16, 0)

    bot = _FakeBot()
    await discipline_bot._day_close_tick(bot)
    await discipline_bot._day_close_tick(bot)

    from services import discipline

    assert discipline.get_salary(1)["bonus_bank"] == -40


async def test_day_close_tick_skips_when_day_already_closed(monkeypatch):
    _make_nazoratchi(1)
    _pin_now(monkeypatch, 16, 0)

    from services import discipline

    discipline.close_day(1, "2026-03-01", total_employees=0)

    bot = _FakeBot()
    await discipline_bot._day_close_tick(bot)

    assert discipline.get_salary(1)["bonus_bank"] == 0
    assert bot.sent == []


async def test_day_close_tick_skips_when_no_supervisor():
    bot = _FakeBot()
    await discipline_bot._day_close_tick(bot)

    assert bot.sent == []


async def test_start_scheduler_registers_job_and_can_shutdown():
    bot = _FakeBot()
    scheduler = discipline_bot.start_scheduler(bot)
    try:
        assert scheduler.get_job("bos_day_close_audit") is not None
        assert scheduler.running is True
    finally:
        scheduler.shutdown(wait=False)
