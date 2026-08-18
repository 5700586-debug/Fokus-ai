"""Lavozimga bog'liq baholash rubrikasi — versiyalangan, faqat ish
bilan bog'liq mezonlar (qarang loyihaning rekruting talab hujjati:
himoyalangan shaxsiy xususiyatlar ballga hech qachon ta'sir qilmaydi,
chunki ular bu ro'yxatda umuman yo'q va hech qachon so'ralmaydi).

``RUBRIC_VERSION = 3`` — real Telegram sinovidan keyin qo'shildi:
``muddat_xavfsizligi`` (muddati o'tgan mahsulot) va ``halollik``
(hamkasb o'g'irligiga guvoh bo'lish) endi ``muammo_yechish`` ichida
yashiringan emas, alohida KRITIK mezonlar (qarang
``services/recruiting_scoring.py``dagi red-flag integratsiyasi)."""

from repositories import recruiting as recruiting_repo

RUBRIC_VERSION = 3

KASSIR_CRITERIA: list[dict] = [
    {"key": "tajriba", "label": "Tegishli tajriba"},
    {"key": "muomala", "label": "Mijoz bilan muomala (mojaro paytida)"},
    {"key": "kassa_xavfsizlik", "label": "Kassa xavfsizligi va shaxsiy login qoidasi"},
    {"key": "muddat_xavfsizligi", "label": "Muddati o'tgan mahsulotga munosabat"},
    {"key": "halollik", "label": "Halollik (hamkasb o'g'irligiga guvoh bo'lish)"},
    {"key": "matematik", "label": "Oddiy matematik aniqlik"},
    {"key": "muammo_yechish", "label": "Muammoni hal qilish"},
    {"key": "javobgarlik", "label": "Javobgarlik (kamomad holati)"},
    {"key": "jadval_moslik", "label": "E'lon qilingan ish jadvaliga moslik"},
]

SOTUVCHI_CRITERIA: list[dict] = [
    {"key": "muomala", "label": "Mijoz bilan muomala (norozilik paytida)"},
    {"key": "ehtiyoj", "label": "Ehtiyojni tushunish"},
    {"key": "tavsiya", "label": "Mahsulot tavsiya qilish"},
    {"key": "javon", "label": "Javon, yaroqlilik va ozodalik"},
    {"key": "muddat_xavfsizligi", "label": "Muddati o'tgan mahsulotga munosabat"},
    {"key": "halollik", "label": "Halollik (hamkasb o'g'irligiga guvoh bo'lish)"},
    {"key": "jamoaviylik", "label": "Jamoaviy ishlash"},
    {"key": "jadval_moslik", "label": "E'lon qilingan ish jadvaliga moslik"},
]

CRITERIA_BY_POSITION: dict[str, list[dict]] = {
    "kassir": KASSIR_CRITERIA,
    "sotuvchi": SOTUVCHI_CRITERIA,
}


def criteria_for(position_key: str) -> list[dict]:
    return CRITERIA_BY_POSITION.get(position_key, [])


def ensure_rubric_version(position_key: str) -> dict:
    """Shu lavozim uchun joriy rubrika versiyasi DB'da mavjudligini
    ta'minlaydi (yo'q bo'lsa yaratadi) va uni qaytaradi."""
    criteria = criteria_for(position_key)
    if not criteria:
        raise ValueError(f"Noma'lum lavozim uchun rubrika: {position_key}")

    recruiting_repo.create_rubric_version(position_key, RUBRIC_VERSION, criteria)
    version = recruiting_repo.get_latest_rubric_version(position_key)
    if version is None:
        raise RuntimeError(f"Rubrika versiyasini saqlab bo'lmadi: {position_key}")
    return version
