"""Nazoratchi "kun yopilmadi" avtomatik minusi: ish kuni (work_date), aniq sana+vaqtli muddat, bir martalik yozish,
barcha nazoratchilar, o'z dam kuni, sozlama o'zgarishi. Soat/vaqt zonasi boshqariladi; lokal DB; Telegram mock."""

import asyncio
from datetime import datetime

import pytest

import db
import discipline_bot
from config import FOUNDER_ID
from services import day_close_deadline, discipline

pytestmark = pytest.mark.anyio

SUP = 1
SUP2 = 2
OLD = "2026-01-01T00:00:00+00:00"


@pytest.fixture
def anyio_backend():
    return "asyncio"


class _Bot:
    def __init__(self):
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, target, text, **kwargs):
        self.sent.append((target, text))


def _supervisor(user_id: int = SUP) -> None:
    from roles import set_role

    set_role(user_id, "nazoratchi", set_by=FOUNDER_ID)


def _pin(monkeypatch, year: int, month: int, day: int, hour: int, minute: int) -> datetime:
    tz = discipline_bot._resolve_timezone()
    fixed = datetime(year, month, day, hour, minute, tzinfo=tz)

    class _Fixed(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed.astimezone(tz) if tz else fixed

    monkeypatch.setattr(discipline_bot, "datetime", _Fixed)
    return fixed


def _set_rule(key: str, value: str, updated_at: str = OLD) -> None:
    conn = db.get_connection()
    try:
        conn.execute(
            "INSERT INTO rules (rule_key, rule_value, updated_by, updated_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(rule_key) DO UPDATE SET rule_value = excluded.rule_value, updated_at = excluded.updated_at",
            (key, value, FOUNDER_ID, updated_at),
        )
        conn.commit()
    finally:
        conn.close()


def _audits(supervisor_id: int = SUP) -> list[str]:
    conn = db.get_connection()
    try:
        rows = conn.execute("SELECT audit_date FROM supervisor_audit WHERE supervisor_id = ?", (supervisor_id,)).fetchall()
    finally:
        conn.close()
    return sorted(row["audit_date"] for row in rows)


def _bank(user_id: int = SUP) -> int:
    return discipline.get_salary(user_id)["bonus_bank"]


def _night_policy() -> None:
    _set_rule("bos.day_close_deadline", "01:30")
    _set_rule("bos.work_day_start", "08:00")


# ------------------------------------------------------------ sof hisoblash --


def test_pure_work_date_and_deadline_datetime_logic():
    tz = discipline_bot._resolve_timezone()
    start, deadline = day_close_deadline.parse_hhmm("08:00"), day_close_deadline.parse_hhmm("01:30")
    d = datetime(2026, 3, 1, 23, 0, tzinfo=tz)
    assert day_close_deadline.work_date_at(d, start).isoformat() == "2026-03-01"
    assert day_close_deadline.work_date_at(datetime(2026, 3, 2, 1, 35, tzinfo=tz), start).isoformat() == "2026-03-01"
    assert day_close_deadline.work_date_at(datetime(2026, 3, 2, 8, 0, tzinfo=tz), start).isoformat() == "2026-03-02"
    due = day_close_deadline.deadline_at(datetime(2026, 3, 1).date(), deadline, start, tz)
    assert due == datetime(2026, 3, 2, 1, 30, tzinfo=tz)  # D kuni uchun muddat D+1 sanasidagi 01:30
    default_start = day_close_deadline.parse_hhmm("00:00")
    assert day_close_deadline.deadline_at(datetime(2026, 3, 1).date(), day_close_deadline.parse_hhmm("20:00"), default_start, tz) == datetime(2026, 3, 1, 20, 0, tzinfo=tz)


# ------------------------------------------------------------------ 20:00 --


async def test_default_20_00_behaviour_and_amount_are_unchanged(monkeypatch):
    _supervisor()
    bot = _Bot()
    _pin(monkeypatch, 2026, 3, 1, 19, 59)
    await discipline_bot._day_close_tick(bot)
    assert _bank() == 0 and _audits() == []

    _pin(monkeypatch, 2026, 3, 1, 20, 0)
    await discipline_bot._day_close_tick(bot)

    assert _bank() == -40 and _audits() == ["2026-03-01"]
    assert any("2026-03-01" in text and "-40" in text for target, text in bot.sent if target == SUP)  # xabarda work_date
    assert any("2026-03-01" in text for target, text in bot.sent if target == FOUNDER_ID)


# ------------------------------------------------- 01:30 muddat, chegara 08:00 --


async def test_night_deadline_belongs_to_previous_work_date(monkeypatch):
    _supervisor()
    _night_policy()
    bot = _Bot()
    for args in ((2026, 3, 1, 23, 0), (2026, 3, 2, 1, 0)):
        _pin(monkeypatch, *args)
        await discipline_bot._day_close_tick(bot)
    assert _bank() == 0 and _audits() == []  # muddat hali kelmagan

    _pin(monkeypatch, 2026, 3, 2, 1, 35)
    await discipline_bot._day_close_tick(bot)
    assert _audits() == ["2026-03-01"] and _bank() == -40  # D uchun bir marta

    _pin(monkeypatch, 2026, 3, 2, 9, 0)  # yangi ish kuni D+1: muddat D+2 01:30
    await discipline_bot._day_close_tick(bot)
    assert _audits() == ["2026-03-01"] and _bank() == -40


async def test_repeated_parallel_and_restart_ticks_never_double_penalize(monkeypatch):
    _supervisor()
    _night_policy()
    _pin(monkeypatch, 2026, 3, 2, 1, 35)
    bot = _Bot()

    await asyncio.gather(*(discipline_bot._day_close_tick(bot) for _ in range(4)))
    await discipline_bot._day_close_tick(_Bot())  # "restart": yangi jarayon, bir xil DB

    assert _bank() == -40 and _audits() == ["2026-03-01"]


async def test_next_calendar_day_closure_does_not_close_the_previous_work_date(monkeypatch):
    _supervisor()
    _night_policy()
    _pin(monkeypatch, 2026, 3, 2, 1, 35)
    discipline.close_day(SUP, "2026-03-02", 3)  # D+1 yopilishi D ni yopmaydi

    await discipline_bot._day_close_tick(_Bot())

    assert _audits() == ["2026-03-01"]


async def test_work_date_closure_prevents_penalty(monkeypatch):
    _supervisor()
    _night_policy()
    discipline.close_day(SUP, "2026-03-01", 3)
    _pin(monkeypatch, 2026, 3, 2, 1, 35)

    await discipline_bot._day_close_tick(_Bot())

    assert _bank() == 0 and _audits() == []


# ------------------------------------------------------------ nazoratchilar --


async def test_every_active_supervisor_is_checked_independently(monkeypatch):
    import roles

    _supervisor(SUP)
    monkeypatch.setitem(roles._USERS, SUP2, {"role": "nazoratchi", "added_by": FOUNDER_ID, "added_at": OLD})
    assert roles.list_users_by_role("nazoratchi") == [SUP, SUP2]
    discipline.close_day(SUP, "2026-03-01", 3)  # birinchisi yopgan, ikkinchisi yo'q
    _pin(monkeypatch, 2026, 3, 1, 21, 0)

    await discipline_bot._day_close_tick(_Bot())

    assert _bank(SUP) == 0 and _bank(SUP2) == -40 and _audits(SUP2) == ["2026-03-01"]


async def test_own_day_off_exempts_only_that_supervisor_and_missing_branch_data_is_not_guessed(monkeypatch):
    import roles
    from services import attendance as attendance_service

    _supervisor(SUP)
    monkeypatch.setitem(roles._USERS, SUP2, {"role": "nazoratchi", "added_by": FOUNDER_ID, "added_at": OLD})
    attendance_service.set_scheduled_day_off(SUP, "2026-03-01", "manual", created_by=FOUNDER_ID, schedule_mode="fixed")
    _pin(monkeypatch, 2026, 3, 1, 21, 0)

    await discipline_bot._day_close_tick(_Bot())

    assert _bank(SUP) == 0 and _audits(SUP) == []  # "Dam" belgilangan
    assert _bank(SUP2) == -40  # grafik ma'lumoti yo'q: taxmin qilinmaydi, oddiy qoida


# --------------------------------------------------------- sozlama o'zgarishi --


async def test_deadline_changed_after_it_passed_is_not_applied_retroactively(monkeypatch):
    _supervisor()
    _set_rule("bos.day_close_deadline", "18:00", updated_at="2026-03-01T14:00:00+00:00")  # 19:00 Toshkent: 18:00 dan KEYIN
    _pin(monkeypatch, 2026, 3, 1, 21, 0)

    await discipline_bot._day_close_tick(_Bot())

    assert _bank() == 0 and _audits() == []  # orqaga minus yo'q


async def test_deadline_changed_before_it_passed_applies_to_that_day(monkeypatch):
    _supervisor()
    _set_rule("bos.day_close_deadline", "22:00", updated_at="2026-03-01T05:00:00+00:00")  # 10:00 Toshkent, muddatdan oldin
    bot = _Bot()
    _pin(monkeypatch, 2026, 3, 1, 21, 0)
    await discipline_bot._day_close_tick(bot)
    assert _bank() == 0
    _pin(monkeypatch, 2026, 3, 1, 22, 5)
    await discipline_bot._day_close_tick(bot)
    assert _bank() == -40 and _audits() == ["2026-03-01"]


async def test_policy_survives_restart_because_it_lives_in_the_database(monkeypatch):
    _supervisor()
    _set_rule("bos.day_close_deadline", "18:00", updated_at="2026-03-01T14:00:00+00:00")
    _pin(monkeypatch, 2026, 3, 1, 21, 0)
    await discipline_bot._day_close_tick(_Bot())
    await discipline_bot._day_close_tick(_Bot())  # jarayon xotirasiga tayanmaydi

    assert _bank() == 0


async def test_invalid_time_format_does_not_crash_or_penalize(monkeypatch):
    _supervisor()
    _set_rule("bos.day_close_deadline", "kech")
    _pin(monkeypatch, 2026, 3, 1, 21, 0)

    await discipline_bot._day_close_tick(_Bot())

    assert _bank() == 0 and _audits() == []


# ------------------------------------------------------------ atomiklik --


@pytest.mark.parametrize(("event", "table"), [("INSERT", "bonus_bank_ledger"), ("INSERT", "salaries"), ("UPDATE", "salaries")])
async def test_write_failure_leaves_no_partial_audit_balance_or_ledger_and_retry_works(monkeypatch, event, table):
    _supervisor()
    if event == "UPDATE":
        discipline.adjust_bonus_bank(SUP, 100, "boshlang'ich", "test", None)
    _pin(monkeypatch, 2026, 3, 1, 21, 0)
    before_bank = _bank()
    conn = db.get_connection()
    try:
        conn.execute(f"CREATE TRIGGER fokus_break BEFORE {event} ON {table} BEGIN SELECT RAISE(ABORT, 'sinov xatosi'); END")
        conn.commit()
        ledger_before = conn.execute("SELECT COUNT(*) FROM bonus_bank_ledger").fetchone()[0]
    finally:
        conn.close()

    await discipline_bot._day_close_tick(_Bot())

    conn = db.get_connection()
    try:
        assert conn.execute("SELECT COUNT(*) FROM bonus_bank_ledger").fetchone()[0] == ledger_before
        conn.execute("DROP TRIGGER fokus_break")
        conn.commit()
    finally:
        conn.close()
    assert _audits() == [] and _bank() == before_bank
    await discipline_bot._day_close_tick(_Bot())  # keyingi tick qayta urinadi
    assert _audits() == ["2026-03-01"] and _bank() == before_bank - 40
