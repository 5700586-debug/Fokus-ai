"""Menu performance without dropping keyboard-owner and tracking protections."""

from datetime import datetime

import pytest
from aiogram.methods import SendMessage, SendPhoto
from aiogram.types import Chat, Message

import db
import employees
from repositories import bot_messages as repo
from services import latency_probe, menu_screens
from tests.test_menu_screen_cleanup import EMP, env  # noqa: F401 — real session fixture

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _screen(chat, mid):
    return Message(message_id=mid, date=datetime.now(), chat=Chat(id=chat, type="private"), text="new")


def _rows(key):
    conn = db.get_connection()
    try:
        return [dict(row) for row in conn.execute(
            "SELECT * FROM bot_workflow_messages WHERE workflow = ? AND workflow_key = ? ORDER BY id",
            (menu_screens.WORKFLOW, key),
        ).fetchall()]
    finally:
        conn.close()


def test_exchange_uses_two_queries_one_connection_and_keeps_other_chats_and_workflows():
    key, flow = menu_screens.screen_key(EMP), menu_screens.flow_key(EMP)
    repo.log_message(menu_screens.WORKFLOW, key, EMP, 101)
    repo.log_message(menu_screens.WORKFLOW, flow, EMP, 102)
    repo.log_message(menu_screens.WORKFLOW, key, EMP + 1, 103)
    repo.log_message("cash_shift_close", key, EMP, 104)
    token = latency_probe._metrics.set(latency_probe._Metrics())
    try:
        metrics = latency_probe._metrics.get()
        old = repo.replace_menu_messages(menu_screens.WORKFLOW, (key, flow), key, EMP, [201, 202])
        assert {r["message_id"] for r in old} == {101, 102}
        assert (metrics.db_queries, metrics.pool_acquires) == (2, 1)
    finally:
        latency_probe._metrics.reset(token)
    assert {r["message_id"] for r in _rows(key)} == {201, 202, 103}
    assert repo.pop_messages("cash_shift_close", key) == [{"chat_id": EMP, "message_id": 104}]


def test_exchange_failure_rolls_back_old_tracking_and_inserts_nothing(monkeypatch):
    key, flow = menu_screens.screen_key(EMP), menu_screens.flow_key(EMP)
    repo.log_message(menu_screens.WORKFLOW, key, EMP, 101)
    real_connect = repo.get_connection

    class FailingConnection:
        def __init__(self):
            self.inner = real_connect()

        def execute(self, sql, *args, **kwargs):
            if sql.startswith("WITH tracked"):
                raise RuntimeError("insert failure")
            return self.inner.execute(sql, *args, **kwargs)

        def commit(self):
            return self.inner.commit()

        def close(self):
            return self.inner.close()

    monkeypatch.setattr(repo, "get_connection", FailingConnection)
    with pytest.raises(RuntimeError, match="insert failure"):
        repo.replace_menu_messages(menu_screens.WORKFLOW, (key, flow), key, EMP, [201])
    assert [r["message_id"] for r in _rows(key)] == [101]


async def test_menu_exchange_and_delete_are_batched_with_keyboard_protected(env):
    chat = EMP
    await menu_screens._commit(env.bot, menu_screens._Capture(chat, 10, [_screen(chat, 101)], keyboard_ids={101}))
    env.session.batches.clear()
    await menu_screens._commit(env.bot, menu_screens._Capture(chat, 11, [_screen(chat, 201)], keyboard_ids={201}))
    assert env.session.batches == [[101, 11]]
    assert [r["message_id"] for r in _rows(menu_screens.screen_key(chat))] == [201]


async def test_tracking_failure_preserves_old_keyboard_and_does_not_delete_anything(env, monkeypatch):
    await env.tap(EMP, "⭐ Mening natijalarim")
    deleted = list(env.session.deleted)
    owner = env.session.keyboard_owners[EMP]

    def fail(*args, **kwargs):
        raise RuntimeError("DB unavailable")

    monkeypatch.setattr(repo, "replace_menu_messages", fail)
    await env.tap(EMP, "💰 Oyligim")
    assert env.session.deleted == deleted
    assert owner not in {mid for _, mid in env.session.deleted}
    assert owner in {r["message_id"] for r in _rows(menu_screens.screen_key(EMP))}


async def test_batch_delete_never_exceeds_one_hundred_ids(env):
    key = menu_screens.screen_key(EMP)
    repo.replace_menu_messages(menu_screens.WORKFLOW, (key, menu_screens.flow_key(EMP)), key, EMP, list(range(100, 305)))
    await menu_screens._commit(env.bot, menu_screens._Capture(EMP, 9000, [_screen(EMP, 1000)], keyboard_ids={1000}))
    assert [len(batch) for batch in env.session.batches] == [100, 100, 6]
    assert (EMP, 1000) not in env.session.deleted


async def _profile_with_photo():
    from tests.test_employee_dashboard import _make_employee

    _make_employee(EMP)
    conn = db.get_connection()
    try:
        conn.execute("UPDATE employees SET photo_file_id = ? WHERE user_id = ?", ("synthetic-photo", EMP))
        conn.commit()
    finally:
        conn.close()


async def test_photo_and_result_use_one_send_and_keep_the_section_keyboard(env, capsys):
    await _profile_with_photo()
    await env.tap(EMP, "⭐ Mening natijalarim")
    markup = env.screens(EMP)[-1]["markup"]
    count = len(env.screens(EMP))
    capsys.readouterr()
    env.session.batches.clear()
    await env.tap(EMP, "⭐ Yulduzlarim")
    new = env.screens(EMP)[count:]
    assert len(new) == 1 and "Joriy yulduzlar" in new[0]["text"] and "Oxirgi 2 kun" in new[0]["text"]
    assert new[0]["markup"] == markup
    assert env.session.keyboard_owners[EMP] == new[0]["id"]
    lines = [line for line in capsys.readouterr().out.splitlines() if "handler=mystars_handler " in line]
    assert len(lines) == 1
    metrics = dict(item.split("=", 1) for item in lines[0].split()[1:])
    assert int(metrics["db_queries"]) <= 11 and metrics["pool_acquires"] == "2"
    assert len(env.session.batches) == 1  # one send + one delete request


async def test_photo_failure_still_sends_the_complete_text(env):
    await _profile_with_photo()
    env.session.fail_send = lambda method: isinstance(method, SendPhoto)
    await env.tap(EMP, "⭐ Yulduzlarim")
    assert "Joriy yulduzlar" in env.screens(EMP)[-1]["text"]
    assert "Oxirgi 2 kun" in env.screens(EMP)[-1]["text"]
    assert env.screens(EMP)[-1]["markup"] is not None


async def test_long_history_keeps_photo_and_full_text_without_truncation(env, monkeypatch):
    await _profile_with_photo()
    from services import employee_dashboard

    real = employee_dashboard.read_mystars

    def long_history(user):
        stars, _, dash = real(user)
        return stars, [{"year_month": f"month-{i}", "stars": 5, "bonus_amount": 1000} for i in range(60)], dash

    monkeypatch.setattr(employee_dashboard, "read_mystars", long_history)
    await env.tap(EMP, "⭐ Yulduzlarim")
    shown = env.screens(EMP)
    assert len(shown) == 2
    assert "month-59" in shown[-1]["text"] and "Oxirgi 2 kun" in shown[-1]["text"]
    assert env.session.keyboard_owners[EMP] == shown[-1]["id"]
