"""Fiks oylik KELISHUVI: kiritish qoidalari, saqlash va sanaga qarab amaldagisini o'qish.

Faqat kelishuvni saqlash va ko'rsatish — ishlangan soatdan oylik hisoblash, bonus/minus/yaxlitlash formulasi yo'q.
Yagona yozish yo'li ``save_agreement`` (eski ``/setsalary`` ham ``discipline.set_fixed_salary`` orqali shunga keladi).
Kelishuv tarixi o'chirilmaydi: har o'zgarish yangi qator. Amaldagi kelishuv — ``effective_from <= bugun`` ichida eng kech
``effective_from`` (teng bo'lsa oxirgi kiritilgan); kelajak sanali kelishuv bugungi fiksni O'ZGARTIRMAYDI va hech qanday
scheduler kerak emas — sana o'qish paytida solishtiriladi. O'tgan sana tanlansa faqat yoziladi: avvalgi baho/bonus/davomat
qayta hisoblanmaydi (bu modul ularga tegmaydi)."""

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

import company_time
from db import get_connection
from repositories import salary_agreements as repo

MAX_SALARY = 2_000_000_000  # Postgres INTEGER chegarasidan past
SOURCE_AGREEMENT = "agreement"
SOURCE_LEGACY = "legacy_setsalary"


class ValidationError(ValueError):
    """Foydalanuvchiga ko'rsatiladigan qisqa o'zbekcha xabar bilan."""


def parse_salary(text: str) -> int:
    cleaned = re.sub(r"(?i)(so['‘’`ʻ]?m|sum)", "", text or "")
    cleaned = re.sub(r"[\s_]", "", cleaned)
    # "," yoki "." faqat minglik ajratgich sifatida (4,000,000 / 4.000.000); "1.5" kabi kasr summa emas
    if re.search(r"[.,]", cleaned):
        if not re.fullmatch(r"\d{1,3}([.,]\d{3})+", cleaned):
            raise ValidationError("Summani raqam bilan yozing, masalan: 4 000 000")
        cleaned = re.sub(r"[.,]", "", cleaned)
    if not cleaned.isdigit():
        raise ValidationError("Summani raqam bilan yozing, masalan: 4 000 000")
    value = int(cleaned)
    if value <= 0:
        raise ValidationError("Summa noldan katta bo'lishi kerak.")
    if value > MAX_SALARY:
        raise ValidationError("Summa juda katta.")
    return value


def parse_days(text: str) -> int:
    cleaned = (text or "").strip()
    if not cleaned.isdigit():
        raise ValidationError("Kunlar sonini butun raqam bilan yozing (1 dan 31 gacha).")
    value = int(cleaned)
    if not 1 <= value <= 31:
        raise ValidationError("Kunlar soni 1 dan 31 gacha bo'lishi kerak.")
    return value


def parse_daily_minutes(text: str) -> int:
    """"12", "12.5", "12,5", "12:30" -> daqiqa (butun). Faqat butun yoki yarim soat; >0 va <=24 soat."""
    raw = (text or "").strip().lower().replace("soat", "").strip()
    try:
        if ":" in raw:
            hours_part, minutes_part = raw.split(":", 1)
            hours, minutes = int(hours_part), int(minutes_part)
            if minutes not in (0, 30):
                raise ValueError
            total = hours * 60 + minutes
        else:
            number = raw.replace(",", ".")
            if not re.fullmatch(r"\d+(\.\d)?", number):
                raise ValueError
            doubled = float(number) * 2
            if doubled != int(doubled):
                raise ValueError
            total = int(doubled) * 30
    except ValueError:
        raise ValidationError("Soatni raqam bilan yozing: butun yoki yarim soat (masalan 12 yoki 12.5).") from None
    if total <= 0 or total > 24 * 60:
        raise ValidationError("Kunlik soat 0 dan katta va 24 dan oshmasligi kerak.")
    return total


def parse_effective_date(text: str, today: date | None = None) -> str:
    today = today or company_time.today()
    raw = (text or "").strip()
    parsed = None
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(raw, fmt).date()
            break
        except ValueError:
            continue
    if parsed is None:
        raise ValidationError("Sanani KK.OO.YYYY ko'rinishida yozing, masalan: 01.11.2026")
    if parsed < date(2020, 1, 1) or parsed > today + timedelta(days=730):
        raise ValidationError("Sana mantiqiy oraliqda emas.")
    return parsed.isoformat()


def validate_agreement(fixed_salary, work_days, daily_minutes, effective_from: str) -> None:
    """Server tomonida yakuniy tekshiruv (FSM ma'lumoti ishonchli deb hisoblanmaydi)."""
    if not isinstance(fixed_salary, int) or isinstance(fixed_salary, bool) or not 0 < fixed_salary <= MAX_SALARY:
        raise ValidationError("Summa noto'g'ri.")
    if not isinstance(work_days, int) or isinstance(work_days, bool) or not 1 <= work_days <= 31:
        raise ValidationError("Kunlar soni noto'g'ri.")
    if not isinstance(daily_minutes, int) or isinstance(daily_minutes, bool) or not 0 < daily_minutes <= 1440 or daily_minutes % 30:
        raise ValidationError("Kunlik soat noto'g'ri.")
    if not isinstance(effective_from, str) or parse_effective_date(effective_from) != effective_from:
        raise ValidationError("Sana noto'g'ri (YYYY-MM-DD kutiladi).")


@dataclass
class SaveResult:
    created: bool
    agreement: dict | None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write(
    employee_id: int, fixed_salary: int, work_days: int | None, daily_minutes: int | None, effective_from: str,
    created_by: int, source: str, request_token: str | None,
) -> SaveResult:
    """Kelishuv qatori + (amaldagi bo'lsa) ``salaries.fixed_salary`` sinxroni BITTA tranzaksiyada. Xatoda hammasi bekor;
    takroriy ``request_token`` hech narsa yozmaydi."""
    now = _now_iso()
    today = company_time.today().isoformat()
    conn = get_connection()
    try:
        agreement_id = repo.insert_agreement(
            conn,
            {
                "employee_id": employee_id, "fixed_salary": fixed_salary, "work_days": work_days,
                "daily_minutes": daily_minutes, "effective_from": effective_from, "created_by": created_by,
                "created_at": now, "source": source, "request_token": request_token,
            },
        )
        if agreement_id is None:
            return SaveResult(False, None)
        current = repo.current_agreement(employee_id, today, conn=conn)
        if current is not None:  # kelajak sanali kelishuv bo'lsa joriy fiks o'zgarmaydi
            repo.mirror_fixed_salary(conn, employee_id, current["fixed_salary"], created_by, now)
        conn.commit()
    except BaseException:
        rollback = getattr(conn, "rollback", None)
        if rollback is not None:
            rollback()
        raise
    finally:
        conn.close()

    saved = next((item for item in repo.list_agreements(employee_id) if item["id"] == agreement_id), None)
    return SaveResult(True, saved)


def save_agreement(
    employee_id: int, fixed_salary: int, work_days: int, daily_minutes: int, effective_from: str,
    created_by: int, request_token: str,
) -> SaveResult:
    validate_agreement(fixed_salary, work_days, daily_minutes, effective_from)
    if not request_token:
        raise ValidationError("Saqlash tokeni yo'q.")
    return _write(employee_id, fixed_salary, work_days, daily_minutes, effective_from, created_by, SOURCE_AGREEMENT, request_token)


def save_legacy_fixed_salary(employee_id: int, fixed_salary: int, updated_by: int) -> SaveResult:
    """Eski ``/setsalary <user_id> <summa>``: bugundan amal qiladigan, kun/soat NOMA'LUM kelishuv qatori."""
    return _write(
        employee_id, fixed_salary, None, None, company_time.today().isoformat(), updated_by, SOURCE_LEGACY, None
    )


def get_current(employee_id: int) -> dict | None:
    return repo.current_agreement(employee_id, company_time.today().isoformat())


def get_upcoming(employee_id: int) -> dict | None:
    return repo.upcoming_agreement(employee_id, company_time.today().isoformat())


def list_history(employee_id: int) -> list[dict]:
    return repo.list_agreements(employee_id)


# ------------------------------------------------------------------ matnlar --


def format_money(value: int) -> str:
    return f"{value:,}".replace(",", " ") + " so'm"


def format_minutes(minutes: int | None) -> str:
    if minutes is None:
        return "Kiritilmagan"
    hours, rest = divmod(minutes, 60)
    return f"{hours} soat" + (f" {rest} daqiqa" if rest else "")


def format_date(iso_date: str) -> str:
    year, month, day = iso_date.split("-")
    return f"{day}.{month}.{year}"


def agreement_lines(agreement: dict) -> list[str]:
    days = agreement.get("work_days")
    return [
        f"📅 Oylik ish kunlari: {str(days) + ' kun' if days is not None else 'Kiritilmagan'}",
        f"🕒 Kunlik ish soati: {format_minutes(agreement.get('daily_minutes'))}",
        f"📌 Amal qilish sanasi: {format_date(agreement['effective_from'])}",
    ]


def view_lines(employee_id: int, legacy_fixed: int) -> list[str]:
    """Ko'rish uchun (Founder va xodimning o'zi): amaldagi kelishuv va kelajakdagisi ALOHIDA."""
    current = get_current(employee_id)
    upcoming = get_upcoming(employee_id)
    lines: list[str] = []
    if current is not None:
        lines.append(f"💵 Fiks oylik: {format_money(current['fixed_salary'])}")
        lines += agreement_lines(current)
    else:
        lines.append(f"💵 Fiks oylik: {format_money(legacy_fixed)}")
        lines.append("📋 Kelishuv kunlari/soati: Kiritilmagan")
    if upcoming is not None:
        lines += [
            "",
            f"⏭ Kelajakdagi kelishuv ({format_date(upcoming['effective_from'])} dan; hozirgi fiksni o'zgartirmaydi):",
            f"💵 {format_money(upcoming['fixed_salary'])}",
            *agreement_lines(upcoming),
        ]
    return lines
