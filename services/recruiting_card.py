"""Founderning shaxsiy chatiga yuboriladigan yopiq nomzod kartasi.

Karta faqat Founderga (yoki rekruting vakolati bor HR'ga) yuboriladi —
xodimlar guruhiga yoki ommaviy kanalga HECH QACHON chiqmaydi (qarang
``recruiting_bot.py``dagi yuborish nuqtasi — doim ``FOUNDER_ID``ga).

Real Telegram sinovida topilgan ikkita muammo bu yerda tuzatilgan:

1. Nomzod yozgan XOM (uzun, imlo xatoli) matn kartaga aynan
   ko'chirilgan edi. Endi karta faqat QISQARTIRILGAN (``_sanitize`` —
   bo'sh joy/tinish belgilarini tozalash, MA'NOSI o'zgartirilmaydi, AI
   orqali "qayta yozish" ATAYLAB qilinmaydi) parchani ko'rsatadi. Asl,
   to'liq matn DB'da har doim o'zgarishsiz saqlanadi
   (``repositories/recruiting.get_answers``) va Founder alohida "📄 Asl
   javoblar" tugmasi orqali to'liq ko'rishi mumkin.
2. Karta juda uzun edi (to'liq mezonlar jadvali, texnik maydonlar).
   Endi Founder 15-20 soniyada o'qib tushunadigan QISQA xulosa
   ko'rinishida — faqat eng kerakli maydonlar, ✅/⚠️/❓ ro'yxatlari
   3 tadan oshmaydi. Kritik red flag bo'lsa, alohida juda qisqa
   ogohlantirish (``format_critical_alert``) ASOSIY kartadan OLDIN
   yuboriladi (qarang ``recruiting_bot.py``)."""

import json
import re

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import company_time

_YES_NO = {1: "ha", 0: "yo'q", None: "-"}

_MONTH_NUMBER_TO_NAME = {
    1: "yanvar", 2: "fevral", 3: "mart", 4: "aprel", 5: "may", 6: "iyun",
    7: "iyul", 8: "avgust", 9: "sentabr", 10: "oktabr", 11: "noyabr", 12: "dekabr",
}

_RETENTION_LABELS = {
    "6oygacha": "6 oygacha",
    "6_12oy": "6-12 oy",
    "1yil_plus": "1 yil va undan ko'p",
}

_RESULT_DISPLAY = {
    "INTERVIEW_RECOMMENDED": "🟢 Mos",
    "NEEDS_HUMAN_REVIEW": "🟡 Qo'lda ko'rib chiqish kerak",
    "REQUIREMENT_MISMATCH": "🔴 Mos emas",
}


def _sanitize(text: str | None, limit: int = 140) -> str:
    """Faqat DETERMINISTIK tozalash — ortiqcha bo'shliq/tinish belgisi
    yig'ilishi olib tashlanadi va uzun matn qisqartiriladi. Ma'no HECH
    QACHON o'zgartirilmaydi (AI qayta yozmaydi)."""
    text = (text or "").strip()
    if not text:
        return "-"
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"([!?.,]){2,}", r"\1", text)
    if text:
        text = text[0].upper() + text[1:]
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


_JOB_STABILITY_COUNT_RE = re.compile(r"(\d+)\s*(?:ta)?\s*(?:joy|ish\s*joy|tashkilot|kompaniya)")
_JOB_STABILITY_FIRST_JOB_PHRASES = ("birinchi ish", "hali ishlamaganman", "hali ishlamagan", "ishlamaganman")


def _job_stability_needs_clarification(text: str | None) -> bool:
    """Ko'p ish almashtirish AVTOMATIK red flag yoki rad etish mezoni
    EMAS (sabablari turlicha bo'lishi mumkin) — faqat Founder e'tibor
    qaratishi uchun yumshoq belgi. Ishonchli aniqlanmasa (raqam
    topilmasa), signal QO'YILMAYDI — xato taxmin qilishdan ko'ra
    jim turish xavfsizroq."""
    if not text:
        return False
    lowered = text.strip().lower()
    if any(phrase in lowered for phrase in _JOB_STABILITY_FIRST_JOB_PHRASES):
        return False
    match = _JOB_STABILITY_COUNT_RE.search(lowered)
    if not match:
        return False
    return int(match.group(1)) >= 3


def _format_birth_date_line(application: dict) -> str:
    """Nomzod allaqachon saqlagan ``birth_day``/``birth_month``/
    ``birth_year``dan (recruiting_bot.py'dagi parser natijasi) odam
    o'qiydigan qator quradi — yosh bugungi (kompaniya) sana bo'yicha
    hisoblanadi."""
    day = application.get("birth_day")
    month = application.get("birth_month")
    year = application.get("birth_year")
    if not (day and month and year):
        return "🎂 Tug'ilgan sana: -"

    month_name = _MONTH_NUMBER_TO_NAME.get(month, str(month))
    today = company_time.today()
    age = today.year - year - ((today.month, today.day) < (month, day))
    return f"🎂 Tug'ilgan sana: {day} {month_name} {year} — {age} yosh"


def _reason_text(overall_result: str, red_flags: list[dict], clarify_questions: list[str], fit_reason: str | None) -> str:
    """Tavsiya ostidagi bitta qisqa "Sabab:" qatori — DETERMINISTIK
    (AI matniga bog'liq emas, hech qachon uzun/texnik bo'lmaydi)."""
    if overall_result == "REQUIREMENT_MISMATCH" and fit_reason:
        return f"Sabab: {_sanitize(fit_reason, 70)}"
    if red_flags:
        if len(red_flags) == 1:
            return f"Sabab: {red_flags[0]['label']}."
        return f"Sabab: {len(red_flags)} ta jiddiy signal aniqlandi."
    if clarify_questions:
        return f"Sabab: {len(clarify_questions)} ta muhim savol aniqlashtirilishi kerak."
    if overall_result == "INTERVIEW_RECOMMENDED":
        return "Sabab: Javoblar ijobiy baholandi."
    return "Sabab: Qo'shimcha ma'lumot yetarli emas."


def format_candidate_card(
    application: dict,
    vacancy: dict,
    assessment: dict,
    rubric_version: dict,
    follow_up_questions: list[str],
) -> str:
    strengths = json.loads(assessment["strengths_json"])
    red_flags = json.loads(assessment.get("red_flags_json") or "[]")
    clarify_questions = json.loads(assessment.get("clarify_questions_json") or "[]")
    overall_result = assessment["overall_result"]

    shift = application.get("shift_preference")
    schedule_bits = []
    if shift:
        schedule_bits.append(f"{shift} smena")
    schedule_bits.append(f"bayramda: {_YES_NO.get(application.get('holiday_available'), '-')}")

    experience_bits = [_sanitize(application.get("prev_employer_text"), 50)]
    if application.get("experience_duration_text"):
        experience_bits.append(_sanitize(application.get("experience_duration_text"), 20))
    leave_reason = _sanitize(application.get("leave_reason_text"), 60)

    retention = _RETENTION_LABELS.get(application.get("retention_intent"), "-")
    if application.get("retention_intent") == "6oygacha" and application.get("retention_intent_reason"):
        retention += f" ({_sanitize(application.get('retention_intent_reason'), 40)})"

    lines = [
        f"🧑‍💼 {_sanitize(application.get('full_name'), 50)} — {vacancy['title']}",
        f"📞 {application.get('phone') or '-'}   🏢 {_sanitize(application.get('preferred_branch'), 30)}",
        _format_birth_date_line(application),
        f"📍 {_sanitize(application.get('residence_area'), 40)}",
        f"📋 {', '.join(experience_bits)} — \"{leave_reason}\"",
        f"💰 Oldingi: {application.get('prev_salary_text') or '-'} → Kutilayotgan: {application.get('expected_salary') or '-'}",
        f"🕒 {', '.join(schedule_bits)}",
        f"📅 Ish boshlash: {application.get('start_date_text') or '-'}",
        f"⏳ Ishlash niyati: {retention}",
        f"⏳ Oxirgi 2 yil: {_sanitize(application.get('job_stability_text'), 70)}",
    ]

    if application.get("fit_result") == "mismatch":
        lines.append(f"📐 Talabga mos emas: {_sanitize(application.get('fit_reason'), 60)}")

    lines.append("")
    lines.append("✅ Kuchli tomonlar:" if strengths else "✅ Kuchli tomonlar: aniqlanmadi")
    for strength in strengths[:3]:
        lines.append(f"• {strength}")

    lines.append("")
    if red_flags:
        lines.append("🚩 Red Flag:")
        for flag in red_flags[:3]:
            lines.append(f"• {flag['label']}")
    else:
        lines.append("🚩 Red Flag: aniqlanmadi")

    clarify_items = list(clarify_questions)
    if _job_stability_needs_clarification(application.get("job_stability_text")):
        clarify_items.append("⚠️ Ish barqarorligini aniqlashtirish kerak")
    if clarify_items:
        lines.append("")
        lines.append("❓ Aniqlashtirish kerak:")
        for question in clarify_items[:3]:
            lines.append(f"• {question}")

    lines.append("")
    lines.append(f"🤖 AI xulosasi: {assessment.get('ai_summary') or '-'}")

    lines.append("")
    lines.append(f"📊 Yakuniy tavsiya: {_RESULT_DISPLAY.get(overall_result, overall_result)}")
    lines.append(_reason_text(overall_result, red_flags, clarify_items, application.get("fit_reason")))

    lines.append("")
    lines.append("⚠️ Yakuniy qarorni siz qabul qilasiz.")

    return "\n".join(lines)


def format_critical_alert(application: dict, red_flags: list[dict]) -> str | None:
    """Kritik red flag bo'lsa — asosiy kartadan OLDIN yuboriladigan
    juda qisqa ogohlantirish (mavjud Founder xabar yuborish oqimidan
    foydalanadi, yangi notification tizimi qurilmagan)."""
    if not red_flags:
        return None
    name = _sanitize(application.get("full_name"), 40)
    if len(red_flags) == 1:
        reason = red_flags[0]["label"]
    else:
        reason = f"{red_flags[0]['label']} va yana {len(red_flags) - 1} ta signal"
    return f"🚨 Muhim signal: {name} — {reason}. Yakuniy qaror Founder'da."


def format_raw_answers(application: dict, answers: list[dict]) -> str:
    """To'liq, HECH QANDAY tahrirlanmagan asl javoblar — faqat Founder
    "📄 Asl javoblar" tugmasini bosganda, alohida xabarda ko'rsatiladi."""
    lines = [f"📄 Asl javoblar — {application.get('full_name') or '-'}", ""]
    for answer in answers:
        prefix = "  ↳ (aniqlashtirish) " if answer.get("is_follow_up") else "❓ "
        lines.append(f"{prefix}{answer['question_text']}")
        lines.append(f"   {answer['answer_text']}")
        lines.append("")
    if not answers:
        lines.append("(javoblar topilmadi)")
    return "\n".join(lines)


def candidate_review_keyboard(application_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📞 Suhbatga chaqirish", callback_data=f"rec_interview:{application_id}"),
                InlineKeyboardButton(text="❓ Qo'shimcha savol", callback_data=f"rec_question:{application_id}"),
            ],
            [
                InlineKeyboardButton(text="🗂 Ko'rib chiqish", callback_data=f"rec_reviewing:{application_id}"),
                InlineKeyboardButton(text="❌ Rad etish", callback_data=f"rec_reject:{application_id}"),
            ],
            [
                InlineKeyboardButton(text="📄 Asl javoblar", callback_data=f"rec_raw:{application_id}"),
            ],
        ]
    )
