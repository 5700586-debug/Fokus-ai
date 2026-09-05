"""Real Telegram orqali PRODUCTION botining (``@Xoqandiy_ai_bot``)
izolyatsiyalangan E2E test (``Sinovchi``) ssenariysini tekshiradi:

``/sinovsmena`` (ikki marta, davom ettirish) -> ikkita noyob
belgilangan mahsulot -> bitta tasdiqlash -> ``/xarid`` izolyatsiya
tekshiruvi -> ``/sinovtugat`` -> ``/xarid`` tozalash tekshiruvi.

Faqat ``roles.E2E_TESTER_TELEGRAM_ID`` (7952886089) uchun ochiq real
xodim/ta'minotchi oqimiga UMUMAN tegmaydi. Har bir qadam qat'iy
tekshiriladi (muvaffaqiyatsizlikda darhol to'xtaydi va ``/sinovtugat``
bilan bir martalik tozalashga urinadi). Hech qachon telefon, sessiya
qiymati, API hash yoki tokenni chop etmaydi -- faqat xavfsiz xulosa
qatorlari (vaqt, mahsulot nomlari — bular Founder tomonidan shu
skript uchun yaratilgan sinov ma'lumotlari, shaxsiy emas).
"""

import asyncio
import os
import sys
import time
from datetime import datetime, timezone

_REQUIRED_ENV_VARS = (
    "E2E_TELEGRAM_API_ID",
    "E2E_TELEGRAM_API_HASH",
    "E2E_TELEGRAM_SESSION",
)

_TARGET_BOT_USERNAME = "Xoqandiy_ai_bot"
_REPLY_TIMEOUT_SECONDS = 60
_WARN_THRESHOLD_SECONDS = 15

_SESSION_LOGIN_REQUIRED_MSG = "ONE-TIME TELEGRAM SESSION LOGIN REQUIRED"


def _load_config() -> dict[str, str]:
    missing = [name for name in _REQUIRED_ENV_VARS if not os.getenv(name)]
    if missing:
        print(_SESSION_LOGIN_REQUIRED_MSG)
        print(f"(sabab: environment o'zgaruvchilar yo'q: {', '.join(missing)})")
        sys.exit(3)
    return {name: os.environ[name] for name in _REQUIRED_ENV_VARS}


def _marker() -> str:
    return str(int(time.time()))


async def _timed_send_and_wait(conv, text: str, label: str):
    start = time.monotonic()
    await conv.send_message(text)
    response = await conv.get_response(timeout=_REPLY_TIMEOUT_SECONDS)
    elapsed = time.monotonic() - start
    warn = " WARN(>15s)" if elapsed > _WARN_THRESHOLD_SECONDS else ""
    print(f"STEP={label} ELAPSED_SECONDS={elapsed:.2f}{warn}")
    return response, elapsed


async def _click_and_wait(conv, message, button_text: str, label: str):
    start = time.monotonic()
    await message.click(text=button_text)
    response = await conv.get_response(timeout=_REPLY_TIMEOUT_SECONDS)
    elapsed = time.monotonic() - start
    warn = " WARN(>15s)" if elapsed > _WARN_THRESHOLD_SECONDS else ""
    print(f"STEP={label} ELAPSED_SECONDS={elapsed:.2f}{warn}")
    return response, elapsed


async def _run(config: dict[str, str]) -> bool:
    from telethon import TelegramClient
    from telethon.sessions import StringSession

    api_id = int(config["E2E_TELEGRAM_API_ID"])
    api_hash = config["E2E_TELEGRAM_API_HASH"]
    session = config["E2E_TELEGRAM_SESSION"]

    client = TelegramClient(StringSession(session), api_id, api_hash)
    await client.connect()

    if not await client.is_user_authorized():
        print(_SESSION_LOGIN_REQUIRED_MSG)
        await client.disconnect()
        return False

    me = await client.get_me()
    print(f"ROBOT_TELEGRAM_ID={me.id}")

    bot_entity = await client.get_entity(_TARGET_BOT_USERNAME)
    resolved_username = (getattr(bot_entity, "username", None) or "").lower()
    if resolved_username != _TARGET_BOT_USERNAME.lower():
        print(f"BOT_USERNAME_MISMATCH resolved={resolved_username}")
        await client.disconnect()
        return False
    print("BOT_USERNAME_MATCH=OK")

    marker = _marker()
    product_a = f"SinovPomidor-{marker}"
    product_b = f"SinovKaram-{marker}"
    print(f"MARKER={marker}")

    all_ok = True
    try:
        async with client.conversation(bot_entity, timeout=_REPLY_TIMEOUT_SECONDS) as conv:
            # 1) /sinovsmena birinchi marta
            resp1, _ = await _timed_send_and_wait(conv, "/sinovsmena", "sinovsmena_first")
            if "TEST smena boshlandi" not in (resp1.text or ""):
                print(f"FAIL=sinovsmena_first REPLY={resp1.text!r}")
                all_ok = False
                raise RuntimeError("sinovsmena_first")
            print("PASS=sinovsmena_first")

            # 2) /sinovsmena ikkinchi marta -- davom ettirish, xato bermasin
            resp2, _ = await _timed_send_and_wait(conv, "/sinovsmena", "sinovsmena_second")
            if "TEST smena boshlandi" not in (resp2.text or ""):
                print(f"FAIL=sinovsmena_second REPLY={resp2.text!r}")
                all_ok = False
                raise RuntimeError("sinovsmena_second")
            print("PASS=sinovsmena_second")

            # 3) Ikkita noyob belgilangan mahsulot -- bitta xabarda 2 qator
            list_text = f"{product_a} 2 kg\n{product_b} 3 dona"
            resp3, _ = await _timed_send_and_wait(conv, list_text, "market_list_submit")
            list_reply = resp3.text or ""
            if "Ro'yxat tayyor" not in list_reply or "Tasdiqlaysizmi?" not in list_reply:
                print(f"FAIL=market_list_submit REPLY={list_reply!r}")
                all_ok = False
                raise RuntimeError("market_list_submit")
            if product_a not in list_reply or product_b not in list_reply:
                print(f"FAIL=market_list_submit_missing_products REPLY={list_reply!r}")
                all_ok = False
                raise RuntimeError("market_list_submit_missing_products")
            print("PASS=market_list_submit")

            # 4) Real tasdiqlash tugmasini ANIQ bir marta bosish
            confirm_resp, _ = await _click_and_wait(conv, resp3, "✅ Tasdiqlash", "list_confirm")
            confirm_text = confirm_resp.text or ""
            if "2 ta mahsulot qo'shildi" not in confirm_text:
                print(f"FAIL=list_confirm REPLY={confirm_text!r}")
                all_ok = False
                raise RuntimeError("list_confirm")
            print("PASS=list_confirm SAVED_COUNT=2")

            # 5) /xarid izolyatsiya tekshiruvi
            xarid_resp, _ = await _timed_send_and_wait(conv, "/xarid", "xarid_isolation")
            xarid_text = xarid_resp.text or ""
            count_a = xarid_text.count(product_a)
            count_b = xarid_text.count(product_b)
            if count_a != 1 or count_b != 1:
                print(
                    "FAIL=xarid_isolation "
                    f"count_a={count_a} count_b={count_b} REPLY={xarid_text!r}"
                )
                all_ok = False
                raise RuntimeError("xarid_isolation")
            print(f"PASS=xarid_isolation PRODUCTS_SHOWN=2 (marker={marker})")

            # 6) /sinovtugat -- DB darajasida tozalash
            finish_resp, _ = await _timed_send_and_wait(conv, "/sinovtugat", "sinovtugat_cleanup")
            finish_text = finish_resp.text or ""
            if "yakunlandi va tozalandi" not in finish_text:
                print(f"FAIL=sinovtugat_cleanup REPLY={finish_text!r}")
                all_ok = False
                raise RuntimeError("sinovtugat_cleanup")
            print(f"PASS=sinovtugat_cleanup REPLY_SUMMARY={finish_text.strip()!r}")

            # 7) /xarid tozalashdan keyin -- aniq kutilgan xabar
            after_resp, _ = await _timed_send_and_wait(conv, "/xarid", "xarid_after_cleanup")
            after_text = after_resp.text or ""
            expected = "Faol TEST yugurish topilmadi. Avval /sinovsmena bilan boshlang."
            if expected not in after_text:
                print(f"FAIL=xarid_after_cleanup REPLY={after_text!r}")
                all_ok = False
                raise RuntimeError("xarid_after_cleanup")
            print("PASS=xarid_after_cleanup")
    except Exception as error:  # noqa: BLE001 -- istalgan kutilmagan xato ham FAIL
        all_ok = False
        print(f"SCENARIO_EXCEPTION={type(error).__name__}: {error}")
        # 8-band: muvaffaqiyatsizlikda bir martalik tozalashga urinish.
        try:
            async with client.conversation(bot_entity, timeout=_REPLY_TIMEOUT_SECONDS) as conv:
                await conv.send_message("/sinovtugat")
                cleanup_resp = await conv.get_response(timeout=_REPLY_TIMEOUT_SECONDS)
                print(f"CLEANUP_AFTER_FAILURE_REPLY={(cleanup_resp.text or '')!r}")
        except Exception as cleanup_error:  # noqa: BLE001
            print(f"CLEANUP_AFTER_FAILURE_ERROR={type(cleanup_error).__name__}: {cleanup_error}")
    finally:
        await client.disconnect()

    return all_ok


def main() -> None:
    config = _load_config()
    passed = asyncio.run(_run(config))
    print(f"SCENARIO_RESULT={'PASS' if passed else 'FAIL'}")
    print(f"FINISHED_AT_UTC={datetime.now(timezone.utc).isoformat()}")
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
