"""``services/recruiting_card.py`` — Founder karta v2 formatlash
testlari. Real Telegram sinovida topilgan muammo: nomzod yozgan XOM
matn kartaga aynan ko'chirilgan edi — bu fayl kartadagi qisqartirish
va "Asl javoblar" alohida ko'rinishini tekshiradi."""

import json

from services import recruiting_card


def _assessment(overall_result="INTERVIEW_RECOMMENDED", red_flags=None, clarify_questions=None, criteria=None):
    return {
        "criteria_scores_json": json.dumps(criteria or [{"key": "tajriba", "label": "Tegishli tajriba", "score": 2, "evidence": "yaxshi"}]),
        "strengths_json": json.dumps(["Tegishli tajriba"]),
        "risks_json": json.dumps([]),
        "red_flags_json": json.dumps(red_flags or []),
        "clarify_questions_json": json.dumps(clarify_questions or []),
        "overall_result": overall_result,
        "ai_summary": "Qisqa xulosa.",
        "source": "deterministic",
    }


def _application(**overrides):
    base = {
        "full_name": "Ali Valiyev",
        "phone": "+998901234567",
        "residence_area": "Toshkent",
        "preferred_branch": "Chilonzor",
        "birth_year": 1998,
        "prev_employer_text": "ABC do'koni",
        "experience_duration_text": "2 yil",
        "leave_reason_text": "Uyga yaqinroq joy kerak edi",
        "pos_experience": 1,
        "reference_check_consent": 1,
        "shift_preference": "kunduzgi",
        "unavailable_days_text": "yo'q",
        "holiday_available": 1,
        "expected_salary": "4 million",
        "start_date_text": "Bir hafta ichida",
        "fit_result": "fit",
        "fit_reason": None,
        "commute_issue": 0,
        "accommodation_needed": 0,
    }
    base.update(overrides)
    return base


def _vacancy():
    return {"title": "Kassir", "position_key": "kassir"}


def _rubric_version():
    return {"version": 2}


def test_card_shows_birth_date():
    application = _application(birth_day=15, birth_month=10, birth_year=1998)
    text = recruiting_card.format_candidate_card(application, _vacancy(), _assessment(), _rubric_version(), [])
    assert "🎂 Tug'ilgan sana:" in text
    assert "15 oktabr 1998" in text


def test_card_computes_age_correctly_from_birth_date():
    import company_time

    today = company_time.today()
    # Tug'ilgan kuni aynan bugun bo'lgan nomzod uchun yosh doim aniq
    # butun son bo'ladi — test qachon ishga tushirilishidan qat'i nazar.
    birth_year = today.year - 25
    application = _application(birth_day=today.day, birth_month=today.month, birth_year=birth_year)
    text = recruiting_card.format_candidate_card(application, _vacancy(), _assessment(), _rubric_version(), [])
    assert "25 yosh" in text


def test_card_truncates_long_raw_evidence_text():
    long_text = "Bu juda uzun va tartibsiz javob. " * 20
    criteria = [{"key": "tajriba", "label": "Tegishli tajriba", "score": 2, "evidence": long_text}]
    text = recruiting_card.format_candidate_card(_application(), _vacancy(), _assessment(criteria=criteria), _rubric_version(), [])
    assert long_text not in text
    assert "…" in text


def test_card_shows_red_flags_prominently_when_present():
    red_flags = [{"key": "expired_product", "label": "Muddati o'tgan mahsulotni sotishga tayyor", "evidence": "sotaman"}]
    text = recruiting_card.format_candidate_card(
        _application(), _vacancy(), _assessment(overall_result="NEEDS_HUMAN_REVIEW", red_flags=red_flags), _rubric_version(), []
    )
    assert "QIZIL XAVFLAR" in text
    assert "Muddati o'tgan mahsulotni sotishga tayyor" in text


def test_card_shows_no_red_flag_section_when_none_present():
    text = recruiting_card.format_candidate_card(_application(), _vacancy(), _assessment(), _rubric_version(), [])
    assert "QIZIL XAVFLAR" not in text


def test_card_shows_clarify_questions_when_present():
    text = recruiting_card.format_candidate_card(
        _application(), _vacancy(), _assessment(clarify_questions=["Kamomad haqida savolga aniqroq javob kerak"]), _rubric_version(), []
    )
    assert "aniqlashtirilishi kerak" in text.lower()
    assert "Kamomad haqida savolga aniqroq javob kerak" in text


def test_card_shows_fit_mismatch_reason():
    application = _application(fit_result="mismatch", fit_reason="Yoshi qonuniy minimal talabdan kichik.")
    text = recruiting_card.format_candidate_card(application, _vacancy(), _assessment(overall_result="REQUIREMENT_MISMATCH"), _rubric_version(), [])
    assert "Mos emas" in text
    assert "Yoshi qonuniy minimal talabdan kichik." in text


def test_format_raw_answers_contains_full_untouched_text():
    long_raw = "xatoli yozilgan javob bo'lsa ham to'liq ko'rinishi kerak!!! juda uzun bo'lsa ham"
    answers = [
        {"question_key": "kassir_muddat", "question_text": "Muddati o'tgan mahsulot?", "answer_text": long_raw, "is_follow_up": False},
    ]
    text = recruiting_card.format_raw_answers(_application(), answers)
    assert long_raw in text  # AI/qisqartirish YO'Q — asl matn to'liq


def test_format_raw_answers_marks_follow_up_entries():
    answers = [
        {"question_key": "kassir_login", "question_text": "Savol?", "answer_text": "Beraman", "is_follow_up": False},
        {"question_key": "kassir_login", "question_text": "Aniqlashtirish?", "answer_text": "Yo'q, bermayman", "is_follow_up": True},
    ]
    text = recruiting_card.format_raw_answers(_application(), answers)
    assert "aniqlashtirish" in text.lower()


def test_format_raw_answers_handles_no_answers_without_crashing():
    text = recruiting_card.format_raw_answers(_application(), [])
    assert text
