from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

import calibration_bot
from config import COMPANY_TIMEZONE, FOUNDER_ID
from tests.bot_harness import send, send_callback

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _company_today() -> str:
    """``calibration_bot`` kompaniya vaqt zonasidagi sanadan foydalanadi
    (talab #9) — server naive ``date.today()``dan farq qilishi mumkin
    (masalan server UTC'da, kompaniya Asia/Tashkent'da), shuning uchun
    testlar ham shu bilan solishtiradi.
    """
    return datetime.now(ZoneInfo(COMPANY_TIMEZONE)).date().isoformat()


def _submit_profile(user_id: int, role_key: str, familiya: str = "Test") -> None:
    import employees

    employees.submit_profile(
        user_id,
        {
            "familiya": familiya, "ism": "User", "otasining_ismi": "Otasi",
            "branch": None, "role_key": role_key, "contacts": [],
        },
    )


async def _approve(main, bot, user_id: int, role_key: str, familiya: str = "Test"):
    _submit_profile(user_id, role_key, familiya)
    return await send_callback(main.dp, bot, FOUNDER_ID, data=f"approve:{user_id}", target_chat_id=FOUNDER_ID)


def _make_question_time_now() -> None:
    from services import rules as rules_service

    rules_service.set_rule("calibration.daily_question_time", "00:00", updated_by=FOUNDER_ID)


async def test_approving_taminotchi_creates_session_without_sending_question(bot_dp):
    main, bot = bot_dp

    sent = await _approve(main, bot, 111, "taminotchi")

    from repositories import baselines as repo

    session = repo.get_session(111)
    assert session is not None
    assert session["role_key"] == "taminotchi"

    # Approval callback faqat standart tasdiqlash xabarini yuboradi —
    # kalibratsiya savoli darhol yuborilmaydi.
    kassir_texts = [getattr(m, "text", None) for m in sent if getattr(m, "chat_id", None) == 111]
    assert all("tasdiqlandi" in (t or "").lower() for t in kassir_texts)


async def test_approving_haydovchi_creates_session(bot_dp):
    main, bot = bot_dp
    await _approve(main, bot, 111, "haydovchi")

    from repositories import baselines as repo

    assert repo.get_session(111) is not None


async def test_approving_nazoratchi_does_not_create_session(bot_dp):
    main, bot = bot_dp
    await _approve(main, bot, 111, "nazoratchi")

    from repositories import baselines as repo

    assert repo.get_session(111) is None


async def test_scheduler_sends_first_question_within_window(bot_dp):
    main, bot = bot_dp
    _make_question_time_now()
    await _approve(main, bot, 111, "taminotchi")

    await calibration_bot._daily_tick(bot)

    from repositories import baselines as repo

    today = _company_today()
    questions = repo.get_questions_for_date(111, today)
    assert len(questions) == 1
    assert questions[0]["answer_text"] is None


async def test_scheduler_respects_configured_send_time(bot_dp):
    main, bot = bot_dp
    from services import rules as rules_service

    rules_service.set_rule("calibration.daily_question_time", "23:59", updated_by=FOUNDER_ID)
    await _approve(main, bot, 111, "taminotchi")

    await calibration_bot._daily_tick(bot)

    from repositories import baselines as repo

    assert repo.get_questions_for_date(111, _company_today()) == []


async def test_scheduler_restart_does_not_duplicate_first_question(bot_dp):
    main, bot = bot_dp
    _make_question_time_now()
    await _approve(main, bot, 111, "taminotchi")

    await calibration_bot._daily_tick(bot)
    await calibration_bot._daily_tick(bot)  # "scheduler qayta ishga tushdi"

    from repositories import baselines as repo

    questions = repo.get_questions_for_date(111, _company_today())
    assert len(questions) == 1


async def test_scheduler_finds_pre_existing_approved_employee(bot_dp):
    """Talab #7: bu feature qo'shilishidan oldin approve qilingan xodim
    ham scheduler tomonidan topilishi kerak — ``on_employee_approved``
    chaqirilmagan bo'lsa ham.
    """
    main, bot = bot_dp
    import employees
    from roles import set_role

    _submit_profile(222, "haydovchi")
    employees.approve_profile(222, approved_by=FOUNDER_ID)
    set_role(222, "haydovchi", set_by=FOUNDER_ID)
    # E'tibor bering: calibration_bot.on_employee_approved(...) ATAYLAB chaqirilmadi.

    from repositories import baselines as repo

    assert repo.get_session(222) is None  # hali sessiya yo'q

    _make_question_time_now()
    await calibration_bot._daily_tick(bot)

    assert repo.get_session(222) is not None
    assert len(repo.get_questions_for_date(222, _company_today())) == 1


async def test_window_expired_employee_gets_no_questions(bot_dp):
    main, bot = bot_dp
    import employees
    from roles import set_role

    _submit_profile(333, "taminotchi")
    employees.approve_profile(333, approved_by=FOUNDER_ID)
    set_role(333, "taminotchi", set_by=FOUNDER_ID)

    conn_profile = employees.get_profile(333)
    from db import get_connection

    conn = get_connection()
    try:
        conn.execute(
            "UPDATE employees SET approved_at = ? WHERE user_id = ?",
            ("2020-01-01T00:00:00+00:00", 333),
        )
        conn.commit()
    finally:
        conn.close()

    _make_question_time_now()
    await calibration_bot._daily_tick(bot)

    from repositories import baselines as repo

    assert repo.get_questions_for_date(333, _company_today()) == []


async def test_answer_routes_to_active_question_and_advances(bot_dp):
    main, bot = bot_dp
    _make_question_time_now()
    await _approve(main, bot, 111, "taminotchi")
    await calibration_bot._daily_tick(bot)

    from repositories import baselines as repo

    today = _company_today()
    first_question = repo.get_active_question(111)
    assert first_question is not None

    sent = await send(main.dp, bot, 111, text="Bugun uchta bozorni aylanib, narxlarni yozib qo'ydim")

    answered = repo.get_question(first_question["id"])
    assert answered["answer_text"] == "Bugun uchta bozorni aylanib, narxlarni yozib qo'ydim"

    plan_length = len(calibration_bot._get_daily_plan(111, "taminotchi", today))
    if plan_length > 1:
        active = repo.get_active_question(111)
        assert active is not None
        assert active["id"] != first_question["id"]
    else:
        assert "tugadi" in sent[0].text.lower()


async def test_vague_answer_triggers_follow_up_then_finalizes(bot_dp):
    main, bot = bot_dp
    _make_question_time_now()
    await _approve(main, bot, 111, "taminotchi")
    await calibration_bot._daily_tick(bot)

    from repositories import baselines as repo

    question_id = repo.get_active_question(111)["id"]

    sent = await send(main.dp, bot, 111, text="ha")
    assert "aniqroq" in sent[0].text.lower()
    question = repo.get_question(question_id)
    assert question["follow_up_count"] == 1
    assert question["answer_text"] is None
    assert repo.get_active_question(111)["id"] == question_id  # hali shu savol faol

    sent = await send(main.dp, bot, 111, text="ok")
    question = repo.get_question(question_id)
    assert question["follow_up_count"] == 2
    assert question["answer_text"] is None

    # Ikkinchi follow-up limitiga yetdi (MAX_FOLLOW_UPS=2) — endi mavhum
    # bo'lsa ham javob yakunlanadi.
    sent = await send(main.dp, bot, 111, text="ok")
    question = repo.get_question(question_id)
    assert question["answer_text"] == "ok"


async def test_calibration_question_filter_ignores_users_without_active_question(bot_dp):
    main, bot = bot_dp

    sent = await send(main.dp, bot, FOUNDER_ID, text="Savol matni")

    assert sent == []


async def test_cross_check_discrepancy_notifies_founder(bot_dp):
    main, bot = bot_dp
    _make_question_time_now()

    await _approve(main, bot, 111, "taminotchi", familiya="Taminotchiyev")
    await _approve(main, bot, 222, "haydovchi", familiya="Haydovchiyev")

    await calibration_bot._daily_tick(bot)

    from repositories import baselines as repo

    q1 = repo.get_active_question(111)
    q2 = repo.get_active_question(222)
    assert q1["is_cross_check"]
    assert q2["is_cross_check"]
    assert q1["question_text"] == q2["question_text"]

    await send(main.dp, bot, 111, text="Chorsu bozoriga borib, kartoshka oldik")
    sent = await send(main.dp, bot, 222, text="Beshqozon bozoriga borib, piyoz oldik")

    founder_messages = [m for m in sent if getattr(m, "chat_id", None) == FOUNDER_ID]
    assert len(founder_messages) == 1
    assert "tafovut" in founder_messages[0].text.lower()


async def test_cross_check_matching_answers_no_discrepancy(bot_dp):
    main, bot = bot_dp
    _make_question_time_now()

    await _approve(main, bot, 111, "taminotchi")
    await _approve(main, bot, 222, "haydovchi")

    await calibration_bot._daily_tick(bot)

    await send(main.dp, bot, 111, text="Chorsu bozoriga borib, kartoshka oldik")
    sent = await send(main.dp, bot, 222, text="Chorsu bozoriga borib, kartoshka oldik")

    founder_messages = [m for m in sent if getattr(m, "chat_id", None) == FOUNDER_ID]
    assert founder_messages == []


async def test_resolve_timezone_falls_back_to_utc_when_tzdata_missing(monkeypatch):
    """Render kabi minimal muhitlarda ``tzdata`` yo'q bo'lsa
    ``ZoneInfo(COMPANY_TIMEZONE)`` xato ko'taradi — bu butun botning
    ishga tushishini yiqitmasligi, faqat UTC'ga qaytishi kerak.
    """
    from datetime import timezone as dt_timezone

    def raise_zoneinfo_not_found(name):
        raise Exception("simulated ZoneInfoNotFoundError: no tzdata")

    monkeypatch.setattr(calibration_bot, "ZoneInfo", raise_zoneinfo_not_found)

    tz = calibration_bot._resolve_timezone()
    assert tz == dt_timezone.utc


async def test_start_scheduler_survives_missing_tzdata(monkeypatch):
    """``start_scheduler`` (main.py ichida bot ishga tushishidan oldin
    chaqiriladi) tzdata yo'q holatda ham xato ko'tarmasligi kerak —
    aks holda butun bot ishga tushmay qoladi.
    """
    def raise_zoneinfo_not_found(name):
        raise Exception("simulated ZoneInfoNotFoundError: no tzdata")

    monkeypatch.setattr(calibration_bot, "ZoneInfo", raise_zoneinfo_not_found)

    class _FakeBot:
        pass

    scheduler = calibration_bot.start_scheduler(_FakeBot())
    try:
        assert scheduler.running is True
    finally:
        scheduler.shutdown(wait=False)


async def test_approval_confirmation_survives_calibration_session_failure(bot_dp, monkeypatch):
    """Kalibratsiya sessiyasini yaratishda kutilmagan xato bo'lsa ham,
    Founder va yangi xodim odatdagi tasdiqlash xabarini olishi kerak —
    ikkinchi darajali funksiya asosiy approval oqimini bloklamasin.
    """
    main, bot = bot_dp

    def raise_error(*args, **kwargs):
        raise RuntimeError("simulated calibration failure")

    monkeypatch.setattr(calibration_bot, "on_employee_approved", raise_error)

    sent = await _approve(main, bot, 111, "taminotchi")

    applicant_messages = [m for m in sent if getattr(m, "chat_id", None) == 111]
    assert any("tasdiqlandi" in (getattr(m, "text", None) or "").lower() for m in applicant_messages)

    from employees import get_profile

    assert get_profile(111)["status"] == "approved"
