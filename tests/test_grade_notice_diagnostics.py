"""Real dispatcher, isolated synthetic DB, Telegram mocked; no production calls."""
import logging
from datetime import timedelta

import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError
from aiogram.methods import AnswerCallbackQuery, SendMessage

import company_time
import employees
from db import get_connection
from services import discipline
from tests.bot_harness import send_callback
from tests.test_discipline_bot_flows import (
    EMPLOYEE, NAZORATCHI, _answers, _bos, _count, _notices, _nzr, _setup,
)

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _events(capsys):
    return [dict(field.split("=", 1) for field in line.split()[1:])
            for line in capsys.readouterr().out.splitlines() if line.startswith("GRADE_DIAGNOSTIC ")]


def _sessions():
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT status FROM nazoratchi_branch_sessions WHERE supervisor_id = ? AND branch = ? AND session_date = ?",
            (NAZORATCHI, employees.get_profile(EMPLOYEE)["branch"], company_time.today().isoformat()),
        ).fetchall()
    finally:
        conn.close()


@pytest.mark.parametrize("entry", [_bos, _nzr])
@pytest.mark.parametrize("grade", [discipline.GRADE_ALO, discipline.GRADE_BAJARILMAGAN])
async def test_first_grade_sends_without_time_bonus_and_diagnoses_acceptance(bot_dp, capsys, entry, grade):
    main, bot = bot_dp
    _setup()
    assert _sessions() == []  # Proves _setup did not open this supervisor/branch/day session.
    assert discipline.get_daily_grade(EMPLOYEE, company_time.today().isoformat()) is None
    sent = await entry(main, bot, grade)
    events = _events(capsys)
    assert len(_notices(sent)) == 1  # A first zero grade is still a new grade.
    assert any(e["stage"] == "save" and e["outcome"] == "new" for e in events)
    assert [e["outcome"] for e in events if e["stage"] == "notice"] == [
        "started", "telegram_attempt", "telegram_accepted"]
    assert len({e["evaluation_ref"] for e in events}) == 1
    assert _count("time_bonus_grants") == 0
    assert len(_sessions()) == 1 and _sessions()[0]["status"] == "open"
    assert discipline.get_daily_grade(EMPLOYEE, company_time.today().isoformat())["grade_key"] == grade


@pytest.mark.parametrize("entry", [_bos, _nzr])
async def test_repeat_and_correction_have_distinct_diagnostics(bot_dp, capsys, entry):
    main, bot = bot_dp
    _setup()
    await entry(main, bot, discipline.GRADE_ALO)
    _events(capsys)
    repeated = await entry(main, bot, discipline.GRADE_ALO)
    events = _events(capsys)
    assert not _notices(repeated)
    assert any(e["stage"] == "save" and e["outcome"] == "unchanged" for e in events)
    assert [e["outcome"] for e in events if e["stage"] == "notice"] == ["skipped_unchanged"]
    corrected = await entry(main, bot, discipline.GRADE_NORMA)
    events = _events(capsys)
    assert len(_notices(corrected)) == 1
    assert any(e["stage"] == "save" and e["outcome"] == "correction" for e in events)
    assert events[-1]["outcome"] == "telegram_accepted"
    assert _count("daily_evaluation_history") == 2


@pytest.mark.parametrize("entry", [_bos, _nzr])
@pytest.mark.parametrize("error_type,outcome", [
    (TelegramNetworkError, "failed"), (TelegramForbiddenError, "not_linked"),
    (TelegramBadRequest, "failed"),
])
async def test_failed_send_and_repeat_expose_existing_no_redelivery_limit(
    bot_dp, capsys, caplog, monkeypatch, entry, error_type, outcome,
):
    main, bot = bot_dp
    _setup()
    real_call = type(bot).__call__

    async def fail(self, method, request_timeout=None):
        if isinstance(method, SendMessage) and method.chat_id == EMPLOYEE:
            raise error_type(method=method, message="PRIVATE_MESSAGE_AND_TOKEN_MUST_NOT_LEAK")
        return await real_call(self, method, request_timeout)

    monkeypatch.setattr(type(bot), "__call__", fail)
    await entry(main, bot, discipline.GRADE_ALO)
    events = _events(capsys)
    assert events[-1]["outcome"] == outcome
    assert events[-1]["error_type"] == error_type.__name__
    assert len([e for e in events if e["error_type"] != "none"]) == 1
    assert not any(e["stage"] == "handler_after_save" for e in events)
    assert not any("grade_notice:" in r.message for r in caplog.records)
    assert "PRIVATE_MESSAGE" not in str(events)
    assert _count("daily_evaluations") == _count("daily_evaluation_history") == 1
    # Diagnostics only: a saved grade is still NOT redelivered by repeating it.
    repeated = await entry(main, bot, discipline.GRADE_ALO)
    assert "Bu baho allaqachon saqlangan." in _answers(repeated)
    assert _events(capsys)[-1]["outcome"] == "skipped_unchanged"


@pytest.mark.parametrize("entry,prefix,stage", [(_bos, "bos:grade", "bos_guard"), (_nzr, "nzr_grade", "nzr_guard")])
async def test_stale_day_guard_is_not_mistaken_for_saved_grade(bot_dp, capsys, entry, prefix, stage):
    main, bot = bot_dp
    _setup()
    old_day = (company_time.today() - timedelta(days=10)).strftime("%Y%m%d")
    sent = await send_callback(main.dp, bot, NAZORATCHI,
                               f"{prefix}:{EMPLOYEE}:alo:{old_day}", NAZORATCHI)
    events = _events(capsys)
    assert events[-1]["stage"] == stage
    assert events[-1]["outcome"] in ("inactive_day", "stale_day")
    assert not any(e["stage"] == "save" for e in events)
    assert not _notices(sent) and _count("daily_evaluations") == 0


def test_diagnostics_visible_with_warning_log_level_and_no_identifying_content(capsys, monkeypatch):
    monkeypatch.setattr(logging.getLogger(), "level", logging.WARNING)
    discipline.log_grade_event(7952886089, "bad\nPRIVATE", "notice", "failed", "TelegramNetworkError")
    output = capsys.readouterr().out
    assert "7952886089" not in output and "PRIVATE" not in output
    assert "work_date=invalid" in output and output.count("\n") == 1
    assert "error_type=TelegramNetworkError" in output


def test_save_error_is_logged_without_exception_body_and_still_raises(monkeypatch, capsys):
    def fail(*args, **kwargs):
        raise RuntimeError("PRIVATE_DB_DETAIL")
    monkeypatch.setattr(discipline.discipline_repo, "save_daily_grade", fail)
    with pytest.raises(RuntimeError, match="PRIVATE_DB_DETAIL"):
        discipline.record_daily_grade(7952886089, 1, "2026-10-17", discipline.GRADE_ALO)
    events = _events(capsys)
    assert events[-1]["stage"] == "save" and events[-1]["outcome"] == "failed"
    assert events[-1]["error_type"] == "RuntimeError"
    assert "PRIVATE_DB_DETAIL" not in str(events)


@pytest.mark.parametrize("profile,expected", [(None, "unknown_employee"), ({"user_id": None}, "not_linked")])
async def test_missing_or_unlinked_profile_is_a_named_skip(monkeypatch, capsys, profile, expected):
    monkeypatch.setattr(discipline.employees, "get_profile", lambda *a, **k: profile)
    result = discipline.EvaluationResult("alo", 3, 3, "2026-10-17", True)
    outcome = await discipline.notify_employee_of_grade(None, 7952886089, result)
    assert outcome == expected
    events = _events(capsys)
    assert events[-1]["outcome"] == expected
    assert not any(e["outcome"] == "telegram_attempt" for e in events)


@pytest.mark.parametrize("function,outcome", [
    ("get_period_point_totals", "totals_failed"), ("format_grade_notice", "format_failed"),
])
async def test_preparation_failure_is_distinct_from_a_telegram_attempt(monkeypatch, capsys, function, outcome):
    monkeypatch.setattr(discipline.employees, "get_profile", lambda *a, **k: {"user_id": 7952886089})
    def fail(*args):
        raise RuntimeError("PRIVATE_QUERY_DETAIL")
    if function == "format_grade_notice":
        monkeypatch.setattr(discipline, "get_period_point_totals", lambda *a: {})
    monkeypatch.setattr(discipline, function, fail)
    result = discipline.EvaluationResult("alo", 3, 3, "2026-10-17", True)
    assert await discipline.notify_employee_of_grade(None, 7952886089, result) == discipline.NOTICE_FAILED
    events = _events(capsys)
    assert events[-1]["outcome"] == outcome and events[-1]["error_type"] == "RuntimeError"
    assert not any(e["outcome"] == "telegram_attempt" for e in events)


@pytest.mark.parametrize("entry", [_bos, _nzr])
@pytest.mark.parametrize("failure", ["notify_entry", "callback_answer"])
async def test_post_save_exception_is_logged_once_and_reraised(bot_dp, monkeypatch, capsys, entry, failure):
    main, bot = bot_dp
    # Let the dispatcher propagate so we can assert the handler re-raised the same exception.
    monkeypatch.setattr(main.dp.errors, "handlers", [])
    _setup()
    if failure == "notify_entry":
        error = RuntimeError("PRIVATE_NOTIFY_DETAIL")
        async def fail(*args):
            raise error
        monkeypatch.setattr(discipline, "notify_employee_of_grade", fail)
    else:
        real_call = type(bot).__call__
        error = TelegramBadRequest(method=AnswerCallbackQuery(callback_query_id="1"), message="query is too old")
        async def fail(self, method, request_timeout=None):
            if isinstance(method, AnswerCallbackQuery):
                raise error
            return await real_call(self, method, request_timeout)
        monkeypatch.setattr(type(bot), "__call__", fail)
    with pytest.raises(type(error)) as raised:
        await entry(main, bot, discipline.GRADE_ALO)
    assert raised.value is error
    events = _events(capsys)
    assert any(e["stage"] == "save" and e["outcome"] == "new" for e in events)
    failures = [e for e in events if e["error_type"] != "none"]
    assert len(failures) == 1
    assert failures[0]["stage"] == "handler_after_save" and failures[0]["outcome"] == "failed"
    assert failures[0]["error_type"] == type(error).__name__
    assert "PRIVATE_NOTIFY_DETAIL" not in str(events) and "query is too old" not in str(events)
    assert _count("daily_evaluations") == _count("daily_evaluation_history") == 1
    assert len(_sessions()) == 1
    if failure == "callback_answer":
        # Both handlers answer the callback AFTER notify: this cannot prevent its first send.
        assert any(e["outcome"] == "telegram_accepted" for e in events)
        assert len(_notices(bot.sent)) == 1
    else:
        assert not _notices(bot.sent)


@pytest.mark.parametrize("entry", [_bos, _nzr])
@pytest.mark.parametrize("function,outcome", [
    ("get_period_point_totals", "totals_failed"), ("format_grade_notice", "format_failed"),
])
async def test_preparation_failure_keeps_existing_reply_without_handler_duplicate(
    bot_dp, monkeypatch, capsys, caplog, entry, function, outcome,
):
    main, bot = bot_dp
    _setup()
    def fail(*args):
        raise RuntimeError("PRIVATE_PREPARATION_DETAIL")
    monkeypatch.setattr(discipline, function, fail)
    sent = await entry(main, bot, discipline.GRADE_ALO)
    events = _events(capsys)
    failures = [e for e in events if e["error_type"] != "none"]
    assert len(failures) == 1 and failures[0]["outcome"] == outcome
    assert not any(e["stage"] == "handler_after_save" for e in events)
    assert not any("grade_notice:" in r.message for r in caplog.records)
    assert not any(e["outcome"] == "telegram_attempt" for e in events)
    assert not _notices(sent)
    assert discipline.grade_notice_reply(discipline.NOTICE_FAILED) in _answers(sent)
    assert _count("daily_evaluations") == 1


@pytest.mark.parametrize("entry", [_bos, _nzr])
@pytest.mark.parametrize("failure", ["guard", "save"])
async def test_guard_and_save_exceptions_are_outside_post_save_handler(bot_dp, monkeypatch, capsys, entry, failure):
    main, bot = bot_dp
    # Let the dispatcher propagate so we can assert the handler re-raised the same exception.
    monkeypatch.setattr(main.dp.errors, "handlers", [])
    _setup()
    error = RuntimeError("PRIVATE_BEFORE_SAVE_DETAIL")
    def fail(*args, **kwargs):
        raise error
    if failure == "guard":
        from services import nazoratchi_day
        monkeypatch.setattr(nazoratchi_day, "check_active", fail)
    else:
        monkeypatch.setattr(discipline.discipline_repo, "save_daily_grade", fail)
    with pytest.raises(RuntimeError) as raised:
        await entry(main, bot, discipline.GRADE_ALO)
    assert raised.value is error
    events = _events(capsys)
    assert not any(e["stage"] == "handler_after_save" for e in events)
    if failure == "save":
        failures = [e for e in events if e["error_type"] != "none"]
        assert len(failures) == 1 and failures[0]["stage"] == "save"
    assert not _notices(bot.sent) and _count("daily_evaluations") == 0
