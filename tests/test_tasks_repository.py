"""VAZIFA + NAZORATCHI + BONUS V1 — 2-bosqich: vazifa biriktirish
repository/service qatlami (``repositories/tasks.py``,
``services/tasks.py``)."""

from repositories import tasks as tasks_repo
from services import tasks as tasks_service


def test_assign_task_to_employee_creates_task_once_by_title():
    task1 = tasks_service.assign_task_to_employee("Ombor", 111, assigned_by=1)
    task2 = tasks_service.assign_task_to_employee("Ombor", 222, assigned_by=1)

    assert task1["id"] == task2["id"]


def test_list_tasks_for_employee_returns_assigned_titles():
    tasks_service.assign_task_to_employee("Suv to'ldirish", 111, assigned_by=1)
    tasks_service.assign_task_to_employee("Kolbasa sovutgichi", 111, assigned_by=1)

    result = tasks_service.list_tasks_for_employee(111)

    assert set(result) == {"Suv to'ldirish", "Kolbasa sovutgichi"}


def test_one_task_can_be_assigned_to_multiple_employees():
    tasks_service.assign_task_to_employee("Ombor", 111, assigned_by=1)
    tasks_service.assign_task_to_employee("Ombor", 222, assigned_by=1)

    assert tasks_service.list_tasks_for_employee(111) == ["Ombor"]
    assert tasks_service.list_tasks_for_employee(222) == ["Ombor"]


def test_assigning_the_same_task_twice_is_a_safe_no_op():
    tasks_service.assign_task_to_employee("Ombor", 111, assigned_by=1)
    tasks_service.assign_task_to_employee("Ombor", 111, assigned_by=2)

    assert tasks_service.list_tasks_for_employee(111) == ["Ombor"]


def test_unassign_task_removes_it_from_employee_card():
    tasks_service.assign_task_to_employee("Ombor", 111, assigned_by=1)
    removed = tasks_service.unassign_task_from_employee("Ombor", 111)

    assert removed is True
    assert tasks_service.list_tasks_for_employee(111) == []


def test_unassign_unknown_task_returns_false():
    assert tasks_service.unassign_task_from_employee("Yo'q vazifa", 111) is False


def test_inactive_task_no_longer_shown_after_unassign_but_task_row_kept():
    tasks_service.assign_task_to_employee("Ombor", 111, assigned_by=1)
    tasks_service.unassign_task_from_employee("Ombor", 111)

    task = tasks_repo.get_task_by_title("Ombor")
    assert task is not None
    assert tasks_repo.list_tasks_for_employee(111) == []
