"""Oylik kelishuvi: matn bilan kiritish, Founder tasdig'i, xodim roziligi, versiyalar, maxfiylik. Telegram mock, vaqtincha DB."""

import pytest

import db
import employees
from config import FOUNDER_ID, RECRUITING_BRANCH_NAMES
from roles import set_role
from services import salary_agreement as sa
from services import salary_agreement_text as sat
from tests.bot_harness import send, send_callback

pytestmark = pytest.mark.anyio

EMP, EMP2, OTHER, MGR = 891001, 891002, 891003, 891004
B1, B2 = RECRUITING_BRANCH_NAMES[0], RECRUITING_BRANCH_NAMES[1]
SAMPLE = (
    f"Ali Valiyev — {B1}\nTarif: 3\nFiks: 1.800.000 so'm\nOyiga: 28 ish kuni\nKuniga: 11 soat\n"
    "Kelishuv boshlanishi: 01.10.2026\nNatija bonusi: oyiga 700.000 so'mgacha"
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _employee(user_id, surname="Valiyev", ism="Ali", branch=B1, role="kassir"):
    set_role(user_id, role, set_by=FOUNDER_ID)
    employees.submit_profile(user_id, {"familiya": surname, "ism": ism, "branch": branch, "role_key": role, "contacts": []})
    employees.approve_profile(user_id, approved_by=FOUNDER_ID)


def _text(sent):
    return "\n".join(getattr(m, "text", "") or "" for m in sent)


def _buttons(sent):
    return [b.callback_data for m in sent if getattr(m, "reply_markup", None) is not None and hasattr(m.reply_markup, "inline_keyboard")
            for row in m.reply_markup.inline_keyboard for b in row]


def _rows(table="salary_agreements"):
    conn = db.get_connection()
    try:
        return [dict(r) for r in conn.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()]
    finally:
        conn.close()


async def _cb(main, bot, data, user=FOUNDER_ID):
    return await send_callback(main.dp, bot, user, data=data, target_chat_id=user)


async def _to_card(main, bot, text=SAMPLE):
    await send(main.dp, bot, FOUNDER_ID, text="/kelishuv")
    return await send(main.dp, bot, FOUNDER_ID, text=text)


def _save_btn(sent):
    return next(d for d in _buttons(sent) if d.startswith("sagr:save:"))


def _to_employee(bot):
    return [m for m in bot.sent if getattr(m, "chat_id", None) == EMP]


# ---------------------------------------------------------------- parser --


@pytest.mark.parametrize("text,value", [("1.800.000", 1_800_000), ("1 800 000", 1_800_000), ("1800000", 1_800_000), ("1,8 mln", 1_800_000), ("700 ming", 700_000)])
def test_amount_spellings_are_equal(text, value):
    assert sat.parse_amount(text) == value


def test_bare_small_number_is_ambiguous_not_guessed():
    with pytest.raises(sat.Ambiguous):
        sat.parse_amount("700")


def test_sample_parses_fully_and_line_order_does_not_matter():
    first = sat.parse_text(SAMPLE)
    assert not first.problems
    shuffled = "\n".join(reversed(SAMPLE.split("\n")))
    second = sat.parse_text(shuffled)
    for key in ("tariff", "fixed_salary", "work_days", "daily_minutes", "effective_from", "result_bonus_cap"):
        assert first.values[key] == second.values[key]
    assert first.values["daily_minutes"] == 660 and first.values["work_days"] == 28
    assert sat.parse_text("Fiks: 1,8 mln; 28 kun, 11 soat").values["fixed_salary"] == 1_800_000


def test_ambiguous_amount_in_text_becomes_question_not_value():
    result = sat.parse_text("Fiks: 700")
    assert "fixed_salary" not in result.values and "fixed_salary" in result.problems


# ------------------------------------------------------------------ oqim --


async def test_full_flow_saves_only_after_confirm_and_sends_to_employee(bot_dp):
    main, bot = bot_dp
    _employee(EMP)
    card = await _to_card(main, bot)
    assert "Tekshiring".lower() in _text(card).lower() and "1 800 000" in _text(card)
    assert _rows() == [] and _to_employee(bot) == []
    saved = await _cb(main, bot, _save_btn(card))
    rows = _rows()
    assert len(rows) == 1 and rows[0]["fixed_salary"] == 1_800_000 and rows[0]["tariff"] == 3
    assert rows[0]["work_days"] == 28 and rows[0]["daily_minutes"] == 660 and rows[0]["result_bonus_cap"] == 700_000
    assert "Xodim tasdig'i kutilmoqda" in _text(saved)
    sent_to_emp = [m for m in saved if getattr(m, "chat_id", None) == EMP]
    assert sent_to_emp and f"sagr:ok:{rows[0]['id']}" in _buttons(sent_to_emp)
    assert _rows("salary_agreement_consents")[0]["delivery_status"] == "sent"
    assert _rows("salary_agreement_consents")[0]["consented_at"] is None
    # hire date unchanged: employees jadvali tegilmagan
    assert employees.get_profile(EMP)["status"] == "approved"


async def test_repeat_save_and_old_card_create_nothing(bot_dp):
    main, bot = bot_dp
    _employee(EMP)
    card = await _to_card(main, bot)
    token = _save_btn(card)
    await _cb(main, bot, token)
    await _cb(main, bot, token)
    assert len(_rows()) == 1 and len(_rows("salary_agreement_consents")) == 1


async def test_edit_invalidates_old_save_and_cancel_saves_nothing(bot_dp):
    main, bot = bot_dp
    _employee(EMP)
    card = await _to_card(main, bot)
    old = _save_btn(card)
    await _cb(main, bot, "sagr:edit")
    await _cb(main, bot, old)
    assert _rows() == []
    new_card = await send(main.dp, bot, FOUNDER_ID, text="Fiks: 2.000.000")
    assert "2 000 000" in _text(new_card)
    await _cb(main, bot, "sagr:cancel")
    await _cb(main, bot, _save_btn(new_card))
    assert _rows() == [] and _to_employee(bot) == []


async def test_missing_parts_are_asked_and_clear_data_not_reasked(bot_dp):
    main, bot = bot_dp
    _employee(EMP)
    sent = await _to_card(main, bot, f"Ali Valiyev — {B1}\nTarif: 3\nFiks: 1,8 mln\nOyiga: 28 kun\nKuniga: 11 soat")
    assert "sanadan boshlanadi" in _text(sent)
    sent = await _cb(main, bot, "sagr:today")
    assert "natija bonusi" in _text(sent).lower()
    sent = await send(main.dp, bot, FOUNDER_ID, text="700")
    assert "Aniq yozing" in _text(sent)
    sent = await send(main.dp, bot, FOUNDER_ID, text="700 ming")
    assert "700 000" in _text(sent) and _save_btn(sent)


async def test_namesake_and_branch_mismatch_ask_to_choose_and_unknown_not_created(bot_dp):
    main, bot = bot_dp
    _employee(EMP, branch=B1)
    _employee(EMP2, branch=B2)
    sent = await _to_card(main, bot, SAMPLE.replace(f"— {B1}", ""))
    assert f"sagr:pick:{EMP}" in _buttons(sent) and f"sagr:pick:{EMP2}" in _buttons(sent)
    sent = await _cb(main, bot, f"sagr:pick:{EMP2}")
    assert B2 in _text(sent) and _save_btn(sent)

    sent = await _to_card(main, bot, SAMPLE.replace(B1, B2).replace("Ali Valiyev", "Sodiq Nomalum"))
    assert "topilmadi" in _text(sent) and employees.get_profile(0) is None
    assert _rows() == []

    only = 891010
    _employee(only, surname="Yagonov", ism="Vali", branch=B1)
    sent = await _to_card(main, bot, SAMPLE.replace("Ali Valiyev", "Vali Yagonov").replace(B1, B2))
    assert f"sagr:pick:{only}" in _buttons(sent)  # filial mos kelmadi — tanlash so'raladi


async def test_only_founder_can_start_or_save(bot_dp):
    main, bot = bot_dp
    _employee(EMP)
    sent = await send(main.dp, bot, EMP, text="/kelishuv")
    assert "Namuna" not in _text(sent) and "Fiks:" not in _text(sent)
    card = await _to_card(main, bot)
    await _cb(main, bot, _save_btn(card), user=EMP)
    assert _rows() == []


# --------------------------------------------------------------- rozilik --


async def _saved(main, bot, text=SAMPLE):
    card = await _to_card(main, bot, text)
    await _cb(main, bot, _save_btn(card))
    return _rows()[-1]["id"]


async def test_only_owner_consents_once_and_exact_version(bot_dp):
    main, bot = bot_dp
    _employee(EMP)
    _employee(OTHER, surname="Boshqa", ism="Bek")
    first = await _saved(main, bot)
    await _cb(main, bot, f"sagr:ok:{first}", user=OTHER)
    assert _rows("salary_agreement_consents")[0]["consented_at"] is None
    await _cb(main, bot, f"sagr:ok:{first}", user=EMP)
    await _cb(main, bot, f"sagr:ok:{first}", user=EMP)
    consent = _rows("salary_agreement_consents")
    assert len(consent) == 1 and consent[0]["consented_by"] == EMP and consent[0]["consented_at"]
    second = await _saved(main, bot, SAMPLE.replace("1.800.000", "2.000.000"))
    assert sa.consent_status_text(sa.get_agreement(first)).startswith("✅")
    rows = {r["agreement_id"]: r for r in _rows("salary_agreement_consents")}
    assert rows[second]["consented_at"] is None  # eski rozilik ko'chmaydi
    assert len(_rows()) == 2  # tarix saqlangan
    await _cb(main, bot, f"sagr:ok:{first}", user=EMP)  # eski versiya tugmasi yangisini tasdiqlamaydi
    assert {r["agreement_id"]: r for r in _rows("salary_agreement_consents")}[second]["consented_at"] is None
    await _cb(main, bot, f"sagr:ok:{second}", user=EMP)
    assert {r["agreement_id"]: r for r in _rows("salary_agreement_consents")}[second]["consented_by"] == EMP


async def test_old_pending_version_cannot_be_confirmed_after_new_version(bot_dp):
    main, bot = bot_dp
    _employee(EMP)
    first = await _saved(main, bot)
    await _saved(main, bot, SAMPLE.replace("1.800.000", "2.000.000"))
    assert sa.record_consent(first, EMP) == sa.CONSENT_SUPERSEDED


async def test_delivery_failure_is_reported_exactly_and_employee_can_still_confirm(bot_dp, monkeypatch):
    main, bot = bot_dp
    _employee(EMP)
    original = bot.send_message

    async def failing(chat_id, *args, **kwargs):
        if chat_id == EMP:
            raise RuntimeError("blocked")
        return await original(chat_id, *args, **kwargs)

    monkeypatch.setattr(bot, "send_message", failing)
    card = await _to_card(main, bot)
    saved = await _cb(main, bot, _save_btn(card))
    text = _text(saved)
    assert "YUBORIB BO'LMADI" in text and "yuborildi." not in text and "rozilik olindi" not in text.lower()
    row = _rows("salary_agreement_consents")[0]
    assert row["delivery_status"] == "failed"
    agreement_id = row["agreement_id"]
    mine = await send(main.dp, bot, EMP, text="/mykelishuv")
    assert f"sagr:ok:{agreement_id}" in _buttons(mine) and "1 800 000" in _text(mine)
    await _cb(main, bot, f"sagr:ok:{agreement_id}", user=EMP)
    assert _rows("salary_agreement_consents")[0]["consented_by"] == EMP


async def test_consent_does_not_change_salary_and_legacy_has_no_auto_consent(bot_dp):
    main, bot = bot_dp
    _employee(EMP)
    sa.save_legacy_fixed_salary(EMP, 3_000_000, FOUNDER_ID)
    assert _rows("salary_agreement_consents") == []
    assert "Rozilik talab qilinmagan" in sa.consent_status_text(sa.get_current(EMP))
    from services import discipline

    before = discipline.get_salary(EMP)["fixed_salary"]
    import company_time

    today = company_time.today().strftime("%d.%m.%Y")  # eski kelishuv bugungi sanali — teng sanada oxirgisi amal qiladi
    await _saved(main, bot, SAMPLE.replace("01.10.2026", today))
    assert discipline.get_salary(EMP)["fixed_salary"] == 1_800_000 != before


# ---------------------------------------------------------------- maxfiylik --


async def test_privacy_other_employee_manager_and_group(bot_dp):
    main, bot = bot_dp
    _employee(EMP)
    _employee(OTHER, surname="Boshqa", ism="Bek")
    _employee(MGR, surname="Rahbar", ism="Ravshan", branch=B2, role="nazoratchi")
    await _saved(main, bot)
    other_view = await send(main.dp, bot, OTHER, text="/mykelishuv")
    assert "1 800 000" not in _text(other_view)
    # vakolati yo'q rahbar (ACTION_LOOKUP_ANY_SALARY yo'q) va boshqa filial: ko'ra olmaydi
    assert sa.can_view(MGR, EMP, B1) is False and sa.can_view(OTHER, EMP, B1) is False
    assert sa.can_view(EMP, EMP, B1) is True and sa.can_view(FOUNDER_ID, EMP, B1) is True
    group = await send(main.dp, bot, EMP, text="/mykelishuv", chat_id=-1001, chat_type="supergroup")
    assert "1 800 000" not in _text(group)
    assert all((getattr(m, "chat_id", 1) or 1) > 0 or "1 800 000" not in (getattr(m, "text", "") or "") for m in bot.sent)


async def test_existing_flows_still_work(bot_dp):
    main, bot = bot_dp
    _employee(EMP)
    sent = await send(main.dp, bot, FOUNDER_ID, text="/setsalary")
    assert "filial" in _text(sent).lower() or _buttons(sent)
    sent = await send(main.dp, bot, EMP, text="/mymaosh")
    assert "Fiks oylik" in _text(sent)


def test_additive_migration_is_safe_to_rerun(temp_db):
    db.init_db()
    db.init_db()
    conn = db.get_connection()
    try:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(salary_agreements)").fetchall()}
    finally:
        conn.close()
    assert {"tariff", "result_bonus_cap"} <= cols


# ------------------------------------------------ "Tushunmadim" + rahbar --

MGR1, MGR2 = 891011, 891012


def _managers():
    _employee(MGR1, surname="Rahbarov", ism="Bek", branch=B1, role="savdo_boshligi")
    _employee(MGR2, surname="Boshqaev", ism="Sher", branch=B2, role="savdo_boshligi")


def _to(bot, chat):
    return [m for m in bot.sent if getattr(m, "chat_id", None) == chat]


def _issues():
    return _rows("salary_agreement_issues")


async def test_employee_message_has_both_buttons(bot_dp):
    main, bot = bot_dp
    _employee(EMP)
    agreement_id = await _saved(main, bot)
    assert {f"sagr:ok:{agreement_id}", f"sagr:no:{agreement_id}"} <= set(_buttons(_to(bot, EMP)))
    texts = [b.text for m in _to(bot, EMP) for row in m.reply_markup.inline_keyboard for b in row]
    assert texts == ["✅ Roziman", "❓ Tushunmadim"]


async def test_not_understood_opens_one_issue_and_notifies_founder_and_own_branch_manager(bot_dp):
    main, bot = bot_dp
    _employee(EMP)
    _managers()
    agreement_id = await _saved(main, bot)
    await _cb(main, bot, f"sagr:no:{agreement_id}", user=EMP)
    issues = _issues()
    assert len(issues) == 1 and issues[0]["agreement_id"] == agreement_id and issues[0]["status"] == "open"
    assert issues[0]["branch"] == B1 and issues[0]["notified_count"] == 2
    import company_time

    assert issues[0]["due_date"] == company_time.today().isoformat()
    for chat in (FOUNDER_ID, MGR1):
        got = _text(_to(bot, chat))
        assert "tushunmadi" in got and "filial rahbari" in got and "1 800 000" not in got
    assert _to(bot, MGR2) == []
    assert _rows("salary_agreement_consents")[0]["consented_at"] is None
    before = len(bot.sent)
    await _cb(main, bot, f"sagr:no:{agreement_id}", user=EMP)  # takroriy
    assert len(_issues()) == 1 and len([m for m in bot.sent[before:] if getattr(m, "chat_id", None) in (FOUNDER_ID, MGR1)]) == 0


async def test_not_understood_rejects_stranger_old_and_consented(bot_dp):
    main, bot = bot_dp
    _employee(EMP)
    _employee(OTHER, surname="Boshqa", ism="Bek")
    first = await _saved(main, bot)
    await _cb(main, bot, f"sagr:no:{first}", user=OTHER)
    assert _issues() == []
    second = await _saved(main, bot, SAMPLE.replace("1.800.000", "2.000.000"))
    await _cb(main, bot, f"sagr:no:{first}", user=EMP)  # eski versiya
    assert _issues() == []
    await _cb(main, bot, f"sagr:ok:{second}", user=EMP)
    await _cb(main, bot, f"sagr:no:{second}", user=EMP)  # rozilikdan keyin
    assert _issues() == []


async def test_each_version_has_its_own_issue_and_resolution_does_not_consent(bot_dp):
    main, bot = bot_dp
    _employee(EMP)
    _managers()
    first = await _saved(main, bot)
    await _cb(main, bot, f"sagr:no:{first}", user=EMP)
    issue_id = _issues()[0]["id"]
    await _cb(main, bot, f"sagr:res:{issue_id}:explained", user=MGR1)
    issue = _issues()[0]
    assert issue["status"] == "resolved" and issue["outcome"] == "explained" and issue["resolved_by"] == MGR1
    assert _rows("salary_agreement_consents")[0]["consented_at"] is None  # hal qilindi != rozilik
    await _cb(main, bot, f"sagr:res:{issue_id}:disagreed", user=FOUNDER_ID)  # takroriy
    assert _issues()[0]["outcome"] == "explained"
    second = await _saved(main, bot, SAMPLE.replace("1.800.000", "2.000.000"))
    await _cb(main, bot, f"sagr:no:{second}", user=EMP)
    assert len(_issues()) == 2 and _issues()[1]["status"] == "open" and _issues()[0]["status"] == "resolved"


async def test_only_founder_or_own_branch_manager_can_resolve(bot_dp):
    main, bot = bot_dp
    _employee(EMP)
    _managers()
    agreement_id = await _saved(main, bot)
    await _cb(main, bot, f"sagr:no:{agreement_id}", user=EMP)
    issue_id = _issues()[0]["id"]
    for user in (EMP, MGR2):
        await _cb(main, bot, f"sagr:res:{issue_id}:explained", user=user)
        assert _issues()[0]["status"] == "open"
    assert sa.record_consent(agreement_id, MGR1) == sa.CONSENT_NOT_OWNER  # rahbar xodim o'rniga rozilik bera olmaydi
    await _cb(main, bot, f"sagr:ok:{agreement_id}", user=MGR1)
    assert _rows("salary_agreement_consents")[0]["consented_at"] is None
    await _cb(main, bot, f"sagr:res:{issue_id}:new_agreement", user=FOUNDER_ID)
    assert _issues()[0]["outcome"] == "new_agreement"


async def test_issue_delivery_failure_is_reported_to_employee(bot_dp, monkeypatch):
    main, bot = bot_dp
    _employee(EMP)
    agreement_id = await _saved(main, bot)
    original = bot.send_message

    async def failing(chat_id, *args, **kwargs):
        if chat_id == FOUNDER_ID:
            raise RuntimeError("blocked")
        return await original(chat_id, *args, **kwargs)

    monkeypatch.setattr(bot, "send_message", failing)
    sent = await _cb(main, bot, f"sagr:no:{agreement_id}", user=EMP)
    assert _issues()[0]["notified_count"] == 0 and _issues()[0]["status"] == "open"
    assert "yetkazib bo'lmadi" in _text(sent) and "rahbarga yuborildi" not in _text(sent)


async def test_view_permissions_own_branch_manager_yes_other_branch_no(bot_dp):
    main, bot = bot_dp
    _employee(EMP)
    _managers()
    _employee(OTHER, surname="Boshqa", ism="Bek")
    agreement_id = await _saved(main, bot)
    assert sa.can_view(MGR1, EMP, B1) and not sa.can_view(MGR2, EMP, B1) and not sa.can_view(OTHER, EMP, B1)
    ok = await _cb(main, bot, f"sagr:view:{agreement_id}", user=MGR1)
    assert "1 800 000" in _text(ok)
    for user in (MGR2, OTHER):
        denied = await _cb(main, bot, f"sagr:view:{agreement_id}", user=user)
        assert "1 800 000" not in _text(denied)
    listing = await send(main.dp, bot, MGR1, text="/filialkelishuv")
    assert f"sagr:view:{agreement_id}" in _buttons(listing)
    empty = await send(main.dp, bot, MGR2, text="/filialkelishuv")
    assert f"sagr:view:{agreement_id}" not in _buttons(empty)
    from services import permissions

    assert not permissions.has_permission(MGR1, permissions.ACTION_LOOKUP_ANY_SALARY)  # barcha oyliklar kengaytirilmagan


async def test_end_of_day_reminder_once_via_existing_scheduler_and_today_problems(bot_dp):
    from datetime import datetime

    import company_time
    import salary_agreement_bot
    from services import founder_today_problems

    main, bot = bot_dp
    _employee(EMP)
    agreement_id = await _saved(main, bot)
    await _cb(main, bot, f"sagr:no:{agreement_id}", user=EMP)
    assert founder_today_problems.build_today_problems_summary()["agreement_questions"]["total"] == 1
    sent = await send(main.dp, bot, FOUNDER_ID, text="🚨 Bugungi muammolar")
    assert "ochiq savollar" in _text(sent) and "1 800 000" not in _text(sent)
    tz = company_time.resolve_timezone()
    day = company_time.today()
    bot.sent = []
    assert await salary_agreement_bot.remind_open_issues(bot, datetime(day.year, day.month, day.day, 15, 0, tzinfo=tz)) == 0
    assert await salary_agreement_bot.remind_open_issues(bot, datetime(day.year, day.month, day.day, 21, 30, tzinfo=tz)) == 1
    assert await salary_agreement_bot.remind_open_issues(bot, datetime(day.year, day.month, day.day, 22, 0, tzinfo=tz)) == 0
    assert len(_to(bot, FOUNDER_ID)) == 1 and "1 800 000" not in _text(_to(bot, FOUNDER_ID))
    from discipline_bot import start_scheduler  # job mavjud scheduler'ga ulanganini tekshirish uchun manba matni

    import inspect

    assert "salary_agreement_issue_reminder" in inspect.getsource(start_scheduler)


# ------------------------------------------- addel_boshligi / amaldagi + kelajak --

ADDEL = 891013


def _future(days=30):
    from datetime import timedelta

    import company_time

    return (company_time.today() + timedelta(days=days)).strftime("%d.%m.%Y")


async def test_addel_boshligi_is_denied_and_not_notified_savdo_boshligi_own_branch_only(bot_dp):
    from services import permissions

    main, bot = bot_dp
    _employee(EMP)
    _managers()
    _employee(ADDEL, surname="Addelov", ism="Ravshan", branch=B1, role="addel_boshligi")
    assert not permissions.has_permission(ADDEL, permissions.ACTION_VIEW_BRANCH_AGREEMENT)
    assert permissions.has_permission(MGR1, permissions.ACTION_VIEW_BRANCH_AGREEMENT)
    assert sa.can_view(MGR1, EMP, B1) and not sa.can_view(MGR2, EMP, B1) and not sa.can_view(ADDEL, EMP, B1)
    assert sa.can_view(FOUNDER_ID, EMP, B1)
    assert sa.branch_managers(B1) == [MGR1] and sa.branch_managers(B2) == [MGR2]
    agreement_id = await _saved(main, bot)
    denied = await _cb(main, bot, f"sagr:view:{agreement_id}", user=ADDEL)
    assert "1 800 000" not in _text(denied)
    await _cb(main, bot, f"sagr:no:{agreement_id}", user=EMP)
    assert _to(bot, ADDEL) == [] and _to(bot, MGR2) == [] and _to(bot, MGR1) and _to(bot, FOUNDER_ID)
    await _cb(main, bot, f"sagr:res:{_issues()[0]['id']}:explained", user=ADDEL)
    assert _issues()[0]["status"] == "open"
    listing = await send(main.dp, bot, ADDEL, text="/filialkelishuv")
    assert not _buttons(listing)


async def test_mykelishuv_current_and_future_cards_bind_buttons_to_their_own_version(bot_dp):
    main, bot = bot_dp
    _employee(EMP)
    today = __import__("company_time").today().strftime("%d.%m.%Y")
    current_id = await _saved(main, bot, SAMPLE.replace("01.10.2026", today))
    future_id = await _saved(main, bot, SAMPLE.replace("01.10.2026", _future()).replace("1.800.000", "2.500.000"))
    cards = await send(main.dp, bot, EMP, text="/mykelishuv")
    assert len(cards) == 2
    now_card, next_card = cards
    assert "Amaldagi kelishuv" in now_card.text and "1 800 000" in now_card.text and "2 500 000" not in now_card.text
    assert "Kelajakdagi kelishuv" in next_card.text and "2 500 000" in next_card.text and _future() in next_card.text
    assert "1 800 000" not in next_card.text
    assert _buttons([now_card]) == [f"sagr:ok:{current_id}", f"sagr:no:{current_id}"]
    assert _buttons([next_card]) == [f"sagr:ok:{future_id}", f"sagr:no:{future_id}"]

    await _cb(main, bot, f"sagr:ok:{current_id}", user=EMP)
    consent = {r["agreement_id"]: r for r in _rows("salary_agreement_consents")}
    assert consent[current_id]["consented_at"] and consent[future_id]["consented_at"] is None
    await _cb(main, bot, f"sagr:ok:{current_id}", user=EMP)  # takroriy
    await _cb(main, bot, f"sagr:no:{future_id}", user=EMP)
    issues = _issues()
    assert len(issues) == 1 and issues[0]["agreement_id"] == future_id
    again = await send(main.dp, bot, EMP, text="/mykelishuv")
    assert _buttons([again[0]]) == [] and _buttons([again[1]]) == [f"sagr:ok:{future_id}"]
    await _cb(main, bot, f"sagr:ok:{future_id}", user=EMP)
    assert all(r["consented_at"] for r in _rows("salary_agreement_consents"))


async def test_replaced_versions_buttons_are_rejected(bot_dp):
    main, bot = bot_dp
    _employee(EMP)
    first = await _saved(main, bot)
    future_old = await _saved(main, bot, SAMPLE.replace("01.10.2026", _future()))
    future_new = await _saved(main, bot, SAMPLE.replace("01.10.2026", _future()).replace("1.800.000", "2.700.000"))
    await _cb(main, bot, f"sagr:ok:{future_old}", user=EMP)  # shu sanadagi yangiroq versiya o'rnini olgan
    await _cb(main, bot, f"sagr:no:{future_old}", user=EMP)
    consent = {r["agreement_id"]: r for r in _rows("salary_agreement_consents")}
    assert consent[future_old]["consented_at"] is None and _issues() == []
    cards = await send(main.dp, bot, EMP, text="/mykelishuv")
    assert [_buttons([c])[0] for c in cards] == [f"sagr:ok:{first}", f"sagr:ok:{future_new}"]
