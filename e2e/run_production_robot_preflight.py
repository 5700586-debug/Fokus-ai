"""Stage 1 preflight: existing Telethon robot session ishlaydimi va
haqiqiy PRODUCTION botiga (``@Xoqandiy_ai_bot``) ulana oladimi
tekshiradi. Hech qanday xabar/anketa ssenariysi yo'q — faqat ulanish,
``get_me()``, username moslikni tekshirish va bitta ``/start`` -> javob
kutish.

Xavfsizlik: bu skript hech qachon telefon, sessiya qiymati, API hash,
token, shaxsiy chat yoki profil ma'lumotini chop etmaydi — FAQAT robot
akkauntning raqamli Telegram ID'sini, username mosligini va javob
vaqtini. Sessiya yo'q/muddati o'tgan/avtorizatsiya so'ralsa, skript
darhol "ONE-TIME TELEGRAM SESSION LOGIN REQUIRED" deb to'xtaydi —
hech qanday parol/kod so'ramaydi.

Kerakli environment o'zgaruvchilar (qiymati hech qachon chop etilmaydi):
- E2E_TELEGRAM_API_ID
- E2E_TELEGRAM_API_HASH
- E2E_TELEGRAM_SESSION
"""

import asyncio
import os
import sys
import time

_REQUIRED_ENV_VARS = (
    "E2E_TELEGRAM_API_ID",
    "E2E_TELEGRAM_API_HASH",
    "E2E_TELEGRAM_SESSION",
)

_TARGET_BOT_USERNAME = "Xoqandiy_ai_bot"
_RESPONSE_TIMEOUT_SECONDS = 60

_SESSION_LOGIN_REQUIRED_MSG = "ONE-TIME TELEGRAM SESSION LOGIN REQUIRED"


def _load_config() -> dict[str, str]:
    missing = [name for name in _REQUIRED_ENV_VARS if not os.getenv(name)]
    if missing:
        print(_SESSION_LOGIN_REQUIRED_MSG)
        print(f"(sabab: environment o'zgaruvchilar yo'q: {', '.join(missing)})")
        sys.exit(3)

    return {name: os.environ[name] for name in _REQUIRED_ENV_VARS}


async def _run(config: dict[str, str]) -> int:
    from telethon import TelegramClient
    from telethon.sessions import StringSession

    api_id = int(config["E2E_TELEGRAM_API_ID"])
    api_hash = config["E2E_TELEGRAM_API_HASH"]
    session = config["E2E_TELEGRAM_SESSION"]

    client = TelegramClient(StringSession(session), api_id, api_hash)

    try:
        await client.connect()
    except Exception as error:  # noqa: BLE001 — ulanish xatosi ham sessiya muammosi
        print(_SESSION_LOGIN_REQUIRED_MSG)
        print(f"(sabab: connect xatosi: {type(error).__name__})")
        return 3

    try:
        authorized = await client.is_user_authorized()
    except Exception as error:  # noqa: BLE001
        print(_SESSION_LOGIN_REQUIRED_MSG)
        print(f"(sabab: avtorizatsiya tekshiruvi xatosi: {type(error).__name__})")
        await client.disconnect()
        return 3

    if not authorized:
        print(_SESSION_LOGIN_REQUIRED_MSG)
        await client.disconnect()
        return 3

    try:
        me = await client.get_me()
        robot_id = me.id

        try:
            bot_entity = await client.get_entity(_TARGET_BOT_USERNAME)
        except Exception as error:  # noqa: BLE001
            print(f"ROBOT_TELEGRAM_ID={robot_id}")
            print(f"BOT_USERNAME_MATCH=ERROR ({type(error).__name__})")
            print("PRODUCTION_BOT_RESPONSE=FAIL")
            print("RESPONSE_TIME_SECONDS=0.00")
            return 1

        resolved_username = (getattr(bot_entity, "username", None) or "").lower()
        username_matches = resolved_username == _TARGET_BOT_USERNAME.lower()

        print(f"ROBOT_TELEGRAM_ID={robot_id}")
        print(f"BOT_USERNAME_MATCH={'OK' if username_matches else 'MISMATCH'}")

        if not username_matches:
            print("PRODUCTION_BOT_RESPONSE=FAIL")
            print("RESPONSE_TIME_SECONDS=0.00")
            return 1

        start = time.monotonic()
        response_received = False
        try:
            async with client.conversation(bot_entity, timeout=_RESPONSE_TIMEOUT_SECONDS) as conv:
                await conv.send_message("/start")
                await conv.get_response(timeout=_RESPONSE_TIMEOUT_SECONDS)
                response_received = True
        except Exception:  # noqa: BLE001 — istalgan kutish xatosi ham FAIL
            response_received = False
        elapsed = time.monotonic() - start

        print(f"PRODUCTION_BOT_RESPONSE={'PASS' if response_received else 'FAIL'}")
        print(f"RESPONSE_TIME_SECONDS={elapsed:.2f}")

        return 0 if response_received else 1
    finally:
        await client.disconnect()


def main() -> None:
    config = _load_config()
    exit_code = asyncio.run(_run(config))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
