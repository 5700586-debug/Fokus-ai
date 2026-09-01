"""Real Telegram orqali ``fokus-ai-test`` botining NAZORATCHI kunlik
nazorat oqimini E2E tekshiruvchi skript: filial -> xodim -> karta ->
vazifalar -> ISH BAHOSI (0/1/2/3) -> ball ayirish -> xodimga xabar ->
"✋ E'tirozim bor" -> sabab -> apellyatsiya ochilishi.

Bu ``e2e/run_e2e.py``/``e2e/run_recruiting_e2e.py`` bilan bir xil
credential/xavfsizlik qoidalariga bo'ysunadi. "Xodimga xabar ->
e'tiroz" qadami REAL, ikkinchi Telegram akkaunt talab qiladigan
qadam bo'lgani uchun, skript avval ``/e2exodim`` (faqat
``ENVIRONMENT == "test"``da, Founder-only, qarang
``nazoratchi_bot.py``) buyrug'i orqali shu test akkauntning O'ZINI
tasdiqlangan xodim sifatida ro'yxatga qo'shadi — shundan keyin
"tanlangan xodim" ANIQ shu test akkaunt bo'lishi KAFOLATLANADI,
moslashuvchan/BLOCKED yo'l yo'q: agar xabar/e'tiroz qadami ishlamasa,
bu HAQIQIY FAILURE.

Nizom bandi: skript o'zining vaqtinchalik nizom bandini
(``_E2E_RULE_NUMBER``) ``/addnizom``+``/setnizombahosi`` orqali
tayyorlaydi (idempotent — ``INSERT OR IGNORE``) — Founderning haqiqiy
nizomlariga tegilmaydi, faqat qo'shimcha, ajratilgan raqam ishlatiladi.
"""

import asyncio
import os
import sys
from datetime import datetime, timezone

_REQUIRED_ENV_VARS = (
    "E2E_TELEGRAM_API_ID",
    "E2E_TELEGRAM_API_HASH",
    "E2E_TELEGRAM_SESSION",
    "E2E_TEST_BOT_USERNAME",
)

_E2E_RULE_NUMBER = 900001
_E2E_RULE_TITLE = "E2E Sinov Nizomi"
_E2E_RULE_AMOUNT = 30


class StepFailed(Exception):
    pass


def _load_config() -> dict[str, str]:
    missing = [name for name in _REQUIRED_ENV_VARS if not os.getenv(name)]
    if missing:
        print(
            "❌ Nazoratchi E2E ishga tushmadi — quyidagi environment o'zgaruvchilar "
            f"yo'q yoki bo'sh: {', '.join(missing)}."
        )
        sys.exit(2)
    return {name: os.environ[name] for name in _REQUIRED_ENV_VARS}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3]


def _extract_inline_buttons(message) -> list[tuple[str, bytes | None]]:
    reply_markup = getattr(message, "reply_markup", None)
    rows = getattr(reply_markup, "rows", None)
    if not rows:
        return []
    pairs = []
    for row in rows:
        for button in getattr(row, "buttons", []):
            text = getattr(button, "text", None)
            data = getattr(button, "data", None)
            if text:
                pairs.append((text, data))
    return pairs


def _assert_contains(response, *expected: str) -> None:
    text = response.text or ""
    for needle in expected:
        if needle not in text:
            raise StepFailed(f"Matnda {needle!r} topilmadi. Haqiqiy javob: {text!r}")


async def _send_and_wait(conv, text: str, *, timeout: int = 25):
    print(f"[{_now()}] → yuborilmoqda: {text!r}")
    await conv.send_message(text)
    response = await conv.get_response(timeout=timeout)
    print(f"[{_now()}] ← qabul qilindi: {(response.text or '<matnsiz>')!r}")
    return response


async def _click_contains(conv, response, needle: str, *, timeout: int = 25):
    buttons = _extract_inline_buttons(response)
    match = next(((text, data) for text, data in buttons if needle in text and data), None)
    if match is None:
        raise StepFailed(f"Tugma topilmadi: {needle!r}. Mavjud tugmalar: {[t for t, _ in buttons]!r}")
    text, data = match
    print(f"[{_now()}] → tugma bosilmoqda: {text!r}")
    await response.click(data=data)
    next_response = await conv.get_response(timeout=timeout)
    print(f"[{_now()}] ← qabul qilindi: {(next_response.text or '<matnsiz>')!r}")
    return next_response


async def _ensure_e2e_rule(conv) -> None:
    """Vaqtinchalik, ajratilgan nizom bandini tayyorlaydi (idempotent —
    ``/addnizom`` allaqachon mavjud raqamda "band" deb javob bersa ham
    xato emas, keyingi qadam baribir ``/setnizombahosi`` bilan miqdorni
    to'g'irlaydi)."""
    await _send_and_wait(
        conv, f"/addnizom {_E2E_RULE_NUMBER} {_E2E_RULE_TITLE} | E2E avtomatik testi uchun vaqtinchalik nizom"
    )
    response = await _send_and_wait(conv, f"/setnizombahosi {_E2E_RULE_NUMBER} {_E2E_RULE_AMOUNT}")
    if "standart ball" not in (response.text or ""):
        raise StepFailed(f"/setnizombahosi kutilmagan javob berdi: {response.text!r}")


_BOOTSTRAP_EMPLOYEE_LABEL_NEEDLE = "E2E Sinov"


async def _open_bootstrapped_employee_card(conv):
    """``/e2exodim`` orqali tayyorlangan xodimni (shu test akkauntning
    o'zi) filial ro'yxatidagi BIRINCHI (index 0) filialdan aniq
    topadi va uning kartasini ochadi — moslashuvchan/BLOCKED emas,
    chunki ``/e2exodim`` shu aniq filialga aniq shu nomdagi xodimni
    kafolatlab qo'yadi."""
    response = await _send_and_wait(conv, "/filiallar")
    branch_buttons = _extract_inline_buttons(response)
    if not branch_buttons:
        raise StepFailed(f"/filiallar hech qanday filial tugmasi bermadi: {response.text!r}")

    branch_text, branch_data = branch_buttons[0]
    print(f"[{_now()}] → filial ochilmoqda: {branch_text!r}")
    await response.click(data=branch_data)
    list_response = await conv.get_response(timeout=25)
    print(f"[{_now()}] ← {(list_response.text or '<matnsiz>')!r}")

    employee_buttons = _extract_inline_buttons(list_response)
    match = next(
        (data for text, data in employee_buttons if _BOOTSTRAP_EMPLOYEE_LABEL_NEEDLE in text and data),
        None,
    )
    if match is None:
        raise StepFailed(
            f"/e2exodim orqali tayyorlangan xodim ({_BOOTSTRAP_EMPLOYEE_LABEL_NEEDLE!r}) birinchi filial "
            f"ro'yxatida topilmadi. Mavjud tugmalar: {[t for t, _ in employee_buttons]!r}"
        )

    print(f"[{_now()}] → xodim tugmasi bosilmoqda (bootstrap qilingan, shu test akkaunt).")
    await list_response.click(data=match)
    card = await conv.get_response(timeout=25)
    print(f"[{_now()}] ← {(card.text or '<matnsiz>')!r}")
    return card


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
        print("❌ Telethon sessiyasi haqiqiy emas yoki muddati o'tgan.")
        await client.disconnect()
        return False

    print(f"➡️  Ulanish o'rnatildi. Bot: @{bot_username}. Ssenariy: NAZORATCHI tugma oqimi.\n")

    try:
        async with client.conversation(bot_username, timeout=25) as conv:
            await _ensure_e2e_rule(conv)

            bootstrap = await _send_and_wait(conv, "/e2exodim")
            _assert_contains(bootstrap, "tayyorlandi")
            print(f"[{_now()}] ✅ E2E sinov xodimi (shu test akkaunt) tayyorlandi.")

            card = await _open_bootstrapped_employee_card(conv)
            _assert_contains(card, "Lavozim:", "Filial:", "Doimiy vazifalar", "vaqt bonusi", "ish bahosi")
            print(f"[{_now()}] ✅ Xodim kartasi ko'rindi (vazifalar/vaqt bonusi/ish bahosi bo'limlari bilan).")

            card = await _click_contains(conv, card, "2")
            _assert_contains(card, "2 (Norma)")
            print(f"[{_now()}] ✅ ISH BAHOSI (0/1/2/3) — '2' bosilgach karta yangilandi.")

            card = await _click_contains(conv, card, "Ball ayirish")
            buttons = _extract_inline_buttons(card)
            rule_button_present = any(
                data and data.startswith(b"nzr_penalty_apply:") and _E2E_RULE_TITLE in text for text, data in buttons
            )
            if not rule_button_present:
                raise StepFailed(
                    f"E2E nizom bandi ({_E2E_RULE_TITLE}) 'Ball ayirish' ro'yxatida topilmadi. "
                    f"Mavjud tugmalar: {[t for t, _ in buttons]!r}"
                )

            card = await _click_contains(conv, card, _E2E_RULE_TITLE)
            _assert_contains(card, f"-{_E2E_RULE_AMOUNT} ball ayirildi")
            print(f"[{_now()}] ✅ MINUS BALL — '{_E2E_RULE_TITLE}' bosilgach -{_E2E_RULE_AMOUNT} ball qo'llandi.")

            # /e2exodim tanlangan xodimni ANIQ shu test akkaunt sifatida
            # kafolatlaydi — shuning uchun bu qadam endi moslashuvchan/
            # BLOCKED emas, majburiy tekshiruv: xabar shu chatga
            # kelmasa, bu haqiqiy FAILURE.
            notice = await conv.get_response(timeout=20)
            print(f"[{_now()}] ✅ XODIM XABARI — shu chatga keldi.")
            _assert_contains(notice, f"-{_E2E_RULE_AMOUNT} ball ayirildi")
            notice_buttons = _extract_inline_buttons(notice)
            has_ack = any(data and data.startswith(b"nzr_ack:") for _, data in notice_buttons)
            has_appeal = any(data and data.startswith(b"nzr_appeal:") for _, data in notice_buttons)
            if not (has_ack and has_appeal):
                raise StepFailed(
                    f"Xodim xabarida Tushundim/E'tirozim tugmalari yo'q: {[t for t, _ in notice_buttons]!r}"
                )

            reason_prompt = await _click_contains(conv, notice, "E'tirozim")
            _assert_contains(reason_prompt, "Sababingizni")
            print(f"[{_now()}] ✅ E'TIROZIM BOR — bosilgach sabab so'raldi.")

            appeal_ack = await _send_and_wait(conv, "E2E test e'tirozi — bu avtomatik sinov.")
            print(f"[{_now()}] ✅ APELLYATSIYA OCHILDI — sabab yuborilgach javob: {appeal_ack.text!r}")

    except StepFailed as error:
        print(f"\n❌ FAILED — {error}")
        await client.disconnect()
        return False
    except Exception as error:  # noqa: BLE001
        print(f"\n❌ FAILED — kutilmagan xato: {type(error).__name__}: {error}")
        await client.disconnect()
        return False

    await client.disconnect()
    return True


def main() -> None:
    config = _load_config()
    passed = asyncio.run(_run(config))

    if passed:
        print("\n✅ Nazoratchi E2E ssenariy TO'LIQ PASSED.")
        sys.exit(0)

    print("\n❌ Nazoratchi E2E ssenariy FAILED.")
    sys.exit(1)


if __name__ == "__main__":
    main()
