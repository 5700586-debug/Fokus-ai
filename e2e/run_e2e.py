"""Real Telegram orqali ``fokus-ai-test`` botini E2E tekshiruvchi
skript.

Bu skript FAQAT ``.github/workflows/e2e_real_telegram.yml`` orqali
(qo'lda ishga tushiriladi) yoki mahalliy ravishda credential mavjud
bo'lganda ishlatiladi. Hech qachon avtomatik/har push'da ishlamaydi va
main/production/real botga umuman tegmaydi — faqat
``E2E_TEST_BOT_USERNAME`` orqali ko'rsatilgan (har doim ``fokus-ai-test``
bo'lishi kerak) bot bilan gaplashadi.

Kerakli environment o'zgaruvchilar (hech qachon repo yoki logga
yozilmaydi — faqat qiymat MAVJUDLIGI tekshiriladi, o'zi hech qachon
print qilinmaydi):
- E2E_TELEGRAM_API_ID
- E2E_TELEGRAM_API_HASH
- E2E_TELEGRAM_SESSION      (oldindan generatsiya qilingan Telethon
                              string session — bu skript hech qachon
                              interaktiv login/telefon/SMS kod
                              so'ramaydi, faqat mavjud sessiyadan
                              foydalanadi)
- E2E_TEST_BOT_USERNAME     (masalan "fokus_ai_test_bot", "@" bilan
                              ham, bilan ham ishlaydi)

Test akkaunt ``fokus-ai-test`` Render xizmatida ALOHIDA ``FOUNDER_ID``
sifatida tanilgan bo'lishi kerak (production'dagi haqiqiy Founder
akkountidan butunlay mustaqil, kod o'zgarmaydi — faqat shu bitta Render
xizmatining o'z environment o'zgaruvchisi). Qarang ``e2e/README.md``
"Bir martalik setup" bo'limi.
"""

import asyncio
import os
import sys

from e2e.scenario import SCENARIO, response_matches

_REQUIRED_ENV_VARS = (
    "E2E_TELEGRAM_API_ID",
    "E2E_TELEGRAM_API_HASH",
    "E2E_TELEGRAM_SESSION",
    "E2E_TEST_BOT_USERNAME",
)


def _load_config() -> dict[str, str]:
    missing = [name for name in _REQUIRED_ENV_VARS if not os.getenv(name)]
    if missing:
        print(
            "❌ E2E test ishga tushmadi — quyidagi environment o'zgaruvchilar "
            f"yo'q yoki bo'sh: {', '.join(missing)}.\n"
            "Bular GitHub Secrets orqali berilishi kerak — qarang "
            "e2e/README.md va .github/workflows/e2e_real_telegram.yml."
        )
        sys.exit(2)

    return {name: os.environ[name] for name in _REQUIRED_ENV_VARS}


def _extract_button_texts(message) -> list[str]:
    """Telethon xabaridagi reply-keyboard (custom keyboard, inline
    emas) tugmalari matnini chiqaradi. Tugma bo'lmasa bo'sh ro'yxat."""
    reply_markup = getattr(message, "reply_markup", None)
    rows = getattr(reply_markup, "rows", None)
    if not rows:
        return []

    texts = []
    for row in rows:
        for button in getattr(row, "buttons", []):
            text = getattr(button, "text", None)
            if text:
                texts.append(text)
    return texts


async def _run(config: dict[str, str]) -> bool:
    from telethon import TelegramClient
    from telethon.sessions import StringSession

    api_id = int(config["E2E_TELEGRAM_API_ID"])
    api_hash = config["E2E_TELEGRAM_API_HASH"]
    session = config["E2E_TELEGRAM_SESSION"]
    bot_username = config["E2E_TEST_BOT_USERNAME"].lstrip("@")

    client = TelegramClient(StringSession(session), api_id, api_hash)
    await client.connect()

    if not await client.is_user_authorized():
        print(
            "❌ Telethon sessiyasi haqiqiy emas yoki muddati o'tgan.\n"
            "E2E_TELEGRAM_SESSION qiymatini qayta generatsiya qilish kerak "
            "— qarang e2e/README.md."
        )
        await client.disconnect()
        return False

    print(f"➡️  Ulanish o'rnatildi. Bot: @{bot_username}. Ssenariy: {len(SCENARIO)} qadam.\n")

    all_passed = True
    try:
        async with client.conversation(bot_username, timeout=30) as conv:
            for step in SCENARIO:
                await conv.send_message(step.send_text)

                response_text: str | None = None
                button_texts: list[str] = []
                try:
                    response = await conv.get_response(timeout=step.timeout_seconds)
                    response_text = response.text
                    button_texts = _extract_button_texts(response)
                except Exception as error:  # noqa: BLE001 — istalgan kutish xatosi ham FAILED
                    print(f"  (kutish xatosi: {type(error).__name__}: {error})")

                ok, reason = response_matches(step, response_text, button_texts)
                status = "✅ PASSED" if ok else "❌ FAILED"
                print(f"{status} — {step.name}: {reason}")

                if not ok:
                    all_passed = False
                    break
    finally:
        await client.disconnect()

    return all_passed


def main() -> None:
    config = _load_config()
    passed = asyncio.run(_run(config))

    if passed:
        print("\n✅ E2E ssenariy TO'LIQ PASSED.")
        sys.exit(0)

    print("\n❌ E2E ssenariy FAILED.")
    sys.exit(1)


if __name__ == "__main__":
    main()
