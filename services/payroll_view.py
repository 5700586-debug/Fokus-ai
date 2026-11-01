"""``Oyligim`` uchun tasdiqlangan hisobning O'QISH qatlami (tugma va xabar ko'rinishi bu yerda YO'Q).

Hech narsa yozmaydi, yangi ledger/kiritish oqimi/avtomatik bonus yaratmaydi. Manba yo'q yoki noaniq bo'lsa qiymat ``None``
("Ma'lumot yo'q") va sababi ``unavailable``/``limitations``da qoladi — nol yoki soxta jami ko'rsatilmaydi; sabab matniga qarab
e'tirof/qo'shimcha ish ajratilmaydi.

Tasdiqlangan formula (Muhammadiy): ``fiks = fiks_oylik * ishlangan_daqiqa / reja_daqiqa`` (butun so'mga yaxlitlanadi),
``yulduz jami = ish_bonusi - min(minus, ish_bonusi) + e'tirof + qo'shimcha_ish`` (ish bonusi = baho ballari + nazoratchi
+5 + vaqt bonusi 2 ball/kun; fiks rejadan oshmaydi) (minus FAQAT ish bonusidan ayriladi,
e'tirof va qo'shimcha ish himoyalangan), ``umumiy = fiks + yulduz_jami * 5000``."""

from datetime import date, timedelta

import company_time
import employees
from repositories import attendance as attendance_repo
from repositories import payroll_view as view_repo
from repositories import salary_agreements as agreements_repo
from services import attendance

STAR_VALUE_SOM = 5000
# Muhammadiy qarori (2026-10-30): vaqt bonusi berilgan har kun = 2 ball; ish bonusi kabi minusdan ta'sirlanadi.
TIME_BONUS_POINTS = 2
# 3-tarif mukofoti (Muhammadiy qarori): faqat 3-tarifdagi xodimga, oy intizomli yakunlansa (yulduz mezonlari bilan
# bir xil: nizom minusi yo'q, ish kunlari to'liq, 1 ish + 1 vaqt istisnosi). Yozilmaydi — har safar hisoblanadi.
TARIFF3_AWARD_SOM = 300_000
NO_DATA = "Ma'lumot yo'q"


def compute_totals(
    plan_minutes: int | None, fixed_salary: int | None, worked_minutes: int | None,
    work_bonus: int | None, minus: int | None, recognition: int | None, extra_work: int | None,
) -> dict:
    """Sof hisob (bazaga tegmaydi). Yetishmagan kirish -> tegishli natija ``None``.
    Rejadan ortiq o'tirilgan vaqt pul emas (Muhammadiy qarori, 2026-10-30): fiks rejadagi summadan oshmaydi —
    qo'shimcha ish faqat alohida kelishilgan "qo'shimcha ish yulduzi" bilan to'lanadi."""
    fixed_amount = None
    if plan_minutes and plan_minutes > 0 and fixed_salary is not None and worked_minutes is not None and worked_minutes >= 0:
        paid_minutes = min(worked_minutes, plan_minutes)
        fixed_amount = (2 * fixed_salary * paid_minutes + plan_minutes) // (2 * plan_minutes)  # yarim so'm yuqoriga

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


def _dates(days: list[str]) -> str:
    shown = ", ".join(f"{d[8:10]}.{d[5:7]}" for d in days[:5])
    return shown + (f" va yana {len(days) - 5} ta" if len(days) > 5 else "")


def _day_gaps(summary: dict) -> list[str]:
    """Hisobni to'liq emas qiladigan kunlar. Noma'lum/yozilmagan kun ishga kelmagan yoki 0 soat deb olinmaydi;
    ruxsatli kelmaslik haq to'lanadigan yoki to'lanmaydigan deb hisoblanmaydi (qoida tasdiqlanmagan)."""
    notes = []
    if summary["missing"]:
        notes.append(f"{len(summary['missing'])} kunda davomat kiritilmagan ({_dates(summary['missing'])}) — o'sha kunlar hisoblanmadi")
    if summary["no_arrival"]:
        notes.append(f"{len(summary['no_arrival'])} kunda kelish vaqti yo'q ({_dates(summary['no_arrival'])}) — o'sha kunlar hisoblanmadi")
    if summary["no_departure"]:
        notes.append(f"{len(summary['no_departure'])} kunda ketish vaqti yo'q ({_dates(summary['no_departure'])}) — o'sha kunlar hisoblanmadi")
    if summary["permitted"]:
        notes.append(f"{len(summary['permitted'])} kun ruxsatli kelmaslik ({_dates(summary['permitted'])}) — ishlangan vaqtga kirmaydi, "
                     "haq to'lanishi qoidasi tasdiqlanmagan")
    if summary["no_schedule"]:
        notes.append(f"{len(summary['no_schedule'])} kunda grafik yo'q — o'sha kunlar hisoblanmadi")
    if summary["unknown"] and (summary["days"] or summary["day_off"] or summary["permitted"] or summary["missing"]):
        notes.append(f"{len(summary['unknown'])} kunda grafik ham, davomat ham yozilmagan — noma'lum (ishga kelmagan deb belgilanmadi)")
    return notes


def _star_bonus(employee_id: int, year_month: str) -> int:
    """Founder tasdiqlagan oylik yulduz bonusi (``bonus_history``). Tasdiqlanmagan oy — 0."""
    from db import get_connection

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT bonus_amount FROM bonus_history WHERE user_id = ? AND year_month = ?", (employee_id, year_month)
        ).fetchone()
    finally:
        conn.close()
    return int(row["bonus_amount"]) if row else 0


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
                "time_bonus": 0, "time_bonus_days": 0, "tariff": None, "tariff_award": 0, "tariff_note": None,
                "star_bonus": 0,
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

    from services import work_time

    conn = get_connection()
    try:
        if start.isoformat() >= work_time.ENTRIES_START:
            # 2026-11 dan: aniq kelish/ketish, har kun grafik oynasiga kesilgan (yagona manba — aralashma yo'q).
            profile = employees.get_profile(employee_id, conn=conn, include_contacts=False)
            hire = (profile or {}).get("hire_date")
            first = max(start.isoformat(), hire) if hire and hire[:10] <= last.isoformat() else start.isoformat()
            summary = work_time.month_summary(employee_id, first, last.isoformat(), conn=conn)
            worked = {"minutes": summary["minutes"], "days": summary["days"], "incomplete": 0, "exact": True}
            limitations += _day_gaps(summary)
        else:
            worked = _worked(employee_id, start, last, conn)
        sources = view_repo.month_sources(employee_id, start.isoformat(), (last + timedelta(days=1)).isoformat(), conn=conn)
    finally:
        conn.close()

    worked_minutes = worked["minutes"] if worked["days"] else None
    if worked_minutes is None:
        unavailable["worked"] = (f"{NO_DATA}: kelish va ketishi to'liq kiritilgan kun yo'q" if worked.get("exact")
                                 else f"{NO_DATA}: davomatda kirish va chiqishi to'liq kun yo'q")
    if worked["incomplete"]:
        limitations.append(
            f"{worked['incomplete']} kunda ketish vaqti yo'q — o'sha kunlar hisoblanmadi" if worked.get("exact")
            else f"{worked['incomplete']} kunda kirish bor, chiqish yo'q — ishlangan vaqt to'liq bo'lmasligi mumkin"
        )

    full_bonus = -sum(a["penalty_amount"] for a in sources["audits"] if a["event_type"] == "day_full_bonus")
    time_bonus = sources["time_bonus_days"] * TIME_BONUS_POINTS
    has_bonus_source = sources["evaluations"] or sources["audits"] or sources["time_bonus_days"]
    work_bonus = (sum(e["grade_points"] for e in sources["evaluations"]) + full_bonus + time_bonus) if has_bonus_source else None
    if work_bonus is None:
        unavailable["work_bonus"] = f"{NO_DATA}: shu oyda kunlik ish bahosi yo'q"
    minus = sum(p["amount"] for p in sources["penalties"]) + sum(a["penalty_amount"] for a in sources["audits"] if a["event_type"] != "day_full_bonus")
    # E'tirof alohida manba emas (Muhammadiy: filial rahbari faqat qo'shimcha ish uchun yulduzcha beradi) — 0.
    recognition = 0
    extra_work = sources["extra_work"]

    # Bonus manbasi bo'lmasa ham jami chiqsin: bonus 0 deb olinadi (sababi ``unavailable``da qoladi).
    totals = compute_totals(plan_minutes, fixed_salary, worked_minutes, work_bonus or 0, minus, recognition, extra_work)

    # --- 3-tarif mukofoti va oylik yulduz bonusi (alohida, ikki marta hisoblanmaydi) ---
    tariff = at_end.get("tariff") if at_end else None
    tariff_award, tariff_note = 0, None
    if tariff == 3:
        if not result["final"]:
            tariff_note = "Oy tugagach hisoblanadi"
        else:
            from services import star_month

            decision = next((d for d in star_month.evaluate(year_month) if d.user_id == employee_id), None)
            if decision is None:
                tariff_note = "Bu oy hisobga olinmaydi"
            elif decision.pending:
                tariff_note = "E'tiroz hal bo'lmagan — kutilmoqda"
            elif decision.passed:
                tariff_award = TARIFF3_AWARD_SOM
            else:
                tariff_note = "; ".join(decision.reasons)
    star_bonus = _star_bonus(employee_id, year_month)
    if totals["total_amount"] is not None:
        totals["total_amount"] += tariff_award + star_bonus
    if totals["fixed_amount"] is None and "fixed" not in unavailable:
        unavailable["fixed"] = f"{NO_DATA}: reja yoki ishlangan vaqt yetarli emas"
    if totals["total_stars"] is None:
        unavailable["total_stars"] = unavailable["total_amount"] = f"{NO_DATA}: tarkibiy qismlardan biri yo'q — jami hisoblanmadi"
    return {
        **result, "plan_minutes": plan_minutes, "fixed_salary": fixed_salary, "worked_minutes": worked_minutes,
        "worked_days": worked["days"], "work_bonus": work_bonus, "time_bonus": time_bonus,
        "time_bonus_days": sources["time_bonus_days"], "minus": minus, "recognition": recognition, "extra_work": extra_work,
        "tariff": tariff, "tariff_award": tariff_award, "tariff_note": tariff_note, "star_bonus": star_bonus,
        **totals, "unavailable": unavailable, "limitations": limitations,
        "complete": not unavailable and not limitations and totals["total_amount"] is not None,
    }
