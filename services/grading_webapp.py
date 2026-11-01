"""📱 Baholash ekrani (Telegram Mini App) — server tomoni mantiqi.

Yangi baholash mantig'i YO'Q: ruxsat (``ACTION_EVALUATE_EMPLOYEE``), kun faolligi, filial yopilgani, takroriy bosish va
tuzatish — hammasi chatdagi bilan bir xil ``discipline.prepare_and_record_grade`` ichida. Sana klientdan OLINMAYDI:
server har so'rovda faol ish kunini o'zi aniqlaydi. Xodimga xabar — ``discipline.notify_employee_of_grade`` (chat bilan
bir xil matn, jim soat). "Bajarilmagan" uchun ixtiyoriy dalil rasmi Mini App'da yuklanmaydi: bot chatda mavjud
``evidence_handlers`` oqimi bilan so'raydi. Minus (nizom) va filial/kun yopish Mini App'da YO'Q — chatda qoladi.
Javoblarda telefon, maosh yoki bonus balansi yo'q.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections import defaultdict, deque
from urllib.parse import parse_qsl

import company_time
import employees
from config import SUPERVISION_BRANCH_NAMES
from repositories import discipline as discipline_repo
from services import discipline, nazoratchi_day, permissions, work_time
from services.telegram_webapp import verify_init_data

INIT_DATA_MAX_AGE = 3600
RATE_LIMIT_PER_MINUTE = 30
GRADE_KEYS = (discipline.GRADE_BAJARILMAGAN, discipline.GRADE_CHALA, discipline.GRADE_NORMA, discipline.GRADE_ALO)

# Bajarilmagan bahodan keyingi ixtiyoriy dalil rasmi taklifi natijasi (sahifa shunga qarab yozadi).
PHOTO_NOT_NEEDED = "none"
PHOTO_REQUESTED = "requested"
PHOTO_CHAT_BUSY = "chat_busy"
PHOTO_FAILED = "failed"

_hits: dict[int, deque] = defaultdict(deque)
_photo_locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)


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
                "time": time_payload(item.profile["user_id"], day.work_date),
            })
        if people:
            payload["branches"].append({"name": branch, "closed": branch in closed, "employees": people})
    return payload


def _result_payload(result) -> dict:
    return {"status": result.status, "minutes": result.minutes, "time_bonus": result.time_bonus}


def time_payload(employee_id: int, work_date: str) -> dict:
    """Xodimning shu ish kunidagi grafigi, kiritilgan kelish/ketish, versiya va server hisobi (taxminsiz)."""
    from db import get_connection

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM employee_scheduled_shifts WHERE employee_id = ? AND shift_date = ?", (employee_id, work_date)
        ).fetchone()
        shift = dict(row) if row else None
        entry = work_time.get_entry(employee_id, work_date, conn=conn)
        version = work_time.current_version(employee_id, work_date, conn=conn)
    finally:
        conn.close()
    arrival, departure = (entry or {}).get("arrival"), (entry or {}).get("departure")
    payload = {
        "shift": (f"{shift['planned_start']}–{shift['planned_end']}" if shift and shift.get("status") == "work"
                  and shift.get("planned_start") and shift.get("planned_end") else None),
        "day_off": bool(shift and shift.get("status") == "off"),
        "arrival": arrival,
        "departure": departure,
        "version": version,
        "result": None,
    }
    if entry is not None:
        payload["result"] = _result_payload(work_time.compute_day(work_date, shift, arrival, departure))
    return payload


def _closed_guard(supervisor_id: int, employee_id: int, work_date: str):
    """``save_entry`` tranzaksiyasi ICHIDA: kun yoki xodim filiali yopilgan bo'lsa — hech narsa yozilmaydi."""
    branch = employees.supervision_branch(employees.get_profile(employee_id) or {})

    def guard(conn) -> None:
        if conn.execute(
            "SELECT 1 FROM daily_closures WHERE supervisor_id = ? AND closure_date = ?", (supervisor_id, work_date)
        ).fetchone():
            raise work_time.WorkTimeError("Bu ish kuni yopilgan.")
        if conn.execute(
            "SELECT 1 FROM nazoratchi_branch_sessions WHERE supervisor_id = ? AND branch = ? AND session_date = ? "
            "AND status = 'closed'", (supervisor_id, branch, work_date),
        ).fetchone():
            raise work_time.WorkTimeError("Bu filial shu ish kunida yopilgan.")

    return guard


def save_time(supervisor_id: int, employee_id, arrival, departure, expected_version) -> dict:
    """Kelish/ketish (bo'sh maydon — o'zgarmaydi). Sana server ish kuni; eskirgan ekran (versiya farqi) — 409."""
    if not isinstance(employee_id, int) or isinstance(employee_id, bool):
        raise WebAppError(400, "Noto'g'ri so'rov.")
    if expected_version is not None and (not isinstance(expected_version, int) or isinstance(expected_version, bool)):
        raise WebAppError(400, "Noto'g'ri so'rov.")
    if not _visible_to(supervisor_id, employee_id):
        raise WebAppError(403, "Bu xodimni baholay olmaysiz.")
    now = company_time.now()
    status = nazoratchi_day.check_active(supervisor_id, nazoratchi_day.current_work_date(now), now)
    work_date = nazoratchi_day.current_work_date(now)
    if status is not None:
        raise WebAppError(409, "Bu ish kuni yopilgan." if status == "closed" else "Ish kuni eskirgan.")
    try:
        work_time.save_entry(
            employee_id, work_date, arrival, departure, supervisor_id,
            guard=_closed_guard(supervisor_id, employee_id, work_date), expected_version=expected_version,
        )
    except work_time.WorkTimeConflict as error:
        raise WebAppError(409, str(error)) from None
    except work_time.WorkTimeError as error:
        raise WebAppError(409 if "yopilgan" in str(error) else 400, str(error)) from None
    return {"ok": True, "employee_id": employee_id, "time": time_payload(employee_id, work_date)}


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
    photo = PHOTO_NOT_NEEDED
    if grade_key == discipline.GRADE_BAJARILMAGAN and result.changed and fsm_storage is not None:
        photo = await _offer_grade_photo(bot, fsm_storage, supervisor_id, employee_id, work_date)
    return {
        "ok": True,
        "employee_id": employee_id,
        "grade": grade_key,
        "changed": result.changed,
        "message": discipline.grade_notice_reply(outcome),
        "photo": photo,
    }


async def _offer_grade_photo(bot, fsm_storage, supervisor_id: int, employee_id: int, work_date: str) -> str:
    """Chatdagi bilan bir xil ixtiyoriy dalil oqimi: holat nazoratchining shaxsiy chatiga o'rnatiladi.

    Nazoratchi chatda BOSHQA jarayonda bo'lsa (masalan minus rasmi kutilmoqda yoki boshqa xodimning dalili hali
    kutilmoqda) — holatga TEGILMAYDI: u jarayon buzilmaydi va rasm noto'g'ri xodimga bog'lanmaydi. Baho baribir
    saqlangan; dalil ixtiyoriy."""
    from aiogram.fsm.context import FSMContext
    from aiogram.fsm.storage.base import StorageKey

    import evidence_handlers

    key = StorageKey(bot_id=bot.id, chat_id=supervisor_id, user_id=supervisor_id)
    state = FSMContext(storage=fsm_storage, key=key)
    name = nazoratchi_day.full_name(employees.get_profile(employee_id) or {"user_id": employee_id})
    # Bir nazoratchining parallel so'rovlari "tekshir -> o'rnat" orasida bir-birini bosib o'tmasin.
    async with _photo_locks[supervisor_id]:
        if await state.get_state() is not None:
            discipline.log_grade_event(employee_id, work_date, "webapp_photo_offer", "chat_busy")
            return PHOTO_CHAT_BUSY
        try:
            await evidence_handlers.request_grade_photo_in_chat(
                bot, supervisor_id, state, employee_id=employee_id, supervisor_id=supervisor_id, eval_date=work_date,
                title=f"❌ {name} — Bajarilmagan (0 ball) saqlandi.",
            )
        except Exception as error:  # noqa: BLE001 - baho saqlangan; rasm taklifi yetmasa baho bekor qilinmaydi
            discipline.log_grade_event(employee_id, work_date, "webapp_photo_offer", "failed", type(error).__name__)
            # Faqat O'ZIMIZ o'rnatgan kutish holatini tozalaymiz — boshqa jarayonning yangi holatiga tegilmaydi.
            pending = (await state.get_data()).get("grade_pending") or {}
            if (await state.get_state() == evidence_handlers.EvidenceStates.waiting_optional_grade_photo.state
                    and pending.get("employee_id") == employee_id and pending.get("eval_date") == work_date):
                await state.clear()
            return PHOTO_FAILED
    return PHOTO_REQUESTED
