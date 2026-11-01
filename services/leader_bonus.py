"""👔 Filial rahbari (savdo_boshligi) kunlik jamoa bonusi — Muhammadiy qarori (2026-11-01), ChatGPT 2 tur tanqididan keyin.

Rahbar erkin grafikda ishlaydi, shuning uchun uning kunlik ⭐ bali O'Z kelishi/bahosidan emas, JAMOASI natijasidan:
- VAQT qismi: rejalashtirilgan ish kunidagi barcha xodimlar o'z vaqtida (kelish < grafik boshlanishi) → 2;
  ≥80% → 1; aks holda 0.
- ISH qismi: jamoaning o'rtacha kunlik bahosi (a'lo 3, norma 2, chala 1, bajarilmagan 0), bir kasr aniqlikda.
  Maksimum 3 + 2 = 5 (oddiy xodim maksimumiga teng).

Himoyalar:
- "Asos grafik" = ish kunidan bir kun oldin 00:00 (Toshkent) holati. Undan keyingi o'zgarish faqat nazoratchi/Founder
  (``ACTION_MANAGE_DAILY_SCHEDULE``) qilgan bo'lsa qabul qilinadi: rahbar smenani kechroq surib yoki "dam" qilib
  natijani yaxshilay olmaydi.
- Ma'lumot to'liq bo'lmasa (kelish kiritilmagan, grafik yo'q, baholanmagan) o'sha qism 0 va sababi yoziladi — taxmin yo'q.
- Natija filial nazorati YOPILGANDA muhrlanadi (``leader_daily_results``), keyingi tuzatishlar o'zgartirmaydi.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, time, timedelta, timezone

import company_time
from db import get_connection
from services import nazoratchi_day, permissions, work_time

logger = logging.getLogger(__name__)

LEADER_ROLE = "savdo_boshligi"
START = work_time.ENTRIES_START
FULL_TIME_POINTS, PART_TIME_POINTS, PART_SHARE = 2, 1, 0.8


def _cutoff(work_date: str) -> str:
    """Asos grafik vaqti: ish kunidan bir kun oldin 00:00 Toshkent → UTC ISO (revisions ``changed_at`` UTC)."""
    day = date.fromisoformat(work_date) - timedelta(days=1)
    local = datetime.combine(day, time(0, 0), tzinfo=company_time.resolve_timezone())
    return local.astimezone(timezone.utc).isoformat()


def baseline_shift(conn, employee_id: int, work_date: str) -> dict | None:
    """Rahbar hisobi uchun grafik: cutoff'gacha bo'lgan oxirgi holat + cutoff'dan keyingi faqat nazoratchi/Founder
    o'zgarishlari. Tarix yo'q bo'lsa — joriy qator (eski yozuvlar)."""
    revisions = [dict(r) for r in conn.execute(
        "SELECT new_status, new_planned_start, new_planned_end, changed_by, changed_at FROM employee_schedule_revisions "
        "WHERE employee_id = ? AND shift_date = ? ORDER BY id", (employee_id, work_date),
    ).fetchall()]
    if not revisions:
        row = conn.execute(
            "SELECT status, planned_start, planned_end FROM employee_scheduled_shifts WHERE employee_id = ? "
            "AND shift_date = ?", (employee_id, work_date),
        ).fetchone()
        return dict(row) if row else None
    cutoff = _cutoff(work_date)
    state = None
    for rev in revisions:
        trusted = rev["changed_by"] is not None and permissions.has_permission(
            rev["changed_by"], permissions.ACTION_MANAGE_DAILY_SCHEDULE)
        if str(rev["changed_at"]) < cutoff or trusted:
            state = {"status": rev["new_status"], "planned_start": rev["new_planned_start"],
                     "planned_end": rev["new_planned_end"]}
    return state


def branch_leaders(branch: str) -> list[int]:
    from roles import list_users_by_role

    import employees

    leaders = []
    for user_id in list_users_by_role(LEADER_ROLE):
        profile = employees.get_profile(user_id, include_contacts=False) or {}
        if profile.get("branch") == branch:
            leaders.append(user_id)
    return leaders


def compute(branch: str, work_date: str, leaders: list[int] | None = None) -> dict:
    """Shu filial va kun uchun jamoa natijasi (faqat O'QIYDI)."""
    leaders = branch_leaders(branch) if leaders is None else leaders
    team = [p for p in nazoratchi_day.branch_employees(branch) if p["user_id"] not in set(leaders)]
    conn = get_connection()
    try:
        planned = on_time = 0
        late, missing_arrival, no_schedule, ungraded = [], [], [], []
        grades: list[int] = []
        for profile in team:
            emp, name = profile["user_id"], nazoratchi_day.full_name(profile)
            shift = baseline_shift(conn, emp, work_date)
            grade = conn.execute(
                "SELECT grade_points FROM daily_evaluations WHERE employee_id = ? AND eval_date = ?", (emp, work_date),
            ).fetchone()
            if grade is not None:
                grades.append(int(grade["grade_points"]))
            if shift is None:
                if grade is not None:
                    no_schedule.append(name)  # ishlagan, lekin grafik yo'q — muvaffaqiyat deb taxmin qilinmaydi
                continue
            if shift.get("status") != "work":
                continue  # dam / sababli
            planned += 1
            if grade is None:
                ungraded.append(name)
            entry = work_time.get_entry(emp, work_date, conn=conn)
            if not entry or not entry.get("arrival"):
                missing_arrival.append(name)
                continue
            result = work_time.compute_day(work_date, shift, entry["arrival"], entry.get("departure"))
            if result.time_bonus:
                on_time += 1
            else:
                late.append(f"{name} {entry['arrival']}")
    finally:
        conn.close()

    incomplete = []
    if missing_arrival:
        incomplete.append("kelish kiritilmagan: " + ", ".join(missing_arrival))
    if no_schedule:
        incomplete.append("grafik yo'q: " + ", ".join(no_schedule))
    if planned == 0 or missing_arrival or no_schedule:
        time_points = 0
    elif on_time == planned:
        time_points = FULL_TIME_POINTS
    elif on_time / planned >= PART_SHARE:
        time_points = PART_TIME_POINTS
    else:
        time_points = 0
    if ungraded:
        incomplete.append("baholanmagan: " + ", ".join(ungraded))
    work_points = 0.0 if ungraded or not grades else round(sum(grades) / len(grades) + 1e-9, 1)
    return {"branch": branch, "work_date": work_date, "leaders": leaders, "planned": planned, "on_time": on_time,
            "late": late, "graded": len(grades), "time_points": time_points, "work_points": work_points,
            "incomplete": incomplete}


def _fmt_points(value: float) -> str:
    return (f"{value:.1f}".rstrip("0").rstrip(".")).replace(".", ",")


def message_text(result: dict) -> str:
    d = result["work_date"]
    lines = [f"👔 Jamoa natijasi — {result['branch']}, {d[8:10]}.{d[5:7]}"]
    if result["planned"]:
        lines.append(f"⏰ O'z vaqtida: {result['on_time']}/{result['planned']} → ⭐ {result['time_points']}")
    else:
        lines.append("⏰ Grafikda ishlovchi yo'q → ⭐ 0")
    if result["late"]:
        lines.append("   Kechikdi: " + ", ".join(result["late"]))
    lines.append(f"📋 Jamoa o'rtacha bahosi → ⭐ {_fmt_points(result['work_points'])}")
    total = result["time_points"] + result["work_points"]
    lines.append(f"Jami bugun: ⭐ {_fmt_points(total)} / 5")
    if result["incomplete"]:
        lines.append("⚠️ Ma'lumot to'liq emas (" + "; ".join(result["incomplete"]) + ") — shu qism hisoblanmadi.")
    return "\n".join(lines)


def snapshot(branch: str, work_date: str, now_iso: str | None = None) -> list[tuple[int, dict]]:
    """Yopilgan filial-kun uchun natijani muhrlaydi (har rahbarga bitta qator; takroriy chaqiruv o'zgartirmaydi).
    Yangi yozilgan (rahbar, natija) juftlarini qaytaradi."""
    if work_date < START:
        return []
    leaders = branch_leaders(branch)
    if not leaders:
        return []
    result = compute(branch, work_date, leaders)
    created = []
    conn = get_connection()
    try:
        for leader in leaders:
            cur = conn.execute(
                "INSERT INTO leader_daily_results (leader_id, branch, work_date, time_points, work_points, on_time, "
                "planned, graded, details, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(leader_id, branch, work_date) DO NOTHING",
                (leader, branch, work_date, result["time_points"], result["work_points"], result["on_time"],
                 result["planned"], result["graded"],
                 json.dumps({"late": result["late"], "incomplete": result["incomplete"]}, ensure_ascii=False),
                 now_iso or datetime.now(timezone.utc).isoformat()),
            )
            if cur.rowcount:
                created.append((leader, result))
        conn.commit()
    finally:
        conn.close()
    return created


def pending_closed_sessions(since: str) -> list[tuple[str, str]]:
    """Yopilgan, lekin rahbar natijasi hali muhrlanmagan (filial, kun) juftlari."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT DISTINCT s.branch, s.session_date FROM nazoratchi_branch_sessions s WHERE s.status = 'closed' "
            "AND s.session_date >= ? AND NOT EXISTS (SELECT 1 FROM leader_daily_results r WHERE r.branch = s.branch "
            "AND r.work_date = s.session_date) ORDER BY s.session_date", (since,),
        ).fetchall()
    finally:
        conn.close()
    return [(row["branch"], row["session_date"]) for row in rows]


async def tick(bot) -> None:
    """Har necha daqiqada: yopilgan filial-kunlarni muhrlab, rahbarga bitta xabar yuboradi."""
    from services import notifications

    since = max(START, (company_time.today() - timedelta(days=7)).isoformat())
    for branch, work_date in pending_closed_sessions(since):
        try:
            for leader, result in snapshot(branch, work_date):
                await notifications.send_once(bot, f"leader_day:{branch}:{work_date}", leader, message_text(result))
        except Exception as error:  # noqa: BLE001 - bitta filial xatosi qolganlarini to'xtatmasin
            logger.error("Rahbar natijasi xatosi (%s, %s): %s", branch, work_date, type(error).__name__)


def month_points(leader_id: int, start: str, last: str, conn=None) -> dict:
    owns = conn is None
    conn = conn or get_connection()
    try:
        rows = conn.execute(
            "SELECT time_points, work_points FROM leader_daily_results WHERE leader_id = ? AND work_date >= ? "
            "AND work_date <= ?", (leader_id, start, last),
        ).fetchall()
    finally:
        if owns:
            conn.close()
    time_total = sum(int(r["time_points"]) for r in rows)
    work_total = round(sum(float(r["work_points"]) for r in rows) + 1e-9, 1)
    return {"days": len(rows), "time_points": time_total, "work_points": work_total}
