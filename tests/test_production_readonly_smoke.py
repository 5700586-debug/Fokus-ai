"""Production read-only smoke E2E: read-only guard KODDA majburiy ekanini, session sirlari logga
chiqmasligini va workflow faqat qo'lda ishlashini tekshiradi. Telethon/tarmoq/credential KERAK EMAS."""

import ast
import re
from pathlib import Path

import pytest

import roles
from e2e import readonly_guard as guard
from e2e import run_production_readonly_smoke as smoke
from services import messages, permissions

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = (ROOT / ".github/workflows/production_readonly_smoke_e2e.yml").read_text(encoding="utf-8")
SCRIPT_PATH = ROOT / "e2e/run_production_readonly_smoke.py"
TODAY = "20261005"


# ------------------------------------------------------------- chiquvchi matn allowlist --


def test_allowlist_is_exactly_the_agreed_texts():
    assert guard.ALLOWED_OUTBOUND_TEXTS == {"/start", "/baholash", "/kunniyop", "🧑‍💼 Nazoratchi"}
    for text in guard.ALLOWED_OUTBOUND_TEXTS:
        assert guard.check_outbound_text(text) == text


@pytest.mark.parametrize(
    "text",
    [
        "/closeshift", "/openshift", "/expense", "/score 111 90", "/sinovsmena", "/sinovtugat", "/xarid",
        "/setrole 1 nazoratchi", "/start extra", " /start", "/BAHOLASH", "Chala - 1", "✅ Filialni yopish",
        "Ha", "Yo'q", "✅ Tasdiqlash", "Pomidor 10 kg", "10", "",
    ],
)
def test_dangerous_or_unlisted_outbound_text_is_blocked(text):
    with pytest.raises(guard.ReadOnlyViolation):
        guard.check_outbound_text(text)


# ------------------------------------------------------------------ callback allowlist --


def test_only_todays_branch_selection_callback_is_allowed():
    assert guard.check_callback(b"bos:br:0:20261005", "📍 SATURN Charhiy", TODAY) == "bos:br:0:20261005"
    assert guard.check_callback("bos:br:3:20261005", "📍 SATURN Shafran", TODAY) == "bos:br:3:20261005"


@pytest.mark.parametrize(
    "data",
    [
        "bos:grade:111:alo:20261005",          # baho berish
        "bos:grade:111:chala",                 # eski formatdagi baho
        "bos:close:0:20261005",                # filialni yopish
        "bos:pen:111:10", "bos:penalty_menu:111",  # jarima/minus
        "bos:emp:111:20261005",                # xodim kartasi (faqat filial tanlash ruxsat)
        "bos:decide:5:approved",               # apellyatsiya qarori
        "nzr_grade:111:alo", "nzr_penalty_apply:111:3", "nzr_match_yes:111:3", "nzr_timebonus:111",
        "csui_close_amount_ok", "csui_disc_approve:1", "csdef_list_confirm", "cashshift_approve:1",
        "rl:ok:1", "bos:br:0:20261005:x", "bos:br:x:20261005", "bos:today", "",
        "bos:br:0:19990101",                   # bugungi sana emas
    ],
)
def test_every_write_capable_or_unlisted_callback_is_blocked(data):
    with pytest.raises(guard.ReadOnlyViolation):
        guard.check_callback(data, "📍 SATURN Charhiy", TODAY)


def test_none_callback_data_is_blocked():
    with pytest.raises(guard.ReadOnlyViolation):
        guard.check_callback(None, "📍 SATURN Charhiy", TODAY)


@pytest.mark.parametrize(
    "label",
    ["✅ Filialni yopish", "Chala - 1", "Norma - 2", "A'lo - 3", "🚫 Ball ayirish (-10/-20/-30)", "✅ Tasdiqlash",
     "❌ Rad etish", "✅ Ha", "❌ Yo'q", "✅ Rozi (ball qaytariladi)", "Minus", "Jarima"],
)
def test_dangerous_label_blocks_even_a_branch_shaped_callback(label):
    with pytest.raises(guard.ReadOnlyViolation):
        guard.check_callback("bos:br:0:20261005", label, TODAY)


# ------------------------------------------------------------------ javob tahlili --


def test_role_classification_is_based_only_on_what_was_seen():
    assert guard.classify_start_reply(messages.GENERIC_DENIAL, []) == guard.ROLE_STRANGER
    assert guard.classify_start_reply("Xush kelibsiz", ["🧑‍💼 Nazoratchi", "💰 Kassa"]) == guard.ROLE_NAZORATCHI
    assert guard.classify_start_reply("Xush kelibsiz", ["👑 Asoschi"]) == guard.ROLE_FOUNDER  # xavfli — skript to'xtaydi
    assert guard.classify_start_reply("nimadir", []) == guard.ROLE_UNKNOWN


def test_denial_texts_recognised():
    for text in (messages.GENERIC_DENIAL, messages.MANAGEMENT_DENIAL, messages.REPEAT_OFFENDER_DENIAL):
        assert guard.is_denial(text)
    assert not guard.is_denial("🏬 Avval filialni tanlang:")


def test_english_ui_words_are_detected_and_simple_uzbek_is_clean():
    for bad in ("⭐ Oylik ball qo'yish", "score", "Review", "pending", "Approve", "Reject", "Time bonus", "Founderga yubor"):
        assert guard.find_forbidden_ui_word([bad]), bad
    clean = ["📋 Baholash", "✅ Filialni yopish", "🏬 Filialni tanlash", "🔵 Ali — baholanmagan", "⚠️ Vali — grafik yo'q"]
    assert guard.find_forbidden_ui_word(clean) is None


def test_branch_screen_status_lines_validated():
    good = "🏬 SATURN Charhiy — 2026-10-05\n\n🔵 Ali T — baholanmagan\n✅ Vali T — baholandi\n🔴 Sami T — damda (Ruxsat: Aka T)\n⚠️ Zafar T — grafik yo'q"
    assert guard.status_lines_are_valid(good)[0] is True
    assert guard.status_lines_are_valid("🏬 X — 1\n\n🟢 Ali — bilmayman")[0] is False


def test_forbidden_reply_traces_detected():
    assert guard.find_forbidden_reply_text("Kutilmagan xatolik yuz berdi")
    assert guard.find_forbidden_reply_text("ProgrammingError: relation")
    assert guard.find_forbidden_reply_text("🏬 Avval filialni tanlang:") is None


# ------------------------------------------------ maxfiy session logga chiqmasligi --


def test_redact_hides_session_hash_and_id():
    secrets = ["1BVtsOKABu8-SECRET-SESSION-STRING", "abcdef0123456789abcdef0123456789", "12345678"]
    line = f"boom {secrets[0]} hash={secrets[1]} id={secrets[2]} ROBOT_TELEGRAM_ID=7952886089"
    cleaned = guard.redact(line, secrets)
    assert not any(secret in cleaned for secret in secrets)
    assert "ROBOT_TELEGRAM_ID=7952886089" in cleaned  # tester ID maxfiy emas (talab qilingan chiqish)


def test_log_wrapper_redacts_loaded_secrets(monkeypatch, capsys):
    secret = "SUPER-SECRET-SESSION-VALUE-123456"
    monkeypatch.setenv("E2E_TELEGRAM_API_ID", "99887766")
    monkeypatch.setenv("E2E_TELEGRAM_API_HASH", "hash0123456789hash0123456789ab")
    monkeypatch.setenv("E2E_TELEGRAM_SESSION", secret)
    monkeypatch.setattr(smoke, "_SECRETS", [])

    smoke._load_config()
    smoke._log(f"FAIL=X REASON='telethon xatosi: {secret}'")
    smoke._fail("STEP", f"api {secret} hash0123456789hash0123456789ab")

    output = capsys.readouterr().out
    assert secret not in output and "hash0123456789hash0123456789ab" not in output
    assert "FAIL=X" in output


def test_missing_config_exits_without_printing_values(monkeypatch, capsys):
    for name in smoke._REQUIRED_ENV_VARS:
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(SystemExit) as exc_info:
        smoke._load_config()
    assert exc_info.value.code == 3
    assert "CONFIG_MISSING" in capsys.readouterr().out


def test_script_never_prints_config_session_or_hash_directly():
    tree = ast.parse(SCRIPT_PATH.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "print":
            names = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
            assert not names & {"config", "session", "api_hash", "api_id"}, ast.dump(node)[:200]


# ----------------------------------- botga yuboradigan YAGONA yo'l = guard'li funksiyalar --


def test_only_guarded_helpers_can_send_or_click():
    tree = ast.parse(SCRIPT_PATH.read_text(encoding="utf-8"))
    risky = {"send_message", "send_file", "forward_messages", "delete_messages", "edit_message", "click",
             "send_read_acknowledge", "action", "upload_file"}
    owners: dict[str, set[str]] = {}
    for function in [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
        for call in [n for n in ast.walk(function) if isinstance(n, ast.Call)]:
            attr = getattr(call.func, "attr", None)
            if attr in risky:
                owners.setdefault(attr, set()).add(function.name)
    assert owners == {"send_message": {"_guarded_send"}, "click": {"_guarded_click"}}, owners


def test_guarded_helpers_call_the_guard_before_acting():
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    send_body = source.split("async def _guarded_send", 1)[1].split("async def _guarded_click", 1)[0]
    click_body = source.split("async def _guarded_click", 1)[1].split("def _check_reply", 1)[0]
    assert send_body.index("check_outbound_text") < send_body.index("send_message")
    assert click_body.index("check_callback") < click_body.index(".click(")


def test_target_bot_and_tester_are_hardcoded_and_checked_before_any_message():
    assert guard.TARGET_BOT_USERNAME == "Xoqandiy_ai_bot"
    assert guard.EXPECTED_TESTER_TELEGRAM_ID == roles.E2E_TESTER_TELEGRAM_ID == 7952886089
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    run_body = source.split("async def _run", 1)[1].split("async def _scenario", 1)[0]
    assert run_body.index("EXPECTED_TESTER_TELEGRAM_ID") < run_body.index("_scenario(")
    assert run_body.index("TARGET_BOT_USERNAME") < run_body.index("_scenario(")


def test_module_imports_without_telethon():
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    top_level = source.split("def _log", 1)[0]
    assert "telethon" not in top_level.replace('"""', "").split("import")[-1] or "from telethon" not in top_level


# ------------------------------------------------------------------------ workflow --


def test_workflow_is_manual_only_with_expected_secrets_and_read_permissions():
    on_block = WORKFLOW.split("\non:", 1)[1].split("\npermissions:", 1)[0]
    assert "workflow_dispatch:" in on_block
    for trigger in ("push:", "pull_request", "schedule:", "workflow_run", "repository_dispatch"):
        assert trigger not in WORKFLOW.split("jobs:", 1)[0].replace("# ", "#").split("\n", 0)[0] or trigger not in on_block
        assert trigger not in on_block, trigger
    for secret in ("E2E_TELEGRAM_API_ID", "E2E_TELEGRAM_API_HASH", "E2E_TELEGRAM_SESSION"):
        assert f"secrets.{secret}" in WORKFLOW
    assert "contents: read" in WORKFLOW
    assert "python -m e2e.run_production_readonly_smoke" in WORKFLOW
    assert "PRODUCTION-READONLY" in WORKFLOW  # yozma tasdiq kiritilmasa job ishlamaydi
    assert not re.search(r"^\s+run:.*(echo|printenv|env\b).*SESSION", WORKFLOW, re.MULTILINE)


# ---------------------------------------- production'da tester roli (kod dalili) --


def test_tester_has_no_role_and_no_nazoratchi_or_founder_permissions_by_default(temp_db):
    tester = roles.E2E_TESTER_TELEGRAM_ID

    assert roles.get_role(tester) is None  # virtual: allowed_users'ga kirmaydi
    assert roles.is_authorized(tester) is False
    for action in (
        permissions.ACTION_EVALUATE_EMPLOYEE, permissions.ACTION_CLOSE_DAY, permissions.ACTION_SCORE_EMPLOYEE,
        permissions.ACTION_VIEW_CASH_SUMMARY, permissions.ACTION_REVIEW_CASH_SHIFT, permissions.ACTION_OPEN_CASH_SHIFT,
    ):
        assert permissions.has_permission(tester, action) is False, action
    # Faqat ikkita tor E2E amali (izolyatsiyalangan sinov smena) tester uchun ochiq.
    assert permissions.has_permission(tester, permissions.ACTION_E2E_TEST_CASH_SHIFT) is True
    assert permissions.has_permission(tester, permissions.ACTION_E2E_VIEW_TEST_RUN) is True
