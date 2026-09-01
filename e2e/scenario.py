"""Rol Testi sandbox ssenariysining sof mantiqi — Telethon yoki
tarmoqqa umuman bog'liq emas, ataylab shunday: shu modul oddiy Linux
CI (mavjud ``requirements-dev.txt``, Telethon shart emas) ichida test
qilinadi, real Telegram orqali E2E esa faqat ``e2e/run_e2e.py``da
(Telethon o'rnatilgan, credential berilgan holatda) ishga tushadi.

Har bir ``Step`` — botga yuboriladigan matn va kutilgan javobning
(matn ichida bo'lishi shart bo'lgan qismlar, tugmalar orasida
bo'lishi shart bo'lgan qismlar) ta'rifi. ``response_matches()`` bitta
qadam natijasini tekshiradi va (mos keldimi, sabab) qaytaradi —
``run_e2e.py`` shu funksiyani chaqiradi, mantiqni ikki marta
yozmaslik uchun.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Step:
    name: str
    send_text: str
    expect_text_contains: tuple[str, ...] = ()
    expect_button_contains: tuple[str, ...] = ()
    timeout_seconds: int = 20


def response_matches(step: Step, response_text: str | None, button_texts: list[str]) -> tuple[bool, str]:
    """Bitta qadam natijasini tekshiradi. ``response_text`` — botdan
    kelgan xabar matni (timeout bo'lsa ``None``), ``button_texts`` —
    shu javobdagi reply-keyboard tugmalari matni (bo'lmasa bo'sh
    ro'yxat)."""
    if response_text is None:
        return False, f"[{step.name}] Bot javob bermadi (timeout, {step.timeout_seconds}s)."

    for expected in step.expect_text_contains:
        if expected not in response_text:
            return False, (
                f"[{step.name}] Matnda {expected!r} topilmadi. "
                f"Haqiqiy javob: {response_text!r}"
            )

    for expected in step.expect_button_contains:
        if not any(expected in text for text in button_texts):
            return False, (
                f"[{step.name}] Tugmalar orasida {expected!r}ga mos keluvchi topilmadi. "
                f"Mavjud tugmalar: {button_texts!r}"
            )

    return True, "OK"


# Ssenariy — main.py'dagi haqiqiy tugma/xabar matnlariga aynan mos
# (qarang ``_SandboxPreviewMiddleware``, ``founder_branches_handler``).
# Rol tanlov tugmasi ``roles.ROLES["kassir"]`` qiymati — "Kassir",
# emojisiz (bu 🧪 Rol testi rol-tanlov ekranining o'zi, kategoriya
# tugmasi emas).
SCENARIO: tuple[Step, ...] = (
    Step(
        name="start",
        send_text="/start",
        expect_text_contains=("Assalomu alaykum",),
        expect_button_contains=("🧪 Rol testi",),
    ),
    Step(
        name="rol_testi_kirish",
        send_text="🧪 Rol testi",
        expect_text_contains=("TEST SANDBOX", "Qaysi rolni sinab ko'rmoqchisiz"),
        expect_button_contains=("Kassir",),
    ),
    Step(
        name="kassir_tanlash",
        send_text="Kassir",
        expect_text_contains=("TEST SANDBOX", "Kassir menyusi"),
        expect_button_contains=("💰 Kassa", "⬅️ Testdan chiqish"),
    ),
    Step(
        name="kassa_bolimi",
        send_text="💰 Kassa",
        expect_text_contains=("TEST SANDBOX", "Kerakli buyruqni tanlang"),
        expect_button_contains=("🔴 Smenani topshirish", "⬅️ Testdan chiqish"),
    ),
    Step(
        name="mutating_action_blocked",
        send_text="🔴 Smenani topshirish",
        expect_text_contains=("TEST SANDBOX", "bazaga yozilmadi"),
    ),
    Step(
        name="testdan_chiqish",
        send_text="⬅️ Testdan chiqish",
        expect_text_contains=("chiqdingiz",),
        expect_button_contains=("👤 Xodim qo'shish", "🏬 Do'konlar"),
    ),
    Step(
        name="dokonlar",
        send_text="🏬 Do'konlar",
        expect_text_contains=("Do'konlar",),
        # Aniq filial nomi (RECRUITING_BRANCH_NAMES) muhitga qarab farq
        # qilishi mumkin — faqat "📍 " prefiksli tugma borligini
        # tekshiramiz, aniq nomni emas.
        expect_button_contains=("📍", "⬅️ Orqaga"),
    ),
)
