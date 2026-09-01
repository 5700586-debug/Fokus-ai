"""Real Telegram orqali ``fokus-ai-test`` botining KASSIR kunlik
hisobot (Daily Report V1) oqimini E2E tekshiruvchi skript: smena ochish
-> mavjud kamchilik gate (bozor/firma/kechagi — "yo'q" deb tezda
o'tkaziladi) -> KUNLIK HISOBOT (Q1 prixodsiz tovar, Q2 narx shikoyati,
Q3 xodim shikoyati) -> real close-shift foto bosqichiga o'tish.

Bu ``e2e/run_e2e.py``/``e2e/run_recruiting_e2e.py``/
``e2e/run_nazoratchi_e2e.py`` bilan bir xil credential/xavfsizlik
qoidalariga bo'ysunadi. Kassir-maxsus buyruqlar (``/openshift``,
``/closeshift``) uchun alohida "kassir" roli SHART EMAS —
``services/permissions.py::has_permission``da Founder rol
tekshiruvidan MUSTASNO (har doim ``True``), shuning uchun bu skript
``/e2exodim``siz, to'g'ridan-to'g'ri FOUNDER_ID akkauntining o'zi bilan
ishlaydi.

Ikkita talab qilingan ssenariy (">=5 signal" va "6+ aniq son so'rash")
BITTA smena ichida birlashtirilgan: Q1ga "6+" tanlanadi, keyin aniq
son sifatida 6 kiritiladi — bu son ham ">=5 signal" chegarasini, ham
"6+ aniq son qabul qilinishi" talabini QAMRAB OLADI (6 >= 5). Buning
sababi: ``cash_shifts`` UNIQUE(employee_id, shift_date) — bitta real
Telegram akkaunt (FOUNDER_ID) uchun kuniga faqat BITTA smena bo'lishi
mumkin, shuning uchun "Q1=5" (tayyor tugma) va "Q1=6+" (erkin son)
alohida-alohida IKKI marta (ikki alohida smena bilan) bir kunda
sinalishi imkonsiz.

Smena kunlik/filial bo'yicha UNIKAL bo'lgani uchun skript ikki holatni
ANIQ qo'llab-quvvatlaydi: (1) FOUNDER_ID uchun hech qachon yopilgan
smena bo'lmagan (birinchi run) — oddiy bitta qadamli "boshlang'ich
qoldiq" oqimi; (2) bugun uchun smena ALLAQACHON mavjud (masalan shu
kun ichida qayta push) — mavjud holatga qarab moslashadi (deficiency/
daily-report gate qayerda to'xtagan bo'lsa, o'sha yerdan davom etadi
yoki allaqachon yopilgan/ko'rib chiqilayotgan bo'lsa muvaffaqiyatli
o'tkazib yuboradi). Uchinchi holat (avvalgi KUNLARDA allaqachon yopilgan
smena bor, LEKIN bugun hali yo'q — yashirin oldingi summani
solishtiradigan qabul qiluvchi oqimi) ATAYLAB qo'llab-quvvatlanmaydi —
bu ochish oqimining o'zini emas, balki KUNLIK HISOBOTni sinash ushbu
skriptning maqsadi; shu holat yuz bersa skript aniq xabar bilan FAILED
bo'ladi (yashirin qiymatni "taxmin qilib" ishonchsiz test yozishdan
ko'ra).
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


class ScenarioSkipped(Exception):
    """Bugun uchun smena allaqachon daily-report gate'dan o'tib
    ketgan (masalan shu kun ichida oldinroq push) — bu FAILURE emas,
    faqat bugun uchun qayta sinab bo'lmasligini bildiradi."""


def _load_config() -> dict[str, str]:
    missing = [name for name in _REQUIRED_ENV_VARS if not os.getenv(name)]
    if missing:
        print(
            "❌ Kassir kunlik hisobot E2E ishga tushmadi — quyidagi environment o'zgaruvchilar "
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


async def _wait_next(conv, *, timeout: int = 25):
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


async def _open_shift_for_e2e(conv) -> None:
    response = await _send_and_wait(conv, "/openshift")
    text = response.text or ""

    if "allaqachon ochilgan" in text:
        print(f"[{_now()}] ℹ️ Bugun uchun smena allaqachon mavjud — to'g'ridan-to'g'ri /closeshift'ga o'tiladi.")
        return

    if "birinchi smenangiz" in text:
        await _send_and_wait(conv, "0")
        print(f"[{_now()}] ✅ Birinchi smena ochildi.")
        return

    raise StepFailed(
        "Kutilmagan /openshift javobi — bu FOUNDER_ID uchun ilgari (boshqa kunda) yopilgan smena bor, "
        "lekin bugun hali yo'q degani, ya'ni yashirin oldingi summani solishtiruvchi qabul qiluvchi "
        "oqimi kerak bo'ladi. Bu skript ATAYLAB shu holatni sinamaydi (modul docstringiga qarang). "
        f"Haqiqiy javob: {text!r}"
    )


async def _reach_daily_report_start(conv) -> "object":
    """``/closeshift``ni yuboradi va, holatga qarab, kamchilik
    gate'ini (bozor/firma — ikkalasi ham "yo'q") tezda o'tkazib,
    kunlik hisobot Q1 (prixodsiz tovar) so'rovi ko'ringan javobni
    qaytaradi. Agar smena allaqachon (bugun ichida oldinroq push
    orqali) daily-report gate'dan o'tib ketgan bo'lsa,
    ``ScenarioSkipped`` ko'taradi."""
    response = await _send_and_wait(conv, "/closeshift")
    text = response.text or ""

    if "allaqachon yopilgan" in text or "tekshiruvida" in text or "topshirilgan" in text:
        raise ScenarioSkipped(f"Bugungi smena allaqachon yakunlangan/tekshiruvda: {text!r}")

    if "rasmini yuboring" in text or "Qayta tekshiring" in text:
        raise ScenarioSkipped("Kunlik hisobot gate bugun allaqachon to'liq bajarilgan (foto bosqichi chiqdi).")

    if "prixodi chiqmagan" in text:
        return response

    # Kamchilik gate hali tugallanmagan -- odatiy holat ANIQ "bozor"
    # bosqichida (get_next_step ketma-ketligi market->company->
    # yesterday, birinchi tugallanmagan qadam qaytadi). Ikkalasi ham
    # "yo'q" deb bosib o'tkaziladi ("kechagi kelmaganlar" ro'yxati
    # bo'sh bo'lgani uchun avtomatik o'tadi).
    response = await _click_contains(conv, response, "bozor kamchiligi yo'q")
    response = await _click_contains(conv, response, "firma zakazi yo'q")
    if "prixodi chiqmagan" not in (response.text or ""):
        raise StepFailed(f"Kamchilik gate'dan keyin kunlik hisobot Q1 kutilgan edi. Haqiqiy javob: {response.text!r}")
    return response


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

    print(f"➡️  Ulanish o'rnatildi. Bot: @{bot_username}. Ssenariy: KASSIR KUNLIK HISOBOT (Daily Report) oqimi.\n")

    try:
        async with client.conversation(bot_username, timeout=25) as conv:
            await _open_shift_for_e2e(conv)

            response = await _reach_daily_report_start(conv)
            print(f"[{_now()}] ✅ Kamchilik gate DONE — kunlik hisobot Q1 (prixodsiz tovar) chiqdi.")

            # Q1 = "6+" -> aniq son so'raladi -> 6 kiritiladi. Bu bir
            # vaqtning o'zida ham "6+ aniq son qabul qilinishi" ham
            # ">=5 signal" talablarini qamrab oladi (modul docstringiga
            # qarang).
            response = await _click_contains(conv, response, "6+")
            _assert_contains(response, "Aniq nechta")
            print(f"[{_now()}] ✅ Q1 = 6+ tanlandi — aniq son so'raldi.")

            response = await _send_and_wait(conv, "6")
            # Signal FOUNDER_ID'ning O'ZIGA ham keladi (skript FOUNDER_ID
            # akkaunti bilan ishlagani uchun) -- navbatda BIRINCHI xabar.
            _assert_contains(response, "PRIXODSIZ TOVAR", "6 ta")
            print(f"[{_now()}] ✅ >=5 SIGNAL — Nazoratchi/Founderga (shu chatga) yuborildi (6 ta).")

            response = await _wait_next(conv)
            _assert_contains(response, "narxi qimmat")
            print(f"[{_now()}] ✅ Signal'dan keyin Q2 (narx shikoyati) savoliga o'tdi.")

            response = await _click_contains(conv, response, "Yo'q, bo'lmadi")
            _assert_contains(response, "xaridor shikoyat")
            print(f"[{_now()}] ✅ Q2 = \"Yo'q, bo'lmadi\" — xodim shikoyati savoliga o'tdi.")

            response = await _click_contains(conv, response, "Yo'q, bo'lmadi")
            _assert_contains(response, "rasmini yuboring")
            print(f"[{_now()}] ✅ Q3 = \"Yo'q, bo'lmadi\" — mavjud close-shift foto bosqichiga o'tdi.")
            print(f"[{_now()}] ✅ TO'LIQ OQIM: deficiency DONE -> Q1 -> Q2 -> Q3 -> close-shift foto bosqichi.")

    except ScenarioSkipped as skip:
        print(f"\nℹ️ SKIPPED (failure emas) — {skip}")
        await client.disconnect()
        return True
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
        print("\n✅ Kassir Daily Report E2E ssenariy TO'LIQ PASSED.")
        sys.exit(0)

    print("\n❌ Kassir Daily Report E2E ssenariy FAILED.")
    sys.exit(1)


if __name__ == "__main__":
    main()
