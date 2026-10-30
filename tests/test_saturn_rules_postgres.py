"""Saturn nizom katalogi importi — PRODUCTION'dagi ``PgConnection`` adapteri orqali HAQIQIY PostgreSQL'da.

Faqat vaqtincha lokal PostgreSQL uchun (production/Supabase'ga HECH QACHON ulanmaydi):

    FOKUS_PG_TEST_DSN='postgresql://USER:PAROL@127.0.0.1:PORT/fokus_pgtest_<id>' \\
        python -m pytest -q tests/test_saturn_rules_postgres.py

``FOKUS_PG_TEST_DSN`` yo'q bo'lsa fayl SKIP qilinadi (bu PostgreSQL tekshiruvi o'tdi degani EMAS). DSN hosti lokal,
baza nomi ``fokus_pgtest_`` bilan boshlanishi va ``DATABASE_URL``/``TEST_DATABASE_URL``dan farqli bo'lishi shart."""

import os
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit

import psycopg2
import pytest

import db
import db_postgres
from services import company_rules_import as importer
from services import discipline

_DSN = os.getenv("FOKUS_PG_TEST_DSN")

pytestmark = pytest.mark.skipif(not _DSN, reason="FOKUS_PG_TEST_DSN o'rnatilmagan (PostgreSQL tekshiruvi o'tkazilmadi)")

FOUNDER = 1
EMPLOYEE = 7_952_886_089  # int4 dan katta sintetik ID


def _assert_safe_dsn() -> None:
    parts = urlsplit(_DSN)
    assert parts.hostname in ("127.0.0.1", "localhost"), "PG test DSN lokal bo'lishi shart"
    assert (parts.path or "").lstrip("/").startswith("fokus_pgtest_"), "baza nomi fokus_pgtest_ bilan boshlanishi shart"
    for name in ("DATABASE_URL", "TEST_DATABASE_URL"):
        assert os.getenv(name) != _DSN, f"{name} bilan bir xil DSN ishlatish taqiqlangan"


def _admin():
    conn = psycopg2.connect(_DSN)
    conn.autocommit = True
    return conn


def _scalar(sql: str):
    conn = _admin()
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
    db.init_db()  # production sxema yo'li: kanonik jadvallar + additiv ustunlar
    mp.undo()
    yield
    db_postgres.close_all_pools()


@pytest.fixture
def pg(pg_schema, temp_db, monkeypatch):
    _assert_safe_dsn()
    admin = _admin()
    try:
        cur = admin.cursor()
        cur.execute("DROP TRIGGER IF EXISTS fokus_break ON company_rule_penalty_options")
        cur.execute("TRUNCATE company_rule_penalty_options, company_rules, discipline_penalties, bonus_bank_ledger, salaries RESTART IDENTITY CASCADE")
    finally:
        admin.close()
    monkeypatch.setattr(db, "_DATABASE_URL", _DSN)
    yield
    db_postgres.close_all_pools()


def _apply():
    return importer.run_import(apply=True, created_by=FOUNDER, expected_version=importer.import_version())


def _counts() -> tuple[int, int]:
    return _scalar("SELECT COUNT(*) FROM company_rules"), _scalar("SELECT COUNT(*) FROM company_rule_penalty_options")


def test_dry_run_writes_nothing_and_apply_imports_the_full_catalog(pg):
    dry = importer.run_import(apply=False, created_by=FOUNDER)
    assert _counts() == (0, 0)
    assert dry["rules_inserted"] == 102 and dry["options_inserted"] == 89 and not dry["conflicts"]

    result = _apply()

    assert result["applied"] and _counts() == (102, 89)
    assert _scalar("SELECT COUNT(*) FROM bonus_bank_ledger") == 0 and _scalar("SELECT COUNT(*) FROM discipline_penalties") == 0


def test_stored_texts_are_exact_source_slices_on_postgres(pg):
    _apply()
    text = importer.read_source()
    conn = _admin()
    try:
        cur = conn.cursor()
        cur.execute("SELECT title, content FROM company_rules")
        rows = cur.fetchall()
    finally:
        conn.close()
    assert rows
    for title, content in rows:
        assert content in text and title in text


def test_repeated_import_is_idempotent(pg):
    _apply()
    second = _apply()
    assert _counts() == (102, 89)
    assert second["rules_inserted"] == 0 and second["options_inserted"] == 0


def test_parallel_imports_leave_one_consistent_catalog(pg):
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(_apply) for _ in range(4)]
        results = [future.result() for future in futures]
    assert all(not result["conflicts"] for result in results)
    assert _counts() == (102, 89)
    assert _scalar("SELECT COUNT(*) - COUNT(DISTINCT source_key) FROM company_rules") == 0


def test_existing_different_rule_is_a_conflict_and_nothing_is_overwritten_or_added(pg):
    discipline.add_rule(26, "BOSHQA SARLAVHA", "qo'lda yozilgan matn", created_by=FOUNDER)

    dry = importer.run_import(apply=False, created_by=FOUNDER)
    applied = importer.run_import(apply=True, created_by=FOUNDER, expected_version=dry["version"])

    assert dry["conflicts"] and applied["conflicts"] == dry["conflicts"] and not applied["applied"]
    assert _counts() == (1, 0)
    assert discipline.get_rule(26)["title"] == "BOSHQA SARLAVHA"


def test_write_error_midway_rolls_back_everything(pg):
    admin = _admin()
    try:
        cur = admin.cursor()
        cur.execute(
            "CREATE OR REPLACE FUNCTION fokus_pgtest_fail() RETURNS trigger LANGUAGE plpgsql AS "
            "$$ BEGIN RAISE EXCEPTION 'sinov: yozuv xatosi'; END $$"
        )
        cur.execute("CREATE TRIGGER fokus_break BEFORE INSERT ON company_rule_penalty_options FOR EACH ROW EXECUTE FUNCTION fokus_pgtest_fail()")
    finally:
        admin.close()
    try:
        with pytest.raises(Exception):
            _apply()
        assert _counts() == (0, 0)
    finally:
        admin = _admin()
        try:
            admin.cursor().execute("DROP TRIGGER fokus_break ON company_rule_penalty_options")
        finally:
            admin.close()


def test_variant_penalty_applies_exactly_the_source_points_on_postgres(pg):
    _apply()
    options = discipline_options(26)
    six = next(o for o in options if o["points"] == 6)

    result = discipline.apply_penalty(EMPLOYEE, FOUNDER, "2026-10-19", 6, 26, "izoh", None, option_id=six["id"])

    assert result["bonus_bank_balance"] == -6
    with pytest.raises(ValueError):
        discipline.apply_penalty(EMPLOYEE, FOUNDER, "2026-10-19", 6, 26, None, None)  # variant tanlanmagan
    with pytest.raises(ValueError):
        discipline.apply_penalty(EMPLOYEE, FOUNDER, "2026-10-19", 20, 26, None, None, option_id=six["id"])
    assert _scalar("SELECT COUNT(*) FROM discipline_penalties") == 1


def discipline_options(rule_number: int) -> list[dict]:
    from repositories import discipline as repo

    return repo.list_penalty_options(rule_number)


# ---------------------------------- minus + balans + ledger BITTA tranzaksiya (PgConnection) --


def _penalty_state() -> tuple:
    return (
        _scalar(f"SELECT COUNT(*) FROM discipline_penalties WHERE employee_id = {EMPLOYEE}"),
        _scalar(f"SELECT COUNT(*) FROM bonus_bank_ledger WHERE user_id = {EMPLOYEE}"),
        _scalar(f"SELECT COALESCE(SUM(bonus_bank), 0) FROM salaries WHERE user_id = {EMPLOYEE}"),
    )


def _set_trigger(table: str, event: str) -> None:
    admin = _admin()
    try:
        cur = admin.cursor()
        cur.execute(
            "CREATE OR REPLACE FUNCTION fokus_pgtest_fail() RETURNS trigger LANGUAGE plpgsql AS "
            "$$ BEGIN RAISE EXCEPTION 'sinov: yozuv xatosi'; END $$"
        )
        cur.execute(f"CREATE TRIGGER fokus_break BEFORE {event} ON {table} FOR EACH ROW EXECUTE FUNCTION fokus_pgtest_fail()")
    finally:
        admin.close()


def _drop_trigger(table: str) -> None:
    admin = _admin()
    try:
        admin.cursor().execute(f"DROP TRIGGER IF EXISTS fokus_break ON {table}")
    finally:
        admin.close()


def test_penalty_success_writes_all_three_records_on_postgres(pg):
    discipline.add_rule(1, "Band", "Matn", created_by=FOUNDER)

    result = discipline.apply_penalty(EMPLOYEE, FOUNDER, "2026-10-19", 10, 1, "izoh", None)

    assert result["bonus_bank_balance"] == -10 and _penalty_state() == (1, 1, -10)
    assert _scalar(f"SELECT ref_id FROM bonus_bank_ledger WHERE user_id = {EMPLOYEE}") == result["penalty_id"]


@pytest.mark.parametrize(
    ("table", "event", "preexisting_salary"),
    [
        ("discipline_penalties", "INSERT", False),
        ("salaries", "INSERT", False),
        ("salaries", "UPDATE", True),
        ("bonus_bank_ledger", "INSERT", False),
        ("bonus_bank_ledger", "INSERT", True),
    ],
)
def test_penalty_failure_at_each_stage_rolls_back_everything_on_postgres(pg, table, event, preexisting_salary):
    discipline.add_rule(1, "Band", "Matn", created_by=FOUNDER)
    if preexisting_salary:
        discipline.adjust_bonus_bank(EMPLOYEE, 50, "boshlang'ich", "test", None)
    before = _penalty_state()
    _set_trigger(table, event)
    try:
        with pytest.raises(Exception):
            discipline.apply_penalty(EMPLOYEE, FOUNDER, "2026-10-19", 10, 1, "izoh", None)
        assert _penalty_state() == before
    finally:
        _drop_trigger(table)

    assert discipline.apply_penalty(EMPLOYEE, FOUNDER, "2026-10-19", 10, 1, None, None)["bonus_bank_balance"] == before[2] - 10
