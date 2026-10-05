"""Bugundan oy oxirigacha grafik (tugmalar orqali): smena -> haftalik dam kuni -> tasdiqlash."""

from datetime import date

import pytest

import company_time
import employees
from config import FOUNDER_ID, RECRUITING_BRANCH_NAMES
from repositories import attendance as attendance_repo
from roles import set_role
from services import nazoratchi_day, schedule_range
from tests.bot_harness import send, send_callback

pytestmark = pytest.mark.anyio

_BRANCH = RECRUITING_BRANCH_NAMES[0]
_NAZORATCHI = 880001
_EMPLOYEE = 700301


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _setup() -> None:
    set_role(_NAZORATCHI, "nazoratchi", set_by=FOUNDER_ID)
    employees.submit_profile(
        _NAZORATCHI, {"familiya": "Nazoratov", "ism": "Bek", "branch": _BRANCH, "role_key": "nazoratchi", "contacts": []}
    )
    employees.approve_profile(_NAZORATCHI, approved_by=FOUNDER_ID)
    set_role(_EMPLOYEE, "kassir", set_by=FOUNDER_ID)
    employees.submit_profile(
        _EMPLOYEE, {"familiya": "Valiyev", "ism": "Ali", "branch": _BRANCH, "role_key": "kassir", "contacts": []}
    )
    employees.approve_profile(_EMPLOYEE, approved_by=FOUNDER_ID)


async def _cb(main, bot, data: str, actor: int = _NAZORATCHI):
    return await send_callback(main.dp, bot, actor, data=data, target_chat_id=actor)


async def _run_flow(main, bot, shift_choice: str, off_choice: str, weekday_choice: str | None = None):
    await _cb(main, bot, f"nzr_srange:{_EMPLOYEE}")
    await _cb(main, bot, f"nzr_srs:{_EMPLOYEE}:{shift_choice}")
    await _cb(main, bot, f"nzr_srd:{_EMPLOYEE}:{off_choice}")
    if weekday_choice is not None:
        await _cb(main, bot, f"nzr_srd:{_EMPLOYEE}:{weekday_choice}")
    return await _cb(main, bot, f"nzr_srok:{_EMPLOYEE}")


def _expected_days() -> list[date]:
    start, end = schedule_range.month_range(company_time.today())
    return schedule_range.dates_in_range(start, end)


def _shift(day: date) -> dict | None:
    return attendance_repo.get_shift_for_date(_EMPLOYEE, day.isoformat())


def _screen_texts(sent) -> list[str]:
    return [getattr(m, "text", "") or "" for m in sent if getattr(m, "text", None)]


# ----------------------------------------------------------------- servis --


def test_month_range_is_today_to_month_end():
    start, end = schedule_range.month_range(date(2026, 10, 6))
    assert (start, end) == (date(2026, 10, 6), date(2026, 10, 31))
    assert schedule_range.month_range(date(2026, 10, 31)) == (date(2026, 10, 31), date(2026, 10, 31))
    assert schedule_range.month_range(date(2028, 2, 10))[1] == date(2028, 2, 29)


def test_confirm_text_matches_agreed_shape():
    text = schedule_range.confirm_text("Valiyev Ali", date(2026, 10, 6), date(2026, 10, 31), {"start": "08:00", "end": "18:00"}, 6)
    assert "06.10.2026 dan 31.10.2026 gacha\n08:00–18:00\nDam kuni: Yakshanba\n\nTasdiqlaysizmi?" in text
    none_text = schedule_range.confirm_text("A", date(2026, 10, 6), date(2026, 10, 31), {"start": "08:00", "end": "18:00"}, None)
    assert "Dam kuni: yo'q" in none_text


def test_apply_range_rejects_bad_times_without_writing(temp_db):
    _setup()
    with pytest.raises(ValueError):
        schedule_range.apply_range(
            _EMPLOYEE, date(2026, 10, 6), date(2026, 10, 10), {"start": "09:00", "end": "09:00"}, None, "test", 1
        )
    assert attendance_repo.get_shift_for_date(_EMPLOYEE, "2026-10-06") is None


# ------------------------------------------------------------------ oqim --


async def test_fixed_shift_with_sunday_off_creates_work_and_off_days(bot_dp):
    main, bot = bot_dp
    _setup()

    sent = await _run_flow(main, bot, "fixed_1", "6")

    days = _expected_days()
    for day in days:
        shift = _shift(day)
        if day.weekday() == 6:
            assert shift["status"] == "off", day
        else:
            assert (shift["status"], shift["planned_start"], shift["planned_end"]) == ("work", "08:00", "18:00"), day
            assert shift["schedule_mode"] == "fixed_1"
    assert _shift(date.fromordinal(days[-1].toordinal() + 1)) is None  # oy oxiridan keyingi kunga tegilmagan
    assert "Grafik saqlandi" in "\n".join(_screen_texts(sent))


async def test_confirm_screen_shows_range_shift_and_off_day(bot_dp):
    main, bot = bot_dp
    _setup()

    await _cb(main, bot, f"nzr_srange:{_EMPLOYEE}")
    await _cb(main, bot, f"nzr_srs:{_EMPLOYEE}:fixed_2")
    sent = await _cb(main, bot, f"nzr_srd:{_EMPLOYEE}:6")

    start, end = schedule_range.month_range(company_time.today())
    text = next(t for t in _screen_texts(sent) if "Tasdiqlaysizmi?" in t)
    assert f"{start.strftime('%d.%m.%Y')} dan {end.strftime('%d.%m.%Y')} gacha\n14:00–01:00\nDam kuni: Yakshanba" in text
    assert _shift(start) is None  # tasdiqlanmaguncha hech narsa yozilmaydi


async def test_other_day_picker_offers_all_weekdays_and_applies_choice(bot_dp):
    main, bot = bot_dp
    _setup()
    await _cb(main, bot, f"nzr_srange:{_EMPLOYEE}")
    await _cb(main, bot, f"nzr_srs:{_EMPLOYEE}:fixed_1")
    picker = await _cb(main, bot, f"nzr_srd:{_EMPLOYEE}:other")
    labels = [b.text for m in picker if getattr(m, "reply_markup", None) for row in m.reply_markup.inline_keyboard for b in row]
    for name in schedule_range.WEEKDAY_NAMES:
        assert name in labels

    await _cb(main, bot, f"nzr_srd:{_EMPLOYEE}:2")  # Chorshanba
    await _cb(main, bot, f"nzr_srok:{_EMPLOYEE}")

    for day in _expected_days():
        assert _shift(day)["status"] == ("off" if day.weekday() == 2 else "work")


async def test_no_off_day_makes_every_day_work(bot_dp):
    main, bot = bot_dp
    _setup()

    await _run_flow(main, bot, "fixed_1", "none")

    assert all(_shift(day)["status"] == "work" for day in _expected_days())


async def test_flexible_time_range_is_applied(bot_dp):
    main, bot = bot_dp
    _setup()

    await _cb(main, bot, f"nzr_srange:{_EMPLOYEE}")
    await _cb(main, bot, f"nzr_srs:{_EMPLOYEE}:flex")
    await send(main.dp, bot, _NAZORATCHI, text="10:00")
    await send(main.dp, bot, _NAZORATCHI, text="20:30")
    await _cb(main, bot, f"nzr_srd:{_EMPLOYEE}:5")
    await _cb(main, bot, f"nzr_srok:{_EMPLOYEE}")

    for day in _expected_days():
        shift = _shift(day)
        if day.weekday() == 5:
            assert shift["status"] == "off"
        else:
            assert (shift["planned_start"], shift["planned_end"], shift["schedule_mode"]) == ("10:00", "20:30", "flexible")


async def test_off_day_does_not_block_branch_close(bot_dp):
    main, bot = bot_dp
    _setup()
    today = company_time.today()

    await _run_flow(main, bot, "fixed_1", "other", str(today.weekday()))  # bugun dam kuni

    status = nazoratchi_day.employee_status(employees.get_profile(_EMPLOYEE), today.isoformat())
    assert status.status == nazoratchi_day.STATUS_OFF
    result = nazoratchi_day.close_session(_NAZORATCHI, _BRANCH, today.isoformat())
    assert result.closed is True and result.blockers == [] and result.off_count == 1


async def test_single_day_manual_change_afterwards_does_not_break_the_rest(bot_dp):
    main, bot = bot_dp
    _setup()
    await _run_flow(main, bot, "fixed_1", "none")
    before = {day: dict(_shift(day)) for day in _expected_days()}

    today = company_time.today()
    await _cb(main, bot, f"nzr_sched:{_EMPLOYEE}")
    await _cb(main, bot, f"nzr_sched_off:{_EMPLOYEE}")
    await _cb(main, bot, f"nzr_sched_confirm:{_EMPLOYEE}")

    assert _shift(today)["status"] == "off"
    for day, row in before.items():
        if day != today:
            assert _shift(day)["status"] == row["status"] and _shift(day)["planned_start"] == row["planned_start"]


async def test_stale_confirm_and_unauthorised_actor_write_nothing(bot_dp):
    main, bot = bot_dp
    _setup()
    set_role(990001, "kassir", set_by=FOUNDER_ID)

    await _cb(main, bot, f"nzr_srok:{_EMPLOYEE}")  # holat yo'q (eskirgan tugma)
    await _run_unauthorised(main, bot)

    assert all(_shift(day) is None for day in _expected_days())


async def _run_unauthorised(main, bot):
    for data in (f"nzr_srange:{_EMPLOYEE}", f"nzr_srs:{_EMPLOYEE}:fixed_1", f"nzr_srd:{_EMPLOYEE}:6", f"nzr_srok:{_EMPLOYEE}"):
        await _cb(main, bot, data, actor=990001)
