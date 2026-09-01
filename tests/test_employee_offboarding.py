"""XODIMNI ISHDAN CHIQARISH / TARIXNI SAQLASH V1 (``nazoratchi_bot.py``):
xodim kartasidagi "🚪 Ishdan chiqarish" tugmasi -> tasdiqlash ekrani ->
``employees.status`` YAGONA kanonik ustunida ``approved`` -> ``offboarded``.
Hech qanday yozuv o'chirilmaydi — bu yerdagi testlar aynan shuni
(tarix + idempotentlik + RBAC/filial chegarasi) tekshiradi.
"""

import pytest

import company_time
import employees
from config import FOUNDER_ID, RECRUITING_BRANCH_NAMES
from repositories import attendance as attendance_repo
from repositories import audit as audit_repo
from repositories import discipline as discipline_repo
from repositories import tasks as tasks_repo
from roles import set_role
from services import attendance as attendance_service
from services import audit as audit_service
from services import permissions as permissions_service
from services import tasks as tasks_service
from tests.bot_harness import send_callback

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


_BRANCH_A = RECRUITING_BRANCH_NAMES[0]
_BRANCH_B = RECRUITING_BRANCH_NAMES[1]
_NAZORATCHI_ID = 920001


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


async def _open_confirm(main, bot, actor_id: int, employee_id: int):
    return await send_callback(main.dp, bot, actor_id, data=f"nzr_offb:{employee_id}", target_chat_id=actor_id)


async def _confirm(main, bot, actor_id: int, employee_id: int):
    return await send_callback(main.dp, bot, actor_id, data=f"nzr_offb_yes:{employee_id}", target_chat_id=actor_id)


def _offboard_audit_events(employee_id: int) -> list[dict]:
    return [
        event
        for event in audit_repo.list_events()
        if event["event_type"] == audit_service.EVENT_EMPLOYEE_OFFBOARDED
        and event["target_id"] == employee_id
    ]


# ------------------------------------------------------------- RUXSAT --


async def test_employee_card_has_offboard_button(bot_dp):
    main, bot = bot_dp
    employee_id = 920101
    _make_employee(employee_id)

    sent = await send_callback(main.dp, bot, FOUNDER_ID, data=f"nzr_emp:{employee_id}", target_chat_id=FOUNDER_ID)

    buttons = [btn.callback_data for row in sent[0].reply_markup.inline_keyboard for btn in row]
    assert f"nzr_offb:{employee_id}" in buttons


async def test_founder_can_offboard_employee(bot_dp):
    main, bot = bot_dp
    employee_id = 920102
    _make_employee(employee_id)

    confirm_screen = await _open_confirm(main, bot, FOUNDER_ID, employee_id)
    assert "Valiyev" in confirm_screen[0].text
    assert _BRANCH_A in confirm_screen[0].text
    assert "Tarix o'chmaydi" in confirm_screen[0].text

    await _confirm(main, bot, FOUNDER_ID, employee_id)

    assert employees.get_status(employee_id) == employees.STATUS_OFFBOARDED


async def test_nazoratchi_can_offboard_employee_in_accessible_branch(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    employee_id = 920103
    _make_employee(employee_id)

    await _open_confirm(main, bot, _NAZORATCHI_ID, employee_id)
    await _confirm(main, bot, _NAZORATCHI_ID, employee_id)

    assert employees.get_status(employee_id) == employees.STATUS_OFFBOARDED


async def test_branch_access_restriction_is_enforced(bot_dp, monkeypatch):
    """Mavjud ``can_access_branch`` qoidasi qayta ishlatiladi: amalga
    ruxsati bo'lgan, lekin filiallararo huquqi yo'q rol boshqa filial
    xodimini ishdan chiqara olmaydi."""
    main, bot = bot_dp
    limited_role = "savdo_boshligi"
    limited_actor_id = 920104
    _make_employee(limited_actor_id, branch=_BRANCH_A, role_key=limited_role)

    monkeypatch.setattr(
        permissions_service, "ROLE_PERMISSIONS",
        {
            **permissions_service.ROLE_PERMISSIONS,
            limited_role: permissions_service.ROLE_PERMISSIONS.get(limited_role, set())
            | {permissions_service.ACTION_OFFBOARD_EMPLOYEE},
        },
    )

    other_branch_employee = 920105
    _make_employee(other_branch_employee, branch=_BRANCH_B)

    await _confirm(main, bot, limited_actor_id, other_branch_employee)

    assert employees.get_status(other_branch_employee) == employees.STATUS_APPROVED
    assert _offboard_audit_events(other_branch_employee) == []


async def test_unauthorized_role_cannot_offboard(bot_dp):
    main, bot = bot_dp
    kassir_id = 920106
    employee_id = 920107
    _make_employee(kassir_id)
    _make_employee(employee_id)

    await _confirm(main, bot, kassir_id, employee_id)

    assert employees.get_status(employee_id) == employees.STATUS_APPROVED
    assert _offboard_audit_events(employee_id) == []


async def test_founder_cannot_offboard_himself(bot_dp):
    main, bot = bot_dp
    _make_employee(FOUNDER_ID)

    await _confirm(main, bot, FOUNDER_ID, FOUNDER_ID)

    assert employees.get_status(FOUNDER_ID) == employees.STATUS_APPROVED
    assert _offboard_audit_events(FOUNDER_ID) == []


async def test_nazoratchi_cannot_offboard_himself(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()

    await _confirm(main, bot, _NAZORATCHI_ID, _NAZORATCHI_ID)

    assert employees.get_status(_NAZORATCHI_ID) == employees.STATUS_APPROVED
    assert _offboard_audit_events(_NAZORATCHI_ID) == []


# -------------------------------------------------------------- OQIM --


async def test_nothing_changes_until_confirmed(bot_dp):
    main, bot = bot_dp
    employee_id = 920108
    _make_employee(employee_id)

    await _open_confirm(main, bot, FOUNDER_ID, employee_id)

    assert employees.get_status(employee_id) == employees.STATUS_APPROVED
    assert _offboard_audit_events(employee_id) == []


async def test_cancel_returns_to_the_employee_card(bot_dp):
    main, bot = bot_dp
    employee_id = 920109
    _make_employee(employee_id)

    await _open_confirm(main, bot, FOUNDER_ID, employee_id)
    sent = await send_callback(main.dp, bot, FOUNDER_ID, data=f"nzr_offb_no:{employee_id}", target_chat_id=FOUNDER_ID)

    buttons = [btn.callback_data for row in sent[0].reply_markup.inline_keyboard for btn in row]
    assert f"nzr_offb:{employee_id}" in buttons
    assert employees.get_status(employee_id) == employees.STATUS_APPROVED


async def test_offboarding_is_audited(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    employee_id = 920110
    _make_employee(employee_id)

    await _confirm(main, bot, _NAZORATCHI_ID, employee_id)

    events = _offboard_audit_events(employee_id)
    assert len(events) == 1
    assert events[0]["actor_id"] == _NAZORATCHI_ID
    assert events[0]["actor_role"] == "nazoratchi"
    assert events[0]["old_value"] == employees.STATUS_APPROVED
    assert events[0]["new_value"] == employees.STATUS_OFFBOARDED
    assert events[0]["created_at"]


async def test_double_confirm_gives_a_single_state_transition_and_audit(bot_dp):
    main, bot = bot_dp
    employee_id = 920111
    _make_employee(employee_id)

    await _confirm(main, bot, FOUNDER_ID, employee_id)
    second = await _confirm(main, bot, FOUNDER_ID, employee_id)

    assert employees.get_status(employee_id) == employees.STATUS_OFFBOARDED
    assert len(_offboard_audit_events(employee_id)) == 1
    # Ikkinchi bosishda xodimga takroriy xabar ketmaydi.
    assert not [m for m in second if getattr(m, "chat_id", None) == employee_id]


async def test_employee_is_notified_once(bot_dp):
    main, bot = bot_dp
    employee_id = 920112
    _make_employee(employee_id)

    sent = await _confirm(main, bot, FOUNDER_ID, employee_id)

    notifications = [m for m in sent if getattr(m, "chat_id", None) == employee_id]
    assert len(notifications) == 1


async def test_notification_failure_does_not_roll_back_the_state_change(bot_dp, monkeypatch):
    main, bot = bot_dp
    employee_id = 920113
    _make_employee(employee_id)

    original_call = bot.__class__.__call__

    async def failing_call(self, method, request_timeout=None):
        if getattr(method, "chat_id", None) == employee_id:
            raise RuntimeError("Telegram xatosi")
        return await original_call(self, method, request_timeout)

    monkeypatch.setattr(bot.__class__, "__call__", failing_call)

    await _confirm(main, bot, FOUNDER_ID, employee_id)

    assert employees.get_status(employee_id) == employees.STATUS_OFFBOARDED
    assert len(_offboard_audit_events(employee_id)) == 1


# ------------------------------------------------------- TARIX SAQLANADI --


async def test_offboarded_employee_disappears_from_the_active_list(bot_dp):
    main, bot = bot_dp
    employee_id = 920114
    _make_employee(employee_id)
    assert employee_id in [p["user_id"] for p in employees.list_approved_by_branch(_BRANCH_A)]

    await _confirm(main, bot, FOUNDER_ID, employee_id)

    assert employee_id not in [p["user_id"] for p in employees.list_approved_by_branch(_BRANCH_A)]


async def test_history_is_preserved_after_offboarding(bot_dp):
    main, bot = bot_dp
    employee_id = 920115
    _make_employee(employee_id)
    today = company_time.today().isoformat()

    discipline_repo.adjust_bonus_bank(employee_id, -30, "test", "penalty", None)
    attendance_repo.record_event(employee_id, "check_in", f"{today}T09:00:00", "test")
    tasks_service.assign_task_to_employee("Zal tozaligi", employee_id, assigned_by=FOUNDER_ID)
    attendance_service.set_scheduled_work_shift(
        employee_id, today, "09:00", "18:00", source="test", created_by=FOUNDER_ID
    )

    await _confirm(main, bot, FOUNDER_ID, employee_id)

    profile = employees.get_profile(employee_id)
    assert profile is not None
    assert profile["familiya"] == "Valiyev"
    assert profile["status"] == employees.STATUS_OFFBOARDED
    assert len(discipline_repo.get_bonus_ledger(employee_id)) == 1
    assert len(attendance_repo.list_events_for_date(employee_id, today)) == 1
    assert tasks_repo.list_tasks_for_employee(employee_id)
    assert attendance_service.get_shift_for_date(employee_id, today) is not None
