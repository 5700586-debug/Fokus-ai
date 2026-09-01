"""``e2e/scenario.py``ning sof mantiqini tekshiradi — Telethon yoki
tarmoq YO'Q, faqat qadamlar ro'yxati va moslik tekshiruvi funksiyasi.
Real Telegram orqali E2E ishga tushirish uchun qarang
``.github/workflows/e2e_real_telegram.yml`` (qo'lda, credential bilan).
"""

from e2e import scenario


def test_scenario_has_expected_step_order():
    names = [step.name for step in scenario.SCENARIO]
    assert names == [
        "start",
        "rol_testi_kirish",
        "kassir_tanlash",
        "kassa_bolimi",
        "mutating_action_blocked",
        "testdan_chiqish",
        "dokonlar",
    ]


def test_response_matches_accepts_valid_response():
    step = scenario.SCENARIO[0]

    ok, reason = scenario.response_matches(
        step, "Assalomu alaykum, Test! 👋", ["🧪 Rol testi", "⚙️ Sozlamalar"]
    )

    assert ok, reason


def test_response_matches_rejects_missing_text():
    step = scenario.SCENARIO[0]

    ok, reason = scenario.response_matches(step, "Boshqa matn", ["🧪 Rol testi"])

    assert not ok
    assert "Assalomu alaykum" in reason


def test_response_matches_rejects_missing_button():
    step = scenario.SCENARIO[0]

    ok, reason = scenario.response_matches(step, "Assalomu alaykum", [])

    assert not ok
    assert "🧪 Rol testi" in reason


def test_response_matches_rejects_timeout_none_response():
    step = scenario.SCENARIO[0]

    ok, reason = scenario.response_matches(step, None, [])

    assert not ok
    assert "timeout" in reason.lower()


def test_mutating_action_step_targets_sandbox_blocked_message_not_a_real_shift_action():
    step = scenario.SCENARIO[4]

    assert step.send_text == "🔴 Smenani topshirish"
    assert "bazaga yozilmadi" in step.expect_text_contains


def test_dokonlar_step_does_not_hardcode_a_specific_branch_name():
    step = scenario.SCENARIO[-1]

    assert step.send_text == "🏬 Do'konlar"
    assert "📍" in step.expect_button_contains
