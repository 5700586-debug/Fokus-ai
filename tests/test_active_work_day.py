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


async def test_old_open_day_continues_only_until_06_then_current_day_wins(bot_dp, monkeypatch):
    main, bot = bot_dp
    _setup_two_branches()
    nazoratchi_day.open_session(SUP, A, D)
    for iso, hour, minute in ((D, 23, 59), (_shift(D, 1), 0, 10), (_shift(D, 1), 5, 59)):
        _pin(monkeypatch, iso, hour, minute)
        day = nazoratchi_day.active_day(SUP, company_time.now())
        assert (day.work_date, day.closed) == (D, False)
    _pin(monkeypatch, _shift(D, 1), 6)
    day = nazoratchi_day.active_day(SUP, company_time.now())
    assert day.work_date == _shift(D, 1) and not day.resumed
    sent = await send(main.dp, bot, SUP, text="/baholash")
    assert "11.03.2026" in sent[0].text and "Avval shu ish kunini" not in sent[0].text


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


async def test_partial_old_day_stays_in_history_without_blocking_the_new_day(bot_dp, monkeypatch):
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
    assert (day.work_date, day.resumed) == (_shift(D, 1), False)  # Old partial day no longer blocks today.
    sent = await send(main.dp, bot, SUP, text="/baholash")
    assert not [b.text for row in sent[0].reply_markup.inline_keyboard for b in row][0].startswith("✅")  # Today A is new.


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
    assert nazoratchi_day.active_day(SUP, discipline_bot._now_company()).work_date == today

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
    await send_callback(main.dp, bot, SUP, data=f"nzr_grade:111:{discipline.GRADE_ALO}:{_ymd(D)}", target_chat_id=SUP)
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
    _pin(monkeypatch, D)
    _work(111, D)
    nazoratchi_day.open_session(SUP, A, D)
    grade = f"bos:grade:111:{discipline.GRADE_NORMA}"

    for caller, ymd in ((SUP, _ymd(_shift(D, 1))), (SUP, _ymd(_shift(D, 5))), (SUP2, _ymd(_shift(D, -1)))):  # eskirgan/kelajak/begona
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


async def test_ungraded_people_are_named_but_do_not_block_close(bot_dp, monkeypatch):
    main, bot = bot_dp
    _setup_two_branches()
    _employee(113, A, "Nograf")
    _pin(monkeypatch, D)
    _work(111, D)
    sent = await send_callback(main.dp, bot, SUP, data=f"bos:close:0:{_ymd(D)}", target_chat_id=SUP)
    text = _text(sent)
    assert "nazorati yopildi" in text and "Alisher" in text and "Nograf" in text and "baholanmadi" in text
    assert discipline.get_daily_grade(111, D) is None and discipline.get_daily_grade(113, D) is None
    assert _closures() == 0 and discipline_repo.get_branch_session(SUP, A, D)["status"] == "closed"


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
    assert audits == [] and discipline.get_salary(SUP)["bonus_bank"] == 0


# ------------------------------------- yopilgan tarixiy kun qayta ochilmaydi --


def _close_everything(day: str) -> None:
    for user, branch in ((111, A), (222, B)):
        _work(user, day)
        discipline.record_daily_grade(user, SUP, day, discipline.GRADE_NORMA)
        assert nazoratchi_day.close_session(SUP, branch, day).closed
    assert discipline.get_closure(SUP, day) is not None


def _add_new_branch_with_employee(monkeypatch) -> str:
    new_branch = "SATURN YANGI FILIAL"
    monkeypatch.setattr(nazoratchi_day, "RECRUITING_BRANCH_NAMES", [*RECRUITING_BRANCH_NAMES, new_branch])
    _employee(333, new_branch, "Yangi")
    return new_branch


def _snapshot() -> tuple:
    conn = db.get_connection()
    try:
        return (
            conn.execute("SELECT supervisor_id, closure_date, closed_at FROM daily_closures ORDER BY id").fetchall().__len__(),
            [tuple(r) for r in conn.execute("SELECT employee_id, eval_date, grade_key FROM daily_evaluations ORDER BY id").fetchall()],
            _session_dates(),
        )
    finally:
        conn.close()


async def test_new_branch_or_employee_never_reopens_a_closed_historical_or_current_day(bot_dp, monkeypatch):
    main, bot = bot_dp
    _setup_two_branches()
    _pin(monkeypatch, D)
    _close_everything(D)
    before = _snapshot()

    _add_new_branch_with_employee(monkeypatch)  # D yopilgandan keyin yangi filial + xodim qo'shildi
    _employee(444, A, "Yangi2")

    same_day = nazoratchi_day.active_day(SUP, discipline_bot._now_company())
    assert (same_day.work_date, same_day.closed) == (D, True)  # joriy yopilgan kun qayta ochilmaydi
    _pin(monkeypatch, _shift(D, 3))
    later = nazoratchi_day.active_day(SUP, discipline_bot._now_company())
    assert (later.work_date, later.resumed, later.closed) == (_shift(D, 3), False, False)  # tarixiy D faol emas
    assert _snapshot() == before  # closure, baho va sessiyalar o'zgarmagan, soxta closure yo'q


async def test_old_open_days_do_not_override_current_day_after_closed_history(bot_dp, monkeypatch):
    main, bot = bot_dp
    _setup_two_branches()
    d1, d2, d3 = D, _shift(D, 1), _shift(D, 2)
    _pin(monkeypatch, d1)
    _close_everything(d1)
    nazoratchi_day.open_session(SUP, A, d3)
    nazoratchi_day.open_session(SUP, A, d2)
    _add_new_branch_with_employee(monkeypatch)
    _pin(monkeypatch, _shift(D, 4))

    day = nazoratchi_day.active_day(SUP, discipline_bot._now_company())

    assert (day.work_date, day.resumed) == (_shift(D, 4), False)  # Old history is kept without hijacking today.


async def test_unclosed_day_still_requires_every_coverage_branch(bot_dp, monkeypatch):
    main, bot = bot_dp
    _setup_two_branches()
    _pin(monkeypatch, D)
    _work(111, D)
    discipline.record_daily_grade(111, SUP, D, discipline.GRADE_NORMA)
    assert nazoratchi_day.close_session(SUP, A, D).closed
    _add_new_branch_with_employee(monkeypatch)

    assert nazoratchi_day.day_fully_closed(SUP, D) is False and discipline.get_closure(SUP, D) is None
    assert nazoratchi_day.active_day(SUP, discipline_bot._now_company()).closed is False


# -------------------------------------------- baho tugmasi karta sanasiga bog'lanadi --


def _grade_buttons(sent) -> dict[str, str]:
    markup = next(m for m in sent if getattr(m, "reply_markup", None) is not None).reply_markup
    return {b.callback_data: b.text for row in markup.inline_keyboard for b in row if b.callback_data.startswith("nzr_grade:")}


def _notices(sent, chat_id: int) -> list:
    return [m for m in sent if getattr(m, "chat_id", None) == chat_id and getattr(m, "text", None) and "Baho" in m.text]


async def test_card_shows_work_date_and_every_grade_button_carries_it_within_64_bytes(bot_dp, monkeypatch):
    main, bot = bot_dp
    _supervisor()
    big = 7_952_886_089
    _employee(big, A, "Katta")
    _pin(monkeypatch, D)

    sent = await send_callback(main.dp, bot, SUP, data=f"nzr_emp:{big}", target_chat_id=SUP)

    assert "📅 Ish kuni: 10.03.2026" in sent[0].text
    buttons = _grade_buttons(sent)
    assert len(buttons) == 4
    assert all(data.endswith(f":{_ymd(D)}") and len(data.encode()) <= 64 for data in buttons)


async def test_stale_card_button_after_day_closed_writes_nothing_and_new_card_works(bot_dp, monkeypatch):
    main, bot = bot_dp
    _setup_two_branches()
    _pin(monkeypatch, D)
    sent = await send_callback(main.dp, bot, SUP, data="nzr_emp:111", target_chat_id=SUP)
    old_button = next(data for data in _grade_buttons(sent) if f":{discipline.GRADE_ALO}:" in data)
    _close_everything(D)  # D yopildi
    _pin(monkeypatch, _shift(D, 1))  # D+1 faol
    before = _snapshot()
    bank = discipline.get_salary(111)["bonus_bank"]

    sent = await send_callback(main.dp, bot, SUP, data=old_button, target_chat_id=SUP)

    assert "Bu tugma eskirgan — xodim kartasini qayta oching." in _text(sent) or "yopilgan" in _text(sent)
    assert _snapshot() == before and discipline.get_salary(111)["bonus_bank"] == bank
    assert _notices(sent, 111) == []  # xodimga xabar yo'q
    assert discipline.get_daily_grade(111, _shift(D, 1)) is None

    fresh = await send_callback(main.dp, bot, SUP, data="nzr_emp:111", target_chat_id=SUP)
    assert "📅 Ish kuni: 11.03.2026" in fresh[0].text
    new_button = next(data for data in _grade_buttons(fresh) if f":{discipline.GRADE_ALO}:" in data)
    assert new_button.endswith(_ymd(_shift(D, 1)))
    await send_callback(main.dp, bot, SUP, data=new_button, target_chat_id=SUP)
    assert discipline.get_daily_grade(111, _shift(D, 1))["grade_key"] == discipline.GRADE_ALO
    assert discipline.get_daily_grade(111, D)["grade_key"] == discipline.GRADE_NORMA  # D o'zgarmagan


@pytest.mark.parametrize(
    "suffix", ["", ":2026-03-10", ":20260399", ":abcdefgh", ":20260311", ":20260315", ":1234"],
)
async def test_undated_malformed_wrong_and_future_grade_buttons_are_rejected(bot_dp, monkeypatch, suffix):
    main, bot = bot_dp
    _setup_two_branches()
    _pin(monkeypatch, D)  # faol kun: D
    before = _snapshot()

    sent = await send_callback(main.dp, bot, SUP, data=f"nzr_grade:111:{discipline.GRADE_ALO}{suffix}", target_chat_id=SUP)

    assert "Bu tugma eskirgan — xodim kartasini qayta oching." in _text(sent)
    assert _snapshot() == before and discipline.get_salary(111)["bonus_bank"] == 0 and _notices(sent, 111) == []


async def test_closed_branch_card_button_is_rejected(bot_dp, monkeypatch):
    main, bot = bot_dp
    _setup_two_branches()
    _pin(monkeypatch, D)
    _work(111, D)
    discipline.record_daily_grade(111, SUP, D, discipline.GRADE_NORMA)
    nazoratchi_day.close_session(SUP, A, D)  # A yopildi, B ochiq: kun faol

    sent = await send_callback(main.dp, bot, SUP, data=f"nzr_grade:111:{discipline.GRADE_ALO}:{_ymd(D)}", target_chat_id=SUP)

    assert "Bu filial shu ish kunida yopilgan" in _text(sent)
    assert discipline.get_daily_grade(111, D)["grade_key"] == discipline.GRADE_NORMA


async def test_card_opened_before_midnight_still_grades_the_still_active_day_after_midnight(bot_dp, monkeypatch):
    main, bot = bot_dp
    _setup_two_branches()
    _pin(monkeypatch, D, 23, 50)
    nazoratchi_day.open_session(SUP, A, D)
    sent = await send_callback(main.dp, bot, SUP, data="nzr_emp:111", target_chat_id=SUP)
    button = next(data for data in _grade_buttons(sent) if f":{discipline.GRADE_NORMA}:" in data)

    _pin(monkeypatch, _shift(D, 1), 0, 20)  # yarim tundan keyin ham D faol
    await send_callback(main.dp, bot, SUP, data=button, target_chat_id=SUP)

    assert discipline.get_daily_grade(111, D)["grade_key"] == discipline.GRADE_NORMA
    assert discipline.get_daily_grade(111, _shift(D, 1)) is None


async def test_repeating_the_same_grade_press_adds_no_record_or_message(bot_dp, monkeypatch):
    main, bot = bot_dp
    _setup_two_branches()
    _pin(monkeypatch, D)
    button = f"nzr_grade:111:{discipline.GRADE_ALO}:{_ymd(D)}"

    first = await send_callback(main.dp, bot, SUP, data=button, target_chat_id=SUP)
    snapshot, bank = _snapshot(), discipline.get_salary(111)["bonus_bank"]
    second = await send_callback(main.dp, bot, SUP, data=button, target_chat_id=SUP)

    assert len(_notices(first, 111)) == 1 and _notices(second, 111) == []
    assert _snapshot() == snapshot and discipline.get_salary(111)["bonus_bank"] == bank


# ------------------------- "Filiallar -> xodim" baho yo'li ham filial sessiyasini ochadi --


def _sessions_of(branch: str, day: str) -> list[str]:
    return [status for b, d, status in _session_dates() if b == branch and d == day]


async def test_first_card_grade_opens_session_so_day_survives_midnight_and_restart(bot_dp, monkeypatch):
    main, bot = bot_dp
    _setup_two_branches()
    _pin(monkeypatch, D, 23, 50)
    sent = await send_callback(main.dp, bot, SUP, data="nzr_emp:111", target_chat_id=SUP)
    assert _session_dates() == []  # faqat kartani ko'rish sessiya yaratmaydi
    button = next(data for data in _grade_buttons(sent) if f":{discipline.GRADE_NORMA}:" in data)

    await send_callback(main.dp, bot, SUP, data=button, target_chat_id=SUP)

    assert _sessions_of(A, D) == ["open"] and _sessions_of(B, D) == []
    _pin(monkeypatch, _shift(D, 1), 0, 20)  # yarim tundan keyin; "restart" — holat faqat bazadan o'qiladi
    day = nazoratchi_day.active_day(SUP, discipline_bot._now_company())
    assert (day.work_date, day.resumed) == (D, False)

    # D kartasi tugmasi yarim tundan keyin ham D ga yozadi (D faol)
    await send_callback(main.dp, bot, SUP, data=f"nzr_grade:111:{discipline.GRADE_ALO}:{_ymd(D)}", target_chat_id=SUP)
    assert discipline.get_daily_grade(111, D)["grade_key"] == discipline.GRADE_ALO
    assert discipline.get_daily_grade(111, _shift(D, 1)) is None
    sent = await send(main.dp, bot, SUP, text="/baholash")
    assert "📅 Ish kuni: 10.03.2026" in sent[0].text and "Avval shu ish kunini yakunlaymiz." not in sent[0].text


async def test_existing_repeated_and_parallel_grading_never_duplicate_or_reopen_the_session(bot_dp, monkeypatch):
    main, bot = bot_dp
    _setup_two_branches()
    _employee(113, A, "Ikkinchi")
    _pin(monkeypatch, D)
    nazoratchi_day.open_session(SUP, A, D)  # mavjud sessiya qayta ishlatiladi

    for user in (111, 113, 111):  # ketma-ket va takroriy bosish (parallel poyga alohida thread testida)
        await send_callback(main.dp, bot, SUP, data=f"nzr_grade:{user}:{discipline.GRADE_NORMA}:{_ymd(D)}", target_chat_id=SUP)
    assert _sessions_of(A, D) == ["open"]

    # yopilgan sessiya qayta ochilmaydi (service darajasida ham)
    _work(111, D)
    _work(113, D)
    assert nazoratchi_day.close_session(SUP, A, D).closed
    discipline.record_daily_grade(111, SUP, D, discipline.GRADE_ALO, session_branch=A)
    assert _sessions_of(A, D) == ["closed"]


async def test_session_is_written_with_a_thread_race_exactly_once(bot_dp, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    _setup_two_branches()
    for user in (113, 114, 115):
        _employee(user, A, f"E{user}")
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda u: discipline.record_daily_grade(u, SUP, D, discipline.GRADE_NORMA, session_branch=A), (113, 114, 115)))
    assert _sessions_of(A, D) == ["open"]


async def test_repeat_same_grade_and_unknown_branch_and_historic_grades_create_no_session(bot_dp, monkeypatch):
    main, bot = bot_dp
    _setup_two_branches()
    _employee(555, "Noma'lum filial", "Begona")
    _pin(monkeypatch, D)
    discipline.record_daily_grade(111, SUP, D, discipline.GRADE_NORMA)  # tarixiy baho: sessiyasiz
    assert _session_dates() == []

    await send_callback(main.dp, bot, SUP, data=f"nzr_grade:111:{discipline.GRADE_NORMA}:{_ymd(D)}", target_chat_id=SUP)  # takroriy
    await send_callback(main.dp, bot, SUP, data=f"nzr_grade:555:{discipline.GRADE_NORMA}:{_ymd(D)}", target_chat_id=SUP)  # filial noma'lum

    assert _session_dates() == []  # backfill va taxminiy filial yo'q
    assert discipline.get_daily_grade(555, D) is not None


async def test_closed_day_or_branch_and_stale_button_write_neither_grade_nor_session(bot_dp, monkeypatch):
    main, bot = bot_dp
    _setup_two_branches()
    _pin(monkeypatch, D)
    _close_everything(D)
    before = _snapshot()

    for data in (
        f"nzr_grade:111:{discipline.GRADE_ALO}:{_ymd(D)}",          # kun yopilgan
        f"nzr_grade:111:{discipline.GRADE_ALO}:{_ymd(_shift(D, 1))}",  # kelajak
        f"nzr_grade:111:{discipline.GRADE_ALO}",                       # sanasiz
    ):
        await send_callback(main.dp, bot, SUP, data=data, target_chat_id=SUP)
    assert _snapshot() == before


@pytest.mark.parametrize("table", ["nazoratchi_branch_sessions", "bonus_bank_ledger", "daily_evaluation_history"])
async def test_grade_or_session_write_failure_rolls_everything_back(bot_dp, monkeypatch, table):
    _setup_two_branches()
    conn = db.get_connection()
    try:
        conn.execute(f"CREATE TRIGGER fokus_break BEFORE INSERT ON {table} BEGIN SELECT RAISE(ABORT, 'sinov xatosi'); END")
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(Exception):
        discipline.record_daily_grade(111, SUP, D, discipline.GRADE_ALO, session_branch=A)

    conn = db.get_connection()
    try:
        conn.execute("DROP TRIGGER fokus_break")
        conn.commit()
        counts = [
            conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
            for name in ("daily_evaluations", "daily_evaluation_history", "bonus_bank_ledger", "nazoratchi_branch_sessions")
        ]
    finally:
        conn.close()
    assert counts == [0, 0, 0, 0] and discipline.get_salary(111)["bonus_bank"] == 0


async def test_both_grading_paths_continue_the_same_unfinished_work_date(bot_dp, monkeypatch):
    main, bot = bot_dp
    _setup_two_branches()
    _employee(113, A, "Ikkinchi")
    _pin(monkeypatch, D, 23, 55)
    await send_callback(main.dp, bot, SUP, data=f"nzr_grade:111:{discipline.GRADE_NORMA}:{_ymd(D)}", target_chat_id=SUP)  # "Filiallar" yo'li
    _pin(monkeypatch, _shift(D, 1), 0, 30)

    await send_callback(main.dp, bot, SUP, data=f"bos:grade:113:{discipline.GRADE_NORMA}:{_ymd(D)}", target_chat_id=SUP)  # "Baholash" yo'li

    assert discipline.get_daily_grade(113, D) is not None and discipline.get_daily_grade(113, _shift(D, 1)) is None
    assert _sessions_of(A, D) == ["open"]
    assert nazoratchi_day.active_day(SUP, discipline_bot._now_company()).work_date == D
