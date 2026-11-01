"""Founder uchun haftalik (har dushanba — o'tgan hafta) va oylik (har oyning 1-kuni — o'tgan oy) hisobot.

Ikki qism: 1) dashboard RASMI (Pillow, faqat o'qiydi — bazaga hech narsa yozmaydi), 2) qisqa AI xulosa
(3–5 muhim gap). AI ishlamasa oddiy qoidaga asoslangan xulosa beriladi — hisobot baribir yetib boradi.

Ma'lumot manbalari (hammasi mavjud jadvallar): ``daily_evaluations`` (baholar, ``eval_date`` = ish kuni),
``discipline_penalties`` (minuslar; e'tiroz qabul qilingan — ``appeal_decision='approved'`` — hisobga olinmaydi),
``day_close_notes`` (baholanmaganlar izohi), ``supervisor_audit`` (nazoratchi +5/−5),
``nazoratchi_branch_sessions`` (filial tashriflari), ``employees`` (ism/filial).
"""

from __future__ import annotations

import io
import logging
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from db import get_connection

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
FONT_REGULAR = ROOT / "assets" / "fonts" / "DejaVuSans.ttf"
FONT_BOLD = ROOT / "assets" / "fonts" / "DejaVuSans-Bold.ttf"

GRADE_ORDER = ("alo", "norma", "chala", "bajarilmagan")
GRADE_NAMES = {"alo": "A'lo", "norma": "Norma", "chala": "Chala", "bajarilmagan": "Bajarilmagan"}
MONTHS = ("Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun", "Iyul", "Avgust", "Sentabr", "Oktabr", "Noyabr", "Dekabr")
_AI_MODEL = "gpt-5-mini"
_AI_TIMEOUT_SECONDS = 8.0  # Founder report AI only; never changes other bot AI calls.


# ------------------------------------------------------------------ davr --


@dataclass(frozen=True)
class Period:
    kind: str  # "week" | "month"
    start: date
    end: date  # shu kun ham kiradi
    prev_start: date
    prev_end: date

    @property
    def title(self) -> str:
        if self.kind == "month":
            return f"Oylik hisobot — {MONTHS[self.start.month - 1]} {self.start.year}"
        return f"Haftalik hisobot — {_ddmm(self.start)}–{_ddmm(self.end)}.{self.end.year}"


def _ddmm(day: date) -> str:
    return day.strftime("%d.%m")


def last_full_period(kind: str, today: date) -> Period:
    """``today`` dan oldingi TO'LIQ davr: hafta = o'tgan dushanba–yakshanba, oy = o'tgan kalendar oy."""
    if kind == "week":
        this_monday = today - timedelta(days=today.weekday())
        start, end = this_monday - timedelta(days=7), this_monday - timedelta(days=1)
        return Period("week", start, end, start - timedelta(days=7), start - timedelta(days=1))
    if kind == "month":
        end = today.replace(day=1) - timedelta(days=1)
        start = end.replace(day=1)
        prev_end = start - timedelta(days=1)
        return Period("month", start, end, prev_end.replace(day=1), prev_end)
    raise ValueError(f"noma'lum davr: {kind}")


# -------------------------------------------------------------- ma'lumot --


@dataclass
class EmployeeRow:
    user_id: int
    name: str
    branch: str
    grades: dict[str, int] = field(default_factory=lambda: {key: 0 for key in GRADE_ORDER})
    points: int = 0
    penalty_count: int = 0
    penalty_points: int = 0

    @property
    def graded_days(self) -> int:
        return sum(self.grades.values())

    @property
    def net(self) -> int:
        return self.points - self.penalty_points

    @property
    def average(self) -> float | None:
        return self.points / self.graded_days if self.graded_days else None


@dataclass
class Totals:
    graded: int = 0
    points: int = 0
    grades: dict[str, int] = field(default_factory=lambda: {key: 0 for key in GRADE_ORDER})
    penalty_count: int = 0
    penalty_points: int = 0
    appeals: int = 0
    ungraded: int = 0

    @property
    def average(self) -> float | None:
        return self.points / self.graded if self.graded else None


@dataclass
class Report:
    period: Period
    totals: Totals
    previous: Totals
    employees: list[EmployeeRow]
    branches: list[dict]
    top_rules: list[dict]
    notes: list[dict]
    supervisor: dict


def _rows(conn, sql: str, params: tuple) -> list[dict]:
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def _totals(conn, start: str, end: str) -> Totals:
    totals = Totals()
    for row in _rows(conn, "SELECT grade_key, COUNT(*) AS n, SUM(grade_points) AS pts FROM daily_evaluations "
                           "WHERE eval_date >= ? AND eval_date <= ? GROUP BY grade_key", (start, end)):
        if row["grade_key"] in totals.grades:
            totals.graded += row["n"]
            totals.points += row["pts"] or 0
            totals.grades[row["grade_key"]] += row["n"]
    for row in _rows(conn, "SELECT COUNT(*) AS n, COALESCE(SUM(amount), 0) AS pts, "
                           "COALESCE(SUM(CASE WHEN appeal_status != 'none' THEN 1 ELSE 0 END), 0) AS appeals "
                           "FROM discipline_penalties WHERE penalty_date >= ? AND penalty_date <= ? "
                           "AND (appeal_decision IS NULL OR appeal_decision != 'approved')", (start, end)):
        totals.penalty_count, totals.penalty_points, totals.appeals = row["n"], row["pts"], row["appeals"]
    for row in _rows(conn, "SELECT COALESCE(SUM(ungraded_count), 0) AS n FROM day_close_notes "
                           "WHERE work_date >= ? AND work_date <= ?", (start, end)):
        totals.ungraded = row["n"]
    return totals


def collect(period: Period) -> Report:
    start, end = period.start.isoformat(), period.end.isoformat()
    conn = get_connection()
    try:
        people = {
            row["user_id"]: row for row in _rows(
                conn, "SELECT user_id, familiya, ism, branch FROM employees", ()
            )
        }

        def employee(user_id: int) -> EmployeeRow:
            person = people.get(user_id) or {}
            name = " ".join(part for part in (person.get("familiya"), person.get("ism")) if part) or str(user_id)
            return EmployeeRow(user_id, name, person.get("branch") or "—")

        rows: dict[int, EmployeeRow] = {}
        for row in _rows(conn, "SELECT employee_id, grade_key, COUNT(*) AS n, SUM(grade_points) AS pts "
                               "FROM daily_evaluations WHERE eval_date >= ? AND eval_date <= ? "
                               "GROUP BY employee_id, grade_key", (start, end)):
            item = rows.setdefault(row["employee_id"], employee(row["employee_id"]))
            if row["grade_key"] in item.grades:  # noma'lum (eski) baho turi o'rtachani buzmasin
                item.grades[row["grade_key"]] += row["n"]
                item.points += row["pts"] or 0
        for row in _rows(conn, "SELECT employee_id, COUNT(*) AS n, SUM(amount) AS pts FROM discipline_penalties "
                               "WHERE penalty_date >= ? AND penalty_date <= ? "
                               "AND (appeal_decision IS NULL OR appeal_decision != 'approved') "
                               "GROUP BY employee_id", (start, end)):
            item = rows.setdefault(row["employee_id"], employee(row["employee_id"]))
            item.penalty_count, item.penalty_points = row["n"], row["pts"] or 0

        top_rules = _rows(
            conn,
            "SELECT p.rule_number, COALESCE(r.title, '') AS title, COUNT(*) AS n, SUM(p.amount) AS pts "
            "FROM discipline_penalties p LEFT JOIN company_rules r ON r.rule_number = p.rule_number "
            "WHERE p.penalty_date >= ? AND p.penalty_date <= ? "
            "AND (p.appeal_decision IS NULL OR p.appeal_decision != 'approved') "
            "GROUP BY p.rule_number, r.title ORDER BY COUNT(*) DESC, SUM(p.amount) DESC LIMIT 3",
            (start, end),
        )
        notes = _rows(conn, "SELECT work_date, branch, ungraded_count, note FROM day_close_notes "
                            "WHERE work_date >= ? AND work_date <= ? ORDER BY work_date", (start, end))
        audits = _rows(conn, "SELECT event_type, COUNT(*) AS n FROM supervisor_audit "
                             "WHERE audit_date >= ? AND audit_date <= ? GROUP BY event_type", (start, end))
        visits = _rows(conn, "SELECT COUNT(DISTINCT session_date) AS days, COUNT(*) AS visits FROM nazoratchi_branch_sessions "
                             "WHERE session_date >= ? AND session_date <= ?", (start, end))
        totals = _totals(conn, start, end)
        previous = _totals(conn, period.prev_start.isoformat(), period.prev_end.isoformat())
    finally:
        conn.close()

    branches: dict[str, dict] = {}
    for item in rows.values():
        branch = branches.setdefault(item.branch, {"branch": item.branch, "graded": 0, "points": 0, "penalty_points": 0})
        branch["graded"] += item.graded_days
        branch["points"] += item.points
        branch["penalty_points"] += item.penalty_points
    for branch in branches.values():
        branch["average"] = branch["points"] / branch["graded"] if branch["graded"] else None

    audit_counts = {row["event_type"]: row["n"] for row in audits}
    visit = visits[0] if visits else {"days": 0, "visits": 0}
    supervisor = {
        "days_in_period": (period.end - period.start).days + 1,
        "visited_days": visit.get("days") or 0,
        "visits": visit.get("visits") or 0,
        "full_close": audit_counts.get("day_full_bonus", 0),
        "auto_close_minus": audit_counts.get("auto_close_minus", 0),
        "notes": len(notes),
    }
    return Report(
        period=period, totals=totals, previous=previous,
        employees=sorted(rows.values(), key=lambda item: (-item.net, item.name)),
        branches=sorted(branches.values(), key=lambda b: -(b["average"] or -1)),
        top_rules=top_rules, notes=notes, supervisor=supervisor,
    )


# ------------------------------------------------------------- xulosa --


def _fmt_avg(value: float | None) -> str:
    return "—" if value is None else f"{value:.2f}".rstrip("0").rstrip(".")


def _delta(now: float | None, before: float | None) -> str:
    if now is None or before is None:
        return ""
    diff = now - before
    if abs(diff) < 0.005:
        return "o'zgarmadi"
    return ("↑ " if diff > 0 else "↓ ") + _fmt_avg(abs(diff))


def fallback_summary(report: Report) -> str:
    """AI ishlamasa: qoidaga asoslangan qisqa xulosa."""
    t, p = report.totals, report.previous
    lines = [f"📊 {report.period.title}"]
    if not t.graded and not t.penalty_count:
        lines.append("• Bu davrda baho ham, minus ham yozilmagan.")
        return "\n".join(lines)
    lines.append(f"• O'rtacha baho: {_fmt_avg(t.average)} (oldingi davr: {_fmt_avg(p.average)}).")
    lines.append(f"• Minuslar: {t.penalty_count} ta, jami {t.penalty_points} ball (oldingi: {p.penalty_count} ta).")
    graded = [e for e in report.employees if e.graded_days]
    if graded:
        lines.append(f"• Eng yaxshi: {graded[0].name} ({graded[0].net} ball).")
        lines.append(f"• Eng orqada: {graded[-1].name} ({graded[-1].net} ball).")
    if t.ungraded:
        lines.append(f"• Baholanmay qolgan holatlar: {t.ungraded} ta — izohlarni ko'ring.")
    if report.supervisor["auto_close_minus"]:
        lines.append(f"• Nazoratchi {report.supervisor['auto_close_minus']} kun kunni o'z vaqtida yopmagan.")
    return "\n".join(lines)


def ai_input(report: Report) -> str:
    """AI uchun ixcham, faqat raqam va izohlar (maosh/telefon kabi shaxsiy ma'lumot YO'Q)."""
    t, p = report.totals, report.previous
    lines = [
        report.period.title,
        f"Baholar: {t.graded} (oldingi {p.graded}); o'rtacha {_fmt_avg(t.average)} (oldingi {_fmt_avg(p.average)}).",
        "Taqsimot: " + ", ".join(f"{GRADE_NAMES[k]} {t.grades[k]}" for k in GRADE_ORDER),
        f"Minuslar: {t.penalty_count} ta / {t.penalty_points} ball (oldingi {p.penalty_count} / {p.penalty_points}); "
        f"e'tirozlar {t.appeals}.",
        f"Baholanmagan holatlar: {t.ungraded}.",
        "Nazoratchi: " + ", ".join(f"{k}={v}" for k, v in report.supervisor.items()),
        "Filiallar: " + "; ".join(
            f"{b['branch']} o'rtacha {_fmt_avg(b['average'])}, minus {b['penalty_points']}" for b in report.branches
        ),
        "Ko'p buzilgan bandlar: " + "; ".join(f"{r['title'] or r['rule_number']} — {r['n']} marta" for r in report.top_rules),
        "Xodimlar (net, baholangan kun, chala+bajarilmagan, minus ball):",
    ]
    for e in report.employees[:40]:
        lines.append(f"- {e.name} ({e.branch}): net {e.net}, {e.graded_days} kun, "
                     f"past {e.grades['chala'] + e.grades['bajarilmagan']}, minus {e.penalty_points}")
    if report.notes:
        lines.append("Nazoratchi izohlari (baholanmaganlar):")
        lines += [f"- {n['work_date']} {n['branch']}: {n['note'][:200]}" for n in report.notes[:30]]
    return "\n".join(lines)


async def ai_summary(client, report: Report) -> str:
    if client is None or (not report.totals.graded and not report.totals.penalty_count):
        return fallback_summary(report)
    try:
        # Scope SDK timeouts/retries to this report only; global OpenAI client unchanged.
        if callable(getattr(client, "with_options", None)):
            client = client.with_options(timeout=_AI_TIMEOUT_SECONDS, max_retries=0)
        response = await client.responses.create(
            model=_AI_MODEL,
            instructions=(
                "Sen Fokus AI direktor yordamchisisan. Do'kon egasiga (Muhammadiy) o'zbek tilida, juda sodda va qisqa "
                "xulosa yoz: birinchi qator sarlavha, keyin 3–5 ta '•' bilan boshlangan gap. Faqat eng muhimi: nima "
                "yaxshilandi/yomonlashdi, kim alohida e'tiborga loyiq (ism bilan), qaysi muammo takrorlanmoqda va "
                "nimaga e'tibor berish kerak (aniq bitta tavsiya). Raqamlarni o'zgartirma, taxmin qilma, nizomni "
                "o'zgartirishni taklif qilma. Jami 900 belgidan oshmasin."
            ),
            input=ai_input(report),
        )
        text = (response.output_text or "").strip()
        return text[:1500] if text else fallback_summary(report)
    except Exception as error:  # noqa: BLE001 - AI xatosi hisobotni to'xtatmaydi
        logger.warning("Davriy hisobot AI xulosasi xatosi: %s", type(error).__name__)
        return fallback_summary(report)


# -------------------------------------------------------------- dashboard --

_W, _PAD = 1080, 48
_BG = (244, 246, 250)
_CARD = (255, 255, 255)
_INK = (24, 32, 48)
_MUTED = (110, 120, 140)
_LINE = (228, 232, 240)
_GOOD = (22, 163, 74)
_BAD = (220, 38, 38)
_ACCENT = (37, 99, 235)
_GRADE_COLORS = {"alo": (22, 163, 74), "norma": (59, 130, 246), "chala": (245, 158, 11), "bajarilmagan": (220, 38, 38)}


def _font(size: int, bold: bool = False):
    from PIL import ImageFont

    return ImageFont.truetype(str(FONT_BOLD if bold else FONT_REGULAR), size)


def _fit(draw, text: str, font, width: int) -> str:
    if draw.textlength(text, font=font) <= width:
        return text
    while text and draw.textlength(text + "…", font=font) > width:
        text = text[:-1]
    return text + "…"


def _card(draw, box, radius: int = 22) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=_CARD, outline=_LINE, width=2)


def render_dashboard(report: Report) -> bytes:
    from PIL import Image, ImageDraw

    t, p = report.totals, report.previous
    graded = [e for e in report.employees if e.graded_days or e.penalty_count]
    top = graded[:5]
    bottom = list(reversed(graded[max(5, len(graded) - 5):]))  # eng yaxshilar bilan takrorlanmaydi
    branch_rows = report.branches[:6]
    # Kartalar balandligi yig'indisi + zaxira; oxirida haqiqiy kontentgacha kesiladi (pastki qism yo'qolmaydi).
    height = (1500 + 64 * max(len(top), 1) + (64 * len(bottom) + 170 if bottom else 0)
              + 58 * max(len(branch_rows), 1) + 300)

    image = Image.new("RGB", (_W, height), _BG)
    draw = ImageDraw.Draw(image)
    y = _PAD

    # Sarlavha
    draw.rounded_rectangle((0, 0, _W, 170), radius=0, fill=_INK)
    draw.text((_PAD, 40), "FOKUS AI", font=_font(26, True), fill=(147, 197, 253))
    draw.text((_PAD, 80), report.period.title, font=_font(40, True), fill=(255, 255, 255))
    y = 200

    # KPI kartalar (2×2)
    kpis = [
        ("O'rtacha baho", _fmt_avg(t.average), _delta(t.average, p.average), (t.average or 0) >= (p.average or 0)),
        ("Baholar soni", str(t.graded), _delta(t.graded, p.graded), t.graded >= p.graded),
        ("Minuslar", f"{t.penalty_count} ta / {t.penalty_points} ball",
         _delta(t.penalty_points, p.penalty_points), t.penalty_points <= p.penalty_points),
        ("Baholanmagan", str(t.ungraded), _delta(t.ungraded, p.ungraded), t.ungraded <= p.ungraded),
    ]
    card_w = (_W - 2 * _PAD - 24) // 2
    for index, (label, value, delta, good) in enumerate(kpis):
        x = _PAD + (index % 2) * (card_w + 24)
        top_y = y + (index // 2) * 164
        _card(draw, (x, top_y, x + card_w, top_y + 144))
        draw.text((x + 28, top_y + 22), label, font=_font(24), fill=_MUTED)
        draw.text((x + 28, top_y + 58), _fit(draw, value, _font(40, True), card_w - 56), font=_font(40, True), fill=_INK)
        if delta:
            color = _MUTED if delta == "o'zgarmadi" else (_GOOD if good else _BAD)
            draw.text((x + 28, top_y + 108), f"{delta}  oldingi davrga nisbatan", font=_font(18), fill=color)
    y += 2 * 164 + 12

    # Baho taqsimoti
    _card(draw, (_PAD, y, _W - _PAD, y + 170))
    draw.text((_PAD + 28, y + 20), "Baholar taqsimoti", font=_font(26, True), fill=_INK)
    bar_x0, bar_x1, bar_y = _PAD + 28, _W - _PAD - 28, y + 66
    if t.graded:
        x = bar_x0
        for key in GRADE_ORDER:
            width = round((bar_x1 - bar_x0) * t.grades[key] / t.graded)
            if width:
                draw.rectangle((x, bar_y, x + width, bar_y + 34), fill=_GRADE_COLORS[key])
                x += width
    else:
        draw.rounded_rectangle((bar_x0, bar_y, bar_x1, bar_y + 34), radius=8, fill=_LINE)
    legend_x = bar_x0
    for key in GRADE_ORDER:
        share = round(100 * t.grades[key] / t.graded) if t.graded else 0
        label = f"{GRADE_NAMES[key]} {t.grades[key]} ({share}%)"
        draw.rounded_rectangle((legend_x, y + 122, legend_x + 18, y + 140), radius=4, fill=_GRADE_COLORS[key])
        draw.text((legend_x + 26, y + 118), label, font=_font(19), fill=_INK)
        legend_x += int(draw.textlength(label, font=_font(19))) + 60
    y += 194

    # Filiallar
    branch_h = 80 + 58 * max(len(branch_rows), 1)
    _card(draw, (_PAD, y, _W - _PAD, y + branch_h))
    draw.text((_PAD + 28, y + 20), "Filiallar — o'rtacha baho (0–3) va minuslar", font=_font(26, True), fill=_INK)
    row_y = y + 72
    if not branch_rows:
        draw.text((_PAD + 28, row_y), "Ma'lumot yo'q", font=_font(22), fill=_MUTED)
    for branch in branch_rows:
        draw.text((_PAD + 28, row_y + 6), _fit(draw, branch["branch"], _font(22), 300), font=_font(22), fill=_INK)
        track = (_PAD + 330, row_y + 8, _W - _PAD - 230, row_y + 34)
        draw.rounded_rectangle(track, radius=13, fill=_LINE)
        if branch["average"] is not None:
            filled = track[0] + round((track[2] - track[0]) * min(branch["average"], 3) / 3)
            draw.rounded_rectangle((track[0], track[1], max(filled, track[0] + 26), track[3]), radius=13, fill=_ACCENT)
        draw.text((_W - _PAD - 205, row_y + 4), _fmt_avg(branch["average"]), font=_font(22, True), fill=_INK)
        minus = branch["penalty_points"]
        draw.text((_W - _PAD - 120, row_y + 4), f"−{minus} ball" if minus else "minus 0",
                  font=_font(18), fill=_BAD if minus else _MUTED)
        row_y += 58
    y += branch_h + 24

    # Xodimlar jadvallari
    def table(title: str, rows: list[EmployeeRow], color) -> None:
        nonlocal y
        h = 120 + 64 * max(len(rows), 1)
        _card(draw, (_PAD, y, _W - _PAD, y + h))
        draw.text((_PAD + 28, y + 20), title, font=_font(26, True), fill=_INK)
        draw.text((_PAD + 28, y + 62), "Xodim", font=_font(18), fill=_MUTED)
        for text, x in (("Kun", 640), ("Minus", 760), ("Ball", 900)):
            draw.text((x, y + 62), text, font=_font(18), fill=_MUTED)
        row_y = y + 96
        if not rows:
            draw.text((_PAD + 28, row_y + 10), "Ma'lumot yo'q", font=_font(22), fill=_MUTED)
        for rank, item in enumerate(rows, 1):
            draw.line((_PAD + 28, row_y, _W - _PAD - 28, row_y), fill=_LINE, width=2)
            draw.ellipse((_PAD + 28, row_y + 14, _PAD + 64, row_y + 50), fill=color)
            draw.text((_PAD + 46, row_y + 32), str(rank), font=_font(18, True), fill=(255, 255, 255), anchor="mm")
            draw.text((_PAD + 80, row_y + 10), _fit(draw, item.name, _font(23, True), 480), font=_font(23, True), fill=_INK)
            draw.text((_PAD + 80, row_y + 38), _fit(draw, item.branch, _font(16), 480), font=_font(16), fill=_MUTED)
            draw.text((640, row_y + 18), str(item.graded_days), font=_font(23), fill=_INK)
            draw.text((760, row_y + 18), f"−{item.penalty_points}" if item.penalty_points else "0", font=_font(23),
                      fill=_BAD if item.penalty_points else _INK)
            draw.text((900, row_y + 18), str(item.net), font=_font(23, True), fill=_INK)
            row_y += 64
        y += h + 24

    table("Eng yaxshi 5 xodim", top, _GOOD)
    if bottom:
        table("E'tibor kerak — eng past 5 xodim", bottom, _BAD)

    # Nazoratchi
    s = report.supervisor
    _card(draw, (_PAD, y, _W - _PAD, y + 150))
    draw.text((_PAD + 28, y + 20), "Nazoratchi", font=_font(26, True), fill=_INK)
    facts = [
        (f"{s['visited_days']}/{s['days_in_period']}", "kun ishladi"),
        (str(s["full_close"]), "to'liq yopilgan (+5)"),
        (str(s["auto_close_minus"]), "yopilmagan (−5)"),
        (str(s["notes"]), "izoh yozilgan"),
    ]
    col_w = (_W - 2 * _PAD - 56) // 4
    for index, (value, label) in enumerate(facts):
        x = _PAD + 28 + index * col_w
        draw.text((x, y + 66), value, font=_font(34, True), fill=_INK)
        draw.text((x, y + 110), label, font=_font(17), fill=_MUTED)
    y += 174

    draw.text((_PAD, y), "Ball: A'lo 3 · Norma 2 · Chala 1 · Bajarilmagan 0; minus ayiriladi.", font=_font(17), fill=_MUTED)
    draw.text((_PAD, y + 26), "E'tirozda bekor qilingan minuslar hisobga olinmagan.", font=_font(17), fill=_MUTED)
    y += 26
    image = image.crop((0, 0, _W, min(height, y + 50)))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


# --------------------------------------------------------------- yuborish --


async def send_report(bot, client, kind: str, chat_id: int, today: date) -> None:
    """Parallel AI + unchanged PNG; bounded AI wait, with private stage timings."""
    import asyncio

    from aiogram.types import BufferedInputFile

    started = time.perf_counter()
    timings = {"collect": -1, "ai": -1, "render": -1, "telegram": -1}
    outcome, image_status, ai_status = "error", "not_started", "not_started"
    try:
        period = last_full_period(kind, today)
        t = time.perf_counter()
        try:
            report = await asyncio.to_thread(collect, period)
        finally:
            timings["collect"] = round((time.perf_counter() - t) * 1000)

        async def make_summary() -> str:
            nonlocal ai_status
            t0 = time.perf_counter()
            try:
                # Hard wall-clock deadline even if an injected/non-SDK client hangs.
                try:
                    result = await asyncio.wait_for(
                        ai_summary(client, report), timeout=_AI_TIMEOUT_SECONDS
                    )
                    ai_status = ("returned_or_fallback" if client is not None and
                                 (report.totals.graded or report.totals.penalty_count) else "skipped")
                    return result
                except asyncio.TimeoutError:
                    ai_status = "timeout_fallback"
                    logger.warning("Founder report AI timed out; using rule-based summary")
                    return fallback_summary(report)
            finally:
                timings["ai"] = round((time.perf_counter() - t0) * 1000)

        async def make_image() -> bytes | None:
            nonlocal image_status
            t0 = time.perf_counter()
            try:
                try:
                    result = await asyncio.to_thread(render_dashboard, report)
                    image_status = "ok"
                    return result
                except Exception as error:  # noqa: BLE001 - image failure must not lose report
                    image_status = "fallback"
                    logger.warning("Dashboard rasmi chizilmadi: %s", type(error).__name__)
                    return None
            finally:
                timings["render"] = round((time.perf_counter() - t0) * 1000)

        # These operations use only the already-collected report and do not mutate DB.
        summary, png = await asyncio.gather(make_summary(), make_image())

        t = time.perf_counter()
        try:
            if png and len(summary) <= 1024:
                await bot.send_photo(chat_id, BufferedInputFile(png, filename=f"{kind}-{period.start}.png"), caption=summary)
            elif png:
                await bot.send_photo(chat_id, BufferedInputFile(png, filename=f"{kind}-{period.start}.png"))
                await bot.send_message(chat_id, summary)
            else:
                await bot.send_message(chat_id, summary)
        finally:
            timings["telegram"] = round((time.perf_counter() - t) * 1000)
        outcome = "ok"
    finally:
        # No names, IDs, report contents, API keys, exception texts or prompts.
        # Instrumentation must never change the result of the real handler.
        try:
            print(
                "FOUNDER_REPORT_TIMING "
                f"kind={kind if kind in ('week', 'month') else 'unknown'} "
                f"collect_ms={timings['collect']} ai_ms={timings['ai']} "
                f"render_ms={timings['render']} telegram_ms={timings['telegram']} "
                f"total_ms={round((time.perf_counter() - started) * 1000)} "
                f"ai_status={ai_status} image_status={image_status} outcome={outcome}",
                flush=True,
            )
        except Exception:  # noqa: BLE001 - never let metrics break a report
            pass
