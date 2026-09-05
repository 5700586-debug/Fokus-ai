"""E2E test avtomatizatsiyasi uchun statik ("virtual") ``Sinovchi``
roli — faqat ``roles.E2E_TESTER_TELEGRAM_ID``ga bog'langan, boshqa
hech kim (Founder ham) unga ega bo'la olmasligini tekshiradi.
"""

import pytest

import employees
import roles
from config import FOUNDER_ID
from services import permissions
from tests.bot_harness import send, texts

pytestmark = pytest.mark.anyio

_OTHER_USER_ID = 111222333
_TESTER_ID = roles.E2E_TESTER_TELEGRAM_ID


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_only_tester_id_gets_e2e_test_permissions():
    assert permissions.has_permission(_TESTER_ID, permissions.ACTION_E2E_TEST_CASH_SHIFT) is True
    assert permissions.has_permission(_TESTER_ID, permissions.ACTION_E2E_VIEW_TEST_RUN) is True

    assert permissions.has_permission(_OTHER_USER_ID, permissions.ACTION_E2E_TEST_CASH_SHIFT) is False
    assert permissions.has_permission(_OTHER_USER_ID, permissions.ACTION_E2E_VIEW_TEST_RUN) is False


def test_founder_does_not_get_e2e_test_permissions_either():
    """Bog'lanish qat'iy BITTA ID'ga — Founder bypass ham bunga
    taalluqli emas (roles.py'dagi talab)."""
    assert permissions.has_permission(FOUNDER_ID, permissions.ACTION_E2E_TEST_CASH_SHIFT) is False
    assert permissions.has_permission(FOUNDER_ID, permissions.ACTION_E2E_VIEW_TEST_RUN) is False


def test_tester_never_becomes_founder_or_admin():
    assert roles.get_role(_TESTER_ID) is None
    assert roles.get_role(_TESTER_ID) != "founder"
    assert roles.is_authorized(_TESTER_ID) is False
    assert _TESTER_ID != FOUNDER_ID


def test_is_e2e_tester_only_matches_exact_id():
    assert roles.is_e2e_tester(_TESTER_ID) is True
    assert roles.is_e2e_tester(_OTHER_USER_ID) is False
    assert roles.is_e2e_tester(FOUNDER_ID) is False


def test_tester_absent_from_role_user_list():
    assert _TESTER_ID not in roles.list_users()


def test_tester_has_no_employee_profile():
    assert employees.get_profile(_TESTER_ID) is None


def test_tester_absent_from_approved_branch_lists():
    from roles import set_role

    set_role(999888777, "kassir", set_by=FOUNDER_ID)
    employees.submit_profile(
        999888777,
        {
            "familiya": "Realov", "ism": "Vali", "otasining_ismi": "Ali",
            "branch": "Filial-1", "role_key": "kassir", "contacts": [],
        },
    )

    branch_employees = employees.list_approved_by_branch("Filial-1")
    assert all(profile["user_id"] != _TESTER_ID for profile in branch_employees)


async def test_other_user_cannot_start_test_shift(bot_dp):
    main, bot = bot_dp
    sent = await send(main.dp, bot, _OTHER_USER_ID, text="/sinovsmena")
    combined = " ".join(t for t in texts(sent) if t)
    assert combined != ""
    assert "TEST smena boshlandi" not in combined


async def test_founder_cannot_start_test_shift(bot_dp):
    main, bot = bot_dp
    sent = await send(main.dp, bot, FOUNDER_ID, text="/sinovsmena")
    combined = " ".join(t for t in texts(sent) if t)
    assert "TEST smena boshlandi" not in combined


async def test_tester_can_start_test_shift(bot_dp):
    main, bot = bot_dp
    sent = await send(main.dp, bot, _TESTER_ID, text="/sinovsmena")
    combined = " ".join(t for t in texts(sent) if t)
    assert "TEST smena boshlandi" in combined


async def test_other_user_cannot_view_test_run_via_xarid(bot_dp):
    main, bot = bot_dp
    sent = await send(main.dp, bot, _OTHER_USER_ID, text="/xarid")
    combined = " ".join(t for t in texts(sent) if t)
    assert "TEST" not in combined


def test_no_parallel_e2e_test_flow_remains_in_cash_shift_bot():
    """Tuzatish: fake parallel oqim butunlay olib tashlangan — faqat
    REAL ``DeficiencyStates``/``csdef_list_*`` handlerlari qoladi,
    ``/xarid`` uchun ikkinchi (dublikat) handler yo'q."""
    import inspect

    import cash_shift_bot

    assert not hasattr(cash_shift_bot, "E2ETestStates")
    assert not hasattr(cash_shift_bot, "_advance_e2e_test_list")
    assert not hasattr(cash_shift_bot, "_process_e2e_test_list")

    source = inspect.getsource(cash_shift_bot)
    assert "e2etest_list_confirm" not in source
    assert "e2etest_list_edit" not in source
    assert 'Command("xarid")' not in source


def test_main_py_handler_registration_order_matches_commit_9f84a6b():
    """Tuzatish: ro'yxatdan o'tkazish tartibi aynan
    ``9f84a6b600be153d9840bb5425eb4f06ecd4583c``dagi kabi (E2E test
    ``Command("xarid")`` interceptori uchun qilingan qayta tartiblash
    butunlay bekor qilingan)."""
    import inspect
    import re

    import main

    source = inspect.getsource(main)
    calls = re.findall(r"^(\w+)\.register\(dp", source, re.MULTILINE)

    expected = [
        "onboarding", "approval", "performance_bot", "cash_shift_bot",
        "inventory_bot", "calibration_bot", "discipline_bot", "supplier_chat_bot",
        "saturn_group_bot", "recruiting_bot", "nazoratchi_bot",
    ]
    assert calls == expected
