"""Oyligim uchun tasdiqlangan hisobning o'qish qatlami: formula, daqiqalar, yetishmagan manbalar, yozmasligi. Vaqtincha DB."""

import db
from config import FOUNDER_ID
from repositories import attendance as attendance_repo
from services import payroll_view as pv
from services import salary_agreement as sa

EMP = 895001
MONTH = "2026-09"  # o'tgan oy (sinov sanasi 2026-10)


def _agreement(token="a1", salary=2_500_000, days=28, minutes=600, date="2026-01-01"):
    return sa.save_agreement(EMP, salary, days, minutes, date, FOUNDER_ID, token, tariff=3).agreement["id"]


def _day(date, start="08:00:00", end="18:00:00"):
    attendance_repo.record_event(EMP, "check_in", f"{date}T{start}+05:00", "test")
    attendance_repo.record_event(EMP, "check_out", f"{date}T{end}+05:00", "test")


def _sql(sql, params=()):
    conn = db.get_connection()
    try:
        conn.execute(sql, params)
        conn.commit()
    finally:
        conn.close()


def _evaluation(date, points):
    _sql(
        "INSERT INTO daily_evaluations (employee_id, supervisor_id, eval_date, grade_key, grade_points, created_at) VALUES (?, 1, ?, 'alo', ?, 'x')",
        (EMP, date, points),
    )


def _penalty(date, amount, decision=None):
    _sql("INSERT OR IGNORE INTO company_rules (rule_number, title, content, is_active, created_by, created_at) VALUES (1, 'Band', 'Matn', 1, 1, 'x')")
    _sql(
        "INSERT INTO discipline_penalties (employee_id, supervisor_id, penalty_date, amount, rule_number, comment, ai_note, "
        "appeal_status, appeal_decision, created_at) VALUES (?, 1, ?, ?, 1, NULL, NULL, 'none', ?, 'x')",
        (EMP, date, amount, decision),
    )


def _count(table):
    conn = db.get_connection()
    try:
        return conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
    finally:
        conn.close()


def _full_month_fixture():
    _agreement()
    for day in range(1, 11):  # 10 kun x 10 soat = 6000 daqiqa
        _day(f"2026-09-{day:02d}")
    _day("2026-09-11", "08:00:00", "08:03:59")  # +3 daqiqa (soniyalar tashlanadi) => 6003 = 100 soat 3 daqiqa
    for day, points in zip(range(1, 15), [3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 1]):
        _evaluation(f"2026-09-{day:02d}", points)  # jami 40
    _penalty("2026-09-05", 5)
    _penalty("2026-09-06", 3, decision="approved")  # apellyatsiyada bekor qilingan — hisobga kirmaydi


# ---------------------------------------------------------------- formula --


def test_confirmed_example_exact():
    result = pv.compute_totals(280 * 60, 2_500_000, 100 * 60 + 3, 40, 5, 6, 50)
    assert result == {"fixed_amount": 893_304, "minus_applied": 5, "total_stars": 91, "total_amount": 1_348_304}


def test_minus_larger_than_work_bonus_only_reduces_work_bonus():
    result = pv.compute_totals(16800, 2_500_000, 16800, 4, 9, 6, 50)
    assert result["minus_applied"] == 4 and result["total_stars"] == 56  # e'tirof va qo'shimcha ish tegilmagan
    assert result["total_amount"] == 2_500_000 + 56 * 5000


def test_missing_inputs_give_none_not_zero():
    base = (16800, 2_500_000, 6003, 40, 5, 6, 50)
    for index in range(7):
        args = list(base)
        args[index] = None
        result = pv.compute_totals(*args)
        assert result["total_amount"] is None, index
    assert pv.compute_totals(16800, 2_500_000, 6003, 40, 5, None, 50)["fixed_amount"] == 893_304
    assert pv.compute_totals(0, 2_500_000, 6003, 40, 5, 6, 50)["fixed_amount"] is None
    assert pv.compute_totals(16800, 2_500_000, 16801, 40, 5, 6, 50)["fixed_amount"] == 2_500_000  # reja oshgan: fiks cheklanadi


# ------------------------------------------------------------------ reader --


def test_month_view_reads_sources_and_leaves_unavailable_ones_empty(temp_db):
    _full_month_fixture()
    view = pv.month_view(EMP, MONTH)
    assert view["plan_minutes"] == 16800 and view["fixed_salary"] == 2_500_000
    assert view["worked_minutes"] == 6003 and view["worked_days"] == 11
    assert view["fixed_amount"] == 893_304
    assert view["work_bonus"] == 40 and view["minus"] == 5 and view["minus_applied"] == 5
    assert view["recognition"] == 0 and view["extra_work"] == 0  # e'tirof = qo'shimcha ish; yozuv yo'q -> 0
    assert view["total_stars"] == 35 and view["total_amount"] == 893_304 + 35 * 5000 and view["complete"] is True
    assert view["final"] is True
    # manbasi bo'lmagan qismlar tashqaridan berilsa, tasdiqlangan misol chiqadi
    full = pv.compute_totals(view["plan_minutes"], view["fixed_salary"], view["worked_minutes"], view["work_bonus"], view["minus"], 6, 50)
    assert full["total_stars"] == 91 and full["total_amount"] == 1_348_304


def test_missing_sources_return_no_data_not_zero(temp_db):
    view = pv.month_view(EMP, MONTH)
    assert view["plan_minutes"] is None and view["worked_minutes"] is None and view["work_bonus"] is None
    assert view["fixed_amount"] is None and view["total_stars"] == 0 and view["total_amount"] is None
    assert view["complete"] is False and "plan" in view["unavailable"] and "worked" in view["unavailable"]
    assert "work_bonus" in view["unavailable"]


def test_agreement_changed_within_month_is_not_guessed(temp_db):
    _agreement("a1", 2_500_000, date="2026-01-01")
    _agreement("a2", 3_000_000, date="2026-09-15")
    _day("2026-09-02")
    view = pv.month_view(EMP, MONTH)
    assert view["plan_minutes"] is None and view["fixed_amount"] is None
    assert any("almashgan" in text for text in view["limitations"])


def test_agreement_effective_before_month_applies_and_future_one_is_ignored(temp_db):
    _agreement("a1", 2_500_000, date="2026-01-01")
    _agreement("a2", 3_000_000, date="2026-10-01")  # keyingi oydan
    _day("2026-09-02")
    view = pv.month_view(EMP, MONTH)
    assert view["fixed_salary"] == 2_500_000 and view["plan_minutes"] == 16800 and not view["limitations"]


def test_legacy_agreement_without_days_or_hours_has_no_plan(temp_db):
    sa.save_legacy_fixed_salary(EMP, 2_500_000, FOUNDER_ID)  # bugundan, kun/soat noma'lum
    view = pv.month_view(EMP, pv.company_time.today().strftime("%Y-%m"))
    assert view["plan_minutes"] is None and view["fixed_amount"] is None and "plan" in view["unavailable"]


def test_worked_over_plan_is_capped_and_incomplete_days_are_flagged(temp_db):
    _agreement(days=1, minutes=60)
    _day("2026-09-02", "08:00:00", "18:00:00")  # 600 > 60 — ortiqcha o'tirish pul emas
    attendance_repo.record_event(EMP, "check_in", "2026-09-03T08:00:00+05:00", "test")  # chiqishsiz kun
    view = pv.month_view(EMP, MONTH)
    assert view["worked_minutes"] == 600 and view["fixed_amount"] == 2_500_000
    assert not any("oshgan" in t for t in view["limitations"]) and any("chiqish yo'q" in t for t in view["limitations"])


def test_future_month_has_no_data(temp_db):
    view = pv.month_view(EMP, "2099-01")
    assert view["worked_minutes"] is None and view["total_amount"] is None and view["complete"] is False


def test_time_bonus_adds_two_points_per_day(temp_db):
    _full_month_fixture()
    for day in ("2026-09-04", "2026-09-05"):
        _sql("INSERT INTO time_bonus_grants (employee_id, grant_date, source, confirmed_by, confirmed_at) VALUES (?, ?, 'auto', NULL, 'x')",
             (EMP, day))
    view = pv.month_view(EMP, MONTH)
    assert view["time_bonus_days"] == 2 and view["time_bonus"] == 4
    assert view["work_bonus"] == 44 and not any("Vaqt bonusi" in t for t in view["limitations"])


def test_time_bonus_alone_is_a_bonus_source(temp_db):
    _agreement()
    _sql("INSERT INTO time_bonus_grants (employee_id, grant_date, source, confirmed_by, confirmed_at) VALUES (?, '2026-09-04', 'manual', 1, 'x')",
         (EMP,))
    assert pv.month_view(EMP, MONTH)["work_bonus"] == 2


def test_extra_work_stars_are_protected_from_minus(temp_db):
    _full_month_fixture()
    _penalty("2026-09-07", 100)  # minus ish bonusidan katta
    _sql("INSERT INTO extra_work_stars (employee_id, work_date, stars, reason, given_by, request_token, created_at) "
         "VALUES (?, '2026-09-08', 6, 'Inventarizatsiyada 2 soat', 1, 't1', 'x')", (EMP,))
    view = pv.month_view(EMP, MONTH)
    assert view["extra_work"] == 6 and view["minus_applied"] == 40
    assert view["total_stars"] == 6 and view["total_amount"] == 893_304 + 6 * 5000


def test_total_shows_even_without_bonus_sources(temp_db):
    _agreement(days=1, minutes=600)
    _day("2026-09-02")
    view = pv.month_view(EMP, MONTH)
    assert view["work_bonus"] is None and "work_bonus" in view["unavailable"]
    assert view["total_amount"] == 2_500_000


def test_read_is_idempotent_writes_nothing_and_ledger_duplicates_do_not_count(temp_db):
    _full_month_fixture()
    for _ in range(3):  # ledger'da takroriy yozuvlar (3 -> 2 tuzatishlari kabi) hisobga qo'shilmaydi
        _sql("INSERT INTO bonus_bank_ledger (user_id, change_amount, balance_after, reason, ref_type, created_at) VALUES (?, 3, 3, 'x', 'daily_evaluation', 'x')", (EMP,))
    tables = ["salary_agreements", "salary_agreement_consents", "attendance_events", "daily_evaluations", "discipline_penalties",
              "bonus_bank_ledger", "salaries", "time_bonus_grants"]
    before = {t: _count(t) for t in tables}
    first = pv.month_view(EMP, MONTH)
    second = pv.month_view(EMP, MONTH)
    assert first == second and {t: _count(t) for t in tables} == before
    assert first["work_bonus"] == 40
