"""BOS (Business Operating System): kunlik baholash, intizomiy jarima/bonus
banki, nazoratchi mas'uliyati va apellyatsiya.

Fiks oylik (``salaries.fixed_salary``) hech qachon bu modul orqali
o'zgartirilmaydi — faqat Founder ``set_fixed_salary`` bilan belgilaydi.
Jarima va kunlik baho FAQAT ``bonus_bank``ga ta'sir qiladi
(``adjust_bonus_bank`` orqali, har bir o'zgarish ``bonus_bank_ledger``da
audit sifatida qoladi).
"""

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

import company_time
import employees
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from repositories import discipline as discipline_repo
from repositories import rule_learning as rule_learning_repo
from services import rules as rules_service

logger = logging.getLogger(__name__)

GRADE_BAJARILMAGAN = "bajarilmagan"
GRADE_CHALA = "chala"
GRADE_NORMA = "norma"
GRADE_ALO = "alo"

GRADE_LABELS = {
    GRADE_BAJARILMAGAN: "Bajarilmagan",
    GRADE_CHALA: "Chala",
    GRADE_NORMA: "Norma",
    GRADE_ALO: "A'lo",
}


def get_grade_points() -> dict[str, int]:
    """Har bir baho uchun ball qiymati — ``bos.grade_points.*`` qoidalari
    orqali Founder ``/setrule`` bilan sozlashi mumkin (kod o'zgarishisiz).
    """
    return rules_service.get_bos_grade_points()


def get_penalty_amounts() -> tuple[int, ...]:
    """Ruxsat etilgan jarima miqdorlari — ``bos.penalty_amounts`` qoidasi
    orqali Founder ``/setrule`` bilan sozlashi mumkin (kod o'zgarishisiz).
    """
    return rules_service.get_bos_penalty_amounts()

APPEAL_NONE = "none"
APPEAL_PENDING = "pending"
APPEAL_RESOLVED = "resolved"

DECISION_APPROVED = "approved"
DECISION_REJECTED = "rejected"

_RULE_NUMBER_RE = re.compile(r"\d+")


# ------------------------------------------------------------- salaries --


def set_fixed_salary(user_id: int, fixed_salary: int, updated_by: int) -> None:
    discipline_repo.upsert_fixed_salary(user_id, fixed_salary, updated_by)


def get_salary(user_id: int) -> dict:
    salary = discipline_repo.get_salary(user_id)
    if salary is None:
        return {"user_id": user_id, "fixed_salary": 0, "bonus_bank": 0}
    return salary


def adjust_bonus_bank(user_id: int, delta: int, reason: str, ref_type: str, ref_id: int | None = None) -> int:
    return discipline_repo.adjust_bonus_bank(user_id, delta, reason, ref_type, ref_id)


def get_bonus_ledger(user_id: int, limit: int = 20) -> list[dict]:
    return discipline_repo.get_bonus_ledger(user_id, limit)


_YEAR_MONTH_RE = re.compile(r"^(\d{4})-(\d{2})$")


def _month_bounds(year_month: str) -> tuple[str, str, str, str]:
    """``"YYYY-MM"`` -> (oy boshi sanasi, keyingi oy boshi sanasi, ikkalasining UTC ISO vaqti). Oy
    chegarasi: boshlanish <= sana < keyingi oy boshlanishi (har oy 31 kun emas; dekabr -> keyingi yil
    yanvar; kabisa fevral). Kompaniya vaqt zonasi ishlatiladi. Yaroqsiz oy/yil uchun ``ValueError``."""
    match = _YEAR_MONTH_RE.match(year_month or "")
    if match is None:
        raise ValueError(f"oy 'YYYY-MM' ko'rinishida bo'lishi kerak: {year_month!r}")
    year, month = int(match.group(1)), int(match.group(2))
    if not 1 <= month <= 12 or year < 1:
        raise ValueError(f"noto'g'ri oy: {year_month!r}")

    start = date(year, month, 1)
    following = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    tz = company_time.resolve_timezone()

    def utc_iso(day: date) -> str:
        return datetime(day.year, day.month, day.day, tzinfo=tz).astimezone(timezone.utc).isoformat()

    return start.isoformat(), following.isoformat(), utc_iso(start), utc_iso(following)


def get_period_point_totals(user_id: int, year_month: str | None = None) -> dict:
    """Berilgan oy (``"YYYY-MM"``; berilmasa kompaniyaning joriy oyi) uchun Bonus/Minus/Jami ball.
    Kunlik baho bonusi baho OYIGA (``eval_date``) tegishli — baho qachon kiritilgani yoki tuzatilgani
    oyni o'zgartirmaydi; boshqa bonus va haqiqiy minuslar ledgerdan o'z yozilgan oyi bo'yicha olinadi
    (qarang ``discipline_repo.get_month_point_totals``). Eski oylar hech qachon o'chirilmaydi — bu
    funksiya faqat KO'RSATISH uchun hisoblaydi va hech narsa yozmaydi."""
    key = company_time.today().strftime("%Y-%m") if year_month is None else year_month
    start_date, end_date, since_iso, until_iso = _month_bounds(key)
    totals = discipline_repo.get_month_point_totals(user_id, start_date, end_date, since_iso, until_iso)
    return {"period_key": key, "bonus": totals["bonus"], "minus": totals["minus"], "net": totals["net"]}


# --------------------------------------------------------- company rules --


def add_rule(rule_number: int, title: str, content: str, created_by: int) -> bool:
    return discipline_repo.create_rule(rule_number, title, content, created_by)


def get_rule(rule_number: int) -> dict | None:
    return discipline_repo.get_rule_by_number(rule_number)


def list_rules() -> list[dict]:
    return discipline_repo.list_active_rules()


def list_learning_rules() -> list[dict]:
    """O'rganish oqimi uchun: madaniyat/bonus modeli/lavozim chek-listlari majburiy o'qitilmaydi."""
    return discipline_repo.list_learning_rules()


def list_rules_with_penalty_amount() -> list[dict]:
    return discipline_repo.list_rules_with_penalty_amount()


def set_rule_penalty_amount(rule_number: int, amount: int, updated_by: int) -> bool:
    """Nizom bandiga standart ball miqdorini belgilaydi — Nazoratchi
    kartasidagi tugma orqali ball ayirish shu miqdordan foydalanadi.
    Faqat Founder chaqiradi (``ACTION_MANAGE_DISCIPLINE_RULES``).
    ``updated_by`` hozircha audit uchun saqlanmaydi (``company_rules``da
    alohida ustun yo'q) — kerak bo'lsa keyin qo'shiladi."""
    if amount <= 0:
        raise ValueError(f"ball miqdori musbat bo'lishi kerak: {amount}")

    rule = discipline_repo.get_rule_by_number(rule_number)
    if rule is not None and rule.get("catalog_kind") is not None:
        # Katalog bandining balli asl manbadagi "–N ball" satridan olinadi; qo'lda o'zgartirilmaydi.
        raise ValueError("katalog bandining balli manbadan olinadi, o'zgartirib bo'lmaydi")

    return discipline_repo.set_rule_penalty_amount(rule_number, amount)


def report_unmatched_incident(
    employee_id: int, reported_by: int, report_text: str, ai_note: str | None = None
) -> int:
    """Hech qanday tasdiqlangan nizom bandiga mos kelmagan holat —
    minus ball QO'LLANMAYDI, faqat Founder ko'rib chiqishi uchun
    audit yozuvi yaratiladi (qarang ``discipline_unmatched_reports``)."""
    return discipline_repo.create_unmatched_report(employee_id, reported_by, report_text, ai_note)


def extract_rule_number(text: str) -> int | None:
    """"3-nizom", "3 nizom", "nizom 3", "3" kabi matndan nizom raqamini
    ajratib oladi — birinchi topilgan butun sonni qaytaradi.
    """
    match = _RULE_NUMBER_RE.search(text)
    return int(match.group()) if match else None


# ------------------------------------------------------------ evaluation --


@dataclass
class EvaluationResult:
    grade_key: str
    grade_points: int
    bonus_bank_balance: int
    eval_date: str = ""
    changed: bool = True
    old_grade_key: str | None = None
    old_grade_points: int | None = None


def record_daily_grade(employee_id: int, supervisor_id: int, eval_date: str, grade_key: str) -> EvaluationResult:
    grade_points_map = get_grade_points()
    if grade_key not in grade_points_map:
        raise ValueError(f"noma'lum baho: {grade_key}")

    grade_points = grade_points_map[grade_key]
    # Baho + tarix + bonus balansi + ledger — repository'da BITTA tranzaksiya (xato bo'lsa hammasi bekor).
    saved = discipline_repo.save_daily_grade(
        employee_id, supervisor_id, eval_date, grade_key, grade_points, f"Kunlik baho: {GRADE_LABELS[grade_key]}"
    )
    previous = saved["previous"]
    old_key = previous["grade_key"] if previous else None
    old_points = previous["grade_points"] if previous else None

    if not saved["changed"]:
        # Xuddi shu baho takroriy bosilgan: tarix/ledger yozilmagan.
        return EvaluationResult(
            grade_key, grade_points, get_salary(employee_id)["bonus_bank"], eval_date, False, old_key, old_points
        )

    return EvaluationResult(grade_key, grade_points, saved["balance"], eval_date, True, old_key, old_points)


# ------------------------------------------------- xodimga baho xabari --

NOTICE_SENT = "sent"
NOTICE_UNCHANGED = "unchanged"
NOTICE_NOT_LINKED = "not_linked"
NOTICE_FAILED = "failed"
NOTICE_UNKNOWN_EMPLOYEE = "unknown_employee"

_QUIET_FROM_HOUR = 22
_QUIET_UNTIL_HOUR = 7

_NOTICE_REPLIES = {
    NOTICE_SENT: "Saqlandi",
    NOTICE_UNCHANGED: "Bu baho allaqachon saqlangan.",
    NOTICE_NOT_LINKED: "Xodim botga ulanmagan — baho saqlandi, xabar yuborilmadi.",
    NOTICE_FAILED: "Baho saqlandi, lekin xodimga xabar yuborib bo'lmadi.",
    NOTICE_UNKNOWN_EMPLOYEE: "Xodim topilmadi.",
}


def grade_notice_reply(outcome: str) -> str:
    """Nazoratchiga qisqa javob matni (callback.answer)."""
    return _NOTICE_REPLIES[outcome]


def is_quiet_time(local_now: datetime) -> bool:
    """22:00 <= vaqt yoki vaqt < 07:00 (kompaniya mahalliy vaqti) — xabar ovozsiz."""
    return local_now.hour >= _QUIET_FROM_HOUR or local_now.hour < _QUIET_UNTIL_HOUR


def format_grade_notice(result: EvaluationResult, totals: dict) -> str:
    """``totals`` — baho OYI (``result.eval_date``) uchun ``get_period_point_totals`` natijasi. Joriy oy
    bahosida "Shu oy …", oldingi oy bahosida oy aniq ko'rsatiladi ("2026-10 uchun …") — eski sana
    xabariga joriy oy yig'indisi qo'shilmaydi."""
    day = date.fromisoformat(result.eval_date).strftime("%d.%m.%Y")
    if result.changed and result.old_grade_points is not None:
        head = f"✏️ Tuzatildi: {result.old_grade_points} → {result.grade_points}"
    else:
        head = f"⭐ Baho: {result.grade_points} — {GRADE_LABELS[result.grade_key]}"
    period_key = totals.get("period_key")
    is_current_month = period_key is None or period_key == company_time.today().strftime("%Y-%m")
    label = "Shu oy" if is_current_month else f"{period_key} uchun"
    return (
        f"📅 Sana: {day}\n"
        f"{head}\n"
        f"{label} bonus: {totals['bonus']}\n"
        f"{label} minus: {totals['minus']}\n"
        f"{label} jami: {totals['net']}"
    )


def employee_telegram_chat_id(employee_id: int) -> int | None:
    """Xodimning Telegram chat_id'si. ``employees.user_id`` — PRIMARY KEY va xodim
    profili Telegram'dan kelgan ``from_user.id`` bilan yaratiladi (onboarding, rekruting),
    ya'ni shaxsiy chat_id shu qiymatning o'zi. Profil yo'q yoki qiymat yaroqsiz bo'lsa ``None``."""
    profile = employees.get_profile(employee_id)
    if profile is None:
        return None
    user_id = profile.get("user_id")
    return user_id if isinstance(user_id, int) and user_id > 0 else None


async def notify_employee_of_grade(bot, employee_id: int, result: EvaluationResult) -> str:
    """Baho DBga yozilgandan KEYIN xodimning shaxsiy chatiga xabar yuboradi. Faqat yuborish
    atrofidagi xato ushlanadi (baho/ledger bekor qilinmaydi); log'ga faqat operatsiya va xato turi."""
    if not result.changed:
        return NOTICE_UNCHANGED
    if employees.get_profile(employee_id) is None:
        return NOTICE_UNKNOWN_EMPLOYEE

    chat_id = employee_telegram_chat_id(employee_id)
    if chat_id is None:
        return NOTICE_NOT_LINKED

    try:
        text = format_grade_notice(result, get_period_point_totals(employee_id, result.eval_date[:7]))
        await bot.send_message(chat_id, text, disable_notification=is_quiet_time(company_time.now()))
    except TelegramForbiddenError:
        logger.error("grade_notice: yuborib bo'lmadi (bot bloklangan/ulanmagan)")
        return NOTICE_NOT_LINKED
    except TelegramBadRequest as error:
        logger.error("grade_notice: yuborib bo'lmadi (%s)", type(error).__name__)
        return NOTICE_NOT_LINKED if "chat not found" in str(error).lower() else NOTICE_FAILED
    except Exception as error:  # noqa: BLE001
        logger.error("grade_notice: yuborib bo'lmadi (%s)", type(error).__name__)
        return NOTICE_FAILED

    return NOTICE_SENT


def get_grade_history(employee_id: int, eval_date: str) -> list[dict]:
    return discipline_repo.get_evaluation_history(employee_id, eval_date)


def format_daily_star_message(
    name: str, grade_points: int, reason: str, totals: dict, day_label: str = "kecha"
) -> str:
    """Xodim uchun yulduzli kunlik xabar matni. Ichki hisob — ball, xodimga ⭐ ko'rinishida;
    Bonus (plus) va Minus ALOHIDA yig'iladi, Hisob = Bonus - Minus ("+3 va -12 = -9" deb
    qo'shilmaydi). Eski xabarni o'chirib yangisini yuborish (live yuborish) alohida TODO —
    bu yerda faqat matn/hisob poydevori. ``totals`` — ``get_period_point_totals`` natijasi."""
    sign = "+" if grade_points >= 0 else ""
    return (
        f"{name}, {day_label} siz {sign}{grade_points} ⭐ oldingiz.\n"
        f"Sabab: {reason}.\n"
        f"Shu oy jami: {totals['bonus']} ⭐\n"
        f"Minus: {totals['minus']} ⭐ kamaygan\n"
        f"Hisob: {totals['net']} ⭐"
    )


def get_daily_grade(employee_id: int, eval_date: str) -> dict | None:
    return discipline_repo.get_daily_evaluation(employee_id, eval_date)


def get_daily_leaderboard(eval_date: str) -> list[dict]:
    rows = discipline_repo.get_evaluations_for_date(eval_date)
    return [{"employee_id": row["employee_id"], "grade_points": row["grade_points"]} for row in rows]


def get_monthly_leaderboard(year_month: str) -> list[dict]:
    start_date = f"{year_month}-01"
    end_date = f"{year_month}-31"

    points = discipline_repo.get_points_totals(start_date, end_date)
    penalties = discipline_repo.get_penalty_totals(start_date, end_date)
    penalty_by_employee = {row["employee_id"]: row["total_penalty"] for row in penalties}

    board: dict[int, int] = {}
    for row in points:
        board[row["employee_id"]] = row["total_points"] - penalty_by_employee.get(row["employee_id"], 0)
    for employee_id, total_penalty in penalty_by_employee.items():
        board.setdefault(employee_id, -total_penalty)

    ranked = sorted(board.items(), key=lambda pair: pair[1], reverse=True)
    return [{"employee_id": employee_id, "net_score": score} for employee_id, score in ranked]


# ------------------------------------------------------------- penalties --


def apply_penalty(
    employee_id: int,
    supervisor_id: int,
    penalty_date: str,
    amount: int,
    rule_number: int,
    comment: str | None,
    ai_note: str | None,
    option_id: int | None = None,
) -> dict:
    rule = discipline_repo.get_rule_by_number(rule_number)
    if rule is None:
        raise ValueError(f"{rule_number}-nizom topilmadi")

    if rule.get("catalog_kind") is not None:
        # Import qilingan katalog bandi: ball FAQAT manbadagi tasdiqlangan miqdor/variantdan.
        # Umumiy -10/-20/-30 ro'yxati bu yerda hech narsani ruxsat etmaydi.
        options = discipline_repo.list_penalty_options(rule_number)
        if option_id is not None:
            option = next((item for item in options if item["id"] == option_id), None)
            if option is None:
                raise ValueError("variant bu bandga tegishli emas yoki nofaol")
            if not option["apply_allowed"]:
                raise ValueError("bu variant xodimga qo'llanmaydi (boshqa shaxsga tegishli)")
            if amount != option["points"]:
                raise ValueError(f"jarima miqdori variantga mos emas: {amount}")
            variant_key = option["variant_key"]
        elif options:
            only = options[0] if len(options) == 1 else None
            if only is not None and rule.get("default_penalty_amount") == amount == only["points"] and only["apply_allowed"]:
                variant_key = only["variant_key"]  # bir ma'noli, shartsiz band: yagona tasdiqlangan miqdor
            else:
                raise ValueError("bu bandda ball variantlari bor — variant tanlanishi shart")
        elif rule.get("default_penalty_amount") is not None and amount == rule["default_penalty_amount"]:
            variant_key = None
        else:
            raise ValueError("bu bandda tasdiqlangan ball miqdori yo'q")
        if variant_key:
            ai_note = f"variant={variant_key}" + (f"; {ai_note}" if ai_note else "")
    else:
        # ``bos.penalty_amounts`` — /baholash oqimidagi umumiy tugma
        # to'plami (-10/-20/-30). Nazoratchi kartasidagi nizom-bandi
        # tugmalari esa har bir bandning O'Z ``default_penalty_amount``
        # qiymatidan foydalanadi (Founder /setnizombahosi bilan
        # belgilagan) — bu ikkalasi mustaqil, shuning uchun ikkalasidan
        # BIRIGA mos kelsa yetarli.
        if amount not in get_penalty_amounts() and amount != rule.get("default_penalty_amount"):
            raise ValueError(f"jarima miqdori noto'g'ri: {amount}")

    saved = discipline_repo.create_penalty_with_balance(
        employee_id, supervisor_id, penalty_date, amount, rule_number, comment, ai_note
    )
    penalty_id, balance = saved["penalty_id"], saved["balance"]

    return {"penalty_id": penalty_id, "bonus_bank_balance": balance, "rule": rule}


def get_penalty_learning_context(penalty_id: int) -> dict | None:
    """Jarima (``discipline_penalties``) va o'sha nizomni o'qish auditi
    (``rule_learning_progress``) orasidagi READ-ONLY bog'lanish -- hech
    qanday yozuv/UI/AI/xabar/avtomatik jazo bu yerda YO'Q, faqat holatni
    o'qib qaytaradi."""
    penalty = discipline_repo.get_penalty(penalty_id)
    if penalty is None:
        return None

    progress = rule_learning_repo.get_progress_for_rule(penalty["employee_id"], penalty["rule_number"])
    completed_at = progress.get("completed_at") if progress else None
    penalty_created_at = penalty.get("created_at")

    if progress is None:
        status = "not_learned"
    elif completed_at is None:
        status = "learning_incomplete"
    elif completed_at <= penalty_created_at:
        status = "understood_before_penalty"
    else:
        status = "understood_after_penalty"

    return {
        "penalty_id": penalty["id"],
        "employee_id": penalty["employee_id"],
        "rule_number": penalty["rule_number"],
        "status": status,
        "title_snapshot": progress.get("title_snapshot") if progress else None,
        "content_snapshot": progress.get("content_snapshot") if progress else None,
        "understood_at": progress.get("understood_confirmed_at") if progress else None,
        "penalty_created_at": penalty_created_at,
    }


def list_appealable_penalties(employee_id: int, limit: int = 10) -> list[dict]:
    return discipline_repo.list_penalties_by_status(employee_id, APPEAL_NONE, limit)


APPEAL_DELIVERY_CLAIM_TTL_SECONDS = 120


def claim_appeal_delivery(penalty_id: int) -> bool:
    stale_before = (datetime.now(timezone.utc) - timedelta(seconds=APPEAL_DELIVERY_CLAIM_TTL_SECONDS)).isoformat()
    return discipline_repo.claim_appeal_delivery(penalty_id, stale_before)


def mark_appeal_delivered(penalty_id: int, founder_message_id: int | None) -> bool:
    return discipline_repo.mark_appeal_delivered(penalty_id, founder_message_id)


def release_appeal_delivery(penalty_id: int) -> None:
    discipline_repo.release_appeal_delivery(penalty_id)


def list_undelivered_appeals(employee_id: int, limit: int = 10) -> list[dict]:
    """Xodimning saqlangan (``pending``), lekin hali Founderga yetkazilmagan e'tirozlari — "Qayta yuborish" uchun."""
    return [
        penalty for penalty in discipline_repo.list_penalties_by_status(employee_id, APPEAL_PENDING, limit)
        if not penalty.get("appeal_delivered_at")
    ]


def get_penalty(penalty_id: int) -> dict | None:
    return discipline_repo.get_penalty(penalty_id)


def submit_appeal(penalty_id: int, reason_text: str, voice_file_id: str | None) -> dict | None:
    penalty = discipline_repo.get_penalty(penalty_id)
    if penalty is None or penalty["appeal_status"] != APPEAL_NONE:
        return None

    if not discipline_repo.set_penalty_appeal(penalty_id, reason_text, voice_file_id):
        return None
    return discipline_repo.get_penalty(penalty_id)


def save_appeal_brief(penalty_id: int, brief: str) -> None:
    discipline_repo.set_penalty_appeal_brief(penalty_id, brief)


def decide_appeal(penalty_id: int, decision: str, decided_by: int) -> dict:
    if decision not in (DECISION_APPROVED, DECISION_REJECTED):
        raise ValueError(f"noma'lum qaror: {decision}")

    penalty = discipline_repo.get_penalty(penalty_id)
    if penalty is None or penalty["appeal_status"] != APPEAL_PENDING:
        raise ValueError("apellyatsiya topilmadi yoki allaqachon hal qilingan")

    decided = discipline_repo.decide_penalty_appeal_with_refund(
        penalty_id, decision, decided_by, refund=(decision == DECISION_APPROVED)
    )
    if decided is None:
        raise ValueError("apellyatsiya topilmadi yoki allaqachon hal qilingan")

    return penalty


# ---------------------------------------------------------- day closure --


def close_day(supervisor_id: int, closure_date: str, total_employees: int) -> bool:
    evaluated_count = len(discipline_repo.get_evaluations_for_date(closure_date))
    return discipline_repo.try_close_day(supervisor_id, closure_date, evaluated_count, total_employees)


def get_closure(supervisor_id: int, closure_date: str) -> dict | None:
    return discipline_repo.get_closure(supervisor_id, closure_date)


def penalize_supervisor_for_late_close(supervisor_id: int, audit_date: str, penalty_amount: int) -> bool:
    """``audit_date`` — ISH KUNI (work_date). Audit + balans + ledger bitta tranzaksiyada, bir ish kuni uchun bir marta."""
    return discipline_repo.record_supervisor_audit_with_penalty(
        supervisor_id, audit_date, "day_not_closed", penalty_amount
    )


# ------------------------------------------------ nizom katalogi: o'qish, tanlash, iqtibos --

SOURCE_ORDER = (
    "nizomlar", "madaniyat", "omborchi", "kassir", "tozalik_xodimi", "non_bolimi", "kolbasa_saryog", "muzlatilgan",
    "oshpaz", "mevachi",
)
LEGACY_SECTION = "legacy"
# Tizim roli -> lavozim chek-listi bo'limi. Faqat aniq mos keladiganlar; boshqa rollar uchun TAXMIN QILINMAYDI.
CHECKLIST_BY_ROLE = {"kassir": "kassir", "tozalik": "tozalik_xodimi"}
QUOTE_MAX_CHARS = 220
PAGE_MAX_CHARS = 3500

_RULE_REFERENCE_RE = re.compile(r"(?<!\d)(\d{1,2})\s*[-\s]?\s*(?:chi\s+)?nizom|nizom\s*(?:raqami|№|#)?\s*(\d{1,2})", re.IGNORECASE)


def checklist_section_for_role(role_key: str | None) -> str | None:
    return CHECKLIST_BY_ROLE.get(role_key or "")


def _section_of(rule: dict) -> str:
    source_key = rule.get("source_key")
    return source_key.split(":", 1)[0] if source_key else LEGACY_SECTION


def _is_candidate(rule: dict) -> bool:
    if rule.get("catalog_kind") == "bonus_model":
        return False
    return not (rule.get("content") or "").startswith("Eslatma:")  # faqat izoh qatori — buzish bandi emas


def get_catalog_entries(*, candidates_only: bool = True) -> list[dict]:
    """Butun katalog: har bir faol band + uning ball variantlari. ``amount_status``: ``options`` (variantlar bor) |
    ``default`` (bitta tasdiqlangan miqdor) | ``none`` (miqdor belgilanmagan — taxminiy ball YO'Q)."""
    rules = discipline_repo.list_active_rules()
    options_by_rule: dict[int, list[dict]] = {}
    for option in discipline_repo.list_penalty_options():
        options_by_rule.setdefault(option["rule_number"], []).append(option)

    entries = []
    for rule in rules:
        legacy = rule.get("catalog_kind") is None
        if candidates_only and legacy and rule.get("default_penalty_amount") is None:
            continue  # eski, miqdori tasdiqlanmagan band — minus katalogida emas (avvalgi xulq)
        entry = dict(rule)
        entry["section"] = _section_of(rule)
        entry["options"] = options_by_rule.get(rule["rule_number"], [])
        entry["display_number"] = rule["rule_number"] if rule.get("catalog_kind") == "nizom" else None
        entry["source_name"] = rule.get("source_name") or "Nizomlar (eski)"
        if entry["options"]:
            entry["amount_status"] = "options"
        elif rule.get("default_penalty_amount") is not None:
            entry["amount_status"] = "default"
        else:
            entry["amount_status"] = "none"
        if candidates_only and not _is_candidate(rule):
            continue
        entries.append(entry)
    return entries


def get_catalog_entry(rule_number: int) -> dict | None:
    return next((entry for entry in get_catalog_entries() if entry["rule_number"] == rule_number), None)


def list_catalog_sources(entries: list[dict] | None = None) -> list[dict]:
    entries = get_catalog_entries() if entries is None else entries
    order = {section: index for index, section in enumerate((*SOURCE_ORDER, LEGACY_SECTION))}
    grouped: dict[str, dict] = {}
    for entry in entries:
        group = grouped.setdefault(entry["section"], {"section": entry["section"], "name": entry["source_name"], "count": 0})
        group["count"] += 1
    return sorted(grouped.values(), key=lambda group: order.get(group["section"], 99))


def entries_in_section(section: str, entries: list[dict] | None = None) -> list[dict]:
    entries = get_catalog_entries() if entries is None else entries
    return [entry for entry in entries if entry["section"] == section]


def entry_amount_text(entry: dict) -> str:
    if entry["amount_status"] == "default":
        return f"−{entry['default_penalty_amount']} ball"
    if entry["amount_status"] == "options":
        return "ball: " + ", ".join(f"−{option['points']}" for option in entry["options"])
    return "Ball miqdori belgilanmagan"


def default_quote(entry: dict) -> str:
    """Tanlash oynasi uchun qisqa iqtibos: bandning O'ZIDAN aynan olingan bo'lak (variant sharti yoki matn boshi)."""
    options = entry.get("options") or []
    source = options[0]["condition_text"] if options else (entry.get("content") or "")
    first = next((line for line in source.split("\n") if line.strip()), "")
    return _cut_quote(first)


def _cut_quote(text: str) -> str:
    text = text.strip()
    if len(text) <= QUOTE_MAX_CHARS:
        return text
    cut = text[:QUOTE_MAX_CHARS].rsplit(" ", 1)[0].rstrip()
    return cut + "…"  # "…" — qisqartirish belgisi; iqtibosning o'zi asl matn boshi


def verified_quote(entry: dict, proposed: str | None) -> str | None:
    """AI taklif qilgan iqtibos bandning kanonik matnidan (sarlavha yoki mazmun) AYNAN topilsagina qabul qilinadi;
    aks holda ``None`` (server o'zi aniq bo'lakni tanlaydi)."""
    if not proposed or not proposed.strip():
        return None
    needle = proposed.strip()
    if needle in (entry.get("content") or "") or needle in (entry.get("title") or ""):
        return _cut_quote(needle)
    return None


def split_text_pages(text: str, limit: int = PAGE_MAX_CHARS) -> list[str]:
    """Matnni Telegram limitiga sig'adigan sahifalarga bo'ladi — HECH NARSA qisqartirilmaydi: sahifalar '\\n' bilan
    ulanganda asl matn tiklanadi (juda uzun yagona satr qat'iy bo'laklanadi)."""
    pages: list[str] = []
    current: list[str] = []
    size = 0
    for line in text.split("\n"):
        pieces = [line[i:i + limit] for i in range(0, len(line), limit)] or [""]
        for piece in pieces:
            extra = len(piece) + (1 if current else 0)
            if current and size + extra > limit:
                pages.append("\n".join(current))
                current, size = [], 0
                extra = len(piece)
            current.append(piece)
            size += extra
    pages.append("\n".join(current))
    return pages


def parse_rule_reference(text: str) -> int | None:
    """"26-nizomga amal qilmadi" kabi aniq murojaat. Faqat "nizom" so'zi bilan kelgan raqam hisoblanadi
    (oddiy vaqt/miqdor raqamlari bandni belgilamaydi). Raqam bandni belgilaydi, ballni emas."""
    match = _RULE_REFERENCE_RE.search(text or "")
    if match is None:
        return None
    number = int(match.group(1) or match.group(2))
    rule = discipline_repo.get_rule_by_number(number)
    if rule is None or rule.get("catalog_kind") not in (None, "nizom"):
        return None
    return number
