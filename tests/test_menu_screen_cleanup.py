"""Shaxsiy chatda asosiy menyu ekranlarini tozalash (``services/menu_screens``). Telegram MOCK, lekin HAQIQIY
``bot.session.middleware`` zanjiri orqali (production bilan bir xil ulanish). Vaqtincha lokal DB."""

import asyncio
import itertools
from datetime import datetime

import pytest
from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import (
    AnswerCallbackQuery, DeleteMessage, DeleteMessages, EditMessageReplyMarkup, EditMessageText, GetMe, SendMessage, SendPhoto,
)
from aiogram.types import CallbackQuery, Chat, Message, ReplyKeyboardMarkup, Update
from aiogram.types import User as TgUser

from config import FOUNDER_ID
from repositories import bot_messages
from services import chat_cleanup, menu_screens

pytestmark = pytest.mark.anyio

NAZ = 570001
EMP = 570002
GROUP = -1001234567890


@pytest.fixture
def anyio_backend():
    return "asyncio"


class FakeSession(BaseSession):
    def __init__(self):
        super().__init__()
        self.ids = itertools.count(100)
        self.sent: list[dict] = []
        self.deleted: list[tuple[int, int]] = []
        self.batches: list[list[int]] = []
        self.markup_removed: list[tuple[int, int]] = []
        self.answers: list[str | None] = []
        self.keyboard_owners: dict[int, int] = {}
        self.fail_send = None
        self.fail_delete = None  # callable(chat, id) -> bool | True
        self.hold = None  # callable(method) -> bool: mos SendMessage `release` bo'lguncha kutadi (boshqariladigan kechikish)
        self.release = asyncio.Event()

    async def close(self):
        return None

    async def stream_content(self, *args, **kwargs):  # pragma: no cover
        yield b""

    async def make_request(self, bot, method, timeout=None):
        if isinstance(method, DeleteMessages):
            self.batches.append(list(method.message_ids))
            if self.fail_delete and (self.fail_delete is True or any(self.fail_delete(method.chat_id, mid) for mid in method.message_ids)):
                raise RuntimeError("batch delete failed")
            self.deleted.extend((method.chat_id, mid) for mid in method.message_ids)
            if self.keyboard_owners.get(method.chat_id) in method.message_ids:
                self.keyboard_owners.pop(method.chat_id)
            return True
        if isinstance(method, DeleteMessage):
            if self.fail_delete and (self.fail_delete is True or self.fail_delete(method.chat_id, method.message_id)):
                raise RuntimeError("o'chirib bo'lmadi (48 soat / allaqachon o'chgan)")
            self.deleted.append((method.chat_id, method.message_id))
            if self.keyboard_owners.get(method.chat_id) == method.message_id:
                self.keyboard_owners.pop(method.chat_id)
            return True
        if isinstance(method, EditMessageReplyMarkup):
            self.markup_removed.append((method.chat_id, method.message_id))
            return True
        if isinstance(method, AnswerCallbackQuery):
            self.answers.append(method.text)
            return True
        if isinstance(method, GetMe):
            return TgUser(id=bot.id, is_bot=True, first_name="T", username="t")
        if isinstance(method, (SendMessage, SendPhoto, EditMessageText)):
            text = getattr(method, "text", None) or getattr(method, "caption", None) or ""
            if isinstance(method, (SendMessage, SendPhoto)):
                if self.fail_send and self.fail_send(method):
                    raise RuntimeError("yuborib bo'lmadi")
                if self.hold and self.hold(method):
                    await self.release.wait()
                message_id = next(self.ids)
                self.sent.append({"chat": method.chat_id, "id": message_id, "text": text, "markup": method.reply_markup})
                if isinstance(method.reply_markup, ReplyKeyboardMarkup):
                    self.keyboard_owners[method.chat_id] = message_id
            else:
                message_id = method.message_id or 1
            return Message(
                message_id=message_id, date=datetime.now(), chat=Chat(id=method.chat_id, type="private"), text=text
            ).as_(bot)
        raise NotImplementedError(method)


class Env:
    def __init__(self, main):
        self.main = main
        self.session = FakeSession()
        self.bot = Bot(token="123456:TEST-TOKEN", session=self.session)
        self.bot.session.middleware(menu_screens.session_middleware)
        self.tap_ids = itertools.count(9000)

    async def tap(self, user_id: int, text: str, *, chat_id: int | None = None, chat_type: str = "private") -> int:
        message_id = next(self.tap_ids)
        message = Message(
            message_id=message_id, date=datetime.now(), chat=Chat(id=chat_id if chat_id is not None else user_id, type=chat_type),
            from_user=TgUser(id=user_id, is_bot=False, first_name="T"), text=text,
        )
        await self.main.dp.feed_update(self.bot, Update(update_id=1, message=message))
        return message_id

    async def callback(self, user_id: int, data: str, message_id: int) -> None:
        message = Message(message_id=message_id, date=datetime.now(), chat=Chat(id=user_id, type="private"), text="x")
        callback = CallbackQuery(id="1", from_user=TgUser(id=user_id, is_bot=False, first_name="T"), chat_instance="c", data=data, message=message)
        await self.main.dp.feed_update(self.bot, Update(update_id=1, callback_query=callback))

    def screens(self, chat: int) -> list[dict]:
        return [m for m in self.session.sent if m["chat"] == chat]

    def alive(self, chat: int) -> set[int]:
        return {m["id"] for m in self.screens(chat)} - {mid for c, mid in self.session.deleted if c == chat}


@pytest.fixture
def env(bot_dp):
    from roles import set_role

    main, _ = bot_dp
    set_role(NAZ, "nazoratchi", set_by=FOUNDER_ID)
    set_role(EMP, "kassir", set_by=FOUNDER_ID)
    menu_screens._latest_tap.clear()
    menu_screens._last_keyboard.clear()
    menu_screens._stale.clear()
    return Env(main)


# ------------------------------------------------------------- asosiy xulq --


@pytest.mark.parametrize(
    ("user", "taps"),
    [
        (EMP, ["⭐ Mening natijalarim", "💰 Oyligim", "🏆 Bugungi o'rnim"]),
        (NAZ, ["🧑‍💼 Nazoratchi", "⭐ Mening natijalarim", "🔙 Orqaga"]),
        (FOUNDER_ID, ["🚨 Bugungi muammolar", "🔙 Orqaga", "🚨 Bugungi muammolar"]),
    ],
)
async def test_three_consecutive_menus_leave_only_the_last_screen(env, user, taps):
    tap_ids = [await env.tap(user, text) for text in taps]

    shown = env.screens(user)
    assert len(shown) == 3
    assert env.alive(user) == {shown[-1]["id"]}  # faqat oxirgi ekran
    for tap_id in tap_ids:
        assert (user, tap_id) in env.session.deleted  # menyu tanlash matnlari ham tozalangan
    assert isinstance(shown[0]["markup"], ReplyKeyboardMarkup) or shown[0]["markup"] is None


async def test_bottom_reply_keyboard_is_never_removed(env):
    await env.tap(EMP, "⭐ Mening natijalarim")
    await env.tap(EMP, "🔙 Orqaga")

    last = env.screens(EMP)[-1]
    assert isinstance(last["markup"], ReplyKeyboardMarkup)  # asosiy menyu klaviaturasi yangi ekran bilan keladi
    assert not any(m["markup"].__class__.__name__ == "ReplyKeyboardRemove" for m in env.session.sent)


@pytest.mark.parametrize("user", [EMP, NAZ, FOUNDER_ID])
async def test_plain_read_screen_resends_keyboard_before_deleting_its_old_owner(env, user):
    await env.tap(user, "⭐ Mening natijalarim")
    old = env.screens(user)[-1]
    await env.tap(user, "💰 Oyligim")
    last = env.screens(user)[-1]
    assert (user, old["id"]) in env.session.deleted
    assert isinstance(last["markup"], ReplyKeyboardMarkup)
    assert last["markup"].keyboard and last["markup"].is_persistent
    assert env.session.keyboard_owners[user] == last["id"]
    assert env.alive(user) == {last["id"]}


async def test_start_home_and_read_screens_replace_one_another(env):
    for text in ("/start", "🏠 Asosiy menyu", "💰 Oyligim", "/start"):
        await env.tap(EMP, text)
        latest = env.screens(EMP)[-1]
        assert env.alive(EMP) == {latest["id"]}
        assert env.session.keyboard_owners[EMP] == latest["id"]


def _texts(markup) -> list[str]:
    return [button.text for row in markup.keyboard for button in row]


@pytest.mark.parametrize(
    ("user", "section", "views"),
    [
        (EMP, "⭐ Mening natijalarim", ["⭐ Yulduzlarim", "💰 Oyligim", "🏆 Bugungi o'rnim"]),
        (NAZ, "🧑‍💼 Nazoratchi", ["🏆 Bugungi natija", "🏆 Bugungi natija", "🏆 Bugungi natija"]),
    ],
)
async def test_three_screens_inside_a_section_keep_that_sections_keyboard(env, user, section, views):
    await env.tap(user, section)
    section_keyboard = _texts(env.screens(user)[-1]["markup"])
    main_menu = _texts(env.main.build_menu(user))
    assert section_keyboard != main_menu

    for text in views:
        await env.tap(user, text)
        last = env.screens(user)[-1]
        assert _texts(last["markup"]) == section_keyboard  # bo'lim klaviaturasi aynan qayta yuborildi
        assert env.session.keyboard_owners[user] == last["id"] and env.alive(user) == {last["id"]}


async def test_founder_screens_keep_the_founder_menu(env):
    for text in ("🚨 Bugungi muammolar", "🔙 Orqaga", "🚨 Bugungi muammolar"):
        await env.tap(FOUNDER_ID, text)
        last = env.screens(FOUNDER_ID)[-1]
        assert _texts(last["markup"]) == _texts(env.main.build_menu(FOUNDER_ID))
        assert env.session.keyboard_owners[FOUNDER_ID] == last["id"]


async def test_restart_with_empty_memory_falls_back_to_the_main_menu(env):
    await env.tap(EMP, "⭐ Mening natijalarim")
    menu_screens._last_keyboard.clear()  # restart: jarayon xotirasi bo'sh

    await env.tap(EMP, "💰 Oyligim")

    assert _texts(env.screens(EMP)[-1]["markup"]) == _texts(env.main.build_menu(EMP))


async def test_inline_screen_keeps_keyboard_owner_untouched_and_it_is_cleaned_after_the_next_keyboard_screen(env, monkeypatch):
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    await env.tap(EMP, "⭐ Mening natijalarim")
    owner = env.screens(EMP)[-1]["id"]
    original = Message.answer

    async def inline_answer(self, text, **kwargs):
        kwargs.setdefault("reply_markup", InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="x", callback_data="x")]]))
        return await original(self, text, **kwargs)

    monkeypatch.setattr(Message, "answer", inline_answer)
    await env.tap(EMP, "💰 Oyligim")  # inline ekran
    monkeypatch.setattr(Message, "answer", original)

    inline = env.screens(EMP)[-1]
    assert (EMP, owner) not in env.session.deleted and (EMP, owner) not in env.session.markup_removed
    assert owner not in menu_screens._stale.get(EMP, ()) and env.session.keyboard_owners[EMP] == owner
    assert inline["id"] in env.alive(EMP) and owner in env.alive(EMP)  # inline tugmalari ham, egasi ham saqlangan

    await env.tap(EMP, "🏆 Bugungi o'rnim")  # keyingi reply-klaviaturali ekran

    last = env.screens(EMP)[-1]
    assert env.session.keyboard_owners[EMP] == last["id"]
    assert (EMP, owner) in env.session.deleted and (EMP, inline["id"]) in env.session.deleted  # eski ega endi tozalandi


async def test_send_failure_keeps_old_screen_and_keyboard_memory(env):
    await env.tap(EMP, "⭐ Mening natijalarim")
    owner = env.screens(EMP)[-1]["id"]
    env.session.fail_send = lambda m: m.chat_id == EMP

    await env.tap(EMP, "💰 Oyligim")

    assert env.session.keyboard_owners[EMP] == owner and menu_screens._last_keyboard[EMP].message_id == owner
    assert (EMP, owner) not in env.session.deleted


async def test_late_request_never_deletes_the_current_keyboard_owner(env):
    chat = EMP

    def screen(message_id):
        return Message(message_id=message_id, date=datetime.now(), chat=Chat(id=chat, type="private"), text="e")

    await menu_screens._commit(env.bot, menu_screens._Capture(chat, 20, [screen(201)], keyboard_ids={201}))
    menu_screens._last_keyboard[chat] = menu_screens._KeyboardRef(ReplyKeyboardMarkup(keyboard=[]), 101, True)  # kech javob egasi
    await menu_screens._commit(env.bot, menu_screens._Capture(chat, 10, [screen(101)], keyboard_ids={101}))

    assert (chat, 101) not in env.session.deleted and (chat, 201) not in env.session.deleted
    assert {r["message_id"] for r in bot_messages.pop_messages(menu_screens.WORKFLOW, menu_screens.screen_key(chat))} >= {101, 201}


async def test_flow_group_denial_and_background_messages_are_not_touched(env):
    # oqim klaviaturasi almashtirilmaydi; keyingi oddiy ekran esa asosiy menyuga qaytadi (oqim klaviaturasi menyu emas)
    await env.tap(FOUNDER_ID, "👤 Xodim qo'shish")
    flow_kb = env.screens(FOUNDER_ID)[-1]["markup"]
    assert _texts(flow_kb) != _texts(env.main.build_menu(FOUNDER_ID))
    await env.tap(FOUNDER_ID, "🚨 Bugungi muammolar")
    assert _texts(env.screens(FOUNDER_ID)[-1]["markup"]) == _texts(env.main.build_menu(FOUNDER_ID))

    # fon bildirishnomasi (capture yo'q) va guruh: reply_markup qo'shilmaydi
    await env.bot.send_message(EMP, "fon xabari")
    await env.tap(EMP, "⭐ Mening natijalarim", chat_id=GROUP, chat_type="supergroup")
    assert env.session.sent[[m["text"] for m in env.session.sent].index("fon xabari")]["markup"] is None
    assert GROUP not in menu_screens._last_keyboard  # guruh klaviatura hisobiga kirmaydi


async def test_send_failure_keeps_previous_screen_and_tap_text(env):
    first = await env.tap(EMP, "⭐ Mening natijalarim")
    env.session.fail_send = lambda m: m.chat_id == EMP
    await env.tap(EMP, "💰 Oyligim")

    assert env.session.deleted == [(EMP, first)]  # faqat birinchi ekranning O'Z tugma matni; eski ekran saqlangan
    assert env.alive(EMP) == {env.screens(EMP)[0]["id"]}


async def test_delete_failures_never_break_the_flow_and_stale_inline_buttons_are_rejected(env):
    await env.tap(EMP, "⭐ Mening natijalarim")
    old = env.screens(EMP)[0]["id"]
    env.session.fail_delete = True

    await env.tap(EMP, "💰 Oyligim")  # o'chirish xatolari hammasi

    assert len(env.screens(EMP)) == 2 and (EMP, old) in env.session.markup_removed  # tugmalar olinishga urinildi
    env.session.answers.clear()
    sent_before = len(env.session.sent)
    await env.callback(EMP, "nzr_ack:1", old)  # eskirgan menyu ekranining tugmasi
    assert env.session.answers == [menu_screens.STALE_ANSWER]
    assert len(env.session.sent) == sent_before  # hech narsa bajarilmadi


async def test_group_chat_is_never_tracked_or_cleaned(env):
    await env.tap(EMP, "⭐ Mening natijalarim", chat_id=GROUP, chat_type="supergroup")
    await env.tap(EMP, "💰 Oyligim", chat_id=GROUP, chat_type="supergroup")

    assert env.session.deleted == []
    assert bot_messages.pop_messages(menu_screens.WORKFLOW, menu_screens.screen_key(GROUP)) == []


async def test_other_chats_other_workflows_and_non_menu_messages_are_untouched(env):
    # boshqa workflow (kassa) kuzatuvi va boshqa foydalanuvchi ekrani
    foreign = Message(message_id=4242, date=datetime.now(), chat=Chat(id=EMP, type="private"), text="smena")
    chat_cleanup.track("cash_shift_close", "77", foreign)
    await env.tap(NAZ, "🧑‍💼 Nazoratchi")
    await env.tap(EMP, "⭐ Mening natijalarim")
    await env.tap(EMP, "💰 Oyligim")
    await env.bot.send_message(EMP, "⭐ Baho: 3 (shaxsiy baho xabari)")  # menyu handleridan tashqari xabar
    await env.tap(EMP, "🏆 Bugungi o'rnim")

    assert (EMP, 4242) not in env.session.deleted
    assert bot_messages.pop_messages("cash_shift_close", "77") != []
    assert {m["id"] for m in env.screens(NAZ)} == env.alive(NAZ)  # NAZ ekrani saqlangan
    grade = next(m for m in env.session.sent if "shaxsiy baho" in (m["text"] or ""))
    assert grade["id"] in env.alive(EMP)


async def test_cash_flow_tap_neither_cleans_nor_is_tracked(env):
    await env.tap(EMP, "⭐ Mening natijalarim")
    screen = env.screens(EMP)[0]["id"]

    cash_tap = await env.tap(EMP, "🟢 Smenani boshlash")  # kassa oqimi: menyu cleanup'iga umuman kirmaydi

    assert screen in env.alive(EMP) and (EMP, cash_tap) not in env.session.deleted
    assert [r["message_id"] for r in bot_messages.pop_messages(menu_screens.WORKFLOW, menu_screens.screen_key(EMP))] == [screen]
    assert bot_messages.pop_messages(menu_screens.WORKFLOW, menu_screens.flow_key(EMP)) == []


async def test_free_text_photo_and_survey_answers_are_not_deleted_as_menu_text(env):
    first = await env.tap(EMP, "⭐ Mening natijalarim")
    for text in ("salom", "25.10.2026", "Ismim Ali, 25 yosh", "💰 Oyligim?"):
        await env.tap(EMP, text)

    assert env.session.deleted == [(EMP, first)]  # erkin matnlar o'chmagan


async def test_existing_fsm_escape_behaviour_is_kept_and_abandoned_question_is_cleaned(env):
    fsm = env.main.dp.fsm.get_context(bot=env.bot, chat_id=FOUNDER_ID, user_id=FOUNDER_ID)
    problems_tap = await env.tap(FOUNDER_ID, "🚨 Bugungi muammolar")
    add_tap = await env.tap(FOUNDER_ID, "👤 Xodim qo'shish")  # ko'p qadamli oqim boshlandi
    assert await fsm.get_state() is not None
    problems_screen, question = env.screens(FOUNDER_ID)
    assert "Kim bo'lib ishlaydi?" in question["text"]
    assert (FOUNDER_ID, problems_screen["id"]) in env.session.deleted  # oldingi oddiy ekran yangi savoldan keyin tozalandi
    assert (FOUNDER_ID, question["id"]) not in env.session.deleted      # savol faol oqimniki — hali turadi

    other_tap = await env.tap(FOUNDER_ID, "🚨 Bugungi muammolar")  # boshqa asosiy menyu

    assert await fsm.get_state() is None  # mavjud xatti-harakat: holat tozalandi
    new_screen = env.screens(FOUNDER_ID)[-1]
    assert (FOUNDER_ID, question["id"]) in env.session.deleted  # tashlab ketilgan savol tozalandi
    for tap_id in (problems_tap, add_tap, other_tap):
        assert (FOUNDER_ID, tap_id) in env.session.deleted
    assert env.alive(FOUNDER_ID) == {new_screen["id"]}


async def test_abandoned_flow_button_text_writes_nothing_and_undeletable_question_goes_stale(env):
    fsm = env.main.dp.fsm.get_context(bot=env.bot, chat_id=FOUNDER_ID, user_id=FOUNDER_ID)
    await env.tap(FOUNDER_ID, "👤 Xodim qo'shish")
    question = env.screens(FOUNDER_ID)[-1]
    env.session.fail_delete = lambda c, m: m == question["id"]
    await env.tap(FOUNDER_ID, "🚨 Bugungi muammolar")
    env.session.fail_delete = None
    assert await fsm.get_state() is None and (FOUNDER_ID, question["id"]) in env.session.markup_removed

    sent_before = len(env.session.sent)
    role_name = next(iter(env.main._ROLE_NAME_TO_KEY))
    await env.tap(FOUNDER_ID, role_name)  # eski oqim tugmasi matni: yangi bo'lim emas, holat yo'q
    env.session.answers.clear()
    await env.callback(FOUNDER_ID, "anything", question["id"])  # eskirgan savol tugmasi

    assert len(env.session.sent) == sent_before and await fsm.get_state() is None
    assert env.session.answers == [menu_screens.STALE_ANSWER]


async def test_flow_followup_questions_are_cleaned_but_user_answers_are_not(env):
    role_name = next(
        name for name, key in env.main._ROLE_NAME_TO_KEY.items() if not env.main.is_single_slot_role(key)
    )
    await env.tap(FOUNDER_ID, "👤 Xodim qo'shish")
    answer = await env.tap(FOUNDER_ID, role_name)  # erkin javob (tugma matni oqim ichida)
    first, second = env.screens(FOUNDER_ID)[-2:]
    assert "Qaysi do'konda" in second["text"]

    await env.tap(FOUNDER_ID, "🚨 Bugungi muammolar")

    assert {(FOUNDER_ID, first["id"]), (FOUNDER_ID, second["id"])} <= set(env.session.deleted)
    assert (FOUNDER_ID, answer) not in env.session.deleted  # anketa javobi menyu matni deb o'chirilmaydi


async def test_finished_flow_result_is_not_tracked_for_cleanup(env):
    # yakuniy natija (taklif havolasi) oqim savoli emas: keyingi menyu uni o'chirmaydi
    single = next((n for n, k in env.main._ROLE_NAME_TO_KEY.items() if env.main.is_single_slot_role(k)), None)
    if single is None:
        pytest.skip("bir slotli rol yo'q")
    await env.tap(FOUNDER_ID, "👤 Xodim qo'shish")
    await env.tap(FOUNDER_ID, single)
    result = env.screens(FOUNDER_ID)[-1]

    await env.tap(FOUNDER_ID, "🚨 Bugungi muammolar")

    assert (FOUNDER_ID, result["id"]) not in env.session.deleted


async def test_flow_question_send_failure_keeps_previous_screen(env):
    await env.tap(FOUNDER_ID, "🚨 Bugungi muammolar")
    screen = env.screens(FOUNDER_ID)[0]
    env.session.fail_send = lambda m: m.chat_id == FOUNDER_ID

    await env.tap(FOUNDER_ID, "👤 Xodim qo'shish")

    assert (FOUNDER_ID, screen["id"]) not in env.session.deleted


def _enroll_with_rules(employee_id: int) -> None:
    import employees
    from services import discipline, rule_learning

    employees.submit_profile(employee_id, {"familiya": "Karimov", "ism": "Vali", "branch": "Filial-1", "role_key": "kassir", "contacts": []})
    employees.approve_profile(employee_id, approved_by=FOUNDER_ID)
    for number in (1, 2):
        discipline.add_rule(number, f"Band {number}", f"Matn {number}", created_by=FOUNDER_ID)
    rule_learning.enroll(employee_id)


async def test_opening_rules_cleans_previous_menu_but_keeps_the_new_rule_card_untracked(env):
    _enroll_with_rules(EMP)
    # Reply-klaviaturali oddiy ekran kerak: "💰 Oyligim" endi inline tugmali (📅 O'tgan oy), shuning uchun boshqasi.
    first = await env.tap(EMP, "🏆 Bugungi o'rnim")
    salary_screen = env.screens(EMP)[0]

    rules_tap = await env.tap(EMP, "📋 Nizomlar")

    card = env.screens(EMP)[-1]
    assert "1-nizom" in card["text"]
    # Nizom kartasi reply-klaviaturasiz: oxirgi klaviatura egasi (oylik ekrani) o'chirilmaydi — menyu klaviaturasi yo'qolmasin.
    assert (EMP, salary_screen["id"]) not in env.session.deleted and env.session.keyboard_owners[EMP] == salary_screen["id"]
    assert (EMP, first) in env.session.deleted and (EMP, rules_tap) in env.session.deleted  # menyu matnlari ham
    assert (EMP, card["id"]) not in env.session.deleted
    tracked = [r["message_id"] for r in bot_messages.pop_messages(menu_screens.WORKFLOW, menu_screens.screen_key(EMP))]
    assert tracked == [salary_screen["id"]]  # faqat klaviatura egasi kuzatuvda; nizom kartasi kuzatilmagan
    bot_messages.log_message(menu_screens.WORKFLOW, menu_screens.screen_key(EMP), EMP, salary_screen["id"])

    await env.tap(EMP, "🏆 Bugungi o'rnim")  # keyingi menyu
    await env.tap(EMP, "⭐ Mening natijalarim")

    assert (EMP, card["id"]) not in env.session.deleted  # faol nizom kartasi saqlanadi
    assert card["markup"] is not None and any(
        b.callback_data for row in card["markup"].inline_keyboard for b in row
    )  # tasdiq tugmalari o'zida


async def test_rules_screen_send_failure_keeps_previous_menu(env):
    _enroll_with_rules(EMP)
    await env.tap(EMP, "💰 Oyligim")
    salary_screen = env.screens(EMP)[0]
    env.session.fail_send = lambda m: m.chat_id == EMP

    await env.tap(EMP, "📋 Nizomlar")

    assert (EMP, salary_screen["id"]) not in env.session.deleted
    env.session.fail_send = None
    assert salary_screen["id"] in env.alive(EMP)


async def test_late_finishing_older_request_does_not_delete_the_newest_screen(env):
    chat = EMP

    def screen(message_id):
        return Message(message_id=message_id, date=datetime.now(), chat=Chat(id=chat, type="private"), text="e")

    newer = menu_screens._Capture(chat, 20, [screen(201)])
    older = menu_screens._Capture(chat, 10, [screen(101), screen(102)])
    await menu_screens._commit(env.bot, newer)
    await menu_screens._commit(env.bot, older)  # kech tugagan eski so'rov

    assert {(chat, 101), (chat, 102), (chat, 10)} <= set(env.session.deleted)
    assert (chat, 201) not in env.session.deleted
    assert [r["message_id"] for r in bot_messages.pop_messages(menu_screens.WORKFLOW, menu_screens.screen_key(chat))] == [201]


async def test_multi_message_screen_is_kept_whole_and_replaced_whole(env):
    chat = EMP

    def screen(message_id):
        return Message(message_id=message_id, date=datetime.now(), chat=Chat(id=chat, type="private"), text="e")

    await menu_screens._commit(env.bot, menu_screens._Capture(chat, 10, [screen(101), screen(102), screen(103)]))
    assert not any(c == chat and m in (101, 102, 103) for c, m in env.session.deleted)  # barcha qismlari saqlangan

    await menu_screens._commit(env.bot, menu_screens._Capture(chat, 11, [screen(201)], keyboard_ids={201}))
    assert {(chat, 101), (chat, 102), (chat, 103)} <= set(env.session.deleted)


async def test_tap_text_deletion_failure_is_retried_on_next_switch(env):
    chat = EMP
    env.session.fail_delete = lambda c, m: m == 9500

    def screen(message_id):
        return Message(message_id=message_id, date=datetime.now(), chat=Chat(id=chat, type="private"), text="e")

    await menu_screens._commit(env.bot, menu_screens._Capture(chat, 9500, [screen(101)], keyboard_ids={101}))
    env.session.fail_delete = None
    await menu_screens._commit(env.bot, menu_screens._Capture(chat, 9501, [screen(102)], keyboard_ids={102}))

    assert (chat, 9500) in env.session.deleted and (chat, 101) in env.session.deleted


# ---------------------------------------- kech tugagan "keep" (faol nizom kartasi) --


async def test_late_keep_reply_after_newer_screen_is_untouched_through_real_middleware_chain(env, monkeypatch):
    from aiogram.fsm.storage.memory import DisabledEventIsolation

    # Productionda ``SimpleEventIsolation`` bitta foydalanuvchi yangilanishlarini ketma-ket bajaradi; bu test shu
    # himoyasiz (parallel) holatni — himoya qatlami sifatida — boshqariladigan kechikish bilan sinaydi.
    monkeypatch.setattr(env.main.dp.fsm, "events_isolation", DisabledEventIsolation())
    _enroll_with_rules(EMP)
    env.session.hold = lambda m: m.chat_id == EMP and "1-nizom" in (m.text or "")  # nizom kartasi kechikadi

    rules_task = asyncio.create_task(env.tap(EMP, "📋 Nizomlar"))
    await asyncio.sleep(0)  # so'rov handlerga kirib, yuborishda kutib turadi
    await asyncio.sleep(0)
    salary_tap = await env.tap(EMP, "💰 Oyligim")  # keyingi bosish oldin tugaydi
    salary_screen = env.screens(EMP)[-1]
    latest_before = dict(menu_screens._latest_tap)
    tracked_before = [r["message_id"] for r in bot_messages.pop_messages(menu_screens.WORKFLOW, menu_screens.screen_key(EMP))]
    for message_id in tracked_before:  # pop yozuvlarni olib tashlaydi — qayta qo'yamiz
        bot_messages.log_message(menu_screens.WORKFLOW, menu_screens.screen_key(EMP), EMP, message_id)
    deleted_before = list(env.session.deleted)
    markup_before = list(env.session.markup_removed)

    env.session.release.set()
    rules_tap = await rules_task

    card = next(m for m in env.screens(EMP) if "1-nizom" in (m["text"] or ""))
    assert card["id"] not in {mid for _, mid in env.session.deleted}  # faol nizom kartasi o'chmagan
    assert (EMP, card["id"]) not in env.session.markup_removed  # tugmalari olinmagan
    assert env.session.markup_removed == markup_before and card["markup"] is not None
    assert menu_screens._latest_tap == latest_before  # eski so'rov _latest_tap'ni qaytarmaydi
    assert salary_screen["id"] in env.alive(EMP) and salary_tap > 0  # yangiroq ekran saqlangan
    assert [r["message_id"] for r in bot_messages.pop_messages(menu_screens.WORKFLOW, menu_screens.screen_key(EMP))] == tracked_before
    assert card["id"] not in tracked_before
    assert bot_messages.pop_messages(menu_screens.WORKFLOW, menu_screens.flow_key(EMP)) == []  # kartalar kuzatuvga kirmagan
    assert (EMP, rules_tap) in env.session.deleted  # faqat eski menyu tanlash matni tozalangan
    assert set(env.session.deleted) - set(deleted_before) <= {(EMP, rules_tap)}
    assert card["id"] not in menu_screens._stale.get(EMP, ())  # stale deb belgilanmagan


async def test_late_keep_reply_with_several_parts_keeps_every_part(env):
    chat = EMP

    def part(message_id):
        return Message(message_id=message_id, date=datetime.now(), chat=Chat(id=chat, type="private"), text="karta")

    await menu_screens._commit(env.bot, menu_screens._Capture(chat, 20, [part(201)]))
    await menu_screens._commit(env.bot, menu_screens._Capture(chat, 10, [part(101), part(102), part(103)], kind="keep"))

    assert {(chat, 101), (chat, 102), (chat, 103)}.isdisjoint(env.session.deleted)
    assert env.session.markup_removed == [] and menu_screens._stale.get(chat) is None
    assert menu_screens._latest_tap[chat] == 20
    assert [r["message_id"] for r in bot_messages.pop_messages(menu_screens.WORKFLOW, menu_screens.screen_key(chat))] == [201]
    assert (chat, 10) in env.session.deleted  # faqat eski tugma matni


async def test_late_plain_screen_is_still_cleaned_and_newer_one_stays(env):
    chat = EMP

    def screen(message_id):
        return Message(message_id=message_id, date=datetime.now(), chat=Chat(id=chat, type="private"), text="e")

    await menu_screens._commit(env.bot, menu_screens._Capture(chat, 20, [screen(201)]))
    await menu_screens._commit(env.bot, menu_screens._Capture(chat, 10, [screen(101)], kind="screen"))

    assert {(chat, 101), (chat, 10)} <= set(env.session.deleted) and (chat, 201) not in env.session.deleted


async def test_sequential_salary_then_rules_still_cleans_salary_and_keeps_card(env):
    _enroll_with_rules(EMP)
    await env.tap(EMP, "💰 Oyligim")
    salary = env.screens(EMP)[0]

    await env.tap(EMP, "📋 Nizomlar")
    card = env.screens(EMP)[-1]
    await env.tap(EMP, "🏆 Bugungi o'rnim")

    assert (EMP, salary["id"]) in env.session.deleted and (EMP, card["id"]) not in env.session.deleted


# ------------------------- restartdan keyin "Nizomlar": klaviatura egasi noma'lum --


def _tracked(chat: int) -> list[int]:
    rows = bot_messages.pop_messages(menu_screens.WORKFLOW, menu_screens.screen_key(chat))
    ids = [r["message_id"] for r in rows]
    for message_id in ids:  # pop yozuvlarni olib tashlaydi — qayta qo'yamiz
        bot_messages.log_message(menu_screens.WORKFLOW, menu_screens.screen_key(chat), chat, message_id)
    return ids


def _restart() -> None:
    menu_screens._last_keyboard.clear()
    menu_screens._latest_tap.clear()  # DB kuzatuvi saqlanadi


async def test_after_restart_opening_rules_keeps_unknown_keyboard_owner_until_next_keyboard_screen(env):
    _enroll_with_rules(EMP)
    await env.tap(EMP, "🏆 Bugungi o'rnim")  # reply-klaviaturali ekran ("💰 Oyligim" endi inline tugmali)
    owner = env.screens(EMP)[-1]["id"]
    assert env.session.keyboard_owners[EMP] == owner
    _restart()

    rules_tap = await env.tap(EMP, "📋 Nizomlar")

    card = env.screens(EMP)[-1]
    assert "1-nizom" in card["text"]
    assert (EMP, owner) not in env.session.deleted and (EMP, owner) not in env.session.markup_removed
    assert owner not in menu_screens._stale.get(EMP, ())
    assert owner in _tracked(EMP) and card["id"] not in _tracked(EMP)  # kuzatuvda qoldi; nizom kartasi kuzatilmagan
    assert (EMP, rules_tap) in env.session.deleted  # menyu tanlash matni mavjud xulq bo'yicha tozalandi

    await env.tap(EMP, "🏆 Bugungi o'rnim")  # oddiy reply-klaviaturali ekran

    last = env.screens(EMP)[-1]
    assert isinstance(last["markup"], ReplyKeyboardMarkup) and env.session.keyboard_owners[EMP] == last["id"]
    assert (EMP, owner) in env.session.deleted  # eski ega endi tozalandi
    assert (EMP, card["id"]) not in env.session.deleted  # faol nizom kartasi saqlangan


async def test_after_restart_rules_send_failure_keeps_old_messages_and_tracking(env):
    _enroll_with_rules(EMP)
    await env.tap(EMP, "💰 Oyligim")
    owner = env.screens(EMP)[-1]["id"]
    _restart()
    env.session.fail_send = lambda m: m.chat_id == EMP

    await env.tap(EMP, "📋 Nizomlar")

    assert (EMP, owner) not in env.session.deleted and owner in _tracked(EMP)
