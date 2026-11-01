"""Aniq ish vaqti (Muhammadiy qarori, 2026-11-01) — kelish/ketish daqiqasi, ishlangan vaqt va vaqt bonusi.

Qoidalar (qat'iy):
* Vaqt bonusi FAQAT erta kelish uchun: kelish < grafik boshlanishi (07:59 < 08:00 → bor; 08:00 → yo'q).
  Keyin erta ketsa ham bonus olib qo'yilmaydi.
* Ishlangan vaqt HAR KUNI alohida = [max(kelish, grafik boshi), min(ketish, grafik oxiri)] — ertaroq kelgan yoki
  kech qolgan daqiqa hisobga kirmaydi, erta ketgan daqiqa ayriladi. Ortiqcha ish faqat qo'shimcha ish yulduzi.
* Grafik yo'q yoki ketish kiritilmagan kun — HISOBLANMAYDI (0 ham emas, xom ham emas): taxmin qilinmaydi.
* Tun smenasi: vaqtlar grafik oynasiga eng yaqin kalendar kuniga bog'lanadi (kelish — boshlanishga, ketish —
  tugashga, ±12 soat ichida). Ish vaqti smena boshlangan ish kuniga (va uning oyiga) tegishli.
* 2026-11-01 dan (``ENTRIES_START``) ishlangan vaqt FAQAT ``work_time_entries``dan; undan oldingi oylar — eski manba.

Hisob hech qachon yozib qo'yilmaydi — har safar ma'lumotdan qayta quriladi (grafik keyin kiritilsa kun o'zi
hisoblanadi). Yagona yozuv: vaqt bonusi ``time_bonus_grants(source='time_entry')`` bilan sinxronlanadi
(boshqa manba yozuviga tegilmaydi).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from db import get_connection

ENTRIES_START = "2026-11-01"
SOURCE_TIME_ENTRY = "time_entry"
STATUS_OK = "ok"
STATUS_NO_SCHEDULE = "no_schedule"
STATUS_DAY_OFF = "day_off"
STATUS_NO_ARRIVAL = "no_arrival"
STATUS_NO_DEPARTURE = "no_departure"
_HALF_DAY = timedelta(hours=12)


class WorkTimeError(ValueError):
    """Foydalanuvchiga ko'rsatiladigan tushunarli xato."""


class WorkTimeConflict(WorkTimeError):
    """Yozuv boshqa joyda (masalan ikkinchi qurilmada) o'zgartirilgan — eskirgan ekran ustidan yozilmaydi."""


def current_version(employee_id: int, work_date: str, conn=None) -> int:
    """Yozuv versiyasi = oxirgi o'zgarish tarixi qatorining id'si (har o'zgarishda qat'iy o'sadi); yozuv yo'q — 0."""
    owns = conn is None
    conn = conn or get_connection()
    try:
        row = conn.execute(
            "SELECT MAX(id) AS v FROM work_time_entry_revisions WHERE employee_id = ? AND work_date = ?",
            (employee_id, work_date),
        ).fetchone()
        return int(row["v"] or 0)
    finally:
        if owns:
            conn.close()


def parse_hhmm(text) -> str | None:
    """"7:59", "07:59" → "07:59". Bo'sh → None. Noto'g'ri → ``WorkTimeError``."""
    if text is None:
        return None
    text = str(text).strip()
    if not text:
        return None
    try:
        parsed = datetime.strptime(text, "%H:%M")
    except ValueError:
        raise WorkTimeError("Vaqtni SS:DD ko'rinishida yozing, masalan 07:59.") from None
    return parsed.strftime("%H:%M")


@dataclass(frozen=True)
class DayResult:
    status: str
    minutes: int = 0          # grafik oynasi ichida ishlangan daqiqa (faqat STATUS_OK)
    time_bonus: bool = False  # kelish < grafik boshi (kelish va grafik bo'lsa — ketishdan qat'i nazar)
    planned_minutes: int = 0


def _at(day: date, hhmm: str, tz) -> datetime:
    hour, minute = (int(part) for part in hhmm.split(":"))
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=tz)


def _nearest(day: date, hhmm: str, target: datetime, tz) -> datetime:
    """``hhmm`` ni ``target``ga eng yaqin kalendar kuniga bog'laydi (oldingi/shu/keyingi kun)."""
    options = [_at(day + timedelta(days=offset), hhmm, tz) for offset in (-1, 0, 1)]
    return min(options, key=lambda moment: abs(moment - target))


def compute_day(work_date: str, shift: dict | None, arrival: str | None, departure: str | None) -> DayResult:
    """Bitta ish kuni natijasi. Faqat hisoblaydi."""
    import company_time

    if shift is None or not shift.get("status"):
        return DayResult(STATUS_NO_SCHEDULE)
    if shift["status"] != "work" or not shift.get("planned_start") or not shift.get("planned_end"):
        return DayResult(STATUS_DAY_OFF)
    tz = company_time.resolve_timezone()
    day = date.fromisoformat(work_date)
    start = _at(day, shift["planned_start"], tz)
    end = _at(day, shift["planned_end"], tz)
    if end <= start:  # tun smenasi: ertasi kuni tugaydi
        end += timedelta(days=1)
    planned = int((end - start).total_seconds() // 60)
    if not arrival:
        return DayResult(STATUS_NO_ARRIVAL, planned_minutes=planned)
    came = _nearest(day, arrival, start, tz)
    bonus = came < start
    if not departure:
        return DayResult(STATUS_NO_DEPARTURE, time_bonus=bonus, planned_minutes=planned)
    left = _nearest(day, departure, end, tz)
    if left <= came or left - came > timedelta(hours=24):
        return DayResult(STATUS_NO_DEPARTURE, time_bonus=bonus, planned_minutes=planned)
    worked = (min(left, end) - max(came, start)).total_seconds() // 60
    return DayResult(STATUS_OK, max(int(worked), 0), bonus, planned)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_entry(employee_id: int, work_date: str, conn=None) -> dict | None:
    owns = conn is None
    conn = conn or get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM work_time_entries WHERE employee_id = ? AND work_date = ?", (employee_id, work_date)
        ).fetchone()
        return dict(row) if row else None
    finally:
        if owns:
            conn.close()


def _shift(employee_id: int, work_date: str, conn) -> dict | None:
    from services.permanent_schedule import resolved_shift
    return resolved_shift(conn, employee_id, work_date)


def save_entry(employee_id: int, work_date: str, arrival, departure, entered_by: int, *, guard=None,
               expected_version: int | None = None) -> DayResult:
    """Kelish/ketishni yozadi (bo'sh qiymat — o'zgarmaydi), tarixni saqlaydi va vaqt bonusini sinxronlaydi.

    ``guard(conn)`` — shu tranzaksiya ICHIDA chaqiriladi (masalan kun/filial yopilmaganini tekshirish); xato bo'lsa
    ``WorkTimeError`` ko'taradi va hech narsa yozilmaydi."""
    if work_date < ENTRIES_START:
        raise WorkTimeError("Bu sana uchun vaqt kiritilmaydi.")
    new_arrival, new_departure = parse_hhmm(arrival), parse_hhmm(departure)
    if new_arrival is None and new_departure is None:
        raise WorkTimeError("Kelish yoki ketish vaqtini yozing.")
    conn = get_connection()
    try:
        if guard is not None:
            guard(conn)
        if expected_version is not None and current_version(employee_id, work_date, conn=conn) != expected_version:
            raise WorkTimeConflict("Bu vaqt boshqa joyda o'zgartirilgan — ekran yangilandi, qayta tekshiring.")
        old = get_entry(employee_id, work_date, conn=conn)
        arrival_value = new_arrival or (old or {}).get("arrival")
        departure_value = new_departure or (old or {}).get("departure")
        now = _now()
        if old is None:
            conn.execute(
                "INSERT INTO work_time_entries (employee_id, work_date, arrival, departure, entered_by, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (employee_id, work_date, arrival_value, departure_value, entered_by, now, now),
            )
        elif (old["arrival"], old["departure"]) != (arrival_value, departure_value):
            conn.execute(
                "UPDATE work_time_entries SET arrival = ?, departure = ?, entered_by = ?, updated_at = ? WHERE id = ?",
                (arrival_value, departure_value, entered_by, now, old["id"]),
            )
        if old is None or (old["arrival"], old["departure"]) != (arrival_value, departure_value):
            conn.execute(
                "INSERT INTO work_time_entry_revisions (employee_id, work_date, old_arrival, old_departure, new_arrival, "
                "new_departure, changed_by, changed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (employee_id, work_date, (old or {}).get("arrival"), (old or {}).get("departure"), arrival_value,
                 departure_value, entered_by, now),
            )
        result = compute_day(work_date, _shift(employee_id, work_date, conn), arrival_value, departure_value)
        _sync_time_bonus(conn, employee_id, work_date, result.time_bonus, entered_by, now)
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _sync_time_bonus(conn, employee_id: int, work_date: str, earned: bool, actor: int, now: str) -> None:
    """Faqat ``source='time_entry'`` yozuviga tegadi; shu kunga boshqa manba yozuvi bo'lsa — o'zgarmaydi."""
    if earned:
        conn.execute(
            "INSERT INTO time_bonus_grants (employee_id, grant_date, source, confirmed_by, confirmed_at) "
            "VALUES (?, ?, ?, ?, ?) ON CONFLICT(employee_id, grant_date) DO NOTHING",
            (employee_id, work_date, SOURCE_TIME_ENTRY, actor, now),
        )
    else:
        conn.execute(
            "DELETE FROM time_bonus_grants WHERE employee_id = ? AND grant_date = ? AND source = ?",
            (employee_id, work_date, SOURCE_TIME_ENTRY),
        )


def resync_day(employee_id: int, work_date: str, actor: int, conn=None) -> DayResult | None:
    """Grafik keyin kiritilgan/o'zgargan kun uchun vaqt bonusini qayta sinxronlash (yozuv bo'lsa).
    ``conn`` berilsa — chaqiruvchi tranzaksiyasi ICHIDA (commit chaqiruvchida)."""
    owns = conn is None
    conn = conn or get_connection()
    try:
        entry = get_entry(employee_id, work_date, conn=conn)
        if entry is None or work_date < ENTRIES_START:
            return None
        result = compute_day(work_date, _shift(employee_id, work_date, conn), entry["arrival"], entry["departure"])
        _sync_time_bonus(conn, employee_id, work_date, result.time_bonus, actor, _now())
        if owns:
            conn.commit()
        return result
    finally:
        if owns:
            conn.close()


# attendance_reasons: rahbar ruxsati tasdiqlangan yoki fors-major (grafikdagi "dam" bilan bir xil narsa EMAS)
_APPROVED_ABSENCE = frozenset({"manager_permission_approved", "force_majeure"})


def month_summary(employee_id: int, start: str, last: str, conn=None) -> dict:
    """``[start, last]`` bo'yicha kunlar tasnifi. Faqat O'QIYDI; noma'lum kun HECH QACHON "kelmagan" yoki 0 soat deb
    yozilmaydi:

    * ``minutes``/``days`` — hisoblangan (kelish+ketish bor) kunlar;
    * ``no_schedule`` (yozuv bor, grafik yo'q/dam), ``no_arrival``, ``no_departure`` — yozuvi to'liq bo'lmagan kunlar;
    * ``day_off`` — grafikda dam, yozuvsiz (tasdiqlangan dam, muammo emas);
    * ``permitted`` — ish kuni, yozuvsiz, lekin rahbar ruxsati/fors-major tasdiqlangan (to'lov qoidasi bu yerda hal qilinmaydi);
    * ``missing`` — grafikda ish kuni, smena tugagan, yozuv ham, tasdiqlangan sabab ham yo'q;
    * ``unknown`` — na grafik, na yozuv, na sabab;
    * ``ongoing`` — smena hali tugamagan (tungi smena, bugungi kun): hali baholanmaydi."""
    import company_time

    owns = conn is None
    conn = conn or get_connection()
    try:
        entries = {
            row["work_date"]: dict(row) for row in conn.execute(
                "SELECT work_date, arrival, departure FROM work_time_entries "
                "WHERE employee_id = ? AND work_date >= ? AND work_date <= ?", (employee_id, start, last),
            ).fetchall()
        }
        reasons = {
            row["event_date"]: row["reason_status"] for row in conn.execute(
                "SELECT event_date, reason_status FROM attendance_reasons "
                "WHERE employee_id = ? AND event_date >= ? AND event_date <= ?", (employee_id, start, last),
            ).fetchall()
        }
        from services.permanent_schedule import resolved_range
        shifts = resolved_range(conn, employee_id, start, last)
    finally:
        if owns:
            conn.close()
    summary = {"minutes": 0, "days": 0, "no_schedule": [], "no_departure": [], "no_arrival": [], "bonus_days": [],
               "day_off": [], "permitted": [], "missing": [], "unknown": [], "ongoing": []}
    tz, now, today = company_time.resolve_timezone(), company_time.now(), company_time.today().isoformat()

    def closed(work_date: str, shift: dict | None) -> bool:
        if not shift or shift.get("status") != "work" or not shift.get("planned_start") or not shift.get("planned_end"):
            return work_date < today
        day = date.fromisoformat(work_date)
        begin, end = _at(day, shift["planned_start"], tz), _at(day, shift["planned_end"], tz)
        if end <= begin:  # tungi smena
            end += timedelta(days=1)
        return now >= end

    day = date.fromisoformat(start)
    while day <= date.fromisoformat(last):
        work_date, shift, entry = day.isoformat(), shifts.get(day.isoformat()), entries.get(day.isoformat())
        day += timedelta(days=1)
        if entry is not None:
            result = compute_day(work_date, shift, entry["arrival"], entry["departure"])
            if result.time_bonus:
                summary["bonus_days"].append(work_date)
            if result.status == STATUS_OK:
                summary["minutes"] += result.minutes
                summary["days"] += 1
            elif result.status in (STATUS_NO_SCHEDULE, STATUS_DAY_OFF):
                summary["no_schedule"].append(work_date)
            elif not closed(work_date, shift):
                summary["ongoing"].append(work_date)
            elif result.status == STATUS_NO_ARRIVAL:
                summary["no_arrival"].append(work_date)
            else:
                summary["no_departure"].append(work_date)
            continue
        if shift is not None and shift.get("status") == "off":
            summary["day_off"].append(work_date)
        elif reasons.get(work_date) in _APPROVED_ABSENCE:
            summary["permitted"].append(work_date)
        elif shift is not None and shift.get("status") == "work":
            summary["missing" if closed(work_date, shift) else "ongoing"].append(work_date)
        elif work_date >= today:
            summary["ongoing"].append(work_date)
        else:
            summary["unknown"].append(work_date)
    return summary
