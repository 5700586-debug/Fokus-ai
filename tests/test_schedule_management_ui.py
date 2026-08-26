"""SCHEDULE MANAGEMENT TELEGRAM UI V1 (``nazoratchi_bot.py``): xodim
kartasidagi "🗓 Ish grafigi" tugmasi -> 1-smena/2-smena/erkin
vaqt/dam olish/boshqa sana -> tasdiqlash ekrani -> saqlash + xodimga
xabar. Mavjud ``services/attendance.py`` schedule core qayta
ishlatiladi -- bu yerda yangi business logic yozilmaydi, faqat
Telegram oqimi.
"""

from datetime import timedelta

import company_time
import employees
from config import FOUNDER_ID, RECRUITING_BRANCH_NAMES
from repositories import attendance as attendance_repo
from roles import set_role
from services import permissions as permissions_service
from tests.bot_harness import send, send_callback

_BRANCH_A = RECRUITING_BRANCH_NAMES[0]
_BRANCH_B = RECRUITING_BRANCH_NAMES[1]
_NAZORATCHI_ID = 880001


def _make_nazoratchi(user_id: int = _NAZORATCHI_ID) -> None:
    set_role(user_id, "nazoratchi", set_by=FOUNDER_ID)
    employees.submit_profile(
        user_id,
        {"familiya": "Nazoratov", "ism": "Bek", "branch": _BRANCH_A, "role_key": "nazoratchi", "contacts": []},
    )
    employees.approve_profile(user_id, approved_by=FOUNDER_ID)


def _make_employee(user_id: int, branch: str = _BRANCH_A, role_key: str = "kassir") -> None:
    set_role(user_id, role_key, set_by=FOUNDER_ID)
    employees.submit_profile(
        user_id,
        {
            "familiya": "Valiyev", "ism": "Ali", "branch": branch, "role_key": role_key, "contacts": [],
        },
    )
    employees.approve_profile(user_id, approved_by=FOUNDER_ID)


async def _open_schedule_menu(main, bot, actor_id: int, employee_id: int):
    return await send_callback(main.dp, bot, actor_id, data=f"nzr_sched:{employee_id}", target_chat_id=actor_id)


# ------------------------------------------------------------- RUXSAT --


async def test_founder_can_manage_any_employees_schedule(bot_dp):
    main, bot = bot_dp
    _make_employee(700101)

    sent = await _open_schedule_menu(main, bot, FOUNDER_ID, 700101)

    assert "Valiyev" in sent[0].text
    buttons = [btn.callback_data for row in sent[0].reply_markup.inline_keyboard for btn in row]
    assert "nzr_sched_fixed:700101:fixed_1" in buttons


async def test_unauthorized_role_cannot_manage_schedule(bot_dp):
    main, bot = bot_dp
    kassir_id = 700102
    _make_employee(kassir_id)
    _make_employee(700103)

    sent = await send_callback(main.dp, bot, kassir_id, data="nzr_sched:700103", target_chat_id=kassir_id)

    assert not any(
        "nzr_sched_fixed" in (btn.callback_data or "")
        for m in sent
        if getattr(m, "reply_markup", None)
        for row in m.reply_markup.inline_keyboard
        for btn in row
    )
    assert attendance_repo.get_shift_for_date(700103, company_time.today().isoformat()) is None


async def test_nazoratchi_cannot_edit_own_schedule(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()

    sent = await _open_schedule_menu(main, bot, _NAZORATCHI_ID, _NAZORATCHI_ID)

    assert attendance_repo.get_shift_for_date(_NAZORATCHI_ID, company_time.today().isoformat()) is None
    assert not any(
        getattr(m, "reply_markup", None) and any(
            "nzr_sched_fixed" in (btn.callback_data or "") for row in m.reply_markup.inline_keyboard for btn in row
        )
        for m in sent
    )


async def test_founder_has_no_self_edit_restriction(bot_dp):
    main, bot = bot_dp

    sent = await _open_schedule_menu(main, bot, FOUNDER_ID, FOUNDER_ID)

    buttons = [btn.callback_data for row in sent[0].reply_markup.inline_keyboard for btn in row]
    assert f"nzr_sched_fixed:{FOUNDER_ID}:fixed_1" in buttons


async def test_branch_access_restriction_is_enforced(bot_dp, monkeypatch):
    main, bot = bot_dp
    limited_role = "savdo_boshligi"
    limited_actor_id = 700104
    _make_employee(limited_actor_id, branch=_BRANCH_A, role_key=limited_role)

    monkeypatch.setattr(
        permissions_service, "ROLE_PERMISSIONS",
        {
            **permissions_service.ROLE_PERMISSIONS,
            limited_role: permissions_service.ROLE_PERMISSIONS.get(limited_role, set())
            | {permissions_service.ACTION_MANAGE_DAILY_SCHEDULE},
        },
    )

    other_branch_employee = 700105
    _make_employee(other_branch_employee, branch=_BRANCH_B)

    await send_callback(main.dp, bot, limited_actor_id, data=f"nzr_sched:{other_branch_employee}", target_chat_id=limited_actor_id)

    assert attendance_repo.get_shift_for_date(other_branch_employee, company_time.today().isoformat()) is None


# --------------------------------------------------------- FIXED / OFF --


async def test_fixed_1_template_is_applied_after_confirm(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    employee_id = 700106
    _make_employee(employee_id)

    await _open_schedule_menu(main, bot, _NAZORATCHI_ID, employee_id)
    await send_callback(
        main.dp, bot, _NAZORATCHI_ID, data=f"nzr_sched_fixed:{employee_id}:fixed_1", target_chat_id=_NAZORATCHI_ID
    )
    await send_callback(
        main.dp, bot, _NAZORATCHI_ID, data=f"nzr_sched_confirm:{employee_id}", target_chat_id=_NAZORATCHI_ID
    )

    shift = attendance_repo.get_shift_for_date(employee_id, company_time.today().isoformat())
    assert shift["planned_start"] == "08:00"
    assert shift["planned_end"] == "18:00"
    assert shift["schedule_mode"] == "fixed_1"


async def test_fixed_2_template_is_applied_after_confirm(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    employee_id = 700107
    _make_employee(employee_id)

    await _open_schedule_menu(main, bot, _NAZORATCHI_ID, employee_id)
    await send_callback(
        main.dp, bot, _NAZORATCHI_ID, data=f"nzr_sched_fixed:{employee_id}:fixed_2", target_chat_id=_NAZORATCHI_ID
    )
    await send_callback(
        main.dp, bot, _NAZORATCHI_ID, data=f"nzr_sched_confirm:{employee_id}", target_chat_id=_NAZORATCHI_ID
    )

    shift = attendance_repo.get_shift_for_date(employee_id, company_time.today().isoformat())
    assert shift["planned_start"] == "14:00"
    assert shift["planned_end"] == "01:00"


async def test_off_day_is_applied_after_confirm(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    employee_id = 700108
    _make_employee(employee_id)

    await _open_schedule_menu(main, bot, _NAZORATCHI_ID, employee_id)
    await send_callback(
        main.dp, bot, _NAZORATCHI_ID, data=f"nzr_sched_off:{employee_id}", target_chat_id=_NAZORATCHI_ID
    )
    await send_callback(
        main.dp, bot, _NAZORATCHI_ID, data=f"nzr_sched_confirm:{employee_id}", target_chat_id=_NAZORATCHI_ID
    )

    shift = attendance_repo.get_shift_for_date(employee_id, company_time.today().isoformat())
    assert shift["status"] == "off"


# ------------------------------------------------------------ FLEXIBLE --


async def test_flexible_daytime_hh_mm_is_applied(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    employee_id = 700109
    _make_employee(employee_id)

    await _open_schedule_menu(main, bot, _NAZORATCHI_ID, employee_id)
    await send_callback(
        main.dp, bot, _NAZORATCHI_ID, data=f"nzr_sched_flex:{employee_id}", target_chat_id=_NAZORATCHI_ID
    )
    await send(main.dp, bot, _NAZORATCHI_ID, text="10:00")
    await send(main.dp, bot, _NAZORATCHI_ID, text="20:00")
    await send_callback(
        main.dp, bot, _NAZORATCHI_ID, data=f"nzr_sched_confirm:{employee_id}", target_chat_id=_NAZORATCHI_ID
    )

    shift = attendance_repo.get_shift_for_date(employee_id, company_time.today().isoformat())
    assert shift["planned_start"] == "10:00"
    assert shift["planned_end"] == "20:00"
    assert shift["schedule_mode"] == "flexible"


async def test_flexible_overnight_is_applied(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    employee_id = 700110
    _make_employee(employee_id)

    await _open_schedule_menu(main, bot, _NAZORATCHI_ID, employee_id)
    await send_callback(
        main.dp, bot, _NAZORATCHI_ID, data=f"nzr_sched_flex:{employee_id}", target_chat_id=_NAZORATCHI_ID
    )
    await send(main.dp, bot, _NAZORATCHI_ID, text="18:00")
    await send(main.dp, bot, _NAZORATCHI_ID, text="02:00")
    await send_callback(
        main.dp, bot, _NAZORATCHI_ID, data=f"nzr_sched_confirm:{employee_id}", target_chat_id=_NAZORATCHI_ID
    )

    shift = attendance_repo.get_shift_for_date(employee_id, company_time.today().isoformat())
    assert shift["planned_start"] == "18:00"
    assert shift["planned_end"] == "02:00"


async def test_flexible_start_equal_end_is_rejected_and_reprompts(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    employee_id = 700111
    _make_employee(employee_id)

    await _open_schedule_menu(main, bot, _NAZORATCHI_ID, employee_id)
    await send_callback(
        main.dp, bot, _NAZORATCHI_ID, data=f"nzr_sched_flex:{employee_id}", target_chat_id=_NAZORATCHI_ID
    )
    await send(main.dp, bot, _NAZORATCHI_ID, text="10:00")
    sent = await send(main.dp, bot, _NAZORATCHI_ID, text="10:00")

    assert "bir xil" in sent[0].text.lower()
    assert attendance_repo.get_shift_for_date(employee_id, company_time.today().isoformat()) is None

    sent = await send(main.dp, bot, _NAZORATCHI_ID, text="18:00")
    assert "Yangi grafik" in sent[0].text


async def test_invalid_time_format_is_rejected_and_reprompts(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    employee_id = 700112
    _make_employee(employee_id)

    await _open_schedule_menu(main, bot, _NAZORATCHI_ID, employee_id)
    await send_callback(
        main.dp, bot, _NAZORATCHI_ID, data=f"nzr_sched_flex:{employee_id}", target_chat_id=_NAZORATCHI_ID
    )
    sent = await send(main.dp, bot, _NAZORATCHI_ID, text="not-a-time")

    assert "Noto'g'ri format" in sent[0].text
    assert attendance_repo.get_shift_for_date(employee_id, company_time.today().isoformat()) is None


# ------------------------------------------------------- BOSHQA SANA --


async def test_other_date_is_applied_to_the_chosen_day(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    employee_id = 700113
    _make_employee(employee_id)
    future_date = (company_time.today() + timedelta(days=5)).isoformat()

    await _open_schedule_menu(main, bot, _NAZORATCHI_ID, employee_id)
    await send_callback(
        main.dp, bot, _NAZORATCHI_ID, data=f"nzr_sched_date:{employee_id}", target_chat_id=_NAZORATCHI_ID
    )
    await send(main.dp, bot, _NAZORATCHI_ID, text=future_date)
    await send_callback(
        main.dp, bot, _NAZORATCHI_ID, data=f"nzr_sched_fixed:{employee_id}:fixed_1", target_chat_id=_NAZORATCHI_ID
    )
    await send_callback(
        main.dp, bot, _NAZORATCHI_ID, data=f"nzr_sched_confirm:{employee_id}", target_chat_id=_NAZORATCHI_ID
    )

    shift = attendance_repo.get_shift_for_date(employee_id, future_date)
    assert shift is not None
    assert attendance_repo.get_shift_for_date(employee_id, company_time.today().isoformat()) is None


# ------------------------------------------------------------- CONFIRM --


async def test_nothing_is_written_until_confirmed(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    employee_id = 700114
    _make_employee(employee_id)

    await _open_schedule_menu(main, bot, _NAZORATCHI_ID, employee_id)
    await send_callback(
        main.dp, bot, _NAZORATCHI_ID, data=f"nzr_sched_fixed:{employee_id}:fixed_1", target_chat_id=_NAZORATCHI_ID
    )

    assert attendance_repo.get_shift_for_date(employee_id, company_time.today().isoformat()) is None


async def test_double_confirm_click_keeps_a_single_row(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    employee_id = 700115
    _make_employee(employee_id)

    await _open_schedule_menu(main, bot, _NAZORATCHI_ID, employee_id)
    await send_callback(
        main.dp, bot, _NAZORATCHI_ID, data=f"nzr_sched_fixed:{employee_id}:fixed_1", target_chat_id=_NAZORATCHI_ID
    )
    await send_callback(
        main.dp, bot, _NAZORATCHI_ID, data=f"nzr_sched_confirm:{employee_id}", target_chat_id=_NAZORATCHI_ID
    )
    await send_callback(
        main.dp, bot, _NAZORATCHI_ID, data=f"nzr_sched_confirm:{employee_id}", target_chat_id=_NAZORATCHI_ID
    )

    today = company_time.today()
    rows = attendance_repo.get_schedule_for_range(employee_id, today.isoformat(), (today + timedelta(days=1)).isoformat())
    assert len(rows) == 1


async def test_re_editing_creates_an_audit_entry(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    employee_id = 700116
    _make_employee(employee_id)

    await _open_schedule_menu(main, bot, _NAZORATCHI_ID, employee_id)
    await send_callback(
        main.dp, bot, _NAZORATCHI_ID, data=f"nzr_sched_fixed:{employee_id}:fixed_1", target_chat_id=_NAZORATCHI_ID
    )
    await send_callback(
        main.dp, bot, _NAZORATCHI_ID, data=f"nzr_sched_confirm:{employee_id}", target_chat_id=_NAZORATCHI_ID
    )

    await _open_schedule_menu(main, bot, _NAZORATCHI_ID, employee_id)
    await send_callback(
        main.dp, bot, _NAZORATCHI_ID, data=f"nzr_sched_fixed:{employee_id}:fixed_2", target_chat_id=_NAZORATCHI_ID
    )
    await send_callback(
        main.dp, bot, _NAZORATCHI_ID, data=f"nzr_sched_confirm:{employee_id}", target_chat_id=_NAZORATCHI_ID
    )

    revisions = attendance_repo.list_schedule_revisions(employee_id, company_time.today().isoformat())
    assert len(revisions) == 2


async def test_employee_notification_failure_does_not_roll_back_the_schedule(bot_dp, monkeypatch):
    main, bot = bot_dp
    _make_nazoratchi()
    employee_id = 700117
    _make_employee(employee_id)

    async def _failing_send_message(*args, **kwargs):
        raise RuntimeError("simulated Telegram delivery failure")

    monkeypatch.setattr(bot, "send_message", _failing_send_message)

    await _open_schedule_menu(main, bot, _NAZORATCHI_ID, employee_id)
    await send_callback(
        main.dp, bot, _NAZORATCHI_ID, data=f"nzr_sched_fixed:{employee_id}:fixed_1", target_chat_id=_NAZORATCHI_ID
    )
    sent = await send_callback(
        main.dp, bot, _NAZORATCHI_ID, data=f"nzr_sched_confirm:{employee_id}", target_chat_id=_NAZORATCHI_ID
    )

    shift = attendance_repo.get_shift_for_date(employee_id, company_time.today().isoformat())
    assert shift is not None
    assert shift["planned_start"] == "08:00"
    assert any("saqlandi" in (getattr(m, "text", "") or "").lower() for m in sent)
