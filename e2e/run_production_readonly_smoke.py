"""PRODUCTION (``@Xoqandiy_ai_bot``) uchun doimiy, FAQAT QO'LDA ishga tushadigan read-only smoke E2E.

Faqat ``.github/workflows/production_readonly_smoke_e2e.yml`` (``workflow_dispatch``) orqali ishlaydi.
Production ma'lumotini O'ZGARTIRMAYDI — bu skript KODDA majburiy (``e2e/readonly_guard.py``):
faqat ``/start``, ``/baholash``, ``/kunniyop`` va "🧑‍💼 Nazoratchi" menyu tugmasi yuboriladi; faqat filial
tanlash callback'i bosiladi; baho/yopish/tasdiqlash/ha-yo'q/jarima/minus hech qachon bosilmaydi.

Eski vaqtinchalik ``1413da9`` skriptidan farqi: u ``/sinovtugat``/``/sinovsmena`` (izolyatsiyalangan,
lekin YOZADIGAN sinov qatorlari) ishlatgan — bu skript ularni UMUMAN yubormaydi (guard bloklaydi).

Kerakli environment (qiymatlar HECH QACHON chop etilmaydi; ``_log`` ularni yashiradi):
- E2E_TELEGRAM_API_ID, E2E_TELEGRAM_API_HASH, E2E_TELEGRAM_SESSION (Telethon StringSession —
  to'liq akkaunt kaliti!). Ixtiyoriy: SMOKE_REQUIRE_NAZORATCHI=1 (nazoratchi tekshiruvlari
  o'tkazib yuborilsa FAIL).

Natija: tester hisobi productionda rolsiz bo'lsa (``roles.get_role`` -> None, loyiha dizayni) bot
"begona" javob beradi — bu holatda faqat jonlilik va ruxsat himoyasi tekshiriladi, nazoratchi
oqimi SKIPPED deb ochiq yoziladi (PASS deb ko'rsatilmaydi).
"""

import asyncio
import os
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from e2e import readonly_guard as guard

_REQUIRED_ENV_VARS = ("E2E_TELEGRAM_API_ID", "E2E_TELEGRAM_API_HASH", "E2E_TELEGRAM_SESSION")
_REPLY_TIMEOUT_SECONDS = 45
_COMPANY_TIMEZONE = "Asia/Tashkent"

_SECRETS: list[str] = []


def _log(message: str) -> None:
    print(guard.redact(message, _SECRETS))


def _load_config() -> dict[str, str]:
    missing = [name for name in _REQUIRED_ENV_VARS if not os.getenv(name)]
    if missing:
        print(f"CONFIG_MISSING: {', '.join(missing)}")
        sys.exit(3)
    config = {name: os.environ[name] for name in _REQUIRED_ENV_VARS}
    _SECRETS.extend(config.values())
    return config


def _today_ymd() -> str:
    return datetime.now(ZoneInfo(_COMPANY_TIMEZONE)).strftime("%Y%m%d")


def _button_texts(message) -> list[str]:
    texts: list[str] = []
    markup = getattr(message, "reply_markup", None)
    for row in getattr(markup, "rows", None) or []:
        for button in getattr(row, "buttons", None) or []:
            if getattr(button, "text", None):
                texts.append(button.text)
    return texts


def _inline_buttons(message) -> list:
    buttons = []
    markup = getattr(message, "reply_markup", None)
    for row in getattr(markup, "rows", None) or []:
        buttons.extend(getattr(row, "buttons", None) or [])
    return buttons


def _fail(step: str, reason: str) -> bool:
    safe = reason.replace("\n", " ")[:300]
    _log(f"FAIL={step} REASON={safe!r}")
    print(f"::error title=PROD SMOKE {step}::{guard.redact(safe, _SECRETS)}")
    return False


# --- Botga YAGONA chiqish yo'llari: har biri guard'dan o'tadi (boshqa .send_message/.click chaqiruvi yo'q) ---


async def _guarded_send(conv, text: str):
    guard.check_outbound_text(text)
    await conv.send_message(text)
    return await conv.get_response(timeout=_REPLY_TIMEOUT_SECONDS)


async def _guarded_click(client, bot_entity, message, button):
    data = getattr(button, "data", None)
    guard.check_callback(data, getattr(button, "text", ""), _today_ymd())
    await message.click(data=data)
    for _ in range(20):  # bot xabarni tahrirlaydi (edit_message_text) — yangilangan holatini o'qiymiz
        await asyncio.sleep(1)
        refreshed = await client.get_messages(bot_entity, ids=message.id)
        if refreshed is not None and refreshed.text != message.text:
            return refreshed
    return await client.get_messages(bot_entity, ids=message.id)


def _check_reply(step: str, reply) -> bool:
    forbidden = guard.find_forbidden_reply_text(reply.text)
    if forbidden:
        return _fail(step, f"taqiqlangan matn {forbidden!r} topildi")
    ui_word = guard.find_forbidden_ui_word([reply.text or ""] + _button_texts(reply))
    if ui_word:
        return _fail(step, f"inglizcha/tushunarsiz so'z: {ui_word}")
    return True


async def _run(config: dict[str, str]) -> int:
    from telethon import TelegramClient
    from telethon.sessions import StringSession

    client = TelegramClient(StringSession(config["E2E_TELEGRAM_SESSION"]), int(config["E2E_TELEGRAM_API_ID"]),
                            config["E2E_TELEGRAM_API_HASH"])
    await client.connect()
    try:
        if not await client.is_user_authorized():
            _fail("SESSION", "session faol emas (qayta login kerak)")
            return 3

        me = await client.get_me()
        _log(f"ROBOT_TELEGRAM_ID={me.id}")
        if me.id != guard.EXPECTED_TESTER_TELEGRAM_ID:
            _fail("TESTER_ID", "session kutilgan E2E tester hisobi emas — TO'XTATILDI, hech narsa yuborilmadi")
            return 4

        bot_entity = await client.get_entity(guard.TARGET_BOT_USERNAME)
        resolved = (getattr(bot_entity, "username", None) or "").lower()
        if resolved != guard.TARGET_BOT_USERNAME.lower():
            _fail("BOT_USERNAME", f"kutilgan @{guard.TARGET_BOT_USERNAME}, topilgan @{resolved} — TO'XTATILDI")
            return 4
        _log("BOT_USERNAME_MATCH=OK")

        try:
            ok, summary = await _scenario(client, bot_entity)
        except guard.ReadOnlyViolation as violation:
            _fail("READ_ONLY_GUARD", str(violation))
            return 5
        for line in summary:
            _log(line)
        return 0 if ok else 1
    finally:
        await client.disconnect()


async def _scenario(client, bot_entity) -> tuple[bool, list[str]]:
    require_nazoratchi = os.getenv("SMOKE_REQUIRE_NAZORATCHI", "").lower() in {"1", "true", "yes"}
    summary: list[str] = []

    async with client.conversation(bot_entity, timeout=_REPLY_TIMEOUT_SECONDS) as conv:
        start = await _guarded_send(conv, "/start")
        if not _check_reply("START", start):
            return False, summary
        role = guard.classify_start_reply(start.text, _button_texts(start))
        _log(f"ROLE_MODE={role}")
        if role == guard.ROLE_FOUNDER:
            return _fail("TESTER_ROLE", "tester Asoschi roliga ega ko'rinadi — xavfli, TO'XTATILDI"), summary
        summary.append("PASS=START_REPLY")

        baholash = await _guarded_send(conv, "/baholash")
        if not _check_reply("BAHOLASH", baholash):
            return False, summary

        if guard.is_denial(baholash.text):
            # Rolsiz tester: ruxsat himoyasi ishlayapti, nazoratchi oqimi tekshirilmaydi (SKIPPED).
            kunniyop = await _guarded_send(conv, "/kunniyop")
            if not _check_reply("KUNNIYOP", kunniyop):
                return False, summary
            if not guard.is_denial(kunniyop.text):
                return _fail("KUNNIYOP", f"rolsiz akkauntga kutilmagan javob: {kunniyop.text!r}"), summary
            summary += [
                "PASS=PERMISSION_GATE (/baholash va /kunniyop rolsiz tester uchun rad etildi)",
                "NAZORATCHI_CHECKS=SKIPPED (tester productionda nazoratchi roliga ega emas — nazoratchi oqimi TEKSHIRILMADI)",
            ]
            print("::warning title=PROD SMOKE::nazoratchi oqimi tekshirilmadi (tester rolsiz)")
            return (not require_nazoratchi) or _fail("NAZORATCHI_REQUIRED", "nazoratchi tekshiruvlari SKIPPED"), summary

        # Nazoratchi rolli tester: menyu -> /baholash -> bitta filial ro'yxati -> /kunniyop (hech narsa bosilmaydi).
        menu = await _guarded_send(conv, "🧑‍💼 Nazoratchi")
        if not _check_reply("MENU", menu):
            return False, summary
        labels = _button_texts(menu)
        missing = [label for label in guard.EXPECTED_MENU_LABELS if label not in labels]
        if missing:
            return _fail("MENU", f"menyuda yo'q: {missing}; bor: {labels}"), summary
        summary.append("PASS=NAZORATCHI_MENU")

        if "Avval filialni tanlang" not in (baholash.text or ""):
            return _fail("BAHOLASH", f"filial tanlash chiqmadi: {baholash.text!r}"), summary
        summary.append("PASS=BAHOLASH_BRANCH_PICKER")

        branch_buttons = [b for b in _inline_buttons(baholash) if str(getattr(b, "text", "")).startswith("📍")]
        if not branch_buttons:
            return _fail("BAHOLASH", "filial tugmalari yo'q"), summary
        screen = await _guarded_click(client, bot_entity, baholash, branch_buttons[0])
        if not _check_reply("BRANCH_SCREEN", screen):
            return False, summary
        valid, reason = guard.status_lines_are_valid(screen.text or "")
        if not valid:
            return _fail("BRANCH_SCREEN", reason), summary
        summary.append("PASS=BRANCH_EMPLOYEE_LIST (faqat ko'rildi, hech narsa bosilmadi)")

        kunniyop = await _guarded_send(conv, "/kunniyop")
        if not _check_reply("KUNNIYOP", kunniyop):
            return False, summary
        if "Qaysi filial nazoratini yopamiz" not in (kunniyop.text or "") and "tugallanmagan" not in (kunniyop.text or ""):
            return _fail("KUNNIYOP", f"kutilmagan javob: {kunniyop.text!r}"), summary
        summary.append("PASS=KUNNIYOP_PICKER (tugmalar bosilmadi, hech narsa yopilmadi)")
    return True, summary


def main() -> int:
    config = _load_config()
    started = time.monotonic()
    code = asyncio.run(_run(config))
    _log(f"SMOKE_EXIT={code} ELAPSED={time.monotonic() - started:.1f}s")
    return code


if __name__ == "__main__":
    sys.exit(main())
