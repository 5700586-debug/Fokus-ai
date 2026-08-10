import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

import db

os.environ.setdefault("BOT_TOKEN", "123456:TEST-TOKEN")
os.environ.setdefault("OPENAI_API_KEY", "test-key")

# ``roles.py`` DATABASE_URL rejimida IMPORT vaqtidayoq ``allowed_users``
# jadvalidan o'qiydi (``_USERS = _load_users()``) — ba'zi test fayllari
# ``roles``ni to'g'ridan-to'g'ri COLLECTION vaqtida import qiladi, ya'ni
# ``temp_db`` fixture ishga tushishidan OLDIN. Shuning uchun sxema shu
# yerda, har qanday test fayli import qilinishidan oldin tayyorlanadi.
if os.getenv("DATABASE_URL"):
    db.init_db()


def _truncate_all_postgres_tables() -> None:
    conn = db.get_connection()
    try:
        rows = conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
        ).fetchall()
        table_names = [row["table_name"] for row in rows]
        if table_names:
            conn.execute(f"TRUNCATE {', '.join(table_names)} RESTART IDENTITY CASCADE")
        conn.commit()
    finally:
        conn.close()


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    # ``DATABASE_URL`` o'rnatilgan bo'lsa (masalan lokal Docker Postgres
    # yoki staging Supabase'ga qarshi qo'lda ishga tushirilganda), butun
    # test svitasi Postgres backend'ga qarshi ishlaydi — har test
    # boshida TRUNCATE bilan tozalanadi (sqlite yo'lidagi tmp_path fayli
    # o'rniga izolyatsiya usuli sifatida).
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        monkeypatch.setattr(db, "_DATABASE_URL", database_url)
        db.init_db()  # jadvallar mavjudligini ta'minlaydi (birinchi test)
        _truncate_all_postgres_tables()
        db.init_db()  # ``rules`` kabi INSERT OR IGNORE seed qatorlarni tiklaydi
    else:
        monkeypatch.setattr(db, "_DB_FILE", str(tmp_path / "test_fokus.db"))
        db.init_db()

    import roles

    monkeypatch.setattr(roles, "_ALLOWED_USERS_FILE", str(tmp_path / "test_allowed_users.json"))
    monkeypatch.setattr(roles, "_USERS", {})

    yield


@pytest.fixture
def bot_dp(temp_db):
    """main.py ni to'liq import qilib, real Telegram tarmog'iga chiqmaydigan
    Bot bilan qaytaradi. ``main`` faqat bir marta import qilinadi
    (Python modul keshi) — keyingi testlarda qayta ishlatiladi, lekin
    barcha DB/FSM chaqiruvlari ``db._DB_FILE`` ni ishga tushirilgan
    paytda emas, chaqirilgan paytda o'qiydi, shuning uchun har bir test
    o'z vaqtinchalik bazasidan foydalanadi.
    """
    import main
    from tests.bot_harness import RecordingBot

    main.ai_users.clear()
    bot = RecordingBot(token=os.environ["BOT_TOKEN"])
    return main, bot
