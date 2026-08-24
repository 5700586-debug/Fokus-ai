"""Real Telegram orqali ``fokus-ai-test`` botining RECRUITING (nomzod/
rezyume) tugma oqimini E2E tekshiruvchi skript.

Bu ``e2e/run_e2e.py`` bilan bir xil credential/xavfsizlik qoidalariga
bo'ysunadi (qarang o'sha faylning docstringi) — faqat ssenariysi
butunlay boshqa, shuning uchun alohida fayl: bu yerda gaplashiladigan
tugmalar ReplyKeyboard EMAS, balki ``callback_data``li INLINE tugmalar
(``recruiting_bot.py``), shuning uchun ``e2e/scenario.py``dagi oddiy
matn-yuborish/matn-taqqoslash naqshi mos kelmaydi.

MUHIM taxmin: ``fokus-ai-test``ning o'z ``FOUNDER_ID``si aynan shu E2E
test Telegram akkaunti (qarang ``e2e/README.md``) — shuning uchun
BITTA akkaunt orqali ham nomzod (ariza beruvchi), ham Founder (qaror
qabul qiluvchi) rolini bir xil chatda ketma-ket sinash mumkin, yangi
login/akkaunt kerak emas.

Ataylab MISMATCH yo'li: tug'ilgan sana yoshni haqiqiy minimal yoshdan
ancha kichik qilib beriladi (``services/recruiting_fit.py``dagi
``check_min_age``) — bu B/C bo'limi (11 ta savol) tugagach darhol
"moslik filtri" MISMATCH natijasi berishini KAFOLATLAYDI, D bo'limi
(~10 ta qo'shimcha erkin matn savoli)/rol savollari/matematik
savol/motivatsiya/foto butunlay o'tkazib yuboriladi va suhbat qisqa,
tez hamda DETERMINISTIK tarzda Founder kartasiga yetib boradi.
Shuning uchun bu skript "matematik savol" tugmasini SINAMAYDI — u
faqat MOS kelgan, D bo'limi + AI-asosli follow-up'larga bog'liq
uzoq yo'lda chiqadi (o'zi flaky bo'lardi, deterministik emas).

``rec_hire`` tugmasi ATAYLAB bosilmaydi — bu chinakam
``employees``/``roles`` yozuvi yaratadi, aynan shu FOUNDER_ID ustida
(chunki shu bitta test akkaunt ham nomzod, ham Founder) — bu sinov
muhitidagi Founder rol/xodim yozuvini kutilmagan tarzda o'zgartirishi
mumkin. Buning o'rniga: holat o'zgartirmaydigan ``rec_question``/
``rec_raw`` tugmalari, keyin BITTA status-o'zgartiruvchi qaror
(``rec_interview``), so'ng xuddi shu arizaga IKKINCHI qaror
(``rec_reject``) — bu atomik race-guard bloklashi kerak (qarang
``recruiting_bot.py::_handle_founder_decision``). ``rec_vac_toggle``
alohida, ariza-mustaqil tekshiriladi va ikki marta bosilib ASL
holatiga qaytariladi (yon ta'sir qoldirilmaydi).
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


class StepFailed(Exception):
    pass


def _load_config() -> dict[str, str]:
    missing = [name for name in _REQUIRED_ENV_VARS if not os.getenv(name)]
    if missing:
        print(
            "❌ Recruiting E2E ishga tushmadi — quyidagi environment o'zgaruvchilar "
            f"yo'q yoki bo'sh: {', '.join(missing)}."
        )
        sys.exit(2)
    return {name: os.environ[name] for name in _REQUIRED_ENV_VARS}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3]


def _extract_inline_buttons(message) -> list[tuple[str, bytes | None]]:
    """(matn, raw callback_data bytes) juftliklari — faqat inline
    keyboard (reply keyboard emas, unda callback_data yo'q)."""
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


async def _click_first(conv, response, *, timeout: int = 25):
    """Javobdagi BIRINCHI mavjud tugmani bosadi (aniq matn muhim
    bo'lmagan hollarda — masalan filial nomi muhitga qarab farq
    qilishi mumkin) va keyingi YANGI xabarni kutadi."""
    buttons = _extract_inline_buttons(response)
    if not buttons:
        raise StepFailed(f"Kutilgan tugmalar topilmadi. Xabar: {response.text!r}")
    text, data = buttons[0]
    print(f"[{_now()}] → tugma bosilmoqda (birinchi variant): {text!r}")
    await response.click(data=data)
    next_response = await conv.get_response(timeout=timeout)
    print(f"[{_now()}] ← qabul qilindi: {(next_response.text or '<matnsiz>')!r}")
    return next_response


async def _click_contains(conv, response, needle: str, *, timeout: int = 25):
    """Matnida ``needle``ni o'z ichiga olgan tugmani bosadi va
    keyingi YANGI xabarni kutadi (tugma bosilgach yangi matn keladigan
    hollar uchun — masalan savol qadamlari)."""
    buttons = _extract_inline_buttons(response)
    match = next(((text, data) for text, data in buttons if needle in text and data), None)
    if match is None:
        raise StepFailed(
            f"Tugma topilmadi: {needle!r}. Mavjud tugmalar: {[t for t, _ in buttons]!r}"
        )
    text, data = match
    print(f"[{_now()}] → tugma bosilmoqda: {text!r}")
    await response.click(data=data)
    next_response = await conv.get_response(timeout=timeout)
    print(f"[{_now()}] ← qabul qilindi: {(next_response.text or '<matnsiz>')!r}")
    return next_response


async def _click_toast(message, data: bytes, *, label: str) -> str | None:
    """Faqat toast/alert qaytaradigan tugma uchun (masalan Founder
    qaror tugmalari) — YANGI chat xabari kutilmaydi, chunki bunday
    handlerlar ``callback.answer(...)`` (toast) chiqaradi va (agar
    bo'lsa) mavjud xabarning ``reply_markup``ini tahrirlaydi, YANGI
    xabar YUBORMAYDI."""
    print(f"[{_now()}] → tugma bosilmoqda (toast kutilmoqda): {label!r}")
    result = await message.click(data=data)
    toast = getattr(result, "message", None)
    print(f"[{_now()}] ← toast: {toast!r}")
    return toast


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
            "E2E_TELEGRAM_SESSION qiymatini qayta generatsiya qilish kerak."
        )
        await client.disconnect()
        return False

    print(f"➡️  Ulanish o'rnatildi. Bot: @{bot_username}. Ssenariy: RECRUITING tugma oqimi.\n")

    try:
        async with client.conversation(bot_username, timeout=25) as conv:
            # 0) Himoya: oldingi (masalan yarim tugatilgan/qulagan) test
            # ariza qolib ketgan bo'lsa, /apply "davom ettiramiz" holatiga
            # tushib, ssenariyni buzishi mumkin — /cancel har doim
            # xavfsiz javob beradi (ariza bo'lmasa ham).
            await _send_and_wait(conv, "/cancel")

            # 1) /apply -> rozilik so'rovi
            response = await _send_and_wait(conv, "/apply")
            _assert_contains(response, "Boshlaymizmi")

            # 2) "✅ Boshlash" -> vakansiya tanlash ekrani
            response = await _click_contains(conv, response, "Boshlash")
            _assert_contains(response, "lavozimga ariza")

            # 3) Vakansiya — birinchi mavjud variant
            response = await _click_first(conv, response)

            # 4) full_name
            response = await _send_and_wait(conv, "Test Nomzod E2E")
            # 5) birth_date — ATAYLAB juda yosh (MISMATCH kafolatlanadi)
            response = await _send_and_wait(conv, "01.01.2016")
            # 6) phone
            response = await _send_and_wait(conv, "+998901234567")
            # 7) residence_area
            response = await _send_and_wait(conv, "Toshkent")
            # 8) preferred_branch — birinchi filial (aniq nom muhitga bog'liq)
            response = await _click_first(conv, response)
            # 9) start_date
            response = await _send_and_wait(conv, "Ertaga")
            # 10) shift_preference — "Farqi yo'q" (faqat YOSH mismatch
            # sinalishi uchun, boshqa mismatch turi aralashmasin)
            response = await _click_contains(conv, response, "Farqi")
            # 11) holiday_available — "Ha"
            response = await _click_contains(conv, response, "Ha")
            # 12) prev_salary
            response = await _send_and_wait(conv, "2000000")
            # 13) expected_salary
            response = await _send_and_wait(conv, "3000000")
            # 14) accommodation_needed — "to'g'ri keladi" (aks holda
            # qo'shimcha accommodation_text qadami chiqadi)
            response = await _click_contains(conv, response, "to'g'ri keladi")

            # B/C tugadi -> fit MISMATCH (yosh) -> D/E/math/motivatsiya/
            # foto BUTUNLAY o'tkazib yuboriladi, suhbat shu yerda tugaydi.
            _assert_contains(response, "Javoblaringiz uchun rahmat")

            # Founder kartasi ALOHIDA, KEYINGI xabar sifatida keladi
            # (qarang recruiting_bot.py::_finish_mismatch_application —
            # avval nomzodga yakunlovchi matn, keyin Founderga karta).
            card = await conv.get_response(timeout=25)
            print(f"[{_now()}] ← Founder kartasi: {(card.text or '<matnsiz>')!r}")

            buttons = _extract_inline_buttons(card)
            button_map = {text: data for text, data in buttons if data}
            required = {"❓ Qo'shimcha savol", "📄 Asl javoblar", "📞 Suhbatga chaqirish", "❌ Rad etish"}
            missing = required - set(button_map)
            if missing:
                raise StepFailed(f"Founder kartasida kutilgan tugmalar yo'q: {missing!r}. Mavjud: {list(button_map)!r}")

            # "❓ Qo'shimcha savol" -> yangi xabar (holat o'zgarmaydi)
            follow_up_msg = await _click_and_wait_new_message(conv, card, button_map["❓ Qo'shimcha savol"], "❓ Qo'shimcha savol")
            _assert_contains(follow_up_msg, "telefon raqami")

            # "📄 Asl javoblar" -> yangi xabar (holat o'zgarmaydi)
            raw_msg = await _click_and_wait_new_message(conv, card, button_map["📄 Asl javoblar"], "📄 Asl javoblar")
            if not (raw_msg.text or "").strip():
                raise StepFailed("'📄 Asl javoblar' bosilgach bot bo'sh javob qaytardi.")

            # "📞 Suhbatga chaqirish" -> FAQAT toast, YANGI xabar yo'q
            interview_toast = await _click_toast(card, button_map["📞 Suhbatga chaqirish"], label="📞 Suhbatga chaqirish")
            if not interview_toast:
                raise StepFailed("'📞 Suhbatga chaqirish' bosilgach hech qanday tasdiq (toast) kelmadi.")

            # Race-guard sinovi: SHU ARIZAGA ikkinchi qaror — bloklanishi
            # kerak (allaqachon 'reviewed').
            reject_toast = await _click_toast(card, button_map["❌ Rad etish"], label="❌ Rad etish (ikkinchi qaror)")
            if not reject_toast or "allaqachon ko'rib chiqilgan" not in reject_toast:
                raise StepFailed(
                    "Race-guard ishlamadi — ikkinchi qaror (❌ Rad etish) bloklanishi kutilgan edi, "
                    f"lekin toast: {reject_toast!r}"
                )

            print(f"[{_now()}] ✅ Race-guard real Telegram orqali tasdiqlandi: ikkinchi qaror bloklandi.")

            # --- vac_toggle: ariza-mustaqil, alohida sinov ---
            vac_response = await _send_and_wait(conv, "/vacancies")
            vac_buttons = _extract_inline_buttons(vac_response)
            if not vac_buttons:
                raise StepFailed(f"/vacancies javobida tugma yo'q: {vac_response.text!r}")
            toggle_text, toggle_data = vac_buttons[0]

            toast1 = await _click_toast(vac_response, toggle_data, label=f"vac_toggle 1-bosish ({toggle_text})")
            if toast1 != "Yangilandi ✅":
                raise StepFailed(f"vac_toggle 1-bosish kutilmagan toast qaytardi: {toast1!r}")

            # ASL holatga qaytarish — xuddi shu callback_data ikkinchi
            # marta bosilsa, is_active yana teskarisiga aylanadi (ya'ni
            # boshlang'ich holatga).
            toast2 = await _click_toast(vac_response, toggle_data, label="vac_toggle 2-bosish (asl holatga qaytarish)")
            if toast2 != "Yangilandi ✅":
                raise StepFailed(f"vac_toggle 2-bosish (qaytarish) kutilmagan toast qaytardi: {toast2!r}")

            print(f"[{_now()}] ✅ vac_toggle tasdiqlandi (asl holatga qaytarildi).")

    except StepFailed as error:
        print(f"\n❌ FAILED — {error}")
        await client.disconnect()
        return False
    except Exception as error:  # noqa: BLE001 — istalgan kutish/tarmoq xatosi ham FAILED
        print(f"\n❌ FAILED — kutilmagan xato: {type(error).__name__}: {error}")
        await client.disconnect()
        return False

    await client.disconnect()
    return True


async def _click_and_wait_new_message(conv, message, data: bytes, label: str):
    print(f"[{_now()}] → tugma bosilmoqda (yangi xabar kutilmoqda): {label!r}")
    await message.click(data=data)
    next_response = await conv.get_response(timeout=25)
    print(f"[{_now()}] ← qabul qilindi: {(next_response.text or '<matnsiz>')!r}")
    return next_response


def main() -> None:
    config = _load_config()
    passed = asyncio.run(_run(config))

    if passed:
        print("\n✅ Recruiting E2E ssenariy TO'LIQ PASSED.")
        sys.exit(0)

    print("\n❌ Recruiting E2E ssenariy FAILED.")
    sys.exit(1)


if __name__ == "__main__":
    main()
