"""E'tirozni Founderga yetkazish: "yuborildi" faqat yetgandan keyin, xatoda "Qayta yuborish", dublikatsiz retry.
Telegram va OpenAI MOCK, vaqtincha lokal DB. Telegram javobi yo'qolgan (natija noma'lum) holatni test QILMAYDI —
bu cheklov STATE'da ochiq qayd etilgan."""

import asyncio
from types import SimpleNamespace

import pytest

from config import FOUNDER_ID
from repositories import discipline as discipline_repo
from services import discipline
from tests.test_discipline_dialog_cleanup import EMP, NAZ2, Tg, _penalty_with_notice, _setup  # noqa: F401

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def tg(bot_dp, monkeypatch):
    main, bot = bot_dp
    return Tg(main, bot, monkeypatch)


def _ai(monkeypatch, main) -> list:
    calls: list = []

    async def fake_create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(output_text="Tavsiya: ko'rib chiqilsin.")

    monkeypatch.setattr(main.openai_client.responses, "create", fake_create)
    return calls


def _founder_cards(tg: Tg) -> list:
    return [m for m in tg.sent_log if m["chat"] == FOUNDER_ID]


def _retry_data(tg: Tg, penalty_id: int):
    edit = [e for e in tg.edits if e[3] is not None and "Qayta yuborish" in str(e[3])][-1]
    return edit[1], edit[3].inline_keyboard[0][0].callback_data


async def _failed_first_attempt(tg: Tg, monkeypatch):
    penalty_id, notice = await _penalty_with_notice(tg, monkeypatch)
    calls = _ai(monkeypatch, tg.main)
    tg.fail_send = lambda m: m.chat_id == FOUNDER_ID
    await tg.press(EMP, f"nzr_appeal:{penalty_id}", notice)
    prompt = tg.last(EMP)
    reason_id = await tg.say(EMP, "Men telefon ishlatmadim")
    tg.fail_send = None
    return penalty_id, calls, prompt, reason_id


async def test_sent_message_appears_only_after_founder_received_the_card(tg, monkeypatch):
    penalty_id, notice = await _penalty_with_notice(tg, monkeypatch)
    _ai(monkeypatch, tg.main)
    await tg.press(EMP, f"nzr_appeal:{penalty_id}", notice)

    await tg.say(EMP, "Men telefon ishlatmadim")

    kinds = [(e[0], e[1] if e[0] == "send" else None, e[2] if e[0] != "answer" else "") for e in tg.events]
    sending = next(i for i, e in enumerate(tg.events) if e[0] == "send" and e[1] == EMP and "Yuborilmoqda" in e[2])
    founder = next(i for i, e in enumerate(tg.events) if e[0] == "send" and e[1] == FOUNDER_ID)
    done = next(i for i, e in enumerate(tg.events) if e[0] == "edit" and "rahbarga yuborildi" in e[2])
    assert sending < founder < done, kinds
    row = discipline.get_penalty(penalty_id)
    assert row["appeal_delivered_at"] and row["appeal_founder_message_id"] == _founder_cards(tg)[-1]["id"]


async def test_founder_failure_keeps_reason_and_messages_and_offers_retry(tg, monkeypatch):
    penalty_id, calls, prompt, reason_id = await _failed_first_attempt(tg, monkeypatch)

    assert tg.deleted == []
    assert not any("rahbarga yuborildi" in e[2] for e in tg.edits)
    assert any("rahbarga yuborilmadi" in e[2] for e in tg.edits)
    row = discipline.get_penalty(penalty_id)
    assert row["appeal_status"] == discipline.APPEAL_PENDING and row["appeal_reason"] == "Men telefon ishlatmadim"
    assert row["appeal_delivered_at"] is None and row["appeal_delivery_claimed_at"] is None  # qayta urinish mumkin
    assert _retry_data(tg, penalty_id)[1] == f"bos:redeliver:{penalty_id}"
    assert (await tg.fsm(EMP, EMP)) == {}  # FSM tozalangan: retry bazadan ishlaydi


async def test_retry_delivers_existing_appeal_without_new_records_or_ai(tg, monkeypatch):
    penalty_id, calls, prompt, reason_id = await _failed_first_attempt(tg, monkeypatch)
    ai_calls_before = len(calls)
    message_id, data = _retry_data(tg, penalty_id)
    ledger_before = discipline_repo.get_bonus_ledger_totals_since(EMP, "1970-01-01T00:00:00")
    penalties_before = len(discipline.list_appealable_penalties(EMP))

    await tg.press(EMP, data, message_id)

    cards = _founder_cards(tg)
    assert len(cards) == 1 and "Men telefon ishlatmadim" in cards[0]["text"] and "Tavsiya" in cards[0]["text"]
    assert any(c.startswith("bos:decide:") for row in cards[0]["markup"].inline_keyboard for c in [b.callback_data for b in row])
    assert len(calls) == ai_calls_before  # AI tavsiyasi qayta yaratilmadi
    assert any(e[1] == message_id and "rahbarga yuborildi" in e[2] and e[3] is None for e in tg.edits)
    assert (EMP, prompt["id"]) in tg.deleted and (EMP, reason_id) in tg.deleted and (EMP, message_id) not in tg.deleted
    assert discipline_repo.get_bonus_ledger_totals_since(EMP, "1970-01-01T00:00:00") == ledger_before
    assert len(discipline.list_appealable_penalties(EMP)) == penalties_before
    assert discipline.get_penalty(penalty_id)["appeal_delivered_at"]


async def test_retry_answers_the_button_before_the_slow_delivery(tg, monkeypatch):
    penalty_id, calls, prompt, reason_id = await _failed_first_attempt(tg, monkeypatch)
    message_id, data = _retry_data(tg, penalty_id)
    tg.events.clear()

    await tg.press(EMP, data, message_id)

    answer = next(i for i, e in enumerate(tg.events) if e[0] == "answer" and "Yuborilmoqda" in (e[1] or ""))
    founder = next(i for i, e in enumerate(tg.events) if e[0] == "send" and e[1] == FOUNDER_ID)
    assert answer < founder


async def test_retry_guards_foreign_resolved_delivered_and_parallel_presses(tg, monkeypatch):
    penalty_id, calls, prompt, reason_id = await _failed_first_attempt(tg, monkeypatch)
    message_id, data = _retry_data(tg, penalty_id)

    await tg.press(NAZ2, data, message_id, chat_id=NAZ2)  # begona
    assert _founder_cards(tg) == []

    await asyncio.gather(tg.press(EMP, data, message_id), tg.press(EMP, data, message_id))  # parallel
    assert len(_founder_cards(tg)) == 1

    await tg.press(EMP, data, message_id)  # allaqachon yetkazilgan
    assert len(_founder_cards(tg)) == 1

    card = _founder_cards(tg)[0]
    await tg.press(FOUNDER_ID, f"bos:decide:{penalty_id}:{discipline.DECISION_REJECTED}", card["id"], chat_id=FOUNDER_ID)
    await tg.press(EMP, data, message_id)  # hal qilingan
    assert len(_founder_cards(tg)) == 1


async def test_resolved_appeal_is_not_redelivered(tg, monkeypatch):
    penalty_id, calls, prompt, reason_id = await _failed_first_attempt(tg, monkeypatch)
    message_id, data = _retry_data(tg, penalty_id)
    discipline_repo.decide_penalty_appeal(penalty_id, discipline.DECISION_REJECTED, FOUNDER_ID)

    await tg.press(EMP, data, message_id)

    assert _founder_cards(tg) == []


async def test_voice_appeal_is_redelivered_with_stored_file_id(tg, monkeypatch):
    penalty_id, notice = await _penalty_with_notice(tg, monkeypatch)
    _ai(monkeypatch, tg.main)
    assert discipline.submit_appeal(penalty_id, "(ovozli xabar)", "VOICE-FILE-ID")
    shown = await tg.bot.send_message(EMP, "⚠️ Yuborilmadi")  # retry tugmasi turgan xabar o'rnida
    data = f"bos:redeliver:{penalty_id}"

    await tg.press(EMP, data, shown.message_id)

    cards = _founder_cards(tg)
    assert len(cards) == 1 and cards[0]["voice"] == "VOICE-FILE-ID" and "(ovozli xabar)" in cards[0]["text"]


async def test_stale_claim_expires_so_a_crashed_attempt_can_be_retried(tg, monkeypatch):
    penalty_id, notice = await _penalty_with_notice(tg, monkeypatch)
    assert discipline.submit_appeal(penalty_id, "sabab", None)
    assert discipline.claim_appeal_delivery(penalty_id)
    assert not discipline.claim_appeal_delivery(penalty_id)  # urinish ketmoqda
    conn = __import__("db").get_connection()
    try:
        conn.execute("UPDATE discipline_penalties SET appeal_delivery_claimed_at = '2000-01-01T00:00:00+00:00' WHERE id = ?", (penalty_id,))
        conn.commit()
    finally:
        conn.close()
    assert discipline.claim_appeal_delivery(penalty_id)  # eskirgan band qayta olinadi


async def test_employee_notice_or_cleanup_failure_keeps_saved_decision_and_refund(tg, monkeypatch):
    penalty_id, notice = await _penalty_with_notice(tg, monkeypatch)
    _ai(monkeypatch, tg.main)
    await tg.press(EMP, f"nzr_appeal:{penalty_id}", notice)
    await tg.say(EMP, "Men telefon ishlatmadim")
    card = tg.last(FOUNDER_ID)
    bank_before = discipline.get_salary(EMP)["bonus_bank"]
    tg.fail_send = lambda m: m.chat_id == EMP  # xodimga natija xabari yuborilmaydi
    tg.fail_delete = True

    await tg.press(FOUNDER_ID, f"bos:decide:{penalty_id}:{discipline.DECISION_APPROVED}", card["id"], chat_id=FOUNDER_ID)

    row = discipline.get_penalty(penalty_id)
    assert row["appeal_status"] == discipline.APPEAL_RESOLVED and row["appeal_decision"] == discipline.DECISION_APPROVED
    assert discipline.get_salary(EMP)["bonus_bank"] == bank_before + 30
