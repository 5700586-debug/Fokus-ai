"""E'tirozni atomik yuborish/hal qilish va dialog xabarlari jurnali — PRODUCTION ``PgConnection`` adapteri orqali
HAQIQIY PostgreSQL'da. Faqat vaqtincha lokal PostgreSQL (production/Supabase'ga HECH QACHON ulanmaydi):

    FOKUS_PG_TEST_DSN='postgresql://USER:PAROL@127.0.0.1:PORT/fokus_pgtest_<id>' \\
        python -m pytest -q tests/test_discipline_appeal_postgres.py

DSN o'rnatilmasa fayl SKIP qilinadi (bu PostgreSQL tekshiruvi o'tdi degani EMAS)."""

import os
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit

import psycopg2
import pytest

import db
import db_postgres
from repositories import bot_messages
from services import dialog_cleanup, discipline

_DSN = os.getenv("FOKUS_PG_TEST_DSN")

pytestmark = pytest.mark.skipif(not _DSN, reason="FOKUS_PG_TEST_DSN o'rnatilmagan (PostgreSQL tekshiruvi o'tkazilmadi)")

FOUNDER = 1
EMPLOYEE = 7_952_886_089


def _assert_safe_dsn() -> None:
    parts = urlsplit(_DSN)
    assert parts.hostname in ("127.0.0.1", "localhost"), "PG test DSN lokal bo'lishi shart"
    assert (parts.path or "").lstrip("/").startswith("fokus_pgtest_"), "baza nomi fokus_pgtest_ bilan boshlanishi shart"
    for name in ("DATABASE_URL", "TEST_DATABASE_URL"):
        assert os.getenv(name) != _DSN, f"{name} bilan bir xil DSN ishlatish taqiqlangan"


def _scalar(sql: str):
    conn = psycopg2.connect(_DSN)
    conn.autocommit = True
    try:
        cur = conn.cursor()
        cur.execute(sql)
        return cur.fetchone()[0]
    finally:
        conn.close()


@pytest.fixture(scope="module")
def pg_schema():
    _assert_safe_dsn()
    mp = pytest.MonkeyPatch()
    mp.setattr(db, "_DATABASE_URL", _DSN)
    db.init_db()
    mp.undo()
    yield
    db_postgres.close_all_pools()


@pytest.fixture
def pg(pg_schema, temp_db, monkeypatch):
    _assert_safe_dsn()
    conn = psycopg2.connect(_DSN)
    conn.autocommit = True
    try:
        conn.cursor().execute(
            "TRUNCATE discipline_penalties, bonus_bank_ledger, salaries, bot_workflow_messages, company_rules RESTART IDENTITY CASCADE"
        )
    finally:
        conn.close()
    monkeypatch.setattr(db, "_DATABASE_URL", _DSN)
    yield
    db_postgres.close_all_pools()


def _penalty() -> int:
    discipline.add_rule(1, "Band", "Matn", created_by=FOUNDER)
    return discipline.apply_penalty(EMPLOYEE, FOUNDER, "2026-10-19", 10, 1, "izoh", None)["penalty_id"]


def test_appeal_can_be_submitted_only_once_on_postgres(pg):
    penalty_id = _penalty()
    assert discipline.submit_appeal(penalty_id, "birinchi", None) is not None
    assert discipline.submit_appeal(penalty_id, "ikkinchi", None) is None
    assert discipline.get_penalty(penalty_id)["appeal_reason"] == "birinchi"


def test_parallel_decisions_refund_exactly_once_on_postgres(pg):
    penalty_id = _penalty()
    discipline.submit_appeal(penalty_id, "sabab", None)

    def decide():
        try:
            discipline.decide_appeal(penalty_id, discipline.DECISION_APPROVED, FOUNDER)
            return True
        except ValueError:
            return False

    with ThreadPoolExecutor(max_workers=4) as pool:
        outcomes = [future.result() for future in [pool.submit(decide) for _ in range(4)]]

    assert outcomes.count(True) == 1
    assert _scalar(f"SELECT bonus_bank FROM salaries WHERE user_id = {EMPLOYEE}") == 0  # -10 + 10 (bir marta)
    assert _scalar("SELECT COUNT(*) FROM bonus_bank_ledger WHERE ref_type = 'appeal_refund'") == 1
    assert _scalar("SELECT COUNT(*) FROM discipline_penalties") == 1  # tarix o'chmagan


def test_dialog_message_log_survives_and_pops_on_postgres(pg):
    from aiogram.types import Chat, Message
    from datetime import datetime

    key = dialog_cleanup.minus_key(EMPLOYEE, "abcd")
    for message_id in (11, 12):
        dialog_cleanup.track(key, Message(message_id=message_id, date=datetime.now(), chat=Chat(id=EMPLOYEE, type="private"), text="x"))
    dialog_cleanup.track(dialog_cleanup.minus_key(EMPLOYEE, "other"), Message(message_id=13, date=datetime.now(), chat=Chat(id=EMPLOYEE, type="private"), text="x"))

    rows = bot_messages.pop_messages(dialog_cleanup.WORKFLOW, key)

    assert sorted(row["message_id"] for row in rows) == [11, 12]
    assert _scalar("SELECT COUNT(*) FROM bot_workflow_messages") == 1  # boshqa dialog tegilmagan
