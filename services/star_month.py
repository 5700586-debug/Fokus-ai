"""Intizomli xodimlar "zvanyasi" — oylik yulduz hisobi (Muhammadiy qarori, 2026-10-30).

Har oy yulduz yo +1, yo −1 (0..5 oralig'ida). +1 uchun HAMMASI bajarilishi shart:
  1) nizom minusi yo'q (e'tirozda bekor qilingani hisobga olinmaydi; e'tiroz hal bo'lmagan bo'lsa — kutiladi);
  2) "bajarilmagan" (0 ball) baho yo'q va "chala" ko'pi bilan 1 kun (ish bonusi istisnosi);
  3) ishlagan kunlarda vaqt bonusi olinmagan kun ko'pi bilan 1 ta (vaqt bonusi istisnosi);
  4) sababsiz kelmagan kun yo'q va grafik bo'yicha ish kunlari to'liq ishlangan
     (kelishuvdagi oylik ish kunlari, bo'lmasa 26; ruxsatli/fors-major kunlar ayiriladi;
      nazoratchi baholamay qoldirgan filial kunlari xodim foydasiga ishlangan hisoblanadi).
Aks holda −1. Pul summasi guruhda ko'rinmaydi — faqat Founder va xodimning o'ziga.

Yozish faqat Founder TASDIG'IDAN keyin (``apply``) — ``monthly_performance``/``star_history``/``bonus_history``
UNIQUE(user_id, year_month) bilan bir oy ikki marta o'zgarmaydi.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from db import get_connection
from repositories import performance as performance_repo
from services import rules as rules_service
from services import work_time

logger = logging.getLogger(__name__)

# Oktabr — sinov oyi (2026-10-20 qarori): bot hisobi noyabrdan haqiqiy. Birinchi yulduz hisobi 1-dekabrda.
FIRST_MONTH = "2026-11"
DEFAULT_WORK_DAYS = 26
MAX_CHALA = 1
MAX_TIME_MISSES = 1
EXCLUDED_ROLES = frozenset({"nazoratchi", "founder"})
EXCUSED_REASONS = ("manager_permission_approved", "force_majeure")
UNJUSTIFIED_REASONS = ("unjustified", "manager_permission_rejected")

ROOT = Path(__file__).resolve().parent.parent
FONT_REGULAR = ROOT / "assets" / "fonts" / "DejaVuSans.ttf"
FONT_BOLD = ROOT / "assets" / "fonts" / "DejaVuSans-Bold.ttf"
MONTHS = ("Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun", "Iyul", "Avgust", "Sentabr", "Oktabr", "Noyabr", "Dekabr")


@dataclass
class Decision:
    user_id: int
    name: str
    branch: str
    passed: bool = False
    pending: bool = False  # e'tiroz hal bo'lmagan — hozircha qaror yo'q
    reasons: list[str] = field(default_factory=list)
    current_stars: int = 0

    @property
    def new_stars(self) -> int:
        if self.pending:
            return self.current_stars
        return min(self.current_stars + 1, 5) if self.passed else max(self.current_stars - 1, 0)


def month_bounds(year_month: str) -> tuple[str, str]:
    start = date.fromisoformat(f"{year_month}-01")
    end = (start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    return start.isoformat(), end.isoformat()


def previous_month(today: date) -> str:
    return (today.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")


def month_label(year_month: str) -> str:
    return f"{MONTHS[int(year_month[5:7]) - 1]} {year_month[:4]}"


def _rows(conn, sql: str, params: tuple) -> list[dict]:
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def _eligible_employees(conn) -> list[dict]:
    from roles import get_role

    people = _rows(conn, "SELECT user_id, familiya, ism, branch, role_key, photo_file_id FROM employees "
                         "WHERE status = 'approved' ORDER BY familiya, ism, user_id", ())
    return [p for p in people if (get_role(p["user_id"]) or p.get("role_key")) not in EXCLUDED_ROLES]


def evaluate(year_month: str) -> list[Decision]:
    """Faqat O'QIYDI. Har bir xodim uchun +1/−1/kutilmoqda va sabablar."""
    if year_month < FIRST_MONTH:
        return []
    start, end = month_bounds(year_month)
    next_day = (date.fromisoformat(end) + timedelta(days=1)).isoformat()  # ISO vaqtlar uchun aniq yuqori chegara
    conn = get_connection()
    try:
        people = _eligible_employees(conn)
        grades: dict[int, dict] = {}
        for row in _rows(conn, "SELECT employee_id, eval_date, grade_key FROM daily_evaluations "
                               "WHERE eval_date >= ? AND eval_date <= ?", (start, end)):
            grades.setdefault(row["employee_id"], {})[row["eval_date"]] = row["grade_key"]
        penalties: dict[int, list[dict]] = {}
        for row in _rows(conn, "SELECT employee_id, appeal_status FROM discipline_penalties "
                               "WHERE penalty_date >= ? AND penalty_date <= ? "
                               "AND (appeal_decision IS NULL OR appeal_decision != 'approved')", (start, end)):
            penalties.setdefault(row["employee_id"], []).append(row)
        time_days: dict[int, set] = {}
        for row in _rows(conn, "SELECT employee_id, grant_date FROM time_bonus_grants "
                               "WHERE grant_date >= ? AND grant_date <= ?", (start, end)):
            time_days.setdefault(row["employee_id"], set()).add(row["grant_date"])
        arrivals: dict[int, set] = {}
        exact = start >= work_time.ENTRIES_START  # 2026-11 dan: aniq kelish/ketish yagona manba
        complete_days: dict[int, set] = {}
        if exact:
            from services.permanent_schedule import resolved_shift
            shifts = {}
            # Only actual time entries require a schedule; resolve exact date rather than inventing days.
            for row in _rows(conn, "SELECT employee_id, work_date, arrival, departure FROM work_time_entries "
                                   "WHERE work_date >= ? AND work_date <= ?", (start, end)):
                arrivals.setdefault(row["employee_id"], set()).add(row["work_date"])
                result = work_time.compute_day(row["work_date"], resolved_shift(conn, row["employee_id"], row["work_date"]),
                                               row["arrival"], row["departure"])
                if result.status == work_time.STATUS_OK:
                    complete_days.setdefault(row["employee_id"], set()).add(row["work_date"])
        else:
            for row in _rows(conn, "SELECT employee_id, event_time FROM attendance_events WHERE event_type = 'check_in' "
                                   "AND event_time >= ? AND event_time < ?", (start, next_day)):
                arrivals.setdefault(row["employee_id"], set()).add(str(row["event_time"])[:10])
        reasons: dict[int, dict] = {}
        for row in _rows(conn, "SELECT employee_id, event_date, reason_status FROM attendance_reasons "
                               "WHERE event_date >= ? AND event_date <= ?", (start, end)):
            reasons.setdefault(row["employee_id"], {})[row["event_date"]] = row["reason_status"]
        ungraded_branch_days: dict[str, set] = {}
        for row in _rows(conn, "SELECT branch, work_date FROM day_close_notes WHERE work_date >= ? AND work_date <= ?",
                         (start, end)):
            ungraded_branch_days.setdefault(row["branch"], set()).add(row["work_date"])
        agreements = {
            row["employee_id"]: row["work_days"] for row in _rows(
                conn, "SELECT employee_id, work_days FROM salary_agreements WHERE effective_from <= ? "
                      "ORDER BY effective_from, id", (end,),
            ) if row["work_days"]
        }
        stars = {p["user_id"]: performance_repo.get_current_stars(p["user_id"], conn=conn) for p in people}
    finally:
        conn.close()

    decisions = []
    for person in people:
        uid = person["user_id"]
        name = " ".join(part for part in (person.get("familiya"), person.get("ism")) if part) or str(uid)
        decision = Decision(uid, name, person.get("branch") or "—", current_stars=stars.get(uid, 0))
        own_grades = grades.get(uid, {})
        worked = set(own_grades) | arrivals.get(uid, set())
        if not worked and not penalties.get(uid):
            continue  # bu oy umuman ishlamagan/yangi — yulduz o'zgarmaydi
        own_penalties = penalties.get(uid, [])
        incomplete = len(worked - complete_days.get(uid, set())) if exact else 0
        if incomplete:
            # Grafik / kelish-ketish to'liq bo'lmagan kun — shart "bajarildi" deb taxmin qilinmaydi (xodim ham yutqazmaydi).
            decision.pending = True
            decision.reasons.append(f"ma'lumot to'liq emas: {incomplete} kunda grafik yoki kelish/ketish vaqti yo'q")
            decisions.append(decision)
            continue
        if any(p["appeal_status"] == "pending" for p in own_penalties):
            decision.pending = True
            decision.reasons.append("e'tiroz hal bo'lmagan — kutilmoqda")
            decisions.append(decision)
            continue
        if own_penalties:
            decision.reasons.append(f"nizom minusi: {len(own_penalties)} ta")
        values = list(own_grades.values())
        if values.count("bajarilmagan"):
            decision.reasons.append(f"bajarilmagan: {values.count('bajarilmagan')} kun")
        if values.count("chala") > MAX_CHALA:
            decision.reasons.append(f"chala: {values.count('chala')} kun (ruxsat {MAX_CHALA})")
        time_misses = len(worked - time_days.get(uid, set()))
        if time_misses > MAX_TIME_MISSES:
            decision.reasons.append(f"vaqt bonusi yo'q: {time_misses} kun (ruxsat {MAX_TIME_MISSES})")
        own_reasons = reasons.get(uid, {})
        unjustified = sum(1 for status in own_reasons.values() if status in UNJUSTIFIED_REASONS)
        if unjustified:
            decision.reasons.append(f"sababsiz kelmagan: {unjustified} kun")
        # Ruxsatli kun faqat ishlanmagan bo'lsa ayiriladi (ishlangan kun ikki marta hisoblanmasin).
        excused = sum(1 for day, status in own_reasons.items() if status in EXCUSED_REASONS and day not in worked)
        credited = worked | ungraded_branch_days.get(person.get("branch") or "", set())
        required = max(agreements.get(uid, DEFAULT_WORK_DAYS) - excused, 0)
        if len(credited) < required:
            decision.reasons.append(f"ishlagan: {len(credited)} kun (kerak {required})")
        decision.passed = not decision.reasons
        decisions.append(decision)
    return decisions


def apply(year_month: str, decisions: list[Decision]) -> list[Decision]:
    """Founder tasdig'idan keyin yozadi. Allaqachon yozilgan xodim/oy o'tkazib yuboriladi (idempotent).
    Qaytaradi: haqiqatda o'zgargan qarorlar."""
    applied = []
    for decision in decisions:
        if decision.pending:
            continue
        if not performance_repo.try_insert_monthly_performance(
            user_id=decision.user_id, year_month=year_month, avg_supervisor_score=None,
            attendance_ok=not any(r.startswith(("ishlagan", "sababsiz", "vaqt")) for r in decision.reasons),
            no_serious_violation=not any(r.startswith("nizom") for r in decision.reasons),
            checklist_completed=not any(r.startswith(("chala", "bajarilmagan")) for r in decision.reasons),
            full_bonus_month=decision.passed,
        ):
            continue
        previous = performance_repo.get_current_stars(decision.user_id)
        decision.current_stars = previous
        new = decision.new_stars
        reason = "Intizomli oy" if decision.passed else "; ".join(decision.reasons)[:500]
        performance_repo.try_record_star_change(decision.user_id, year_month, previous, new, reason)
        performance_repo.try_record_bonus(decision.user_id, year_month, new, rules_service.get_bonus_for_stars(new))
        applied.append(decision)
    return applied


def preview_text(year_month: str, decisions: list[Decision]) -> str:
    lines = [f"⭐ Yulduzlar — {month_label(year_month)} (hali yozilmagan)"]
    up = [d for d in decisions if d.passed and not d.pending]
    down = [d for d in decisions if not d.passed and not d.pending]
    waiting = [d for d in decisions if d.pending]
    if up:
        lines.append("\n⬆️ +1 yulduz:")
        lines += [f"• {d.name}: {d.current_stars} → {d.new_stars} ⭐" for d in up]
    if down:
        lines.append("\n⬇️ −1 yulduz:")
        lines += [f"• {d.name}: {d.current_stars} → {d.new_stars} ⭐ ({'; '.join(d.reasons)})" for d in down]
    if waiting:
        lines.append("\n⏳ Kutilmoqda:")
        lines += [f"• {d.name} ({'; '.join(d.reasons)})" for d in waiting]
    if not decisions:
        lines.append("Yulduz hisobi noyabr oyidan boshlanadi." if year_month < FIRST_MONTH
                     else "Bu oy hisoblanadigan xodim yo'q.")
    return "\n".join(lines)


def current_board() -> list[dict]:
    """Guruh jadvali uchun: hamma xodimning joriy yulduzi (ko'pi tepada). Pul YO'Q."""
    conn = get_connection()
    try:
        people = _eligible_employees(conn)
        rows = []
        for person in people:
            name = " ".join(part for part in (person.get("familiya"), person.get("ism")) if part) or str(person["user_id"])
            rows.append({
                "user_id": person["user_id"], "name": name, "branch": person.get("branch") or "—",
                "photo_file_id": person.get("photo_file_id"),
                "stars": performance_repo.get_current_stars(person["user_id"], conn=conn),
            })
    finally:
        conn.close()
    return sorted(rows, key=lambda row: (-row["stars"], row["name"]))


# ------------------------------------------------------------------ rasm --

_W, _PAD, _ROW = 1080, 48, 112
_BG, _CARD, _INK, _MUTED, _LINE = (244, 246, 250), (255, 255, 255), (24, 32, 48), (110, 120, 140), (228, 232, 240)
_GOLD, _OFF = (245, 180, 0), (210, 214, 222)


def _font(size: int, bold: bool = False):
    from PIL import ImageFont

    return ImageFont.truetype(str(FONT_BOLD if bold else FONT_REGULAR), size)


def _star(draw, cx: float, cy: float, r: float, fill) -> None:
    import math

    points = []
    for i in range(10):
        radius = r if i % 2 == 0 else r * 0.45
        angle = math.pi / 2 + i * math.pi / 5
        points.append((cx + radius * math.cos(angle), cy - radius * math.sin(angle)))
    draw.polygon(points, fill=fill)


def _avatar(image, draw, box, photo: bytes | None, name: str) -> None:
    from PIL import Image, ImageDraw, ImageOps

    size = box[2] - box[0]
    if photo:
        try:
            face = ImageOps.fit(Image.open(io.BytesIO(photo)).convert("RGB"), (size, size))
            mask = Image.new("L", (size, size), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)
            image.paste(face, box[:2], mask)
            return
        except Exception:  # noqa: BLE001 - buzilgan rasm: bosh harf bilan davom
            pass
    draw.ellipse(box, fill=(219, 234, 254))
    initials = "".join(part[0] for part in name.split()[:2]).upper() or "?"
    draw.text(((box[0] + box[2]) / 2, (box[1] + box[3]) / 2), initials, font=_font(26, True), fill=(37, 99, 235),
              anchor="mm")


def render_board(rows: list[dict], title: str, photos: dict[int, bytes] | None = None) -> bytes:
    from PIL import Image, ImageDraw

    photos = photos or {}
    height = 200 + _ROW * max(len(rows), 1) + 120
    image = Image.new("RGB", (_W, height), _BG)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, _W, 160), fill=_INK)
    draw.text((_PAD, 34), "INTIZOMLI XODIMLAR", font=_font(24, True), fill=(253, 224, 71))
    draw.text((_PAD, 74), title, font=_font(38, True), fill=(255, 255, 255))
    y = 184
    draw.rounded_rectangle((_PAD - 16, y - 8, _W - _PAD + 16, y + _ROW * max(len(rows), 1) + 8), radius=22,
                           fill=_CARD, outline=_LINE, width=2)
    if not rows:
        draw.text((_PAD + 10, y + 30), "Hali xodimlar yo'q", font=_font(24), fill=_MUTED)
    for index, row in enumerate(rows):
        top = y + index * _ROW
        if index:
            draw.line((_PAD, top, _W - _PAD, top), fill=_LINE, width=2)
        _avatar(image, draw, (_PAD + 6, top + 16, _PAD + 86, top + 96), photos.get(row["user_id"]), row["name"])
        name_font = _font(26, True)
        name = row["name"]
        while draw.textlength(name, font=name_font) > 430 and len(name) > 3:
            name = name[:-2]
        draw.text((_PAD + 108, top + 26), name if name == row["name"] else name + "…", font=name_font, fill=_INK)
        draw.text((_PAD + 108, top + 62), row["branch"], font=_font(18), fill=_MUTED)
        for star in range(5):
            _star(draw, 640 + star * 74, top + _ROW / 2, 28, _GOLD if star < row["stars"] else _OFF)
    draw.text((_PAD, height - 70), "Har oy intizomli ishlagan xodimning bitta yulduzi yonadi.", font=_font(19),
              fill=_MUTED)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


async def download_photos(bot, rows: list[dict]) -> dict[int, bytes]:
    """Telegram file_id → bayt (faqat xotirada, diskka yozilmaydi). Xato bo'lsa — bosh harf."""
    photos = {}
    for row in rows:
        file_id = row.get("photo_file_id")
        if not file_id:
            continue
        try:
            buffer = io.BytesIO()
            await bot.download(file_id, destination=buffer)
            photos[row["user_id"]] = buffer.getvalue()
        except Exception as error:  # noqa: BLE001
            logger.info("Xodim rasmi yuklanmadi: %s", type(error).__name__)
    return photos
