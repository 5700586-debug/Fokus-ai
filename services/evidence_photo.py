"""S2: Telegram photo evidence for penalties, shared validation before the existing transaction.

Only a Telegram file_id is persisted. Callers must stage pending data in FSM and
wait for a photo before calling apply_pending_penalty.
"""

import employees
from services import discipline, permissions


def apply_pending_penalty(pending: dict, actor_id: int, evidence_file_id: str) -> dict:
    if not isinstance(evidence_file_id, str) or not evidence_file_id.strip():
        raise ValueError("Minus uchun dalil rasmi majburiy.")
    if not isinstance(pending, dict) or pending.get("supervisor_id") != actor_id:
        raise ValueError("Tasdiq eskirgan yoki boshqa nazoratchiga tegishli.")
    employee_id = pending.get("employee_id")
    rule_number = pending.get("rule_number")
    amount = pending.get("amount")
    if not all(isinstance(value, int) and not isinstance(value, bool) for value in (employee_id, rule_number, amount)):
        raise ValueError("Minus ma'lumotlari noto'g'ri.")
    if employees.get_profile(employee_id) is None:
        raise ValueError("Xodim topilmadi.")
    if not permissions.has_permission(actor_id, permissions.ACTION_EVALUATE_EMPLOYEE):
        raise PermissionError("Ball ayirishga ruxsat yo'q.")
    # apply_penalty() itself revalidates the current rule, option, and amount.
    # penalty_date is deliberately unchanged from the originating handler.
    return discipline.apply_penalty(
        employee_id, actor_id, pending["penalty_date"], amount, rule_number,
        pending.get("comment"), pending.get("ai_note"),
        option_id=pending.get("option_id"),
        evidence_file_id=evidence_file_id,
    )
