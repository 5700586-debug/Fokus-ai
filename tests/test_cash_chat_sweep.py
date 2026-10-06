"""Kassa dialogining eski vaqtinchalik xabarlarini yoshga qarab tozalash + eskirgan csui_ tugmalari."""

from datetime import datetime, timedelta, timezone

import pytest
from aiogram.methods import AnswerCallbackQuery, DeleteMessage, SendMessage

import cash_chat_cleanup
from db import get_connection
from repositories import bot_messages as bot_messages_repo
from repositories import cash_shifts as cash_shifts_repo
from services import cash_shift
from tests.bot_harness import RecordingBot, send, send_callback
from tests.test_cash_close_manual_review import (
    KASSIR, MOLIYACHI, _joined, _shift, _submit_to_moliyachi, _to_photo_prompt,
)

pytestmark = [pytest.mark.anyio, pytest.mark.usefixtures("manual_close_review")]


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _log(workflow: str, key: str, chat_id: int, message_id: int, age_hours: float) -> None:
    bot_messages_repo.log_message(workflow, key, chat_id, message_id)
    old = (datetime.now(timezone.utc) - timedelta(hours=age_hours)).isoformat()
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE bot_workflow_messages SET sent_at = ? WHERE workflow = ? AND message_id = ?",
            (old, workflow, message_id),
        )
        conn.commit()
    finally:
        conn.close()


def _remaining() -> set[int]:
    conn = get_connection()
    try:
        return {r["message_id"] for r in conn.execute("SELECT message_id FROM bot_workflow_messages").fetchall()}
    finally:
        conn.close()


def _bot() -> RecordingBot:
    return RecordingBot(token="123456:TEST")


def _deleted(bot: RecordingBot) -> set[int]:
    return {m.message_id for m in bot.sent if isinstance(m, DeleteMessage)}


async def test_old_cash_shift_close_and_cash_close_review_messages_are_deleted_new_ones_stay(temp_db):
    _log("cash_shift_close", "1", 111, 10, age_hours=9)
    _log("cash_close_review", "2", 111, 20, age_hours=9)
    _log("cash_shift_close", "1", 111, 11, age_hours=7)   # yangi
    _log("cash_close_review", "2", 111, 21, age_hours=1)  # yangi
    bot = _bot()

    handled = await cash_chat_cleanup.sweep(bot)

    assert handled == 2
    assert _deleted(bot) == {10, 20}
    assert _remaining() == {11, 21}


async def test_other_workflows_are_never_touched(temp_db):
    _log("rule_learning", "5", 111, 30, age_hours=100)
    bot = _bot()

    await cash_chat_cleanup.sweep(bot)

    assert _deleted(bot) == set() and _remaining() == {30}


async def test_review_photos_of_shift_still_awaiting_finance_stay(bot_dp):
    main, bot = bot_dp
    await _to_photo_prompt(main, bot)
    await _submit_to_moliyachi(main, bot)
    shift = _shift()
    assert shift["status"] == cash_shift.STATUS_NEEDS_FINANCE_REVIEW
    conn = get_connection()
    try:
        before = conn.execute(
            "SELECT COUNT(*) AS n FROM bot_workflow_messages WHERE workflow = 'cash_close_review'"
        ).fetchone()["n"]
        conn.execute(
            "UPDATE bot_workflow_messages SET sent_at = ?", ((datetime.now(timezone.utc) - timedelta(hours=30)).isoformat(),)
        )
        conn.commit()
    finally:
        conn.close()
    assert before >= 7  # kassir rasm/summa xabarlari + moliyachi 3 rasm
    sweeper_bot = _bot()

    await cash_chat_cleanup.sweep(sweeper_bot)

    assert _deleted(sweeper_bot) == set()  # qaror kutilmoqda: moliyachi rasmni ko'rishi kerak
    conn = get_connection()
    try:
        after = conn.execute(
            "SELECT COUNT(*) AS n FROM bot_workflow_messages WHERE workflow = 'cash_close_review'"
        ).fetchone()["n"]
    finally:
        conn.close()
    assert after == before

    # Qaror qilingach (rad) qatorlar odatdagidek tozalanadi, qaror oqimi buzilmagan.
    await send_callback(main.dp, bot, MOLIYACHI, data=f"cashclose_no:{shift['id']}", target_chat_id=MOLIYACHI)
    assert cash_shifts_repo.get_shift(shift["id"])["status"] == cash_shift.STATUS_RECHECK_REQUIRED


async def test_old_review_rows_of_decided_shift_are_swept(bot_dp):
    main, bot = bot_dp
    await _to_photo_prompt(main, bot)
    shift_id = _shift()["id"]  # hali ochiq (yuborilmagan, tashlab ketilgan oqim)
    _log("cash_close_review", str(shift_id), KASSIR, 40, age_hours=12)
    sweeper_bot = _bot()

    await cash_chat_cleanup.sweep(sweeper_bot)

    assert 40 in _deleted(sweeper_bot)


async def test_money_data_and_final_messages_are_untouched(bot_dp):
    main, bot = bot_dp
    await _to_photo_prompt(main, bot)
    await _submit_to_moliyachi(main, bot)
    shift_before = _shift()
    await send_callback(main.dp, bot, MOLIYACHI, data=f"cashclose_ok:{shift_before['id']}", target_chat_id=MOLIYACHI)
    decided_shift = _shift()
    conn = get_connection()
    try:
        approvals_before = [dict(r) for r in conn.execute("SELECT * FROM cash_shift_approvals").fetchall()]
    finally:
        conn.close()
    _log("cash_shift_close", str(shift_before["id"]), KASSIR, 50, age_hours=20)

    sweeper_bot = _bot()
    await cash_chat_cleanup.sweep(sweeper_bot)

    after = _shift()
    assert {k: v for k, v in after.items() if k != "updated_at"} == {
        k: v for k, v in decided_shift.items() if k != "updated_at"
    }  # pul/holat ustunlari tozalashdan oldingi bilan bir xil
    assert after["actual_cash_balance"] == 300000 and after["status"] != cash_shift.STATUS_NEEDS_FINANCE_REVIEW
    conn = get_connection()
    try:
        approvals_after = [dict(r) for r in conn.execute("SELECT * FROM cash_shift_approvals").fetchall()]
    finally:
        conn.close()
    assert approvals_after == approvals_before and approvals_after
    # Faqat track qilingan 50 o'chdi; yakuniy xabarlar (Smena yopildi, Moliyachi tasdiqladi/qaytardi) track
    # qilinmagan, shuning uchun sweep ularni ko'rmaydi ham.
    assert _deleted(sweeper_bot) == {50}


async def test_failing_delete_does_not_crash_sweep_or_scheduler_tick(temp_db, monkeypatch):
    _log("cash_shift_close", "1", 111, 60, age_hours=9)
    _log("cash_close_review", "2", 111, 61, age_hours=9)
    bot = _bot()

    async def _fail(*args, **kwargs):
        raise RuntimeError("Telegram o'chirishga ruxsat bermadi")

    bot.delete_message = _fail

    await cash_chat_cleanup._tick(bot)  # istisno ko'tarilmaydi

    assert _remaining() == set()  # qatorlar baribir olib tashlanadi (qayta urinilmaydi)

    async def _boom(_bot):
        raise RuntimeError("kutilmagan")

    monkeypatch.setattr(cash_chat_cleanup, "sweep", _boom)
    await cash_chat_cleanup._tick(bot)  # scheduler yiqilmaydi


async def test_scheduler_runs_every_30_minutes(temp_db):
    scheduler = cash_chat_cleanup.start_scheduler(_bot())
    try:
        job = scheduler.get_job("cash_chat_sweep")
        assert job is not None and job.trigger.interval == timedelta(minutes=30)
    finally:
        scheduler.shutdown(wait=False)


# ------------------------------------------------------- eskirgan csui_ tugmalari --


async def test_stateless_old_csui_button_gets_stale_answer(bot_dp):
    main, bot = bot_dp

    sent = await send_callback(main.dp, bot, KASSIR, data="csui_rev_send", target_chat_id=KASSIR)

    answers = [m for m in sent if isinstance(m, AnswerCallbackQuery)]
    assert answers and "Bu tugma eskirgan" in answers[0].text and answers[0].show_alert is True
    assert not any(isinstance(m, SendMessage) for m in sent)


@pytest.mark.parametrize("data", ["csui_close_amount_ok", "csui_open_prev_ok:abc", "csui_recv_amount_ok", "csui_ledger_items"])
async def test_other_stateless_csui_buttons_are_also_answered(bot_dp, data):
    main, bot = bot_dp

    sent = await send_callback(main.dp, bot, KASSIR, data=data, target_chat_id=KASSIR)

    assert any(isinstance(m, AnswerCallbackQuery) and "Bu tugma eskirgan" in (m.text or "") for m in sent)


async def test_resubmit_button_still_works_and_is_not_swallowed_by_the_stale_fallback(bot_dp):
    main, bot = bot_dp
    await _to_photo_prompt(main, bot)
    await _submit_to_moliyachi(main, bot)
    shift_id = _shift()["id"]
    await send_callback(main.dp, bot, MOLIYACHI, data=f"cashclose_no:{shift_id}", target_chat_id=MOLIYACHI)

    sent = await send_callback(main.dp, bot, KASSIR, data=f"csui_rev_resubmit:{shift_id}", target_chat_id=KASSIR)

    assert "📒 Daftar rasmini yuboring" in _joined(sent)
    assert not any(isinstance(m, AnswerCallbackQuery) and "eskirgan" in (m.text or "") for m in sent)


async def test_active_state_buttons_still_reach_their_handlers(bot_dp):
    main, bot = bot_dp
    await _to_photo_prompt(main, bot)

    sent = await _submit_to_moliyachi(main, bot)  # holat faol: csui_rev_send o'z handleriga tushadi

    assert not any(isinstance(m, AnswerCallbackQuery) and "eskirgan" in (m.text or "") for m in sent)
    assert _shift()["status"] == cash_shift.STATUS_NEEDS_FINANCE_REVIEW
