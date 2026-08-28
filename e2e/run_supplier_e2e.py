"""Real Telegram orqali ``fokus-ai-test`` botining TA'MINOTCHI xarid
oqimini E2E tekshiruvchi skript: ``/xarid`` -> mahsulot qo'shish (➕) ->
miqdor+narx (birinchi marta yangi narx, keyingi run'larda ♻️/✏️ tez
tasdiqlash) -> filialga real taqsimlash -> ``/natijam``.

Bu ``e2e/run_e2e.py``/``e2e/run_recruiting_e2e.py``/
``e2e/run_nazoratchi_e2e.py``/``e2e/run_cashshift_e2e.py`` bilan bir
xil credential/xavfsizlik qoidalariga bo'ysunadi. Ta'minotchi-maxsus
buyruqlar (``/xarid``, ``/natijam``) uchun alohida "taminotchi" roli
SHART EMAS — ``services/permissions.py::has_permission``da Founder rol
tekshiruvidan MUSTASNO (har doim ``True``), shuning uchun bu skript
to'g'ridan-to'g'ri FOUNDER_ID akkauntining o'zi bilan ishlaydi.

``/xarid``ning bozor buyurtmasi ro'yxati REAL kassir ma'lumotiga bog'liq
(``shift_deficiency_items``) va bu skript uni yaratmaydi (bu butunlay
boshqa, ``e2e/run_cashshift_e2e.py``da allaqachon sinaladigan oqim),
shuning uchun ro'yxat odatda bo'sh bo'ladi — E2E ATAYLAB "➕ Mahsulot
qo'shish" (ad-hoc) yo'lidan boradi: bu yo'l bo'sh/to'la ro'yxatdan
QAT'IY NAZAR har doim ishlaydigan, DETERMINISTIK yagona yo'l. Doimiy
mahsulot nomi ishlatiladi — birinchi run'da narx tarixi yo'q (yangi
narx kiritiladi), keyingi run'larda (bugun qayta push yoki keyingi
kunlar) tarix allaqachon bor (♻️/✏️ tez tasdiqlash tekshiriladi) —
ikkala UX yo'li ham vaqt o'tishi bilan tabiiy ravishda sinaladi.

Nazoratchi tomonidagi "xodim yo'q" holatini (mavjud ``employees.
list_approved_by_branch`` mantig'iga bog'liq) real E2E orqali ISHONCHLI
sinash uchun biror filialning ANIQ bo'sh ekanini kafolatlaydigan mavjud
mexanizm yo'q (yangi bootstrap/auth arxitektura yaratish bu skriptning
maqsadi emas) — shu sabab bu holat REAL E2E'da SINALMAYDI, faqat mavjud
pytest darajasidagi targeted testlar (``tests/test_nazoratchi_
supervision.py``) orqali tasdiqlangan.
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

_PRODUCT_NAME = "E2E Sinov Mahsuloti"
_PRODUCT_UNIT = "dona"
_PRODUCT_QUANTITY = "3"
_FIRST_TIME_PRICE = "1000"


class StepFailed(Exception):
    pass


def _load_config() -> dict[str, str]:
    missing = [name for name in _REQUIRED_ENV_VARS if not os.getenv(name)]
    if missing:
        print(
            "❌ Ta'minotchi xarid E2E ishga tushmadi — quyidagi environment o'zgaruvchilar "
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


async def _click_first_button(conv, response, *, timeout: int = 25):
    """Filial nomi oldindan noma'lum (hardcode qilinmaydi) — birinchi
    (index 0) tugmani, matnidan qat'i nazar, bosadi."""
    buttons = _extract_inline_buttons(response)
    if not buttons:
        raise StepFailed("Tugma topilmadi (bo'sh klaviatura).")
    text, data = buttons[0]
    print(f"[{_now()}] → tugma bosilmoqda: {text!r}")
    await response.click(data=data)
    next_response = await conv.get_response(timeout=timeout)
    print(f"[{_now()}] ← qabul qilindi: {(next_response.text or '<matnsiz>')!r}")
    return next_response


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

    print(f"➡️  Ulanish o'rnatildi. Bot: @{bot_username}. Ssenariy: TA'MINOTCHI XARID oqimi.\n")

    try:
        async with client.conversation(bot_username, timeout=25) as conv:
            response = await _send_and_wait(conv, "/xarid")
            print(f"[{_now()}] ✅ /xarid ochildi.")

            response = await _click_contains(conv, response, "Mahsulot qo'shish")
            _assert_contains(response, "Mahsulot nomini")
            print(f"[{_now()}] ✅ ➕ Mahsulot qo'shish bosildi.")

            response = await _send_and_wait(conv, _PRODUCT_NAME)
            response = await _send_and_wait(conv, _PRODUCT_QUANTITY)
            response = await _click_contains(conv, response, _PRODUCT_UNIT)

            price_text = response.text or ""
            if "Oxirgi narx" in price_text:
                response = await _click_contains(conv, response, "O'zgarmagan")
                print(f"[{_now()}] ✅ ♻️ Oldingi narx tez tasdiqlandi.")
            else:
                _assert_contains(response, "Birlik narxini")
                response = await _send_and_wait(conv, _FIRST_TIME_PRICE)
                print(f"[{_now()}] ✅ Birinchi marta narx kiritildi (tarix yo'q edi).")

            # Narxdan keyin ikkita xabar ketma-ket keladi: (1) "✅ ... so'm"
            # tasdiq (yuqorida allaqachon ushlangan), (2) taqsimot ekrani --
            # shu ikkinchisini alohida kutib olish kerak.
            _assert_contains(response, "so'm")
            response = await _wait_next(conv)
            _assert_contains(response, "Filiallarga taqsimlash")
            print(f"[{_now()}] ✅ Real xarid saqlandi, taqsimot ekrani chiqdi.")

            # Filial nomi hardcode qilinmaydi -- birinchi (index 0)
            # filial tugmasi bosiladi, so'ng SOTIB OLINGAN miqdorning
            # HAMMASI shu bitta filialga beriladi (qoldiq darhol 0
            # bo'ladi, filiallar soni qancha bo'lishidan qat'i nazar).
            response = await _click_first_button(conv, response)
            _assert_contains(response, "berildi?")
            response = await _send_and_wait(conv, _PRODUCT_QUANTITY)

            response = await _click_contains(conv, response, "Yakunlash")
            _assert_contains(response, "taqsimlandi")
            # "✅ ... taqsimlandi." tasdiqidan keyin filial hisoboti
            # ALOHIDA xabar sifatida keladi.
            response = await _wait_next(conv)
            _assert_contains(response, "🏢")
            print(f"[{_now()}] ✅ Filialga real taqsimlandi — filial hisoboti chiqdi.")

            response = await _send_and_wait(conv, "/natijam")
            _assert_contains(response, "Bugungi natijangiz", "Buyurtma", "Bajarilish")
            print(f"[{_now()}] ✅ /natijam javob berdi.")

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
        print("\n✅ Ta'minotchi xarid E2E ssenariy TO'LIQ PASSED.")
        sys.exit(0)

    print("\n❌ Ta'minotchi xarid E2E ssenariy FAILED.")
    sys.exit(1)


if __name__ == "__main__":
    main()
