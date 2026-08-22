"""Fokus HR — RBAC izolyatsiyasi (Founder-only ko'rib chiqish), tugma
ikki marta bosilishi (idempotentlik) va vakansiya boshqaruvi uchun
testlar."""

import pytest

from config import FOUNDER_ID
from repositories import recruiting as recruiting_repo
from services import recruiting_privacy
from tests.bot_harness import send, send_callback

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


ORDINARY_EMPLOYEE_ID = 500001
UNKNOWN_USER_ID = 500002


def _texts_to(sent, chat_id: int) -> list[str]:
    result = []
    for method in sent:
        if getattr(method, "chat_id", None) != chat_id:
            continue
        t = getattr(method, "text", None) or getattr(method, "caption", None)
        if t:
            result.append(t)
    return result


def _create_awaiting_review_application(candidate_id: int) -> int:
    kassir = recruiting_repo.get_vacancy_by_key("kassir")
    application_id = recruiting_repo.create_application(
        candidate_id, kassir["id"], recruiting_privacy.compute_retention_expiry()
    )
    recruiting_repo.record_consent(application_id)
    recruiting_repo.update_application(application_id, full_name="Test Nomzod", current_step="submitted", status="awaiting_review")
    rubric_id = recruiting_repo.create_rubric_version("kassir", 1, [{"key": "x", "label": "X"}])
    recruiting_repo.save_assessment(
        application_id, rubric_id, "INTERVIEW_RECOMMENDED", [{"key": "x", "score": 2, "evidence": "y"}], ["y"], [], None, "deterministic"
    )
    return application_id


# ------------------------------------------------------------------- RBAC --


async def test_unknown_user_cannot_manage_vacancies(bot_dp):
    main, bot = bot_dp

    sent = await send(main.dp, bot, UNKNOWN_USER_ID, text="/vacancies")
    texts_out = _texts_to(sent, UNKNOWN_USER_ID)
    assert not any("Kassir" in t or "Sotuvchi" in t for t in texts_out)


async def test_ordinary_employee_cannot_manage_vacancies(bot_dp):
    import roles

    main, bot = bot_dp
    roles.set_role(ORDINARY_EMPLOYEE_ID, "kassir", set_by=FOUNDER_ID)

    sent = await send(main.dp, bot, ORDINARY_EMPLOYEE_ID, text="/vacancies")
    texts_out = _texts_to(sent, ORDINARY_EMPLOYEE_ID)
    assert not any("Kassir (" in t or "sotuvchi)" in t for t in texts_out)


async def test_founder_can_manage_vacancies(bot_dp):
    main, bot = bot_dp

    sent = await send(main.dp, bot, FOUNDER_ID, text="/vacancies")
    texts_out = _texts_to(sent, FOUNDER_ID)
    assert any("kassir" in t.lower() for t in texts_out)
    assert any("sotuvchi" in t.lower() for t in texts_out)


async def test_ordinary_employee_cannot_decide_on_application(bot_dp):
    import roles

    main, bot = bot_dp
    roles.set_role(ORDINARY_EMPLOYEE_ID, "kassir", set_by=FOUNDER_ID)
    application_id = _create_awaiting_review_application(600001)

    await send_callback(
        main.dp, bot, ORDINARY_EMPLOYEE_ID, f"rec_interview:{application_id}", target_chat_id=FOUNDER_ID
    )

    application = recruiting_repo.get_application(application_id)
    assert application["founder_decision"] is None


async def test_founder_can_decide_on_application(bot_dp):
    main, bot = bot_dp
    application_id = _create_awaiting_review_application(600002)

    await send_callback(main.dp, bot, FOUNDER_ID, f"rec_interview:{application_id}", target_chat_id=FOUNDER_ID)

    application = recruiting_repo.get_application(application_id)
    assert application["founder_decision"] == "interview"
    assert application["founder_decision_by"] == FOUNDER_ID
    assert application["status"] == "reviewed"


# --------------------------------------------------------- idempotentlik --


async def test_double_click_on_decision_button_is_a_no_op_the_second_time(bot_dp):
    main, bot = bot_dp
    application_id = _create_awaiting_review_application(600003)

    first = await send_callback(main.dp, bot, FOUNDER_ID, f"rec_interview:{application_id}", target_chat_id=FOUNDER_ID)
    second = await send_callback(main.dp, bot, FOUNDER_ID, f"rec_reject:{application_id}", target_chat_id=FOUNDER_ID)

    application = recruiting_repo.get_application(application_id)
    # Birinchi qaror qoladi — ikkinchi (allaqachon ko'rib chiqilgan)
    # bosilish uni "rejected"ga o'zgartirmasligi kerak.
    assert application["founder_decision"] == "interview"
    assert first and second  # ikkalasi ham javob yubordi (masalan alert)


async def test_decision_on_unknown_application_does_not_crash(bot_dp):
    main, bot = bot_dp
    sent = await send_callback(main.dp, bot, FOUNDER_ID, "rec_interview:999999", target_chat_id=FOUNDER_ID)
    assert sent  # AnswerCallbackQuery (alert) yuborilgan bo'lishi kerak, xato emas


# --------------------------------------------------------------- post-hire --


async def test_founder_hire_creates_active_employee_with_role_branch_and_auto_menu(bot_dp):
    """Post-hire oqimi: "🎯 Ishga olish" bosilgach nomzod MAVJUD
    employee/role mexanizmi orqali aktiv xodimga aylanishi, lavozim va
    filiali biriktirilishi, "👥 Xodimlar" ro'yxatida (``roles.list_users``
    orqali) darhol ko'rinishi va /start so'ramasdan o'z menyusini
    avtomatik olishi kerak — Recruiting tarixi (``founder_decision``)
    alohida saqlanadi.
    """
    import employees
    import roles

    main, bot = bot_dp
    candidate_id = 600006
    application_id = _create_awaiting_review_application(candidate_id)
    recruiting_repo.update_application(
        application_id, phone="+998901112233", residence_area="Toshkent",
        preferred_branch="Chilonzor filiali",
    )

    sent = await send_callback(main.dp, bot, FOUNDER_ID, f"rec_hire:{application_id}", target_chat_id=FOUNDER_ID)

    assert roles.get_role(candidate_id) == "kassir"
    profile = employees.get_profile(candidate_id)
    assert profile["status"] == "approved"
    assert profile["role_key"] == "kassir"
    assert profile["branch"] == "Chilonzor filiali"
    assert candidate_id in roles.list_users()

    candidate_messages = [m for m in sent if getattr(m, "chat_id", None) == candidate_id]
    assert len(candidate_messages) == 1
    assert "/start" not in candidate_messages[0].text
    assert candidate_messages[0].reply_markup is not None

    application = recruiting_repo.get_application(application_id)
    assert application["founder_decision"] == "hired"


async def test_double_hire_click_does_not_crash_or_duplicate(bot_dp):
    main, bot = bot_dp
    candidate_id = 600007
    application_id = _create_awaiting_review_application(candidate_id)

    first = await send_callback(main.dp, bot, FOUNDER_ID, f"rec_hire:{application_id}", target_chat_id=FOUNDER_ID)
    second = await send_callback(main.dp, bot, FOUNDER_ID, f"rec_hire:{application_id}", target_chat_id=FOUNDER_ID)

    assert first and second  # ikkalasi ham javob yubordi, xato emas

    import employees

    profile = employees.get_profile(candidate_id)
    assert profile["status"] == "approved"


def test_set_founder_decision_if_only_claims_when_status_matches():
    """Atomic guard: ikkita "parallel worker" bir xil arizani bir
    vaqtda "Ishga olish" deb band qilishga urinsa (masalan ikki xil
    bot worker yoki ikki marta tez ketma-ket bosilgan tugma), faqat
    BIRINCHISI muvaffaqiyatli bo'lishi kerak.
    """
    application_id = _create_awaiting_review_application(700001)

    first = recruiting_repo.set_founder_decision_if(application_id, "awaiting_review", "hired", 999)
    second = recruiting_repo.set_founder_decision_if(application_id, "awaiting_review", "hired", 888)

    assert first is True
    assert second is False

    application = recruiting_repo.get_application(application_id)
    assert application["founder_decision_by"] == 999  # ikkinchisi qayta yozmadi
    assert application["status"] == "reviewed"


async def test_hire_does_not_touch_employees_when_application_already_claimed(bot_dp):
    """Regressiya (multi-worker idempotency): agar ariza allaqachon
    (masalan parallel boshqa worker tomonidan) "band qilingan" bo'lsa,
    ``handle_hire`` ``employees.submit_profile``ga UMUMAN yetib
    bormasligi kerak — xodim yozuvi yaratilmaydi/tegilmaydi, rol
    berilmaydi, nomzodga xabar yuborilmaydi.
    """
    main, bot = bot_dp
    candidate_id = 700002
    application_id = _create_awaiting_review_application(candidate_id)

    # "Boshqa worker" arizani allaqachon band qilgan deb simulyatsiya qilamiz.
    claimed = recruiting_repo.set_founder_decision_if(application_id, "awaiting_review", "hired", 999999)
    assert claimed is True

    import employees
    import roles

    sent = await send_callback(main.dp, bot, FOUNDER_ID, f"rec_hire:{application_id}", target_chat_id=FOUNDER_ID)

    assert employees.get_profile(candidate_id) is None
    assert roles.get_role(candidate_id) is None
    assert [m for m in sent if getattr(m, "chat_id", None) == candidate_id] == []


# --------------------------------------------------------- karta manzili --


async def test_founder_card_never_targets_a_group_chat():
    """Karta doim ``FOUNDER_ID`` shaxsiy chatiga yuboriladi — bu
    ``recruiting_bot._run_assessment_and_notify_founder`` kodida
    qattiq yozilgan, guruh/kanal chat_id bilan almashtirilmaydi."""
    import inspect

    import recruiting_bot

    source = inspect.getsource(recruiting_bot._run_assessment_and_notify_founder)
    assert "FOUNDER_ID" in source
    assert "group_chat_id" not in source


async def test_more_questions_button_shows_phone_and_follow_ups_to_founder_only(bot_dp):
    import roles

    main, bot = bot_dp
    roles.set_role(ORDINARY_EMPLOYEE_ID, "kassir", set_by=FOUNDER_ID)
    application_id = _create_awaiting_review_application(600004)
    recruiting_repo.update_application(application_id, phone="+998900000000")

    denied = await send_callback(
        main.dp, bot, ORDINARY_EMPLOYEE_ID, f"rec_question:{application_id}", target_chat_id=FOUNDER_ID
    )
    assert not any("+998900000000" in (getattr(m, "text", "") or "") for m in denied)

    allowed = await send_callback(main.dp, bot, FOUNDER_ID, f"rec_question:{application_id}", target_chat_id=FOUNDER_ID)
    assert any("+998900000000" in (getattr(m, "text", "") or "") for m in allowed)


async def test_raw_answers_button_shows_full_text_to_founder_only(bot_dp):
    import roles

    main, bot = bot_dp
    roles.set_role(ORDINARY_EMPLOYEE_ID, "kassir", set_by=FOUNDER_ID)
    application_id = _create_awaiting_review_application(600005)
    recruiting_repo.add_answer(
        application_id, "kassir_muddat", "Muddati o'tgan mahsulot?",
        "juda xatoli va uzun asl javob matni bo'lsin",
    )

    denied = await send_callback(
        main.dp, bot, ORDINARY_EMPLOYEE_ID, f"rec_raw:{application_id}", target_chat_id=FOUNDER_ID
    )
    assert not any("juda xatoli va uzun asl javob matni" in (getattr(m, "text", "") or "") for m in denied)

    allowed = await send_callback(main.dp, bot, FOUNDER_ID, f"rec_raw:{application_id}", target_chat_id=FOUNDER_ID)
    assert any("juda xatoli va uzun asl javob matni" in (getattr(m, "text", "") or "") for m in allowed)
