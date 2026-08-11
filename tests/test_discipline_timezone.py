from datetime import datetime, timezone as dt_timezone

import discipline_bot


def test_today_uses_company_timezone_not_server_utc_date(monkeypatch):
    """Regression: discipline_bot used to call ``date.today()`` directly,
    which returns the *server's* date. On a UTC host, 23:30 UTC is already
    04:30 the next day in Asia/Tashkent (UTC+5), so evaluations/penalties
    entered late at night were silently stamped with yesterday's date
    relative to the company's actual calendar day. ``_today()`` must use
    COMPANY_TIMEZONE instead of the server clock.
    """
    fixed_utc = datetime(2026, 3, 1, 23, 30, tzinfo=dt_timezone.utc)

    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed_utc.astimezone(tz) if tz else fixed_utc

    monkeypatch.setattr(discipline_bot, "datetime", _FixedDatetime)

    assert discipline_bot._today().isoformat() == "2026-03-02"
