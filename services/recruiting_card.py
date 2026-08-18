"""Founderning shaxsiy chatiga yuboriladigan yopiq nomzod kartasi.

Karta faqat Founderga (yoki rekruting vakolati bor HR'ga) yuboriladi —
xodimlar guruhiga yoki ommaviy kanalga HECH QACHON chiqmaydi (qarang
``recruiting_bot.py``dagi yuborish nuqtasi — doim ``FOUNDER_ID``ga).

Real Telegram sinovida topilgan muammo: nomzod yozgan XOM (uzun,
imlo xatoli) matn kartaga aynan ko'chirilgan edi. Endi karta faqat
QISQARTIRILGAN (``_sanitize`` — bo'sh joy/tinish belgilarini tozalash,
MA'NOSI o'zgartirilmaydi, AI orqali "qayta yozish" ATAYLAB qilinmaydi —
bu nomzod fikrini buzish xavfini keltirib chiqarardi) parchani
ko'rsatadi. Asl, to'liq matn DB'da har doim o'zgarishsiz saqlanadi
(``repositories/recruiting.get_answers``) va Founder alohida "📄 Asl
javoblar" tugmasi orqali to'liq ko'rishi mumkin (qarang
``recruiting_bot.py``dagi ``rec_raw:`` callback)."""

import json
import re

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

_RESULT_LABELS = {
    "INTERVIEW_RECOMMENDED": "✅ Suhbatga tavsiya etiladi",
    "NEEDS_HUMAN_REVIEW": "🕵️ Qo'lda ko'rib chiqish kerak",
    "REQUIREMENT_MISMATCH": "⚠️ Talabga mos kelmaydi",
}

_FIT_LABELS = {
    "fit": "✅ Mos",
    "mismatch": "⚠️ Mos emas",
}

_YES_NO = {1: "ha", 0: "yo'q", None: "-"}

_RETENTION_LABELS = {
    "6oygacha": "6 oygacha",
    "6_12oy": "6-12 oy",
    "1yil_plus": "1 yil va undan ko'p",
}


def _score_bar(score: int | None) -> str:
    return {0: "❌", 1: "◐", 2: "✅", None: "➖"}.get(score, "?")


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


def format_candidate_card(
    application: dict,
    vacancy: dict,
    assessment: dict,
    rubric_version: dict,
    follow_up_questions: list[str],
) -> str:
    criteria_scores = json.loads(assessment["criteria_scores_json"])
    strengths = json.loads(assessment["strengths_json"])
    red_flags = json.loads(assessment.get("red_flags_json") or "[]")
    clarify_questions = json.loads(assessment.get("clarify_questions_json") or "[]")

    result_label = _RESULT_LABELS.get(assessment["overall_result"], assessment["overall_result"])
    fit_result = application.get("fit_result")
    fit_label = _FIT_LABELS.get(fit_result, "❓ Aniqlanmadi")

    lines = [
        f"🧑‍💼 Nomzod kartasi — {vacancy['title']}",
        "",
        f"👤 {_sanitize(application.get('full_name'), 60)}",
        f"📞 {application.get('phone') or '-'}   📍 {_sanitize(application.get('residence_area'), 40)}   🏢 {_sanitize(application.get('preferred_branch'), 40)}",
        f"🎂 Tug'ilgan yil: {application.get('birth_year') or '-'} (ballga ta'sir qilmaydi — faqat qonuniy yosh tekshiruvi uchun)",
        "",
        f"📋 Tajriba: {_sanitize(application.get('prev_employer_text'), 80)}"
        + (f" ({_sanitize(application.get('experience_duration_text'), 30)})" if application.get("experience_duration_text") else ""),
        f"🚪 Ketish sababi: {_sanitize(application.get('leave_reason_text'), 80)}",
        f"💳 POS/kassa tajribasi: {_YES_NO.get(application.get('pos_experience'), '-')}",
        f"📞 Tavsiyanoma uchun bog'lanishga rozi: {_YES_NO.get(application.get('reference_check_consent'), '-')}",
        "",
        f"🕒 Smena: {application.get('shift_preference') or '-'}   "
        f"Ishlay olmaydigan kunlar: {_sanitize(application.get('unavailable_days_text'), 40)}   "
        f"Bayramda: {_YES_NO.get(application.get('holiday_available'), '-')}",
        f"💰 Oldingi oylik: {application.get('prev_salary_text') or '-'}   "
        f"Kutilayotgan oylik: {application.get('expected_salary') or '-'}",
        f"📅 Boshlash sanasi: {application.get('start_date_text') or '-'}   "
        f"Ishlash niyati: {_RETENTION_LABELS.get(application.get('retention_intent'), '-')}",
    ]

    if application.get("retention_intent") == "6oygacha" and application.get("retention_intent_reason"):
        lines.append(f"   ↳ Sababi: {_sanitize(application.get('retention_intent_reason'), 80)}")
    if application.get("commute_issue"):
        lines.append("🚌 Filialgacha qatnovda muammo bor deb belgiladi.")
    if application.get("accommodation_needed"):
        lines.append(f"🤝 Qulaylik so'ragan: {_sanitize(application.get('accommodation_text'), 80)}")
    if application.get("attendance_barrier_text") and application["attendance_barrier_text"].strip().lower() not in ("yo'q", "yoq", "-"):
        lines.append(f"🗓 Muntazam kelishga xalaqit: {_sanitize(application.get('attendance_barrier_text'), 80)}")

    lines += [
        "",
        f"📐 Talab mosligi: {fit_label}" + (f" — {application.get('fit_reason')}" if fit_result == "mismatch" and application.get("fit_reason") else ""),
        f"📊 Natija: {result_label}",
        "",
        "Mezonlar bo'yicha ball:",
    ]
    for criterion in criteria_scores:
        lines.append(f"  {_score_bar(criterion['score'])} {criterion['label']} — {_sanitize(criterion['evidence'])}")

    lines.append("")
    lines.append("💪 Kuchli tomonlar:" if strengths else "💪 Kuchli tomonlar: aniqlanmadi")
    for strength in strengths:
        lines.append(f"  • {strength}")

    if red_flags:
        lines.append("")
        lines.append("🚩 QIZIL XAVFLAR (majburiy inson tekshiruvi):")
        for flag in red_flags:
            lines.append(f"  • {flag['label']}: {_sanitize(flag['evidence'])}")

    if clarify_questions:
        lines.append("")
        lines.append("❓ Suhbatda aniqlashtirilishi kerak:")
        for question in clarify_questions[:4]:
            lines.append(f"  • {question}")

    if follow_up_questions:
        lines.append("")
        lines.append("💬 Suhbat davomida so'ralgan qo'shimcha savollar:")
        for question in follow_up_questions[:3]:
            lines.append(f"  • {question}")

    if application.get("substance_policy_agree") is not None or application.get("criminal_record") is not None:
        lines.append("")
        lines.append("ℹ️ Qo'shimcha ma'lumot (ball emas, faqat Founder ko'rib chiqishi uchun):")
        if application.get("substance_policy_agree") is not None:
            lines.append(f"  • Ichimlik/chekish qoidasiga rozi: {_YES_NO.get(application.get('substance_policy_agree'))}")
        if application.get("criminal_record") is not None:
            lines.append(f"  • Sudlanganlik: {_YES_NO.get(application.get('criminal_record'))} (avtomatik qaror emas)")

    if application.get("candidate_photo_file_id"):
        lines.append("")
        lines.append("📷 Nomzod rasmi yuqorida alohida yuborildi.")

    lines.append("")
    lines.append(f"🤖 AI xulosasi: {assessment.get('ai_summary') or '-'}")
    lines.append("")
    lines.append(f"Rubrika versiyasi: {rubric_version['version']} | Tahlil manbasi: {assessment['source']}")
    lines.append(
        "\n⚠️ Bu faqat AI/deterministik TAVSIYA — yakuniy ishga olish yoki rad etish "
        "qarorini FAQAT siz (yoki vakolatli HR) qabul qilasiz."
    )

    return "\n".join(lines)


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
