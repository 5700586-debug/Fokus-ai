from datetime import datetime, timedelta

import pytest

import inventory_bot

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


class _FakeBot:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, target, text, **kwargs):
        self.sent.append((target, text))


def _make_savdo_boshligi(user_id: int) -> None:
    from roles import set_role
    from config import FOUNDER_ID

    set_role(user_id, "savdo_boshligi", set_by=FOUNDER_ID)


async def test_send_daily_reminders_targets_only_savdo_boshligi():
    from roles import set_role
    from config import FOUNDER_ID

    _make_savdo_boshligi(1)
    set_role(2, "haydovchi", set_by=FOUNDER_ID)

    bot = _FakeBot()
    await inventory_bot.send_daily_reminders(bot)

    targets = [t for t, _ in bot.sent]
    assert targets == [1]


async def test_send_daily_reminders_is_idempotent_same_day():
    _make_savdo_boshligi(1)

    bot = _FakeBot()
    await inventory_bot.send_daily_reminders(bot)
    await inventory_bot.send_daily_reminders(bot)

    assert len(bot.sent) == 1


async def test_reminder_tick_skips_before_configured_time(monkeypatch):
    from services import rules as rules_service

    rules_service.set_rule("inventory.reminder_time", "23:59", updated_by=1)
    _make_savdo_boshligi(1)

    bot = _FakeBot()
    await inventory_bot._reminder_tick(bot)

    assert bot.sent == []


async def test_reminder_tick_sends_after_configured_time():
    from services import rules as rules_service

    rules_service.set_rule("inventory.reminder_time", "00:00", updated_by=1)
    _make_savdo_boshligi(1)

    bot = _FakeBot()
    await inventory_bot._reminder_tick(bot)

    assert len(bot.sent) == 1


async def test_reminder_tick_uses_company_timezone_not_server_clock(monkeypatch):
    """Regression: ``_reminder_tick`` used bare ``datetime.now()`` (server
    clock). On a UTC host, 19:40 UTC is already 00:40 the next day in
    Asia/Tashkent (UTC+5) — comparing that against a ``reminder_time`` meant
    in company-local time would fire hours late. Pin the server instant to
    19:40 UTC and confirm the tick reacts to the Tashkent-local 00:40, not
    the UTC 19:40.
    """
    from datetime import timezone as dt_timezone
    from services import rules as rules_service

    import company_time

    rules_service.set_rule("inventory.reminder_time", "00:30", updated_by=1)
    _make_savdo_boshligi(1)

    fixed_utc = datetime(2026, 8, 11, 19, 40, tzinfo=dt_timezone.utc)
    monkeypatch.setattr(company_time, "now", lambda: fixed_utc.astimezone(company_time.resolve_timezone()))

    bot = _FakeBot()
    await inventory_bot._reminder_tick(bot)

    assert len(bot.sent) == 1


async def test_start_scheduler_registers_job_and_can_shutdown():
    bot = _FakeBot()
    scheduler = inventory_bot.start_scheduler(bot)
    try:
        assert scheduler.get_job("inventory_daily_reminder") is not None
        assert scheduler.running is True
    finally:
        scheduler.shutdown(wait=False)
