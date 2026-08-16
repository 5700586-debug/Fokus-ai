"""RBAC/xavfsizlik hodisalarini ``security_audit_log``ga yozadi.

Qamrab olingan hodisalar: rol berish/almashtirish, foydalanuvchini
ro'yxatdan o'chirish, nazoratchi tayinlashga urinish (muvaffaqiyatli va
rad etilgan), filiallararo kirishga urinish, muhim ruxsatsiz boshqaruv
amali. Har birida (mavjud bo'lsa) actor, rol, chat, target, eski/yangi
qiymat, sabab, vaqt va so'rov ID saqlanadi. Token/parol/``.env`` qiymati
yoki xodimning shaxsiy ma'lumoti BU YERGA HECH QACHON yozilmaydi — faqat
rol kalitlari, user_id va ozod-matn sabab (masalan filial nomi).

Audit yozuvi ikkinchi darajali amal — DB xatosi asosiy handler oqimini
hech qachon to'xtatmasligi kerak (mavjud loyihadagi "xato bo'lsa ham
asosiy oqim davom etadi" konvensiyasi, qarang ``approval.py``).
"""

import uuid

from repositories import audit as audit_repo

EVENT_ROLE_ASSIGNED = "role_assigned"
EVENT_ROLE_ASSIGN_DENIED = "role_assign_denied"
EVENT_NAZORATCHI_ASSIGN_BLOCKED = "nazoratchi_assign_blocked"
EVENT_USER_REMOVED = "user_removed"
EVENT_CROSS_BRANCH_ATTEMPT = "cross_branch_attempt"
EVENT_UNAUTHORIZED_PRIVILEGED_ACTION = "unauthorized_privileged_action"

# Fokus HR (rekruting) — nomzod arizasi hayot aylanishi va Founder
# qarorlari. ``target_id`` — ariza ID (nomzod Telegram ID emas, PII
# kamaytirish uchun); ``reason``/``new_value``ga nomzod javob matni
# yozilmaydi.
EVENT_RECRUITING_APPLICATION_STARTED = "recruiting_application_started"
EVENT_RECRUITING_APPLICATION_CANCELLED = "recruiting_application_cancelled"
EVENT_RECRUITING_APPLICATION_SUBMITTED = "recruiting_application_submitted"
EVENT_RECRUITING_ASSESSMENT_COMPLETED = "recruiting_assessment_completed"
EVENT_RECRUITING_FOUNDER_DECISION = "recruiting_founder_decision"
EVENT_RECRUITING_DATA_PURGED = "recruiting_data_purged"


def _new_request_id() -> str:
    return uuid.uuid4().hex[:16]


def log_event(
    event_type: str,
    actor_id: int | None = None,
    actor_role: str | None = None,
    chat_id: int | None = None,
    target_id: int | None = None,
    old_value: str | None = None,
    new_value: str | None = None,
    reason: str | None = None,
) -> None:
    try:
        audit_repo.record_event(
            event_type=event_type,
            request_id=_new_request_id(),
            actor_id=actor_id,
            actor_role=actor_role,
            chat_id=chat_id,
            target_id=target_id,
            old_value=old_value,
            new_value=new_value,
            reason=reason,
        )
    except Exception as error:
        print(f"Audit yozuvini saqlab bo'lmadi ({event_type}): {error!r}")
