"""Doimiy grafik: sanali versiya + kunlik istisno. Hech qachon o'tgan sanalarga retroaktiv qo'llanmaydi."""
from __future__ import annotations

from datetime import date
import company_time
from db import get_connection


class ScheduleConflict(ValueError):
    pass


def effective_default(conn, employee_id: int, day: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM employee_schedule_defaults WHERE employee_id = ? AND effective_from <= ? "
        "ORDER BY effective_from DESC, id DESC LIMIT 1",
        (employee_id, day),
    ).fetchone()
    if not row:
        return None
    row = dict(row)
    return {"employee_id": employee_id, "shift_date": day, "status": "work",
            "planned_start": row["planned_start"], "planned_end": row["planned_end"],
            "source": "permanent_default", "default_id": row["id"]}


def resolved_shift(conn, employee_id: int, day: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM employee_scheduled_shifts WHERE employee_id = ? AND shift_date = ?",
        (employee_id, day),
    ).fetchone()
    return dict(row) if row else effective_default(conn, employee_id, day)


def resolved_range(conn, employee_id: int, first: str, last: str) -> dict[str, dict]:
    """Inclusive, 2 bulk reads rather than one/two SQL queries per calendar day."""
    start, end = date.fromisoformat(first), date.fromisoformat(last)
    if end < start:
        return {}
    if (end - start).days > 93:
        raise ValueError("Grafik davri juda uzun")
    from datetime import timedelta
    versions = [
        dict(row) for row in conn.execute(
            "SELECT * FROM employee_schedule_defaults WHERE employee_id = ? AND effective_from <= ? "
            "ORDER BY effective_from, id", (employee_id, last),
        ).fetchall()
    ]
    overrides = {
        row["shift_date"]: dict(row) for row in conn.execute(
            "SELECT * FROM employee_scheduled_shifts WHERE employee_id = ? "
            "AND shift_date >= ? AND shift_date <= ?", (employee_id, first, last),
        ).fetchall()
    }
    result: dict[str, dict] = {}
    day, idx, current = start, 0, None
    while day <= end:
        key = day.isoformat()
        while idx < len(versions) and versions[idx]["effective_from"] <= key:
            current = versions[idx]
            idx += 1
        if key in overrides:
            result[key] = overrides[key]
        elif current is not None:
            result[key] = {
                "employee_id": employee_id, "shift_date": key, "status": "work",
                "planned_start": current["planned_start"], "planned_end": current["planned_end"],
                "source": "permanent_default", "default_id": current["id"],
            }
        day += timedelta(days=1)
    return result

def latest_version(conn, employee_id: int) -> int:
    row = conn.execute(
        "SELECT MAX(id) AS v FROM employee_schedule_defaults WHERE employee_id = ?",
        (employee_id,),
    ).fetchone()
    return int(row["v"] or 0)


def set_default(employee_id: int, effective_from: str, start: str, end: str,
                actor: int, expected_version: int, reason: str | None = None) -> dict:
    """Only today (before start) or future. Never rewrite individual days."""
    from services.attendance import _parse_hhmm
    first = date.fromisoformat(effective_from)
    now = company_time.now()
    a, b = _parse_hhmm(start), _parse_hhmm(end)
    if not a or not b or a == b:
        raise ScheduleConflict("Ish vaqtini to'g'ri kiriting")
    if first <= now.date():
        raise ScheduleConflict("Doimiy grafik faqat ertangi yoki undan keyingi sanadan boshlanadi")
    start, end = "%02d:%02d" % a, "%02d:%02d" % b
    conn = get_connection()
    try:
        if latest_version(conn, employee_id) != expected_version:
            raise ScheduleConflict("Grafik boshqa oynada o'zgargan")
        if conn.execute("SELECT 1 FROM star_history WHERE user_id = ? AND year_month >= ? LIMIT 1",
                        (employee_id, effective_from[:7])).fetchone():
            raise ScheduleConflict("Yulduz qarori chiqqan oyga doimiy grafik kiritilmaydi")
        if conn.execute("SELECT 1 FROM employee_schedule_defaults WHERE employee_id = ? AND effective_from = ?",
                        (employee_id, effective_from)).fetchone():
            raise ScheduleConflict("Bu sanada doimiy grafik allaqachon belgilangan")
        # Non-retroactive: earlier effective dates never inserted after a later one.
        latest = conn.execute("SELECT MAX(effective_from) AS last FROM employee_schedule_defaults WHERE employee_id = ?",
                              (employee_id,)).fetchone()["last"]
        if latest and effective_from < latest:
            raise ScheduleConflict("Oldindan kiritilgan kelajak grafigini orqaga ko'chirib bo'lmaydi")
        old = effective_default(conn, employee_id, effective_from)
        if old and old["planned_start"] == start and old["planned_end"] == end:
            return {"changed": False, "version": expected_version}
        conn.execute(
            "INSERT INTO employee_schedule_defaults (employee_id, effective_from, planned_start, planned_end, "
            "created_by, created_at, reason) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (employee_id, effective_from, start, end, actor, now.isoformat(), reason),
        )
        version = latest_version(conn, employee_id)
        conn.commit()
        return {"changed": True, "version": version}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def can_edit_past(conn) -> bool:
    row = conn.execute("SELECT allow_nazoratchi_past FROM employee_schedule_edit_settings WHERE id = 1").fetchone()
    return bool(row["allow_nazoratchi_past"]) if row else True


def set_past_permission(conn, enabled: bool, actor: int) -> bool:
    old = can_edit_past(conn)
    if old == enabled:
        return False
    now = company_time.now().isoformat()
    conn.execute("INSERT INTO employee_schedule_edit_settings(id, allow_nazoratchi_past, changed_by, changed_at) "
                 "VALUES (1, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET allow_nazoratchi_past=excluded.allow_nazoratchi_past,"
                 " changed_by=excluded.changed_by, changed_at=excluded.changed_at", (int(enabled), actor, now))
    conn.execute("INSERT INTO employee_schedule_edit_settings_history(old_enabled,new_enabled,changed_by,changed_at)"
                 " VALUES(?,?,?,?)", (int(old), int(enabled), actor, now))
    return True
