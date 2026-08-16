"""Moslashuvchan qo'shimcha savol (adaptive follow-up).

Nomzod javobi xavfli (masalan kassa/login xavfsizligini buzadigan),
noaniq yoki o'zaro zid ko'rinsa, BITTA aniqlashtiruvchi savol so'raladi.
Avval AI (mavjud bo'lsa) so'raladi — u faqat qisqa JSON qaytaradi,
qat'iy tekshiriladi. AI ishlamasa yoki noto'g'ri/uzun natija bersa,
oldindan yozilgan deterministik qoidalarga o'tiladi. Suhbat davomida
maksimal necha marta so'ralishi (``config.RECRUITING_MAX_FOLLOW_UPS``)
chaqiruvchi kod (``recruiting_bot.py``) tomonidan nazorat qilinadi —
bu modul faqat "shu javobga qo'shimcha savol kerakmi va qanday" degan
savolga javob beradi.
"""

import json
import logging

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

_MODEL = "gpt-5-mini"
_MIN_LEN = 5
_MAX_LEN = 200

# (javobda qidiriladigan kalit so'zlar, mos aniqlashtiruvchi savol).
# Birinchi mos kelgan qoida ishlatiladi.
_DETERMINISTIC_RULES: list[tuple[tuple[str, ...], str]] = [
    (
        ("kassamni beraman", "kassani beraman", "loginimni beraman", "login beraman",
         "parolimni beraman", "parolni beraman", "hisobimni beraman", "kirish ma'lumotlarimni beraman"),
        "U foydalanganidan keyin kassada kamomad chiqsa, javobgarlik kimda bo'ladi?",
    ),
    (
        ("bilmayman", "hech narsa qilmayman", "e'tibor bermayman", "ahamiyat bermayman", "farqi yo'q"),
        "Bu vaziyatda aniq qanday harakat qilishingizni tasavvur qiling — birinchi qadamingiz nima bo'lardi?",
    ),
    (
        ("uni ayblayman", "u aybdor", "mening aybim emas", "boshqasining aybi"),
        "Vaziyatni tuzatish uchun o'zingiz qanday qadam qo'yasiz?",
    ),
]


def _normalize(text: str) -> str:
    return text.strip().lower().replace("‘", "'").replace("’", "'")


def deterministic_follow_up(answer_text: str) -> str | None:
    lowered = _normalize(answer_text)
    for keywords, question in _DETERMINISTIC_RULES:
        if any(keyword in lowered for keyword in keywords):
            return question
    return None


def _parse_json(raw: str) -> dict | None:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
    try:
        data = json.loads(cleaned)
    except (ValueError, TypeError):
        return None
    return data if isinstance(data, dict) else None


async def _ai_follow_up(client: AsyncOpenAI, question_text: str, answer_text: str) -> str | None:
    try:
        response = await client.responses.create(
            model=_MODEL,
            instructions=(
                "Sen ishga qabul suhbatini kuzatuvchi yordamchisan. Faqat berilgan JAVOB "
                "xavfli (masalan xavfsizlik yoki kassa qoidasini buzadigan), noaniq yoki "
                "o'zaro zid bo'lsa, BITTA qisqa (10-25 so'z) aniqlashtiruvchi savol taklif "
                "qil. Javob normal/qoniqarli bo'lsa, follow_up qiymatini null qil. "
                "Nomzodni ayblama, haqorat qilma, unga o'rgatib qo'yma, shaxsiy yoki "
                "himoyalangan xususiyat (din, millat, oilaviy holat va h.k.) haqida hech "
                "qachon so'rama. Yangi mavzu o'ylab topma — faqat shu javobga aniqlik "
                "kiritishga oid savol ber. Faqat quyidagi JSON formatida javob qaytar, "
                'boshqa hech narsa yozma: {"follow_up": "savol matni yoki null"}'
            ),
            input=f"Savol: {question_text}\nNomzod javobi: {answer_text}",
        )
        data = _parse_json(response.output_text or "")
        if data is None:
            return None
        follow_up = data.get("follow_up")
        if not isinstance(follow_up, str):
            return None
        follow_up = follow_up.strip()
        if not (_MIN_LEN <= len(follow_up) <= _MAX_LEN):
            return None
        return follow_up
    except Exception as error:  # noqa: BLE001 - AI xatosi suhbatni to'xtatmasin
        logger.warning("OpenAI xatosi (recruiting follow-up): %r", error)
        return None


async def decide_follow_up(
    client: AsyncOpenAI | None, question_text: str, answer_text: str
) -> str | None:
    """``None`` — qo'shimcha savol kerak emas. Aks holda — bitta
    aniqlashtiruvchi savol matni."""
    if client is not None:
        ai_result = await _ai_follow_up(client, question_text, answer_text)
        if ai_result:
            return ai_result

    return deterministic_follow_up(answer_text)
