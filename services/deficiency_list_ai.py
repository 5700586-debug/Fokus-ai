"""Kassir smena yopishida ko'p qatorli bozor ro'yxatini alohida
pozitsiyalarga ({product_name, quantity, unit}) ajratish.

Avval TO'LIQ deterministik regex bilan har bir qator parse qilinadi.
Faqat aniq bo'lmagan qatorlar BITTA umumiy ``gpt-5-mini`` chaqiruvida
(bitta qatorga bitta chaqiruv EMAS — butun ro'yxat uchun bitta so'rov)
AI'ga yuboriladi. AI hech qachon mahsulot/miqdor/birlikni o'zi
TO'QIMAYDI — noaniq qolgan qator uchun ``null`` qaytaradi, keyin
foydalanuvchidan qo'lda aniqlashtirish so'raladi (``cash_shift_bot.py``).

Tamoyil ``services/supplier_purchase.py``/``services/discipline_ai.py``
bilan bir xil: tor AI chaqiruvi, oddiy fail-safe fallback.
"""

import json
import re

from openai import AsyncOpenAI

from services.shift_deficiency import KNOWN_UNITS

_AI_MODEL = "gpt-5-mini"

# Mahsulot nomidagi o'lcham/hajm yozuvlari (masalan "500 gr") ushbu
# ro'yxatga KIRMAYDI — shuning uchun regex ularni miqdor deb
# noto'g'ri o'qib qolmaydi, ular nom ichida saqlanib qoladi.
_UNIT_ALIASES = {
    "karobka": "quti",
    "коробка": "quti",
    "ta": "dona",
}

_UNIT_PATTERN = "|".join(sorted(set(KNOWN_UNITS) | set(_UNIT_ALIASES.keys()), key=len, reverse=True))

_LINE_RE = re.compile(
    r"^(?P<name>.+?)\s+(?P<qty>\d+(?:[.,]\d+)?)\s*(?P<unit>" + _UNIT_PATTERN + r")\s*$",
    re.IGNORECASE,
)


def _normalize_unit(raw_unit: str) -> str:
    unit = (raw_unit or "").strip().lower()
    return _UNIT_ALIASES.get(unit, unit)


def split_lines(text: str) -> list[str]:
    return [line.strip() for line in (text or "").splitlines() if line.strip()]


def parse_line_deterministic(line: str) -> dict | None:
    """Bitta qatorni ``{product_name, quantity, unit}``ga o'giradi,
    yoki qat'iy formatga tushmasa ``None`` (keyin AI/qo'lda
    aniqlashtirish navbatiga tushadi)."""
    match = _LINE_RE.match((line or "").strip())
    if not match:
        return None

    quantity = float(match.group("qty").replace(",", "."))
    if quantity <= 0:
        return None

    name = match.group("name").strip()
    if not name:
        return None

    unit = _normalize_unit(match.group("unit"))
    if unit not in KNOWN_UNITS:
        return None

    return {"product_name": name, "quantity": quantity, "unit": unit}


def parse_lines_deterministic(lines: list[str]) -> list[dict]:
    return [{"raw_line": line, "parsed": parse_line_deterministic(line)} for line in lines]


_AI_INSTRUCTIONS = (
    "Sen Fokus AI kassir yordamchisisan. Kassir bozor ro'yxatini qo'lda yozgan, "
    "ba'zi qatorlarni oddiy qoidalar bilan aniqlab bo'lmadi — ular senga beriladi. "
    "Har bir qatorni {product_name, quantity, unit} ko'rinishiga o'gir. "
    "Ruxsat etilgan birliklar FAQAT: " + ", ".join(KNOWN_UNITS) + ". "
    "'karobka' yoki 'коробка' uchrasa — 'quti' deb ol; 'ta' uchrasa — 'dona' deb ol. "
    "Mahsulot nomidagi o'lcham/hajmni (masalan '500 gr', '1.5 litrli idish') "
    "product_name ICHIDA SAQLA, uni quantity deb hisoblama. "
    "Hech qachon mahsulot nomi, miqdor yoki birlikni O'ZING TO'QIMA — qatordan "
    "ANIQ chiqmasa, o'sha qator uchun barcha maydonlarni null qil. "
    "Javobni FAQAT quyidagi JSON massiv ko'rinishida qaytar, boshqa hech qanday matn yozma:\n"
    '[{"line": "asl qator matni", "product_name": matn yoki null, '
    '"quantity": son yoki null, "unit": matn yoki null}, ...]\n'
    "Massiv uzunligi va tartibi berilgan qatorlar bilan AYNAN bir xil bo'lsin."
)


def _parse_ai_json(raw_text: str) -> list | None:
    text = (raw_text or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return None
    return data if isinstance(data, list) else None


def _coerce_quantity(value) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        quantity = float(value)
    elif isinstance(value, str):
        try:
            quantity = float(value.strip().replace(",", "."))
        except ValueError:
            return None
    else:
        return None
    return quantity if quantity > 0 else None


async def resolve_unclear_lines(client: AsyncOpenAI, unclear_lines: list[str]) -> dict[str, dict | None]:
    """``unclear_lines`` uchun BITTA umumiy AI chaqiruvi (qatorlar soni
    qancha bo'lmasin — bitta qatorga bitta chaqiruv EMAS). Natija —
    {raw_line: {"product_name", "quantity", "unit"} yoki None}. AI
    javobi to'liq validatsiya qilinadi: unit ruxsat etilganlar
    ro'yxatidan tashqarida yoki quantity musbat son bo'lmasa, o'sha
    qator ``None`` deb qoladi (fail-safe — AI hech qachon noto'g'ri/
    to'qib chiqarilgan ma'lumot bilan yozilmaydi)."""
    unique_lines = list(dict.fromkeys(unclear_lines))
    result: dict[str, dict | None] = {line: None for line in unique_lines}
    if not unique_lines:
        return result

    try:
        response = await client.responses.create(
            model=_AI_MODEL,
            instructions=_AI_INSTRUCTIONS,
            input="\n".join(unique_lines),
        )
        data = _parse_ai_json(response.output_text)
    except Exception as error:  # noqa: BLE001
        print(f"OpenAI xatosi (resolve_unclear_lines): {error!r}")
        data = None

    if data is None:
        return result

    for entry in data:
        if not isinstance(entry, dict):
            continue
        line = entry.get("line")
        if line not in result:
            continue

        name = entry.get("product_name")
        if not isinstance(name, str) or not name.strip():
            continue

        quantity = _coerce_quantity(entry.get("quantity"))
        if quantity is None:
            continue

        unit_raw = entry.get("unit")
        if not isinstance(unit_raw, str):
            continue
        unit = _normalize_unit(unit_raw)
        if unit not in KNOWN_UNITS:
            continue

        result[line] = {"product_name": name.strip(), "quantity": quantity, "unit": unit}

    return result


async def parse_shopping_list(client: AsyncOpenAI | None, text: str) -> list[dict]:
    """To'liq oqim: qatorlarga bo'lish -> deterministik parse -> faqat
    noaniq qatorlar uchun BITTA AI chaqiruvi. Natija — har bir qator
    uchun ``{"raw_line", "parsed"}`` (``parsed is None`` — hali ham
    noaniq, foydalanuvchidan qo'lda so'ralishi kerak)."""
    lines = split_lines(text)
    results = parse_lines_deterministic(lines)

    unclear = [item["raw_line"] for item in results if item["parsed"] is None]
    if unclear and client is not None:
        ai_results = await resolve_unclear_lines(client, unclear)
        for item in results:
            if item["parsed"] is None:
                item["parsed"] = ai_results.get(item["raw_line"])

    return results
