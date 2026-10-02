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

import asyncio
import json
import re

from openai import AsyncOpenAI

from services.shift_deficiency import KNOWN_UNITS

_AI_MODEL = "gpt-5-mini"

# Mahsulot nomidagi o'lcham/hajm yozuvlari (masalan "500 gr") ushbu
# ro'yxatga KIRMAYDI — shuning uchun regex ularni miqdor deb
# noto'g'ri o'qib qolmaydi, ular nom ichida saqlanib qoladi.
_UNIT_ALIASES = {
    "коробка": "karobka",
    "karopka": "karobka",
    "korobka": "karobka",
    "yashig": "yashik",
    "yashiq": "yashik",
    "ящик": "yashik",
    "ta": "dona",
}

# So'z bilan yozilgan sonlar ("bir karobka"). Faqat birlik oldida,
# alohida so'z sifatida miqdor deb o'qiladi.
_NUMBER_WORDS = {
    "bir": 1, "ikki": 2, "uch": 3, "to'rt": 4, "besh": 5,
    "olti": 6, "yetti": 7, "sakkiz": 8, "to'qqiz": 9, "o'n": 10,
}
_QUALITY_FIXES = {"kotta": "katta", "kutta": "katta", "kichiq": "kichik"}
# Shu aniq sifat so'zlarini kod o'zi o'qiydi; qolganini (masalan "pishgan",
# "yirikroq") mavjud AI savol kontekstida ajratadi (``classify_answer_words``).
_QUALITY_WORDS = {
    "katta", "kichik", "o'rta", "o'rtacha", "yirik", "mayda",
    "qizil", "sariq", "yashil", "oq", "qora", "pushti", "ko'k",
}
# Javob emas — hech qachon mahsulot sifati/nomi bo'lmaydi. Yolg'iz "ha" ham
# hech narsani hal qilmaydi va so'z sifatida qo'shilmaydi.
_NON_ANSWERS = {
    "bilmayman", "bilmadim", "bilmiman", "bilmaymiz", "yo'q", "yoq", "nomalum", "no'malum",
    "hozircha", "keyin", "nima", "nimadir", "tushunmadim", "ha", "xa", "ok",
}

_UNIT_PATTERN = "|".join(sorted(set(KNOWN_UNITS) | set(_UNIT_ALIASES.keys()), key=len, reverse=True))
_WORD_PATTERN = "|".join(sorted((re.escape(w) for w in _NUMBER_WORDS), key=len, reverse=True))
_QTY_PATTERN = r"\d+(?:[.,]\d+)?|" + _WORD_PATTERN

_LINE_RE = re.compile(
    r"^(?P<name>.+?)\s+(?P<qty>" + _QTY_PATTERN + r")\s*(?P<unit>" + _UNIT_PATTERN + r")\s*$",
    re.IGNORECASE,
)
_QTY_ONLY_RE = re.compile(r"^(?P<name>.+?)\s+(?P<qty>" + _QTY_PATTERN + r")\s*$", re.IGNORECASE)
_UNIT_ONLY_RE = re.compile(r"^(?P<name>.+?)\s+(?P<unit>" + _UNIT_PATTERN + r")\s*$", re.IGNORECASE)
_PAIR_RE = re.compile(
    r"(?<!\S)(?:(?P<num>\d+(?:[.,]\d+)?)\s*|(?P<word>" + _WORD_PATTERN + r")\s+)(?P<unit>" + _UNIT_PATTERN + r")(?!\S)",
    re.IGNORECASE,
)
_QTY_TOKEN_RE = re.compile(r"(?<!\S)(?P<qty>" + _QTY_PATTERN + r")(?!\S)", re.IGNORECASE)
_UNIT_TOKEN_RE = re.compile(r"(?<!\S)(?P<unit>" + _UNIT_PATTERN + r")(?!\S)", re.IGNORECASE)
_NUMBERED_RE = re.compile(r"^\s*(\d+)\s*[.)\-:]\s*(.*)$")
_EDIT_RE = re.compile(r"^\s*(?:yangi|almashtir)\s*:\s*(?P<line>.+)$", re.IGNORECASE)
_HINT_TOKENS = set(KNOWN_UNITS) | set(_UNIT_ALIASES) | set(_NUMBER_WORDS)


def _clean_apostrophes(text: str) -> str:
    return (text or "").replace("’", "'").replace("ʻ", "'").replace("`", "'")


def _to_quantity(raw: str) -> float | None:
    key = _clean_apostrophes(raw).strip().lower()
    if key in _NUMBER_WORDS:
        return float(_NUMBER_WORDS[key])
    try:
        quantity = float(key.replace(",", "."))
    except ValueError:
        return None
    return quantity if quantity > 0 else None


def normalize_name_words(name: str) -> str:
    """Faqat ma'lum imlo variantlarini to'g'rilaydi (kotta/kutta -> katta,
    kichiq -> kichik); mahsulot sifati nomda saqlanadi."""
    def _fix(match: re.Match) -> str:
        word = match.group(0)
        fixed = _QUALITY_FIXES[word.lower()]
        return fixed.capitalize() if word[0].isupper() else fixed

    pattern = "|".join(_QUALITY_FIXES)
    return re.sub(r"\b(?:" + pattern + r")\b", _fix, name or "", flags=re.IGNORECASE)


def has_quantity_hint(text: str) -> bool:
    """Qatorda miqdor/birlik belgisi bormi (raqam, so'z son yoki birlik) —
    raqamsiz oddiy mahsulot nomi AI'ga yuborilmasligi uchun."""
    if re.search(r"\d", text or ""):
        return True
    return any(token in _HINT_TOKENS for token in _clean_apostrophes(text).lower().split())


def _normalize_unit(raw_unit: str) -> str:
    unit = (raw_unit or "").strip().lower()
    return _UNIT_ALIASES.get(unit, unit)


def split_lines(text: str) -> list[str]:
    return [line.strip() for line in (text or "").splitlines() if line.strip()]


def parse_line_deterministic(line: str) -> dict | None:
    """Bitta qatorni ``{product_name, quantity, unit}``ga o'giradi,
    yoki qat'iy formatga tushmasa ``None`` (keyin AI/qo'lda
    aniqlashtirish navbatiga tushadi)."""
    match = _LINE_RE.match(_clean_apostrophes(line).strip())
    if not match:
        return None

    quantity = _to_quantity(match.group("qty"))
    if quantity is None:
        return None

    name = normalize_name_words(match.group("name").strip())
    if not name:
        return None

    unit = _normalize_unit(match.group("unit"))
    if unit not in KNOWN_UNITS:
        return None

    return {"product_name": name, "quantity": quantity, "unit": unit}


def parse_line_partial(line: str) -> dict:
    """To'liq o'qilmagan qatordan faqat ANIQ yozilganini oladi:
    ``{product_name, quantity|None, unit|None}``. Yetishmagan miqdor/
    birlik hech qachon to'qilmaydi — ``None`` qoladi (keyin kassirdan
    so'raladi). Oxiridagi yolg'iz son miqdor deb olinadi."""
    text = _clean_apostrophes(line).strip()

    match = _QTY_ONLY_RE.match(text)
    if match:
        quantity = _to_quantity(match.group("qty"))
        if quantity is not None:
            return {
                "product_name": normalize_name_words(match.group("name").strip()),
                "quantity": quantity, "unit": None,
            }

    match = _UNIT_ONLY_RE.match(text)
    if match:
        unit = _normalize_unit(match.group("unit"))
        if unit in KNOWN_UNITS:
            return {
                "product_name": normalize_name_words(match.group("name").strip()),
                "quantity": None, "unit": unit,
            }

    return {"product_name": normalize_name_words(text), "quantity": None, "unit": None}


def parse_short_answer(text: str) -> dict | None:
    """Kassirning qisqa javobi ("2 blok", "kg", "3", "kotta", "pishgan 2 kg").
    Natija: ``{"quantity", "unit", "quality", "unknown"}`` (yo'qlari ``None``/
    bo'sh); hech narsa tushunilmasa ``None``. Miqdor/birlikdan oldingi
    so'zlar HECH QACHON mahsulot nomi bo'lmaydi — faqat sifat yoki AI/
    kassir aniqlashtirishi kerak bo'lgan noaniq so'z. Mahsulotni
    almashtirish faqat aniq tanlov orqali."""
    raw = _clean_apostrophes(text).strip()
    if not raw:
        return None

    quantity = unit = None
    rest = raw
    pair = _PAIR_RE.search(raw)
    if pair:
        quantity = _to_quantity(pair.group("num") or pair.group("word"))
        unit = _normalize_unit(pair.group("unit"))
        rest = raw[:pair.start()] + " " + raw[pair.end():]
    else:
        unit_match = _UNIT_TOKEN_RE.search(raw)
        if unit_match:
            unit = _normalize_unit(unit_match.group("unit"))
            rest = rest[:unit_match.start()] + " " + rest[unit_match.end():]
        qty_match = _QTY_TOKEN_RE.search(rest)
        if qty_match:
            quantity = _to_quantity(qty_match.group("qty"))
            rest = rest[:qty_match.start()] + " " + rest[qty_match.end():]

    if unit is not None and unit not in KNOWN_UNITS:
        unit = None
    leftover = [normalize_name_words(word) for word in rest.split()]
    if len(leftover) > 4:
        return None
    known = [word for word in leftover if word.lower() in _QUALITY_WORDS]
    # Javob-emas so'zlar ("bilmayman", "ha") hech qachon sifat ham, noaniq so'z ham bo'lmaydi.
    unknown = [word for word in leftover if word.lower() not in _QUALITY_WORDS | _NON_ANSWERS]
    quality = " ".join(known) or None

    if quantity is None and unit is None and quality is None and not unknown:
        return None
    return {"quantity": quantity, "unit": unit, "quality": quality, "unknown": unknown}


def unknown_answer_words(text: str) -> list[str]:
    """Qisqa javobdagi kod o'qiy olmagan so'zlar (AI/kassir aniqlashtirishi
    mumkin bo'lganlar). Javob-emas so'zlar bu ro'yxatga kirmaydi."""
    answer = parse_short_answer(text)
    return answer["unknown"] if answer else []


_QUALITY_AI_INSTRUCTIONS = (
    "Sen Fokus AI kassir yordamchisisan. Kassirdan zakaz ro'yxatidagi mahsulot haqida "
    "yetishmagan ma'lumot so'raldi va u qisqa javob berdi. Senga mahsulot, berilgan savol va "
    "javobdagi tushunilmagan so'zlar beriladi. Agar bu so'zlar shu mahsulotning SIFATINI bildirsa "
    "(masalan pishgan, yirikroq, yangi, qattiq) — ularni AYNAN javobdagi ko'rinishida 'quality' ga yoz. "
    "Agar bu so'zlar BOSHQA mahsulot nomi bo'lsa (masalan 'olma' uchun 'karam') — ularni AYNAN "
    "javobdagi ko'rinishida 'product' ga yoz. Miqdor, birlik yoki brend nomini hech qachon "
    "qaytarma va hech narsani O'ZING TO'QIMA. Javob emas ('bilmayman') yoki sifatmi mahsulotmi "
    "noaniq bo'lsa — ikkalasi ham null. "
    'Faqat JSON: {"quality": matn yoki null, "product": matn yoki null}'
)


def _validated_words(value, allowed: set[str]) -> str | None:
    if not isinstance(value, str):
        return None
    words = [normalize_name_words(_clean_apostrophes(word)) for word in value.split()]
    if not words or len(words) > 3:
        return None
    for word in words:
        lowered = word.lower()
        if lowered not in allowed or lowered in _NON_ANSWERS or re.search(r"\d", lowered):
            return None
        if lowered in _HINT_TOKENS:
            return None
    return " ".join(words)


async def classify_answer_words(
    client: AsyncOpenAI | None, product_name: str, question: str, unknown_words: list[str]
) -> dict:
    """Mavjud AI orqali (yangi integratsiyasiz) tushunilmagan so'zlarni
    shu mahsulotning SIFATI yoki BOSHQA mahsulot nomi sifatida ajratadi:
    ``{"quality": str|None, "product": str|None}``. AI faqat kassir YOZGAN
    so'zlardan tanlay oladi. Xato, timeout yoki noaniq javobda ikkalasi
    ``None`` — chaqiruvchi hech narsani o'zgartirmaydi."""
    empty = {"quality": None, "product": None}
    if client is None or not unknown_words:
        return empty

    allowed = {word.lower() for word in unknown_words}
    try:
        response = await asyncio.wait_for(
            client.responses.create(
                model=_AI_MODEL,
                instructions=_QUALITY_AI_INSTRUCTIONS,
                input=(
                    f"Mahsulot: {product_name}\nSavol: {question}\n"
                    f"Javobdagi so'zlar: {' '.join(unknown_words)}"
                ),
            ),
            timeout=15,
        )
        data = json.loads(response.output_text)
    except Exception as error:  # noqa: BLE001
        print(f"OpenAI xatosi (classify_answer_words): {error!r}")
        return empty

    if not isinstance(data, dict):
        return empty
    product = _validated_words(data.get("product"), allowed)
    if product:
        return {"quality": None, "product": product}  # mahsulot ustun — nom almashmaydi, so'raladi
    return {"quality": _validated_words(data.get("quality"), allowed), "product": None}


async def resolve_quality_words(
    client: AsyncOpenAI | None, product_name: str, question: str, unknown_words: list[str]
) -> str | None:
    """``classify_answer_words`` ning faqat sifat qismi."""
    return (await classify_answer_words(client, product_name, question, unknown_words))["quality"]


def split_numbered_answers(text: str) -> tuple[list[tuple[int, str]], list[str]]:
    """"1. 2 blok\\n2. 1 kg" -> [(1, "2 blok"), (2, "1 kg")]. Ikkinchi
    qiymat — raqamsiz (tegishliligi noaniq) qatorlar."""
    numbered: list[tuple[int, str]] = []
    stray: list[str] = []
    for line in split_lines(text):
        match = _NUMBERED_RE.match(line)
        if match:
            numbered.append((int(match.group(1)), match.group(2).strip()))
        else:
            stray.append(line)
    return numbered, stray


def _finalize(item: dict) -> None:
    """Nom, miqdor, birlik to'liq VA noaniq so'z/taklif qolmagan bo'lsagina
    qator hal bo'ldi (``parsed``) deb belgilanadi."""
    partial = item.get("partial") or {}
    if (
        partial.get("product_name") and partial.get("quantity") is not None
        and partial.get("unit") is not None and not partial.get("unresolved")
        and not partial.get("replace_proposal")
    ):
        item["parsed"] = {
            "product_name": partial["product_name"], "quantity": partial["quantity"], "unit": partial["unit"],
        }
        item["partial"] = None


def _append_quality(partial: dict, quality: str | None) -> None:
    if quality and quality.lower() not in (partial["product_name"] or "").lower():
        partial["product_name"] = f"{partial['product_name']} {quality}".strip()


def apply_short_answer(
    item: dict, text: str, extra_quality: str | None = None, other_product: str | None = None
) -> bool:
    """Qisqa javobni ``item``ga qo'shadi (oldingi aniq ma'lumot saqlanadi).
    - Aniq miqdor/birlik/sifat har doim saqlanadi.
    - ``extra_quality`` (AI tasdiqlagan sifat) nomga qo'shiladi.
    - ``other_product`` (AI "boshqa mahsulot" degan): nom/miqdor/birlik
      O'ZGARMAYDI, almashtirish taklifi ``partial["replace_proposal"]`` da
      kassir tasdiqlashini kutadi. Taklif turganda boshqa javob rad etiladi.
    - Klassifikatsiya qilinmagan so'z ``partial["unresolved"]`` da yo'qolmay
      qoladi (nomga qo'shilmaydi) — kassir aniq tanlaydi.
    Faqat noaniq so'zdan iborat javob (AI tasdiqlamagan) rad etiladi
    (``False``, ``item`` o'zgarmaydi)."""
    answer = parse_short_answer(text)
    if answer is None:
        return False

    unknown = answer["unknown"]
    has_clear_part = answer["quantity"] is not None or answer["unit"] is not None or answer["quality"]

    partial = dict(item.get("partial") or parse_line_partial(item["raw_line"]))
    if other_product:
        partial["replace_proposal"] = {
            "product_name": other_product, "quantity": answer["quantity"], "unit": answer["unit"],
        }
        item["partial"] = partial
        return True

    if partial.get("replace_proposal"):
        # Taklif faqat aniq ha/yo'q yoki aniq tahrir bilan hal bo'ladi — oddiy
        # miqdor/birlik javobi uni o'chirmaydi va nomga/miqdorga tegmaydi.
        return False
    if unknown and not extra_quality and not has_clear_part:
        return False

    if answer["quantity"] is not None:
        partial["quantity"] = answer["quantity"]
    if answer["unit"] is not None:
        partial["unit"] = answer["unit"]
    _append_quality(partial, answer["quality"])

    unresolved = list(partial.get("unresolved") or [])
    if extra_quality:
        _append_quality(partial, extra_quality)
        confirmed = {word.lower() for word in extra_quality.split()}
        unresolved = [word for word in unresolved if word.lower() not in confirmed]
        unknown = [word for word in unknown if word.lower() not in confirmed]
    for word in unknown:
        if word.lower() not in {w.lower() for w in unresolved}:
            unresolved.append(word)
    partial["unresolved"] = unresolved
    item["partial"] = partial

    _finalize(item)
    return True


def parse_explicit_edit(text: str) -> dict | None:
    """Ixtiyoriy aniq tahrir: "yangi: Karam 2 dona" — qatorni to'liq yangi
    mahsulot bilan almashtiradi (kassir bunga majbur emas)."""
    match = _EDIT_RE.match(text or "")
    return parse_line_deterministic(match.group("line")) if match else None


def apply_explicit_edit(item: dict, text: str) -> bool:
    parsed = parse_explicit_edit(text)
    if parsed is None:
        return False
    item["parsed"] = parsed
    item["partial"] = None
    return True


_CHOICE_YES = {"ha", "xa", "ok", "ha, qo'shilsin"}
_CHOICE_NO = {"yo'q", "yoq", "qo'shma", "kerak emas"}
_CHOICE_REPLACE = {"almashtirish", "almashtir", "almashtiraman", "mahsulot"}
_CHOICE_DESCRIBE = {"tavsif", "tavsif qo'sh", "tavsif qo'shish", "tavsif qo'shaman"}


def resolve_unresolved_by_choice(item: dict, text: str) -> bool:
    """Kassirning aniq tanlovi.
    - Almashtirish taklifi (AI "boshqa mahsulot" degan): "ha" — almashtirish,
      "yo'q" — nom qoladi.
    - Klassifikatsiya qilinmagan so'z: "almashtirish" — so'z yangi mahsulot
      nomi bo'ladi, "tavsif" — nomga tavsif sifatida qo'shiladi, "yo'q" —
      so'z tashlanadi. Oddiy "ha" bu holatni HAL QILMAYDI.
    Aniq miqdor/birlik o'zgarmaydi. Boshqa javobda ``False``."""
    partial = item.get("partial") or {}
    proposal = partial.get("replace_proposal")
    unresolved = partial.get("unresolved")
    if not unresolved and not proposal:
        return False

    choice = _clean_apostrophes(text).strip().lower()

    if proposal:
        if choice not in _CHOICE_YES and choice not in _CHOICE_NO:
            return False
        if choice in _CHOICE_YES:
            partial["product_name"] = proposal["product_name"]
            if proposal["quantity"] is not None:
                partial["quantity"] = proposal["quantity"]
            if proposal["unit"] is not None:
                partial["unit"] = proposal["unit"]
            partial["unresolved"] = []
        partial.pop("replace_proposal", None)
    else:
        if choice in _CHOICE_REPLACE:
            partial["product_name"] = " ".join(unresolved)
        elif choice in _CHOICE_DESCRIBE:
            _append_quality(partial, " ".join(unresolved))
        elif choice not in _CHOICE_NO:
            return False
        partial["unresolved"] = []

    item["partial"] = partial
    _finalize(item)
    return True


def replace_question(old_name: str, new_name: str) -> str:
    """"Olmani karamga almashtirasizmi?" — oddiy -ni / -ga(-ka/-qa) qo'shimchalari."""
    old_word = (old_name or "").strip().lower()
    new_word = (new_name or "").strip().lower()
    dative = "qa" if new_word.endswith("q") else "ka" if new_word.endswith("k") else "ga"
    return f"{old_word.capitalize()}ni {new_word}{dative} almashtirasizmi?"


def parse_lines_deterministic(lines: list[str]) -> list[dict]:
    return [{"raw_line": line, "parsed": parse_line_deterministic(line)} for line in lines]


_AI_INSTRUCTIONS = (
    "Sen Fokus AI kassir yordamchisisan. Kassir bozor ro'yxatini qo'lda yozgan, "
    "ba'zi qatorlarni oddiy qoidalar bilan aniqlab bo'lmadi — ular senga beriladi. "
    "Har bir qatorni {product_name, quantity, unit} ko'rinishiga o'gir. "
    "Ruxsat etilgan birliklar FAQAT: " + ", ".join(KNOWN_UNITS) + ". "
    "'коробка'/'karopka'/'korobka' uchrasa — 'karobka'; 'yashig'/'yashiq'/'ящик' — 'yashik'; "
    "'ta' — 'dona' deb ol. So'z bilan yozilgan sonni raqamga o'gir (bir=1, ikki=2, uch=3, "
    "to'rt=4, besh=5). Raqam va birlik yopishib yozilgan bo'lsa ('1karopka') ularni ajrat. "
    "Miqdor yoki birlik yozilmagan bo'lsa — ularni O'ZING TO'QIMA, null qil. "
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

        result[line] = {"product_name": normalize_name_words(name.strip()), "quantity": quantity, "unit": unit}

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

    for item in results:
        if item["parsed"] is None:
            item["partial"] = parse_line_partial(item["raw_line"])

    return results
