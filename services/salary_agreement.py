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
TARIFFS = (1, 2, 3)  # tarif faqat belgi; 1-2 qoidalari hali tasdiqlanmagan, fiks har doim qo'lda


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


def validate_salary_amount(fixed_salary) -> None:
    """Eski va yangi yo'l uchun YAGONA summa qoidasi: musbat butun so'm, ``MAX_SALARY`` gacha."""
    if not isinstance(fixed_salary, int) or isinstance(fixed_salary, bool) or not 0 < fixed_salary <= MAX_SALARY:
        raise ValidationError("Summa musbat butun so'm bo'lishi kerak (1 dan 2 000 000 000 gacha).")


def validate_agreement(fixed_salary, work_days, daily_minutes, effective_from: str) -> None:
    """Server tomonida yakuniy tekshiruv (FSM ma'lumoti ishonchli deb hisoblanmaydi)."""
    validate_salary_amount(fixed_salary)
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
    created_by: int, source: str, request_token: str | None, tariff: int | None = None,
    result_bonus_cap: int | None = None, with_consent: bool = False,
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
                "tariff": tariff, "result_bonus_cap": result_bonus_cap,
            },
        )
        if agreement_id is None:
            return SaveResult(False, None)
        if with_consent:
            repo.insert_consent_row(conn, agreement_id, employee_id)
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
    created_by: int, request_token: str, *, tariff: int | None = None, result_bonus_cap: int | None = None,
    with_consent: bool = False,
) -> SaveResult:
    validate_agreement(fixed_salary, work_days, daily_minutes, effective_from)
    if tariff is not None and (not isinstance(tariff, int) or isinstance(tariff, bool) or tariff not in TARIFFS):
        raise ValidationError("Tarif noto'g'ri.")
    if result_bonus_cap is not None:
        validate_salary_amount(result_bonus_cap)
    if not request_token:
        raise ValidationError("Saqlash tokeni yo'q.")
    return _write(
        employee_id, fixed_salary, work_days, daily_minutes, effective_from, created_by, SOURCE_AGREEMENT, request_token,
        tariff, result_bonus_cap, with_consent,
    )


def save_legacy_fixed_salary(employee_id: int, fixed_salary: int, updated_by: int) -> SaveResult:
    """Eski ``/setsalary <user_id> <summa>``: bugundan amal qiladigan, kun/soat NOMA'LUM kelishuv qatori."""
    validate_salary_amount(fixed_salary)  # service bevosita chaqirilganda ham 0/manfiy/juda katta summa rad etiladi
    return _write(
        employee_id, fixed_salary, None, None, company_time.today().isoformat(), updated_by, SOURCE_LEGACY, None
    )


def get_current(employee_id: int) -> dict | None:
    return repo.current_agreement(employee_id, company_time.today().isoformat())


def get_upcoming(employee_id: int) -> dict | None:
    return repo.upcoming_agreement(employee_id, company_time.today().isoformat())


def get_all_upcoming(employee_id: int) -> list[dict]:
    return repo.upcoming_agreements(employee_id, company_time.today().isoformat())


def employee_ids_with_agreements() -> set[int]:
    return repo.employee_ids_with_agreements()


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


def agreement_lines(agreement: dict, show_bonus_cap: bool = True) -> list[str]:
    days = agreement.get("work_days")
    extra = []
    if agreement.get("tariff") is not None:
        extra.append(f"🏷 Tarif: {agreement['tariff']}")
    cap = agreement.get("result_bonus_cap")
    if cap and show_bonus_cap:  # eski yozuvlardagi qiymat ko'rsatiladi; yangi kelishuvda bonus chegarasi kiritilmaydi
        extra.append(f"🎯 Natija bonusi: {'oyiga ' + format_money(cap) + 'gacha (chegara, kafolatlangan to‘lov emas)' if cap else 'Belgilanmagan'}")
    return extra + [
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


# ------------------------------------------------------------ rozilik --

DELIVERY_PENDING, DELIVERY_SENT, DELIVERY_FAILED = "pending", "sent", "failed"
CONSENT_RECORDED, CONSENT_ALREADY, CONSENT_NOT_OWNER, CONSENT_SUPERSEDED, CONSENT_UNKNOWN = (
    "recorded", "already", "not_owner", "superseded", "unknown",
)


def get_consent(agreement_id: int) -> dict | None:
    return repo.get_consent(agreement_id)


def mark_delivery(agreement_id: int, ok: bool) -> None:
    repo.set_delivery(agreement_id, DELIVERY_SENT if ok else DELIVERY_FAILED, _now_iso())


_UNSET = object()


def consent_status_text(agreement: dict, consent=_UNSET, issue=_UNSET) -> str:
    """Xodim va Founder uchun aniq holat. Rozilik jadvalida qatori yo'q (eski) kelishuvga rozilik TALAB QILINMAGAN.
    ``consent``/``issue`` oldindan o'qilgan bo'lsa (``employee_cards``) qayta so'ralmaydi."""
    if consent is _UNSET:
        consent = repo.get_consent(agreement["id"])
    if consent is None:
        return "Rozilik talab qilinmagan (eski kelishuv)"
    if issue is _UNSET:
        issue = repo.get_issue_for_agreement(agreement["id"])
    question = ""
    if issue is not None:
        question = "\n❓ Xodim savol bergan: " + (
            "hal qilingan (" + ISSUE_OUTCOMES.get(issue["outcome"], "-") + ")" if issue["status"] == "resolved" else "hal qilinmagan"
        )
    if consent["consented_at"]:
        return f"✅ Xodim roziligi olingan ({consent['consented_at'][:16].replace('T', ' ')} UTC)" + question
    if consent["delivery_status"] == DELIVERY_FAILED:
        return "⚠️ Xodimga yuborilmadi — xodim tasdig'i kutilmoqda" + question
    return "⏳ Xodim tasdig'i kutilmoqda" + question


def record_consent(agreement_id: int, user_id: int) -> str:
    """Faqat kelishuv egasi, faqat aynan shu versiya (yangi versiya chiqqan bo'lsa eskisi tasdiqlanmaydi)."""
    agreement = repo.get_agreement(agreement_id)
    if agreement is None or repo.get_consent(agreement_id) is None:
        return CONSENT_UNKNOWN
    if agreement["employee_id"] != user_id:
        return CONSENT_NOT_OWNER
    if not is_live(agreement):
        return CONSENT_SUPERSEDED
    return CONSENT_RECORDED if repo.record_consent(agreement_id, user_id, _now_iso()) else CONSENT_ALREADY


def employee_cards(employee_id: int) -> list[dict]:
    """``/mykelishuv`` uchun: amaldagi (bo'lsa) va har kelajak sanadagi oxirgi kelishuv — tartib va qoidalar ``get_current``/
    ``get_all_upcoming`` bilan bir xil, lekin 3 ta so'rov bilan (kartalar soniga bog'liq emas). Har element:
    ``agreement``, ``kind`` (current|upcoming), ``consent``, ``issue``, ``pending`` (rozilik qatori bor, tasdiqlanmagan;
    ko'rsatilgan kartalar doim 'jonli'). Faqat o'qish; callbacklar baribir bazadan yangidan tekshiradi."""
    agreements, consents, issues = repo.employee_snapshot(employee_id)
    today = company_time.today().isoformat()
    past = [a for a in agreements if a["effective_from"] <= today]
    current = max(past, key=lambda a: (a["effective_from"], a["id"])) if past else None
    winners: dict[str, dict] = {}
    for a in agreements:
        if a["effective_from"] > today and (a["effective_from"] not in winners or a["id"] > winners[a["effective_from"]]["id"]):
            winners[a["effective_from"]] = a
    ordered = ([(current, "current")] if current else []) + [(winners[d], "upcoming") for d in sorted(winners)]
    return [
        {
            "agreement": a, "kind": kind, "consent": consents.get(a["id"]), "issue": issues.get(a["id"]),
            "pending": consents.get(a["id"]) is not None and not consents[a["id"]]["consented_at"],
        }
        for a, kind in ordered
    ]


def is_live(agreement: dict) -> bool:
    """Versiya hali almashtirilmagan: bugungi AMALDAGI kelishuv yoki har bir kelajak sanadagi oxirgi kiritilgan kelishuv. Almashtirilgan
    (yangi versiya o'rnini olgan) versiyaga rozilik/savol yozilmaydi; amaldagi paytda kelajak versiya uni bekor qilmaydi."""
    employee_id = agreement["employee_id"]
    live = [get_current(employee_id), *get_all_upcoming(employee_id)]
    return agreement["id"] in {item["id"] for item in live if item is not None}


def pending_consent(agreement: dict) -> bool:
    """Shu versiya uchun rozilik qatori bor, hali tasdiqlanmagan va versiya almashtirilmagan."""
    consent = repo.get_consent(agreement["id"])
    return consent is not None and not consent["consented_at"] and is_live(agreement)


def latest_pending_consent_id(employee_id: int) -> int | None:
    for item in (get_current(employee_id), *get_all_upcoming(employee_id)):
        if item is not None and pending_consent(item):
            return item["id"]
    return None


def version_number(employee_id: int, agreement_id: int) -> int:
    return repo.version_number(employee_id, agreement_id)


def get_agreement(agreement_id: int) -> dict | None:
    return repo.get_agreement(agreement_id)


def can_view(viewer_id: int, employee_id: int, employee_branch: str | None) -> bool:
    """Kelishuv va summalar: xodimning o'zi, Founder, yoki shu xodim filialiga biriktirilgan vakolatli rahbar
    (``ACTION_VIEW_BRANCH_AGREEMENT`` + ``can_access_branch`` — rahbar rollari filiallararo emas, faqat O'Z filiali).
    Boshqa hamma — yo'q. Har ochish/callbackda qayta chaqiriladi."""
    from services import permissions

    if viewer_id == employee_id:
        return True
    if permissions.get_role(viewer_id) == "founder":
        return True
    return permissions.has_permission(viewer_id, permissions.ACTION_VIEW_BRANCH_AGREEMENT) and permissions.can_access_branch(
        viewer_id, employee_branch
    )


def branch_managers(branch: str | None) -> list[int]:
    """Shu filialning vakolatli rahbarlari (tasdiqlangan profil, o'z filiali shu)."""
    import employees
    from roles import list_users_by_role
    from services import permissions

    if not branch:
        return []
    found = []
    for role_key, actions in permissions.ROLE_PERMISSIONS.items():
        if permissions.ACTION_VIEW_BRANCH_AGREEMENT not in actions:
            continue
        for user_id in list_users_by_role(role_key):
            profile = employees.get_profile(user_id, include_contacts=False)
            if profile and profile.get("status") == "approved" and can_view(user_id, -1, branch):
                found.append(user_id)
    return found


# ------------------------------------------------- "Tushunmadim" savollari --

ISSUE_EXPLAINED, ISSUE_NEW_AGREEMENT, ISSUE_DISAGREED = "explained", "new_agreement", "disagreed"
ISSUE_OUTCOMES = {
    ISSUE_EXPLAINED: "tushuntirildi",
    ISSUE_NEW_AGREEMENT: "yangi kelishuv",
    ISSUE_DISAGREED: "kelishilmadi",
}
ISSUE_OPENED, ISSUE_ALREADY, ISSUE_CONSENTED = "opened", "already", "consented"


def ask_not_understood(agreement_id: int, user_id: int) -> tuple[str, dict | None]:
    """Xodim "❓ Tushunmadim"ni bosdi: faqat egasi, faqat joriy (eng yangi) versiya, rozilik berilmagan. Versiya uchun
    bitta savol; takroriy bosish yangisini ochmaydi. Qaytadi: (natija, savol)."""
    import employees

    agreement = repo.get_agreement(agreement_id)
    consent = repo.get_consent(agreement_id) if agreement else None
    if agreement is None or consent is None:
        return CONSENT_UNKNOWN, None
    if agreement["employee_id"] != user_id:
        return CONSENT_NOT_OWNER, None
    if not is_live(agreement):
        return CONSENT_SUPERSEDED, None
    if consent["consented_at"]:
        return ISSUE_CONSENTED, None
    profile = employees.get_profile(user_id, include_contacts=False) or {}
    issue_id = repo.open_issue(
        agreement_id, user_id, profile.get("branch"), company_time.today().isoformat(), _now_iso()
    )
    if issue_id is None:
        return ISSUE_ALREADY, repo.get_issue_for_agreement(agreement_id)
    return ISSUE_OPENED, repo.get_issue(issue_id)


def can_manage_issue(user_id: int, issue: dict) -> bool:
    return user_id != issue["employee_id"] and can_view(user_id, issue["employee_id"], issue["branch"])


def resolve_issue(issue_id: int, user_id: int, outcome: str) -> str:
    """Yopish: Founder yoki o'sha filial rahbari; xodimning o'zi emas. Rozilikni O'ZGARTIRMAYDI."""
    issue = repo.get_issue(issue_id)
    if issue is None or outcome not in ISSUE_OUTCOMES:
        return "unknown"
    if not can_manage_issue(user_id, issue):
        return "denied"
    return "resolved" if repo.resolve_issue(issue_id, user_id, outcome, _now_iso()) else "already"


def issue_for_agreement(agreement_id: int) -> dict | None:
    return repo.get_issue_for_agreement(agreement_id)


def get_issue(issue_id: int) -> dict | None:
    return repo.get_issue(issue_id)


def set_issue_notified(issue_id: int, count: int) -> None:
    repo.set_issue_notified(issue_id, count)


def open_issues() -> list[dict]:
    return repo.list_open_issues()


def mark_issue_reminded(issue_id: int, day: str) -> None:
    repo.mark_reminded(issue_id, day)


def latest_agreement_id(employee_id: int) -> int | None:
    agreements = repo.list_agreements(employee_id)
    return agreements[-1]["id"] if agreements else None
