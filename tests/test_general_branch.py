"""Filialga biriktirilmagan xodimlar (haydovchi, ta'minotchi, moliyachi) nazoratchiga virtual "Umumiy (filialsiz)"
bo'limida ko'rinadi; bu bo'lim kunni yopish uchun MAJBURIY EMAS."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

import company_time
import employees
from config import FOUNDER_ID, RECRUITING_BRANCH_NAMES, SUPERVISION_BRANCH_NAMES, SUPERVISION_GENERAL_BRANCH
from db import get_connection
from repositories import discipline as discipline_repo
from services import discipline, nazoratchi_day

NAZ, DRIVER, CASHIER = 1, 801, 802


@pytest.fixture(autouse=True)
def _daytime(monkeypatch):
    fixed = datetime(2026, 11, 3, 12, 0, tzinfo=ZoneInfo("Asia/Tashkent"))
    monkeypatch.setattr(company_time, "now", lambda: fixed)


def _seed():
    from roles import set_role

    set_role(NAZ, "nazoratchi", set_by=FOUNDER_ID)
    set_role(DRIVER, "haydovchi", set_by=FOUNDER_ID)
    conn = get_connection()
    try:
        conn.execute("INSERT INTO employees (user_id, familiya, ism, branch, status) VALUES (?, 'Haydovchi', 'Ali', NULL, 'approved')",
                     (DRIVER,))
        conn.execute("INSERT INTO employees (user_id, familiya, ism, branch, status) VALUES (?, 'Kassir', 'Vali', ?, 'approved')",
                     (CASHIER, RECRUITING_BRANCH_NAMES[0]))
        conn.commit()
    finally:
        conn.close()


def test_general_branch_lists_branchless_staff_only():
    _seed()
    assert SUPERVISION_BRANCH_NAMES[-1] == SUPERVISION_GENERAL_BRANCH
    assert SUPERVISION_GENERAL_BRANCH not in RECRUITING_BRANCH_NAMES
    ids = [p["user_id"] for p in nazoratchi_day.branch_employees(SUPERVISION_GENERAL_BRANCH, NAZ)]
    assert ids == [DRIVER]
    assert employees.supervision_branch(employees.get_profile(DRIVER)) == SUPERVISION_GENERAL_BRANCH
    assert employees.supervision_branch(employees.get_profile(CASHIER)) == RECRUITING_BRANCH_NAMES[0]


def test_general_branch_is_not_required_to_close_the_day():
    _seed()
    assert SUPERVISION_GENERAL_BRANCH not in nazoratchi_day.coverage_branches(NAZ)
    snapshot = nazoratchi_day.read_day_context(NAZ, company_time.now())
    assert SUPERVISION_GENERAL_BRANCH not in snapshot["required_branches"]


def test_grading_branchless_employee_opens_general_session():
    _seed()
    work_date = nazoratchi_day.current_work_date(company_time.now())
    prepared = discipline.prepare_and_record_grade(DRIVER, NAZ, work_date, discipline.GRADE_NORMA)
    assert prepared.result is not None
    sessions = discipline_repo.list_branch_sessions_up_to(NAZ, work_date)
    assert any(s["branch"] == SUPERVISION_GENERAL_BRANCH for s in sessions)
