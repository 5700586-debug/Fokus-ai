"""E'tiroz qarori + ball qaytarish + refund ledger BITTA tranzaksiyada (SQLite)."""

from concurrent.futures import ThreadPoolExecutor

import pytest

import db
from tests import db_fail
from config import FOUNDER_ID
from services import discipline

EMPLOYEE = 750001


def _pending_appeal() -> int:
    discipline.add_rule(1, "Band", "Matn", created_by=FOUNDER_ID)
    penalty_id = discipline.apply_penalty(EMPLOYEE, FOUNDER_ID, "2026-10-19", 10, 1, "izoh", None)["penalty_id"]
    assert discipline.submit_appeal(penalty_id, "sabab", None)
    return penalty_id


def _state(penalty_id: int) -> dict:
    conn = db.get_connection()
    try:
        penalty = conn.execute(
            "SELECT appeal_status, appeal_decision FROM discipline_penalties WHERE id = ?", (penalty_id,)
        ).fetchone()
        return {
            "status": penalty["appeal_status"], "decision": penalty["appeal_decision"],
            "balance": conn.execute("SELECT bonus_bank FROM salaries WHERE user_id = ?", (EMPLOYEE,)).fetchone()["bonus_bank"],
            "refunds": conn.execute("SELECT COUNT(*) AS n FROM bonus_bank_ledger WHERE ref_type = 'appeal_refund'").fetchone()["n"],
            "ledger": conn.execute("SELECT COUNT(*) AS n FROM bonus_bank_ledger").fetchone()["n"],
        }
    finally:
        conn.close()


def _trigger(event: str, table: str) -> None:
    db_fail.break_writes(table, event)  # SQLite va Postgres ikkalasida haqiqiy yozuv xatosi


def _drop(table: str) -> None:
    db_fail.repair(table)


def test_approval_writes_decision_balance_and_one_refund_consistently():
    penalty_id = _pending_appeal()

    discipline.decide_appeal(penalty_id, discipline.DECISION_APPROVED, FOUNDER_ID)

    assert _state(penalty_id) == {"status": "resolved", "decision": "approved", "balance": 0, "refunds": 1, "ledger": 2}
    with pytest.raises(ValueError):
        discipline.decide_appeal(penalty_id, discipline.DECISION_APPROVED, FOUNDER_ID)
    assert _state(penalty_id)["refunds"] == 1


def test_rejection_changes_no_balance_and_writes_no_refund():
    penalty_id = _pending_appeal()
    before = _state(penalty_id)

    discipline.decide_appeal(penalty_id, discipline.DECISION_REJECTED, FOUNDER_ID)

    after = _state(penalty_id)
    assert after["status"] == "resolved" and after["decision"] == "rejected"
    assert (after["balance"], after["refunds"], after["ledger"]) == (before["balance"], 0, before["ledger"])


@pytest.mark.parametrize(
    ("event", "table"),
    [("UPDATE", "discipline_penalties"), ("UPDATE", "salaries"), ("INSERT", "bonus_bank_ledger")],
)
def test_failure_at_each_stage_rolls_back_and_appeal_stays_pending_for_retry(event, table):
    penalty_id = _pending_appeal()
    before = _state(penalty_id)
    _trigger(event, table)

    with pytest.raises(Exception):
        discipline.decide_appeal(penalty_id, discipline.DECISION_APPROVED, FOUNDER_ID)

    _drop(table)
    assert _state(penalty_id) == before and before["status"] == "pending"
    discipline.decide_appeal(penalty_id, discipline.DECISION_APPROVED, FOUNDER_ID)  # qayta urinish ishlaydi
    assert _state(penalty_id)["refunds"] == 1 and _state(penalty_id)["balance"] == 0


@pytest.mark.parametrize("second", [discipline.DECISION_APPROVED, discipline.DECISION_REJECTED])
def test_parallel_decisions_give_one_final_decision_and_at_most_one_refund(second):
    penalty_id = _pending_appeal()

    def decide(decision):
        try:
            discipline.decide_appeal(penalty_id, decision, FOUNDER_ID)
            return decision
        except Exception:  # ValueError (allaqachon hal) yoki SQLite qulf — ikkalasi ham "g'olib emas"
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = [f.result() for f in [pool.submit(decide, discipline.DECISION_APPROVED), pool.submit(decide, second)]]

    state = _state(penalty_id)
    winners = [o for o in outcomes if o]
    assert len(winners) <= 1 and (not winners or winners[0] == state["decision"])
    assert state["refunds"] == (1 if state["decision"] == "approved" else 0) and state["refunds"] <= 1
    assert state["balance"] == (0 if state["decision"] == "approved" else -10)
