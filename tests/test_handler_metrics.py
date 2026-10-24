"""HANDLER_METRICS: har handler uchun bitta log qatori (ma'nolari: ``services/latency_probe.py``)."""

import asyncio
import re
from types import SimpleNamespace

import pytest

import config
import db
from services import latency_probe
from tests.bot_harness import send

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _lines(out: str) -> list[dict]:
    result = []
    for line in out.splitlines():
        if line.startswith("HANDLER_METRICS "):
            result.append(dict(part.split("=", 1) for part in line.split()[1:]))
    return result


def _data(name: str = "my_handler") -> dict:
    return {"handler": SimpleNamespace(callback=SimpleNamespace(__name__=name))}


async def measure(kind, handler, name="my_handler"):
    """Haqiqiy zanjirni taqlid qiladi: outer ``measure_handler`` ichida inner ``name_handler`` handlerni nomlaydi."""
    data = _data(name)

    async def named(event, d):
        return await latency_probe.name_handler(handler, event, d)

    return await latency_probe.measure_handler(kind, named, object(), data)


async def test_one_line_with_counts_execute_only_and_commit_time_separate(capsys):
    async def handler(event, data):
        conn = db.get_connection()
        conn.execute("SELECT 1")
        conn.execute("SELECT 2")
        conn.commit()
        conn.close()
        return "ok"

    assert await measure("callback", handler, "calc") == "ok"

    (line,) = _lines(capsys.readouterr().out)
    assert line["handler"] == "calc" and line["kind"] == "callback" and line["outcome"] == "ok"
    assert line["db_queries"] == "2" and line["pool_acquires"] == "1"  # PRAGMA va commit sanalmadi
    assert set(line) == {"handler", "kind", "total_ms", "db_queries", "db_ms", "pool_acquires", "pool_ms", "rollbacks", "rollback_ms", "telegram_ms", "outcome"}


async def test_executemany_and_executescript_count_as_one_call_each(capsys):
    async def handler(event, data):
        conn = db.get_connection()
        conn.execute("CREATE TABLE IF NOT EXISTS _m (a INTEGER)")
        conn.executemany("INSERT INTO _m VALUES (?)", [(1,), (2,), (3,)])
        conn.executescript("DROP TABLE _m;")
        conn.close()

    await measure("message", handler)

    assert _lines(capsys.readouterr().out)[0]["db_queries"] == "3"


async def test_concurrent_updates_do_not_mix_measurements(capsys):
    async def make(n: int):
        async def handler(event, data):
            conn = db.get_connection()
            for _ in range(n):
                conn.execute("SELECT 1")
                await asyncio.sleep(0)
            conn.close()

        await measure("message", handler, f"h{n}")

    await asyncio.gather(make(1), make(4), make(2))

    counts = {line["handler"]: line["db_queries"] for line in _lines(capsys.readouterr().out)}
    assert counts == {"h1": "1", "h4": "4", "h2": "2"}


async def test_error_keeps_original_exception_logs_error_and_restores_context(capsys):
    class Boom(Exception):
        pass

    async def handler(event, data):
        raise Boom("asl xato")

    with pytest.raises(Boom, match="asl xato"):
        await measure("callback", handler, "bad")

    assert _lines(capsys.readouterr().out)[0]["outcome"] == "error"
    assert latency_probe._metrics.get() is None


async def test_measuring_failure_never_breaks_the_handler(monkeypatch):
    def broken_print(*args, **kwargs):
        raise RuntimeError("log yiqildi")

    monkeypatch.setattr("builtins.print", broken_print)

    async def handler(event, data):
        return "natija"

    assert await measure("message", handler) == "natija"
    assert latency_probe._metrics.get() is None


async def test_can_be_switched_off(monkeypatch, capsys):
    monkeypatch.setattr(config, "HANDLER_METRICS_ENABLED", False)

    async def handler(event, data):
        return 1

    assert await measure("message", handler) == 1
    assert _lines(capsys.readouterr().out) == []


async def test_telegram_time_is_counted_once_and_legacy_probe_is_not_double_counted(capsys):
    latency_probe.begin_update(latency_probe._PROBE_USER_ID)  # mavjud LATENCY_PROBE holati ham faol

    async def make_request(bot, method):
        await asyncio.sleep(0.01)
        return "javob"

    async def handler(event, data):
        await latency_probe.telegram_request_middleware(make_request, None, None)
        with latency_probe.db_execute():
            pass
        return None

    await measure("message", handler)

    line = _lines(capsys.readouterr().out)[0]
    assert int(line["telegram_ms"]) >= 9 and line["db_queries"] == "1"
    assert latency_probe._active.get().db_queries == 1  # mavjud zond ham aynan bir marta sanadi
    latency_probe._active.set(None)


async def test_real_chain_logs_static_handler_name_without_content(bot_dp, capsys):
    from roles import set_role
    from config import FOUNDER_ID

    main, bot = bot_dp
    set_role(7001, "kassir", set_by=FOUNDER_ID)

    await send(main.dp, bot, 7001, text="/mymaosh")

    out = capsys.readouterr().out
    lines = _lines(out)
    assert len(lines) == 1 and lines[0]["kind"] == "message" and lines[0]["handler"] == "my_salary_handler"
    assert "mymaosh" not in out.replace("HANDLER_METRICS", "") and "7001" not in out


async def test_unmatched_update_writes_no_line(bot_dp, capsys):
    main, bot = bot_dp
    from roles import set_role
    from config import FOUNDER_ID

    set_role(7002, "kassir", set_by=FOUNDER_ID)

    await send(main.dp, bot, 7002, text="hech qaysi handlerga mos kelmaydigan matn 12345")

    assert _lines(capsys.readouterr().out) == []


async def test_explicit_rollbacks_are_counted_and_time_stays_inside_db_ms(capsys):
    async def handler(event, data):
        conn = db.get_connection()
        conn.execute("SELECT 1")
        conn.rollback()
        conn.rollback()
        conn.close()

    await measure("message", handler)

    line = _lines(capsys.readouterr().out)[0]
    assert line["rollbacks"] == "2" and line["db_queries"] == "1"
    assert int(line["rollback_ms"]) <= int(line["db_ms"])  # db_ms ichida, qayta qo'shilmagan
