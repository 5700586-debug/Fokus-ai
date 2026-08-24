"""Xodimga biriktirilgan doimiy vazifalar/hududlar — minimal xizmat
qatlami. Xodim bu yerda hech narsa bosmaydi ("Bajarildi" tugmasi
yo'q) — vazifalar faqat KO'RSATISH uchun, Nazoratchi haqiqiy joyida
tekshiradi."""

from repositories import tasks as tasks_repo


def get_or_create_task(title: str, created_by: int) -> dict:
    title = title.strip()
    existing = tasks_repo.get_task_by_title(title)
    if existing is not None:
        return existing

    task_id = tasks_repo.create_task(title, created_by)
    return tasks_repo.get_task_by_title(title) or {"id": task_id, "title": title}


def assign_task_to_employee(title: str, employee_id: int, assigned_by: int) -> dict:
    task = get_or_create_task(title, assigned_by)
    tasks_repo.assign_task(task["id"], employee_id, assigned_by)
    return task


def unassign_task_from_employee(title: str, employee_id: int) -> bool:
    task = tasks_repo.get_task_by_title(title.strip())
    if task is None:
        return False
    tasks_repo.unassign_task(task["id"], employee_id)
    return True


def list_tasks_for_employee(employee_id: int) -> list[str]:
    return [row["title"] for row in tasks_repo.list_tasks_for_employee(employee_id)]
