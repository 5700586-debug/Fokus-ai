"""Nazoratchi kunlik tekshiruv oqimi: filial tanlash -> xodimlar holati -> baholash ->
qayta baholash -> baholanmaganlar qolsa ham FILIAL sessiyasini yopish.

Sessiya = sana + filial + nazoratchi (``nazoratchi_branch_sessions``). Yopilmagan sessiya
tarixi saqlanadi; eski kun yangi ish kunini to'smaydi. Grafikni nazoratchi emas, filial rahbari kiritadi:
bu yerda grafik faqat O'QILADI (``employee_scheduled_shifts``). Yozuv yo'q kun — NOMA'LUM
("grafik yo'q"): bot ish/dam deb TAXMIN QILMAYDI.

TODO: dam olishga "kim ruxsat berdi" ustuni hozir yo'q — ``employee_scheduled_shifts.created_by``
(grafikni kim yozgan) ko'rsatiladi; alohida "ruxsat bergan" maydoni kerak bo'lsa keyin qo'shiladi.
"""

from dataclasses import dataclass, field

from datetime import datetime, time
from zoneinfo import ZoneInfo

import employees
from config import RECRUITING_BRANCH_NAMES
from repositories import discipline as discipline_repo
from services import attendance as attendance_service
from services import day_close_deadline, discipline
from services import rules as rules_service

STATUS_EVALUATED = "evaluated"      # ✅ baholandi
STATUS_PENDING = "pending"          # 🔵 ishda, baholanmagan
STATUS_OFF = "off"                  # 🔴 damda
STATUS_NOT_EVALUATED = "not_evaluated"  # yopilgan kunda baho yozilmagan
STATUS_NO_SCHEDULE = "no_schedule"  # ⚠️ grafik yo'q

STATUS_EMOJI = {
    STATUS_EVALUATED: "✅", STATUS_PENDING: "🔵", STATUS_OFF: "🔴", STATUS_NO_SCHEDULE: "⚠️",
    STATUS_NOT_EVALUATED: "⚪",
}
# Ochiq kun ekranida baholanishi kutilayotganlar; yopishga to'siq emas.
BLOCKING_STATUSES = frozenset({STATUS_PENDING, STATUS_NO_SCHEDULE})
_MANAGEMENT_ROLE_KEYS = frozenset({"founder", "nazoratchi"})


def full_name(profile: dict) -> str:
    return " ".join(part for part in (profile.get("familiya"), profile.get("ism")) if part) or str(profile["user_id"])


def branch_employees(branch: str, exclude_user_id: int | None = None) -> list[dict]:
    """Filialning tasdiqlangan oddiy xodimlari (nazoratchi/Founder va so'rovchining o'zi chiqarilgan)."""
    return [
        profile for profile in employees.list_approved_by_branch(branch)
        if profile.get("role_key") not in _MANAGEMENT_ROLE_KEYS and profile["user_id"] != exclude_user_id
    ]


@dataclass
class EmployeeStatus:
    profile: dict
    status: str
    permitted_by: str | None = None

    @property
    def name(self) -> str:
        return full_name(self.profile)

    @property
    def emoji(self) -> str:
        return STATUS_EMOJI[self.status]

    def line(self) -> str:
        label = {
            STATUS_EVALUATED: "baholandi", STATUS_PENDING: "baholanmagan",
            STATUS_OFF: "damda", STATUS_NO_SCHEDULE: "grafik yo'q", STATUS_NOT_EVALUATED: "baholanmadi",
        }[self.status]
        text = f"{self.emoji} {self.name} — {label}"
        if self.status == STATUS_OFF and self.permitted_by:
            text += f" (Ruxsat: {self.permitted_by})"
        return text


def employee_status(profile: dict, review_date: str, *, closed: bool = False) -> EmployeeStatus:
    user_id = profile["user_id"]
    if discipline.get_daily_grade(user_id, review_date) is not None:
        return EmployeeStatus(profile, STATUS_EVALUATED)

    shift = attendance_service.get_shift_for_date(user_id, review_date)
    if shift is None:
        return EmployeeStatus(profile, STATUS_NOT_EVALUATED if closed else STATUS_NO_SCHEDULE)  # taxmin qilinmaydi
    if shift.get("status") == "off":
        permitter = None
        created_by = shift.get("created_by")
        if created_by:
            permitter_profile = employees.get_profile(created_by)
            permitter = full_name(permitter_profile) if permitter_profile else None
        return EmployeeStatus(profile, STATUS_OFF, permitter)
    return EmployeeStatus(profile, STATUS_NOT_EVALUATED if closed else STATUS_PENDING)


def branch_statuses(branch: str, review_date: str, exclude_user_id: int | None = None, *, closed: bool = False) -> list[EmployeeStatus]:
    return [employee_status(profile, review_date, closed=closed) for profile in branch_employees(branch, exclude_user_id)]


def coverage_branches(supervisor_id: int) -> list[str]:
    """Kun yopilishi uchun tekshirilishi SHART filiallar: mavjud filial ro'yxati (``RECRUITING_BRANCH_NAMES``) dan
    tekshiriladigan xodimi bor filiallar. Xodimi yo'q filial tekshiruv talab qilmaydi; tekshirilmagan filial hech qachon
    yopilgan deb TAXMIN QILINMAYDI."""
    return [branch for branch in RECRUITING_BRANCH_NAMES if branch_employees(branch, supervisor_id)]


def branch_pending_count(branch: str, work_date: str, supervisor_id: int) -> int:
    """"Baholanmagan" = ishda (baholanmagan) + grafik yo'q (baholanmagan). Damdagilar va baholanganlar kirmaydi."""
    return sum(1 for item in branch_statuses(branch, work_date, supervisor_id) if item.status in BLOCKING_STATUSES)


def day_fully_closed(
    supervisor_id: int, work_date: str, sessions: list[dict] | None = None, *, required_branches=None,
) -> bool:
    """Ish kuni FAQAT barcha qamrov filiallari yopilgandagina yopilgan (bitta filial butun kunni yopmaydi)."""
    if sessions is None:
        sessions = discipline_repo.list_branch_sessions_up_to(supervisor_id, work_date)
    closed = {item["branch"] for item in sessions if item["session_date"] == work_date and item["status"] == "closed"}
    required = set(coverage_branches(supervisor_id)) if required_branches is None else required_branches
    if required:
        return required <= closed
    opened = [item for item in sessions if item["session_date"] == work_date]
    return bool(opened) and all(item["status"] == "closed" for item in opened)


@dataclass
class ActiveDay:
    work_date: str
    resumed: bool = False  # oldingi yakunlanmagan kun davom ettirilmoqda
    closed: bool = False   # joriy ish kuni allaqachon yopilgan (qayta ochilmaydi, yangisi hali boshlanmagan)


def current_work_date(now: datetime) -> str:
    """Muhammadiy qarori: 00:00–05:59 oldingi ish kuni; 06:00 dan yangi kun."""
    local = now.astimezone(ZoneInfo("Asia/Tashkent"))
    return day_close_deadline.work_date_at(local, time(6)).isoformat()


def read_day_context(supervisor_id: int, now: datetime) -> dict:
    current = current_work_date(now)
    snapshot = discipline_repo.get_day_review_snapshot(supervisor_id, current, RECRUITING_BRANCH_NAMES)
    return {"current": current, **snapshot}


def active_day(supervisor_id: int, now: datetime, *, snapshot: dict | None = None) -> ActiveDay:
    """Faqat joriy 06:00 ish kuni. Eski ochiq sessiya uni orqaga tortmaydi; yozuv yo'q."""
    current = snapshot["current"] if snapshot is not None else current_work_date(now)
    sessions = snapshot["sessions"] if snapshot is not None else discipline_repo.list_branch_sessions_up_to(supervisor_id, current)
    closed = (current in snapshot["closed_dates"] or day_fully_closed(
        supervisor_id, current, sessions, required_branches=snapshot["required_branches"],
    )) if snapshot is not None else _is_closed_day(supervisor_id, current, sessions)
    return ActiveDay(current, closed=closed)


def _is_closed_day(supervisor_id: int, work_date: str, sessions: list[dict]) -> bool:
    """Yopilgan kun: ``daily_closures`` yozuvi bor (har qanday TARIXIY kun uchun ham — keyin qo'shilgan filial/xodim uni
    qayta ochmaydi) yoki shu kunning barcha qamrov filiallari yopilgan."""
    return discipline.get_closure(supervisor_id, work_date) is not None or day_fully_closed(supervisor_id, work_date, sessions)


def check_active(supervisor_id: int, review_date: str, now: datetime, *, snapshot: dict | None = None) -> str | None:
    """Callback/yozuv uchun himoya: ``None`` — ruxsat; ``"stale"`` — sana faol ish kuni emas (eskirgan/kelajak/boshqa kun);
    ``"closed"`` — faol kun yopilgan. Yopilgan yoki faol bo'lmagan kunga hech narsa yozilmaydi."""
    day = active_day(supervisor_id, now) if snapshot is None else active_day(supervisor_id, now, snapshot=snapshot)
    if day.closed and review_date == day.work_date:
        return "closed"
    if review_date != day.work_date:
        return "stale"
    return None


def open_session(supervisor_id: int, branch: str, review_date: str) -> dict:
    return discipline_repo.open_branch_session(supervisor_id, branch, review_date)


def stale_open_sessions(supervisor_id: int, today: str) -> list[dict]:
    """Oldingi kunlardan yopilmay qolgan filial sessiyalari (har biri alohida)."""
    return discipline_repo.list_open_branch_sessions(supervisor_id, before_date=today)


@dataclass
class CloseResult:
    closed: bool
    already_closed: bool = False
    blockers: list[EmployeeStatus] = field(default_factory=list)
    evaluated: int = 0
    total: int = 0
    off_count: int = 0


def close_session(supervisor_id: int, branch: str, review_date: str) -> CloseResult:
    """Baholanmaganlar ham qolishi mumkin; ularga baho/ball yozilmaydi."""
    session = open_session(supervisor_id, branch, review_date)
    if session["status"] == "closed":
        return CloseResult(closed=False, already_closed=True)
    statuses = branch_statuses(branch, review_date, exclude_user_id=supervisor_id)
    evaluated = sum(1 for item in statuses if item.status == STATUS_EVALUATED)
    off_count = sum(1 for item in statuses if item.status == STATUS_OFF)
    if not discipline_repo.close_branch_session(session["id"], evaluated, len(statuses)):
        return CloseResult(closed=False, already_closed=True)

    # Qo'lda yopishda barcha qamrov filiallari yopilgach kunning o'zi yakunlanadi.
    if day_fully_closed(supervisor_id, review_date):
        discipline.close_day(supervisor_id, review_date, len(statuses))

    return CloseResult(closed=True, evaluated=evaluated, total=len(statuses), off_count=off_count)


def blockers_text(blockers: list[EmployeeStatus]) -> str:
    lines = ["❌ Yopib bo'lmaydi. Hali baholanmaganlar:", ""]
    lines += [f"• {item.line()}" for item in blockers]
    if any(item.status == STATUS_NO_SCHEDULE for item in blockers):
        lines += ["", "⚠️ Grafik yo'q xodimlar: grafikni filial rahbari kiritadi; ishda bo'lsa baholang."]
    return "\n".join(lines)


def ensure_auto_close_policy(now: datetime) -> str:
    return discipline_repo.auto_close_start(current_work_date(now))


def auto_close_expired(now: datetime) -> dict:
    ensure_auto_close_policy(now)
    return discipline_repo.close_expired_review_days(current_work_date(now))


def preview_legacy_close(now: datetime) -> dict:
    return discipline_repo.preview_review_day_closure(current_work_date(now))


def confirm_legacy_close(now: datetime, version: str) -> dict:
    return discipline_repo.close_expired_review_days(current_work_date(now), expected_version=version)
