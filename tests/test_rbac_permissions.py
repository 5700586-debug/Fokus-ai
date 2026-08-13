"""RBAC markazlashtirilgan mexanizmi uchun testlar.

Ikki qatlam tekshiriladi:
1. Sof birlik testlar (``services/permissions.py``): yangi Founder-only
   ``ACTION_*``lar, ``has_any_permission()``, ``can_access_branch()``,
   ``ensure_permission()``/``ensure_any_permission()`` — ruxsat berilgan,
   taqiqlangan va noma'lum (ro'yxatdan o'tmagan) foydalanuvchi holatlari
   uchun.
2. Uchidan-uchigacha regressiya (``bot_dp``): ilgari to'g'ridan-to'g'ri
   ``FOUNDER_ID`` bilan tekshirilgan, endi markazlashtirilgan mexanizmga
   o'tkazilgan buyruqlar — Founder ishlayapti, boshqa rol va begona
   foydalanuvchi qisqa "Saturncha" javob bilan rad etilyapti (endi jim
   emas — qarang ``services/messages.py``).
"""

import os
from datetime import datetime

import pytest
from aiogram.methods import AnswerCallbackQuery
from aiogram.types import CallbackQuery, Chat, Message
from aiogram.types import User as TgUser

from config import FOUNDER_ID
from roles import ROLES
from services import messages as messages_catalog
from services import permissions
from tests.bot_harness import RecordingBot, make_message, send, send_callback

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _set_role(user_id: int, role_key: str) -> None:
    from roles import set_role

    set_role(user_id, role_key, set_by=FOUNDER_ID)


_DENIAL_TEXTS = {
    messages_catalog.GENERIC_DENIAL,
    messages_catalog.CASH_FINANCE_DENIAL,
    messages_catalog.MANAGEMENT_DENIAL,
    messages_catalog.REPEAT_OFFENDER_DENIAL,
}


def _assert_denied(sent) -> None:
    """Ruxsatsiz urinish endi JIM emas — bitta qisqa "Saturncha" javob
    yuboriladi (aynan qaysi matn takroriy-urinish holatiga bog'liq bo'lishi
    mumkin, shuning uchun to'plamga a'zolik tekshiriladi, aniq matnga emas).
    """
    assert len(sent) == 1, sent
    assert sent[0].text in _DENIAL_TEXTS, sent[0].text


# --------------------------------------------------------- has_permission --

_NEW_FOUNDER_ONLY_ACTIONS = sorted(
    {
        permissions.ACTION_MANAGE_INVITES,
        permissions.ACTION_MANAGE_ROLES,
        permissions.ACTION_REMOVE_USER,
        permissions.ACTION_LIST_USERS,
        permissions.ACTION_VIEW_PROFILE,
        permissions.ACTION_APPROVE_APPLICANT,
        permissions.ACTION_MANAGE_DISCIPLINE_RULES,
        permissions.ACTION_SET_SALARY,
        permissions.ACTION_LOOKUP_ANY_SALARY,
        permissions.ACTION_DECIDE_APPEAL,
        permissions.ACTION_SET_RULE,
        permissions.ACTION_LIST_RULES,
        permissions.ACTION_PROCESS_MONTH,
        permissions.ACTION_MANAGE_VEHICLES,
        permissions.ACTION_SATURN_TEST,
        permissions.ACTION_INVITE_SUPPLIER,
        permissions.ACTION_LIST_SUPPLIERS,
        permissions.ACTION_SUPPLIER_REPORT,
        permissions.ACTION_COMPARE_SUPPLIERS,
    }
)

_NON_FOUNDER_ROLES = [key for key in ROLES if key != "founder"]


def test_founder_only_actions_absent_from_role_permissions_table():
    granted_anywhere = set()
    for actions in permissions.ROLE_PERMISSIONS.values():
        granted_anywhere |= actions

    overlap = granted_anywhere & set(_NEW_FOUNDER_ONLY_ACTIONS)
    assert overlap == set(), f"Founder-only amallar rolga biriktirilib qo'yilgan: {overlap}"


@pytest.mark.parametrize("action", _NEW_FOUNDER_ONLY_ACTIONS)
def test_founder_only_action_granted_to_founder(monkeypatch, action):
    monkeypatch.setattr(permissions, "get_role", lambda user_id: "founder")
    assert permissions.has_permission(1, action) is True


@pytest.mark.parametrize("role_key", _NON_FOUNDER_ROLES)
@pytest.mark.parametrize("action", _NEW_FOUNDER_ONLY_ACTIONS)
def test_founder_only_action_denied_for_every_non_founder_role(monkeypatch, action, role_key):
    monkeypatch.setattr(permissions, "get_role", lambda user_id: role_key)
    assert permissions.has_permission(1, action) is False


@pytest.mark.parametrize("action", _NEW_FOUNDER_ONLY_ACTIONS)
def test_founder_only_action_denied_for_unknown_user(monkeypatch, action):
    monkeypatch.setattr(permissions, "get_role", lambda user_id: None)
    assert permissions.has_permission(1, action) is False


# ----------------------------------------------------- has_any_permission --


def test_has_any_permission_true_if_one_of_several_actions_granted(monkeypatch):
    monkeypatch.setattr(permissions, "get_role", lambda user_id: "moliyachi")
    assert (
        permissions.has_any_permission(
            1, permissions.ACTION_VIEW_CASH_SUMMARY, permissions.ACTION_REVIEW_CASH_SHIFT
        )
        is True
    )


def test_has_any_permission_false_if_none_of_several_actions_granted(monkeypatch):
    monkeypatch.setattr(permissions, "get_role", lambda user_id: "sotuvchi")
    assert (
        permissions.has_any_permission(
            1, permissions.ACTION_VIEW_CASH_SUMMARY, permissions.ACTION_REVIEW_CASH_SHIFT
        )
        is False
    )


def test_has_any_permission_false_for_unknown_user(monkeypatch):
    monkeypatch.setattr(permissions, "get_role", lambda user_id: None)
    assert (
        permissions.has_any_permission(
            1, permissions.ACTION_VIEW_CASH_SUMMARY, permissions.ACTION_REVIEW_CASH_SHIFT
        )
        is False
    )


def test_has_any_permission_true_for_founder_even_without_table_entry(monkeypatch):
    monkeypatch.setattr(permissions, "get_role", lambda user_id: "founder")
    assert permissions.has_any_permission(1, permissions.ACTION_SET_SALARY) is True


# ----------------------------------------------------------- can_access_branch --


def test_can_access_branch_true_for_founder_any_branch(monkeypatch):
    monkeypatch.setattr(permissions, "get_role", lambda user_id: "founder")
    assert permissions.can_access_branch(1, "Chilonzor") is True
    assert permissions.can_access_branch(1, "Yunusobod") is True


@pytest.mark.parametrize("role_key", ["moliyachi", "nazoratchi"])
def test_can_access_branch_true_for_cross_branch_roles(monkeypatch, role_key):
    monkeypatch.setattr(permissions, "get_role", lambda user_id: role_key)
    assert permissions.can_access_branch(1, "Har qanday filial") is True


def test_can_access_branch_true_for_own_branch(monkeypatch):
    monkeypatch.setattr(permissions, "get_role", lambda user_id: "savdo_boshligi")
    monkeypatch.setattr(permissions, "get_profile", lambda user_id: {"branch": "Chilonzor"})
    assert permissions.can_access_branch(1, "Chilonzor") is True


def test_can_access_branch_false_for_other_branch(monkeypatch):
    monkeypatch.setattr(permissions, "get_role", lambda user_id: "savdo_boshligi")
    monkeypatch.setattr(permissions, "get_profile", lambda user_id: {"branch": "Chilonzor"})
    assert permissions.can_access_branch(1, "Yunusobod") is False


def test_can_access_branch_false_when_profile_has_no_branch(monkeypatch):
    monkeypatch.setattr(permissions, "get_role", lambda user_id: "savdo_boshligi")
    monkeypatch.setattr(permissions, "get_profile", lambda user_id: {"branch": None})
    assert permissions.can_access_branch(1, "Chilonzor") is False


def test_can_access_branch_false_for_unknown_user(monkeypatch):
    monkeypatch.setattr(permissions, "get_role", lambda user_id: None)
    assert permissions.can_access_branch(1, "Chilonzor") is False


# --------------------------------------------------------- ensure_permission --


def _bound_message(bot: RecordingBot, user_id: int, text: str) -> Message:
    return make_message(user_id, text=text).as_(bot)


async def test_ensure_permission_true_for_granted_message(monkeypatch):
    monkeypatch.setattr(permissions, "get_role", lambda user_id: "founder")
    bot = RecordingBot(token=os.environ["BOT_TOKEN"])
    message = _bound_message(bot, 1, "/setrule x 1")

    assert await permissions.ensure_permission(message, permissions.ACTION_SET_RULE) is True
    assert bot.sent == []


async def test_ensure_permission_message_denied_sends_fallback(monkeypatch):
    monkeypatch.setattr(permissions, "get_role", lambda user_id: "kassir")
    bot = RecordingBot(token=os.environ["BOT_TOKEN"])
    message = _bound_message(bot, 1, "/setrule x 1")

    assert await permissions.ensure_permission(message, permissions.ACTION_SET_RULE) is False
    assert len(bot.sent) == 1
    assert bot.sent[0].text in _DENIAL_TEXTS


async def test_ensure_permission_denied_when_message_has_no_user(monkeypatch):
    monkeypatch.setattr(permissions, "get_role", lambda user_id: "founder")
    message = Message(message_id=1, date=datetime.now(), chat=Chat(id=1, type="private"), text="hi")

    assert await permissions.ensure_permission(message, permissions.ACTION_SET_RULE) is False


def _make_bound_callback(bot: RecordingBot, user_id: int, data: str) -> CallbackQuery:
    target_message = Message(
        message_id=1, date=datetime.now(), chat=Chat(id=user_id, type="private"), text="card"
    )
    user = TgUser(id=user_id, is_bot=False, first_name="Test")
    return CallbackQuery(
        id="1", from_user=user, chat_instance="ci", data=data, message=target_message
    ).as_(bot)


async def test_ensure_permission_callback_denied_sends_toast(monkeypatch):
    monkeypatch.setattr(permissions, "get_role", lambda user_id: "kassir")
    bot = RecordingBot(token=os.environ["BOT_TOKEN"])
    callback = _make_bound_callback(bot, 1, "bos:decide:1:approved")

    result = await permissions.ensure_permission(callback, permissions.ACTION_DECIDE_APPEAL)

    assert result is False
    assert len(bot.sent) == 1
    assert isinstance(bot.sent[0], AnswerCallbackQuery)
    assert bot.sent[0].text in _DENIAL_TEXTS
    assert bot.sent[0].show_alert is not True


async def test_ensure_permission_callback_granted_sends_no_ack(monkeypatch):
    monkeypatch.setattr(permissions, "get_role", lambda user_id: "founder")
    bot = RecordingBot(token=os.environ["BOT_TOKEN"])
    callback = _make_bound_callback(bot, 1, "bos:decide:1:approved")

    result = await permissions.ensure_permission(callback, permissions.ACTION_DECIDE_APPEAL)

    assert result is True
    assert bot.sent == []


async def test_ensure_any_permission_true_if_one_of_two_granted(monkeypatch):
    monkeypatch.setattr(permissions, "get_role", lambda user_id: "moliyachi")
    bot = RecordingBot(token=os.environ["BOT_TOKEN"])
    message = _bound_message(bot, 1, "/cashsummary")

    result = await permissions.ensure_any_permission(
        message, permissions.ACTION_VIEW_CASH_SUMMARY, permissions.ACTION_OPEN_CASH_SHIFT
    )
    assert result is True
    assert bot.sent == []


async def test_ensure_any_permission_false_if_none_granted(monkeypatch):
    monkeypatch.setattr(permissions, "get_role", lambda user_id: "sotuvchi")
    bot = RecordingBot(token=os.environ["BOT_TOKEN"])
    message = _bound_message(bot, 1, "/cashsummary")

    result = await permissions.ensure_any_permission(
        message, permissions.ACTION_VIEW_CASH_SUMMARY, permissions.ACTION_OPEN_CASH_SHIFT
    )
    assert result is False
    assert len(bot.sent) == 1


# ---------------------------------------------------------------- audit log --


async def test_denied_privileged_action_is_audited(monkeypatch):
    monkeypatch.setattr(permissions, "get_role", lambda user_id: "kassir")
    bot = RecordingBot(token=os.environ["BOT_TOKEN"])
    message = _bound_message(bot, 777, "/setrule x 1")

    from repositories import audit as audit_repo
    from services import audit

    await permissions.ensure_permission(message, permissions.ACTION_SET_RULE)

    events = audit_repo.list_events_for_actor(777)
    assert any(e["event_type"] == audit.EVENT_UNAUTHORIZED_PRIVILEGED_ACTION for e in events)


async def test_denied_operational_action_is_not_audited(monkeypatch):
    """Oddiy amaliy (Founder-only bo'lmagan) amalga rad javobi audit
    hajmini shishirmasin — faqat Founder-only amalga urinish yoziladi.
    """
    monkeypatch.setattr(permissions, "get_role", lambda user_id: "sotuvchi")
    bot = RecordingBot(token=os.environ["BOT_TOKEN"])
    message = _bound_message(bot, 778, "/openshift")

    from repositories import audit as audit_repo
    from services import audit

    await permissions.ensure_permission(message, permissions.ACTION_OPEN_CASH_SHIFT)

    events = audit_repo.list_events_for_actor(778)
    assert not any(e["event_type"] == audit.EVENT_UNAUTHORIZED_PRIVILEGED_ACTION for e in events)


async def test_stranger_denial_is_not_audited(monkeypatch):
    monkeypatch.setattr(permissions, "get_role", lambda user_id: None)
    bot = RecordingBot(token=os.environ["BOT_TOKEN"])
    message = _bound_message(bot, 779, "/setrule x 1")

    from repositories import audit as audit_repo

    await permissions.ensure_permission(message, permissions.ACTION_SET_RULE)

    assert audit_repo.list_events_for_actor(779) == []


# ------------------------------------------------- uchidan-uchigacha regressiya --
# Ilgari to'g'ridan-to'g'ri ``id != FOUNDER_ID`` bilan tekshirilgan, endi
# ``services/permissions.py`` orqali markazlashtirilgan buyruqlar — kim
# nima qila olishi o'zgarmagan (Founder ishlaydi, boshqa rol/begona rad
# etiladi), faqat rad etish javobi endi jim emas.


async def test_removeuser_founder_only(bot_dp):
    main, bot = bot_dp
    _set_role(111, "kassir")
    _set_role(222, "sotuvchi")

    sent = await send(main.dp, bot, 111, text="/removeuser 222")
    _assert_denied(sent)

    sent = await send(main.dp, bot, 999999, text="/removeuser 222")
    _assert_denied(sent)

    sent = await send(main.dp, bot, FOUNDER_ID, text="/removeuser 222")
    assert "chirildi" in sent[0].text


async def test_profile_founder_only(bot_dp):
    main, bot = bot_dp
    _set_role(111, "nazoratchi")

    sent = await send(main.dp, bot, 111, text="/profile 111")
    _assert_denied(sent)

    sent = await send(main.dp, bot, 999999, text="/profile 111")
    _assert_denied(sent)

    sent = await send(main.dp, bot, FOUNDER_ID, text="/profile 111")
    assert "topilmadi" in sent[0].text


async def test_setsalary_founder_only(bot_dp):
    main, bot = bot_dp
    _set_role(111, "kassir")

    sent = await send(main.dp, bot, 111, text="/setsalary 111 3000000")
    _assert_denied(sent)

    sent = await send(main.dp, bot, 999999, text="/setsalary 111 3000000")
    _assert_denied(sent)

    sent = await send(main.dp, bot, FOUNDER_ID, text="/setsalary 111 3000000")
    assert "o'rnatildi" in sent[0].text


async def test_maosh_lookup_founder_only(bot_dp):
    main, bot = bot_dp
    _set_role(111, "kassir")

    sent = await send(main.dp, bot, 111, text="/maosh 111")
    _assert_denied(sent)

    sent = await send(main.dp, bot, 999999, text="/maosh 111")
    _assert_denied(sent)

    sent = await send(main.dp, bot, FOUNDER_ID, text="/maosh 111")
    assert "Fiks oylik" in sent[0].text


async def test_listrules_founder_only(bot_dp):
    main, bot = bot_dp
    _set_role(111, "kassir")

    sent = await send(main.dp, bot, 111, text="/listrules")
    _assert_denied(sent)

    sent = await send(main.dp, bot, 999999, text="/listrules")
    _assert_denied(sent)

    sent = await send(main.dp, bot, FOUNDER_ID, text="/listrules")
    assert sent != []


async def test_supplierlist_founder_only(bot_dp):
    main, bot = bot_dp
    _set_role(111, "kassir")

    sent = await send(main.dp, bot, 111, text="/supplierlist")
    _assert_denied(sent)

    sent = await send(main.dp, bot, 999999, text="/supplierlist")
    _assert_denied(sent)

    sent = await send(main.dp, bot, FOUNDER_ID, text="/supplierlist")
    assert sent != []


async def test_supplierscompare_founder_only(bot_dp):
    main, bot = bot_dp
    _set_role(111, "kassir")

    sent = await send(main.dp, bot, 111, text="/supplierscompare pomidor")
    _assert_denied(sent)

    sent = await send(main.dp, bot, 999999, text="/supplierscompare pomidor")
    _assert_denied(sent)

    sent = await send(main.dp, bot, FOUNDER_ID, text="/supplierscompare pomidor")
    assert sent != []


async def test_appeal_decision_denied_for_non_founder(bot_dp, monkeypatch):
    main, bot = bot_dp
    _set_role(1, "nazoratchi")
    _set_role(111, "kassir")

    from services import discipline

    discipline.add_rule(3, "Kechikish", "Ishga kechikish taqiqlanadi", created_by=FOUNDER_ID)

    async def fake_create(**kwargs):
        from types import SimpleNamespace

        return SimpleNamespace(output_text="✅ Mos keladi.")

    monkeypatch.setattr(main.openai_client.responses, "create", fake_create)

    await send_callback(main.dp, bot, 1, data="bos:pen:111:10", target_chat_id=1)
    await send(main.dp, bot, 1, text="3-nizom")
    assert discipline.get_salary(111)["bonus_bank"] == -10

    sent = await send(main.dp, bot, 111, text="/apellyatsiya")
    penalty_callback_data = sent[0].reply_markup.inline_keyboard[0][0].callback_data
    await send_callback(main.dp, bot, 111, data=penalty_callback_data, target_chat_id=111)
    await send(main.dp, bot, 111, text="Men kasal edim")

    # Nazoratchi (Founder emas) apellyatsiyani hal qilishga urinadi —
    # yakuniy qaror doim Founderga tegishli, shu sababli rad etilishi
    # va jarima o'zgarishsiz qolishi kerak.
    approve_data = f"bos:decide:{penalty_callback_data.split(':')[2]}:{discipline.DECISION_APPROVED}"
    await send_callback(main.dp, bot, 1, data=approve_data, target_chat_id=1)

    assert discipline.get_salary(111)["bonus_bank"] == -10


async def test_moliyachi_can_view_other_employee_cash_summary(bot_dp):
    main, bot = bot_dp
    _set_role(1, "moliyachi")
    _set_role(111, "kassir")

    sent = await send(main.dp, bot, 1, text="/cashsummary 111")
    assert "smena topilmadi" in sent[0].text


async def test_sotuvchi_cannot_view_other_employee_cash_summary(bot_dp):
    main, bot = bot_dp
    _set_role(1, "sotuvchi")
    _set_role(111, "kassir")

    sent = await send(main.dp, bot, 1, text="/cashsummary 111")
    _assert_denied(sent)


# --------------------------------------------------------- filial chegarasi --


async def test_savdo_boshligi_cannot_request_explicit_branch_at_all(bot_dp):
    """savdo_boshligi'da ``ACTION_VIEW_INVENTORY_SUMMARY``/
    ``ACTION_REVIEW_INVENTORY_VARIANCE`` yo'q — filial argumenti bilan
    chaqirish amal darajasidayoq (can_access_branch'gacha yetmasdan) rad
    etiladi.
    """
    main, bot = bot_dp
    _set_role(111, "savdo_boshligi")

    sent = await send(main.dp, bot, 111, text="/inventorysummary BoshqaFilial")
    _assert_denied(sent)


async def test_action_granted_role_without_cross_branch_flag_is_still_branch_scoped(bot_dp, monkeypatch):
    """Himoya chuqurligi: amal ruxsati (``has_permission``) va filial
    ma'lumot chegarasi (``can_access_branch``) mustaqil — hatto
    kelajakda biror rolga ``ACTION_VIEW_INVENTORY_SUMMARY`` berilib,
    ``_CROSS_BRANCH_ROLES``ga qo'shilmay qolsa ham, boshqa filialni
    ko'ra olmasligi va bu urinish audit qilinishi kerak.
    """
    main, bot = bot_dp
    _set_role(111, "kassir")

    monkeypatch.setitem(
        permissions.ROLE_PERMISSIONS,
        "kassir",
        permissions.ROLE_PERMISSIONS["kassir"] | {permissions.ACTION_VIEW_INVENTORY_SUMMARY},
    )

    sent = await send(main.dp, bot, 111, text="/inventorysummary BoshqaFilial")
    _assert_denied(sent)

    from repositories import audit as audit_repo
    from services import audit

    events = audit_repo.list_events_for_actor(111)
    assert any(e["event_type"] == audit.EVENT_CROSS_BRANCH_ATTEMPT for e in events)


async def test_moliyachi_can_view_any_branch_inventory_summary(bot_dp):
    main, bot = bot_dp
    _set_role(1, "moliyachi")

    sent = await send(main.dp, bot, 1, text="/inventorysummary BoshqaFilial")
    assert "hisoboti topilmadi" in sent[0].text
