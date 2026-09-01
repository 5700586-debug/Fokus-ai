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


def test_penalize_supervisor_for_late_close_deducts_bonus_bank():
    assert discipline.penalize_supervisor_for_late_close(999, "2026-03-01", 40) is True
    assert discipline.get_salary(999)["bonus_bank"] == -40


def test_penalize_supervisor_for_late_close_same_day_is_idempotent():
    discipline.penalize_supervisor_for_late_close(999, "2026-03-01", 40)
    assert discipline.penalize_supervisor_for_late_close(999, "2026-03-01", 40) is False
    assert discipline.get_salary(999)["bonus_bank"] == -40
