"""Saturn nizomi, korporativ madaniyati va 8 lavozim chek-listini ASL manbadan (``content/saturn_rules/source.txt``)
``company_rules`` kanonik jadvaliga xavfsiz import qilish.

Asl matn HECH QACHON tahrirlanmaydi: manifest (``manifest.json``) faqat texnik ajratish xaritasi — har bir band/iqtibos
asl fayldagi aniq qator va belgi oralig'iga bog'langan, matn import paytida manbadan AYNAN kesib olinadi (qo'lda qayta
terilmaydi). Ball miqdori faqat manbadagi "–N ball" satridan olinadi; miqdorsiz bandlarga ball taxmin qilinmaydi.

Import: default dry-run; ``plan`` va ``apply`` BITTA tekshiruv kodini ishlatadi; bitta tranzaksiya; idempotent;
mavjud boshqa matn/ball bo'lsa ustidan yozmaydi (aniq konflikt). Production'da avtomatik ishlamaydi — faqat Founder
amali orqali (``discipline_bot.py``).
"""

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE_PATH = ROOT / "content" / "saturn_rules" / "source.txt"
MANIFEST_PATH = ROOT / "content" / "saturn_rules" / "manifest.json"

ORIGINAL_SOURCE_NAME = "SATURN_NIZOM_CHEKLIST_MANBA.txt"
MANIFEST_VERSION = 1
METADATA_LINES = (1, 2)  # manba/sana va tayyorlash izohi — nizom emas

# ---------------------------------------------------------------- bo'limlar --

_SEPARATOR_RE = re.compile(r"^#{10} (.+?) #{10}$")

# Ajratkichdagi texnik nom -> (bo'lim kaliti, turi, manba nomi (UI uchun))
SECTION_META = {
    "KORPORATIV MADANIYAT": ("madaniyat", "culture", "Korporativ madaniyat"),
    "NIZOMLAR": ("nizomlar", "nizom", "Nizomlar"),
    "OMBORCHI": ("omborchi", "checklist", "Omborchi chek-listi"),
    "KASSIR": ("kassir", "checklist", "Kassir chek-listi"),
    "TOZALIK XODIMI": ("tozalik_xodimi", "checklist", "Tozalik xodimi chek-listi"),
    "NON BOLIMI": ("non_bolimi", "checklist", "Non bo'limi chek-listi"),
    "KOLBASA VA SARYOG": ("kolbasa_saryog", "checklist", "Kolbasa, pishloq va sariyog' bo'limi chek-listi"),
    "TOVUQ GOSHT CHUCHVARA LAGMON": ("muzlatilgan", "checklist", "Muzlatilgan mahsulotlar bo'limi chek-listi"),
    "OSHPAZ": ("oshpaz", "checklist", "Oshpaz chek-listi"),
    "MEVACHI": ("mevachi", "checklist", "Meva-sabzavot bo'limi xodimi chek-listi"),
}
EXPECTED_SECTION_ORDER = tuple(SECTION_META)

# Muhammadiy tasdiqlagan rasmiy 1–26 xarita (faqat NIZOMLAR bo'limidagi bonus modelidan KEYINGI 26 band).
OFFICIAL_NIZOM_TITLES = (
    "QOIDALAR ASOSIDA ISH TUTISH",
    "QOIDALAR HAMMA UCHUN BIR XIL",
    "BONUS VA MINUS BALL HISOBI",
    "XATOSINI O‘ZI TAN OLISH",
    "MINUS BALLGA NOROZILIK BILDIRISH",
    "“NOANIQ” HOLATNI QAYTA KO‘RIB CHIQISH",
    "ADOLATLI NIZOM",
    "OLDINDAN RUXSAT OLISH",
    "UZOQ MUDDATLI RUXSAT",
    "RUXSATNING SABABI VA MUDDATI",
    "BUYRUQDA BALL KO‘RSATILMAGAN BO‘LSA",
    "NIZOMNI BILMASLIK BAHONA EMAS",
    "MIJOZ BILAN SALOMLASHISH",
    "RAHBAR BERGAN VAZIFANI BAJARISH",
    "DO‘KONNI YOPISH TARTIBI",
    "KOMPANIYA BUYUMLARIDAN FOYDALANISH",
    "ORQA ESHIK VA YUKLARNI KIRITISH",
    "ISHGA VAQTIDA KELISH",
    "TELEFONDAN FOYDALANISH",
    "KALITLARNI JOYIGA QO‘YISH",
    "ASBOBLAR VA ELEKTR SIMLARINI TEKSHIRISH",
    "MIJOZ VA TA’MINOTCHILARDAN MANFAAT KUTMASLIK",
    "KATTA VA KICHIK O‘G‘IRLIK",
    "OMBORDA TARTIB SAQLASH",
    "DAM OLISH KUNIDA VAZIFANI TOPSHIRISH",
    "ISH JOYIDA ODOB VA PROFESSIONAL MASOFA",
)
BONUS_MODEL_TITLE = "BONUS VA MINUS BALLARNI HISOBLASH MODELI"
NIZOM_DOC_TITLE = "KOMPANIYANING ICHKI TARTIB QOIDALARI"
CULTURE_HEADING = "SATURN JAMOASINING KORPORATIV MADANIYATI"

# Texnik ID'lar (rasmiy nizom raqami EMAS): kanonik jadvalda rule_number sifatida saqlanadi, UI ko'rsatmaydi.
TECHNICAL_ID_BASE = {"bonus_model": 10_000, "culture": 10_100}
CHECKLIST_ID_BASE = {
    "omborchi": 10_200, "kassir": 10_300, "tozalik_xodimi": 10_400, "non_bolimi": 10_500,
    "kolbasa_saryog": 10_600, "muzlatilgan": 10_700, "oshpaz": 10_800, "mevachi": 10_900,
}

# Korporativ madaniyat bandlari (sarlavhasiz matn) — qo'lda belgilangan qator oraliqlari; matn manbadan kesib olinadi.
# (birinchi qator, oxirgi qator, nomzod_emasmi)
CULTURE_BANDS = (
    (7, 7, True), (8, 10, False), (11, 13, False), (14, 14, True), (15, 17, False), (18, 18, True),
    (19, 20, False), (21, 22, False), (23, 25, False), (26, 26, False), (27, 27, False), (28, 30, False),
    (31, 33, False), (34, 35, False),
)

_PENALTY_RE = re.compile(r"[–−-]\s?(\d+)\s*ball", re.IGNORECASE)
_AMOUNT_IN_HEADING_RE = re.compile(r"[–−-]\s?\d+\s*BALL", re.IGNORECASE)

_QUOTE_TRANSLATION = str.maketrans({
    "‘": "'", "’": "'", "ʻ": "'", "ʼ": "'", "`": "'", "´": "'",
    "“": '"', "”": '"', "«": '"', "»": '"',
})


def normalize_title(text: str) -> str:
    """Faqat solishtirish uchun (saqlanmaydi): tipografik apostrof/qo'shtirnoq va chekka bo'shliqlarni tenglashtiradi."""
    return re.sub(r"\s+", " ", text.translate(_QUOTE_TRANSLATION)).strip().upper()


def read_source(path: Path | None = None) -> str:
    return (path or SOURCE_PATH).read_bytes().decode("utf-8")


def source_sha256(path: Path | None = None) -> str:
    return hashlib.sha256((path or SOURCE_PATH).read_bytes()).hexdigest()


class SourceError(Exception):
    """Manba tuzilishi/rasmiy xaritaga mos kelmasa — import to'xtaydi."""


class Source:
    """Asl matn + qator/belgi oraliqlari."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.lines = text.split("\n")
        self.offsets: list[int] = []
        position = 0
        for line in self.lines:
            self.offsets.append(position)
            position += len(line) + 1

    def span(self, first_line: int, last_line: int) -> tuple[int, int]:
        """1-asosli qatorlar -> (boshlanish, tugash) belgi oralig'i."""
        return self.offsets[first_line - 1], self.offsets[last_line - 1] + len(self.lines[last_line - 1])

    def slice(self, first_line: int, last_line: int) -> str:
        start, end = self.span(first_line, last_line)
        return self.text[start:end]

    def is_blank(self, number: int) -> bool:
        return not self.lines[number - 1].strip()


def _is_heading(line: str) -> bool:
    stripped = line.strip()
    if not stripped or stripped != stripped.upper() or not any(ch.isalpha() for ch in stripped):
        return False
    if stripped.startswith("NATIJA:") or _AMOUNT_IN_HEADING_RE.search(stripped):
        return False
    return len(stripped) <= 100 and not stripped.endswith(".")


# ------------------------------------------------- ball variantlari (qo'lda belgilangan metadata) --
# Faqat QO'SHIMCHA texnik metadata: kimga tegishli, qaysi qatorlar shart/old shart. Ball esa har doim manbadagi
# "–N ball" satridan olinadi; matn bu yerda qayta yozilmaydi (faqat qator raqamlari).
#   condition: iqtibos/shart qatorlari (default — ball qatorining o'zi)
#   gate:      yakuniy tasdiqdan oldin nazoratchi tasdiqlashi shart bo'lgan old shart/javobgarlik qatorlari
#   target:    offender (default) | responsible | both | disputant | supplier | inspector
OPTION_META: dict[int, dict] = {
    10: {"condition": (9, 10)},
    13: {"condition": (11, 13)},
    17: {"condition": (16, 17)},
    121: {"target": "disputant", "gate": (121, 121)},
    129: {"target": "inspector"},
    181: {"gate": (181, 183)},
    185: {"skip": True},  # 181-qatordagi o'sha natijaning "NATIJA:" xulosasi — alohida variant emas
    228: {"target": "responsible", "gate": (228, 228)},
    306: {"target": "responsible", "gate": (306, 306)},
    390: {"written_warning": True},
    425: {"gate": (425, 425)},
    452: {"target": "responsible", "condition": (451, 452), "gate": (451, 452)},
    518: {"condition": (517, 518), "gate": (517, 518)},
    559: {"target": "both", "gate": (559, 559)},
    565: {"target": "both", "gate": (565, 565)},
    911: {"target": "supplier"},
}
NON_EMPLOYEE_TARGETS = frozenset({"supplier", "inspector"})

# Miqdorsiz yoki noaniq oqibatlar: matn katalogda ko'rinadi, lekin avtomatik ball YO'Q (Muhammadiy hal qiladi).
UNRESOLVED_NOTES = (
    (28, 30, "Ish vaqtida uyiga kirib chiqish/orqada gaplashib turish — 'minus ball yozilishiga sabab bo'ladi', miqdori ko'rsatilmagan."),
    (31, 33, "Xato haqida aytgan xodimga bonus — miqdorini rahbar belgilaydi (minus emas)."),
    (109, 111, "O'zini tan olsa minus ball 50 foizga kamayadi — qaysi ball asosida va yaxlitlash qoidasi ko'rsatilmagan (modifikator)."),
    (181, 183, "Buyruqning o'zida boshqa ball ko'rsatilgan bo'lsa 'o'sha miqdor qo'llanadi' — miqdor buyruqdan olinadi, bu yerda raqam yo'q."),
    (230, 230, "Haqiqiy zarar yuz bersa moddiy javobgarlik 'alohida tartibda' — qoidasi/miqdori ko'rsatilmagan."),
    (262, 268, "Bir haftada uch marta kech qolsa haftalik bonus berilmaydi — bonusdan mahrum qilish (minus ball emas)."),
    (280, 280, "Yolg'on takrorlansa uch marta yozma ogohlantirish, keyin ishda qolishi qayta ko'rib chiqiladi — ball ko'rsatilmagan."),
    (329, 331, "Katta o'g'irlik — zarar qoplatiladi, ishda qolishi qayta ko'rib chiqiladi, jinoyat alomati bo'lsa topshiriladi — ball ko'rsatilmagan."),
    (333, 337, "'Telefon o'ynab o'tirish ham kompaniya vaqtini o'zlashtirish' — bu kichik o'g'irlik (−6)ga tegishlimi, aniq aytilmagan."),
    (392, 392, "Holat takrorlansa yoki jiddiy tegajog'lik aniqlansa ishda qolishi qayta ko'rib chiqiladi — ball ko'rsatilmagan."),
    (408, 408, "Omborchi hisobda xato qilsa zararni qoplaydi — moddiy javobgarlik miqdori ko'rsatilmagan."),
    (450, 450, "Kompyuterda chiqmay qolgan har bir mahsulot prixotchining KPI hisobiga minus — miqdori ko'rsatilmagan."),
    (497, 497, "Shogird imtihondan o'tsa ustoz kassirga bonus — bonus (minus emas)."),
    (519, 519, "Kassirga asosli shikoyat uch marta takrorlansa ishdan bo'shatiladi — ball emas, oqibat."),
    (933, 933, "Ta'minotchi qaytariladigan mahsulotni olmasa 'minus ball ta'minotchiga yoziladi' — miqdori ko'rsatilmagan va ta'minotchi xodim emas."),
    (988, 988, "Foydali yangilik uchun mevachiga maxsus bonus — bonus (minus emas)."),
    (1012, 1012, "Nazoratchi bonusi miqdori alohida KPI yoki kelishuv asosida — bonus (minus emas)."),
)


# ------------------------------------------------------------------ manifest --


def _last_content_line(src: Source, first: int, last: int) -> int:
    while last > first and src.is_blank(last):
        last -= 1
    return last


def _item(src: Source, *, key, section_key, kind, source_name, title_line, first_line, last_line, rule_number,
          official_number=None, candidate=True, title=None) -> dict:
    """Band yozuvi. ``title`` — sarlavha qatori (asl), ``content`` — sarlavhadan KEYINGI asl matn bo'lagi (yoki
    sarlavhasiz bandlarda butun oraliq). Matn oraliqlari belgi pozitsiyalari bilan bog'langan."""
    start, end = src.span(first_line, last_line)
    return {
        "key": key,
        "section": section_key,
        "kind": kind,
        "source_name": source_name,
        "rule_number": rule_number,
        "official_number": official_number,
        "title": title if title is not None else src.lines[title_line - 1],
        "title_line": title_line,
        "first_line": first_line,
        "last_line": last_line,
        "start": start,
        "end": end,
        "candidate": candidate,
    }


def _heading_lines(src: Source, first: int, last: int) -> list[int]:
    return [n for n in range(first, last + 1) if _is_heading(src.lines[n - 1]) and not _SEPARATOR_RE.match(src.lines[n - 1])]


def build_structure(src: Source) -> tuple[list[dict], list[dict], list[dict]]:
    """(bo'limlar, bandlar, ikkilamchi 'sarlavha' qatorlari). Tuzilish rasmiy xaritaga mos kelmasa ``SourceError``."""
    separators = [(n, _SEPARATOR_RE.match(line).group(1)) for n, line in enumerate(src.lines, 1) if _SEPARATOR_RE.match(line)]
    if tuple(name for _, name in separators) != EXPECTED_SECTION_ORDER:
        raise SourceError(f"bo'lim ajratkichlari kutilgan 10 ta emas/tartibi boshqa: {[name for _, name in separators]}")

    last_nonblank = _last_content_line(src, 1, len(src.lines))
    sections: list[dict] = []
    for index, (line_no, name) in enumerate(separators):
        key, kind, source_name = SECTION_META[name]
        next_sep = separators[index + 1][0] if index + 1 < len(separators) else last_nonblank + 2
        sections.append({
            "key": key, "name": name, "kind": kind, "source_name": source_name,
            "separator_line": line_no, "first_line": line_no + 1,
            "last_line": _last_content_line(src, line_no + 1, next_sep - 1),
        })

    items: list[dict] = []
    for section in sections:
        key, kind = section["key"], section["kind"]
        first, last = section["first_line"], section["last_line"]
        name = section["source_name"]

        if key == "madaniyat":
            heading = next(n for n in range(first, last + 1) if src.lines[n - 1].strip())
            if src.lines[heading - 1] != CULTURE_HEADING:
                raise SourceError("korporativ madaniyat sarlavhasi topilmadi")
            covered = set()
            for number, (band_first, band_last, note) in enumerate(CULTURE_BANDS, 1):
                items.append(_item(
                    src, key=f"madaniyat:{number:02d}", section_key=key, kind="culture", source_name=name,
                    title_line=heading, first_line=band_first, last_line=band_last,
                    rule_number=TECHNICAL_ID_BASE["culture"] + number, candidate=not note,
                ))
                covered.update(range(band_first, band_last + 1))
            body = {n for n in range(heading + 1, last + 1) if src.lines[n - 1].strip()}
            if body - covered:
                raise SourceError(f"madaniyat qatorlari bandlarga kirmadi: {sorted(body - covered)}")
            continue

        headings = _heading_lines(src, first, last)
        if key == "nizomlar":
            if src.lines[headings[0] - 1] != NIZOM_DOC_TITLE or src.lines[headings[1] - 1] != BONUS_MODEL_TITLE:
                raise SourceError("NIZOMLAR kirish sarlavhalari kutilganidek emas")
            rule_headings = headings[2:]
            if len(rule_headings) != 26:
                raise SourceError(f"rasmiy 1–26 xarita manba bilan mos kelmadi: {len(rule_headings)} ta sarlavha")
            for number, (line_no, official) in enumerate(zip(rule_headings, OFFICIAL_NIZOM_TITLES), 1):
                if normalize_title(src.lines[line_no - 1]) != normalize_title(official):
                    raise SourceError(f"rasmiy xarita mos kelmadi: {number}-nizom {src.lines[line_no - 1]!r} != {official!r}")
            starts = [(headings[1], "bonus_model", None)] + [(n, "nizom", i) for i, n in enumerate(rule_headings, 1)]
        else:
            # Chek-list: birinchi sarlavha — bo'lim nomi (…CHEK-LISTI), undan keyingi satr — hisoblash izohi.
            if not src.lines[headings[0] - 1].endswith("CHEK-LISTI"):
                raise SourceError(f"{name}: chek-list nomi topilmadi")
            starts = [(n, "checklist", i) for i, n in enumerate(headings[1:], 1)]

        for position, (line_no, item_kind, number) in enumerate(starts):
            nxt = starts[position + 1][0] if position + 1 < len(starts) else last + 1
            last_line = _last_content_line(src, line_no, nxt - 1)
            if item_kind == "bonus_model":
                item_key, rule_number = "nizomlar:bonus_model", TECHNICAL_ID_BASE["bonus_model"]
                official_number = None
            elif item_kind == "nizom":
                item_key, rule_number, official_number = f"nizomlar:{number:02d}", number, number
            else:
                item_key = f"{key}:{number:02d}"
                rule_number, official_number = CHECKLIST_ID_BASE[key] + number, None
            items.append(_item(
                src, key=item_key, section_key=key, kind=item_kind, source_name=name,
                title_line=line_no, first_line=line_no, last_line=last_line, rule_number=rule_number,
                official_number=official_number,
            ))

    # Sarlavha/izoh qatorlari (bo'lim nomi, "Ichki hisobda 1 ball…") — katalog bandi EMAS, lekin qamrovda hisoblanadi.
    header_lines = []
    for section in sections:
        if section["key"] == "madaniyat":
            header_lines.append({"section": section["key"], "lines": [6]})
            continue
        covered_from = min((it["title_line"] for it in items if it["section"] == section["key"]), default=section["last_line"] + 1)
        if section["key"] == "nizomlar":
            covered_from = next(it["title_line"] for it in items if it["key"] == "nizomlar:bonus_model")
        header_lines.append({
            "section": section["key"],
            "lines": [n for n in range(section["first_line"], covered_from) if src.lines[n - 1].strip()],
        })
    return sections, items, header_lines


def build_options(src: Source, items: list[dict]) -> list[dict]:
    """Har bir "–N ball" satri (bonus modeli misollaridan tashqari) bitta ball varianti. Ball faqat shu satrdan olinadi."""
    options: list[dict] = []
    for item in items:
        if item["kind"] == "bonus_model":
            continue  # modeldagi "–6 ball" — hisoblash MISOLI, jarima emas
        ordinal = 0
        for line_no in range(item["first_line"], item["last_line"] + 1):
            for match in _PENALTY_RE.finditer(src.lines[line_no - 1]):
                ordinal += 1
                meta = OPTION_META.get(line_no, {})
                if meta.get("skip"):
                    ordinal -= 1
                    continue
                condition = meta.get("condition", (line_no, line_no))
                gate = meta.get("gate")
                target = meta.get("target", "offender")
                options.append({
                    "key": f"{item['key']}:o{ordinal}",
                    "item": item["key"],
                    "points": int(match.group(1)),
                    "line": line_no,
                    "points_start": src.offsets[line_no - 1] + match.start(),
                    "points_end": src.offsets[line_no - 1] + match.end(),
                    "condition_lines": list(condition),
                    "condition_start": src.span(*condition)[0],
                    "condition_end": src.span(*condition)[1],
                    "gate_lines": list(gate) if gate else None,
                    "target": target,
                    "apply_allowed": target not in NON_EMPLOYEE_TARGETS,
                    "written_warning": bool(meta.get("written_warning")),
                })
    return options


def build_manifest(text: str | None = None) -> dict:
    """Manifest — butunlay manbadan hosil qilinadi; matn qo'lda terilmaydi."""
    source_text = read_source() if text is None else text
    src = Source(source_text)
    sections, items, header_lines = build_structure(src)
    options = build_options(src, items)

    by_item: dict[str, list[dict]] = {}
    for option in options:
        by_item.setdefault(option["item"], []).append(option)
    for item in items:
        item_options = by_item.get(item["key"], [])
        simple = (
            len(item_options) == 1 and item_options[0]["target"] == "offender" and not item_options[0]["gate_lines"]
        )
        item["default_points"] = item_options[0]["points"] if simple else None

    unresolved = [
        {"first_line": a, "last_line": b, "note": note,
         "start": src.span(a, b)[0], "end": src.span(a, b)[1]}
        for a, b, note in UNRESOLVED_NOTES
    ]
    return {
        "version": MANIFEST_VERSION,
        "source": {
            "original_name": ORIGINAL_SOURCE_NAME,
            "stored_path": "content/saturn_rules/source.txt",
            "sha256": hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
            "bytes": len(source_text.encode("utf-8")),
            "lines": len(source_text.rstrip("\n").split("\n")),
            "metadata_lines": list(METADATA_LINES),
        },
        "official_nizom_titles": list(OFFICIAL_NIZOM_TITLES),
        "sections": sections,
        "section_headers": header_lines,
        "items": items,
        "penalty_options": options,
        "unresolved": unresolved,
    }


def manifest_json(manifest: dict) -> str:
    return json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=False) + "\n"


def load_manifest(path: Path | None = None) -> dict:
    return json.loads((path or MANIFEST_PATH).read_text(encoding="utf-8"))


# ---------------------------------------------------------- tekshiruv (dry-run va apply UMUMIY) --


def import_version(manifest: dict | None = None) -> str:
    manifest = manifest or load_manifest()
    return f"{manifest['source']['sha256'][:12]}-v{manifest['version']}"


def validate(text: str | None = None, manifest: dict | None = None) -> list[str]:
    """Manba va manifest yaxlitligi. Bo'sh ro'yxat = import qilish mumkin. Dry-run ham, apply ham AYNAN shuni ishlatadi."""
    errors: list[str] = []
    try:
        source_text = read_source() if text is None else text
        manifest = load_manifest() if manifest is None else manifest
    except (OSError, ValueError) as error:
        return [f"manba/manifest o'qilmadi: {type(error).__name__}"]

    src = Source(source_text)
    declared = manifest.get("source", {})
    raw = source_text.encode("utf-8")
    if hashlib.sha256(raw).hexdigest() != declared.get("sha256") or len(raw) != declared.get("bytes"):
        errors.append("manba SHA-256/hajmi manifestdagi bilan mos emas")
    if declared.get("original_name") != ORIGINAL_SOURCE_NAME:
        errors.append("manifestda yagona manba nomi noto'g'ri")
    if manifest.get("version") != MANIFEST_VERSION:
        errors.append("manifest versiyasi qo'llab-quvvatlanmaydi")

    try:
        rebuilt = build_manifest(source_text)
    except SourceError as error:
        return errors + [f"manba tuzilishi: {error}"]
    if json.loads(json.dumps(rebuilt)) != manifest:
        errors.append("manifest manbadan hosil qilinganiga teng emas (qayta yaratish kerak)")

    items = manifest.get("items", [])
    keys = [item["key"] for item in items]
    numbers = [item["rule_number"] for item in items]
    if len(set(keys)) != len(keys) or len(set(numbers)) != len(numbers):
        errors.append("band kalitlari yoki rule_number takrorlangan")
    official = [item for item in items if item["kind"] == "nizom"]
    if [item["rule_number"] for item in official] != list(range(1, 27)):
        errors.append("rasmiy 1–26 raqamlar noto'g'ri")
    for item in items:
        if item["kind"] != "nizom" and 1 <= item["rule_number"] <= 26:
            errors.append(f"{item['key']}: texnik ID rasmiy nizom raqamiga urildi")
        if src.text[item["start"]:item["end"]] != src.slice(item["first_line"], item["last_line"]):
            errors.append(f"{item['key']}: matn oralig'i manbaga mos emas")

    covered = set()
    for item in items:
        covered.update(range(item["title_line"], item["last_line"] + 1))
    for header in manifest.get("section_headers", []):
        covered.update(header["lines"])
    skipped = set(METADATA_LINES) | {s["separator_line"] for s in manifest.get("sections", [])}
    lost = [
        n for n, line in enumerate(src.lines, 1)
        if line.strip() and n not in covered and n not in skipped
    ]
    if lost:
        errors.append(f"manba qatorlari katalogda yo'q: {lost[:10]}")

    for option in manifest.get("penalty_options", []):
        line = src.lines[option["line"] - 1]
        match = _PENALTY_RE.search(line, option["points_start"] - src.offsets[option["line"] - 1])
        if match is None or int(match.group(1)) != option["points"]:
            errors.append(f"{option['key']}: ball qiymati manbadagi satrga mos emas")
        if src.text[option["points_start"]:option["points_end"]] != match.group(0) if match else True:
            errors.append(f"{option['key']}: ball oralig'i noto'g'ri")
    return errors


def _exact(src: Source, lines) -> str:
    return src.slice(lines[0], lines[1])


def build_rows(text: str | None = None, manifest: dict | None = None) -> tuple[list[dict], list[dict]]:
    """Kanonik ``company_rules`` va ball variantlari qatorlari — matn manbadan AYNAN kesib olinadi."""
    source_text = read_source() if text is None else text
    manifest = load_manifest() if manifest is None else manifest
    src = Source(source_text)
    kind_map = {"nizom": "nizom", "bonus_model": "bonus_model", "culture": "culture", "checklist": "checklist"}
    rule_rows: list[dict] = []
    number_by_key = {}
    for item in manifest["items"]:
        if item["kind"] == "culture":
            content = src.slice(item["first_line"], item["last_line"])
        else:
            body_first = next(n for n in range(item["title_line"] + 1, item["last_line"] + 1) if not src.is_blank(n))
            content = src.slice(body_first, item["last_line"])
        number_by_key[item["key"]] = item["rule_number"]
        rule_rows.append({
            "rule_number": item["rule_number"],
            "title": item["title"],
            "content": content,
            "catalog_kind": kind_map[item["kind"]],
            "source_key": item["key"],
            "source_name": item["source_name"],
            "default_penalty_amount": item["default_points"],
            "candidate": item["candidate"],
        })
    option_rows = [
        {
            "variant_key": option["key"],
            "rule_number": number_by_key[option["item"]],
            "points": option["points"],
            "condition_text": _exact(src, option["condition_lines"]),
            "gate_text": _exact(src, option["gate_lines"]) if option["gate_lines"] else None,
            "target": option["target"],
            "apply_allowed": 1 if option["apply_allowed"] else 0,
            "written_warning": 1 if option["written_warning"] else 0,
        }
        for option in manifest["penalty_options"]
    ]
    return rule_rows, option_rows


class ImportBlocked(Exception):
    """Manba/manifest tekshiruvidan o'tmadi yoki versiya mos emas — hech narsa yozilmaydi."""


def run_import(*, apply: bool, created_by: int, expected_version: str | None = None) -> dict:
    """``apply=False`` — dry-run (hech narsa yozmaydi). Ikkalasi ham bir xil tekshiruv va reja kodini ishlatadi;
    konflikt bo'lsa apply ham yozmaydi va dry-run bilan bir xil xulosa beradi."""
    from repositories import discipline as discipline_repo

    text, manifest = read_source(), load_manifest()
    errors = validate(text, manifest)
    if errors:
        raise ImportBlocked("; ".join(errors))
    version = import_version(manifest)
    if apply and expected_version != version:
        raise ImportBlocked(f"import versiyasi tasdiqlanmagan: kutilgan {version}")

    rule_rows, option_rows = build_rows(text, manifest)
    result = discipline_repo.import_catalog(rule_rows, option_rows, created_by=created_by, apply=apply)
    result["unresolved"] = len(manifest["unresolved"])
    result["version"] = version
    result["applied"] = bool(apply and not result["conflicts"])
    return result


if __name__ == "__main__":  # python -m services.company_rules_import  -> manifest.json yangilanadi
    MANIFEST_PATH.write_text(manifest_json(build_manifest()), encoding="utf-8")
    print(f"manifest yozildi: {MANIFEST_PATH}")
