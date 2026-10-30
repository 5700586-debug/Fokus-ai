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
