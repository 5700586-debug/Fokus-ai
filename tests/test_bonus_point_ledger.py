"""Bonus/Minus BALL tizimi — mavjud ``bonus_bank_ledger``dan (jarima va
kunlik baho allaqachon shu ledgerga yozadi) davr bo'yicha Bonus/Minus/
Jami hisoblash. Yangi jadval YARATILMAGAN — faqat mavjud ledgerni davr
bo'yicha filtrlaydigan o'qish qatlami (qarang
``repositories/discipline.py::get_bonus_ledger_totals_since`` va
``services/discipline.py::get_period_point_totals``)."""

from repositories import discipline as discipline_repo
from services import discipline

_USER_ID = 810001


def test_bonus_and_minus_accumulate_separately():
    discipline_repo.adjust_bonus_bank(_USER_ID, 30, "test bonus", "test", None)
    discipline_repo.adjust_bonus_bank(_USER_ID, 20, "test bonus 2", "test", None)
    discipline_repo.adjust_bonus_bank(_USER_ID, -15, "test minus", "test", None)

    totals = discipline_repo.get_bonus_ledger_totals_since(_USER_ID, "1970-01-01T00:00:00+00:00")

    assert totals["bonus"] == 50
    assert totals["minus"] == 15
    assert totals["net"] == 35


def test_net_equals_bonus_minus_minus():
    discipline_repo.adjust_bonus_bank(_USER_ID, 10, "b", "test", None)
    discipline_repo.adjust_bonus_bank(_USER_ID, -4, "m", "test", None)

    totals = discipline_repo.get_bonus_ledger_totals_since(_USER_ID, "1970-01-01T00:00:00+00:00")

    assert totals["net"] == totals["bonus"] - totals["minus"]


def test_totals_since_a_future_boundary_are_zero_but_old_rows_still_exist():
    discipline_repo.adjust_bonus_bank(_USER_ID, 40, "old bonus", "test", None)

    far_future = "2999-01-01T00:00:00+00:00"
    totals = discipline_repo.get_bonus_ledger_totals_since(_USER_ID, far_future)
    assert totals == {"bonus": 0, "minus": 0, "net": 0}

    ledger = discipline_repo.get_bonus_ledger(_USER_ID)
    assert any(row["reason"] == "old bonus" for row in ledger)


def test_get_period_point_totals_reflects_grade_and_penalty():
    employee_id = 810002
    supervisor_id = 810003

    discipline_repo.create_rule(9100, "Test nizomi", "Test uchun", supervisor_id)
    discipline_repo.set_rule_penalty_amount(9100, 20)

    discipline.record_daily_grade(employee_id, supervisor_id, "2026-08-25", discipline.GRADE_ALO)
    discipline.apply_penalty(employee_id, supervisor_id, "2026-08-25", 20, 9100, comment=None, ai_note=None)

    totals = discipline.get_period_point_totals(employee_id)

    assert totals["bonus"] >= 3
    assert totals["minus"] >= 20
    assert totals["net"] == totals["bonus"] - totals["minus"]
    assert "period_key" in totals
