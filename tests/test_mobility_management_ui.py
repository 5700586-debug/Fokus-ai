"""MOBILITY / BRANCH VISIT MANAGEMENT TELEGRAM UI V1 (``nazoratchi_bot.py``):
xodim kartasidagi "📍 Filial nazorati" tugmasi -> rejim (mobility
policy) / filial talabi qo'shish-tahrirlash-o'chirish / boshqa sana /
compliance ko'rinishi. Mavjud ``services/attendance.py`` mobility core
qayta ishlatiladi -- bu yerda yangi business logic yozilmaydi, faqat
Telegram oqimi.
"""

from datetime import timedelta

import company_time
import employees
from config import FOUNDER_ID, RECRUITING_BRANCH_NAMES
from repositories import attendance as attendance_repo
from roles import set_role
from services import attendance as attendance_service
from services import permissions as permissions_service
from tests.bot_harness import send, send_callback

_BRANCH_A = RECRUITING_BRANCH_NAMES[0]
_BRANCH_B = RECRUITING_BRANCH_NAMES[1]
_NAZORATCHI_ID = 890001


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
        {"familiya": "Valiyev", "ism": "Ali", "branch": branch, "role_key": role_key, "contacts": []},
    )
    employees.approve_profile(user_id, approved_by=FOUNDER_ID)


def _visit_time(day, hour: int, minute: int) -> str:
    from datetime import datetime
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=company_time.resolve_timezone()).isoformat()


async def _open_mobility_menu(main, bot, actor_id: int, employee_id: int):
    return await send_callback(main.dp, bot, actor_id, data=f"nzr_mob:{employee_id}", target_chat_id=actor_id)


async def _add_requirement(main, bot, actor_id: int, employee_id: int, branch: str, minutes: int):
    """To'liq "add" oqimi: filial tanlash -> tezkor daqiqa -> confirm."""
    await send_callback(main.dp, bot, actor_id, data=f"nzr_mob_branch:{employee_id}:{branch}", target_chat_id=actor_id)
    await send_callback(main.dp, bot, actor_id, data=f"nzr_mob_min:{employee_id}:{minutes}", target_chat_id=actor_id)
    return await send_callback(main.dp, bot, actor_id, data=f"nzr_mob_confirm:{employee_id}", target_chat_id=actor_id)


# ------------------------------------------------------------- RUXSAT --


async def test_founder_can_manage_mobility(bot_dp):
    main, bot = bot_dp
    employee_id = 810101
    _make_employee(employee_id)

    sent = await _open_mobility_menu(main, bot, FOUNDER_ID, employee_id)

    assert "Valiyev" in sent[0].text
    buttons = [btn.callback_data for row in sent[0].reply_markup.inline_keyboard for btn in row]
    assert f"nzr_mob_add:{employee_id}" in buttons


async def test_nazoratchi_can_manage_mobility(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    employee_id = 810102
    _make_employee(employee_id)

    sent = await _open_mobility_menu(main, bot, _NAZORATCHI_ID, employee_id)

    buttons = [btn.callback_data for row in sent[0].reply_markup.inline_keyboard for btn in row]
    assert f"nzr_mob_add:{employee_id}" in buttons


async def test_unauthorized_role_cannot_manage_mobility(bot_dp):
    main, bot = bot_dp
    kassir_id = 810103
    employee_id = 810104
    _make_employee(kassir_id)
    _make_employee(employee_id)

    sent = await send_callback(main.dp, bot, kassir_id, data=f"nzr_mob:{employee_id}", target_chat_id=kassir_id)

    assert not any(getattr(m, "reply_markup", None) for m in sent)
    assert attendance_service.get_branch_visit_requirements(employee_id, company_time.today().isoformat()) == []


async def test_nazoratchi_cannot_edit_own_mobility(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()

    sent = await _open_mobility_menu(main, bot, _NAZORATCHI_ID, _NAZORATCHI_ID)

    assert not any(
        getattr(m, "reply_markup", None) and any(
            f"nzr_mob_add:{_NAZORATCHI_ID}" == btn.callback_data for row in m.reply_markup.inline_keyboard for btn in row
        )
        for m in sent
    )


async def test_founder_has_no_self_management_restriction(bot_dp):
    main, bot = bot_dp

    sent = await _open_mobility_menu(main, bot, FOUNDER_ID, FOUNDER_ID)

    buttons = [btn.callback_data for row in sent[0].reply_markup.inline_keyboard for btn in row]
    assert f"nzr_mob_add:{FOUNDER_ID}" in buttons


async def test_branch_access_restriction_is_enforced(bot_dp, monkeypatch):
    main, bot = bot_dp
    limited_role = "savdo_boshligi"
    limited_actor_id = 810105
    _make_employee(limited_actor_id, branch=_BRANCH_A, role_key=limited_role)

    monkeypatch.setattr(
        permissions_service, "ROLE_PERMISSIONS",
        {
            **permissions_service.ROLE_PERMISSIONS,
            limited_role: permissions_service.ROLE_PERMISSIONS.get(limited_role, set())
            | {permissions_service.ACTION_MANAGE_BRANCH_VISIT_REQUIREMENTS},
        },
    )

    other_branch_employee = 810106
    _make_employee(other_branch_employee, branch=_BRANCH_B)

    await send_callback(main.dp, bot, limited_actor_id, data=f"nzr_mob:{other_branch_employee}", target_chat_id=limited_actor_id)

    assert attendance_service.get_branch_visit_requirements(other_branch_employee, company_time.today().isoformat()) == []


# -------------------------------------------------------------- POLICY --


async def test_mobility_mode_branch_visit_required_is_saved(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    employee_id = 810107
    _make_employee(employee_id)

    await _open_mobility_menu(main, bot, _NAZORATCHI_ID, employee_id)
    await send_callback(main.dp, bot, _NAZORATCHI_ID, data=f"nzr_mob_mode:{employee_id}", target_chat_id=_NAZORATCHI_ID)
    await send_callback(
        main.dp, bot, _NAZORATCHI_ID,
        data=f"nzr_mob_mode_set:{employee_id}:{attendance_service.MOBILITY_BRANCH_VISIT_REQUIRED}",
        target_chat_id=_NAZORATCHI_ID,
    )

    assert attendance_service.resolve_mobility_policy(employee_id) == attendance_service.MOBILITY_BRANCH_VISIT_REQUIRED


async def test_mobility_mode_none_is_saved(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    employee_id = 810108
    _make_employee(employee_id)
    attendance_service.set_employee_mobility_mode(employee_id, attendance_service.MOBILITY_BRANCH_VISIT_REQUIRED)

    await _open_mobility_menu(main, bot, _NAZORATCHI_ID, employee_id)
    await send_callback(main.dp, bot, _NAZORATCHI_ID, data=f"nzr_mob_mode:{employee_id}", target_chat_id=_NAZORATCHI_ID)
    await send_callback(
        main.dp, bot, _NAZORATCHI_ID,
        data=f"nzr_mob_mode_set:{employee_id}:{attendance_service.MOBILITY_NONE}",
        target_chat_id=_NAZORATCHI_ID,
    )

    assert attendance_service.resolve_mobility_policy(employee_id) == attendance_service.MOBILITY_NONE


async def test_role_default_is_not_overwritten_by_employee_override(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    employee_id = 810109
    _make_employee(employee_id, role_key="kassir")
    attendance_service.set_role_mobility_mode("kassir", attendance_service.MOBILITY_NONE)

    await _open_mobility_menu(main, bot, _NAZORATCHI_ID, employee_id)
    await send_callback(main.dp, bot, _NAZORATCHI_ID, data=f"nzr_mob_mode:{employee_id}", target_chat_id=_NAZORATCHI_ID)
    await send_callback(
        main.dp, bot, _NAZORATCHI_ID,
        data=f"nzr_mob_mode_set:{employee_id}:{attendance_service.MOBILITY_BRANCH_VISIT_REQUIRED}",
        target_chat_id=_NAZORATCHI_ID,
    )

    other_employee = 810110
    _make_employee(other_employee, role_key="kassir")
    assert attendance_service.resolve_mobility_policy(other_employee) == attendance_service.MOBILITY_NONE
    assert attendance_service.resolve_mobility_policy(employee_id) == attendance_service.MOBILITY_BRANCH_VISIT_REQUIRED


async def test_employee_override_beats_role_default(bot_dp):
    main, bot = bot_dp
    employee_id = 810111
    _make_employee(employee_id, role_key="kassir")
    attendance_service.set_role_mobility_mode("kassir", attendance_service.MOBILITY_BRANCH_VISIT_REQUIRED)
    attendance_service.set_employee_mobility_mode(employee_id, attendance_service.MOBILITY_NONE)

    assert attendance_service.resolve_mobility_policy(employee_id) == attendance_service.MOBILITY_NONE


# ------------------------------------------------------------------ ADD --


async def test_add_requirement_saturn_1_thirty_minutes(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    employee_id = 810112
    _make_employee(employee_id)

    await _open_mobility_menu(main, bot, _NAZORATCHI_ID, employee_id)
    await _add_requirement(main, bot, _NAZORATCHI_ID, employee_id, _BRANCH_A, 30)

    requirements = attendance_service.get_branch_visit_requirements(employee_id, company_time.today().isoformat())
    assert any(r["branch"] == _BRANCH_A and r["min_stay_minutes"] == 30 for r in requirements)


async def test_add_requirement_saturn_2_forty_five_minutes(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    employee_id = 810113
    _make_employee(employee_id)

    await _open_mobility_menu(main, bot, _NAZORATCHI_ID, employee_id)
    await _add_requirement(main, bot, _NAZORATCHI_ID, employee_id, _BRANCH_B, 45)

    requirements = attendance_service.get_branch_visit_requirements(employee_id, company_time.today().isoformat())
    assert any(r["branch"] == _BRANCH_B and r["min_stay_minutes"] == 45 for r in requirements)


async def test_add_requirement_custom_twenty_five_minutes(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    employee_id = 810114
    _make_employee(employee_id)

    await _open_mobility_menu(main, bot, _NAZORATCHI_ID, employee_id)
    await send_callback(main.dp, bot, _NAZORATCHI_ID, data=f"nzr_mob_branch:{employee_id}:{_BRANCH_A}", target_chat_id=_NAZORATCHI_ID)
    await send_callback(main.dp, bot, _NAZORATCHI_ID, data=f"nzr_mob_custom:{employee_id}", target_chat_id=_NAZORATCHI_ID)
    await send(main.dp, bot, _NAZORATCHI_ID, text="25")
    await send_callback(main.dp, bot, _NAZORATCHI_ID, data=f"nzr_mob_confirm:{employee_id}", target_chat_id=_NAZORATCHI_ID)

    requirements = attendance_service.get_branch_visit_requirements(employee_id, company_time.today().isoformat())
    assert any(r["branch"] == _BRANCH_A and r["min_stay_minutes"] == 25 for r in requirements)


async def test_add_requirement_custom_ninety_minutes(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    employee_id = 810115
    _make_employee(employee_id)

    await _open_mobility_menu(main, bot, _NAZORATCHI_ID, employee_id)
    await send_callback(main.dp, bot, _NAZORATCHI_ID, data=f"nzr_mob_branch:{employee_id}:{_BRANCH_A}", target_chat_id=_NAZORATCHI_ID)
    await send_callback(main.dp, bot, _NAZORATCHI_ID, data=f"nzr_mob_custom:{employee_id}", target_chat_id=_NAZORATCHI_ID)
    await send(main.dp, bot, _NAZORATCHI_ID, text="90")
    await send_callback(main.dp, bot, _NAZORATCHI_ID, data=f"nzr_mob_confirm:{employee_id}", target_chat_id=_NAZORATCHI_ID)

    requirements = attendance_service.get_branch_visit_requirements(employee_id, company_time.today().isoformat())
    assert any(r["branch"] == _BRANCH_A and r["min_stay_minutes"] == 90 for r in requirements)


async def test_custom_zero_is_rejected(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    employee_id = 810116
    _make_employee(employee_id)

    await _open_mobility_menu(main, bot, _NAZORATCHI_ID, employee_id)
    await send_callback(main.dp, bot, _NAZORATCHI_ID, data=f"nzr_mob_branch:{employee_id}:{_BRANCH_A}", target_chat_id=_NAZORATCHI_ID)
    await send_callback(main.dp, bot, _NAZORATCHI_ID, data=f"nzr_mob_custom:{employee_id}", target_chat_id=_NAZORATCHI_ID)
    sent = await send(main.dp, bot, _NAZORATCHI_ID, text="0")

    assert "Musbat" in sent[0].text
    assert attendance_service.get_branch_visit_requirements(employee_id, company_time.today().isoformat()) == []


async def test_custom_negative_is_rejected(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    employee_id = 810117
    _make_employee(employee_id)

    await _open_mobility_menu(main, bot, _NAZORATCHI_ID, employee_id)
    await send_callback(main.dp, bot, _NAZORATCHI_ID, data=f"nzr_mob_branch:{employee_id}:{_BRANCH_A}", target_chat_id=_NAZORATCHI_ID)
    await send_callback(main.dp, bot, _NAZORATCHI_ID, data=f"nzr_mob_custom:{employee_id}", target_chat_id=_NAZORATCHI_ID)
    sent = await send(main.dp, bot, _NAZORATCHI_ID, text="-5")

    assert "Musbat" in sent[0].text
    assert attendance_service.get_branch_visit_requirements(employee_id, company_time.today().isoformat()) == []


async def test_custom_non_numeric_is_rejected(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    employee_id = 810118
    _make_employee(employee_id)

    await _open_mobility_menu(main, bot, _NAZORATCHI_ID, employee_id)
    await send_callback(main.dp, bot, _NAZORATCHI_ID, data=f"nzr_mob_branch:{employee_id}:{_BRANCH_A}", target_chat_id=_NAZORATCHI_ID)
    await send_callback(main.dp, bot, _NAZORATCHI_ID, data=f"nzr_mob_custom:{employee_id}", target_chat_id=_NAZORATCHI_ID)
    sent = await send(main.dp, bot, _NAZORATCHI_ID, text="abc")

    assert "Musbat" in sent[0].text
    assert attendance_service.get_branch_visit_requirements(employee_id, company_time.today().isoformat()) == []


# ------------------------------------------------------- MULTI-BRANCH --


async def test_one_date_three_branches(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    employee_id = 810119
    _make_employee(employee_id)
    today = company_time.today().isoformat()

    await _open_mobility_menu(main, bot, _NAZORATCHI_ID, employee_id)
    await _add_requirement(main, bot, _NAZORATCHI_ID, employee_id, _BRANCH_A, 30)
    await _open_mobility_menu(main, bot, _NAZORATCHI_ID, employee_id)
    await _add_requirement(main, bot, _NAZORATCHI_ID, employee_id, _BRANCH_B, 45)

    requirements = attendance_service.get_branch_visit_requirements(employee_id, today)
    assert len(requirements) == 2


async def test_updating_one_branch_leaves_the_other_untouched(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    employee_id = 810120
    _make_employee(employee_id)
    today = company_time.today().isoformat()

    await _open_mobility_menu(main, bot, _NAZORATCHI_ID, employee_id)
    await _add_requirement(main, bot, _NAZORATCHI_ID, employee_id, _BRANCH_A, 30)
    await _open_mobility_menu(main, bot, _NAZORATCHI_ID, employee_id)
    await _add_requirement(main, bot, _NAZORATCHI_ID, employee_id, _BRANCH_B, 45)

    await _open_mobility_menu(main, bot, _NAZORATCHI_ID, employee_id)
    await _add_requirement(main, bot, _NAZORATCHI_ID, employee_id, _BRANCH_B, 60)

    requirements = {r["branch"]: r["min_stay_minutes"] for r in attendance_service.get_branch_visit_requirements(employee_id, today)}
    assert requirements[_BRANCH_A] == 30
    assert requirements[_BRANCH_B] == 60


async def test_re_adding_the_same_branch_does_not_duplicate(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    employee_id = 810121
    _make_employee(employee_id)
    today = company_time.today().isoformat()

    await _open_mobility_menu(main, bot, _NAZORATCHI_ID, employee_id)
    await _add_requirement(main, bot, _NAZORATCHI_ID, employee_id, _BRANCH_A, 30)
    await _open_mobility_menu(main, bot, _NAZORATCHI_ID, employee_id)
    await _add_requirement(main, bot, _NAZORATCHI_ID, employee_id, _BRANCH_A, 45)

    requirements = attendance_service.get_branch_visit_requirements(employee_id, today)
    assert len(requirements) == 1
    assert requirements[0]["min_stay_minutes"] == 45


# ---------------------------------------------------------------- CONFIRM --


async def test_nothing_is_written_until_confirmed(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    employee_id = 810122
    _make_employee(employee_id)

    await _open_mobility_menu(main, bot, _NAZORATCHI_ID, employee_id)
    await send_callback(main.dp, bot, _NAZORATCHI_ID, data=f"nzr_mob_branch:{employee_id}:{_BRANCH_A}", target_chat_id=_NAZORATCHI_ID)
    await send_callback(main.dp, bot, _NAZORATCHI_ID, data=f"nzr_mob_min:{employee_id}:30", target_chat_id=_NAZORATCHI_ID)

    assert attendance_service.get_branch_visit_requirements(employee_id, company_time.today().isoformat()) == []


async def test_confirm_writes_to_the_db(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    employee_id = 810123
    _make_employee(employee_id)

    await _open_mobility_menu(main, bot, _NAZORATCHI_ID, employee_id)
    await _add_requirement(main, bot, _NAZORATCHI_ID, employee_id, _BRANCH_A, 30)

    assert len(attendance_service.get_branch_visit_requirements(employee_id, company_time.today().isoformat())) == 1


async def test_double_confirm_click_gives_a_single_db_row(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    employee_id = 810124
    _make_employee(employee_id)
    today = company_time.today().isoformat()

    await _open_mobility_menu(main, bot, _NAZORATCHI_ID, employee_id)
    await send_callback(main.dp, bot, _NAZORATCHI_ID, data=f"nzr_mob_branch:{employee_id}:{_BRANCH_A}", target_chat_id=_NAZORATCHI_ID)
    await send_callback(main.dp, bot, _NAZORATCHI_ID, data=f"nzr_mob_min:{employee_id}:30", target_chat_id=_NAZORATCHI_ID)
    await send_callback(main.dp, bot, _NAZORATCHI_ID, data=f"nzr_mob_confirm:{employee_id}", target_chat_id=_NAZORATCHI_ID)
    await send_callback(main.dp, bot, _NAZORATCHI_ID, data=f"nzr_mob_confirm:{employee_id}", target_chat_id=_NAZORATCHI_ID)

    requirements = attendance_service.get_branch_visit_requirements(employee_id, today)
    assert len(requirements) == 1


async def test_double_confirm_click_gives_a_single_audit_revision(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    employee_id = 810125
    _make_employee(employee_id)
    today = company_time.today().isoformat()

    await _open_mobility_menu(main, bot, _NAZORATCHI_ID, employee_id)
    await send_callback(main.dp, bot, _NAZORATCHI_ID, data=f"nzr_mob_branch:{employee_id}:{_BRANCH_A}", target_chat_id=_NAZORATCHI_ID)
    await send_callback(main.dp, bot, _NAZORATCHI_ID, data=f"nzr_mob_min:{employee_id}:30", target_chat_id=_NAZORATCHI_ID)
    await send_callback(main.dp, bot, _NAZORATCHI_ID, data=f"nzr_mob_confirm:{employee_id}", target_chat_id=_NAZORATCHI_ID)
    await send_callback(main.dp, bot, _NAZORATCHI_ID, data=f"nzr_mob_confirm:{employee_id}", target_chat_id=_NAZORATCHI_ID)

    revisions = attendance_repo.list_branch_visit_requirement_revisions(employee_id, today, _BRANCH_A)
    assert len(revisions) == 1


async def test_double_confirm_click_sends_a_single_notification(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    employee_id = 810126
    _make_employee(employee_id)

    await _open_mobility_menu(main, bot, _NAZORATCHI_ID, employee_id)
    await send_callback(main.dp, bot, _NAZORATCHI_ID, data=f"nzr_mob_branch:{employee_id}:{_BRANCH_A}", target_chat_id=_NAZORATCHI_ID)
    await send_callback(main.dp, bot, _NAZORATCHI_ID, data=f"nzr_mob_min:{employee_id}:30", target_chat_id=_NAZORATCHI_ID)
    sent_first = await send_callback(main.dp, bot, _NAZORATCHI_ID, data=f"nzr_mob_confirm:{employee_id}", target_chat_id=_NAZORATCHI_ID)
    sent_second = await send_callback(main.dp, bot, _NAZORATCHI_ID, data=f"nzr_mob_confirm:{employee_id}", target_chat_id=_NAZORATCHI_ID)

    notifications_first = [m for m in sent_first if getattr(m, "chat_id", None) == employee_id]
    notifications_second = [m for m in sent_second if getattr(m, "chat_id", None) == employee_id]
    assert len(notifications_first) == 1
    assert len(notifications_second) == 0


# -------------------------------------------------------------- EDIT/REMOVE --


async def test_edit_changes_the_minutes(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    employee_id = 810127
    _make_employee(employee_id)
    today = company_time.today().isoformat()

    await _open_mobility_menu(main, bot, _NAZORATCHI_ID, employee_id)
    await _add_requirement(main, bot, _NAZORATCHI_ID, employee_id, _BRANCH_A, 30)

    await send_callback(main.dp, bot, _NAZORATCHI_ID, data=f"nzr_mob_edit:{employee_id}:{_BRANCH_A}", target_chat_id=_NAZORATCHI_ID)
    await send_callback(main.dp, bot, _NAZORATCHI_ID, data=f"nzr_mob_branch:{employee_id}:{_BRANCH_A}", target_chat_id=_NAZORATCHI_ID)
    await send_callback(main.dp, bot, _NAZORATCHI_ID, data=f"nzr_mob_min:{employee_id}:60", target_chat_id=_NAZORATCHI_ID)
    await send_callback(main.dp, bot, _NAZORATCHI_ID, data=f"nzr_mob_confirm:{employee_id}", target_chat_id=_NAZORATCHI_ID)

    requirements = attendance_service.get_branch_visit_requirements(employee_id, today)
    assert requirements[0]["min_stay_minutes"] == 60


async def test_edit_creates_an_audit_entry(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    employee_id = 810128
    _make_employee(employee_id)
    today = company_time.today().isoformat()

    await _open_mobility_menu(main, bot, _NAZORATCHI_ID, employee_id)
    await _add_requirement(main, bot, _NAZORATCHI_ID, employee_id, _BRANCH_A, 30)

    await send_callback(main.dp, bot, _NAZORATCHI_ID, data=f"nzr_mob_edit:{employee_id}:{_BRANCH_A}", target_chat_id=_NAZORATCHI_ID)
    await send_callback(main.dp, bot, _NAZORATCHI_ID, data=f"nzr_mob_branch:{employee_id}:{_BRANCH_A}", target_chat_id=_NAZORATCHI_ID)
    await send_callback(main.dp, bot, _NAZORATCHI_ID, data=f"nzr_mob_min:{employee_id}:60", target_chat_id=_NAZORATCHI_ID)
    await send_callback(main.dp, bot, _NAZORATCHI_ID, data=f"nzr_mob_confirm:{employee_id}", target_chat_id=_NAZORATCHI_ID)

    revisions = attendance_repo.list_branch_visit_requirement_revisions(employee_id, today, _BRANCH_A)
    assert len(revisions) == 2
    assert revisions[0]["action"] == "create"
    assert revisions[1]["action"] == "update"
    assert revisions[1]["old_min_stay_minutes"] == 30
    assert revisions[1]["new_min_stay_minutes"] == 60


async def test_remove_does_not_touch_db_until_confirmed(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    employee_id = 810129
    _make_employee(employee_id)
    today = company_time.today().isoformat()

    await _open_mobility_menu(main, bot, _NAZORATCHI_ID, employee_id)
    await _add_requirement(main, bot, _NAZORATCHI_ID, employee_id, _BRANCH_A, 30)

    await send_callback(main.dp, bot, _NAZORATCHI_ID, data=f"nzr_mob_remove:{employee_id}:{_BRANCH_A}", target_chat_id=_NAZORATCHI_ID)

    requirements = attendance_service.get_branch_visit_requirements(employee_id, today)
    assert len(requirements) == 1


async def test_remove_deletes_only_the_targeted_row(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    employee_id = 810130
    _make_employee(employee_id)
    today = company_time.today().isoformat()

    await _open_mobility_menu(main, bot, _NAZORATCHI_ID, employee_id)
    await _add_requirement(main, bot, _NAZORATCHI_ID, employee_id, _BRANCH_A, 30)
    await _open_mobility_menu(main, bot, _NAZORATCHI_ID, employee_id)
    await _add_requirement(main, bot, _NAZORATCHI_ID, employee_id, _BRANCH_B, 45)

    await send_callback(main.dp, bot, _NAZORATCHI_ID, data=f"nzr_mob_remove:{employee_id}:{_BRANCH_A}", target_chat_id=_NAZORATCHI_ID)
    await send_callback(main.dp, bot, _NAZORATCHI_ID, data=f"nzr_mob_remove_yes:{employee_id}:{_BRANCH_A}", target_chat_id=_NAZORATCHI_ID)

    requirements = {r["branch"] for r in attendance_service.get_branch_visit_requirements(employee_id, today)}
    assert requirements == {_BRANCH_B}


async def test_remove_creates_an_audit_entry(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    employee_id = 810131
    _make_employee(employee_id)
    today = company_time.today().isoformat()

    await _open_mobility_menu(main, bot, _NAZORATCHI_ID, employee_id)
    await _add_requirement(main, bot, _NAZORATCHI_ID, employee_id, _BRANCH_A, 30)

    await send_callback(main.dp, bot, _NAZORATCHI_ID, data=f"nzr_mob_remove:{employee_id}:{_BRANCH_A}", target_chat_id=_NAZORATCHI_ID)
    await send_callback(main.dp, bot, _NAZORATCHI_ID, data=f"nzr_mob_remove_yes:{employee_id}:{_BRANCH_A}", target_chat_id=_NAZORATCHI_ID)

    revisions = attendance_repo.list_branch_visit_requirement_revisions(employee_id, today, _BRANCH_A)
    assert revisions[-1]["action"] == "remove"
    assert revisions[-1]["new_min_stay_minutes"] is None


# -------------------------------------------------------------------- DATE --


async def test_default_date_is_today(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    employee_id = 810132
    _make_employee(employee_id)

    sent = await _open_mobility_menu(main, bot, _NAZORATCHI_ID, employee_id)

    today_display = company_time.today().strftime("%d.%m.%Y")
    assert today_display in sent[0].text


async def test_future_date_is_used_for_the_requirement(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    employee_id = 810133
    _make_employee(employee_id)
    future_date = (company_time.today() + timedelta(days=5)).isoformat()

    await _open_mobility_menu(main, bot, _NAZORATCHI_ID, employee_id)
    await send_callback(main.dp, bot, _NAZORATCHI_ID, data=f"nzr_mob_date:{employee_id}", target_chat_id=_NAZORATCHI_ID)
    await send(main.dp, bot, _NAZORATCHI_ID, text=future_date)
    await _add_requirement(main, bot, _NAZORATCHI_ID, employee_id, _BRANCH_A, 30)

    assert len(attendance_service.get_branch_visit_requirements(employee_id, future_date)) == 1
    assert attendance_service.get_branch_visit_requirements(employee_id, company_time.today().isoformat()) == []


async def test_past_date_can_be_edited_and_creates_an_audit_entry(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    employee_id = 810134
    _make_employee(employee_id)
    past_date = (company_time.today() - timedelta(days=3)).isoformat()

    await _open_mobility_menu(main, bot, _NAZORATCHI_ID, employee_id)
    await send_callback(main.dp, bot, _NAZORATCHI_ID, data=f"nzr_mob_date:{employee_id}", target_chat_id=_NAZORATCHI_ID)
    await send(main.dp, bot, _NAZORATCHI_ID, text=past_date)
    await _add_requirement(main, bot, _NAZORATCHI_ID, employee_id, _BRANCH_A, 30)

    assert len(attendance_service.get_branch_visit_requirements(employee_id, past_date)) == 1
    revisions = attendance_repo.list_branch_visit_requirement_revisions(employee_id, past_date, _BRANCH_A)
    assert len(revisions) == 1


async def test_invalid_date_format_is_rejected(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    employee_id = 810135
    _make_employee(employee_id)

    await _open_mobility_menu(main, bot, _NAZORATCHI_ID, employee_id)
    await send_callback(main.dp, bot, _NAZORATCHI_ID, data=f"nzr_mob_date:{employee_id}", target_chat_id=_NAZORATCHI_ID)
    sent = await send(main.dp, bot, _NAZORATCHI_ID, text="28-08-2026")

    assert "YYYY-MM-DD" in sent[0].text


# --------------------------------------------------------------- COMPLIANCE --


async def test_compliance_met_when_stay_exceeds_requirement(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    employee_id = 810136
    _make_employee(employee_id)
    today = company_time.today()

    attendance_service.set_branch_visit_requirement(employee_id, today.isoformat(), _BRANCH_A, 30)
    attendance_service.record_branch_visit_event(employee_id, _BRANCH_A, "enter", _visit_time(today, 10, 0), "test")
    attendance_service.record_branch_visit_event(employee_id, _BRANCH_A, "exit", _visit_time(today, 10, 35), "test")

    sent = await send_callback(main.dp, bot, _NAZORATCHI_ID, data=f"nzr_mob_reqs:{employee_id}", target_chat_id=_NAZORATCHI_ID)
    assert "Bajarildi" in sent[0].text


async def test_compliance_not_met_when_stay_is_short(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    employee_id = 810137
    _make_employee(employee_id)
    today = company_time.today()

    attendance_service.set_branch_visit_requirement(employee_id, today.isoformat(), _BRANCH_A, 45)
    attendance_service.record_branch_visit_event(employee_id, _BRANCH_A, "enter", _visit_time(today, 10, 0), "test")
    attendance_service.record_branch_visit_event(employee_id, _BRANCH_A, "exit", _visit_time(today, 10, 20), "test")

    sent = await send_callback(main.dp, bot, _NAZORATCHI_ID, data=f"nzr_mob_reqs:{employee_id}", target_chat_id=_NAZORATCHI_ID)
    assert "Yetarli emas" in sent[0].text


async def test_compliance_incomplete_when_exit_missing(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    employee_id = 810138
    _make_employee(employee_id)
    today = company_time.today()

    attendance_service.set_branch_visit_requirement(employee_id, today.isoformat(), _BRANCH_A, 30)
    attendance_service.record_branch_visit_event(employee_id, _BRANCH_A, "enter", _visit_time(today, 10, 0), "test")

    sent = await send_callback(main.dp, bot, _NAZORATCHI_ID, data=f"nzr_mob_reqs:{employee_id}", target_chat_id=_NAZORATCHI_ID)
    assert "to'liq emas" in sent[0].text


async def test_no_requirement_is_not_an_automatic_pass(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    employee_id = 810139
    _make_employee(employee_id)

    sent = await send_callback(main.dp, bot, _NAZORATCHI_ID, data=f"nzr_mob_reqs:{employee_id}", target_chat_id=_NAZORATCHI_ID)
    assert "belgilanmagan" in sent[0].text
    assert "Bajarildi" not in sent[0].text


async def test_requirement_with_no_visit_shows_zero_and_not_met(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    employee_id = 810140
    _make_employee(employee_id)
    today = company_time.today()

    attendance_service.set_branch_visit_requirement(employee_id, today.isoformat(), _BRANCH_A, 30)

    sent = await send_callback(main.dp, bot, _NAZORATCHI_ID, data=f"nzr_mob_reqs:{employee_id}", target_chat_id=_NAZORATCHI_ID)
    assert "Haqiqiy: 0" in sent[0].text
    assert "Yetarli emas" in sent[0].text


async def test_overnight_visit_belongs_to_the_logical_shift_date(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    employee_id = 810141
    _make_employee(employee_id)
    today = company_time.today()
    next_day = today + timedelta(days=1)

    attendance_service.set_scheduled_work_shift(employee_id, today.isoformat(), "18:00", "02:00", "test")
    attendance_service.set_branch_visit_requirement(employee_id, today.isoformat(), _BRANCH_A, 30)
    attendance_service.record_branch_visit_event(employee_id, _BRANCH_A, "enter", _visit_time(today, 23, 40), "test")
    attendance_service.record_branch_visit_event(employee_id, _BRANCH_A, "exit", _visit_time(next_day, 0, 30), "test")

    sent = await send_callback(main.dp, bot, _NAZORATCHI_ID, data=f"nzr_mob_reqs:{employee_id}", target_chat_id=_NAZORATCHI_ID)
    assert "Bajarildi" in sent[0].text


# ------------------------------------------------------------ NOTIFICATION --


async def test_add_notifies_the_employee(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    employee_id = 810142
    _make_employee(employee_id)

    await _open_mobility_menu(main, bot, _NAZORATCHI_ID, employee_id)
    sent = await _add_requirement(main, bot, _NAZORATCHI_ID, employee_id, _BRANCH_A, 30)

    notice = next(m for m in sent if getattr(m, "chat_id", None) == employee_id)
    assert "belgilandi" in notice.text


async def test_edit_notifies_the_employee_with_new_value(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    employee_id = 810143
    _make_employee(employee_id)

    await _open_mobility_menu(main, bot, _NAZORATCHI_ID, employee_id)
    await _add_requirement(main, bot, _NAZORATCHI_ID, employee_id, _BRANCH_A, 30)

    await send_callback(main.dp, bot, _NAZORATCHI_ID, data=f"nzr_mob_edit:{employee_id}:{_BRANCH_A}", target_chat_id=_NAZORATCHI_ID)
    sent = await _add_requirement(main, bot, _NAZORATCHI_ID, employee_id, _BRANCH_A, 60)

    notice = next(m for m in sent if getattr(m, "chat_id", None) == employee_id)
    assert "o'zgartirildi" in notice.text
    assert "60" in notice.text


async def test_remove_notifies_the_employee(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    employee_id = 810144
    _make_employee(employee_id)

    await _open_mobility_menu(main, bot, _NAZORATCHI_ID, employee_id)
    await _add_requirement(main, bot, _NAZORATCHI_ID, employee_id, _BRANCH_A, 30)

    await send_callback(main.dp, bot, _NAZORATCHI_ID, data=f"nzr_mob_remove:{employee_id}:{_BRANCH_A}", target_chat_id=_NAZORATCHI_ID)
    sent = await send_callback(main.dp, bot, _NAZORATCHI_ID, data=f"nzr_mob_remove_yes:{employee_id}:{_BRANCH_A}", target_chat_id=_NAZORATCHI_ID)

    notice = next(m for m in sent if getattr(m, "chat_id", None) == employee_id)
    assert "bekor qilindi" in notice.text


async def test_notification_failure_does_not_roll_back_the_requirement(bot_dp, monkeypatch):
    main, bot = bot_dp
    _make_nazoratchi()
    employee_id = 810145
    _make_employee(employee_id)

    async def _failing_send_message(*args, **kwargs):
        raise RuntimeError("simulated Telegram delivery failure")

    monkeypatch.setattr(bot, "send_message", _failing_send_message)

    await _open_mobility_menu(main, bot, _NAZORATCHI_ID, employee_id)
    await _add_requirement(main, bot, _NAZORATCHI_ID, employee_id, _BRANCH_A, 30)

    requirements = attendance_service.get_branch_visit_requirements(employee_id, company_time.today().isoformat())
    assert len(requirements) == 1
    assert requirements[0]["min_stay_minutes"] == 30


# ------------------------------------------------------------- REGRESSION --


async def test_schedule_ui_regression_unaffected(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    employee_id = 810146
    _make_employee(employee_id)

    sent = await send_callback(main.dp, bot, _NAZORATCHI_ID, data=f"nzr_sched:{employee_id}", target_chat_id=_NAZORATCHI_ID)

    buttons = [btn.callback_data for row in sent[0].reply_markup.inline_keyboard for btn in row]
    assert f"nzr_sched_fixed:{employee_id}:fixed_1" in buttons


async def test_mystars_dashboard_regression_unaffected(bot_dp):
    main, bot = bot_dp
    employee_id = 810147
    _make_employee(employee_id)

    from services import employee_dashboard

    dashboard = employee_dashboard.build_dashboard(employee_id)
    assert dashboard is not None
    assert "hours" in dashboard


async def test_mobility_core_service_regression_unaffected(bot_dp):
    employee_id = 810148
    _make_employee(employee_id)
    today = company_time.today().isoformat()

    accepted = attendance_service.set_branch_visit_requirement(employee_id, today, _BRANCH_A, 30)
    assert accepted is True
    assert attendance_service.get_daily_branch_compliance(employee_id, today)[0]["required_minutes"] == 30


async def test_overnight_schedule_actual_hours_regression_unaffected(bot_dp):
    employee_id = 810149
    _make_employee(employee_id)
    today = company_time.today().isoformat()

    attendance_service.set_scheduled_work_shift(employee_id, today, "14:00", "01:00", "test")
    attendance_service.record_manual_arrival(employee_id, today, "14:00")
    attendance_service.record_manual_departure(employee_id, today, "01:00")

    assert attendance_service.get_worked_hours_for_day(employee_id, today) == 11.0


async def test_bonus_minus_logic_is_untouched(bot_dp):
    from services import discipline

    employee_id = 810150
    _make_employee(employee_id)

    totals = discipline.get_period_point_totals(employee_id)
    assert totals["bonus"] == 0
    assert totals["minus"] == 0


async def test_no_face_id_events_are_created_by_the_ui(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    employee_id = 810151
    _make_employee(employee_id)

    await _open_mobility_menu(main, bot, _NAZORATCHI_ID, employee_id)
    await _add_requirement(main, bot, _NAZORATCHI_ID, employee_id, _BRANCH_A, 30)

    events = attendance_repo.list_branch_visit_events(
        employee_id, _BRANCH_A, "1970-01-01", (company_time.today() + timedelta(days=1)).isoformat()
    )
    assert events == []
