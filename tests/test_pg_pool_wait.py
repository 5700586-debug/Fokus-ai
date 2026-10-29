"""Postgres pool to'la bo'lsa ulanish darhol xato bermay, qisqa muddat bo'shashini kutadi."""

import psycopg2.pool
import pytest

import db_postgres


class _FakePool:
    def __init__(self, fail_times: int, message: str = "connection pool exhausted"):
        self.fail_times = fail_times
        self.calls = 0
        self.message = message

    def getconn(self):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise psycopg2.pool.PoolError(self.message)
        return "conn"


def test_waits_until_a_connection_is_released(monkeypatch):
    monkeypatch.setattr(db_postgres, "_POOL_RETRY_INTERVAL", 0.001)
    pool = _FakePool(fail_times=3)

    assert db_postgres._getconn_waiting(pool, wait_seconds=2) == "conn"
    assert pool.calls == 4


def test_still_raises_after_the_wait_deadline(monkeypatch):
    monkeypatch.setattr(db_postgres, "_POOL_RETRY_INTERVAL", 0.001)
    pool = _FakePool(fail_times=10_000)

    with pytest.raises(psycopg2.pool.PoolError):
        db_postgres._getconn_waiting(pool, wait_seconds=0.05)


def test_other_pool_errors_are_not_retried():
    pool = _FakePool(fail_times=1, message="connection pool is closed")

    with pytest.raises(psycopg2.pool.PoolError):
        db_postgres._getconn_waiting(pool, wait_seconds=2)
    assert pool.calls == 1
