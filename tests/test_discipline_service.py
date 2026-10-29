import pytest

from repositories import discipline as discipline_repo
from services import discipline


def _add_rule(rule_number: int = 3, created_by: int = 1) -> None:
    discipline.add_rule(rule_number, "Kechikish", "Ishga kechikish taqiqlanadi", created_by)


# ------------------------------------------------------------- salaries --


def test_get_salary_defaults_when_missing():
    salary = discipline.get_salary(111)
    assert salary == {"user_id": 111, "fixed_salary": 0, "bonus_bank": 0}


def test_set_fixed_salary_never_touches_bonus_bank():
    discipline.adjust_bonus_bank(111, 5, "test", "test", None)
    discipline.set_fixed_salary(111, 3_000_000, updated_by=1)

    salary = discipline.get_salary(111)
    assert salary["fixed_salary"] == 3_000_000
    assert salary["bonus_bank"] == 5


def test_adjust_bonus_bank_creates_row_and_logs_ledger():
    balance = discipline.adjust_bonus_bank(111, 7, "sinov", "test", None)
    assert balance == 7

    ledger = discipline.get_bonus_ledger(111)
    assert len(ledger) == 1
    assert ledger[0]["change_amount"] == 7
    assert ledger[0]["balance_after"] == 7


# --------------------------------------------------------------- rules --


def test_add_rule_then_get_rule():
    assert discipline.add_rule(3, "Kechikish", "Matn", created_by=1) is True
    rule = discipline.get_rule(3)
    assert rule["title"] == "Kechikish"


def test_add_rule_duplicate_number_is_noop():
    discipline.add_rule(3, "Birinchi", "Matn", created_by=1)
    assert discipline.add_rule(3, "Ikkinchi", "Boshqa matn", created_by=1) is False

    rule = discipline.get_rule(3)
    assert rule["title"] == "Birinchi"


@pytest.mark.parametrize(
    "text,expected",
    [
        ("3-nizom", 3),
        ("3 nizom", 3),
        ("nizom 12", 12),
        ("bunday nizom yo'q", None),
    ],
)
def test_extract_rule_number(text, expected):
    assert discipline.extract_rule_number(text) == expected


# ---------------------------------------------------------- daily grading --


def test_record_daily_grade_first_time_credits_full_points():
    result = discipline.record_daily_grade(111, 999, "2026-03-01", discipline.GRADE_ALO)

    assert result.grade_points == 3
    assert result.bonus_bank_balance == 3


def test_record_daily_grade_regrade_only_applies_delta():
    discipline.record_daily_grade(111, 999, "2026-03-01", discipline.GRADE_CHALA)
    result = discipline.record_daily_grade(111, 999, "2026-03-01", discipline.GRADE_ALO)

    # Chala(1) -> A'lo(3): balans faqat delta (+2) bilan o'sishi kerak,
    # ikkalasi ham qo'shilib +4 bo'lib qolmasligi kerak.
    assert result.bonus_bank_balance == 3


def test_record_daily_grade_same_grade_twice_does_not_double_count():
    discipline.record_daily_grade(111, 999, "2026-03-01", discipline.GRADE_NORMA)
    result = discipline.record_daily_grade(111, 999, "2026-03-01", discipline.GRADE_NORMA)

    assert result.bonus_bank_balance == 2

    ledger = discipline.get_bonus_ledger(111)
    assert len(ledger) == 1  # delta=0 bo'lgani uchun ikkinchi yozuv qo'shilmagan


def test_record_daily_grade_invalid_grade_raises():
    with pytest.raises(ValueError):
        discipline.record_daily_grade(111, 999, "2026-03-01", "a'lo-emas")


# --------------------- VAZIFA+NAZORATCHI+BONUS V1, 4-bosqich: ISH BAHOSI --


def test_bajarilmagan_grade_is_worth_zero_points():
    result = discipline.record_daily_grade(111, 999, "2026-03-01", discipline.GRADE_BAJARILMAGAN)

    assert result.grade_points == 0
    assert result.bonus_bank_balance == 0


def test_regrade_from_alo_to_bajarilmagan_removes_the_points():
    discipline.record_daily_grade(111, 999, "2026-03-01", discipline.GRADE_ALO)
    result = discipline.record_daily_grade(111, 999, "2026-03-01", discipline.GRADE_BAJARILMAGAN)

    assert result.bonus_bank_balance == 0


def test_get_daily_grade_returns_none_when_not_yet_graded():
    assert discipline.get_daily_grade(111, "2026-03-01") is None


def test_get_daily_grade_returns_recorded_grade():
    discipline.record_daily_grade(111, 999, "2026-03-01", discipline.GRADE_NORMA)

    grade = discipline.get_daily_grade(111, "2026-03-01")
    assert grade["grade_key"] == "norma"
    assert grade["grade_points"] == 2


# --------------------- VAZIFA+NAZORATCHI+BONUS V1, 5-bosqich: BALL AYIRISH --


def test_new_rule_has_no_penalty_amount_by_default():
    _add_rule(5)

    rule = discipline.get_rule(5)
    assert rule["default_penalty_amount"] is None
    assert discipline.list_rules_with_penalty_amount() == []


def test_set_rule_penalty_amount_makes_it_selectable():
    _add_rule(5)

    assert discipline.set_rule_penalty_amount(5, 30, updated_by=1) is True

    rules = discipline.list_rules_with_penalty_amount()
    assert len(rules) == 1
    assert rules[0]["rule_number"] == 5
    assert rules[0]["default_penalty_amount"] == 30


def test_set_rule_penalty_amount_unknown_rule_returns_false():
    assert discipline.set_rule_penalty_amount(999, 30, updated_by=1) is False


def test_set_rule_penalty_amount_rejects_non_positive():
    _add_rule(5)
    with pytest.raises(ValueError):
        discipline.set_rule_penalty_amount(5, 0, updated_by=1)


def test_apply_penalty_accepts_rule_specific_amount_outside_default_set():
    """25 ``bos.penalty_amounts`` standart to'plamida (10,20,30) yo'q,
    lekin nizom bandining O'Z belgilangan miqdori bo'lgani uchun
    qabul qilinishi kerak (Nazoratchi kartasidagi tugma oqimi)."""
    _add_rule(5)
    discipline.set_rule_penalty_amount(5, 25, updated_by=1)

    result = discipline.apply_penalty(1, 999, "2026-03-01", 25, 5, comment=None, ai_note=None)

    assert result["bonus_bank_balance"] == -25


def test_apply_penalty_still_rejects_amount_matching_neither_source():
    _add_rule(5)
    discipline.set_rule_penalty_amount(5, 25, updated_by=1)

    with pytest.raises(ValueError):
        discipline.apply_penalty(1, 999, "2026-03-01", 999, 5, comment=None, ai_note=None)


def test_report_unmatched_incident_does_not_touch_bonus_bank():
    discipline.report_unmatched_incident(1, reported_by=999, report_text="Nazoratchini haqorat qildi")

    assert discipline.get_salary(1)["bonus_bank"] == 0


def test_grade_points_are_tunable_via_rules(monkeypatch):
    """Founder /setrule orqali (kod o'zgarishisiz) baho ballarini
    o'zgartira olishi kerak — GRADE_POINTS avvalgidek kodga hardcode
    qilinmagan.
    """
    from services import rules as rules_service

    rules_service.set_rule("bos.grade_points.alo", "5", updated_by=1)

    result = discipline.record_daily_grade(111, 999, "2026-03-01", discipline.GRADE_ALO)
    assert result.grade_points == 5
    assert result.bonus_bank_balance == 5


def test_penalty_amounts_are_tunable_via_rules():
    from services import rules as rules_service

    _add_rule(5)
    rules_service.set_rule("bos.penalty_amounts", "15,25", updated_by=1)

    with pytest.raises(ValueError):
        discipline.apply_penalty(1, 999, "2026-03-01", 10, 5, comment=None, ai_note=None)

    result = discipline.apply_penalty(1, 999, "2026-03-01", 15, 5, comment=None, ai_note=None)
    assert result["bonus_bank_balance"] == -15


def test_daily_leaderboard_orders_by_points_desc():
    discipline.record_daily_grade(1, 999, "2026-03-01", discipline.GRADE_CHALA)
    discipline.record_daily_grade(2, 999, "2026-03-01", discipline.GRADE_ALO)
    discipline.record_daily_grade(3, 999, "2026-03-01", discipline.GRADE_NORMA)

    board = discipline.get_daily_leaderboard("2026-03-01")
    assert [row["employee_id"] for row in board] == [2, 3, 1]


def test_monthly_leaderboard_nets_points_against_penalties():
    _add_rule(5)
    discipline.record_daily_grade(1, 999, "2026-03-01", discipline.GRADE_ALO)
    discipline.record_daily_grade(1, 999, "2026-03-02", discipline.GRADE_ALO)
    discipline.apply_penalty(1, 999, "2026-03-03", 10, 5, comment=None, ai_note=None)

    board = discipline.get_monthly_leaderboard("2026-03")
    assert board == [{"employee_id": 1, "net_score": -4}]  # 3+3 ball - 10 jarima


# ------------------------------------------------------------- penalties --


def test_apply_penalty_invalid_amount_raises():
    _add_rule(5)
    with pytest.raises(ValueError):
        discipline.apply_penalty(1, 999, "2026-03-01", 15, 5, comment=None, ai_note=None)


def test_apply_penalty_unknown_rule_raises():
    with pytest.raises(ValueError):
        discipline.apply_penalty(1, 999, "2026-03-01", 10, 404, comment=None, ai_note=None)


def test_apply_penalty_deducts_bonus_bank_and_records_rule():
    _add_rule(5)
    discipline.adjust_bonus_bank(1, 20, "boshlang'ich", "test", None)

    result = discipline.apply_penalty(1, 999, "2026-03-01", 10, 5, comment="kechikdi", ai_note="AI izohi")

    assert result["bonus_bank_balance"] == 10
    assert result["rule"]["rule_number"] == 5
    assert discipline.get_salary(1)["bonus_bank"] == 10


def test_list_appealable_penalties_only_returns_status_none():
    _add_rule(5)
    result = discipline.apply_penalty(1, 999, "2026-03-01", 10, 5, comment=None, ai_note=None)
    discipline.submit_appeal(result["penalty_id"], "bu adolatsiz", None)

    assert discipline.list_appealable_penalties(1) == []


# ------------------------------------------------------------- appeals --


def test_submit_appeal_sets_pending_status():
    _add_rule(5)
    result = discipline.apply_penalty(1, 999, "2026-03-01", 10, 5, comment=None, ai_note=None)

    appeal = discipline.submit_appeal(result["penalty_id"], "sabab", "voice123")
    assert appeal["appeal_status"] == discipline.APPEAL_PENDING
    assert appeal["appeal_reason"] == "sabab"


def test_submit_appeal_twice_returns_none():
    _add_rule(5)
    result = discipline.apply_penalty(1, 999, "2026-03-01", 10, 5, comment=None, ai_note=None)
    discipline.submit_appeal(result["penalty_id"], "sabab", None)

    assert discipline.submit_appeal(result["penalty_id"], "yana", None) is None


def test_decide_appeal_approved_refunds_bonus_bank():
    _add_rule(5)
    result = discipline.apply_penalty(1, 999, "2026-03-01", 10, 5, comment=None, ai_note=None)
    discipline.submit_appeal(result["penalty_id"], "sabab", None)

    penalty = discipline.decide_appeal(result["penalty_id"], discipline.DECISION_APPROVED, decided_by=1)

    assert penalty["employee_id"] == 1
    assert discipline.get_salary(1)["bonus_bank"] == 0  # -10 jarima + 10 qaytarildi

    # decide_appeal o'zi qaytargan dict yozuv YANGILANISHIDAN OLDIN olingan
    # snapshot (kod shunday yozilgan) — haqiqiy saqlangan holatni bazadan
    # to'g'ridan-to'g'ri tekshiramiz.
    persisted = discipline_repo.get_penalty(result["penalty_id"])
    assert persisted["appeal_status"] == discipline.APPEAL_RESOLVED
    assert persisted["appeal_decision"] == discipline.DECISION_APPROVED


def test_decide_appeal_rejected_does_not_refund():
    _add_rule(5)
    result = discipline.apply_penalty(1, 999, "2026-03-01", 10, 5, comment=None, ai_note=None)
    discipline.submit_appeal(result["penalty_id"], "sabab", None)

    discipline.decide_appeal(result["penalty_id"], discipline.DECISION_REJECTED, decided_by=1)

    assert discipline.get_salary(1)["bonus_bank"] == -10


def test_decide_appeal_invalid_decision_raises():
    _add_rule(5)
    result = discipline.apply_penalty(1, 999, "2026-03-01", 10, 5, comment=None, ai_note=None)
    discipline.submit_appeal(result["penalty_id"], "sabab", None)

    with pytest.raises(ValueError):
        discipline.decide_appeal(result["penalty_id"], "noma'lum", decided_by=1)


def test_decide_appeal_without_pending_appeal_raises():
    _add_rule(5)
    result = discipline.apply_penalty(1, 999, "2026-03-01", 10, 5, comment=None, ai_note=None)

    with pytest.raises(ValueError):
        discipline.decide_appeal(result["penalty_id"], discipline.DECISION_APPROVED, decided_by=1)


def test_decide_appeal_already_resolved_raises():
    _add_rule(5)
    result = discipline.apply_penalty(1, 999, "2026-03-01", 10, 5, comment=None, ai_note=None)
    discipline.submit_appeal(result["penalty_id"], "sabab", None)
    discipline.decide_appeal(result["penalty_id"], discipline.DECISION_REJECTED, decided_by=1)

    with pytest.raises(ValueError):
        discipline.decide_appeal(result["penalty_id"], discipline.DECISION_APPROVED, decided_by=1)


# ---------------------------------------------------------- day closure --


def test_close_day_first_time_succeeds():
    discipline.record_daily_grade(1, 999, "2026-03-01", discipline.GRADE_ALO)
    assert discipline.close_day(999, "2026-03-01", total_employees=1) is True


def test_close_day_twice_is_idempotent():
    discipline.close_day(999, "2026-03-01", total_employees=0)
    assert discipline.close_day(999, "2026-03-01", total_employees=0) is False


def test_get_closure_returns_recorded_counts():
    discipline.record_daily_grade(1, 999, "2026-03-01", discipline.GRADE_ALO)
    discipline.close_day(999, "2026-03-01", total_employees=2)

    closure = discipline.get_closure(999, "2026-03-01")
    assert closure["evaluated_count"] == 1
    assert closure["total_count"] == 2


def test_removed_late_close_penalty_never_deducts_bonus_bank():
    assert discipline.penalize_supervisor_for_late_close(999, "2026-03-01", 40) is False
    assert discipline.get_salary(999)["bonus_bank"] == 0


def test_penalize_supervisor_for_late_close_same_day_is_idempotent():
    discipline.penalize_supervisor_for_late_close(999, "2026-03-01", 40)
    assert discipline.penalize_supervisor_for_late_close(999, "2026-03-01", 40) is False
    assert discipline.get_salary(999)["bonus_bank"] == 0


# ---------------------------------------------- kunlik baho: takror/tuzatish --

from datetime import datetime, timedelta, timezone  # noqa: E402

import company_time  # noqa: E402

_DAY = "2026-10-18"


def _ledger_count(user_id: int) -> int:
    return len(discipline.get_bonus_ledger(user_id, limit=100))


def _history_count(user_id: int, day: str = _DAY) -> int:
    return len(discipline.get_grade_history(user_id, day))


def test_same_grade_twice_changes_nothing_the_second_time():
    first = discipline.record_daily_grade(111, 1, _DAY, discipline.GRADE_ALO)
    second = discipline.record_daily_grade(111, 1, _DAY, discipline.GRADE_ALO)

    assert first.changed is True and first.old_grade_points is None and first.eval_date == _DAY
    assert second.changed is False and second.old_grade_points == 3
    assert discipline.get_salary(111)["bonus_bank"] == 3
    assert _ledger_count(111) == 1 and _history_count(111) == 1


def test_correction_keeps_history_and_applies_only_the_delta():
    discipline.record_daily_grade(111, 1, _DAY, discipline.GRADE_ALO)
    result = discipline.record_daily_grade(111, 1, _DAY, discipline.GRADE_NORMA)

    assert result.changed and (result.old_grade_points, result.grade_points) == (3, 2)
    assert discipline.get_daily_grade(111, _DAY)["grade_points"] == 2
    assert discipline.get_salary(111)["bonus_bank"] == 2
    assert [row["grade_points"] for row in discipline.get_grade_history(111, _DAY)] == [3, 2]


def test_zero_grade_is_saved_recorded_and_not_repeated():
    first = discipline.record_daily_grade(111, 1, _DAY, discipline.GRADE_BAJARILMAGAN)
    again = discipline.record_daily_grade(111, 1, _DAY, discipline.GRADE_BAJARILMAGAN)

    assert first.changed is True and first.grade_points == 0
    assert again.changed is False
    assert discipline.get_daily_grade(111, _DAY)["grade_points"] == 0  # 0 "baho yo'q" emas
    assert _history_count(111) == 1 and _ledger_count(111) == 0  # delta 0 — ledger yozuvi yo'q


def test_correction_three_to_zero():
    discipline.record_daily_grade(111, 1, _DAY, discipline.GRADE_ALO)
    result = discipline.record_daily_grade(111, 1, _DAY, discipline.GRADE_BAJARILMAGAN)

    assert result.changed and (result.old_grade_points, result.grade_points) == (3, 0)
    assert discipline.get_salary(111)["bonus_bank"] == 0
    assert discipline.get_daily_grade(111, _DAY)["grade_points"] == 0


def test_save_is_won_by_exactly_one_of_two_identical_attempts():
    first = discipline_repo.save_daily_grade(111, 1, _DAY, "alo", 3, "sinov")
    second = discipline_repo.save_daily_grade(111, 1, _DAY, "alo", 3, "sinov")

    assert (first["changed"], second["changed"]) == (True, False)
    assert first["balance"] == 3 and second["balance"] is None


def test_grade_correction_is_not_a_disciplinary_minus():
    discipline.record_daily_grade(111, 1, _DAY, discipline.GRADE_ALO)
    assert _totals(111) == {"bonus": 3, "minus": 0, "net": 3}

    discipline.record_daily_grade(111, 1, _DAY, discipline.GRADE_NORMA)

    assert _totals(111) == {"bonus": 2, "minus": 0, "net": 2}


def test_real_minus_and_other_bonus_are_kept_next_to_a_correction():
    today = company_time.today().isoformat()  # boshqa ledger yozuvlari yozilgan oyida (hozir) hisoblanadi
    month = today[:7]
    discipline.record_daily_grade(111, 1, today, discipline.GRADE_ALO)
    discipline.record_daily_grade(111, 1, today, discipline.GRADE_NORMA)
    discipline.adjust_bonus_bank(111, -1, "nizom", "penalty", 1)  # haqiqiy intizomiy minus
    discipline.adjust_bonus_bank(111, 4, "boshqa bonus", "other_bonus", None)

    assert _totals(111, month) == {"bonus": 6, "minus": 1, "net": 5}
    assert _totals(111, "2000-01") == {"bonus": 0, "minus": 0, "net": 0}  # boshqa oyga aralashmaydi


def _totals(user_id: int, year_month: str = _DAY[:7]) -> dict:
    totals = discipline.get_period_point_totals(user_id, year_month)
    return {"bonus": totals["bonus"], "minus": totals["minus"], "net": totals["net"]}


def test_notice_text_for_new_grade_and_correction(monkeypatch):
    _freeze_now(monkeypatch, 2026, 10, 19, 12)  # joriy oy = baho oyi -> "Shu oy"
    new = discipline.record_daily_grade(111, 1, _DAY, discipline.GRADE_ALO)
    text = discipline.format_grade_notice(new, {"period_key": "2026-10", "bonus": 3, "minus": 0, "net": 3})
    assert text == (
        "📅 Sana: 18.10.2026\n⭐ Baho: 3 — A'lo\nShu oy bonus: 3\nShu oy minus: 0\nShu oy jami: 3"
    )

    fixed = discipline.record_daily_grade(111, 1, _DAY, discipline.GRADE_NORMA)
    text = discipline.format_grade_notice(fixed, {"period_key": "2026-10", "bonus": 2, "minus": 0, "net": 2})
    assert text == (
        "📅 Sana: 18.10.2026\n✏️ Tuzatildi: 3 → 2\nShu oy bonus: 2\nShu oy minus: 0\nShu oy jami: 2"
    )
    assert "⭐ Baho" not in text


@pytest.mark.parametrize(
    "hour, minute, quiet",
    [(21, 59, False), (22, 0, True), (23, 30, True), (0, 0, True), (6, 59, True), (7, 0, False), (12, 0, False)],
)
def test_quiet_hours_boundaries(hour, minute, quiet):
    assert discipline.is_quiet_time(datetime(2026, 10, 18, hour, minute)) is quiet


# ----------------------------------------- bitta baholash = bitta tranzaksiya --

import sqlite3  # noqa: E402

from tests import db_fail  # noqa: E402
from concurrent.futures import ThreadPoolExecutor  # noqa: E402

from db import get_connection  # noqa: E402


def _ddl(sql: str) -> None:
    conn = get_connection()
    try:
        conn.execute(sql)
        conn.commit()
    finally:
        conn.close()


def _break_inserts_into(table: str) -> None:
    """Haqiqiy DB darajasida shu jadvalga INSERT paytida xato (tranzaksiya ICHIDAGI yozuv bosqichida).
    SQLite va Postgres ikkalasida ishlaydi (qarang ``tests/db_fail.py``)."""
    db_fail.break_writes(table, "INSERT", name=f"break_{table}", message="sinov: yozuv xatosi")


def _repair(table: str) -> None:
    db_fail.repair(table, name=f"break_{table}")


def _state(user_id: int = 111) -> dict:
    conn = get_connection()
    try:
        evaluation = conn.execute(
            "SELECT grade_key, grade_points FROM daily_evaluations WHERE employee_id = ? AND eval_date = ?",
            (user_id, _DAY),
        ).fetchone()
        salary = conn.execute("SELECT bonus_bank FROM salaries WHERE user_id = ?", (user_id,)).fetchone()
        history = [r["grade_points"] for r in conn.execute(
            "SELECT grade_points FROM daily_evaluation_history WHERE employee_id = ? ORDER BY id", (user_id,)
        ).fetchall()]
        ledger = [r["change_amount"] for r in conn.execute(
            "SELECT change_amount FROM bonus_bank_ledger WHERE user_id = ? ORDER BY id", (user_id,)
        ).fetchall()]
    finally:
        conn.close()
    return {
        "grade": (evaluation["grade_key"], evaluation["grade_points"]) if evaluation else None,
        "balance": salary["bonus_bank"] if salary else None,
        "history": history,
        "ledger": ledger,
    }


@pytest.mark.parametrize("failing_table", ["daily_evaluation_history", "bonus_bank_ledger"])
def test_first_grade_failure_leaves_nothing_half_written_and_retry_succeeds_once(failing_table):
    _break_inserts_into(failing_table)

    with pytest.raises(db_fail.WRITE_ERROR):
        discipline.record_daily_grade(111, 1, _DAY, discipline.GRADE_ALO)

    assert _state() == {"grade": None, "balance": None, "history": [], "ledger": []}  # hech biri yarim qolmagan

    _repair(failing_table)
    result = discipline.record_daily_grade(111, 1, _DAY, discipline.GRADE_ALO)  # qayta bosish

    assert result.changed is True and result.bonus_bank_balance == 3
    assert _state() == {"grade": ("alo", 3), "balance": 3, "history": [3], "ledger": [3]}
    assert discipline.record_daily_grade(111, 1, _DAY, discipline.GRADE_ALO).changed is False  # endi haqiqatan takror


def test_salary_write_failure_rolls_back_evaluation_and_history_too():
    db_fail.break_writes("salaries", "INSERT", name="break_salaries", message="sinov: balans xatosi")

    with pytest.raises(db_fail.WRITE_ERROR):
        discipline.record_daily_grade(111, 1, _DAY, discipline.GRADE_ALO)

    assert _state() == {"grade": None, "balance": None, "history": [], "ledger": []}
    db_fail.repair("salaries", name="break_salaries")
    discipline.record_daily_grade(111, 1, _DAY, discipline.GRADE_ALO)
    assert _state() == {"grade": ("alo", 3), "balance": 3, "history": [3], "ledger": [3]}


@pytest.mark.parametrize("failing_table", ["bonus_bank_ledger", "daily_evaluation_history"])
def test_failed_correction_keeps_old_grade_balance_and_history_and_retry_has_no_fake_minus(failing_table):
    discipline.record_daily_grade(111, 1, _DAY, discipline.GRADE_ALO)
    before = _state()
    _break_inserts_into(failing_table)

    with pytest.raises(db_fail.WRITE_ERROR):
        discipline.record_daily_grade(111, 1, _DAY, discipline.GRADE_NORMA)  # 3 -> 2

    assert _state() == before == {"grade": ("alo", 3), "balance": 3, "history": [3], "ledger": [3]}

    _repair(failing_table)
    result = discipline.record_daily_grade(111, 1, _DAY, discipline.GRADE_NORMA)

    assert result.changed and (result.old_grade_points, result.grade_points) == (3, 2)
    assert _state() == {"grade": ("norma", 2), "balance": 2, "history": [3, 2], "ledger": [3, -1]}
    totals = discipline.get_period_point_totals(111)
    assert (totals["bonus"], totals["minus"], totals["net"]) == (2, 0, 2)  # soxta intizomiy minus yo'q


def test_parallel_identical_grades_apply_exactly_one_change(tmp_path):
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(
            lambda _: discipline.record_daily_grade(111, 1, _DAY, discipline.GRADE_ALO), range(6)
        ))

    assert sum(1 for r in results if r.changed) == 1
    assert _state() == {"grade": ("alo", 3), "balance": 3, "history": [3], "ledger": [3]}


def test_parallel_balance_updates_do_not_lose_each_other():
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(lambda i: discipline.adjust_bonus_bank(222, 1, f"sinov {i}", "test", None), range(12)))

    assert discipline.get_salary(222)["bonus_bank"] == 12  # atomik delta: yangilanish yo'qolmagan
    assert len(discipline.get_bonus_ledger(222, limit=100)) == 12


def test_adjust_bonus_bank_keeps_its_contract():
    assert discipline.adjust_bonus_bank(333, 5, "a", "test", None) == 5
    assert discipline.adjust_bonus_bank(333, -2, "b", "test", 9) == 3
    ledger = discipline.get_bonus_ledger(333)
    assert sorted((row["change_amount"], row["balance_after"]) for row in ledger) == [(-2, 3), (5, 5)]


def test_employee_model_has_no_telegram_less_employee_unit_proof():
    """Mavjud model: ``employees.user_id`` — PRIMARY KEY va Telegram ID'ning o'zi; alohida ichki ID yoki
    Telegram bog'lanishi ustuni yo'q. Telegram ID'siz xodimni saqlash/baholash MODELDA QO'LLANMAYDI."""
    columns = db_fail.table_columns("employees")
    conn = get_connection()
    try:
        if db_fail._is_postgres():
            primary_key = {row["name"] for row in conn.execute(
                "SELECT kcu.column_name AS name FROM information_schema.table_constraints tc "
                "JOIN information_schema.key_column_usage kcu "
                "ON tc.constraint_name = kcu.constraint_name AND tc.table_name = kcu.table_name "
                "WHERE tc.table_name = ? AND tc.constraint_type = 'PRIMARY KEY'",
                ("employees",),
            ).fetchall()}
        else:
            primary_key = {row["name"] for row in conn.execute("PRAGMA table_info(employees)").fetchall() if row["pk"]}
    finally:
        conn.close()

    assert primary_key == {"user_id"}
    assert not {"telegram_id", "chat_id", "internal_id", "employee_id"} & columns


# ----------------------------------------- oylik hisob = baho sanasi (eval_date) oyi --


def _freeze_now(monkeypatch, year: int, month: int, day: int, hour: int = 12) -> None:
    fixed = datetime(year, month, day, hour, 0, tzinfo=company_time.resolve_timezone())
    monkeypatch.setattr(company_time, "now", lambda: fixed)


def _month(user_id: int, year_month: str) -> dict:
    return _totals(user_id, year_month)


def test_october_grade_entered_in_october_is_counted_once_in_october(monkeypatch):
    _freeze_now(monkeypatch, 2026, 10, 18)

    discipline.record_daily_grade(111, 1, "2026-10-18", discipline.GRADE_ALO)
    discipline.record_daily_grade(111, 1, "2026-10-18", discipline.GRADE_ALO)  # takror

    assert _month(111, "2026-10") == {"bonus": 3, "minus": 0, "net": 3}
    assert discipline.get_period_point_totals(111)["period_key"] == "2026-10"
    assert discipline.get_period_point_totals(111)["bonus"] == 3


def test_october_grade_entered_in_november_belongs_to_october_not_november(monkeypatch):
    _freeze_now(monkeypatch, 2026, 11, 5)

    discipline.record_daily_grade(111, 1, "2026-10-28", discipline.GRADE_ALO)  # noyabrda kiritilgan oktabr bahosi

    assert _month(111, "2026-10") == {"bonus": 3, "minus": 0, "net": 3}
    assert _month(111, "2026-11") == {"bonus": 0, "minus": 0, "net": 0}
    current = discipline.get_period_point_totals(111)  # joriy oy = noyabr
    assert (current["period_key"], current["bonus"]) == ("2026-11", 0)


def test_correcting_an_october_grade_in_november_changes_only_october(monkeypatch):
    _freeze_now(monkeypatch, 2026, 10, 28)
    discipline.record_daily_grade(111, 1, "2026-10-28", discipline.GRADE_ALO)
    _freeze_now(monkeypatch, 2026, 11, 5)
    discipline.record_daily_grade(111, 1, "2026-11-03", discipline.GRADE_ALO)  # noyabr bahosi

    result = discipline.record_daily_grade(111, 1, "2026-10-28", discipline.GRADE_NORMA)  # 3 -> 2

    assert result.changed and (result.old_grade_points, result.grade_points) == (3, 2)
    assert _month(111, "2026-10") == {"bonus": 2, "minus": 0, "net": 2}  # oktabr kamaydi, soxta minus yo'q
    assert _month(111, "2026-11") == {"bonus": 3, "minus": 0, "net": 3}  # noyabr o'zgarmadi
    # Audit saqlangan: ledger'da tuzatish yozuvi bor (-1), tarix [3, 2].
    assert [row["grade_points"] for row in discipline.get_grade_history(111, "2026-10-28")] == [3, 2]
    assert sorted(row["change_amount"] for row in discipline.get_bonus_ledger(111, 100)) == [-1, 3, 3]


def test_repeating_the_same_old_month_grade_does_not_change_any_month(monkeypatch):
    _freeze_now(monkeypatch, 2026, 11, 5)
    discipline.record_daily_grade(111, 1, "2026-10-28", discipline.GRADE_ALO)

    again = discipline.record_daily_grade(111, 1, "2026-10-28", discipline.GRADE_ALO)

    assert again.changed is False
    assert _month(111, "2026-10") == {"bonus": 3, "minus": 0, "net": 3}
    assert _ledger_count(111) == 1


def test_zero_grade_and_three_to_zero_in_month_totals(monkeypatch):
    _freeze_now(monkeypatch, 2026, 10, 18)
    discipline.record_daily_grade(111, 1, "2026-10-10", discipline.GRADE_BAJARILMAGAN)
    assert _month(111, "2026-10") == {"bonus": 0, "minus": 0, "net": 0}
    assert discipline.record_daily_grade(111, 1, "2026-10-10", discipline.GRADE_BAJARILMAGAN).changed is False

    discipline.record_daily_grade(111, 1, "2026-10-11", discipline.GRADE_ALO)
    assert _month(111, "2026-10")["bonus"] == 3
    discipline.record_daily_grade(111, 1, "2026-10-11", discipline.GRADE_BAJARILMAGAN)  # 3 -> 0

    assert _month(111, "2026-10") == {"bonus": 0, "minus": 0, "net": 0}


def test_two_months_of_one_employee_are_separate():
    discipline.record_daily_grade(111, 1, "2026-09-30", discipline.GRADE_ALO)
    discipline.record_daily_grade(111, 1, "2026-10-01", discipline.GRADE_NORMA)
    discipline.record_daily_grade(111, 1, "2026-10-02", discipline.GRADE_CHALA)

    assert _month(111, "2026-09")["bonus"] == 3
    assert _month(111, "2026-10")["bonus"] == 3  # 2 + 1


def test_two_employees_do_not_mix():
    discipline.record_daily_grade(111, 1, "2026-10-05", discipline.GRADE_ALO)
    discipline.record_daily_grade(222, 1, "2026-10-05", discipline.GRADE_CHALA)

    assert _month(111, "2026-10")["bonus"] == 3
    assert _month(222, "2026-10")["bonus"] == 1
    assert _month(333, "2026-10") == {"bonus": 0, "minus": 0, "net": 0}


def test_december_to_january_boundary():
    discipline.record_daily_grade(111, 1, "2026-12-31", discipline.GRADE_ALO)
    discipline.record_daily_grade(111, 1, "2027-01-01", discipline.GRADE_CHALA)

    assert _month(111, "2026-12")["bonus"] == 3
    assert _month(111, "2027-01")["bonus"] == 1
    assert discipline._month_bounds("2026-12")[:2] == ("2026-12-01", "2027-01-01")  # keyingi yil yanvari


def test_february_regular_and_leap_year_boundaries():
    discipline.record_daily_grade(111, 1, "2027-02-28", discipline.GRADE_ALO)
    discipline.record_daily_grade(111, 1, "2027-03-01", discipline.GRADE_CHALA)
    discipline.record_daily_grade(222, 1, "2028-02-29", discipline.GRADE_ALO)  # kabisa yili
    discipline.record_daily_grade(222, 1, "2028-03-01", discipline.GRADE_CHALA)

    assert _month(111, "2027-02")["bonus"] == 3 and _month(111, "2027-03")["bonus"] == 1
    assert _month(222, "2028-02")["bonus"] == 3 and _month(222, "2028-03")["bonus"] == 1
    assert discipline._month_bounds("2027-02")[1] == "2027-03-01"
    assert discipline._month_bounds("2028-02")[1] == "2028-03-01"


@pytest.mark.parametrize("bad", ["2026-13", "2026-00", "26-10", "2026-1", "", "2026/10", "2026-10-01", "abcd-ef"])
def test_year_month_is_validated(bad):
    with pytest.raises(ValueError):
        discipline.get_period_point_totals(111, bad)


def test_month_boundaries_use_the_company_timezone_for_other_ledger_entries():
    """Boshqa (baho bo'lmagan) yozuvlar ledgerdan o'z created_at oyi bo'yicha, kompaniya (UTC+5) chegarasida."""
    conn = get_connection()
    try:
        for created_at in ("2026-09-30T18:59:59+00:00", "2026-09-30T19:00:00+00:00", "2026-10-31T18:59:59+00:00"):
            conn.execute(
                "INSERT INTO bonus_bank_ledger (user_id, change_amount, balance_after, reason, ref_type, ref_id, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (111, 2, 0, "sinov", "other_bonus", None, created_at),
            )
        conn.commit()
    finally:
        conn.close()

    assert _month(111, "2026-09")["bonus"] == 2  # 23:59:59 Toshkent — sentyabr
    assert _month(111, "2026-10")["bonus"] == 4  # 00:00:00 va 23:59:59 Toshkent — oktabr
    assert _month(111, "2026-11")["bonus"] == 0


def test_grade_ledger_entries_are_never_counted_a_second_time():
    """Kanonik manba daily_evaluations: ledgerdagi daily_evaluation yozuvi (hatto balans bilan) qayta qo'shilmaydi."""
    discipline.record_daily_grade(111, 1, "2026-10-05", discipline.GRADE_ALO)
    discipline.adjust_bonus_bank(111, 100, "tarixiy ledger-only yozuv", "daily_evaluation", None)  # bahosiz yozuv

    assert _month(111, "2026-10") == {"bonus": 3, "minus": 0, "net": 3}  # faqat daily_evaluations'dagi baho
