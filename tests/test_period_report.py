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



async def test_founder_report_timing_stages_and_privacy(monkeypatch, capsys):
    """Live diagnostics separate AI and Pillow; never print captions, IDs, or report data."""
    import asyncio
    import time
    from types import SimpleNamespace

    fake_report = SimpleNamespace(totals=SimpleNamespace(graded=1, penalty_count=0))
    private_caption = "ONLY_TEST_PRIVATE_CAPTION"

    def fake_collect(_period):
        time.sleep(0.015)
        return fake_report

    async def fake_ai(_client, _report):
        await asyncio.sleep(0.035)
        return private_caption

    def fake_render(_report):
        time.sleep(0.030)
        return b"fake image bytes"

    class Bot:
        sent = 0

        async def send_photo(self, chat_id, photo, caption=None):
            assert chat_id == 123456789 and caption == private_caption
            await asyncio.sleep(0.020)
            self.sent += 1

        async def send_message(self, *_args, **_kwargs):
            raise AssertionError("Expected one photo, not text fallback")

    monkeypatch.setattr(period_report, "collect", fake_collect)
    monkeypatch.setattr(period_report, "ai_summary", fake_ai)
    monkeypatch.setattr(period_report, "render_dashboard", fake_render)
    bot = Bot()
    await period_report.send_report(bot, object(), "month", 123456789, date(2026, 11, 1))
    log = capsys.readouterr().out
    assert bot.sent == 1 and log.count("FOUNDER_REPORT_TIMING ") == 1
    assert private_caption not in log and "123456789" not in log
    fields = dict(pair.split("=", 1) for pair in log.split("FOUNDER_REPORT_TIMING ", 1)[1].split())
    assert fields["kind"] == "month" and fields["outcome"] == "ok"
    assert fields["render_status"] == "ok" and fields["ai_requested"] == "1"
    assert int(fields["collect_ms"]) >= 10
    assert int(fields["ai_ms"]) >= 30
    assert int(fields["render_ms"]) >= 25
    assert int(fields["telegram_ms"]) >= 15
    assert int(fields["total_ms"]) >= sum(int(fields[f"{s}_ms"]) for s in
                                         ("collect", "ai", "render", "telegram")) - 4


async def test_founder_report_render_failure_logs_fallback_and_still_sends(monkeypatch, capsys):
    from types import SimpleNamespace
    fake_report = SimpleNamespace(totals=SimpleNamespace(graded=0, penalty_count=0))

    def bad_render(_report):
        raise RuntimeError("PRIVATE_IMAGE_ERROR")

    async def fake_ai(_client, _report):
        return "Qisqa xulosa"

    class Bot:
        messages = []

        async def send_message(self, chat_id, text):
            self.messages.append((chat_id, text))

    monkeypatch.setattr(period_report, "collect", lambda _period: fake_report)
    monkeypatch.setattr(period_report, "ai_summary", fake_ai)
    monkeypatch.setattr(period_report, "render_dashboard", bad_render)
    bot = Bot()
    await period_report.send_report(bot, None, "week", 123456789, date(2026, 10, 26))
    log = capsys.readouterr().out
    assert bot.messages == [(123456789, "Qisqa xulosa")]
    assert "PRIVATE_IMAGE_ERROR" not in log and "123456789" not in log
    assert "render_status=fallback" in log and "ai_requested=0" in log
    assert "outcome=ok" in log and "telegram_ms=" in log


async def test_founder_report_collect_error_still_logs_without_changing_exception(monkeypatch, capsys):
    def bad_collect(_period):
        raise ValueError("PRIVATE_DB_ERROR")

    monkeypatch.setattr(period_report, "collect", bad_collect)
    with pytest.raises(ValueError, match="PRIVATE_DB_ERROR"):
        await period_report.send_report(None, None, "week", 123456789, date(2026, 10, 26))
    log = capsys.readouterr().out
    assert "outcome=error" in log and "collect_ms=" in log
    assert "ai_ms=-1" in log and "render_ms=-1" in log and "telegram_ms=-1" in log
    assert "PRIVATE_DB_ERROR" not in log and "123456789" not in log
