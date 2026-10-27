"""Nazoratchi kunlik tekshiruv oqimi: filial tanlash -> xodimlar holati -> baholash ->
qayta baholash -> filial sessiyasini yopish; oylik ball Founder-only; pul maxfiyligi."""

from datetime import timedelta
from types import SimpleNamespace

import pytest
from aiogram.methods import EditMessageText

import company_time
import discipline_bot
import employees
from config import FOUNDER_ID, RECRUITING_BRANCH_NAMES
from services import attendance as attendance_service
from services import discipline, nazoratchi_day
from tests.bot_harness import send, send_callback

pytestmark = pytest.mark.anyio

BRANCH_A, BRANCH_B = RECRUITING_BRANCH_NAMES[0], RECRUITING_BRANCH_NAMES[1]
SUPERVISOR = 1


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _today() -> str:
    return company_time.today().isoformat()


def _display(iso: str) -> str:
    year, month, day = iso.split("-")
    return f"{day}.{month}.{year}"


def _ymd(iso: str = None) -> str:
    return (iso or _today()).replace("-", "")


def _employee(user_id: int, branch: str, surname: str, role: str = "sotuvchi") -> None:
    from roles import set_role

    set_role(user_id, role, set_by=FOUNDER_ID)
    employees.submit_profile(
        user_id, {"familiya": surname, "ism": "T", "branch": branch, "role_key": role, "contacts": []}
    )
    employees.approve_profile(user_id, approved_by=FOUNDER_ID)


def _supervisor() -> None:
    from roles import set_role

    set_role(SUPERVISOR, "nazoratchi", set_by=FOUNDER_ID)


def _texts(sent) -> list[str]:
    return [m.text for m in sent if getattr(m, "text", None)]


def _joined(sent) -> str:
    return "\n".join(_texts(sent))


def _branch_screen_message(sent):
    return next(m for m in sent if getattr(m, "text", None) and "🏬" in m.text and "—" in m.text)


# ---------------------------------------------------------- 1. filial tanlash --


async def test_baholash_asks_branch_first_and_hides_all_employees(bot_dp):
    main, bot = bot_dp
    _supervisor()
    _employee(111, BRANCH_A, "Alisher")
    _employee(222, BRANCH_B, "Botir")

    sent = await send(main.dp, bot, SUPERVISOR, text="/baholash")
    assert "Filialni tanlang" in sent[0].text and f"📅 Ish kuni: {_display(_today())}" in sent[0].text
    assert "Alisher" not in sent[0].text and "Botir" not in sent[0].text  # hamma xodim aralash chiqmaydi
    labels = [b.text for row in sent[0].reply_markup.inline_keyboard for b in row]
    assert labels == [f"📍 {name}" for name in RECRUITING_BRANCH_NAMES]


async def test_selected_branch_shows_only_its_employees(bot_dp):
    main, bot = bot_dp
    _supervisor()
    _employee(111, BRANCH_A, "Alisher")
    _employee(222, BRANCH_B, "Botir")

    sent = await send_callback(main.dp, bot, SUPERVISOR, data=f"bos:br:0:{_ymd()}", target_chat_id=SUPERVISOR)
    text = sent[0].text
    assert "Alisher" in text and "Botir" not in text
    buttons = [b.text for row in sent[0].reply_markup.inline_keyboard for b in row]
    assert any("Alisher" in label for label in buttons) and not any("Botir" in label for label in buttons)


# ------------------------------------------------------------ 2/3. holatlar --


async def test_employee_statuses_are_shown_with_emoji(bot_dp):
    main, bot = bot_dp
    _supervisor()
    _employee(900, BRANCH_A, "Sherzod", role="savdo_boshligi")  # grafikni kiritgan filial rahbari
    _employee(111, BRANCH_A, "Pending")
    _employee(112, BRANCH_A, "Graded")
    _employee(113, BRANCH_A, "Dam")
    _employee(114, BRANCH_A, "Nograf")
    today = _today()
    attendance_service.set_scheduled_work_shift(111, today, "09:00", "18:00", "test", created_by=900)
    attendance_service.set_scheduled_work_shift(112, today, "09:00", "18:00", "test", created_by=900)
    attendance_service.set_scheduled_day_off(113, today, "test", created_by=900)
    discipline.record_daily_grade(112, SUPERVISOR, today, discipline.GRADE_NORMA)

    sent = await send_callback(main.dp, bot, SUPERVISOR, data=f"bos:br:0:{_ymd()}", target_chat_id=SUPERVISOR)
    text = sent[0].text
    assert "🔵 Pending T — baholanmagan" in text
    assert "✅ Graded T — baholandi" in text
    assert "🔴 Dam T — damda (Ruxsat: Sherzod T)" in text  # grafikni kim yozgan bo'lsa ko'rsatiladi
    assert "⚠️ Nograf T — grafik yo'q" in text  # taxmin qilinmaydi


# ------------------------------------------------------------ 4. sessiyani yopish --


async def test_close_allows_pending_and_no_schedule_and_keeps_day_off(bot_dp):
    main, bot = bot_dp
    _supervisor()
    _employee(111, BRANCH_A, "Pending")
    _employee(113, BRANCH_A, "Dam")
    _employee(114, BRANCH_A, "Nograf")
    today = _today()
    attendance_service.set_scheduled_work_shift(111, today, "09:00", "18:00", "test")
    attendance_service.set_scheduled_day_off(113, today, "test")
    sent = await send_callback(main.dp, bot, SUPERVISOR, data=f"bos:close:0:{_ymd()}", target_chat_id=SUPERVISOR)
    text = _joined(sent)
    assert "nazorati yopildi" in text and "baholanmadi" in text
    assert "Pending T" in text and "Nograf T" in text and "Damda: Dam T" in text
    assert discipline.get_daily_grade(111, today) is None and discipline.get_daily_grade(114, today) is None
    assert nazoratchi_day.close_session(SUPERVISOR, BRANCH_A, today).already_closed


async def test_close_succeeds_after_all_required_graded_and_session_closed(bot_dp):
    main, bot = bot_dp
    _supervisor()
    _employee(111, BRANCH_A, "Pending")
    _employee(113, BRANCH_A, "Dam")
    today = _today()
    attendance_service.set_scheduled_work_shift(111, today, "09:00", "18:00", "test")
    attendance_service.set_scheduled_day_off(113, today, "test")

    sent = await send_callback(
        main.dp, bot, SUPERVISOR, data=f"bos:grade:111:{discipline.GRADE_ALO}:{_ymd()}", target_chat_id=SUPERVISOR
    )
    screen = next(m for m in sent if isinstance(m, EditMessageText))  # xodimga ketgan xabar emas, nazoratchi ekrani
    assert "3 ball" in screen.text and "✅ Pending T — baholandi" in screen.text  # ro'yxatda ✅

    sent = await send_callback(main.dp, bot, SUPERVISOR, data=f"bos:close:0:{_ymd()}", target_chat_id=SUPERVISOR)
    assert f"{BRANCH_A} nazorati yopildi" in sent[0].text and "baholangan: 1/2" in sent[0].text
    assert "Damda: Dam T" in sent[0].text

    from repositories import discipline as discipline_repo

    assert discipline_repo.get_branch_session(SUPERVISOR, BRANCH_A, today)["status"] == "closed"
    assert discipline.get_closure(SUPERVISOR, today) is not None  # mavjud kun yopish belgisi

    sent = await send_callback(main.dp, bot, SUPERVISOR, data=f"bos:close:0:{_ymd()}", target_chat_id=SUPERVISOR)
    assert "allaqachon yopilgan" in sent[0].text


async def test_each_branch_session_is_separate(bot_dp):
    _supervisor()
    _employee(111, BRANCH_A, "Pending")
    _employee(222, BRANCH_B, "Botir")
    today = _today()
    assert nazoratchi_day.close_session(SUPERVISOR, BRANCH_B, today).closed
    assert discipline.get_closure(SUPERVISOR, today) is None
    assert nazoratchi_day.close_session(SUPERVISOR, BRANCH_A, today).closed
    assert discipline.get_closure(SUPERVISOR, today) is not None
    assert discipline.get_daily_grade(111, today) is None


# ------------------------------------------------------ 5/6. eski yopilmagan sessiya --


async def test_previous_unclosed_day_does_not_capture_current_day(bot_dp):
    main, bot = bot_dp
    _supervisor()
    _employee(111, BRANCH_A, "Pending")
    yesterday = (company_time.today() - timedelta(days=1)).isoformat()
    nazoratchi_day.open_session(SUPERVISOR, BRANCH_A, yesterday)
    sent = await send(main.dp, bot, SUPERVISOR, text="/baholash")
    assert f"📅 Ish kuni: {_display(_today())}" in sent[0].text and "Avval shu ish kunini" not in sent[0].text
    old = await send_callback(main.dp, bot, SUPERVISOR, data=f"bos:grade:111:alo:{_ymd(yesterday)}", target_chat_id=SUPERVISOR)
    assert "eskirgan" in _joined(old)
    await send_callback(main.dp, bot, SUPERVISOR, data=f"bos:grade:111:alo:{_ymd()}", target_chat_id=SUPERVISOR)
    assert discipline.get_daily_grade(111, _today()) is not None and discipline.get_daily_grade(111, yesterday) is None
    from repositories import discipline as discipline_repo
    assert discipline_repo.get_branch_session(SUPERVISOR, BRANCH_A, yesterday)["status"] == "open"


async def test_several_old_open_branches_do_not_change_the_current_work_date(bot_dp):
    main, bot = bot_dp
    _supervisor()
    old, newer = ((company_time.today() - timedelta(days=n)).isoformat() for n in (2, 1))
    nazoratchi_day.open_session(SUPERVISOR, BRANCH_A, newer)
    nazoratchi_day.open_session(SUPERVISOR, BRANCH_A, old)
    nazoratchi_day.open_session(SUPERVISOR, BRANCH_B, old)
    sent = await send(main.dp, bot, SUPERVISOR, text="/baholash")
    assert f"📅 Ish kuni: {_display(_today())}" in sent[0].text
    assert "Avval shu ish kunini" not in sent[0].text


# ---------------------------------------------------- 7. oylik ball (/score) --


async def test_score_not_for_nazoratchi_but_founder_can(bot_dp):
    main, bot = bot_dp
    _supervisor()
    _employee(111, BRANCH_A, "Alisher")

    sent = await send(main.dp, bot, SUPERVISOR, text="/score 111 90")
    assert "qayd etildi" not in " ".join(_texts(sent))

    sent = await send(main.dp, bot, FOUNDER_ID, text="/score 111 90")
    assert "qayd etildi" in sent[0].text

    sent = await send(main.dp, bot, SUPERVISOR, text="🧑‍💼 Nazoratchi")
    labels = [b.text for row in sent[0].reply_markup.keyboard for b in row]
    assert "⭐ Oylik ball qo'yish" not in labels


# ------------------------------------------------------- 8. qayta baholash --


async def test_regrading_keeps_every_grade_as_separate_history(bot_dp):
    main, bot = bot_dp
    _supervisor()
    _employee(111, BRANCH_A, "Alisher")
    today = _today()

    discipline.record_daily_grade(111, SUPERVISOR, today, discipline.GRADE_ALO)
    discipline.record_daily_grade(111, SUPERVISOR, today, discipline.GRADE_CHALA)

    history = discipline.get_grade_history(111, today)
    assert [(row["grade_key"], row["grade_points"]) for row in history] == [
        (discipline.GRADE_ALO, 3), (discipline.GRADE_CHALA, 1),  # eski baho o'chmadi
    ]
    assert discipline.get_daily_grade(111, today)["grade_key"] == discipline.GRADE_CHALA  # joriy baho

    sent = await send_callback(main.dp, bot, SUPERVISOR, data=f"bos:emp:111:{_ymd()}", target_chat_id=SUPERVISOR)
    assert "A'lo (3 ball)" in sent[0].text and "Chala (1 ball)" in sent[0].text  # qayta baholash tugmalari qolgan
    assert any("bos:grade:111" in (b.callback_data or "") for row in sent[0].reply_markup.inline_keyboard for b in row)


# ------------------------------------------------ 9/10. plus/minus va yulduz --


def test_plus_and_minus_kept_separate_and_star_message_format(bot_dp):
    _employee(111, BRANCH_A, "Eshmat")
    discipline.record_daily_grade(111, SUPERVISOR, _today(), discipline.GRADE_ALO)  # +3
    discipline.add_rule(1, "Telefon", "Ish vaqtida telefon", FOUNDER_ID)
    discipline.apply_penalty(111, SUPERVISOR, _today(), 10, 1, comment="telefon", ai_note=None)  # -10

    totals = discipline.get_period_point_totals(111)
    assert (totals["bonus"], totals["minus"], totals["net"]) == (3, 10, -7)  # alohida yig'iladi, Hisob = farq

    from services import employee_dashboard

    text = employee_dashboard.format_dashboard_text(employee_dashboard.build_dashboard(111))
    assert "🟢 Bonus: 3" in text and "🔴 Minus: 10" in text and "⭐ Jami: -7" in text

    message = discipline.format_daily_star_message(
        "Eshmat", 3, "polka yaxshi", {"bonus": 113, "minus": 12, "net": 101}
    )
    assert message == (
        "Eshmat, kecha siz +3 ⭐ oldingiz.\nSabab: polka yaxshi.\nShu oy jami: 113 ⭐\n"
        "Minus: 12 ⭐ kamaygan\nHisob: 101 ⭐"
    )


# ------------------------------------------------------- 11. savdo maxfiyligi --


async def test_branch_head_gets_only_own_branch_shortage_with_full_card_nazoratchi_none(bot_dp):
    main, bot = bot_dp
    import cash_shift_bot
    from tests.test_cash_money_privacy import NAZORATCHI_ID, _has_money, _make_roles, _seed_shift, _texts_for
    from tests.test_cash_shift_ai_vision import _make_savdo_boshligi
    from tests.test_cash_shift_bot_flows import _make_kassir

    _make_kassir(111, branch="Filial-1")
    _make_savdo_boshligi(777, "Filial-1")
    _make_savdo_boshligi(778, "Filial-2")
    _make_roles()
    shift = _seed_shift()  # Filial-1 kassiri smenasi

    bot.sent = []
    await cash_shift_bot._notify_branch_shortage(SimpleNamespace(bot=bot), shift)

    assert _has_money(_texts_for(bot, 777)[0])  # o'z filiali rahbari to'liq ko'radi
    assert _texts_for(bot, 778) == []  # boshqa filial rahbari ko'rmaydi
    assert _texts_for(bot, NAZORATCHI_ID) == []  # nazoratchi ko'rmaydi


@pytest.fixture(autouse=True)
def _daytime_clock_for_non_boundary_tests(monkeypatch):
    # Boundary/night tests explicitly override this; ordinary callbacks use one stable work day.
    fixed = company_time.now().replace(hour=12, minute=0, second=0, microsecond=0)
    monkeypatch.setattr(company_time, "now", lambda: fixed)
