"""Haqiqiy tarmoqqa chiqmasdan to'liq Dispatcher orqali xabar
simulyatsiya qilish uchun yordamchi qatlam (Bot.__call__ ni almashtirib,
Telegram API so'rovlarini yozib boradi).
"""

from datetime import datetime

from aiogram import Bot
from aiogram.methods import (
    AnswerCallbackQuery,
    EditMessageReplyMarkup,
    EditMessageText,
    GetMe,
    SendMessage,
    SendPhoto,
    TelegramMethod,
)
from aiogram.types import CallbackQuery, Chat, Message, PhotoSize, Update
from aiogram.types import User as TgUser


class RecordingBot(Bot):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.sent: list[TelegramMethod] = []

    async def __call__(self, method: TelegramMethod, request_timeout: int | None = None):
        if isinstance(method, (SendMessage, SendPhoto, EditMessageText)):
            self.sent.append(method)
            return Message(
                message_id=len(self.sent),
                date=datetime.now(),
                chat=Chat(id=method.chat_id, type="private"),
                text=getattr(method, "text", None) or getattr(method, "caption", None) or "",
            ).as_(self)
        if isinstance(method, GetMe):
            return TgUser(id=self.id, is_bot=True, first_name="TestBot", username="test_bot")
        if isinstance(method, (EditMessageReplyMarkup, AnswerCallbackQuery)):
            self.sent.append(method)
            return True

        raise NotImplementedError(f"Test harness da qo'llab-quvvatlanmagan metod: {method!r}")


def make_message(
    user_id: int,
    text: str | None = None,
    photo_file_id: str | None = None,
    message_id: int = 1,
) -> Message:
    user = TgUser(id=user_id, is_bot=False, first_name="Test")
    chat = Chat(id=user_id, type="private")
    kwargs: dict = dict(message_id=message_id, date=datetime.now(), chat=chat, from_user=user)

    if photo_file_id is not None:
        kwargs["photo"] = [
            PhotoSize(file_id=photo_file_id, file_unique_id=f"u{message_id}", width=100, height=100)
        ]
    else:
        kwargs["text"] = text or ""

    return Message(**kwargs)


async def send(dp, bot: RecordingBot, user_id: int, text: str | None = None, photo_file_id: str | None = None):
    bot.sent = []
    message = make_message(user_id, text=text, photo_file_id=photo_file_id, message_id=len(bot.sent) + 1)
    update = Update(update_id=1, message=message)
    await dp.feed_update(bot, update)
    return bot.sent


async def send_callback(
    dp, bot: RecordingBot, user_id: int, data: str, target_chat_id: int, message_id: int = 1
):
    bot.sent = []
    target_message = Message(
        message_id=message_id,
        date=datetime.now(),
        chat=Chat(id=target_chat_id, type="private"),
        text="card",
    )
    user = TgUser(id=user_id, is_bot=False, first_name="Test")
    callback = CallbackQuery(
        id="1", from_user=user, chat_instance="ci", data=data, message=target_message
    )
    update = Update(update_id=1, callback_query=callback)
    await dp.feed_update(bot, update)
    return bot.sent


def texts(sent_messages) -> list[str]:
    result = []
    for m in sent_messages:
        text = getattr(m, "text", None)
        if text is None:
            text = getattr(m, "caption", None)
        result.append(text)
    return result
