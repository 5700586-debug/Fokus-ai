"""``FOUNDER_ID`` .env/Render environment orqali boshqariladi — kod
o'zgarishisiz Founder almashtirish mumkin bo'lishi kerak, lekin env
o'rnatilmagan (masalan hali yangilanmagan Render deploy) holatda ham
avvalgi Founder bilan ishlashda uzilish bo'lmasligi kerak.
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


def test_founder_id_defaults_when_env_var_unset():
    output = _run_snippet(
        "import config; print(config.FOUNDER_ID)",
        {"BOT_TOKEN": "x", "OPENAI_API_KEY": "x", "FOUNDER_ID": ""},
    )
    assert output == "34213422"


def test_founder_id_honors_env_var_override():
    output = _run_snippet(
        "import config; print(config.FOUNDER_ID)",
        {"BOT_TOKEN": "x", "OPENAI_API_KEY": "x", "FOUNDER_ID": "999888777"},
    )
    assert output == "999888777"
