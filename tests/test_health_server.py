import pytest

import health_server

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def test_health_server_binds_and_responds_ok():
    """Render Web Service $PORT'ga bog'lanishni kutadi — bu server
    o'sha talabni qondiradi, botning Telegram polling ishiga tegmasdan.
    """
    import aiohttp

    runner = await health_server.start(port=0)
    try:
        host, port = runner.addresses[0]

        async with aiohttp.ClientSession() as session:
            async with session.get(f"http://127.0.0.1:{port}/") as response:
                assert response.status == 200
                assert await response.text() == "OK"

            async with session.get(f"http://127.0.0.1:{port}/health") as response:
                assert response.status == 200
    finally:
        await runner.cleanup()


async def test_health_server_uses_port_env_var_by_default(monkeypatch):
    monkeypatch.setenv("PORT", "0")

    runner = await health_server.start()
    try:
        assert runner.addresses  # muvaffaqiyatli bog'landi
    finally:
        await runner.cleanup()
