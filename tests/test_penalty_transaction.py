"""Minus + balans + ledger BITTA tranzaksiyada (SQLite): istalgan bosqichda xato bo'lsa hech biri saqlanmaydi."""

import pytest

import db
from tests import db_fail
from config import FOUNDER_ID
from services import discipline

EMPLOYEE = 730001


def _setup() -> None:
    discipline.add_rule(1, "Band", "Matn", created_by=FOUNDER_ID)


def _state() -> dict:
    conn = db.get_connection()
    try:
        salary = conn.execute("SELECT bonus_bank FROM salaries WHERE user_id = ?", (EMPLOYEE,)).fetchone()
        return {
            "penalties": conn.execute("SELECT COUNT(*) AS n FROM discipline_penalties WHERE employee_id = ?", (EMPLOYEE,)).fetchone()["n"],
            "ledger": conn.execute("SELECT COUNT(*) AS n FROM bonus_bank_ledger WHERE user_id = ?", (EMPLOYEE,)).fetchone()["n"],
            "balance": salary["bonus_bank"] if salary else None,
        }
    finally:
        conn.close()


def _trigger(event: str, table: str) -> None:
    db_fail.break_writes(table, event)  # SQLite va Postgres ikkalasida haqiqiy yozuv xatosi


def _drop(table: str) -> None:
    db_fail.repair(table)


def _apply():
    return discipline.apply_penalty(EMPLOYEE, FOUNDER_ID, "2026-10-19", 10, 1, "izoh", None)


def test_success_writes_penalty_balance_and_ledger_consistently():
    _setup()
    result = _apply()

    assert result["bonus_bank_balance"] == -10
    assert _state() == {"penalties": 1, "ledger": 1, "balance": -10}
    conn = db.get_connection()
    try:
        ledger = conn.execute("SELECT change_amount, ref_type, ref_id, balance_after FROM bonus_bank_ledger").fetchone()
    finally:
        conn.close()
    assert (ledger["change_amount"], ledger["ref_type"], ledger["ref_id"], ledger["balance_after"]) == (
        -10, "penalty", result["penalty_id"], -10
    )


@pytest.mark.parametrize(
    ("event", "table", "preexisting_salary"),
    [
        ("INSERT", "discipline_penalties", False),   # 1-bosqich: jarima yozuvi
        ("INSERT", "salaries", False),               # 2-bosqich: balans (yangi qator)
        ("UPDATE", "salaries", True),                # 2-bosqich: balans (mavjud qator)
        ("INSERT", "bonus_bank_ledger", False),      # 3-bosqich: ledger
        ("INSERT", "bonus_bank_ledger", True),
    ],
)
def test_failure_at_any_write_stage_leaves_nothing_partial(event, table, preexisting_salary):
    _setup()
    if preexisting_salary:
        discipline.adjust_bonus_bank(EMPLOYEE, 50, "boshlang'ich", "test", None)
    before = _state()
    _trigger(event, table)

    with pytest.raises(Exception):
        _apply()

    _drop(table)
    assert _state() == before
    expected = (before["balance"] or 0) - 10
    assert _apply()["bonus_bank_balance"] == expected  # qayta urinish noldan to'liq ishlaydi
