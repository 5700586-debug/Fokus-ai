"""``db_postgres.PgConnection`` endi jarayon-lokal ``ThreadedConnectionPool``
orqali fizik ulanishlarni QAYTA ISHLATADI (avval har bir chaqiruv
to'g'ridan-to'g'ri ``psycopg2.connect()`` ochardi -- production'da
bitta buyruq 6-11 marta shunday qilib, ``LATENCY_PROBE`` bo'yicha
eng katta o'lchangan kechikish shu edi). Bu fayl faqat pool
qatlamining o'zini -- fizik ulanish qayta ishlatilishini, tugallanmagan
tranzaksiya rollback qilinishini, buzilgan ulanish tashlab
yuborilishini, ikki marta ``close()`` xavfsizligini, checkout qilingan
ulanishning hech qachon "sizib qolmasligi"ni va turli DSN'lar mustaqil
pool olishini -- tekshiradi. Faqat Postgres backend'ga tegishli --
SQLite yo'lida hech qanday pool yo'q, shuning uchun ``DATABASE_URL``
o'rnatilmagan muhitda bu fayl butunlay o'tkazib yuboriladi.
"""

import os

import pytest

import db

pytestmark = [
    pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="faqat Postgres backend uchun"),
]


def test_repeated_sequential_use_reuses_one_physical_connection(monkeypatch):
    import psycopg2

    # Pool'ni oldindan "isitib" olamiz -- shu daqiqadan keyin ketma-ket
    # ulanishlarning hech biri YANGI fizik connect so'ramasligi kerak.
    warm_conn = db.get_connection()
    warm_conn.close()

    real_connect = psycopg2.connect
    calls: list[int] = []

    def _counting_connect(*args, **kwargs):
        calls.append(1)
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(psycopg2, "connect", _counting_connect)

    physical_ids = set()
    for _ in range(5):
        conn = db.get_connection()
        physical_ids.add(id(conn._conn))
        conn.close()

    assert calls == [], f"isitilgandan keyin yangi fizik connect() kutilmagan edi, topildi: {len(calls)}"
    assert len(physical_ids) == 1, "har safar bitta xuddi shu fizik ulanish qayta ishlatilishi kutilgan edi"


def test_close_returns_healthy_connection_to_pool_instead_of_closing_it():
    conn = db.get_connection()
    pg_conn = conn._conn
    conn.close()
    assert pg_conn.closed == 0, "sog'lom ulanish jismonan yopilmasligi, pool'ga qaytarilishi kerak"


def test_uncommitted_transaction_rolled_back_before_reuse():
    setup_conn = db.get_connection()
    try:
        setup_conn.execute("CREATE TABLE IF NOT EXISTS _pool_test_rollback (id SERIAL PRIMARY KEY, val TEXT)")
        setup_conn.commit()
    finally:
        setup_conn.close()

    conn = db.get_connection()
    physical_id = id(conn._conn)
    conn.execute("INSERT INTO _pool_test_rollback (val) VALUES (?)", ("uncommitted",))
    # ATAYLAB commit() chaqirilmaydi -- close() buni rollback qilishi kerak.
    conn.close()

    conn2 = db.get_connection()
    assert id(conn2._conn) == physical_id, "xuddi shu fizik ulanish qayta ishlatilishi kutilgan edi"
    row = conn2.execute("SELECT COUNT(*) AS n FROM _pool_test_rollback").fetchone()
    conn2.close()
    assert row["n"] == 0, "commit qilinmagan yozuv rollback qilinmasdan qolib ketdi"


def test_broken_connection_is_discarded_not_reused(monkeypatch):
    conn = db.get_connection()
    pool_obj = conn._pool
    physical = conn._conn

    putconn_calls: list[tuple[bool, bool]] = []
    original_putconn = pool_obj.putconn

    def _spy_putconn(connection, key=None, close=False):
        putconn_calls.append((connection is physical, close))
        return original_putconn(connection, key=key, close=close)

    monkeypatch.setattr(pool_obj, "putconn", _spy_putconn)

    physical.close()  # ulanishni "tashqaridan" (kutilmagan) uzamiz
    conn.close()

    assert putconn_calls == [(True, True)], (
        f"buzilgan ulanish close=True bilan pool'dan chiqarib tashlanishi kutilgan edi, olindi: {putconn_calls}"
    )


def test_double_close_is_harmless():
    conn = db.get_connection()
    conn.close()
    conn.close()  # ikkinchi chaqiruv hech narsa qilmasligi, xato bermasligi kerak


def test_exception_between_get_and_close_cannot_leak_checked_out_connection():
    conn = db.get_connection()
    pool_obj = conn._pool
    physical_id = id(conn._conn)

    try:
        try:
            raise RuntimeError("kutilmagan xato")
        finally:
            conn.close()
    except RuntimeError:
        pass

    # ``_rused`` -- pool ichidagi ``id(conn) -> key`` teskari xaritasi
    # (qarang psycopg2/pool.py). Agar checkout hali ham "ochiq" hisoblansa,
    # bu fizik ulanish shu xaritada qolgan bo'lardi.
    assert physical_id not in pool_obj._rused, "checkout qilingan ulanish pool hisobida sizib qolgan"


def test_simultaneous_checkouts_receive_different_physical_connections():
    """``getconn()``ning avtomatik yaratilgan kaliti (psycopg2/pool.py
    ``_getkey()`` -- oddiy o'suvchi hisoblagich, kalit ATAYLAB
    uzatilmasa ham) ikkita BIR VAQTDA ochiq ``PgConnection`` hech qachon
    bitta xuddi shu fizik ulanishga (demak bitta umumiy tranzaksiyaga)
    to'qnashmasligini ta'minlaydi -- ikkinchisi birinchisi YOPILMASDAN
    turib ochiladi."""
    conn_a = db.get_connection()
    conn_b = db.get_connection()
    try:
        assert id(conn_a._conn) != id(conn_b._conn), (
            "bir vaqtda ochilgan ikkita ulanish bitta xuddi shu fizik ulanishni olib qo'ydi"
        )
    finally:
        conn_a.close()
        conn_b.close()


def test_different_dsns_get_independent_pools(monkeypatch):
    import psycopg2.pool as pg_pool

    import db_postgres

    class _FakePool:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    monkeypatch.setattr(pg_pool, "ThreadedConnectionPool", _FakePool)
    monkeypatch.setattr(db_postgres, "_pools", {})

    pool_a = db_postgres._get_pool("postgresql://tester-a/db")
    pool_b = db_postgres._get_pool("postgresql://tester-b/db")
    pool_a_again = db_postgres._get_pool("postgresql://tester-a/db")

    assert pool_a is not pool_b, "turli DSN'lar mustaqil pool olishi kutilgan edi"
    assert pool_a is pool_a_again, "bir xil DSN uchun bitta pool qayta ishlatilishi kutilgan edi"


def test_pool_initialization_failure_propagates_without_retry(monkeypatch):
    import psycopg2
    import psycopg2.pool as pg_pool

    import db_postgres

    class _BoomingPool:
        def __init__(self, *args, **kwargs):
            raise psycopg2.pool.PoolError("simulated pool init failure")

    monkeypatch.setattr(pg_pool, "ThreadedConnectionPool", _BoomingPool)
    monkeypatch.setattr(db_postgres, "_pools", {})

    with pytest.raises(psycopg2.pool.PoolError):
        db_postgres._get_pool("postgresql://tester-boom/db")
