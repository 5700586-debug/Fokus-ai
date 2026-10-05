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
_MAX_LINE_CHARS = 300


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


def _wrap_items(prefix: str, indent: str, items: list[str], separator: str) -> list[str]:
    """Elementlarni (sabab/ism) ``_MAX_LINE_CHARS`` dan oshmaydigan qatorlarga joylaydi."""
    lines, current, count = [], prefix, 0
    for item in items:
        if count and len(current) + len(separator) + len(item) > _MAX_LINE_CHARS:
            lines.append(current)
            current, count = indent, 0
        current += (separator if count else "") + item
        count += 1
    lines.append(current)
    return lines


def _employee_lines(item: nazoratchi_day.EmployeeStatus, review_date: str) -> list[str]:
    user_id = item.profile["user_id"]

    grade = discipline.get_daily_grade(user_id, review_date)
    work = "qo'yilmagan" if grade is None else _signed_stars(grade["grade_points"])

    time_bonus = time_bonus_repo.get_for_date(user_id, review_date)
    time_text = "tasdiqlanmagan" if time_bonus is None else "✅ berildi"

    penalties = discipline_repo.list_active_penalties_for_date(user_id, review_date)
    minus = f"−{sum(p['amount'] for p in penalties)} ❌" if penalties else "0"

    lines = [f"• {item.name} — vaqt: {time_text}, ish: {work}, minus: {minus}"]
    if penalties:
        reasons = list(dict.fromkeys(_penalty_reason(p) for p in penalties))
        lines += _wrap_items("  Sabab: ", "  ", reasons, "; ")
    return lines


class _Packer:
    """Qatorlarni xabarlarga joylaydi: hech bir xabar ``limit`` dan oshmaydi, xodimning bosh qatori
    (ism + vaqt + ish + minus) hech qachon sabablardan ajralmaydi."""

    def __init__(self, header_lines: list[str], limit: int) -> None:
        self.limit = limit
        self.chunks: list[str] = []
        self.lines = list(header_lines)
        self.has_units = False

    def _fits(self, extra: list[str]) -> bool:
        return len("\n".join(self.lines + extra)) <= self.limit

    def _flush(self) -> None:
        self.chunks.append("\n".join(self.lines).rstrip())
        self.lines, self.has_units = [], False

    def add(self, lines: list[str], keep: int, continuation: str) -> None:
        if self._fits(lines):
            self.lines += lines
        elif self.has_units and len("\n".join(lines)) <= self.limit:
            self._flush()
            self.lines = list(lines)
        else:
            head, rest = lines[:keep], lines[keep:]
            if self.has_units and not self._fits(head):
                self._flush()
            self.lines += head
            for line in rest:
                if not self._fits([line]):
                    self._flush()
                    self.lines = [continuation]
                self.lines.append(line)
        self.has_units = True

    def finish(self) -> list[str]:
        self._flush()
        return self.chunks


def build_close_report(
    branch: str, review_date: str, statuses: list[nazoratchi_day.EmployeeStatus], evaluated: int, total: int
) -> list[str]:
    """Yopilgan filial uchun xabar(lar). Xodim qatori bo'linmaydi; juda ko'p sabab keyingi xabarda
    "<ism> — sabablar davomi" bilan davom etadi."""
    label = date.fromisoformat(review_date).strftime("%d.%m.%Y")
    header = f"✅ {branch} nazorati yopildi\n📅 {label} — baholangan: {evaluated}/{total}"
    packer = _Packer([header, ""], MAX_MESSAGE_CHARS)

    for item in statuses:
        if item.status != nazoratchi_day.STATUS_OFF:
            packer.add(_employee_lines(item, review_date), 1, f"{item.name} — sabablar davomi")

    off_names = [item.name for item in statuses if item.status == nazoratchi_day.STATUS_OFF]
    if off_names:
        packer.add(["", *_wrap_items("Damda: ", "  ", off_names, ", ")], 2, "Damda — davomi:")

    return packer.finish()
