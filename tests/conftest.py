import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

import db

os.environ.setdefault("BOT_TOKEN", "123456:TEST-TOKEN")
os.environ.setdefault("OPENAI_API_KEY", "test-key")


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
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
