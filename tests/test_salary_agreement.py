"""Fiks kelishuvi: Founder oqimi, saqlash/amal qilish qoidalari, ko'rish. Telegram mock, vaqtincha lokal DB."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import pytest

import company_time
import db
import employees
from config import FOUNDER_ID, RECRUITING_BRANCH_NAMES
from repositories import discipline as discipline_repo
from roles import set_role
from services import discipline
from services import salary_agreement as sa
from tests.bot_harness import send, send_callback

pytestmark = pytest.mark.anyio

EMP = 890001
OTHER = 890002
BRANCH = RECRUITING_BRANCH_NAMES[0]


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _employee(user_id: int, branch: str = BRANCH, surname: str = "Valiyev") -> None:
    set_role(user_id, "kassir", set_by=FOUNDER_ID)
    employees.submit_profile(user_id, {"familiya": surname, "ism": "Ali", "branch": branch, "role_key": "kassir", "contacts": []})
    employees.approve_profile(user_id, approved_by=FOUNDER_ID)


def _rows(employee_id: int | None = None) -> list[dict]:
    conn = db.get_connection()
    try:
        query = "SELECT * FROM salary_agreements" + (" WHERE employee_id = ?" if employee_id else "") + " ORDER BY id"
        return [dict(r) for r in conn.execute(query, (employee_id,) if employee_id else ()).fetchall()]
    finally:
        conn.close()


def _text(sent) -> str:
    return "\n".join(getattr(m, "text", "") or "" for m in sent)


def _buttons(sent) -> list[str]:
    return [b.callback_data for m in sent if getattr(m, "reply_markup", None) is not None and hasattr(m.reply_markup, "inline_keyboard")
            for row in m.reply_markup.inline_keyboard for b in row]


async def _cb(main, bot, data, user=FOUNDER_ID):
    return await send_callback(main.dp, bot, user, data=data, target_chat_id=user)


async def _flow_to_card(main, bot, *, amount="4 000 000", days="28", hours="12", date_text=None):
    await send(main.dp, bot, FOUNDER_ID, text="/setsalary")
    await _cb(main, bot, "sal:br:0")
    await _cb(main, bot, f"sal:emp:{EMP}")
    await send(main.dp, bot, FOUNDER_ID, text=amount)
    await send(main.dp, bot, FOUNDER_ID, text=days)
    sent = await send(main.dp, bot, FOUNDER_ID, text=hours)
    assert "sana" in _text(sent).lower()
    if date_text is None:
        return await _cb(main, bot, "sal:today")
    return await send(main.dp, bot, FOUNDER_ID, text=date_text)


def _save_data(card) -> str:
    return next(d for d in _buttons(card) if d.startswith("sal:save:"))


# ------------------------------------------------------------- oqim --


async def test_full_founder_flow_saves_exact_values_only_after_save(bot_dp):
    main, bot = bot_dp
    _employee(EMP)

    card = await _flow_to_card(main, bot)
    text = _text(card)
    assert "Valiyev" in text and BRANCH in text and "4 000 000 so'm" in text and "28 kun" in text and "12 soat" in text
    assert set(d for d in _buttons(card)) >= {"sal:edit", "sal:cancel"} and _rows() == []  # Saqlashgacha yozuv yo'q

    done = await _cb(main, bot, _save_data(card))

    (row,) = _rows(EMP)
    assert (row["fixed_salary"], row["work_days"], row["daily_minutes"]) == (4_000_000, 28, 720)
    assert row["effective_from"] == company_time.today().isoformat() and row["created_by"] == FOUNDER_ID and row["created_at"]
    assert row["source"] == "agreement" and "Kelishuv saqlandi" in _text(done)
    assert discipline.get_salary(EMP)["fixed_salary"] == 4_000_000


@pytest.mark.parametrize(("text", "minutes"), [("12.5", 750), ("12,5", 750), ("12:30", 750), ("8", 480), ("0.5", 30), ("24", 1440)])
def test_half_hours_are_supported_and_stored_in_whole_minutes(text, minutes):
    assert sa.parse_daily_minutes(text) == minutes


@pytest.mark.parametrize("bad", ["0", "-1", "24.5", "25", "12.3", "abc", "", "12:15", "1e1"])
def test_invalid_hours_are_rejected(bad):
    with pytest.raises(sa.ValidationError):
        sa.parse_daily_minutes(bad)


@pytest.mark.parametrize("bad", ["0", "-5", "abc", "1.5", "", "99999999999", "4 000 000 000"])
def test_invalid_amounts_are_rejected(bad):
    with pytest.raises(sa.ValidationError):
        sa.parse_salary(bad)


@pytest.mark.parametrize("text", ["4000000", "4 000 000", "4,000,000", "4_000_000", "4 000 000 so'm"])
def test_amount_formats_are_accepted(text):
    assert sa.parse_salary(text) == 4_000_000


@pytest.mark.parametrize("bad", ["0", "32", "-1", "x", "", "1.5"])
def test_invalid_days_are_rejected(bad):
    with pytest.raises(sa.ValidationError):
        sa.parse_days(bad)


@pytest.mark.parametrize("bad", ["31.02.2026", "abc", "", "01.01.1999", "2026-13-01", "01.01.2100"])
def test_invalid_dates_are_rejected(bad):
    with pytest.raises(sa.ValidationError):
        sa.parse_effective_date(bad)


async def test_invalid_input_keeps_the_step_and_writes_nothing(bot_dp):
    main, bot = bot_dp
    _employee(EMP)
    await send(main.dp, bot, FOUNDER_ID, text="/setsalary")
    await _cb(main, bot, "sal:br:0")
    await _cb(main, bot, f"sal:emp:{EMP}")

    bad = await send(main.dp, bot, FOUNDER_ID, text="salom")
    assert "❌" in _text(bad) and "summa" in _text(bad).lower()
    await send(main.dp, bot, FOUNDER_ID, text="3 000 000")
    bad_days = await send(main.dp, bot, FOUNDER_ID, text="45")
    assert "❌" in _text(bad_days) and _rows() == []


async def test_cancel_and_abandoned_flows_write_nothing(bot_dp):
    main, bot = bot_dp
    _employee(EMP)
    card = await _flow_to_card(main, bot)
    cancelled = await _cb(main, bot, "sal:cancel")
    assert "Hech narsa saqlanmadi" in _text(cancelled)
    stale = await _cb(main, bot, _save_data(card))  # bekor qilingach eski Saqlash ishlamaydi
    assert "eskirgan" in _text(stale) and _rows() == []

    await send(main.dp, bot, FOUNDER_ID, text="/setsalary")  # tugallanmagan oqim
    await _cb(main, bot, "sal:br:0")
    await _cb(main, bot, f"sal:emp:{EMP}")
    await send(main.dp, bot, FOUNDER_ID, text="5 000 000")
    await send(main.dp, bot, FOUNDER_ID, text="/mymaosh")  # boshqa buyruqqa chiqib ketildi
    assert _rows() == []


async def test_edit_changes_one_field_and_shows_the_card_again(bot_dp):
    main, bot = bot_dp
    _employee(EMP)
    card = await _flow_to_card(main, bot)
    menu = await _cb(main, bot, "sal:edit")
    assert {"sal:fld:amount", "sal:fld:days", "sal:fld:hours", "sal:fld:date"} <= set(_buttons(menu))

    await _cb(main, bot, "sal:fld:days")
    again = await send(main.dp, bot, FOUNDER_ID, text="26")

    assert "26 kun" in _text(again) and "4 000 000" in _text(again) and _rows() == []
    await _cb(main, bot, _save_data(again))
    assert _rows(EMP)[0]["work_days"] == 26


# ------------------------------------------------------- ruxsat va qalbaki --


async def test_unauthorized_user_and_forged_callbacks_cannot_write(bot_dp):
    main, bot = bot_dp
    _employee(EMP)
    _employee(OTHER, surname="Begona")
    card = await _flow_to_card(main, bot)
    token_button = _save_data(card)

    denied = await send(main.dp, bot, OTHER, text="/setsalary")
    assert "filial" not in _text(denied).lower()
    forged = await _cb(main, bot, token_button, user=OTHER)  # Founder bo'lmagan foydalanuvchi
    forged_branch = await _cb(main, bot, "sal:br:0", user=OTHER)
    assert _rows() == [] and "filial" not in _text(forged_branch).lower()

    await send(main.dp, bot, FOUNDER_ID, text="/setsalary")  # Founder: boshqa filial xodimi / qalbaki id
    await _cb(main, bot, "sal:br:0")
    wrong = await _cb(main, bot, "sal:emp:999999999")
    assert "eskirgan" in _text(wrong)
    no_state = await _cb(main, bot, "sal:save:" + "0" * 16)
    assert "eskirgan" in _text(no_state) and _rows() == []


async def test_repeated_save_press_creates_one_agreement(bot_dp):
    main, bot = bot_dp
    _employee(EMP)
    card = await _flow_to_card(main, bot)
    save = _save_data(card)

    await _cb(main, bot, save)
    second = await _cb(main, bot, save)

    assert len(_rows(EMP)) == 1 and ("eskirgan" in _text(second) or "allaqachon" in _text(second))


def test_parallel_save_with_same_token_creates_one_agreement():
    today = company_time.today().isoformat()

    def save(_):
        return sa.save_agreement(EMP, 4_000_000, 28, 720, today, FOUNDER_ID, "same-token")

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(save, range(4)))

    assert sum(1 for r in results if r.created) == 1 and len(_rows(EMP)) == 1


# ---------------------------------------------------- tarix va amal sanasi --


def _save(amount, effective, token, days=28, minutes=720):
    return sa.save_agreement(EMP, amount, days, minutes, effective, FOUNDER_ID, token)


def test_history_is_kept_and_current_is_chosen_by_effective_date():
    today = company_time.today()
    _save(3_000_000, (today - timedelta(days=30)).isoformat(), "t1")
    _save(3_500_000, today.isoformat(), "t2")
    _save(3_700_000, today.isoformat(), "t3")  # xuddi shu sana: oxirgi kiritilgani amalda
    _save(9_999_999, (today - timedelta(days=60)).isoformat(), "t4")  # o'tmishdagi sana: amaldagini o'zgartirmaydi

    assert [r["fixed_salary"] for r in _rows(EMP)] == [3_000_000, 3_500_000, 3_700_000, 9_999_999]  # hech narsa o'chmagan
    assert sa.get_current(EMP)["fixed_salary"] == 3_700_000 and discipline.get_salary(EMP)["fixed_salary"] == 3_700_000


def test_future_agreement_does_not_change_todays_fixed_salary_and_is_shown_separately():
    today = company_time.today()
    discipline_repo.upsert_fixed_salary(EMP, 2_000_000, FOUNDER_ID)  # eski fiks
    future = (today + timedelta(days=20)).isoformat()

    _save(5_000_000, future, "f1")

    assert discipline.get_salary(EMP)["fixed_salary"] == 2_000_000 and sa.get_current(EMP) is None
    assert sa.get_upcoming(EMP)["fixed_salary"] == 5_000_000
    lines = "\n".join(sa.view_lines(EMP, 2_000_000))
    assert "Kelajakdagi kelishuv" in lines and "hozirgi fiksni o'zgartirmaydi" in lines and "Kiritilmagan" in lines
    assert lines.index("2 000 000") < lines.index("5 000 000")


def test_future_agreement_becomes_current_by_date_without_a_scheduler(monkeypatch):
    today = company_time.today()
    _save(5_000_000, (today + timedelta(days=3)).isoformat(), "f2")
    assert sa.get_current(EMP) is None

    monkeypatch.setattr(company_time, "today", lambda: today + timedelta(days=3))

    assert discipline.get_salary(EMP)["fixed_salary"] == 5_000_000


def test_past_date_keeps_bonus_bank_grades_and_ledger_untouched():
    today = company_time.today()
    discipline.adjust_bonus_bank(EMP, 50, "test", "test", None)
    discipline.record_daily_grade(EMP, FOUNDER_ID, today.isoformat(), discipline.GRADE_ALO)
    before = discipline_repo.get_salary(EMP)["bonus_bank"]
    ledger_before = discipline.get_bonus_ledger(EMP, limit=100)

    _save(4_000_000, (today - timedelta(days=90)).isoformat(), "p1")

    assert discipline_repo.get_salary(EMP)["bonus_bank"] == before
    assert discipline.get_bonus_ledger(EMP, limit=100) == ledger_before
    assert discipline.get_daily_grade(EMP, today.isoformat()) is not None
    assert discipline_repo.get_salary(EMP)["fixed_salary"] == 4_000_000  # ustun amaldagi kelishuv bilan sinxron


def test_salaries_column_and_get_salary_never_disagree():
    today = company_time.today().isoformat()
    _save(3_100_000, today, "m1")
    assert discipline_repo.get_salary(EMP)["fixed_salary"] == discipline.get_salary(EMP)["fixed_salary"] == 3_100_000


def test_service_validation_is_enforced_even_if_the_caller_is_untrusted():
    today = company_time.today().isoformat()
    for args in ((0, 28, 720, today), (1, 0, 720, today), (1, 28, 721, today), (1, 28, 0, today), (1, 28, 720, "01.01.2026"), (True, 28, 720, today)):
        with pytest.raises(sa.ValidationError):
            sa.save_agreement(EMP, *args, FOUNDER_ID, "x")
    assert _rows() == []


# ------------------------------------------------------------- eski yo'l --


async def test_legacy_setsalary_uses_the_same_write_path_and_shows_missing_days_and_hours(bot_dp):
    main, bot = bot_dp
    _employee(EMP)
    discipline.adjust_bonus_bank(EMP, 7, "test", "test", None)

    sent = await send(main.dp, bot, FOUNDER_ID, text=f"/setsalary {EMP} 3000000")
    assert "o'rnatildi" in _text(sent)

    (row,) = _rows(EMP)
    assert row["source"] == "legacy_setsalary" and row["work_days"] is None and row["daily_minutes"] is None
    assert discipline.get_salary(EMP) == {**discipline.get_salary(EMP), "fixed_salary": 3_000_000, "bonus_bank": 7}
    view = await send(main.dp, bot, FOUNDER_ID, text=f"/maosh {EMP}")
    assert "3 000 000 so'm" in _text(view) and "Kiritilmagan" in _text(view) and "7 ball" in _text(view)


def test_old_salary_without_agreement_is_shown_as_not_entered():
    discipline_repo.upsert_fixed_salary(EMP, 2_500_000, FOUNDER_ID)

    lines = "\n".join(sa.view_lines(EMP, discipline.get_salary(EMP)["fixed_salary"]))

    assert "2 500 000 so'm" in lines and "Kelishuv kunlari/soati: Kiritilmagan" in lines


# --------------------------------------------------------------- ko'rish --


async def test_employee_sees_only_own_agreement_and_group_gets_nothing(bot_dp):
    main, bot = bot_dp
    _employee(EMP)
    _employee(OTHER, surname="Begona")
    today = company_time.today().isoformat()
    sa.save_agreement(EMP, 4_000_000, 28, 720, today, FOUNDER_ID, "v1")
    sa.save_agreement(OTHER, 7_777_777, 20, 480, today, FOUNDER_ID, "v2")

    mine = await send(main.dp, bot, EMP, text="/mymaosh")
    assert "4 000 000" in _text(mine) and "7 777 777" not in _text(mine) and "28 kun" in _text(mine) and "12 soat" in _text(mine)

    group = await send(main.dp, bot, EMP, text="/mymaosh", chat_id=-100123, chat_type="supergroup")
    assert "4 000 000" not in _text(group) and "shaxsiy chatda" in _text(group)

    other_lookup = await send(main.dp, bot, EMP, text=f"/maosh {OTHER}")  # xodim boshqaning oyligini ko'ra olmaydi
    assert "7 777 777" not in _text(other_lookup)

    founder_group = await send(main.dp, bot, FOUNDER_ID, text=f"/maosh {OTHER}", chat_id=-100123, chat_type="supergroup")
    assert "7 777 777" not in _text(founder_group)


# --------------------------------------------------------------- migration --


def test_migration_twice_keeps_data_and_old_salaries():
    discipline_repo.upsert_fixed_salary(EMP, 2_000_000, FOUNDER_ID)
    _save(3_000_000, company_time.today().isoformat(), "mg1")

    db.init_db()
    db.init_db()

    assert len(_rows(EMP)) == 1 and discipline_repo.get_salary(EMP)["fixed_salary"] == 3_000_000


def test_failed_write_rolls_back_agreement_and_salary_mirror():
    conn = db.get_connection()
    try:
        conn.execute("CREATE TRIGGER fokus_break BEFORE INSERT ON salaries BEGIN SELECT RAISE(ABORT, 'sinov'); END")
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(Exception):
        _save(3_000_000, company_time.today().isoformat(), "rb1")

    conn = db.get_connection()
    try:
        conn.execute("DROP TRIGGER fokus_break")
        conn.commit()
    finally:
        conn.close()
    assert _rows(EMP) == []
    assert _save(3_000_000, company_time.today().isoformat(), "rb1").created  # qayta urinish ishlaydi
