"""Fokus AI DB sxemasi — domen bo'yicha bo'lingan modullar.

Har bir modul o'z domenidagi jadvallarni (va kerak bo'lsa boshlang'ich
seed ma'lumotlarini) bitta SQL string sifatida eksport qiladi. ``db.py``
ularning hammasini ``init_db()`` da ketma-ket bajaradi — bu loyihaning
"migration" mexanizmi: barcha ``CREATE TABLE IF NOT EXISTS`` va
``INSERT OR IGNORE``, shuning uchun qayta ishga tushirish xavfsiz
(idempotent).

Mavjud ``employees`` / ``invites`` / ``employee_contacts`` / ``fsm_storage``
jadvallari ``core.py`` da o'zgarishsiz saqlanadi.
"""

from . import (
    attendance,
    baselines,
    cash_shifts,
    checklists,
    core,
    cross_check,
    discipline,
    inventory,
    market,
    meal_plans,
    notifications,
    performance,
    reports,
    saturn_group,
    suppliers,
    vehicles,
)

SCHEMA_STATEMENTS: list[str] = [
    core.SCHEMA,
    performance.SCHEMA,
    checklists.SCHEMA,
    meal_plans.SCHEMA,
    market.SCHEMA,
    vehicles.SCHEMA,
    reports.SCHEMA,
    cross_check.SCHEMA,
    baselines.SCHEMA,
    notifications.SCHEMA,
    attendance.SCHEMA,
    cash_shifts.SCHEMA,
    inventory.SCHEMA,
    discipline.SCHEMA,
    suppliers.SCHEMA,
    saturn_group.SCHEMA,
]
