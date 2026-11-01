"""Intizomli xodimlar yulduzi: oyiga +1/−1, nizom minusida istisno yo'q, bonuslarda 1 tadan istisno,
Founder tasdig'isiz hech narsa yozilmaydi, bir oy ikki marta o'zgarmaydi."""

from datetime import date, timedelta

import pytest
from aiogram.methods import SendMessage, SendPhoto

import discipline_bot
from config import FOUNDER_ID
from db import get_connection
from repositories import performance as performance_repo
from services import discipline, star_month
from tests.bot_harness import send_callback

pytestmark = pytest.mark.anyio

GOOD, CHALA2, TIME2, MINUS, PENDING, NAZ = 101, 102, 103, 104, 105, 106


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _seed(month_start: date = date(2026, 11, 1), days: int = 30) -> None:
    from roles import set_role

    discipline.add_rule(18, "Ishga vaqtida kelish", "Kechikish taqiqlanadi", created_by=FOUNDER_ID)
    set_role(NAZ, "nazoratchi", set_by=FOUNDER_ID)
    conn = get_connection()
    try:
        for uid in (GOOD, CHALA2, TIME2, MINUS, PENDING, NAZ):
            conn.execute("INSERT INTO employees (user_id, familiya, ism, branch, status) "
                         "VALUES (?, ?, 'X', 'SATURN A', 'approved')", (uid, f"Xodim{uid}"))
        for offset in range(days):
            if offset % 7 == 6:
                continue  # dam kuni
            day = (month_start + timedelta(days=offset)).isoformat()
            for uid in (GOOD, CHALA2, TIME2, MINUS, PENDING, NAZ):
                grade = "chala" if uid == CHALA2 and offset in (1, 2) else "alo"
                conn.execute("INSERT INTO daily_evaluations (employee_id, supervisor_id, eval_date, grade_key, grade_points, "
                             "created_at) VALUES (?, ?, ?, ?, 3, 'x')", (uid, NAZ, day, grade))
                if not (uid == TIME2 and offset in (3, 4)):
                    conn.execute("INSERT INTO time_bonus_grants (employee_id, grant_date, source, confirmed_at) "
                                 "VALUES (?, ?, 'manual', 'x')", (uid, day))
                # 2026-11 dan yulduz aniq kelish/ketish va grafik bilan to'liq kunlarga tayanadi.
                conn.execute("INSERT INTO employee_scheduled_shifts (employee_id, shift_date, planned_start, planned_end, "
                             "status, source, created_at) VALUES (?, ?, '08:00', '18:00', 'work', 'test', 'x')", (uid, day))
                late = uid == TIME2 and offset in (3, 4)
                conn.execute("INSERT INTO work_time_entries (employee_id, work_date, arrival, departure, entered_by, "
                             "created_at, updated_at) VALUES (?, ?, ?, '18:00', 1, 'x', 'x')",
                             (uid, day, "08:05" if late else "07:55"))
        for uid, status in ((MINUS, "none"), (PENDING, "pending")):
            conn.execute("INSERT INTO discipline_penalties (employee_id, supervisor_id, penalty_date, amount, rule_number, "
                         "appeal_status, created_at) VALUES (?, ?, ?, 10, 18, ?, 'x')",
                         (uid, NAZ, (month_start + timedelta(days=4)).isoformat(), status))
        conn.commit()
    finally:
        conn.close()


def _by_id(decisions) -> dict:
    return {d.user_id: d for d in decisions}


def test_rules_plus_minus_pending_and_supervisor_excluded():
    _seed()
    decisions = _by_id(star_month.evaluate("2026-11"))
    assert NAZ not in decisions
    assert decisions[GOOD].passed and decisions[GOOD].new_stars == 1
    assert not decisions[CHALA2].passed and any("chala" in r for r in decisions[CHALA2].reasons)
    assert not decisions[TIME2].passed and any("vaqt" in r for r in decisions[TIME2].reasons)
    assert not decisions[MINUS].passed and any("nizom" in r for r in decisions[MINUS].reasons)
    assert decisions[PENDING].pending


def test_one_exception_each_is_allowed():
    _seed()
    conn = get_connection()
    try:
        conn.execute("UPDATE daily_evaluations SET grade_key = 'alo' WHERE employee_id = ? AND eval_date = '2026-11-03'",
                     (CHALA2,))
        conn.execute("INSERT INTO time_bonus_grants (employee_id, grant_date, source, confirmed_at) "
                     "VALUES (?, '2026-11-05', 'manual', 'x')", (TIME2,))
        conn.commit()
    finally:
        conn.close()
    decisions = _by_id(star_month.evaluate("2026-11"))
    assert decisions[CHALA2].passed and decisions[TIME2].passed


def test_too_few_worked_days_fails():
    _seed(days=20)
    decision = _by_id(star_month.evaluate("2026-11"))[GOOD]
    assert not decision.passed and any("ishlagan" in r for r in decision.reasons)


def test_trial_month_is_not_counted():
    _seed(month_start=date(2026, 10, 1), days=31)
    assert star_month.evaluate("2026-10") == []
    assert "noyabr" in star_month.preview_text("2026-10", [])


def test_apply_is_idempotent_and_stars_go_down_but_not_below_zero():
    _seed()
    applied = star_month.apply("2026-11", star_month.evaluate("2026-11"))
    assert {d.user_id for d in applied} == {GOOD, CHALA2, TIME2, MINUS}
    assert performance_repo.get_current_stars(GOOD) == 1
    assert performance_repo.get_current_stars(MINUS) == 0
    assert star_month.apply("2026-11", star_month.evaluate("2026-11")) == []
    board = star_month.current_board()
    assert board[0]["user_id"] == GOOD and board[0]["stars"] == 1
    assert "bonus" not in str(board).lower()


def test_board_png_renders_without_photos():
    _seed()
    png = star_month.render_board(star_month.current_board(), "Yulduzlar")
    assert png[:4] == b"\x89PNG" and len(png) > 5_000


async def test_founder_confirms_then_employees_are_notified(bot_dp, monkeypatch):
    main, bot = bot_dp
    _seed()
    monkeypatch.setattr(discipline_bot, "_company_today", lambda: date(2026, 12, 1))
    bot.sent.clear()
    await discipline_bot._star_month_tick(bot)
    await discipline_bot._star_month_tick(bot)  # ikkinchi marta yuborilmaydi
    previews = [m for m in bot.sent if isinstance(m, SendMessage) and m.chat_id == FOUNDER_ID and "Yulduzlar" in m.text]
    assert len(previews) == 1 and performance_repo.get_current_stars(GOOD) == 0  # ko'rik hech narsa yozmaydi

    denied = await send_callback(main.dp, bot, GOOD, data="stars:ok:2026-11", target_chat_id=GOOD)
    assert performance_repo.get_current_stars(GOOD) == 0 and not any(isinstance(m, SendPhoto) for m in denied)

    sent = await send_callback(main.dp, bot, FOUNDER_ID, data="stars:ok:2026-11", target_chat_id=FOUNDER_ID)
    assert performance_repo.get_current_stars(GOOD) == 1
    assert any(isinstance(m, SendMessage) and m.chat_id == GOOD and "0 → 1" in m.text for m in sent)
    assert any(isinstance(m, SendPhoto) and m.chat_id == FOUNDER_ID for m in sent)
    again = await send_callback(main.dp, bot, FOUNDER_ID, data="stars:ok:2026-11", target_chat_id=FOUNDER_ID)
    assert not any(isinstance(m, SendMessage) and m.chat_id == GOOD for m in again)


async def test_current_month_cannot_be_confirmed(bot_dp, monkeypatch):
    main, bot = bot_dp
    _seed()
    monkeypatch.setattr(discipline_bot, "_company_today", lambda: date(2026, 11, 20))
    await send_callback(main.dp, bot, FOUNDER_ID, data="stars:ok:2026-11", target_chat_id=FOUNDER_ID)
    assert performance_repo.get_current_stars(GOOD) == 0


async def test_founder_star_board_button(bot_dp):
    main, bot = bot_dp
    sent = await send_callback(main.dp, bot, FOUNDER_ID, data="stars:show", target_chat_id=FOUNDER_ID)
    assert any(isinstance(m, SendPhoto) for m in sent)


def test_incomplete_data_makes_decision_pending_not_failed():
    """Grafik yoki ketish vaqti yo'q kun — "shart bajarildi" ham, "bajarilmadi" ham deb taxmin qilinmaydi."""
    _seed()
    conn = get_connection()
    try:
        conn.execute("UPDATE work_time_entries SET departure = NULL WHERE employee_id = ? AND work_date = '2026-11-02'", (GOOD,))
        conn.commit()
    finally:
        conn.close()
    decision = _by_id(star_month.evaluate("2026-11"))[GOOD]
    assert decision.pending and not decision.passed and decision.new_stars == decision.current_stars
    assert any("to'liq emas" in r for r in decision.reasons)
