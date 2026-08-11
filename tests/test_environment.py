"""ENVIRONMENT=test bo'lganda bot BUTUNLAY boshqa nomli muhit
o'zgaruvchilarini (TEST_BOT_TOKEN, TEST_DATABASE_URL) o'qishi, va
production nomlariga (BOT_TOKEN, DATABASE_URL) hech qachon tegmasligi —
hatto ikkalasi bir xil ``.env``da tursa ham — shuni tekshiradi.
"""

import os
import subprocess
import sys


def _run_snippet(snippet: str, env_overrides: dict) -> str:
    env = {**os.environ, **env_overrides}
    result = subprocess.run(
        [sys.executable, "-c", snippet],
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    # ``import main`` o'zining xavfsiz startup bannerini (ENVIRONMENT,
    # bot_id prefiksi) ham stdout'ga chiqaradi — bizga faqat oxirgi
    # qatordagi (bizning ``print()``imiz) qiziq.
    return result.stdout.strip().splitlines()[-1]


def test_production_is_the_default_environment():
    output = _run_snippet(
        "import config; print(config.ENVIRONMENT)",
        {"BOT_TOKEN": "x", "OPENAI_API_KEY": "x", "ENVIRONMENT": ""},
    )
    assert output == "production"


def test_unknown_environment_value_falls_back_to_production():
    output = _run_snippet(
        "import config; print(config.ENVIRONMENT)",
        {"BOT_TOKEN": "x", "OPENAI_API_KEY": "x", "ENVIRONMENT": "staging"},
    )
    assert output == "production"


def test_main_uses_test_bot_token_not_bot_token_when_environment_is_test(tmp_path):
    output = _run_snippet(
        "import main; print(main.BOT_TOKEN)",
        {
            "BOT_TOKEN": "PROD:should-not-be-used",
            "TEST_BOT_TOKEN": "TESTTOK:should-be-used",
            "OPENAI_API_KEY": "x",
            "ENVIRONMENT": "test",
            "FOKUS_DATA_DIR": str(tmp_path),
            "DATABASE_URL": "",
        },
    )
    assert output == "TESTTOK:should-be-used"


def test_main_uses_bot_token_when_environment_is_production(tmp_path):
    output = _run_snippet(
        "import main; print(main.BOT_TOKEN)",
        {
            "BOT_TOKEN": "PROD:should-be-used",
            "TEST_BOT_TOKEN": "TESTTOK:should-not-be-used",
            "OPENAI_API_KEY": "x",
            "FOKUS_DATA_DIR": str(tmp_path),
            "DATABASE_URL": "",
        },
    )
    assert output == "PROD:should-be-used"


def test_main_fails_fast_with_clear_error_when_test_token_missing(tmp_path):
    result = subprocess.run(
        [sys.executable, "-c", "import main"],
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        env={
            **os.environ,
            "BOT_TOKEN": "PROD:xxx",
            "OPENAI_API_KEY": "x",
            "ENVIRONMENT": "test",
            "TEST_BOT_TOKEN": "",
            "FOKUS_DATA_DIR": str(tmp_path),
            "DATABASE_URL": "",
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "TEST_BOT_TOKEN" in result.stderr


def test_db_uses_separate_sqlite_file_in_test_environment(tmp_path):
    output = _run_snippet(
        "import db; print(db._DB_FILE)",
        {
            "BOT_TOKEN": "x",
            "OPENAI_API_KEY": "x",
            "ENVIRONMENT": "test",
            "FOKUS_DATA_DIR": str(tmp_path),
            "DATABASE_URL": "",
        },
    )
    assert output == str(tmp_path / "fokus_test.db")


def test_db_ignores_database_url_in_test_environment_without_test_database_url(tmp_path):
    """Production DATABASE_URL bor bo'lsa ham, test muhitida
    TEST_DATABASE_URL o'rnatilmagan bo'lsa, Postgresga ULANMAYDI — SQLite
    fallback ishlatiladi (production bazasiga tasodifan ulanish yo'q).
    """
    output = _run_snippet(
        "import db; print(db._DATABASE_URL)",
        {
            "BOT_TOKEN": "x",
            "OPENAI_API_KEY": "x",
            "ENVIRONMENT": "test",
            "FOKUS_DATA_DIR": str(tmp_path),
            "DATABASE_URL": "postgresql://prod-should-be-ignored/db",
            "TEST_DATABASE_URL": "",
        },
    )
    assert output == "None"


def test_db_uses_test_database_url_when_provided(tmp_path):
    output = _run_snippet(
        "import db; print(db._DATABASE_URL)",
        {
            "BOT_TOKEN": "x",
            "OPENAI_API_KEY": "x",
            "ENVIRONMENT": "test",
            "FOKUS_DATA_DIR": str(tmp_path),
            "DATABASE_URL": "postgresql://prod-should-be-ignored/db",
            "TEST_DATABASE_URL": "postgresql://test-schema/db",
        },
    )
    assert output == "postgresql://test-schema/db"


def test_roles_allowed_users_file_is_separate_in_test_environment(tmp_path):
    output = _run_snippet(
        "import roles; print(roles._ALLOWED_USERS_FILE)",
        {
            "BOT_TOKEN": "x",
            "OPENAI_API_KEY": "x",
            "ENVIRONMENT": "test",
            "FOKUS_DATA_DIR": str(tmp_path),
            "DATABASE_URL": "",
        },
    )
    assert output == str(tmp_path / "allowed_users_test.json")
