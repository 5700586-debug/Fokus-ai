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

_YES_NO = {1: "ha", 0: "yo'q", None: "-"}


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


def _signals(risks: list[dict], red_flags: list[dict]) -> list[str]:
    """Qizil bayroqlar (kritik) + past baholangan (lekin kritik
    KATEGORIYAGA kirmaydigan) mezonlar — bitta ro'yxat, kritiklari
    birinchi, jami 3 tadan oshmaydi. ``risks`` (``recruiting_scoring``dan)
    red-flag mezonlarini ALLAQACHON chetlab o'tgan — shuning uchun bu
    yerda takrorlanish yo'q (Founder bir xil signalni ikki marta
    ko'rmasligi kerak)."""
    signals = [flag["label"] for flag in red_flags]
    for risk in risks:
        signals.append(f"{risk['criterion']}: {_sanitize(risk['evidence'], 50)}")
    return signals[:3]


def format_candidate_card(
    application: dict,
    vacancy: dict,
    assessment: dict,
    rubric_version: dict,
    follow_up_questions: list[str],
) -> str:
    strengths = json.loads(assessment["strengths_json"])
    risks = json.loads(assessment.get("risks_json") or "[]")
    red_flags = json.loads(assessment.get("red_flags_json") or "[]")
    clarify_questions = json.loads(assessment.get("clarify_questions_json") or "[]")

    shift = application.get("shift_preference")
    schedule_bits = []
    if shift:
        schedule_bits.append(f"{shift} smena")
    schedule_bits.append(f"bayramda: {_YES_NO.get(application.get('holiday_available'), '-')}")

    experience_bits = [_sanitize(application.get("prev_employer_text"), 50)]
    if application.get("experience_duration_text"):
        experience_bits.append(_sanitize(application.get("experience_duration_text"), 20))
    leave_reason = _sanitize(application.get("leave_reason_text"), 60)

    lines = [
        f"🧑‍💼 {_sanitize(application.get('full_name'), 50)} — {vacancy['title']}",
        f"📞 {application.get('phone') or '-'}   🏢 {_sanitize(application.get('preferred_branch'), 30)}",
        f"📋 {', '.join(experience_bits)} — \"{leave_reason}\"",
        f"💰 Oldingi: {application.get('prev_salary_text') or '-'} → Kutilayotgan: {application.get('expected_salary') or '-'}",
        f"🕒 {', '.join(schedule_bits)}",
    ]

    if application.get("fit_result") == "mismatch":
        lines.append(f"📐 Talabga mos emas: {_sanitize(application.get('fit_reason'), 60)}")

    lines.append("")
    lines.append("✅ Kuchli tomonlar:" if strengths else "✅ Kuchli tomonlar: aniqlanmadi")
    for strength in strengths[:3]:
        lines.append(f"• {strength}")

    signals = _signals(risks, red_flags)
    if signals:
        lines.append("")
        lines.append("⚠️ Xavf/signallar:")
        for signal in signals:
            lines.append(f"• {signal}")

    if clarify_questions:
        lines.append("")
        lines.append("❓ Aniqlashtirish kerak:")
        for question in clarify_questions[:3]:
            lines.append(f"• {question}")

    lines.append("")
    lines.append(f"🤖 AI xulosasi: {assessment.get('ai_summary') or '-'}")
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
