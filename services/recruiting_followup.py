"""Moslashuvchan qo'shimcha savol (adaptive follow-up) — "jonli suhbat"
hissi uchun asosiy mexanizm.

Nomzod javobi noaniq, mavzudan tashqari, ikki xil talqin qilinadigan
yoki (ma'lum savol turlari uchun) xavfli ko'rinsa, BITTA qisqa,
oddiy/xalqchil tilda aniqlashtiruvchi savol so'raladi. Real Telegram
sinovida aniqlangan muammolar:

- Imloviy xato/sheva/og'zaki yozuvni AI aniqlashtirmadi — shu sabab
  quyidagi AI ko'rsatmasida buni ANIQ talab qilamiz (imlo emas, MA'NO
  muhim).
- Qo'shimcha savollar "protsedura", "protokol" kabi og'ir so'zlar bilan
  chiqdi — AI ko'rsatmasida bunday so'zlar ANIQ taqiqlangan, deterministik
  qoidalar ham shu uslubda yozilgan.

Avval AI (mavjud bo'lsa) so'raladi — u faqat qisqa JSON qaytaradi,
qat'iy tekshiriladi. AI ishlamasa yoki noto'g'ri/uzun natija bersa,
oldindan yozilgan deterministik qoidalarga o'tiladi (``recruiting_redflags``
va umumiy "noaniq javob" tekshiruvi). Suhbat davomida BITTA javobga
maksimal necha marta so'ralishi (``config.RECRUITING_MAX_FOLLOW_UPS``)
chaqiruvchi kod (``recruiting_bot.py``) tomonidan nazorat qilinadi — bu
modul faqat "shu javobga qo'shimcha savol kerakmi va qanday" degan
savolga javob beradi.

AI HECH QACHON nomzod o'rniga ma'no o'ylab topmaydi: ishonchi past
bo'lsa (noaniq holat), AI ``null`` qaytarishga o'rgatilgan — bunda
deterministik qoida ishlaydi yoki (mos kelmasa) javob "noaniq" deb
belgilanadi, chaqiruvchi kod inson ko'rib chiqishini talab qiladi."""

import json
import logging

from openai import AsyncOpenAI

from services import recruiting_redflags

logger = logging.getLogger(__name__)

_MODEL = "gpt-5-mini"
_MIN_LEN = 5
_MAX_LEN = 200

def _redflag_checker_for(question_key: str | None):
    from services import recruiting_questions as rq

    if question_key is None:
        return None
    if question_key in rq.EXPIRED_PRODUCT_QUESTION_KEYS:
        return recruiting_redflags.check_expired_product
    if question_key in rq.SHORTAGE_QUESTION_KEYS:
        return recruiting_redflags.check_shortage_response
    if question_key in rq.CREDENTIAL_SHARING_QUESTION_KEYS:
        return recruiting_redflags.check_credential_sharing
    if question_key in rq.CUSTOMER_CONFLICT_QUESTION_KEYS:
        return recruiting_redflags.check_customer_conflict
    return None


# Oddiy, mavzudan qat'i nazar "javob aslida hech narsa aytmayapti" holatlari
# — imlo emas, MAZMUN yo'qligi (masalan bitta so'z, umuman aloqasiz javob).
_GENERIC_VAGUE_PHRASES = (
    "bilmayman", "bilmadim", "nima desam", "nima deyman", "aytolmayman",
    "farqi yo'q", "har xil", "shunchaki", "hech narsa", "yo'q gap",
)


def _normalize(text: str) -> str:
    return text.strip().lower().replace("‘", "'").replace("’", "'")


def _looks_too_short_to_be_an_answer(text: str) -> bool:
    """Juda qisqa (1-2 so'z, sanoq/undov) javoblar — ochiq savolga
    "ha"/"yo'q"/"xa" kabi javob amalda hech narsa bildirmaydi."""
    words = text.split()
    if len(words) > 2:
        return False
    return _normalize(text) in {"ha", "yo'q", "yoq", "xa", "yaxshi", "bilmayman", "-", "?"}


def deterministic_follow_up(answer_text: str, question_key: str | None = None) -> str | None:
    """Savolga xos (agar ``question_key`` berilsa) yoki umumiy qoidalar
    bo'yicha aniqlashtiruvchi savol matni, yoki javob aniq/xavfsiz bo'lsa
    ``None``."""
    lowered = _normalize(answer_text)
    if not lowered:
        return "Kechirasiz, javobingizni ko'rmadim — birroz batafsilroq yozib bera olasizmi?"

    checker = _redflag_checker_for(question_key)
    if checker is not None:
        status = checker(answer_text)
        if status == recruiting_redflags.RED:
            return _redflag_clarifying_question(question_key)
        if status == recruiting_redflags.UNCLEAR:
            return _redflag_clarifying_question(question_key)
        # GREEN — aniq, xavfsiz javob, qo'shimcha savol shart emas.
        return None

    # Umumiy (savol turiga bog'liq bo'lmagan) noaniqlik tekshiruvi.
    if _looks_too_short_to_be_an_answer(answer_text) or any(p in lowered for p in _GENERIC_VAGUE_PHRASES):
        return "Tushunmadim — bu holatda aniq nima qilgan bo'lardingiz, birrov aytib bera olasizmi?"

    # Eski (umumiy) login/kassa ulashish signali — savol kaliti berilmagan
    # chaqiruvlar (masalan mavjud testlar) uchun ham ishlashi kerak.
    credential_status = recruiting_redflags.check_credential_sharing(answer_text)
    if credential_status == recruiting_redflags.RED:
        return "U foydalanganidan keyin kassada kamomad chiqsa, buning uchun kim javobgar bo'ladi?"

    return None


def _redflag_clarifying_question(question_key: str | None) -> str:
    from services import recruiting_questions as rq

    if question_key in rq.EXPIRED_PRODUCT_QUESTION_KEYS:
        return "Aniqlashtiray — muddati o'tgan mahsulotni sotib yuborasizmi, yoki uni javondan olib tashlaysizmi?"
    if question_key in rq.SHORTAGE_QUESTION_KEYS:
        return "Tushunmadim — kassada pul kam chiqsa, buni birinchi kimga aytasiz?"
    if question_key in rq.CREDENTIAL_SHARING_QUESTION_KEYS:
        return "Aniqlik uchun so'rayman — login yoki kassangizni hech kimga bermaysiz, to'g'rimi?"
    if question_key in rq.CUSTOMER_CONFLICT_QUESTION_KEYS:
        return "Xaridor sizni haqorat qilsa ham, xotirjam yo'l tutasizmi?"
    return "Tushunmadim, birrov aniqroq aytib bera olasizmi?"


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
                "Sen ishga qabul suhbatini olib boruvchi, iliq va sabrli HR "
                "yordamchisan. Nomzod javobida IMLOVIY XATO, SHEVA yoki OG'ZAKI "
                "yozuv bo'lishi mumkin — buning uchun JAZOLAMA, faqat MA'NOSINI "
                "tushunishga harakat qil. Javob tushunarli va mavzuga oid bo'lsa, "
                "follow_up qiymatini null qil.\n\n"
                "Faqat quyidagi holatlarda BITTA qisqa, oddiy va xalqchil tilda "
                "aniqlashtiruvchi savol taklif qil:\n"
                "- javob noaniq yoki ikki xil talqin qilinadi;\n"
                "- javob savolga aloqasi yo'q yoki mavzudan qochadi;\n"
                "- javob xavfsizlik yoki kassa/mahsulot qoidasini buzadigan tarzda xavfli ko'rinadi.\n\n"
                "QAT'IY TAQIQ: savolda 'protsedura', 'protokol', 'eskalatsiya', "
                "'rasmiylashtirish' kabi rasmiy/og'ir so'zlarni ISHLATMA — oddiy "
                "kundalik so'zlashuv tilida yoz (masalan 'kimga aytasiz' emas "
                "'rasmiylashtirasizmi' kabi emas). Nomzodni ayblama, haqorat "
                "qilma, unga o'rgatib qo'yma, shaxsiy yoki himoyalangan xususiyat "
                "(din, millat, oilaviy holat va h.k.) haqida hech qachon so'rama. "
                "Yangi mavzu o'ylab topma — faqat shu javobga aniqlik kiritishga "
                "oid savol ber.\n\n"
                "AGAR ISHONCHING PAST bo'lsa (javob chindan ham tushunarsiz "
                "ekanini aniq bila olmasang), baribir eng xavfsiz yo'l — oddiy "
                "aniqlashtiruvchi savol taklif qilish, LEKIN nomzod o'rniga hech "
                "qachon ma'no o'ylab topma yoki uning fikrini taxmin qilib yozma.\n\n"
                "Faqat quyidagi JSON formatida javob qaytar, boshqa hech narsa "
                'yozma: {"follow_up": "savol matni yoki null"}'
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
        lowered = follow_up.lower()
        if any(word in lowered for word in ("protsedura", "protokol", "eskalatsiya", "rasmiylashtir")):
            return None
        return follow_up
    except Exception as error:  # noqa: BLE001 - AI xatosi suhbatni to'xtatmasin
        logger.warning("OpenAI xatosi (recruiting follow-up): %r", error)
        return None


async def decide_follow_up(
    client: AsyncOpenAI | None, question_text: str, answer_text: str, question_key: str | None = None
) -> str | None:
    """``None`` — qo'shimcha savol kerak emas. Aks holda — bitta
    aniqlashtiruvchi savol matni. ``question_key`` berilsa, kritik
    (red-flag) kategoriyalar bo'yicha maxsus tekshiruv ham ishlaydi."""
    if client is not None:
        ai_result = await _ai_follow_up(client, question_text, answer_text)
        if ai_result:
            return ai_result

    return deterministic_follow_up(answer_text, question_key)
