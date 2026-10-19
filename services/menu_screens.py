"""Shaxsiy chatda asosiy menyu bo'limlari almashganda eski menyu ekranlari va foydalanuvchi bosgan menyu tugma
matnini xavfsiz tozalash — mavjud ``chat_cleanup`` kuzatuvi (``bot_workflow_messages``) ustida yupqa qatlam.

Ishlash: ``MenuScreenMiddleware`` faqat PRIVATE chatdagi, ANIQ ro'yxatdagi menyu tugmalari uchun ishlaydi
(``configure(screen_texts=...)``). Handler bajarilayotganda ``session_middleware`` shu chatga yuborilgan
xabarlarni yig'adi; handler muvaffaqiyatli tugab, kamida bitta yangi ekran chiqqandan KEYIN oldingi menyu
ekranlari va menyu tugma matnlari o'chiriladi. Faqat shu mexanizm qayd etgan xabarlar (workflow
``private_menu_screen``, kalit ``menu:<chat_id>``) o'chadi; boshqa workflow/kalitlarga, baho/minus, tasdiq
kartalari, hisobotlar va kassa xabarlariga tegilmaydi. Eski chat tarixi skanerlanmaydi.

O'chirish xatosi (48 soat, allaqachon o'chgan, ruxsat yo'q) oqimni to'xtatmaydi: eskirgan inline tugmalar
olib tashlanadi, bo'lmasa xabar "eskirgan" deb belgilanadi va ``StaleMenuCallbackMiddleware`` uning callback'ini
rad etadi (belgi jarayon xotirasida — qayta ishga tushganda yo'qoladi)."""

import asyncio
import logging
from collections import OrderedDict, deque
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Iterable

from aiogram import BaseMiddleware, Bot
from aiogram.methods import SendAnimation, SendAudio, SendDocument, SendMessage, SendPhoto, SendVideo, SendVoice
from aiogram.types import CallbackQuery, Message

from repositories import bot_messages as repo
from services import chat_cleanup

logger = logging.getLogger(__name__)

WORKFLOW = "private_menu_screen"
STALE_ANSWER = "Bu tugma eskirgan."
_SEND_METHODS = (SendMessage, SendPhoto, SendDocument, SendVoice, SendVideo, SendAnimation, SendAudio)
_MAX_STALE_PER_CHAT = 500
_MAX_CHATS = 5000

_screen_texts: frozenset[str] = frozenset()
_denial_texts: tuple[str, ...] = ()
_latest_tap: "OrderedDict[int, int]" = OrderedDict()
_locks: dict[int, asyncio.Lock] = {}
_stale: dict[int, deque] = {}


@dataclass
class _Capture:
    chat_id: int
    tap_message_id: int
    screens: list[Message] = field(default_factory=list)


_capture: ContextVar[_Capture | None] = ContextVar("menu_screen_capture", default=None)


def configure(screen_texts: Iterable[str], denial_texts: Iterable[str] = ()) -> None:
    global _screen_texts, _denial_texts
    _screen_texts = frozenset(screen_texts)
    _denial_texts = tuple(denial_texts)


def screen_key(chat_id: int) -> str:
    return f"menu:{chat_id}"


def _is_menu_tap(message: Message) -> bool:
    return (
        message.chat.type == "private"
        and message.from_user is not None
        and not message.from_user.is_bot
        and (message.text or "") in _screen_texts
    )


def _is_denial(text: str | None) -> bool:
    return bool(text) and any(text.startswith(denial) for denial in _denial_texts)


async def session_middleware(make_request, bot: Bot, method):
    """``bot.session.middleware(...)``: menyu bosilishi paytida shu chatga yuborilgan xabarlarni yig'adi."""
    result = await make_request(bot, method)
    capture = _capture.get()
    if capture is not None and isinstance(method, _SEND_METHODS):
        sent = getattr(result, "result", result)
        if (
            isinstance(sent, Message)
            and sent.chat.id == capture.chat_id
            and not _is_denial(getattr(method, "text", None))
        ):
            capture.screens.append(sent)
    return result


def _mark_stale(chat_id: int, message_id: int) -> None:
    marks = _stale.setdefault(chat_id, deque(maxlen=_MAX_STALE_PER_CHAT))
    marks.append(message_id)
    if len(_stale) > _MAX_CHATS:
        _stale.pop(next(iter(_stale)))


async def _remove(bot: Bot, chat_id: int, message_id: int) -> bool:
    """Xabarni o'chiradi; bo'lmasa inline tugmalarini oladi; bo'lmasa 'eskirgan' deb belgilaydi. Hech qachon yiqilmaydi."""
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
        return True
    except Exception as error:  # noqa: BLE001
        logger.info("Menyu xabarini o'chirib bo'lmadi (%s/%s): %r", chat_id, message_id, error)
    try:
        await bot.edit_message_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=None)
    except Exception as error:  # noqa: BLE001
        logger.info("Eskirgan menyu tugmalarini olib bo'lmadi (%s/%s): %r", chat_id, message_id, error)
    _mark_stale(chat_id, message_id)
    return False


async def _commit(bot: Bot, capture: _Capture) -> None:
    chat_id = capture.chat_id
    lock = _locks.setdefault(chat_id, asyncio.Lock())
    async with lock:
        new_ids = {screen.message_id for screen in capture.screens}
        if capture.tap_message_id < _latest_tap.get(chat_id, 0):
            # Kech tugagan eski so'rov: joriy (yangiroq) ekran hisobiga tegmaymiz, o'z natijasini olib tashlaymiz.
            for message_id in (*new_ids, capture.tap_message_id):
                await _remove(bot, chat_id, message_id)
            return

        key = screen_key(chat_id)
        try:
            old_rows = repo.pop_messages(WORKFLOW, key)
        except Exception as error:  # noqa: BLE001
            logger.error("Menyu ekranlari ro'yxatini olib bo'lmadi (chat=%s): %r", chat_id, error)
            old_rows = []

        for row in old_rows:
            if row["message_id"] not in new_ids and row["message_id"] != capture.tap_message_id:
                await _remove(bot, row["chat_id"], row["message_id"])  # o'chmasa eskirgan deb belgilanadi

        for screen in capture.screens:
            chat_cleanup.track(WORKFLOW, key, screen)
        # Joriy menyu tanlash matni ham o'chadi; o'chmasa keyingi almashishda qayta uriniladi.
        if not await _remove_tap(bot, chat_id, capture.tap_message_id):
            _track_id(key, chat_id, capture.tap_message_id)

        _latest_tap[chat_id] = capture.tap_message_id
        _latest_tap.move_to_end(chat_id)
        while len(_latest_tap) > _MAX_CHATS:
            _latest_tap.popitem(last=False)


async def _remove_tap(bot: Bot, chat_id: int, message_id: int) -> bool:
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
        return True
    except Exception as error:  # noqa: BLE001
        logger.info("Menyu tugma matnini o'chirib bo'lmadi (%s/%s): %r", chat_id, message_id, error)
        return False


def _track_id(key: str, chat_id: int, message_id: int) -> None:
    try:
        repo.log_message(WORKFLOW, key, chat_id, message_id)
    except Exception as error:  # noqa: BLE001
        logger.error("Menyu tugma matnini kuzatib bo'lmadi: %r", error)


class MenuScreenMiddleware(BaseMiddleware):
    """``dp.message.outer_middleware``: menyu tugmasi bosilganda (private chat, ro'yxatdagi matn) yangi ekranni
    kuzatadi va muvaffaqiyatdan keyin eski ekranlarni tozalaydi. Handler xato bersa tozalanmaydi."""

    async def __call__(self, handler, event: Message, data: dict):
        if not isinstance(event, Message) or not _is_menu_tap(event):
            return await handler(event, data)

        capture = _Capture(chat_id=event.chat.id, tap_message_id=event.message_id)
        token = _capture.set(capture)
        try:
            result = await handler(event, data)
        finally:
            _capture.reset(token)

        if capture.screens:
            try:
                await _commit(data["bot"], capture)
            except Exception as error:  # noqa: BLE001
                logger.error("Menyu tozalash xatosi (oqim davom etadi): %r", error)
        return result


class StaleMenuCallbackMiddleware(BaseMiddleware):
    """``dp.callback_query.outer_middleware``: FAQAT tozalash o'chira olmagan eski menyu ekranlari tugmalarini rad etadi."""

    async def __call__(self, handler, event: CallbackQuery, data: dict):
        message = getattr(event, "message", None)
        if (
            isinstance(event, CallbackQuery)
            and message is not None
            and message.message_id in _stale.get(message.chat.id, ())
        ):
            await event.answer(STALE_ANSWER, show_alert=False)
            return None
        return await handler(event, data)
