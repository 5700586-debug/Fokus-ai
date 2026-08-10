"""``FOKUS_DATA_DIR`` orqali fokus.db/allowed_users.json doimiy diskka
(masalan Render Persistent Disk) ko'chirilishi mumkinligini tekshiradi —
Render'da bu env var o'rnatilmasa avvalgi xatti-harakat (ilova papkasi)
saqlanib qolishi kerak.
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


def test_db_file_defaults_to_app_dir_without_env_var(tmp_path):
    output = _run_snippet(
        "import db, os; print(db._DB_FILE)",
        {"BOT_TOKEN": "x", "OPENAI_API_KEY": "x", "FOKUS_DATA_DIR": ""},
    )
    assert output.endswith(os.path.join("Fokus-ai", "fokus.db")) or output.endswith("fokus.db")
    assert str(tmp_path) not in output


def test_db_file_honors_fokus_data_dir_env_var(tmp_path):
    output = _run_snippet(
        "import db; print(db._DB_FILE)",
        {"BOT_TOKEN": "x", "OPENAI_API_KEY": "x", "FOKUS_DATA_DIR": str(tmp_path)},
    )
    assert output == str(tmp_path / "fokus.db")


def test_allowed_users_file_honors_fokus_data_dir_env_var(tmp_path):
    output = _run_snippet(
        "import roles; print(roles._ALLOWED_USERS_FILE)",
        {"BOT_TOKEN": "x", "OPENAI_API_KEY": "x", "FOKUS_DATA_DIR": str(tmp_path)},
    )
    assert output == str(tmp_path / "allowed_users.json")
