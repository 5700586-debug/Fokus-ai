"""Minus va e'tiroz dialogidagi eski ishchi xabarlarni tozalash (Telegram va OpenAI MOCK, vaqtincha lokal DB).
Bot har yuborgan xabarga noyob ID beradi va o'chirishlarni yozib boradi."""

import itertools
import json
from datetime import datetime
from types import SimpleNamespace

import pytest
from aiogram.methods import AnswerCallbackQuery, DeleteMessage, EditMessageReplyMarkup, EditMessageText, SendMessage, SendVoice
from aiogram.types import CallbackQuery, Chat, Message, Update
from aiogram.types import User as TgUser

from config import FOUNDER_ID, RECRUITING_BRANCH_NAMES
from repositories import bot_messages
from services import dialog_cleanup, discipline
from tests.bot_harness import RecordingBot, make_message

pytestmark = pytest.mark.anyio

NAZ = 560001
NAZ2 = 560002
EMP = 740001
CARD = 9001  # xodim kartasi / minus menyusi xabari (nazoratchi chatida)
RULE = 3


@pytest.fixture
def anyio_backend():
    return "asyncio"


class Tg:
    def __init__(self, main, bot, monkeypatch):
        self.main, self.bot = main, bot
        self.ids = itertools.count(5000)
        self.deleted: list[tuple[int, int]] = []
        self.sent_log: list[dict] = []
        self.edits: list[tuple] = []
        self.events: list[tuple] = []
        self.markup_removed: list[tuple[int, int]] = []
        self.fail_send = None
        self.fail_delete = False
        self.on_delete = None
        original = RecordingBot.__call__

        async def call(inner, method, request_timeout=None):
            if isinstance(method, DeleteMessage):
                if self.on_delete:
                    self.on_delete()
                if self.fail_delete:
                    raise RuntimeError("o'chirib bo'lmadi")
                self.deleted.append((method.chat_id, method.message_id))
                return True
            if isinstance(method, (SendMessage, SendVoice)):
                if self.fail_send and self.fail_send(method):
                    raise RuntimeError("yuborib bo'lmadi")
                message_id = next(self.ids)
                text = method.text if isinstance(method, SendMessage) else (method.caption or "")
                self.sent_log.append(
                    {"chat": method.chat_id, "id": message_id, "text": text, "markup": method.reply_markup,
                     "voice": method.voice if isinstance(method, SendVoice) else None}
                )
                self.events.append(("send", method.chat_id, text))
                return Message(
                    message_id=message_id, date=datetime.now(), chat=Chat(id=method.chat_id, type="private"), text=text
                ).as_(inner)
            if isinstance(method, AnswerCallbackQuery):
                self.events.append(("answer", method.text))
            if isinstance(method, EditMessageText):
                self.edits.append((method.chat_id, method.message_id, method.text, method.reply_markup))
                self.events.append(("edit", method.chat_id, method.text))
            if isinstance(method, EditMessageReplyMarkup) and method.reply_markup is None:
                self.markup_removed.append((method.chat_id, method.message_id))
            return await original(inner, method, request_timeout)

        monkeypatch.setattr(RecordingBot, "__call__", call)

    async def say(self, user_id: int, text: str, chat_id: int | None = None) -> int:
        message_id = next(self.ids)
        update = Update(update_id=1, message=make_message(user_id, text=text, message_id=message_id, chat_id=chat_id))
        await self.main.dp.feed_update(self.bot, update)
        return message_id

    async def photo(self, user_id: int, file_id: str = "evidence-1") -> None:
        """S2: nazoratchi minus uchun dalil rasmini yuboradi."""
        update = Update(update_id=1, message=make_message(user_id, photo_file_id=file_id, message_id=next(self.ids)))
        await self.main.dp.feed_update(self.bot, update)

    async def press(self, user_id: int, data: str, msg_id: int, chat_id: int | None = None) -> None:
        chat = chat_id if chat_id is not None else user_id
        target = Message(message_id=msg_id, date=datetime.now(), chat=Chat(id=chat, type="private"), text="x")
        user = TgUser(id=user_id, is_bot=False, first_name="T")
        update = Update(update_id=1, callback_query=CallbackQuery(id="1", from_user=user, chat_instance="c", data=data, message=target))
        await self.main.dp.feed_update(self.bot, update)

    def last(self, chat: int) -> dict:
        return [m for m in self.sent_log if m["chat"] == chat][-1]

    def buttons(self, entry: dict) -> dict:
        return {b.callback_data: b.text for row in entry["markup"].inline_keyboard for b in row}

    async def fsm(self, chat: int, user: int):
        return await self.main.dp.fsm.get_context(bot=self.bot, chat_id=chat, user_id=user).get_data()


@pytest.fixture
def tg(bot_dp, monkeypatch):
    main, bot = bot_dp
    return Tg(main, bot, monkeypatch)


def _setup(monkeypatch, main, ai=None) -> None:
    import employees
    from roles import set_role

    for user in (NAZ, NAZ2):
        set_role(user, "nazoratchi", set_by=FOUNDER_ID)
    employees.submit_profile(
        EMP, {"familiya": "Valiyev", "ism": "Ali", "branch": RECRUITING_BRANCH_NAMES[0], "role_key": "kassir", "contacts": []}
    )
    employees.approve_profile(EMP, approved_by=FOUNDER_ID)
    discipline.add_rule(RULE, "Telefon ishlatdi", "Ish vaqtida telefon ishlatish taqiqlanadi", created_by=FOUNDER_ID)
    discipline.set_rule_penalty_amount(RULE, 30, updated_by=FOUNDER_ID)

    async def fake_create(**kwargs):
        text = json.dumps(ai) if ai is not None else "[{\"id\": %d}]" % RULE
        return SimpleNamespace(output_text=text)

    monkeypatch.setattr(main.openai_client.responses, "create", fake_create)


def _bank() -> int:
    return discipline.get_salary(EMP)["bonus_bank"]


async def _to_prompt(tg: Tg, user: int = NAZ, card: int = CARD) -> None:
    await tg.press(user, f"nzr_penalty:{EMP}", card, chat_id=user)
    await tg.press(user, f"nzr_penalty_other:{EMP}", card, chat_id=user)


# ----------------------------------------------------------- nazoratchi --


async def test_old_messages_deleted_only_after_new_screen_is_shown(tg, monkeypatch):
    _setup(monkeypatch, tg.main)
    await _to_prompt(tg)
    assert tg.deleted == []  # savol mavjud xabarni tahrirlaydi, hech narsa o'chmaydi

    reason_id = await tg.say(NAZ, "Telefon bilan o'ynab turdi")

    screen = tg.last(NAZ)
    assert sorted(tg.deleted) == sorted([(NAZ, CARD), (NAZ, reason_id)])  # eski savol + sabab xabari
    assert (NAZ, screen["id"]) not in tg.deleted
    assert any(c.startswith("nzr_pa:") for c in tg.buttons(screen))  # bitta yakuniy ekran
    assert _bank() == 0


async def test_failed_new_screen_keeps_old_screen_and_reason_text(tg, monkeypatch):
    _setup(monkeypatch, tg.main)
    await _to_prompt(tg)
    tg.fail_send = lambda m: m.chat_id == NAZ and m.reply_markup is not None

    await tg.say(NAZ, "Telefon bilan o'ynab turdi")

    assert tg.deleted == []
    assert (await tg.fsm(NAZ, NAZ))["penalty_other_text"] == "Telefon bilan o'ynab turdi"
    assert (await tg.fsm(NAZ, NAZ))["cat_confirm"] is None  # qo'llash mumkin bo'lgan tasdiq qolmaydi


async def test_cleanup_failure_does_not_break_the_flow(tg, monkeypatch):
    _setup(monkeypatch, tg.main)
    tg.fail_delete = True
    await _to_prompt(tg)
    await tg.say(NAZ, "Telefon bilan o'ynab turdi")
    screen = tg.last(NAZ)

    await tg.press(NAZ, next(c for c in tg.buttons(screen) if c.startswith("nzr_pa:")), screen["id"], chat_id=NAZ)
    assert _bank() == 0  # S2: rasm kelmaguncha minus yozilmaydi
    await tg.photo(NAZ)

    assert _bank() == -30


async def test_other_chats_dialogs_and_workflows_are_never_touched(tg, monkeypatch):
    _setup(monkeypatch, tg.main)
    bystander = Message(message_id=777, date=datetime.now(), chat=Chat(id=NAZ2, type="private"), text="b")
    dialog_cleanup.track(dialog_cleanup.minus_key(NAZ2, "othr"), bystander)           # boshqa nazoratchi dialogi
    dialog_cleanup.track(dialog_cleanup.minus_key(NAZ, "olddlg"), Message(message_id=778, date=datetime.now(), chat=Chat(id=NAZ, type="private"), text="c"))
    await _to_prompt(tg)
    await tg.say(NAZ, "Telefon bilan o'ynab turdi")
    screen = tg.last(NAZ)
    await tg.press(NAZ, next(c for c in tg.buttons(screen) if c.startswith("nzr_pa:")), screen["id"], chat_id=NAZ)
    await tg.photo(NAZ)

    assert (NAZ2, 777) not in tg.deleted and (NAZ, 778) not in tg.deleted
    assert all(chat == NAZ for chat, _ in tg.deleted)
    assert bot_messages.pop_messages(dialog_cleanup.WORKFLOW, dialog_cleanup.minus_key(NAZ2, "othr")) != []


async def test_final_result_stays_single_confirmation_kept_and_stale_press_is_harmless(tg, monkeypatch):
    _setup(monkeypatch, tg.main)
    await _to_prompt(tg)
    await tg.say(NAZ, "Telefon bilan o'ynab turdi")
    screen = tg.last(NAZ)
    apply_data = next(c for c in tg.buttons(screen) if c.startswith("nzr_pa:"))
    assert "Aniqlashtiring" not in screen["text"] and _bank() == 0  # aniq holat: bitta ekran, oldin minus yo'q
    deleted_before = list(tg.deleted)

    await tg.press(NAZ, apply_data, screen["id"], chat_id=NAZ)
    await tg.press(NAZ, apply_data, screen["id"], chat_id=NAZ)  # takroriy bosish
    await tg.photo(NAZ)
    await tg.photo(NAZ)  # S2: takroriy rasm ikkinchi minus yaratmaydi

    assert _bank() == -30
    assert any(m["chat"] == NAZ and "qayd etildi" in m["text"] for m in tg.sent_log)  # natija xabari ko'rsatilgan
    assert (NAZ, screen["id"]) not in tg.deleted and tg.deleted == deleted_before  # natija qoladi
    assert discipline.list_appealable_penalties(EMP)  # minus bazada saqlangan


async def test_cancel_ends_the_dialog_and_old_confirmation_is_dead(tg, monkeypatch):
    _setup(monkeypatch, tg.main)
    await _to_prompt(tg)
    await tg.say(NAZ, "Telefon bilan o'ynab turdi")
    screen = tg.last(NAZ)
    apply_data = next(c for c in tg.buttons(screen) if c.startswith("nzr_pa:"))

    await tg.press(NAZ, f"nzr_penalty:{EMP}", screen["id"], chat_id=NAZ)  # bekor qilish
    await tg.press(NAZ, apply_data, screen["id"], chat_id=NAZ)

    assert _bank() == 0
    assert (NAZ, screen["id"]) not in tg.deleted  # bekor qilingan ekran menyuga aylandi, o'chmaydi


async def test_asoschiga_route_keeps_result_and_cleans_helper_messages(tg, monkeypatch):
    _setup(monkeypatch, tg.main, ai=[{"id": 99999}])
    await _to_prompt(tg)
    reason_id = await tg.say(NAZ, "Aloqasiz holat")
    screen = tg.last(NAZ)
    assert (NAZ, CARD) in tg.deleted and (NAZ, reason_id) in tg.deleted

    await tg.press(NAZ, f"nzr_px:{EMP}", screen["id"], chat_id=NAZ)

    assert _bank() == 0
    assert any(e[1] == screen["id"] and "Asoschi" in e[2] for e in tg.edits)
    assert (NAZ, screen["id"]) not in tg.deleted
    assert any(m["chat"] == FOUNDER_ID and "Aloqasiz holat" in m["text"] for m in tg.sent_log)


# --------------------------------------------------------------- e'tiroz --


async def _penalty_with_notice(tg: Tg, monkeypatch) -> tuple[int, int]:
    """Minus qo'yiladi; xodimga ketgan xabar (e'tiroz tugmasi bilan) qaytariladi: (penalty_id, notice_message_id)."""
    _setup(monkeypatch, tg.main)

    async def brief(**kwargs):
        return SimpleNamespace(output_text="Tavsiya: ko'rib chiqilsin.")

    penalty = discipline.apply_penalty(EMP, NAZ, "2026-10-19", 30, RULE, "izoh", None)
    notice_id = next(tg.ids)
    return penalty["penalty_id"], notice_id


def _ai_brief(monkeypatch, main) -> None:
    async def fake_create(**kwargs):
        return SimpleNamespace(output_text="Tavsiya: ko'rib chiqilsin.")

    monkeypatch.setattr(main.openai_client.responses, "create", fake_create)


async def test_employee_appeal_cleans_prompt_and_reason_keeps_result_and_founder_card(tg, monkeypatch):
    penalty_id, notice = await _penalty_with_notice(tg, monkeypatch)
    _ai_brief(monkeypatch, tg.main)
    seen_reason = []
    tg.on_delete = lambda: seen_reason.append(discipline.get_penalty(penalty_id)["appeal_reason"])

    await tg.press(EMP, f"nzr_appeal:{penalty_id}", notice)
    prompt = tg.last(EMP)
    assert tg.markup_removed == [] and tg.deleted == []  # tugma e'tiroz yuborilgunga qadar saqlanadi
    reason_id = await tg.say(EMP, "Men telefon ishlatmadim")

    assert seen_reason and all(r == "Men telefon ishlatmadim" for r in seen_reason)  # o'chirishdan oldin bazada
    assert sorted(tg.deleted) == sorted([(EMP, prompt["id"]), (EMP, reason_id)])
    assert (EMP, notice) in tg.markup_removed  # eski tugma yangi e'tiroz yaratmaydi
    final = [m for m in tg.sent_log if m["chat"] == EMP][-1]
    assert (EMP, final["id"]) not in tg.deleted  # "yuborildi" natijasi qoladi
    assert any(e[1] == final["id"] and "rahbarga yuborildi" in e[2] for e in tg.edits)
    card = tg.last(FOUNDER_ID)
    assert "Men telefon ishlatmadim" in card["text"] and any(c.startswith("bos:decide:") for c in tg.buttons(card))
    assert all(chat != FOUNDER_ID for chat, _ in tg.deleted)  # hal bo'lmagan Founder kartasi saqlanadi
    assert discipline.get_penalty(penalty_id)["appeal_status"] == discipline.APPEAL_PENDING


async def test_old_or_repeated_appeal_button_creates_no_second_appeal(tg, monkeypatch):
    penalty_id, notice = await _penalty_with_notice(tg, monkeypatch)
    _ai_brief(monkeypatch, tg.main)
    await tg.press(EMP, f"nzr_appeal:{penalty_id}", notice)
    await tg.say(EMP, "Birinchi sabab")
    founder_cards = len([m for m in tg.sent_log if m["chat"] == FOUNDER_ID])
    sent_before = len(tg.sent_log)

    await tg.press(EMP, f"nzr_appeal:{penalty_id}", notice)  # eski tugma
    await tg.say(EMP, "Ikkinchi sabab")                        # FSM holati ochilmagan -> e'tiborsiz

    assert len([m for m in tg.sent_log if m["chat"] == FOUNDER_ID]) == founder_cards == 1
    assert discipline.get_penalty(penalty_id)["appeal_reason"] == "Birinchi sabab"
    assert len(tg.sent_log) == sent_before  # yangi savol ham yuborilmadi


async def test_other_employee_cannot_use_someone_elses_appeal_button(tg, monkeypatch):
    penalty_id, notice = await _penalty_with_notice(tg, monkeypatch)
    _ai_brief(monkeypatch, tg.main)

    await tg.press(NAZ2, f"nzr_appeal:{penalty_id}", notice, chat_id=NAZ2)

    assert discipline.get_penalty(penalty_id)["appeal_status"] == discipline.APPEAL_NONE
    assert [m for m in tg.sent_log if m["chat"] == NAZ2] == []


async def test_founder_decision_updates_card_removes_buttons_and_stale_press_is_noop(tg, monkeypatch):
    penalty_id, notice = await _penalty_with_notice(tg, monkeypatch)
    _ai_brief(monkeypatch, tg.main)
    await tg.press(EMP, f"nzr_appeal:{penalty_id}", notice)
    await tg.say(EMP, "Men telefon ishlatmadim")
    card = tg.last(FOUNDER_ID)
    approve = f"bos:decide:{penalty_id}:{discipline.DECISION_APPROVED}"
    bank_before = _bank()

    await tg.press(FOUNDER_ID, approve, card["id"], chat_id=FOUNDER_ID)
    await tg.press(FOUNDER_ID, approve, card["id"], chat_id=FOUNDER_ID)  # takroriy bosish
    await tg.press(FOUNDER_ID, f"bos:decide:{penalty_id}:{discipline.DECISION_REJECTED}", card["id"], chat_id=FOUNDER_ID)

    assert _bank() == bank_before + 30  # ball faqat bir marta qaytdi
    assert any(e[1] == card["id"] and "qondirildi" in e[2] for e in tg.edits)  # karta qaror bilan yangilandi
    assert (FOUNDER_ID, card["id"]) in tg.markup_removed or any(e[1] == card["id"] for e in tg.edits)
    assert discipline.get_penalty(penalty_id)["appeal_decision"] == discipline.DECISION_APPROVED
    result = [m for m in tg.sent_log if m["chat"] == EMP and "Apellyatsiya natijasi" in m["text"]]
    assert len(result) == 1  # xodimga qaror xabari ham bitta
    assert all(chat != FOUNDER_ID for chat, _ in tg.deleted)


async def test_founder_send_failure_keeps_employee_messages(tg, monkeypatch):
    penalty_id, notice = await _penalty_with_notice(tg, monkeypatch)
    _ai_brief(monkeypatch, tg.main)
    tg.fail_send = lambda m: m.chat_id == FOUNDER_ID
    await tg.press(EMP, f"nzr_appeal:{penalty_id}", notice)

    await tg.say(EMP, "Men telefon ishlatmadim")

    assert tg.deleted == []  # Founderga yetmagan: hech narsa tozalanmaydi
    assert discipline.get_penalty(penalty_id)["appeal_reason"] == "Men telefon ishlatmadim"


async def test_appeal_through_apellyatsiya_command_edits_the_list_message(tg, monkeypatch):
    penalty_id, _ = await _penalty_with_notice(tg, monkeypatch)
    _ai_brief(monkeypatch, tg.main)
    from roles import set_role

    set_role(EMP, "kassir", set_by=FOUNDER_ID)
    listing = await tg.say(EMP, "/apellyatsiya")
    menu = tg.last(EMP)

    await tg.press(EMP, f"bos:appeal:{penalty_id}", menu["id"])
    reason_id = await tg.say(EMP, "Men telefon ishlatmadim")

    assert any(e[1] == menu["id"] and "Sababingizni" in e[2] for e in tg.edits)  # ro'yxat xabari savolga aylandi
    assert (EMP, menu["id"]) in tg.deleted and (EMP, reason_id) in tg.deleted
    assert discipline.get_penalty(penalty_id)["appeal_status"] == discipline.APPEAL_PENDING
    assert listing != menu["id"]
