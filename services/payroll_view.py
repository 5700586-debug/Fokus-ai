"""``Oyligim`` uchun tasdiqlangan hisobning O'QISH qatlami (tugma va xabar ko'rinishi bu yerda YO'Q).

Hech narsa yozmaydi, yangi ledger/kiritish oqimi/avtomatik bonus yaratmaydi. Manba yo'q yoki noaniq bo'lsa qiymat ``None``
("Ma'lumot yo'q") va sababi ``unavailable``/``limitations``da qoladi — nol yoki soxta jami ko'rsatilmaydi; sabab matniga qarab
e'tirof/qo'shimcha ish ajratilmaydi.

Tasdiqlangan formula (Muhammadiy): ``fiks = fiks_oylik * ishlangan_daqiqa / reja_daqiqa`` (butun so'mga yaxlitlanadi),
``yulduz jami = ish_bonusi - min(minus, ish_bonusi) + e'tirof + qo'shimcha_ish`` (minus FAQAT ish bonusidan ayriladi,
e'tirof va qo'shimcha ish himoyalangan), ``umumiy = fiks + yulduz_jami * 5000``."""

from datetime import date, timedelta

import company_time
import employees
from repositories import attendance as attendance_repo
from repositories import payroll_view as view_repo
from repositories import salary_agreements as agreements_repo
from services import attendance

STAR_VALUE_SOM = 5000
NO_DATA = "Ma'lumot yo'q"


def compute_totals(
    plan_minutes: int | None, fixed_salary: int | None, worked_minutes: int | None,
    work_bonus: int | None, minus: int | None, recognition: int | None, extra_work: int | None,
) -> dict:
    """Sof hisob (bazaga tegmaydi). Yetishmagan kirish -> tegishli natija ``None``; ishlangan vaqt rejadan oshsa fiks
    ``None`` (oshgan qism qoidasi tasdiqlanmagan)."""
    fixed_amount = None
    if plan_minutes and plan_minutes > 0 and fixed_salary is not None and worked_minutes is not None and 0 <= worked_minutes <= plan_minutes:
        fixed_amount = (2 * fixed_salary * worked_minutes + plan_minutes) // (2 * plan_minutes)  # yarim so'm yuqoriga

    minus_applied = None
    if work_bonus is not None and minus is not None:
        minus_applied = min(minus, max(work_bonus, 0))

    total_stars = None
    if minus_applied is not None and recognition is not None and extra_work is not None:
        total_stars = work_bonus - minus_applied + recognition + extra_work

    total_amount = fixed_amount + total_stars * STAR_VALUE_SOM if fixed_amount is not None and total_stars is not None else None
    return {"fixed_amount": fixed_amount, "minus_applied": minus_applied, "total_stars": total_stars, "total_amount": total_amount}


def _month_bounds(year_month: str) -> tuple[date, date]:
    year, month = (int(part) for part in year_month.split("-"))
    start = date(year, month, 1)
    next_start = date(year + (month == 12), month % 12 + 1, 1)
    return start, next_start


def _agreement_as_of(agreements: list[dict], on: date) -> dict | None:
    candidates = [a for a in agreements if a["effective_from"] <= on.isoformat()]
    return max(candidates, key=lambda a: (a["effective_from"], a["id"])) if candidates else None


def _worked(employee_id: int, start: date, last: date, conn) -> dict:
    """Ishlangan daqiqa (har kun daqiqasigacha, pastga) mavjud davomat/smena qoidalari (``_worked_hours_from_records``) bilan."""
    fetch_end = (last + timedelta(days=2)).isoformat()
    shifts = {s["shift_date"]: s for s in attendance_repo.get_schedule_for_range(employee_id, start.isoformat(), fetch_end, conn=conn)}
    events = attendance_repo.list_events_for_range(employee_id, start.isoformat(), fetch_end, conn=conn)
    minutes = days = incomplete = 0
    day = start
    while day <= last:
        iso = day.isoformat()
        hours = attendance._worked_hours_from_records(iso, shifts.get(iso), shifts.get((day + timedelta(days=1)).isoformat()), events)
        if hours is not None:
            minutes += int(hours * 60 + 1e-6)
            days += 1
        elif any(e["event_type"] == attendance.EVENT_CHECK_IN and e["event_time"][:10] == iso for e in events):
            incomplete += 1
        day += timedelta(days=1)
    return {"minutes": minutes, "days": days, "incomplete": incomplete}


def month_view(employee_id: int, year_month: str) -> dict:
    """Bir oy uchun hisob komponentlari va jami. Faqat o'qiydi. ``complete`` — hamma manba bor va cheklov yo'q."""
    start, next_start = _month_bounds(year_month)
    today = company_time.today()
    last = min(next_start - timedelta(days=1), today)
    unavailable: dict[str, str] = {}
    limitations: list[str] = []
    result = {"employee_id": employee_id, "year_month": year_month, "final": today >= next_start, "star_value": STAR_VALUE_SOM}

    if last < start:
        reason = f"{NO_DATA}: oy hali boshlanmagan"
        return {**result, "plan_minutes": None, "fixed_salary": None, "worked_minutes": None, "worked_days": 0, "work_bonus": None,
                "minus": None, "recognition": None, "extra_work": None, **compute_totals(None, None, None, None, None, None, None),
                "unavailable": {"month": reason}, "limitations": [reason], "complete": False}

    # --- kelishuv (reja va fiks) ---
    agreements = agreements_repo.list_agreements(employee_id)
    at_start, at_end = _agreement_as_of(agreements, start), _agreement_as_of(agreements, last)
    plan_minutes = fixed_salary = None
    if at_end is None:
        unavailable["plan"] = unavailable["fixed"] = f"{NO_DATA}: kelishuv yo'q"
    elif at_start is None or at_start["id"] != at_end["id"]:
        reason = "Oy davomida kelishuv almashgan — reja va fiks aniq emas"
        unavailable["plan"] = unavailable["fixed"] = reason
        limitations.append(reason)
    elif at_end.get("work_days") is None or at_end.get("daily_minutes") is None:
        unavailable["plan"] = f"{NO_DATA}: kelishuvda ish kunlari/soati kiritilmagan"
        fixed_salary = at_end["fixed_salary"]
    else:
        plan_minutes = at_end["work_days"] * at_end["daily_minutes"]
        fixed_salary = at_end["fixed_salary"]

    from db import get_connection

    conn = get_connection()
    try:
        worked = _worked(employee_id, start, last, conn)
        sources = view_repo.month_sources(employee_id, start.isoformat(), (last + timedelta(days=1)).isoformat(), conn=conn)
    finally:
        conn.close()

    worked_minutes = worked["minutes"] if worked["days"] else None
    if worked_minutes is None:
        unavailable["worked"] = f"{NO_DATA}: davomatda kirish va chiqishi to'liq kun yo'q"
    if worked["incomplete"]:
        limitations.append(f"{worked['incomplete']} kunda kirish bor, chiqish yo'q — ishlangan vaqt to'liq bo'lmasligi mumkin")
    if worked_minutes is not None and plan_minutes and worked_minutes > plan_minutes:
        reason = "Ishlangan vaqt rejadan oshgan — oshgan qism qoidasi tasdiqlanmagan"
        unavailable["fixed"] = reason
        limitations.append(reason)

    full_bonus = -sum(a["penalty_amount"] for a in sources["audits"] if a["event_type"] == "day_full_bonus")
    work_bonus = (sum(e["grade_points"] for e in sources["evaluations"]) + full_bonus) if sources["evaluations"] or full_bonus else None
    if work_bonus is None:
        unavailable["work_bonus"] = f"{NO_DATA}: shu oyda kunlik ish bahosi yo'q"
    minus = sum(p["amount"] for p in sources["penalties"]) + sum(a["penalty_amount"] for a in sources["audits"] if a["event_type"] != "day_full_bonus")
    if sources["time_bonus_days"]:
        limitations.append("Vaqt bonusi berilgan, lekin uning yulduz qiymati tizimda saqlanmaydi — hisobga kirmaydi")
    unavailable["recognition"] = f"{NO_DATA}: e'tirof manbasi yo'q"
    unavailable["extra_work"] = f"{NO_DATA}: qo'shimcha ish manbasi yo'q"

    totals = compute_totals(plan_minutes, fixed_salary, worked_minutes, work_bonus, minus, None, None)
    if totals["fixed_amount"] is None and "fixed" not in unavailable:
        unavailable["fixed"] = f"{NO_DATA}: reja yoki ishlangan vaqt yetarli emas"
    if totals["total_stars"] is None:
        unavailable["total_stars"] = unavailable["total_amount"] = f"{NO_DATA}: tarkibiy qismlardan biri yo'q — jami hisoblanmadi"
    return {
        **result, "plan_minutes": plan_minutes, "fixed_salary": fixed_salary, "worked_minutes": worked_minutes,
        "worked_days": worked["days"], "work_bonus": work_bonus, "minus": minus, "recognition": None, "extra_work": None,
        **totals, "unavailable": unavailable, "limitations": limitations,
        "complete": not unavailable and not limitations and totals["total_amount"] is not None,
    }
