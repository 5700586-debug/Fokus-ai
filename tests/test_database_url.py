"""``DATABASE_URL``ni o'qish va xavfsiz log qilish bilan bog'liq xatti-harakat.

Render Environment UI'ga qo'lda joylashtirilganda qiymat oxiriga bilinmas
bo'sh joy/qator ko'chirish ilashib qolishi keng tarqalgan xato — bunday
DSN'ni psycopg2 butunlay parslay olmaydi va ulanish darhol yiqiladi
(qarang: ``db.py``dagi ``_DATABASE_URL`` normalizatsiyasi).
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
    return result.stdout.strip()


def test_database_url_trailing_whitespace_is_stripped():
    output = _run_snippet(
        "import db; print(repr(db._DATABASE_URL))",
        {
            "BOT_TOKEN": "x",
            "OPENAI_API_KEY": "x",
            "DATABASE_URL": "postgresql://user:pass@example.com:5432/db \n",
        },
    )
    assert output == repr("postgresql://user:pass@example.com:5432/db")


def test_database_url_blank_value_is_treated_as_unset():
    output = _run_snippet(
        "import db; print(repr(db._DATABASE_URL))",
        {"BOT_TOKEN": "x", "OPENAI_API_KEY": "x", "DATABASE_URL": "   "},
    )
    assert output == repr(None)


def test_redact_dsn_never_includes_the_password():
    import db

    redacted = db._redact_dsn("postgresql://postgres.abc123:s3cr3t-pass@aws-0-eu.pooler.supabase.com:5432/postgres")

    assert "s3cr3t-pass" not in redacted
    assert "aws-0-eu.pooler.supabase.com:5432" in redacted
    assert "postgres.abc123" in redacted
