"""Nazoratchi kunlik tekshiruv oqimi: filial tanlash -> xodimlar holati -> baholash ->
qayta baholash -> hamma KERAKLI xodim baholangach FILIAL sessiyasini yopish.

Sessiya = sana + filial + nazoratchi (``nazoratchi_branch_sessions``). Yopilmagan sessiya
yo'qolmaydi va majburan yopilmaydi. Grafikni nazoratchi emas, filial rahbari kiritadi:
bu yerda grafik faqat O'QILADI (``employee_scheduled_shifts``). Yozuv yo'q kun — NOMA'LUM
("grafik yo'q"): bot ish/dam deb TAXMIN QILMAYDI.

TODO: dam olishga "kim ruxsat berdi" ustuni hozir yo'q — ``employee_scheduled_shifts.created_by``
(grafikni kim yozgan) ko'rsatiladi; alohida "ruxsat bergan" maydoni kerak bo'lsa keyin qo'shiladi.
"""

from dataclasses import dataclass, field

import employees
from repositories import discipline as discipline_repo
from services import attendance as attendance_service
from services import discipline

STATUS_EVALUATED = "evaluated"      # ✅ baholandi
STATUS_PENDING = "pending"          # 🔵 ishda, baholanmagan
STATUS_OFF = "off"                  # 🔴 damda
STATUS_NO_SCHEDULE = "no_schedule"  # ⚠️ grafik yo'q

STATUS_EMOJI = {
    STATUS_EVALUATED: "✅", STATUS_PENDING: "🔵", STATUS_OFF: "🔴", STATUS_NO_SCHEDULE: "⚠️",
}
# Yopishga to'sqinlik qiladigan holatlar: ishdagi baholanmagan va grafik yo'q (baholanmagan).
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
            STATUS_OFF: "damda", STATUS_NO_SCHEDULE: "grafik yo'q",
        }[self.status]
        text = f"{self.emoji} {self.name} — {label}"
        if self.status == STATUS_OFF and self.permitted_by:
            text += f" (Ruxsat: {self.permitted_by})"
        return text


def employee_status(profile: dict, review_date: str) -> EmployeeStatus:
    user_id = profile["user_id"]
    if discipline.get_daily_grade(user_id, review_date) is not None:
        return EmployeeStatus(profile, STATUS_EVALUATED)

    shift = attendance_service.get_shift_for_date(user_id, review_date)
    if shift is None:
        return EmployeeStatus(profile, STATUS_NO_SCHEDULE)  # taxmin qilinmaydi
    if shift.get("status") == "off":
        permitter = None
        created_by = shift.get("created_by")
        if created_by:
            permitter_profile = employees.get_profile(created_by)
            permitter = full_name(permitter_profile) if permitter_profile else None
        return EmployeeStatus(profile, STATUS_OFF, permitter)
    return EmployeeStatus(profile, STATUS_PENDING)


def branch_statuses(branch: str, review_date: str, exclude_user_id: int | None = None) -> list[EmployeeStatus]:
    return [employee_status(profile, review_date) for profile in branch_employees(branch, exclude_user_id)]


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
    """Tanlangan filial sessiyasini yopadi: ishdagi baholanmagan va grafik yo'q (baholanmagan)
    xodimlar qolsa yopmaydi va ro'yxatini qaytaradi; damdagilar to'sqinlik qilmaydi."""
    session = open_session(supervisor_id, branch, review_date)
    if session["status"] == "closed":
        return CloseResult(closed=False, already_closed=True)

    statuses = branch_statuses(branch, review_date, exclude_user_id=supervisor_id)
    blockers = [item for item in statuses if item.status in BLOCKING_STATUSES]
    if blockers:
        return CloseResult(closed=False, blockers=blockers, total=len(statuses))

    evaluated = sum(1 for item in statuses if item.status == STATUS_EVALUATED)
    off_count = sum(1 for item in statuses if item.status == STATUS_OFF)
    if not discipline_repo.close_branch_session(session["id"], evaluated, len(statuses)):
        return CloseResult(closed=False, already_closed=True)

    # Mavjud kunlik yopish belgisi (scheduler "kun yopilmadi" jarimasi uchun) — nazoratchining shu
    # sanadagi BARCHA ochilgan filial sessiyalari yopilgandagina qo'yiladi.
    if not discipline_repo.list_open_branch_sessions(supervisor_id, on_date=review_date):
        discipline.close_day(supervisor_id, review_date, len(statuses))

    return CloseResult(closed=True, evaluated=evaluated, total=len(statuses), off_count=off_count)


def blockers_text(blockers: list[EmployeeStatus]) -> str:
    lines = ["❌ Yopib bo'lmaydi. Hali baholanmaganlar:", ""]
    lines += [f"• {item.line()}" for item in blockers]
    if any(item.status == STATUS_NO_SCHEDULE for item in blockers):
        lines += ["", "⚠️ Grafik yo'q xodimlar: grafikni filial rahbari kiritadi; ishda bo'lsa baholang."]
    return "\n".join(lines)
