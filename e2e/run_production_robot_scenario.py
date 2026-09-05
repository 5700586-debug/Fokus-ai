"""Real Telegram orqali PRODUCTION botining (``@Xoqandiy_ai_bot``)
izolyatsiyalangan E2E test (``Sinovchi``) ssenariysini tekshiradi,
ikkinchi marta (expired-callback tuzatishi -- ``fix/list-confirm-
expired-query`` -- production'ga chiqqandan keyin):

pre-cleanup ``/sinovtugat`` -> ``/sinovsmena`` (ikki marta, davom
ettirish) -> ikkita noyob belgilangan mahsulot -> bitta tasdiqlash ->
``/xarid`` izolyatsiya tekshiruvi -> ``/sinovtugat`` -> ``/xarid``
tozalash tekshiruvi.

Faqat ``roles.E2E_TESTER_TELEGRAM_ID`` (7952886089) uchun ochiq real
xodim/ta'minotchi oqimiga UMUMAN tegmaydi. Har bir qadam qat'iy
tekshiriladi (muvaffaqiyatsizlikda darhol to'xtaydi, ``::error title=
E2E STEP <N>::...`` GitHub annotation'ini chiqaradi va ``/sinovtugat``
bilan bir martalik tozalashga urinadi). Hech qachon telefon, sessiya
qiymati, API hash yoki tokenni chop etmaydi -- faqat xavfsiz xulosa
qatorlari (vaqt, mahsulot nomlari — bular Founder tomonidan shu
skript uchun yaratilgan sinov ma'lumotlari, shaxsiy emas).

``callback.answer()`` bilan bog'liq "query is too old" xatosi endi
handler ichida darhol (DB yozuvidan OLDIN) yutiladi -- bu skript
foydalanuvchiga ko'rinadigan Telegram javoblari va o'z stdout'ida shu
matn yoki umumiy "Kutilmagan xatolik" izidan qolmaganini tekshiradi.
Bu FAQAT robot/skript darajasidagi ko'rinadigan dalil -- Render
ilova loglari bu yerdan o'qilmaydi (qarang skript oxiridagi
``RENDER_LOG_CHECK`` chiqishi).
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

# STEP 3.7: hech qachon bu matnlardan biri ham ko'rinmasin (bot
# javobida ham, skriptning o'z stdout/exception matnida ham).
_FORBIDDEN_SUBSTRINGS = (
    "Kutilmagan xatolik",
    "query is too old",
    "response timeout expired",
    "query ID is invalid",
    "TelegramBadRequest",
    "Bad Request:",
)


def _load_config() -> dict[str, str]:
    missing = [name for name in _REQUIRED_ENV_VARS if not os.getenv(name)]
    if missing:
        print(_SESSION_LOGIN_REQUIRED_MSG)
        print(f"(sabab: environment o'zgaruvchilar yo'q: {', '.join(missing)})")
        sys.exit(3)
    return {name: os.environ[name] for name in _REQUIRED_ENV_VARS}


def _marker() -> str:
    return f"E2E_{int(time.time())}"


def _fail(step_number: int, label: str, reason: str) -> None:
    sanitized = reason.replace("\n", " ")[:400]
    print(f"FAIL=STEP{step_number}_{label} REASON={sanitized!r}")
    print(f"::error title=E2E STEP {step_number}::{sanitized}")


def _check_forbidden(step_number: int, label: str, *texts: str) -> str | None:
    for text in texts:
        if not text:
            continue
        for needle in _FORBIDDEN_SUBSTRINGS:
            if needle in text:
                _fail(step_number, label, f"forbidden substring {needle!r} found in output")
                return needle
    return None


async def _timed_send_and_wait(conv, text: str, label: str):
    start = time.monotonic()
    await conv.send_message(text)
    response = await conv.get_response(timeout=_REPLY_TIMEOUT_SECONDS)
    elapsed = time.monotonic() - start
    warn = " SLOW(>15s)" if elapsed > _WARN_THRESHOLD_SECONDS else ""
    print(f"STEP={label} ELAPSED_SECONDS={elapsed:.2f}{warn}")
    return response, elapsed


async def _click_and_wait(conv, message, button_text: str, label: str):
    start = time.monotonic()
    await message.click(text=button_text)
    response = await conv.get_response(timeout=_REPLY_TIMEOUT_SECONDS)
    elapsed = time.monotonic() - start
    warn = " SLOW(>15s)" if elapsed > _WARN_THRESHOLD_SECONDS else ""
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
    product_a = f"Sinov pomidor {marker}"
    product_b = f"Sinov karam {marker}"
    print(f"MARKER={marker}")

    all_ok = True
    try:
        async with client.conversation(bot_entity, timeout=_REPLY_TIMEOUT_SECONDS) as conv:
            # 1) Xavfsiz pre-cleanup -- oldingi urinishdan qolgan faol
            # TEST yugurish bo'lsa ham, yo'q bo'lsa ham ikkalasi PASS.
            pre_resp, _ = await _timed_send_and_wait(conv, "/sinovtugat", "pre_cleanup")
            pre_text = pre_resp.text or ""
            if _check_forbidden(1, "pre_cleanup", pre_text):
                all_ok = False
                raise RuntimeError("pre_cleanup_forbidden_text")
            if "Faol TEST smena topilmadi" not in pre_text and "yakunlandi va tozalandi" not in pre_text:
                _fail(1, "pre_cleanup", f"unexpected reply: {pre_text!r}")
                all_ok = False
                raise RuntimeError("pre_cleanup")
            print("PASS=STEP1_pre_cleanup")

            # 2) /sinovsmena ikki marta -- ``start_test_shift`` DB
            # darajasida idempotent (mavjud bo'lsa ANIQ o'sha
            # shift/test_run_id'ni qaytaradi, hech qachon yangisini
            # yaratmaydi -- qarang services/e2e_test_access.py). Bot
            # javobi ikkala holatda ham bir xil statik matn bo'lgani
            # uchun (shift/run ID Telegram javobida ko'rsatilmaydi),
            # shu yerdan faqat IKKALA chaqiruv ham xuddi shu
            # muvaffaqiyatli matnni qaytarganini tekshirish mumkin --
            # "bir xil smena/yugurish" kafolati DB darajasida kod bilan
            # ta'minlangan, bu skript uni to'g'ridan-to'g'ri DB'dan
            # solishtirmaydi (ruxsat yo'q).
            resp1, _ = await _timed_send_and_wait(conv, "/sinovsmena", "sinovsmena_first")
            text1 = resp1.text or ""
            if _check_forbidden(2, "sinovsmena_resume", text1):
                all_ok = False
                raise RuntimeError("sinovsmena_first_forbidden_text")
            if "TEST smena boshlandi" not in text1:
                _fail(2, "sinovsmena_resume", f"first call unexpected reply: {text1!r}")
                all_ok = False
                raise RuntimeError("sinovsmena_first")

            resp2, _ = await _timed_send_and_wait(conv, "/sinovsmena", "sinovsmena_second")
            text2 = resp2.text or ""
            if _check_forbidden(2, "sinovsmena_resume", text2):
                all_ok = False
                raise RuntimeError("sinovsmena_second_forbidden_text")
            if "TEST smena boshlandi" not in text2:
                _fail(2, "sinovsmena_resume", f"second call unexpected reply: {text2!r}")
                all_ok = False
                raise RuntimeError("sinovsmena_second")
            if text1 != text2:
                _fail(2, "sinovsmena_resume", f"replies differ: first={text1!r} second={text2!r}")
                all_ok = False
                raise RuntimeError("sinovsmena_resume_mismatch")
            print("PASS=STEP2_sinovsmena_resume (both calls identical success reply)")

            # 3) Ikkita noyob belgilangan mahsulot -- bitta xabarda 2 qator
            list_text = f"{product_a} 2 kg\n{product_b} 3 dona"
            resp3, _ = await _timed_send_and_wait(conv, list_text, "market_list_submit")
            list_reply = resp3.text or ""
            if _check_forbidden(3, "market_list_submit", list_reply):
                all_ok = False
                raise RuntimeError("market_list_submit_forbidden_text")
            if "Ro'yxat tayyor" not in list_reply or "Tasdiqlaysizmi?" not in list_reply:
                _fail(3, "market_list_submit", f"unexpected reply: {list_reply!r}")
                all_ok = False
                raise RuntimeError("market_list_submit")
            if product_a not in list_reply or product_b not in list_reply:
                _fail(3, "market_list_submit", f"marker products missing from reply: {list_reply!r}")
                all_ok = False
                raise RuntimeError("market_list_submit_missing_products")
            print("PASS=STEP3_market_list_submit")

            # 4) Real tasdiqlash tugmasini ANIQ bir marta bosish --
            # aynan shu bosish expired-callback ssenariysini yuzaga
            # chiqargan real hodisa edi.
            confirm_resp, _ = await _click_and_wait(conv, resp3, "✅ Tasdiqlash", "list_confirm")
            confirm_text = confirm_resp.text or ""
            if _check_forbidden(4, "list_confirm", confirm_text):
                all_ok = False
                raise RuntimeError("list_confirm_forbidden_text")
            if "✅ TEST: 2 ta mahsulot qo'shildi" not in confirm_text:
                _fail(4, "list_confirm", f"unexpected reply: {confirm_text!r}")
                all_ok = False
                raise RuntimeError("list_confirm")
            print("PASS=STEP4_list_confirm SAVED_COUNT=2")

            # 5) /xarid izolyatsiya tekshiruvi -- ikkala marker aynan
            # bir marta ko'rinishi, dublikat yoki begona (marker'siz)
            # qator bo'lmasligi kerak.
            xarid_resp, _ = await _timed_send_and_wait(conv, "/xarid", "xarid_isolation")
            xarid_text = xarid_resp.text or ""
            if _check_forbidden(5, "xarid_isolation", xarid_text):
                all_ok = False
                raise RuntimeError("xarid_isolation_forbidden_text")
            count_a = xarid_text.count(product_a)
            count_b = xarid_text.count(product_b)
            if count_a != 1 or count_b != 1:
                _fail(
                    5, "xarid_isolation",
                    f"count_a={count_a} count_b={count_b} REPLY={xarid_text!r}",
                )
                all_ok = False
                raise RuntimeError("xarid_isolation")
            print(f"PASS=STEP5_xarid_isolation PRODUCTS_SHOWN=2 (marker={marker})")

            # 6) /sinovtugat -- DB darajasida tozalash
            finish_resp, _ = await _timed_send_and_wait(conv, "/sinovtugat", "sinovtugat_cleanup")
            finish_text = finish_resp.text or ""
            if _check_forbidden(6, "sinovtugat_cleanup", finish_text):
                all_ok = False
                raise RuntimeError("sinovtugat_cleanup_forbidden_text")
            if "yakunlandi va tozalandi" not in finish_text:
                _fail(6, "sinovtugat_cleanup", f"unexpected reply: {finish_text!r}")
                all_ok = False
                raise RuntimeError("sinovtugat_cleanup")
            print(f"PASS=STEP6_sinovtugat_cleanup REPLY_SUMMARY={finish_text.strip()!r}")

            # 7) /xarid tozalashdan keyin -- aniq kutilgan xabar
            after_resp, _ = await _timed_send_and_wait(conv, "/xarid", "xarid_after_cleanup")
            after_text = after_resp.text or ""
            if _check_forbidden(7, "xarid_after_cleanup", after_text):
                all_ok = False
                raise RuntimeError("xarid_after_cleanup_forbidden_text")
            expected = "Faol TEST yugurish topilmadi"
            if expected not in after_text:
                _fail(7, "xarid_after_cleanup", f"unexpected reply: {after_text!r}")
                all_ok = False
                raise RuntimeError("xarid_after_cleanup")
            print("PASS=STEP7_xarid_after_cleanup")
    except Exception as error:  # noqa: BLE001 -- istalgan kutilmagan xato ham FAIL
        all_ok = False
        print(f"SCENARIO_EXCEPTION={type(error).__name__}: {error}")
        # STEP 5.1: muvaffaqiyatsizlikda bir martalik tozalashga urinish.
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
    print("RENDER_LOG_CHECK=UNAVAILABLE (Render application logs were not read by this script)")
    print(f"FINISHED_AT_UTC={datetime.now(timezone.utc).isoformat()}")
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
