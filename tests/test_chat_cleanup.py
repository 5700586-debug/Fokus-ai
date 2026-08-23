import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import DeleteMessage

from repositories import bot_messages as repo
from services import chat_cleanup

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


class _FakeMessage:
    def __init__(self, chat_id: int, message_id: int) -> None:
        self.chat = type("Chat", (), {"id": chat_id})()
        self.message_id = message_id


class _FakeBot:
    def __init__(self) -> None:
        self.deleted: list[tuple[int, int]] = []
        self.fail_message_ids: set[int] = set()

    async def delete_message(self, chat_id: int, message_id: int) -> bool:
        if message_id in self.fail_message_ids:
            raise TelegramBadRequest(
                method=DeleteMessage(chat_id=chat_id, message_id=message_id),
                message="message to delete not found",
            )
        self.deleted.append((chat_id, message_id))
        return True


async def test_cleanup_deletes_all_tracked_messages_for_workflow():
    chat_cleanup.track("cash_shift_close", "42", _FakeMessage(111, 501))
    chat_cleanup.track("cash_shift_close", "42", _FakeMessage(111, 502))

    bot = _FakeBot()
    await chat_cleanup.cleanup(bot, "cash_shift_close", "42")

    assert sorted(bot.deleted) == [(111, 501), (111, 502)]
    assert repo.pop_messages("cash_shift_close", "42") == []


async def test_cleanup_survives_telegram_delete_failure():
    chat_cleanup.track("cash_shift_close", "77", _FakeMessage(222, 601))
    chat_cleanup.track("cash_shift_close", "77", _FakeMessage(222, 602))

    bot = _FakeBot()
    bot.fail_message_ids.add(601)

    await chat_cleanup.cleanup(bot, "cash_shift_close", "77")

    assert bot.deleted == [(222, 602)]


async def test_cleanup_only_touches_its_own_workflow_key():
    chat_cleanup.track("cash_shift_close", "1", _FakeMessage(1, 10))
    chat_cleanup.track("cash_shift_close", "2", _FakeMessage(1, 20))

    bot = _FakeBot()
    await chat_cleanup.cleanup(bot, "cash_shift_close", "1")

    assert bot.deleted == [(1, 10)]
    remaining = repo.pop_messages("cash_shift_close", "2")
    assert [row["message_id"] for row in remaining] == [20]
