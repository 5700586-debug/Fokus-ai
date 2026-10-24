"""Startup'dagi bir martalik fon "SELECT 1" o'lchovi (Postgres). Telegram/DB mock: haqiqiy Postgres testi
``tests/test_discipline_appeal_postgres.py``da (lokal Docker)."""

import asyncio
import time

import pytest

import config
import db
from services import db_startup_probe, latency_probe

pytestmark = pytest.mark.anyio

SECRET = "postgresql://user:SECRETPASS@host/db"


@pytest.fixture
def anyio_backend():
    return "asyncio"


class _Cursor:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _FakeConn:
    def __init__(self, row=None, delay=0.0, fail_execute=False, fail_rollback=False):
        self.row = {"one": 1} if row is None else row
        self.delay, self.fail_execute, self.fail_rollback = delay, fail_execute, fail_rollback
        self.executed, self.rollbacks, self.closed = 0, 0, False

    def execute(self, sql, params=()):
        self.executed += 1
        if self.delay:
            time.sleep(self.delay)
        if self.fail_execute:
            raise RuntimeError(SECRET)
        return _Cursor(self.row)

    def rollback(self):
        self.rollbacks += 1
        if self.fail_rollback:
            raise RuntimeError(SECRET)

    def close(self):
        self.closed = True


def _lines(out: str) -> list[str]:
    return [line for line in out.splitlines() if line.startswith("DB_STARTUP_PROBE ")]


def test_one_warmup_plus_seven_samples_one_final_line_and_connection_returned():
    conn = _FakeConn()

    line = db_startup_probe._probe_sync(lambda: conn)

    assert conn.executed == 8 and conn.rollbacks == 1 and conn.closed
    assert line.startswith("DB_STARTUP_PROBE outcome=ok samples=7 ") and "\n" not in line
    for key in ("sample_ms=[", "min_ms=", "median_ms=", "max_ms=", "first_execute_ms=", "pool_ms=", "rollback_ms="):
        assert key in line


@pytest.mark.parametrize(
    ("conn", "stage"),
    [
        (_FakeConn(row={"one": 2}), "verify"),
        (_FakeConn(fail_execute=True), "execute"),
        (_FakeConn(fail_rollback=True), "rollback"),
    ],
)
def test_errors_give_one_safe_line_without_secrets_and_still_return_the_connection(conn, stage):
    line = db_startup_probe._probe_sync(lambda: conn)

    assert f"outcome=error stage={stage}" in line and conn.closed
    assert "SECRET" not in line and "postgresql" not in line and "RuntimeError" not in line


def test_pool_failure_is_a_safe_line():
    def connect():
        raise RuntimeError(SECRET)

    line = db_startup_probe._probe_sync(connect)

    assert "outcome=error stage=pool" in line and "SECRET" not in line


async def test_disabled_or_non_postgres_does_nothing(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(db, "_DATABASE_URL", "x")
    monkeypatch.setattr(config, "DB_STARTUP_PROBE_ENABLED", False)
    await db_startup_probe.run_once(lambda: calls.append(1))
    monkeypatch.setattr(config, "DB_STARTUP_PROBE_ENABLED", True)
    monkeypatch.setattr(db, "_DATABASE_URL", None)
    await db_startup_probe.run_once(lambda: calls.append(1))

    assert calls == [] and _lines(capsys.readouterr().out) == []


async def test_runs_once_in_a_thread_without_blocking_the_event_loop(monkeypatch, capsys):
    monkeypatch.setattr(db, "_DATABASE_URL", "x")
    monkeypatch.setattr(config, "DB_STARTUP_PROBE_ENABLED", True)
    ticks = 0

    async def ticker():
        nonlocal ticks
        while True:
            await asyncio.sleep(0.005)
            ticks += 1

    ticker_task = asyncio.create_task(ticker())
    holder: list = []
    conn = _FakeConn(delay=0.03)  # 8 x 30 ms ~ 240 ms sinxron ish
    monkeypatch.setattr(db, "get_connection", lambda: conn)
    db_startup_probe.start(holder)
    await db_startup_probe.shutdown(holder, timeout=5)
    ticker_task.cancel()

    assert len(_lines(capsys.readouterr().out)) == 1 and conn.executed == 8
    assert ticks >= 15  # event loop to'silmagan


async def test_probe_failure_never_raises_and_does_not_touch_handler_metrics(monkeypatch, capsys):
    monkeypatch.setattr(db, "_DATABASE_URL", "x")
    monkeypatch.setattr(config, "DB_STARTUP_PROBE_ENABLED", True)

    class _Counting(_FakeConn):
        def execute(self, sql, params=()):
            with latency_probe.db_execute():  # PgConnection kabi hook'ni chaqiradi
                return super().execute(sql, params)

    token = latency_probe._metrics.set(latency_probe._Metrics())
    try:
        metrics = latency_probe._metrics.get()
        await db_startup_probe.run_once(lambda: _Counting())
        assert metrics.db_queries == 0  # oddiy handler metrikasiga aralashmadi
        await db_startup_probe.run_once(lambda: (_ for _ in ()).throw(RuntimeError(SECRET)))  # xato: yiqilmaydi
    finally:
        latency_probe._metrics.reset(token)

    out = capsys.readouterr().out
    assert len(_lines(out)) == 2 and "SECRET" not in out
