"""📅 Grafik ekrani (Telegram Mini App) — server tomoni.

Kim nima qila oladi (ChatGPT 2 tur tanqididan keyin kelishilgan):
- Nazoratchi (``ACTION_MANAGE_DAILY_SCHEDULE``) — barcha filial. Boshlangan/o'tgan smena yoki kelish-ketish yozilgan
  kunni ham o'zgartira oladi, lekin SABAB majburiy (tarixda ``is_late_change=1``).
- Filial rahbari (faqat ``ACTION_EDIT_BRANCH_SCHEDULE``) — faqat o'z filiali, faqat BOSHLANMAGAN smenalar; kelish/ketish
  yozilgan kunga va o'tgan kunlarga tegolmaydi. Eski Telegram grafik buyruqlari bu ruxsat bilan OCHILMAYDI.
- Hech kim o'z grafigini o'zgartira olmaydi; yulduz qarori yozilgan oy (``star_history``) — hamma uchun qulflangan.

Saqlash — bitta tranzaksiya: barcha kataklar + tarix + vaqt bonusi qayta hisobi. Bitta katakda xato (eskirgan ekran,
qulf, ruxsat) bo'lsa HECH NARSA yozilmaydi. Sana va "boshlanganmi" — faqat server soatidan.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import company_time
import employees
from config import SUPERVISION_BRANCH_NAMES
from db import get_connection
from repositories import attendance as attendance_repo
from services import attendance, nazoratchi_day, permissions, work_time, permanent_schedule
from services.grading_webapp import WebAppError

MAX_CHANGES = 300
WEEK_RANGE = 8  # joriy haftadan oldinga/orqaga necha hafta ochiladi
WEEKDAYS = ("Du", "Se", "Ch", "Pa", "Ju", "Sh", "Ya")
SOURCE = "mini_app_grafik"

LOCK_STAR = "star"        # yulduz qarori chiqqan oy — hech kim
LOCK_STARTED = "started"  # boshlangan/o'tgan smena yoki kelish-ketish yozilgan kun — faqat nazoratchi, sabab bilan
LOCK_SELF = "self"        # o'z grafigi


def is_full(user_id: int) -> bool:
    return permissions.has_permission(user_id, permissions.ACTION_MANAGE_DAILY_SCHEDULE)


def can_open(user_id: int) -> bool:
    return is_full(user_id) or permissions.has_permission(user_id, permissions.ACTION_EDIT_BRANCH_SCHEDULE)


def visible_branches(user_id: int) -> list[str]:
    if is_full(user_id):
        return list(SUPERVISION_BRANCH_NAMES)
    profile = employees.get_profile(user_id, include_contacts=False) or {}
    branch = profile.get("branch")
    return [branch] if branch and permissions.can_access_branch(user_id, branch) else []


def _week_monday(week_start) -> date:
    today = company_time.today()
    current = today - timedelta(days=today.weekday())
    if week_start in (None, ""):
        return current
    try:
        monday = date.fromisoformat(str(week_start))
    except ValueError:
        raise WebAppError(400, "Noto'g'ri hafta.") from None
    monday -= timedelta(days=monday.weekday())
    if abs((monday - current).days) > WEEK_RANGE * 7:
        raise WebAppError(400, "Bu hafta juda uzoq.")
    return monday


def _hm_to_dt(day: str, hhmm: str | None) -> datetime | None:
    parsed = attendance._parse_hhmm(hhmm or "") if hhmm else None
    if parsed is None:
        return None
    d = date.fromisoformat(day)
    return datetime(d.year, d.month, d.day, parsed[0], parsed[1], tzinfo=company_time.resolve_timezone())


def _started(day: str, existing: dict | None, new_start: str | None, has_entry: bool, now: datetime) -> bool:
    """Kun o'tgan, kelish/ketish yozilgan, eski yoki yangi smena boshlanish vaqti allaqachon kelgan — "boshlangan".
    O'tgan kun (shu jumladan bugunga o'tadigan kechagi tun smenasi) har doim boshlangan hisoblanadi."""
    if has_entry or date.fromisoformat(day) < now.date():
        return True
    for start in ((existing or {}).get("planned_start") if (existing or {}).get("status") == "work" else None, new_start):
        moment = _hm_to_dt(day, start)
        if moment is not None and moment <= now:
            return True
    return False


def _in(ids) -> str:
    return ",".join("?" for _ in ids)


def _week_data(conn, ids: list[int], first: str, last: str) -> tuple[dict, dict, set, set]:
    shifts, versions, entries, stars = {}, {}, set(), set()
    if not ids:
        return shifts, versions, entries, stars
    for emp in ids:
        for d, shift in permanent_schedule.resolved_range(conn, emp, first, last).items():
            shifts[(emp, d)] = shift
    for row in conn.execute(
        f"SELECT employee_id, shift_date, MAX(id) AS v FROM employee_schedule_revisions WHERE employee_id IN ({_in(ids)}) "
        "AND shift_date >= ? AND shift_date <= ? GROUP BY employee_id, shift_date", (*ids, first, last),
    ).fetchall():
        versions[(row["employee_id"], row["shift_date"])] = int(row["v"] or 0)
    for row in conn.execute(
        f"SELECT employee_id, work_date FROM work_time_entries WHERE employee_id IN ({_in(ids)}) AND work_date >= ? "
        "AND work_date <= ?", (*ids, first, last),
    ).fetchall():
        entries.add((row["employee_id"], row["work_date"]))
    months = sorted({first[:7], last[:7]})
    for row in conn.execute(
        f"SELECT user_id, year_month FROM star_history WHERE user_id IN ({_in(ids)}) AND year_month IN ({_in(months)})",
        (*ids, *months),
    ).fetchall():
        stars.add((row["user_id"], row["year_month"]))
    return shifts, versions, entries, stars


def week_payload(user_id: int, week_start=None) -> dict:
    """Hafta (Du–Ya): filiallar → xodimlar → 7 katak. Telefon/maosh yo'q."""
    monday = _week_monday(week_start)
    days = [(monday + timedelta(days=i)).isoformat() for i in range(7)]
    now = company_time.now()
    full = is_full(user_id)
    branches = []
    for branch in visible_branches(user_id):
        people = nazoratchi_day.branch_employees(branch, exclude_user_id=user_id)
        if people:
            branches.append((branch, people))
    ids = [p["user_id"] for _b, people in branches for p in people]
    conn = get_connection()
    try:
        shifts, versions, entries, stars = _week_data(conn, ids, days[0], days[-1])
        past_enabled = permanent_schedule.can_edit_past(conn)
    finally:
        conn.close()
    payload = {
        "week_start": days[0], "today": now.date().isoformat(), "full": full, "past_edit_enabled": past_enabled, "founder": permissions.has_permission(user_id, permissions.ACTION_MANAGE_ROLES),
        "days": [{"date": d, "label": WEEKDAYS[i]} for i, d in enumerate(days)],
        "prev_week": (monday - timedelta(days=7)).isoformat(), "next_week": (monday + timedelta(days=7)).isoformat(),
        "branches": [],
    }
    for branch, people in branches:
        rows = []
        for profile in people:
            emp = profile["user_id"]
            cells = []
            for d in days:
                shift = shifts.get((emp, d))
                started = _started(d, shift, None, (emp, d) in entries, now)
                lock = LOCK_STAR if (emp, d[:7]) in stars else (LOCK_STARTED if started and (not full or (d < now.date().isoformat() and not past_enabled and not permissions.has_permission(user_id, permissions.ACTION_MANAGE_ROLES))) else None)
                cells.append({
                    "date": d,
                    "status": shift["status"] if shift else None,
                    "start": shift.get("planned_start") if shift else None,
                    "end": shift.get("planned_end") if shift else None,
                    "version": versions.get((emp, d), -(shift["default_id"]) if shift and shift.get("default_id") else 0),
                    "locked": lock,
                    "late": bool(started and full),  # nazoratchi uchun: o'zgartirsa sabab so'raladi
                })
            rows.append({"id": emp, "name": nazoratchi_day.full_name(profile), "cells": cells})
        payload["branches"].append({"name": branch, "employees": rows})
    return payload


def _parse_change(raw) -> dict:
    if not isinstance(raw, dict):
        raise WebAppError(400, "Noto'g'ri so'rov.")
    emp, day, status, version = raw.get("employee_id"), raw.get("date"), raw.get("status"), raw.get("expected_version")
    if not isinstance(emp, int) or isinstance(emp, bool) or not isinstance(version, int) or isinstance(version, bool):
        raise WebAppError(400, "Noto'g'ri so'rov.")
    try:
        day = date.fromisoformat(str(day)).isoformat()
    except ValueError:
        raise WebAppError(400, "Noto'g'ri sana.") from None
    if status == "off":
        return {"employee_id": emp, "date": day, "status": "off", "start": None, "end": None, "version": version}
    if status != "work":
        raise WebAppError(400, "Noto'g'ri so'rov.")
    start, end = attendance._parse_hhmm(str(raw.get("start") or "")), attendance._parse_hhmm(str(raw.get("end") or ""))
    if start is None or end is None or start == end:
        raise WebAppError(400, f"{day}: boshlanish va tugash vaqtini to'g'ri kiriting.")
    return {"employee_id": emp, "date": day, "status": "work", "start": "%02d:%02d" % start, "end": "%02d:%02d" % end,
            "version": version}


def _fmt_cell(status, start, end) -> str:
    if status == "work":
        return f"{start}–{end}"
    return "dam" if status == "off" else "—"


def save(user_id: int, raw_changes, reason) -> dict:
    """Barcha o'zgarishlar BITTA tranzaksiyada. Xato bo'lsa hech narsa yozilmaydi va qaysi katak sabab bo'lgani aytiladi.
    Qaytaradi: {"ok", "saved", "notify": {employee_id: [qator, ...]}} — notify faqat bugundan keyingi kunlar."""
    if not isinstance(raw_changes, list) or not raw_changes or len(raw_changes) > MAX_CHANGES:
        raise WebAppError(400, "O'zgarish yo'q yoki juda ko'p.")
    reason = (str(reason).strip()[:300] if reason else "") or None
    changes = [_parse_change(item) for item in raw_changes]
    if len({(c["employee_id"], c["date"]) for c in changes}) != len(changes):
        raise WebAppError(400, "Bir katak ikki marta yuborildi.")
    full = is_full(user_id)
    allowed = set(visible_branches(user_id))
    profiles, modes = {}, {}
    for emp in {c["employee_id"] for c in changes}:  # tranzaksiyadan OLDIN (alohida ulanishlar)
        profile = employees.get_profile(emp, include_contacts=False)
        if profile is None or employees.supervision_branch(profile) not in allowed:
            raise WebAppError(403, "Bu xodimning grafigini o'zgartira olmaysiz.")
        if emp == user_id or emp not in {p["user_id"] for p in nazoratchi_day.branch_employees(
                employees.supervision_branch(profile), exclude_user_id=user_id)}:
            raise WebAppError(403, "Bu xodimning grafigini o'zgartira olmaysiz.")
        profiles[emp], modes[emp] = profile, attendance.resolve_schedule_mode(emp)

    now = company_time.now()
    today = now.date().isoformat()
    notify: dict[int, list[tuple[str, str]]] = {}
    saved = 0
    conn = get_connection()
    try:
        for c in changes:
            emp, day = c["employee_id"], c["date"]
            where = f"{nazoratchi_day.full_name(profiles[emp])}, {day[8:10]}.{day[5:7]}"
            if conn.execute("SELECT 1 FROM star_history WHERE user_id = ? AND year_month = ?", (emp, day[:7])).fetchone():
                raise WebAppError(409, f"{where}: bu oy yulduz qarori chiqqan — grafik qulflangan.")
            current = conn.execute(
                "SELECT MAX(id) AS v FROM employee_schedule_revisions WHERE employee_id = ? AND shift_date = ?", (emp, day),
            ).fetchone()
            raw_version = int(current["v"] or 0)
            current_effective = permanent_schedule.resolved_shift(conn, emp, day)
            effective_version = raw_version if raw_version else -(current_effective["default_id"]) if current_effective and current_effective.get("default_id") else 0
            if effective_version != c["version"]:
                raise WebAppError(409, f"{where}: boshqa joyda o'zgartirilgan — ekran yangilandi, qayta tekshiring.")
            row = conn.execute(
                "SELECT status, planned_start, planned_end FROM employee_scheduled_shifts WHERE employee_id = ? "
                "AND shift_date = ?", (emp, day),
            ).fetchone()
            existing = dict(row) if row else current_effective
            if existing and existing["status"] == c["status"] and (
                c["status"] == "off" or (existing["planned_start"], existing["planned_end"]) == (c["start"], c["end"])
            ):
                continue  # o'zgarishsiz — tarix qatori ham yo'q
            has_entry = conn.execute(
                "SELECT 1 FROM work_time_entries WHERE employee_id = ? AND work_date = ?", (emp, day),
            ).fetchone() is not None
            late = _started(day, existing, c["start"], has_entry, now)
            if late and not full:
                raise WebAppError(403, f"{where}: smena boshlangan yoki o'tgan — faqat nazoratchi o'zgartiradi.")
            if day < today and full and not permanent_schedule.can_edit_past(conn) and not permissions.has_permission(user_id, permissions.ACTION_MANAGE_ROLES):
                raise WebAppError(403, f"{where}: eski kun tahririni Asoschi yopgan.")
            if late and not reason:
                raise WebAppError(400, f"{where}: boshlangan/o'tgan smena — sabab yozing.")
            attendance_repo._record_schedule_revision(
                conn, emp, day, existing, c["status"], c["start"], c["end"], user_id, reason, late,
            )
            conn.execute(
                "INSERT INTO employee_scheduled_shifts "
                "(employee_id, shift_date, planned_start, planned_end, status, schedule_mode, source, created_by, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
                f"ON CONFLICT(employee_id, shift_date) DO UPDATE SET {attendance_repo._SHIFT_UPDATE_CLAUSE}",
                (emp, day, c["start"], c["end"], c["status"], modes[emp], SOURCE, user_id, attendance_repo._now()),
            )
            work_time.resync_day(emp, day, actor=user_id, conn=conn)
            saved += 1
            if day >= today:
                label = WEEKDAYS[date.fromisoformat(day).weekday()]
                notify.setdefault(emp, []).append(
                    (day, f"• {label} {day[8:10]}.{day[5:7]} — {_fmt_cell(c['status'], c['start'], c['end'])}")
                )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return {"ok": True, "saved": saved, "notify": notify}



def permanent_info(user_id: int) -> dict:
    """Only scoped employees; no phone/salary data."""
    conn = get_connection()
    try:
        branches = []
        for branch in visible_branches(user_id):
            people = nazoratchi_day.branch_employees(branch, exclude_user_id=user_id)
            items = []
            for profile in people:
                emp = profile["user_id"]
                row = conn.execute(
                    "SELECT * FROM employee_schedule_defaults WHERE employee_id = ? "
                    "ORDER BY effective_from DESC, id DESC LIMIT 1", (emp,),
                ).fetchone()
                items.append({"id": emp, "name": nazoratchi_day.full_name(profile),
                              "default": {"start": row["planned_start"], "end": row["planned_end"],
                                          "effective_from": row["effective_from"]} if row else None,
                              "version": permanent_schedule.latest_version(conn, emp)})
            branches.append({"name": branch, "employees": items})
        return {"ok": True, "branches": branches}


def save_permanent(user_id: int, employee_id, effective_from, start, end, expected_version, reason=None) -> dict:
    if not isinstance(employee_id, int) or isinstance(employee_id, bool) or not isinstance(expected_version, int):
        raise WebAppError(400, "Noto'g'ri ma'lumot.")
    if employee_id == user_id:
        raise WebAppError(403, "O'zingizning grafigingizni o'zgartira olmaysiz.")
    profile = employees.get_profile(employee_id, include_contacts=False)
    if profile is None or employees.supervision_branch(profile) not in set(visible_branches(user_id)):
        raise WebAppError(403, "Bu xodim sizning filialingizda emas.")
    if employee_id not in {p["user_id"] for p in nazoratchi_day.branch_employees(
            employees.supervision_branch(profile), exclude_user_id=user_id)}:
        raise WebAppError(403, "Bu xodimga ruxsat yo'q.")
    try:
        applied = permanent_schedule.set_default(
            employee_id, str(effective_from), str(start), str(end), user_id, expected_version,
            (str(reason).strip()[:300] or None) if reason else None,
        )
    except (ValueError, TypeError) as err:
        raise WebAppError(409, str(err)) from None
    return {"ok": True, **applied, "employee_id": employee_id, "effective_from": effective_from,
            "start": start, "end": end}


def edit_settings(user_id: int) -> dict:
    if not permissions.has_permission(user_id, permissions.ACTION_MANAGE_ROLES):
        raise WebAppError(403, "Faqat Asoschi.")
    conn = get_connection()
    try:
        return {"ok": True, "allow_nazoratchi_past": permanent_schedule.can_edit_past(conn)}
    finally:
        conn.close()


def save_edit_settings(user_id: int, enabled) -> dict:
    if not permissions.has_permission(user_id, permissions.ACTION_MANAGE_ROLES):
        raise WebAppError(403, "Faqat Asoschi.")
    if not isinstance(enabled, bool):
        raise WebAppError(400, "Ruxsat qiymati noto'g'ri.")
    conn = get_connection()
    try:
        changed = permanent_schedule.set_past_permission(conn, enabled, user_id)
        conn.commit()
        return {"ok": True, "changed": changed, "allow_nazoratchi_past": enabled}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def notify_text(lines: list[tuple[str, str]]) -> str:
    """Bitta saqlashda xodimga bitta xabar: kunlar tartib bilan."""
    body = "\n".join(text for _day, text in sorted(lines))
    return f"📅 Grafigingiz o'zgardi:\n{body}\n\nSavol bo'lsa — /grafik orqali so'rov yuboring."


def history(user_id: int, employee_id, day) -> dict:
    if not isinstance(employee_id, int) or isinstance(employee_id, bool):
        raise WebAppError(400, "Noto'g'ri so'rov.")
    try:
        day = date.fromisoformat(str(day)).isoformat()
    except ValueError:
        raise WebAppError(400, "Noto'g'ri sana.") from None
    profile = employees.get_profile(employee_id, include_contacts=False)
    if profile is None or employees.supervision_branch(profile) not in set(visible_branches(user_id)):
        raise WebAppError(403, "Bu xodimni ko'ra olmaysiz.")
    names: dict[int, str] = {}

    def who(actor):
        if actor is None:
            return "tizim"
        if actor not in names:
            p = employees.get_profile(actor, include_contacts=False)
            names[actor] = nazoratchi_day.full_name(p) if p else ("Asoschi" if actor == _founder() else str(actor))
        return names[actor]

    items = [
        {
            "at": _local(row["changed_at"]),
            "by": who(row["changed_by"]),
            "old": _fmt_cell(row["old_status"], row["old_planned_start"], row["old_planned_end"]),
            "new": _fmt_cell(row["new_status"], row["new_planned_start"], row["new_planned_end"]),
            "reason": row.get("reason"),
            "late": bool(row.get("is_late_change")),
        }
        for row in attendance_repo.list_schedule_revisions(employee_id, day)
    ]
    return {"ok": True, "employee_id": employee_id, "date": day, "items": items[-20:]}


def _local(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).astimezone(company_time.resolve_timezone()).strftime("%d.%m %H:%M")
    except (TypeError, ValueError):
        return str(iso)[:16]


def _founder() -> int:
    from config import FOUNDER_ID

    return FOUNDER_ID
