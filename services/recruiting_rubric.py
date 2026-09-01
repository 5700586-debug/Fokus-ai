"""Lavozimga bog'liq baholash rubrikasi — versiyalangan, faqat ish
bilan bog'liq mezonlar (qarang loyihaning rekruting talab hujjati:
himoyalangan shaxsiy xususiyatlar ballga hech qachon ta'sir qilmaydi,
chunki ular bu ro'yxatda umuman yo'q va hech qachon so'ralmaydi).

``RUBRIC_VERSION = 4`` — savol banki qisqartirilgandan keyin (qarang
``services/recruiting_questions.py``): endi ikkala lavozim uchun bir
xil, faqat 4 ta umumiy vaziyatli savolga mos mezonlar + muddat
xavfsizligi (operatsion tekshiruv) + tajriba/matematik(kassir)/jadval.
Kassa xavfsizligi (login) va javobgarlik (kamomad) mezonlari — endi
mos savol so'ralmagani uchun OLIB TASHLANDI (rubrikada bo'lishi
Founderga "javob berilmagan" deb bo'sh ko'rinardi)."""

from repositories import recruiting as recruiting_repo

RUBRIC_VERSION = 4

_SHARED_CRITERIA: list[dict] = [
    {"key": "tajriba", "label": "Tegishli tajriba"},
    {"key": "muomala", "label": "Mijoz bilan muomala (mojaro paytida)"},
    {"key": "savdo_fikrlash", "label": "Savdo fikrlashi / mijoz ehtiyoji"},
    {"key": "halollik", "label": "Halollik (hamkasb o'g'irligiga guvoh bo'lish)"},
    {"key": "tashabbuskorlik", "label": "Tashabbuskorlik"},
    {"key": "muddat_xavfsizligi", "label": "Muddati o'tgan mahsulotga munosabat"},
    {"key": "jadval_moslik", "label": "E'lon qilingan ish jadvaliga moslik"},
]

KASSIR_CRITERIA: list[dict] = _SHARED_CRITERIA[:5] + [
    {"key": "matematik", "label": "Oddiy matematik aniqlik"},
] + _SHARED_CRITERIA[5:]

SOTUVCHI_CRITERIA: list[dict] = list(_SHARED_CRITERIA)

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
