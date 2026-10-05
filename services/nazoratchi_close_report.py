"""Filial nazorati yopilgach nazoratchiga ko'rsatiladigan xodimlar kunlik natijasi.

Faqat O'QIYDI: ish bahosi (``daily_evaluations``), vaqt bonusi (``time_bonus_grants``) va amaldagi
minuslar (``discipline_penalties``, apellyatsiyada bekor qilinganlari chiqarilgan). Yangi ball
yozilmaydi va hisoblash qoidasi yaratilmaydi: vaqt bonusi uchun tizimda ball qiymati saqlanmaydi,
shuning uchun faqat "berildi"/"tasdiqlanmagan" ko'rsatiladi. Pul summalari chiqmaydi."""

from datetime import date

from repositories import discipline as discipline_repo
from repositories import time_bonus as time_bonus_repo
from services import discipline, nazoratchi_day

MAX_MESSAGE_CHARS = 3800
_MAX_REASON_CHARS = 120


def _signed_stars(points: int) -> str:
    if points == 0:
        return "0"
    return f"+{points} ⭐" if points > 0 else f"{points} ⭐"


def _penalty_reason(penalty: dict) -> str:
    reason = (penalty.get("comment") or "").strip()
    if not reason:
        rule = discipline_repo.get_rule_by_number(penalty["rule_number"])
        reason = (rule or {}).get("title") or f"{penalty['rule_number']}-nizom"
    return reason[:_MAX_REASON_CHARS]


def _employee_block(item: nazoratchi_day.EmployeeStatus, review_date: str) -> str:
    user_id = item.profile["user_id"]

    grade = discipline.get_daily_grade(user_id, review_date)
    work = "qo'yilmagan" if grade is None else _signed_stars(grade["grade_points"])

    time_bonus = time_bonus_repo.get_for_date(user_id, review_date)
    time_text = "tasdiqlanmagan" if time_bonus is None else "✅ berildi"

    penalties = discipline_repo.list_active_penalties_for_date(user_id, review_date)
    minus = f"−{sum(p['amount'] for p in penalties)} ❌" if penalties else "0"

    lines = [f"• {item.name} — vaqt: {time_text}, ish: {work}, minus: {minus}"]
    if penalties:
        reasons = "; ".join(dict.fromkeys(_penalty_reason(p) for p in penalties))
        lines.append(f"  Sabab: {reasons}")
    return "\n".join(lines)


def build_close_report(
    branch: str, review_date: str, statuses: list[nazoratchi_day.EmployeeStatus], evaluated: int, total: int
) -> list[str]:
    """Yopilgan filial uchun xabar(lar): xodim qatori hech qachon ikkiga bo'linmaydi."""
    label = date.fromisoformat(review_date).strftime("%d.%m.%Y")
    header = f"✅ {branch} nazorati yopildi\n📅 {label} — baholangan: {evaluated}/{total}"

    units = [
        _employee_block(item, review_date) for item in statuses if item.status != nazoratchi_day.STATUS_OFF
    ]
    off_names = [item.name for item in statuses if item.status == nazoratchi_day.STATUS_OFF]
    if off_names:
        units.append(f"\nDamda: {', '.join(off_names)}")

    chunks: list[str] = []
    current = header + "\n\n"
    has_units = False
    for unit in units:
        if has_units and len(current) + len(unit) + 1 > MAX_MESSAGE_CHARS:
            chunks.append(current.rstrip("\n"))
            current, has_units = "", False
        current += unit + "\n"
        has_units = True
    chunks.append(current.rstrip("\n"))
    return chunks
