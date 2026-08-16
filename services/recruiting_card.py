"""Founderning shaxsiy chatiga yuboriladigan yopiq nomzod kartasi.

Karta faqat Founderga (yoki rekruting vakolati bor HR'ga) yuboriladi —
xodimlar guruhiga yoki ommaviy kanalga HECH QACHON chiqmaydi (qarang
``recruiting_bot.py``dagi yuborish nuqtasi — doim ``FOUNDER_ID``ga).
"""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

_RESULT_LABELS = {
    "INTERVIEW_RECOMMENDED": "✅ Suhbatga tavsiya etiladi",
    "NEEDS_HUMAN_REVIEW": "🕵️ Qo'lda ko'rib chiqish kerak",
    "REQUIREMENT_MISMATCH": "⚠️ Talabga mos kelmaydi",
}


def _score_bar(score: int) -> str:
    return {0: "❌", 1: "◐", 2: "✅"}.get(score, "?")


def format_candidate_card(
    application: dict,
    vacancy: dict,
    assessment: dict,
    rubric_version: dict,
    follow_up_questions: list[str],
) -> str:
    import json

    criteria_scores = json.loads(assessment["criteria_scores_json"])
    strengths = json.loads(assessment["strengths_json"])
    risks = json.loads(assessment["risks_json"])

    result_label = _RESULT_LABELS.get(assessment["overall_result"], assessment["overall_result"])

    lines = [
        f"🧑‍💼 Nomzod kartasi — {vacancy['title']}",
        "",
        f"👤 F.I.Sh.: {application.get('full_name') or '-'}",
        f"📞 Telefon: {application.get('phone') or '-'}",
        f"📋 Tajriba: {application.get('experience_text') or '-'}",
        f"🕒 Ish jadvaliga moslik: {application.get('availability_text') or '-'}",
        f"📅 Ish boshlash sanasi: {application.get('start_date_text') or '-'}",
        "",
        f"📊 Natija: {result_label}",
        "",
        "Mezonlar bo'yicha ball:",
    ]
    for criterion in criteria_scores:
        lines.append(f"  {_score_bar(criterion['score'])} {criterion['label']} — {criterion['evidence']}")

    lines.append("")
    lines.append("💪 Kuchli tomonlar:" if strengths else "💪 Kuchli tomonlar: aniqlanmadi")
    for strength in strengths:
        lines.append(f"  • {strength}")

    if risks:
        lines.append("")
        lines.append("⚠️ Xavf/noaniqlik:")
        for risk in risks:
            lines.append(f"  • {risk['criterion']}: {risk['evidence']}")

    if follow_up_questions:
        lines.append("")
        lines.append("❓ Suhbatda so'rash mumkin bo'lgan savollar:")
        for question in follow_up_questions[:3]:
            lines.append(f"  • {question}")

    lines.append("")
    lines.append(f"🤖 AI xulosasi: {assessment.get('ai_summary') or '-'}")
    lines.append("")
    lines.append(f"Rubrika versiyasi: {rubric_version['version']} | Tahlil manbasi: {assessment['source']}")
    lines.append(
        "\n⚠️ Bu faqat AI/deterministik TAVSIYA — yakuniy ishga olish yoki rad etish "
        "qarorini FAQAT siz (yoki vakolatli HR) qabul qilasiz."
    )

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
        ]
    )
