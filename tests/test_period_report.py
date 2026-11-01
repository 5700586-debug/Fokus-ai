"""Founder haftalik/oylik hisoboti: davr chegaralari, raqamlar, dashboard rasmi, bir martalik yuborish."""

from datetime import date

import pytest
from aiogram.methods import SendPhoto

import discipline_bot
from config import FOUNDER_ID
from db import get_connection
from services import discipline, period_report
from tests.bot_harness import send_callback

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _seed() -> None:
    discipline.add_rule(18, "Ishga vaqtida kelish", "Kechikish taqiqlanadi", created_by=FOUNDER_ID)
    conn = get_connection()
    try:
        for user_id, familiya, branch in ((101, "Karimov", "SATURN A"), (102, "Aliyeva", "SATURN B")):
            conn.execute(
                "INSERT INTO employees (user_id, familiya, ism, branch, status) VALUES (?, ?, 'X', ?, 'approved')",
                (user_id, familiya, branch),
            )
        grades = [
            (101, "2026-10-19", "alo", 3), (101, "2026-10-20", "norma", 2),
            (102, "2026-10-19", "chala", 1), (102, "2026-10-20", "bajarilmagan", 0),
            (101, "2026-10-12", "norma", 2),  # oldingi hafta
            (101, "2026-10-26", "alo", 3),  # keyingi hafta — kirmaydi
        ]
        for employee_id, day, key, points in grades:
            conn.execute(
                "INSERT INTO daily_evaluations (employee_id, supervisor_id, eval_date, grade_key, grade_points, created_at) "
                "VALUES (?, 1, ?, ?, ?, ?)", (employee_id, day, key, points, day),
            )
        for employee_id, amount, decision in ((102, 20, None), (102, 10, "approved")):
            conn.execute(
                "INSERT INTO discipline_penalties (employee_id, supervisor_id, penalty_date, amount, rule_number, "
                "appeal_decision, created_at) VALUES (?, 1, '2026-10-21', ?, 18, ?, 'x')",
                (employee_id, amount, decision),
            )
        conn.execute("INSERT INTO day_close_notes VALUES (1, '2026-10-21', 'SATURN B', 2, 'Ikki xodim erta ketdi', 'x')")
        conn.commit()
    finally:
        conn.close()


def test_last_full_period_bounds():
    week = period_report.last_full_period("week", date(2026, 10, 26))  # dushanba
    assert (week.start, week.end) == (date(2026, 10, 19), date(2026, 10, 25))
    assert (week.prev_start, week.prev_end) == (date(2026, 10, 12), date(2026, 10, 18))
    assert period_report.last_full_period("week", date(2026, 10, 29)).start == date(2026, 10, 19)
    month = period_report.last_full_period("month", date(2026, 11, 1))
    assert (month.start, month.end, month.prev_start) == (date(2026, 10, 1), date(2026, 10, 31), date(2026, 9, 1))
    assert period_report.last_full_period("month", date(2026, 1, 1)).start == date(2025, 12, 1)
    assert "Oktabr" in month.title


def test_collect_counts_only_the_period_and_skips_cancelled_penalties():
    _seed()
    report = period_report.collect(period_report.last_full_period("week", date(2026, 10, 26)))
    totals = report.totals
    assert (totals.graded, totals.points) == (4, 6)
    assert totals.grades == {"alo": 1, "norma": 1, "chala": 1, "bajarilmagan": 1}
    assert (totals.penalty_count, totals.penalty_points, totals.ungraded) == (1, 20, 2)
    assert report.previous.graded == 1
    best, worst = report.employees[0], report.employees[-1]
    assert (best.user_id, best.net) == (101, 5)
    assert (worst.user_id, worst.net) == (102, 1 - 20)
    assert {b["branch"] for b in report.branches} == {"SATURN A", "SATURN B"}
    assert report.top_rules[0]["n"] == 1


def test_dashboard_png_and_fallback_summary():
    _seed()
    report = period_report.collect(period_report.last_full_period("week", date(2026, 10, 26)))
    png = period_report.render_dashboard(report)
    assert png[:8] == b"\x89PNG\r\n\x1a\n" and len(png) > 10_000
    text = period_report.fallback_summary(report)
    assert "Karimov X" in text and "Minuslar: 1 ta" in text


def test_empty_period_still_renders():
    report = period_report.collect(period_report.last_full_period("month", date(2026, 11, 1)))
    assert period_report.render_dashboard(report)[:4] == b"\x89PNG"
    assert "yozilmagan" in period_report.fallback_summary(report)


async def test_ai_failure_falls_back():
    _seed()
    report = period_report.collect(period_report.last_full_period("week", date(2026, 10, 26)))

    class _Broken:
        class responses:  # noqa: N801
            @staticmethod
            async def create(**kwargs):
                raise RuntimeError("down")

    assert await period_report.ai_summary(_Broken(), report) == period_report.fallback_summary(report)


async def test_scheduled_report_is_sent_once_per_period(bot_dp, monkeypatch):
    main, bot = bot_dp
    _seed()
    monkeypatch.setattr(discipline_bot, "_company_today", lambda: date(2026, 10, 26))
    monkeypatch.setattr(discipline_bot, "_OPENAI_CLIENT", None)
    bot.sent.clear()
    await discipline_bot._period_report_tick(bot, "week")
    await discipline_bot._period_report_tick(bot, "week")
    photos = [m for m in bot.sent if isinstance(m, SendPhoto) and m.chat_id == FOUNDER_ID]
    assert len(photos) == 1 and "Haftalik hisobot" in (photos[0].caption or "")


async def test_founder_button_sends_report_and_others_are_denied(bot_dp, monkeypatch):
    main, bot = bot_dp
    monkeypatch.setattr(discipline_bot, "_OPENAI_CLIENT", None)
    sent = await send_callback(main.dp, bot, FOUNDER_ID, data="frep:monthly", target_chat_id=FOUNDER_ID)
    assert any(isinstance(m, SendPhoto) and m.chat_id == FOUNDER_ID for m in sent)
    denied = await send_callback(main.dp, bot, 999999, data="frep:weekly", target_chat_id=999999)
    assert not any(isinstance(m, SendPhoto) for m in denied)



async def test_founder_report_ai_and_image_run_concurrently(monkeypatch, capsys):
    """AI must not block the start of Pillow; unchanged PNG and caption reach Telegram once."""
    import asyncio
    import threading
    import time
    from types import SimpleNamespace

    report = SimpleNamespace(totals=SimpleNamespace(graded=1, penalty_count=0))
    image_started = threading.Event()
    private_text = "CONFIDENTIAL_TEST_CAPTION"
    private_id = 1289912389
    expected_png = b"PNG_FIXED_BYTES"

    async def fake_ai(_client, _report):
        # Sequential AI -> image code would fail this assertion.
        started = await asyncio.to_thread(image_started.wait, 0.8)
        assert started, "Image render did not begin while AI was still running"
        return private_text

    def fake_render(_report):
        image_started.set()
        time.sleep(0.025)
        return expected_png

    class Bot:
        photos = []

        async def send_photo(self, chat_id, photo, caption=None):
            self.photos.append((chat_id, photo.data, caption))

        async def send_message(self, *a, **kw):
            raise AssertionError("Unexpected extra message")

    monkeypatch.setattr(period_report, "collect", lambda _period: report)
    monkeypatch.setattr(period_report, "ai_summary", fake_ai)
    monkeypatch.setattr(period_report, "render_dashboard", fake_render)
    monkeypatch.setattr(period_report, "_AI_TIMEOUT_SECONDS", 1.5)
    bot = Bot()
    await period_report.send_report(bot, object(), "month", private_id, date(2026, 11, 1))
    log = capsys.readouterr().out
    assert bot.photos == [(private_id, expected_png, private_text)]
    assert log.count("FOUNDER_REPORT_TIMING ") == 1
    assert private_text not in log and str(private_id) not in log
    assert "ai_status=returned_or_fallback" in log and "image_status=ok outcome=ok" in log
    assert all(f"{part}_ms=" in log for part in ("collect", "ai", "render", "telegram", "total"))


async def test_founder_report_slow_ai_is_bounded_without_retries(monkeypatch, capsys):
    """Slow API never delays sending PNG after the report-specific timeout."""
    import asyncio
    import time
    from types import SimpleNamespace

    report = SimpleNamespace(totals=SimpleNamespace(graded=1, penalty_count=0))
    private_id = 991238128
    class SlowClient:
        def __init__(self):
            self.responses = self
            self.options = []
            self.cancelled = False

        def with_options(self, **kwargs):
            self.options.append(kwargs)
            return self

        async def create(self, **kwargs):
            try:
                await asyncio.sleep(2.0)
            except asyncio.CancelledError:
                self.cancelled = True
                raise

    class Bot:
        photos = []

        async def send_photo(self, chat_id, photo, caption=None):
            self.photos.append((chat_id, photo.data, caption))

        async def send_message(self, *a, **kw):
            raise AssertionError("Expected PNG+caption")

    client = SlowClient()
    monkeypatch.setattr(period_report, "collect", lambda _period: report)
    monkeypatch.setattr(period_report, "render_dashboard", lambda _report: b"ORIGINAL_PNG")
    monkeypatch.setattr(period_report, "fallback_summary", lambda _report: "RULE_BASED_FALLBACK")
    monkeypatch.setattr(period_report, "_AI_TIMEOUT_SECONDS", 0.05)
    bot = Bot()
    t = time.perf_counter()
    await period_report.send_report(bot, client, "week", private_id, date(2026, 10, 26))
    elapsed = time.perf_counter() - t
    log = capsys.readouterr().out
    assert elapsed < 1.0, "API must not delay report for seconds"
    assert client.options == [{"timeout": 0.05, "max_retries": 0}]
    assert client.cancelled
    assert bot.photos == [(private_id, b"ORIGINAL_PNG", "RULE_BASED_FALLBACK")]
    assert "ai_status=timeout_fallback" in log and "outcome=ok" in log
    assert str(private_id) not in log and "RULE_BASED_FALLBACK" not in log


async def test_founder_report_image_failure_keeps_fallback_text(monkeypatch, capsys):
    from types import SimpleNamespace

    report = SimpleNamespace(totals=SimpleNamespace(graded=0, penalty_count=0))
    def broken_image(_report):
        raise ValueError("SECRET_IMAGE_DETAILS")

    class Bot:
        messages = []

        async def send_message(self, chat_id, message):
            self.messages.append((chat_id, message))

    monkeypatch.setattr(period_report, "collect", lambda _period: report)
    monkeypatch.setattr(period_report, "render_dashboard", broken_image)
    monkeypatch.setattr(period_report, "fallback_summary", lambda _report: "SUMMARIZED_TEXT")
    bot = Bot()
    await period_report.send_report(bot, None, "week", 888222111, date(2026, 10, 26))
    output = capsys.readouterr().out
    assert bot.messages == [(888222111, "SUMMARIZED_TEXT")]
    assert "image_status=fallback" in output and "ai_status=skipped" in output
    assert "SECRET_IMAGE_DETAILS" not in output and "888222111" not in output


async def test_founder_report_db_error_is_not_swallowed_by_timing(monkeypatch, capsys):
    def broken_collect(_period):
        raise ValueError("SECRET_DATABASE_DETAILS")

    monkeypatch.setattr(period_report, "collect", broken_collect)
    with pytest.raises(ValueError, match="SECRET_DATABASE_DETAILS"):
        await period_report.send_report(None, None, "month", 898123999, date(2026, 11, 1))
    log = capsys.readouterr().out
    assert "outcome=error" in log and "ai_ms=-1" in log and "render_ms=-1" in log
    assert "SECRET_DATABASE_DETAILS" not in log and "898123999" not in log
