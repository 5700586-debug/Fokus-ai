"""Vaqtinchalik "Yuborilmoqda…" xabari (yoki xodimga barcha javoblar) yuborilmasa ham e'tiroz Founderga yetkaziladi,
holat bazada saqlanadi va xodim uni mavjud menyudan qayta yubora oladi. Telegram/OpenAI MOCK, vaqtincha lokal DB."""

from types import SimpleNamespace

import pytest

from config import FOUNDER_ID
from repositories import discipline as discipline_repo
from roles import set_role
from services import discipline
from tests.test_discipline_dialog_cleanup import EMP, NAZ2, Tg, _penalty_with_notice

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def tg(bot_dp, monkeypatch):
    main, bot = bot_dp
    return Tg(main, bot, monkeypatch)


def _ai(monkeypatch, main) -> None:
    async def fake_create(**kwargs):
        return SimpleNamespace(output_text="Tavsiya: ko'rib chiqilsin.")

    monkeypatch.setattr(main.openai_client.responses, "create", fake_create)


def _cards(tg: Tg) -> list:
    return [m for m in tg.sent_log if m["chat"] == FOUNDER_ID]


def _employee_texts(tg: Tg) -> list[str]:
    return [m["text"] for m in tg.sent_log if m["chat"] == EMP]


def _retry_buttons(message: dict) -> list[str]:
    markup = message["markup"]
    return [b.callback_data for row in markup.inline_keyboard for b in row] if markup else []


async def _appeal(tg: Tg, monkeypatch, *, fail_waiting=False, fail_founder=False, fail_employee=False):
    penalty_id, notice = await _penalty_with_notice(tg, monkeypatch)
    _ai(monkeypatch, tg.main)
    set_role(EMP, "kassir", set_by=FOUNDER_ID)
    await tg.press(EMP, f"nzr_appeal:{penalty_id}", notice)
    prompt = tg.last(EMP)
    tg.fail_send = lambda m: (
        (fail_founder and m.chat_id == FOUNDER_ID)
        or (fail_employee and m.chat_id == EMP)
        or (fail_waiting and m.chat_id == EMP and "Yuborilmoqda" in (m.text or ""))
    )
    reason_id = await tg.say(EMP, "Men telefon ishlatmadim")
    tg.fail_send = None
    return penalty_id, prompt, reason_id


async def test_waiting_message_failure_does_not_stop_delivery_to_founder(tg, monkeypatch):
    penalty_id, prompt, reason_id = await _appeal(tg, monkeypatch, fail_waiting=True)

    assert len(_cards(tg)) == 1 and "Men telefon ishlatmadim" in _cards(tg)[0]["text"]
    assert discipline.get_penalty(penalty_id)["appeal_delivered_at"]


async def test_without_waiting_message_final_success_arrives_as_new_message_then_cleanup(tg, monkeypatch):
    penalty_id, prompt, reason_id = await _appeal(tg, monkeypatch, fail_waiting=True)

    final = [m for m in tg.sent_log if m["chat"] == EMP and "rahbarga yuborildi" in m["text"]]
    assert len(final) == 1
    assert (EMP, prompt["id"]) in tg.deleted and (EMP, reason_id) in tg.deleted
    assert (EMP, final[0]["id"]) not in tg.deleted


async def test_no_waiting_and_founder_failure_gives_new_message_with_retry_button(tg, monkeypatch):
    penalty_id, prompt, reason_id = await _appeal(tg, monkeypatch, fail_waiting=True, fail_founder=True)

    failed = [m for m in tg.sent_log if m["chat"] == EMP and "rahbarga yuborilmadi" in m["text"]]
    assert len(failed) == 1 and f"bos:redeliver:{penalty_id}" in _retry_buttons(failed[0])
    assert tg.deleted == [] and _cards(tg) == []
    row = discipline.get_penalty(penalty_id)
    assert row["appeal_status"] == discipline.APPEAL_PENDING and row["appeal_reason"] == "Men telefon ishlatmadim"
    assert row["appeal_delivered_at"] is None


async def test_all_employee_replies_failing_keeps_reason_state_and_old_messages(tg, monkeypatch):
    penalty_id, prompt, reason_id = await _appeal(tg, monkeypatch, fail_employee=True)  # Founderga yetadi
    delivered = discipline.get_penalty(penalty_id)
    assert len(_cards(tg)) == 1 and delivered["appeal_delivered_at"]  # xodimga xabar xatosi yetkazilganlikni buzmaydi
    assert tg.deleted == []  # yakuniy ekran ko'rsatilmadi -> eski xabarlar qoladi



async def test_all_failing_leaves_pending_undelivered_appeal_and_no_cleanup(tg, monkeypatch):
    penalty_id, prompt, reason_id = await _appeal(tg, monkeypatch, fail_employee=True, fail_founder=True)

    row = discipline.get_penalty(penalty_id)
    assert row["appeal_status"] == discipline.APPEAL_PENDING and row["appeal_reason"] == "Men telefon ishlatmadim"
    assert row["appeal_delivered_at"] is None and row["appeal_delivery_claimed_at"] is None
    assert tg.deleted == [] and _cards(tg) == []


async def test_employee_finds_undelivered_appeal_in_apellyatsiya_menu_after_fsm_is_gone(tg, monkeypatch):
    penalty_id, prompt, reason_id = await _appeal(tg, monkeypatch, fail_employee=True, fail_founder=True)
    assert (await tg.fsm(EMP, EMP)) == {}  # FSM tozalangan (restartga teng)

    await tg.say(EMP, "/apellyatsiya")
    menu = tg.last(EMP)
    assert f"bos:redeliver:{penalty_id}" in _retry_buttons(menu)

    ledger_before = discipline_repo.get_bonus_ledger_totals_since(EMP, "1970-01-01T00:00:00")
    await tg.press(EMP, f"bos:redeliver:{penalty_id}", menu["id"])
    await tg.press(EMP, f"bos:redeliver:{penalty_id}", menu["id"])  # takroriy urinish

    assert len(_cards(tg)) == 1  # bitta karta
    assert any(e[1] == menu["id"] and "rahbarga yuborildi" in e[2] for e in tg.edits)
    assert discipline_repo.get_bonus_ledger_totals_since(EMP, "1970-01-01T00:00:00") == ledger_before
    assert discipline.get_penalty(penalty_id)["appeal_reason"] == "Men telefon ishlatmadim"
    await tg.say(EMP, "/apellyatsiya")  # yetkazilgach menyuda qayta yuborish yo'q
    assert f"bos:redeliver:{penalty_id}" not in _retry_buttons(tg.last(EMP))


async def test_old_appeal_button_on_undelivered_appeal_offers_retry_not_a_new_appeal(tg, monkeypatch):
    penalty_id, prompt, reason_id = await _appeal(tg, monkeypatch, fail_employee=True, fail_founder=True)
    sent_before = len(tg.sent_log)

    await tg.press(EMP, f"nzr_appeal:{penalty_id}", 12345)

    offer = tg.sent_log[sent_before]
    assert f"bos:redeliver:{penalty_id}" in _retry_buttons(offer)
    assert discipline.get_penalty(penalty_id)["appeal_reason"] == "Men telefon ishlatmadim"  # sabab qayta so'ralmadi
    assert (await tg.fsm(EMP, EMP)) == {}  # yangi FSM holati ochilmadi


async def test_foreign_resolved_and_delivered_appeals_are_not_resent(tg, monkeypatch):
    penalty_id, prompt, reason_id = await _appeal(tg, monkeypatch, fail_employee=True, fail_founder=True)
    set_role(NAZ2, "kassir", set_by=FOUNDER_ID)
    await tg.say(NAZ2, "/apellyatsiya")
    assert all(f"bos:redeliver:{penalty_id}" not in _retry_buttons(m) for m in tg.sent_log if m["chat"] == NAZ2)
    await tg.press(NAZ2, f"bos:redeliver:{penalty_id}", 777, chat_id=NAZ2)
    assert _cards(tg) == []  # begona

    discipline_repo.decide_penalty_appeal(penalty_id, discipline.DECISION_REJECTED, FOUNDER_ID)
    await tg.press(EMP, f"bos:redeliver:{penalty_id}", 778)
    assert _cards(tg) == []  # hal qilingan
