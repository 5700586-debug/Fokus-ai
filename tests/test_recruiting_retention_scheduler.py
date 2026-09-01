import pytest

import recruiting_bot
from repositories import recruiting as recruiting_repo

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


class _FakeBot:
    pass


async def test_retention_purge_tick_deletes_only_expired_applications():
    kassir = recruiting_repo.get_vacancy_by_key("kassir")
    past_id = recruiting_repo.create_application(777777, kassir["id"], "2000-01-01T00:00:00+00:00")
    future_id = recruiting_repo.create_application(888888, kassir["id"], "2099-01-01T00:00:00+00:00")

    await recruiting_bot._retention_purge_tick()

    assert recruiting_repo.get_application(past_id) is None
    assert recruiting_repo.get_application(future_id) is not None


async def test_start_scheduler_registers_job_and_can_shutdown():
    scheduler = recruiting_bot.start_scheduler(_FakeBot())
    try:
        assert scheduler.get_job("recruiting_retention_purge") is not None
        assert scheduler.running is True
    finally:
        scheduler.shutdown(wait=False)
