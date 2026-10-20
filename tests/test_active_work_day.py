"""Nazoratchining FAOL ish kuni: yopilmagan kun avtomatik davom etadi, yopilgach keyingisi ochiladi. Vaqt boshqariladi,
lokal DB, Telegram mock. Kassa kodiga tegilmaydi."""

import asyncio
from datetime import datetime, timedelta

import pytest

import company_time
import db
import discipline_bot
import employees
from config import FOUNDER_ID, RECRUITING_BRANCH_NAMES
from repositories import discipline as discipline_repo
from services import attendance as attendance_service
from services import discipline, nazoratchi_day
from tests.bot_harness import send, send_callback

pytestmark = pytest.mark.anyio

A, B = RECRUITING_BRANCH_NAMES[0], RECRUITING_BRANCH_NAMES[1]
SUP = 1
SUP2 = 2
D = "2026-03-10"


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _ymd(iso: str) -> str:
    return iso.replace("-", "")


def _shift(iso: str, days: int) -> str:
    return (datetime.fromisoformat(iso) + timedelta(days=days)).date().isoformat()


def _pin(monkeypatch, iso: str, hour: int = 12, minute: int = 0) -> datetime:
    tz = discipline_bot._resolve_timezone()
    year, month, day = (int(part) for part in iso.split("-"))
    fixed = datetime(year, month, day, hour, minute, tzinfo=tz)

    class _Fixed(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed.astimezone(tz) if tz else fixed

    monkeypatch.setattr(discipline_bot, "datetime", _Fixed)
    monkeypatch.setattr(company_time, "now", lambda: fixed)
    return fixed


def _supervisor(user_id: int = SUP) -> None:
    from roles import set_role

    set_role(user_id, "nazoratchi", set_by=FOUNDER_ID)


def _employee(user_id: int, branch: str, surname: str) -> None:
    from roles import set_role

    set_role(user_id, "sotuvchi", set_by=FOUNDER_ID)
    employees.submit_profile(user_id, {"familiya": surname, "ism": "T", "branch": branch, "role_key": "sotuvchi", "contacts": []})
    employees.approve_profile(user_id, approved_by=FOUNDER_ID)


def _work(user_id: int, iso: str) -> None:
    attendance_service.set_scheduled_work_shift(user_id, iso, "09:00", "18:00", "test")


def _setup_two_branches() -> None:
    _supervisor()
    _employee(111, A, "Alisher")
    _employee(222, B, "Botir")


def _session_dates() -> list[tuple[str, str, str]]:
    conn = db.get_connection()
    try:
        rows = conn.execute("SELECT branch, session_date, status FROM nazoratchi_branch_sessions ORDER BY session_date, branch").fetchall()
    finally:
        conn.close()
    return [(r["branch"], r["session_date"], r["status"]) for r in rows]


def _closures() -> int:
    conn = db.get_connection()
    try:
        return conn.execute("SELECT COUNT(*) FROM daily_closures").fetchone()[0]
    finally:
        conn.close()


def _text(sent) -> str:
    return "\n".join(m.text for m in sent if getattr(m, "text", None))


# ----------------------------------------------------------- faol kun --


async def test_open_day_is_continued_next_calendar_day_and_survives_midnight_and_restart(bot_dp, monkeypatch):
    main, bot = bot_dp
    _setup_two_branches()
    _pin(monkeypatch, D, 23, 50)
    nazoratchi_day.open_session(SUP, A, D)

    for iso, hour, minute in ((D, 23, 59), (_shift(D, 1), 0, 10), (_shift(D, 1), 9, 0)):  # yarim tun va "restart" (yangi hisob)
        _pin(monkeypatch, iso, hour, minute)
        day = nazoratchi_day.active_day(SUP, discipline_bot._now_company())
        assert (day.work_date, day.closed) == (D, False)

    sent = await send(main.dp, bot, SUP, text="/baholash")
    assert f"📅 Ish kuni: 10.03.2026" in sent[0].text and "Avval shu ish kunini yakunlaymiz." in sent[0].text


async def test_entering_alone_never_closes_penalizes_or_creates_sessions(bot_dp, monkeypatch):
    main, bot = bot_dp
    _setup_two_branches()
    _pin(monkeypatch, _shift(D, 3))
    nazoratchi_day.open_session(SUP, A, D)
    before = _session_dates()

    await send(main.dp, bot, SUP, text="/baholash")
    await send(main.dp, bot, SUP, text="/kunniyop")

    assert _session_dates() == before and _closures() == 0
    assert discipline.get_salary(SUP)["bonus_bank"] == 0


async def test_one_closed_branch_does_not_close_the_day_or_open_the_next(bot_dp, monkeypatch):
    main, bot = bot_dp
    _setup_two_branches()
    _pin(monkeypatch, _shift(D, 1))
    for user, branch in ((111, A), (222, B)):
        _work(user, D)
    discipline.record_daily_grade(111, SUP, D, discipline.GRADE_NORMA)
    nazoratchi_day.open_session(SUP, A, D)

    assert nazoratchi_day.close_session(SUP, A, D).closed is True  # faqat A yopildi; B tekshirilmagan

    assert _closures() == 0
    day = nazoratchi_day.active_day(SUP, discipline_bot._now_company())
    assert (day.work_date, day.resumed) == (D, True)  # keyingi kun ochilmadi
    sent = await send(main.dp, bot, SUP, text="/baholash")
    assert [b.text for row in sent[0].reply_markup.inline_keyboard for b in row][0].startswith("✅")  # A yopilgan belgisi


async def test_closing_all_coverage_branches_closes_day_then_next_work_date_opens_without_inventing_days(bot_dp, monkeypatch):
    main, bot = bot_dp
    _setup_two_branches()
    today = _shift(D, 3)
    _pin(monkeypatch, today)
    for user in (111, 222):
        _work(user, D)
        discipline.record_daily_grade(user, SUP, D, discipline.GRADE_NORMA)
    future = _shift(today, 2)
    nazoratchi_day.open_session(SUP, A, future)  # kelajak sanasi e'tiborsiz qoladi
    nazoratchi_day.open_session(SUP, A, D)
    assert nazoratchi_day.active_day(SUP, discipline_bot._now_company()).work_date == D

    assert nazoratchi_day.close_session(SUP, A, D).closed and nazoratchi_day.close_session(SUP, B, D).closed

    assert discipline.get_closure(SUP, D) is not None
    day = nazoratchi_day.active_day(SUP, discipline_bot._now_company())
    assert (day.work_date, day.resumed, day.closed) == (today, False, False)  # joriy ish kuni, oraliq kunlarsiz
    assert {row[1] for row in _session_dates()} == {D, future}  # oradagi/kelajak kunlar yaratilmagan


async def test_closed_current_day_is_not_reopened_and_new_day_not_started_message(bot_dp, monkeypatch):
    main, bot = bot_dp
    _setup_two_branches()
    _pin(monkeypatch, D)
    for user in (111, 222):
        _work(user, D)
        discipline.record_daily_grade(user, SUP, D, discipline.GRADE_NORMA)
    nazoratchi_day.close_session(SUP, A, D)
    nazoratchi_day.close_session(SUP, B, D)
    sessions_before = _session_dates()

    sent = await send(main.dp, bot, SUP, text="/baholash")

    assert "Bu ish kuni yopilgan" in sent[0].text and sent[0].reply_markup is None
    sent = await send_callback(main.dp, bot, SUP, data=f"bos:br:0:{_ymd(D)}", target_chat_id=SUP)
    assert "Bu ish kuni yopilgan" in _text(sent)
    assert _session_dates() == sessions_before and _closures() == 1


# ------------------------------------------------- baho/yopish aynan faol kunga --


async def test_grades_go_to_the_active_work_date_even_on_the_next_calendar_day(bot_dp, monkeypatch):
    main, bot = bot_dp
    _setup_two_branches()
    _pin(monkeypatch, _shift(D, 1), 0, 20)
    _work(111, D)
    nazoratchi_day.open_session(SUP, A, D)

    await send_callback(main.dp, bot, SUP, data=f"bos:grade:111:{discipline.GRADE_NORMA}:{_ymd(D)}", target_chat_id=SUP)
    assert discipline.get_daily_grade(111, D) is not None and discipline.get_daily_grade(111, _shift(D, 1)) is None

    # nzr_* (filial -> xodim kartasi) oqimi ham faol kunga yozadi
    await send_callback(main.dp, bot, SUP, data=f"nzr_grade:111:{discipline.GRADE_ALO}", target_chat_id=SUP)
    assert discipline.get_daily_grade(111, D)["grade_key"] == discipline.GRADE_ALO
    assert discipline.get_daily_grade(111, _shift(D, 1)) is None
    sent = await send_callback(main.dp, bot, SUP, data="nzr_emp:111", target_chat_id=SUP)
    assert "📅 Ish kuni: 10.03.2026" in _text(sent) and "Avval shu ish kunini yakunlaymiz." in _text(sent)


async def test_branch_screen_shows_date_branch_and_ungraded_count(bot_dp, monkeypatch):
    main, bot = bot_dp
    _setup_two_branches()
    _pin(monkeypatch, D)
    _work(111, D)

    sent = await send_callback(main.dp, bot, SUP, data=f"bos:br:0:{_ymd(D)}", target_chat_id=SUP)

    head = sent[0].text.split("\n")[:3]
    assert head == ["📅 Ish kuni: 10.03.2026", f"🏬 Filial: {A}", "Baholanmagan: 1"]


async def test_stale_foreign_future_and_duplicate_callbacks_write_nothing(bot_dp, monkeypatch):
    import roles

    main, bot = bot_dp
    _setup_two_branches()
    monkeypatch.setitem(roles._USERS, SUP2, {"role": "nazoratchi", "added_by": FOUNDER_ID, "added_at": "2026-01-01T00:00:00+00:00"})
    _pin(monkeypatch, _shift(D, 1))
    _work(111, D)
    nazoratchi_day.open_session(SUP, A, D)
    grade = f"bos:grade:111:{discipline.GRADE_NORMA}"

    for caller, ymd in ((SUP, _ymd(_shift(D, 1))), (SUP, _ymd(_shift(D, 5))), (SUP2, _ymd(D))):  # eskirgan/kelajak/begona
        sent = await send_callback(main.dp, bot, caller, data=f"{grade}:{ymd}", target_chat_id=caller)
        assert "Bu tugma eskirgan" in _text(sent) or "yopilgan" in _text(sent)
    assert discipline.get_daily_grade(111, D) is None and discipline.get_daily_grade(111, _shift(D, 1)) is None

    discipline.record_daily_grade(111, SUP, D, discipline.GRADE_NORMA)
    _work(222, D)
    discipline.record_daily_grade(222, SUP, D, discipline.GRADE_NORMA)
    await asyncio.gather(*(send_callback(main.dp, bot, SUP, data=f"bos:close:0:{_ymd(D)}", target_chat_id=SUP) for _ in range(2)))
    await send_callback(main.dp, bot, SUP, data=f"bos:close:1:{_ymd(D)}", target_chat_id=SUP)
    await send_callback(main.dp, bot, SUP, data=f"bos:close:1:{_ymd(D)}", target_chat_id=SUP)  # takroriy
    assert _closures() == 1 and [row for row in _session_dates() if row[2] == "closed"].__len__() == 2


async def test_closed_branch_session_does_not_accept_new_grades(bot_dp, monkeypatch):
    main, bot = bot_dp
    _setup_two_branches()
    _pin(monkeypatch, D)
    _work(111, D)
    discipline.record_daily_grade(111, SUP, D, discipline.GRADE_NORMA)
    nazoratchi_day.close_session(SUP, A, D)  # B hali ochiq: kun faol, lekin A yopilgan

    sent = await send_callback(main.dp, bot, SUP, data=f"bos:grade:111:{discipline.GRADE_ALO}:{_ymd(D)}", target_chat_id=SUP)

    assert "Bu filial shu ish kunida yopilgan" in _text(sent)
    assert discipline.get_daily_grade(111, D)["grade_key"] == discipline.GRADE_NORMA


async def test_blockers_are_named_and_never_bypassed(bot_dp, monkeypatch):
    main, bot = bot_dp
    _setup_two_branches()
    _employee(113, A, "Nograf")
    _pin(monkeypatch, _shift(D, 1))
    _work(111, D)  # ishda, baholanmagan; 113 — grafik yo'q
    nazoratchi_day.open_session(SUP, A, D)

    sent = await send_callback(main.dp, bot, SUP, data=f"bos:close:0:{_ymd(D)}", target_chat_id=SUP)

    text = _text(sent)
    assert "Yopib bo'lmaydi" in text and "Alisher" in text and "Nograf" in text and "10.03.2026" in text
    assert discipline.get_daily_grade(111, D) is None and discipline.get_daily_grade(113, D) is None  # avtomatik baho yo'q
    assert _closures() == 0 and discipline_repo.get_branch_session(SUP, A, D)["status"] == "open"


# ------------------------------------------------------- PR #54 bilan uyg'unlik --


async def test_resumed_open_day_window_does_not_cause_extra_penalty_with_the_auto_audit(bot_dp, monkeypatch):
    main, bot = bot_dp
    _setup_two_branches()
    nazoratchi_day.open_session(SUP, A, D)
    _pin(monkeypatch, _shift(D, 1), 21, 0)  # D muddati (20:00) o'tgan, D yopilmagan

    class _Bot:
        async def send_message(self, *args, **kwargs):
            return None

    await discipline_bot._day_close_tick(_Bot())
    await send(main.dp, bot, SUP, text="/baholash")  # oyna ochilishi minus yaratmaydi
    await discipline_bot._day_close_tick(_Bot())

    # Avtomatik minus PR #54 siyosati bo'yicha joriy ish kuni (D+1, muddat 20:00 o'tgan) uchun BIR marta; ochiq D oynasi
    # (faol kun) o'zi minus yaratmaydi va backfill yo'q.
    conn = db.get_connection()
    try:
        audits = [row["audit_date"] for row in conn.execute("SELECT audit_date FROM supervisor_audit").fetchall()]
    finally:
        conn.close()
    assert audits == [_shift(D, 1)] and discipline.get_salary(SUP)["bonus_bank"] == -40
