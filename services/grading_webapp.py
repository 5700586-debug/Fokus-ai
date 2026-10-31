"""📱 Baholash ekrani (Telegram Mini App) — server tomoni mantiqi.

Yangi baholash mantig'i YO'Q: ruxsat (``ACTION_EVALUATE_EMPLOYEE``), kun faolligi, filial yopilgani, takroriy bosish va
tuzatish — hammasi chatdagi bilan bir xil ``discipline.prepare_and_record_grade`` ichida. Sana klientdan OLINMAYDI:
server har so'rovda faol ish kunini o'zi aniqlaydi. Xodimga xabar — ``discipline.notify_employee_of_grade`` (chat bilan
bir xil matn, jim soat). "Bajarilmagan" uchun ixtiyoriy dalil rasmi Mini App'da yuklanmaydi: bot chatda mavjud
``evidence_handlers`` oqimi bilan so'raydi. Minus (nizom) va filial/kun yopish Mini App'da YO'Q — chatda qoladi.
Javoblarda telefon, maosh yoki bonus balansi yo'q.
"""

from __future__ import annotations

import json
import time
from collections import defaultdict, deque
from urllib.parse import parse_qsl

import company_time
import employees
from config import SUPERVISION_BRANCH_NAMES
from repositories import discipline as discipline_repo
from services import discipline, nazoratchi_day, permissions
from services.telegram_webapp import verify_init_data

INIT_DATA_MAX_AGE = 3600
RATE_LIMIT_PER_MINUTE = 30
GRADE_KEYS = (discipline.GRADE_BAJARILMAGAN, discipline.GRADE_CHALA, discipline.GRADE_NORMA, discipline.GRADE_ALO)

_hits: dict[int, deque] = defaultdict(deque)


class WebAppError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def authenticate(init_data: str, bot_token: str, *, now: int | None = None) -> int:
    """Imzo va muddat tekshirilgan initData'dan foydalanuvchi id. Klient yuborgan boshqa id'ga ishonilmaydi."""
    if not verify_init_data(init_data, bot_token, now=now, max_age=INIT_DATA_MAX_AGE):
        raise WebAppError(401, "Sessiya eskirgan — ekranni botdan qayta oching.")
    try:
        user = json.loads(dict(parse_qsl(init_data, keep_blank_values=True)).get("user") or "{}")
        user_id = int(user["id"])
    except (ValueError, TypeError, KeyError):
        raise WebAppError(401, "Sessiya eskirgan — ekranni botdan qayta oching.") from None
    if not permissions.has_permission(user_id, permissions.ACTION_EVALUATE_EMPLOYEE):
        raise WebAppError(403, "Ruxsat yo'q.")
    return user_id


def check_rate(user_id: int, *, now: float | None = None) -> None:
    current = time.monotonic() if now is None else now
    bucket = _hits[user_id]
    while bucket and current - bucket[0] > 60:
        bucket.popleft()
    if len(bucket) >= RATE_LIMIT_PER_MINUTE:
        raise WebAppError(429, "Juda tez — bir oz kuting.")
    bucket.append(current)


def day_payload(supervisor_id: int) -> dict:
    """Faol ish kuni, filiallar va xodimlar holati. Faqat ism, holat va baho kaliti."""
    now = company_time.now()
    day = nazoratchi_day.active_day(supervisor_id, now)
    payload = {
        "work_date": day.work_date,
        "day_closed": day.closed,
        "grades": [{"key": key, "label": discipline.GRADE_LABELS[key]} for key in GRADE_KEYS],
        "branches": [],
    }
    if day.closed:
        return payload
    closed = {
        item["branch"] for item in discipline_repo.list_branch_sessions_up_to(supervisor_id, day.work_date)
        if item["session_date"] == day.work_date and item["status"] == "closed"
    }
    for branch in SUPERVISION_BRANCH_NAMES:
        people = []
        for item in nazoratchi_day.branch_statuses(branch, day.work_date, exclude_user_id=supervisor_id):
            grade = discipline.get_daily_grade(item.profile["user_id"], day.work_date)
            people.append({
                "id": item.profile["user_id"],
                "name": item.name,
                "status": item.status,
                "grade": grade["grade_key"] if grade else None,
            })
        if people:
            payload["branches"].append({"name": branch, "closed": branch in closed, "employees": people})
    return payload


def _visible_to(supervisor_id: int, employee_id: int) -> bool:
    profile = employees.get_profile(employee_id)
    if profile is None:
        return False
    branch = employees.supervision_branch(profile)
    return any(p["user_id"] == employee_id for p in nazoratchi_day.branch_employees(branch, supervisor_id))


async def grade(bot, fsm_storage, supervisor_id: int, employee_id, grade_key) -> dict:
    """Bitta baho. Takroriy so'rov ikkinchi yozuv yaratmaydi (DB: bir xil baho -> ``changed=False``)."""
    if not isinstance(employee_id, int) or isinstance(employee_id, bool) or grade_key not in GRADE_KEYS:
        raise WebAppError(400, "Noto'g'ri so'rov.")
    if not _visible_to(supervisor_id, employee_id):
        raise WebAppError(403, "Bu xodimni baholay olmaysiz.")
    work_date = nazoratchi_day.current_work_date(company_time.now())
    discipline.log_grade_event(employee_id, work_date, "webapp_request", "received")
    prepared = discipline.prepare_and_record_grade(employee_id, supervisor_id, work_date, grade_key)
    if prepared.error:
        raise WebAppError(409, prepared.error)
    result = prepared.result
    outcome = await discipline.notify_employee_of_grade(bot, employee_id, result)
    if grade_key == discipline.GRADE_BAJARILMAGAN and result.changed and fsm_storage is not None:
        await _offer_grade_photo(bot, fsm_storage, supervisor_id, employee_id, work_date)
    return {
        "ok": True,
        "employee_id": employee_id,
        "grade": grade_key,
        "changed": result.changed,
        "message": discipline.grade_notice_reply(outcome),
    }


async def _offer_grade_photo(bot, fsm_storage, supervisor_id: int, employee_id: int, work_date: str) -> None:
    """Chatdagi bilan bir xil ixtiyoriy dalil oqimi: holat nazoratchining shaxsiy chatiga o'rnatiladi."""
    from aiogram.fsm.context import FSMContext
    from aiogram.fsm.storage.base import StorageKey

    import evidence_handlers

    key = StorageKey(bot_id=bot.id, chat_id=supervisor_id, user_id=supervisor_id)
    state = FSMContext(storage=fsm_storage, key=key)
    name = nazoratchi_day.full_name(employees.get_profile(employee_id) or {"user_id": employee_id})
    try:
        await evidence_handlers.request_grade_photo_in_chat(
            bot, supervisor_id, state, employee_id=employee_id, supervisor_id=supervisor_id, eval_date=work_date,
            title=f"❌ {name} — Bajarilmagan (0 ball) saqlandi.",
        )
    except Exception as error:  # noqa: BLE001 - baho saqlangan; rasm taklifi yetmasa baho bekor qilinmaydi
        discipline.log_grade_event(employee_id, work_date, "webapp_photo_offer", "failed", type(error).__name__)
