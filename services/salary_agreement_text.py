"""Oylik kelishuvi matnini (erkin yozuv) aniq maydonlarga ajratish va xodimni mavjud tasdiqlangan xodimlar orasidan topish.

Faqat deterministik qoidalar (AI/pullik integratsiya yo'q). Tushunilmagan yoki ikki xil o'qilishi mumkin bo'lgan qism HECH
QACHON taxmin qilinmaydi — ``ParseResult.problems``da qoladi va Founderdan so'raladi."""

import re
from dataclasses import dataclass, field
from datetime import date
from difflib import SequenceMatcher

import employees
from config import RECRUITING_BRANCH_NAMES
from services import salary_agreement as sa

FIELDS = ("employee", "tariff", "fixed_salary", "work_days", "daily_minutes", "effective_from", "result_bonus_cap")
_AMOUNT = r"(\d[\d\s .,]*?)\s*(mln|million|milyon|ming|min|k|m)?\b"
# Yorliq so'zi (imlo variantlari bilan): bunday so'z bilan boshlangan qator ism emas
_LABEL_WORD = re.compile(
    r"\s*(?:ta[rn]?r?if\w{0,2}|taraf|tarf|fi[kx]s\w{0,2}|fix|oylik\w{0,2}|oyiga|oyda|kuniga|kunlik|natija|"
    r"b[ou]n[uo]s\w{0,2}|boshlan\w*|sana\w?|kelishuv\w*)(?![a-z'])",
    re.I,
)
_APOS = re.compile(r"['‘’`ʻʼ]")


@dataclass
class ParseResult:
    values: dict = field(default_factory=dict)  # FIELDS ichidan; employee uchun {"name", "branch_hint"}
    problems: dict = field(default_factory=dict)  # field -> foydalanuvchiga savol


_CYR = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo", "ж": "j", "з": "z", "и": "i", "й": "y",
    "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f",
    "х": "x", "ц": "s", "ч": "ch", "ш": "sh", "щ": "sh", "ъ": "", "ы": "i", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    "ў": "o'", "қ": "q", "ғ": "g'", "ҳ": "h",
}
_MONTHS = {
    "yanvar": 1, "fevral": 2, "mart": 3, "aprel": 4, "may": 5, "iyun": 6, "iyul": 7, "avgust": 8,
    "sentabr": 9, "sentyabr": 9, "oktabr": 10, "oktyabr": 10, "noyabr": 11, "dekabr": 12,
}


def translit(text: str) -> str:
    """O'zbek kirill / aralash yozuvni lotinga o'tkazadi (harfma-harf; lotin harflar o'zgarmaydi)."""
    return "".join(_CYR.get(ch, ch) for ch in (text or "").lower())


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", _APOS.sub("", translit(text))).strip()


class Ambiguous(ValueError):
    pass


def parse_amount(text: str) -> int:
    """"1.800.000", "1 800 000", "1800000", "1,8 mln", "700 ming" -> so'm. Birligi yo'q kichik son (masalan "700")
    ikki xil o'qiladi (700 ming / 1 million kabi) — ``Ambiguous``."""
    raw = norm(text)
    raw = re.sub(r"\b(som|sum|so'm|somgacha|gacha|oyiga|oyda)\b|som\w*", "", raw).strip()
    match = re.fullmatch(_AMOUNT, raw)
    if not match:
        raise sa.ValidationError("Summani tushunmadim.")
    number, unit = match.group(1).strip(), match.group(2)
    if unit:
        scale = 1_000_000 if unit in ("mln", "million", "milyon", "m") else 1000
        if not re.fullmatch(r"\d+([.,]\d+)?", number.replace(" ", "")):
            raise sa.ValidationError("Summani tushunmadim.")
        value = round(float(number.replace(" ", "").replace(",", ".")) * scale)
        sa.validate_salary_amount(value)
        return value
    compact = re.sub(r"[\s ]", "", number)
    if re.search(r"[.,]", compact):
        return sa.parse_salary(compact)
    if not compact.isdigit():
        raise sa.ValidationError("Summani tushunmadim.")
    if int(compact) < 10_000:
        raise Ambiguous(f"«{compact}» qancha so'm? Aniq yozing: «{compact} ming» yoki «{compact} million».")
    return sa.parse_salary(compact)


def _grab(label_pattern: str, text: str) -> str | None:
    match = re.search("(?:" + label_pattern + ")" + r"[^\S\n]*[:=\-–—]?[^\S\n]*([^\n;]*)", text, re.I)
    return match.group(1).strip() if match else None


def _set_amount(result: ParseResult, key: str, raw: str | None) -> None:
    if raw is None:
        return
    try:
        result.values[key] = parse_amount(raw)
    except Ambiguous as error:
        result.problems[key] = str(error)
    except sa.ValidationError:
        result.problems[key] = "Summani tushunmadim. Masalan: 1 800 000 yoki 1,8 mln."


def parse_text(text: str, today: date | None = None, name_words: int = 2) -> ParseResult:
    result = ParseResult()
    lowered = _APOS.sub("", translit(text))
    lines = [line.strip() for line in lowered.splitlines() if line.strip()]

    # Ism qatori istalgan o'rinda: yorliq so'zi bilan boshlanmagan, raqamsiz birinchi qator ("Ism Familiya — Filial")
    for line in lines:
        if _LABEL_WORD.match(line) or any(ch.isdigit() for ch in line.split("—")[0].split("–")[0]) or re.search(r"\d{4}", line):
            continue
        parts = re.split(r"\s+[—–-]\s+|\s*[—–,]\s*", line, maxsplit=1)
        if len(parts) == 1:  # ajratgichsiz: "Ism Familiya Saturn Charhiy"
            for branch in RECRUITING_BRANCH_NAMES:
                if norm(line).endswith(" " + norm(branch)):
                    parts = [line[: len(line) - len(branch)].strip(), branch]
                    break
        name = parts[0].strip(" :,.")
        if name and len(name.split()) >= name_words and not any(ch.isdigit() for ch in name):
            result.values["employee"] = {"name": name, "branch_hint": parts[1].strip() if len(parts) > 1 else None}
            break

    tariff = _grab(r"\bta[rn]?r?if\w*|\btaraf\w*|\btarf\w*", lowered)
    if tariff is not None:
        match = re.match(r"(\d+)", tariff)
        if match and int(match.group(1)) in sa.TARIFFS:
            result.values["tariff"] = int(match.group(1))
        else:
            result.problems["tariff"] = "Tarifni 1, 2 yoki 3 deb yozing."

    _set_amount(result, "fixed_salary", _grab(r"\b(?:fi[kx]s\w*|fix\w*|oylik\w*)", lowered))
    bonus = _grab(r"\b(?:natija\s*)?b[ou]n[uo]s\w*", lowered)
    if bonus is not None:
        if re.fullmatch(r"(yoq|yo'q|yo‘q|0|belgilanmagan)", norm(bonus)):
            result.values["result_bonus_cap"] = None
            result.values["bonus_none"] = True
        else:
            _set_amount(result, "result_bonus_cap", bonus)

    days = re.search(r"(?<![\d.\-/])(\d{1,2})[^\S\n]*(?:ta[^\S\n]*)?(?:ish[^\S\n]*)?kun\w*", lowered, re.I)
    if days:
        try:
            result.values["work_days"] = sa.parse_days(days.group(1))
        except sa.ValidationError as error:
            result.problems["work_days"] = str(error)
    else:
        label = re.search(r"\boyiga\s*[:=\-]?\s*(\d{1,2})\s*(?=$|[\n,;.])", lowered, re.I | re.M)
        if label:
            try:
                result.values["work_days"] = sa.parse_days(label.group(1))
            except sa.ValidationError as error:
                result.problems["work_days"] = str(error)

    hours = re.search(r"(?:kuniga\s*[:=\-]?\s*)?(\d{1,2}(?:[.,:]\d{1,2})?)\s*soat", lowered, re.I)
    if hours:
        try:
            result.values["daily_minutes"] = sa.parse_daily_minutes(hours.group(1))
        except sa.ValidationError as error:
            result.problems["daily_minutes"] = str(error)

    if "daily_minutes" not in result.values and "daily_minutes" not in result.problems:
        raw_hours = _grab(r"\bkuniga", lowered)
        if raw_hours and re.fullmatch(r"\d{1,2}([.,:]\d{1,2})?", raw_hours):
            try:
                result.values["daily_minutes"] = sa.parse_daily_minutes(raw_hours)
            except sa.ValidationError as error:
                result.problems["daily_minutes"] = str(error)

    month = re.search(r"(?<![\d.])(\d{1,2})\s*[-\s]?\s*(" + "|".join(_MONTHS) + r")\w*\s*,?\s*(\d{4})", lowered)
    date_match = None if month else re.search(r"\b(\d{1,2}[./-]\d{1,2}[./-]\d{4}|\d{4}-\d{2}-\d{2})\b", lowered)
    if month:
        try:
            result.values["effective_from"] = sa.parse_effective_date(
                f"{int(month.group(1)):02d}.{_MONTHS[month.group(2)]:02d}.{month.group(3)}", today
            )
        except sa.ValidationError as error:
            result.problems["effective_from"] = str(error)
    elif date_match:
        raw = date_match.group(1)
        if re.match(r"\d{1,2}[/-]", raw):
            raw = raw.replace("/", ".").replace("-", ".")
        try:
            result.values["effective_from"] = sa.parse_effective_date(raw, today)
        except sa.ValidationError as error:
            result.problems["effective_from"] = str(error)
    return result


def parse_bare(field_key: str, text: str, today: date | None = None) -> ParseResult:
    """So'ralgan bitta maydonga qisqa javob ("1,8 mln", "28", "11", "01.10.2026", "3")."""
    result = ParseResult()
    raw = (text or "").strip()
    try:
        if field_key in ("fixed_salary", "result_bonus_cap"):
            if field_key == "result_bonus_cap" and norm(raw) in ("yoq", "yoq", "0", "bonus yoq"):
                result.values["bonus_none"] = True
                result.values[field_key] = None
            else:
                result.values[field_key] = parse_amount(raw)
        elif field_key == "work_days":
            result.values[field_key] = sa.parse_days(re.sub(r"(?i)\s*(ta\s*)?(ish\s*)?kun\w*", "", raw).strip())
        elif field_key == "daily_minutes":
            result.values[field_key] = sa.parse_daily_minutes(raw)
        elif field_key == "effective_from":
            result.values[field_key] = sa.parse_effective_date(raw.replace("/", "."), today)
        elif field_key == "tariff":
            if raw.isdigit() and int(raw) in sa.TARIFFS:
                result.values[field_key] = int(raw)
            else:
                result.problems[field_key] = "Tarifni 1, 2 yoki 3 deb yozing."
        elif field_key == "employee":
            parts = re.split(r"\s+[—–-]\s+|\s*[—–,]\s*", _APOS.sub("", raw), maxsplit=1)
            result.values[field_key] = {"name": parts[0].strip(), "branch_hint": parts[1].strip() if len(parts) > 1 else None}
    except Ambiguous as error:
        result.problems[field_key] = str(error)
    except sa.ValidationError as error:
        result.problems[field_key] = str(error)
    return result


# ----------------------------------------------------------- xodimni topish --


def _tokens(*parts) -> set[str]:
    return {t for part in parts if part for t in norm(part).replace("-", " ").split()}


def _canon(token: str) -> str:
    return re.sub(r"(.)\1+", r"\1", token.replace("x", "h").replace("w", "v"))


def _close(a: str, b: str) -> bool:
    a, b = _canon(a), _canon(b)
    return a == b or (min(len(a), len(b)) >= 4 and SequenceMatcher(None, a, b).ratio() >= 0.8)


def _branch_matches(hint: str | None) -> list[str]:
    if not hint:
        return []
    h = norm(hint)
    exact = [b for b in RECRUITING_BRANCH_NAMES if norm(b) == h] or [b for b in RECRUITING_BRANCH_NAMES if h in norm(b)]
    if exact:
        return exact
    return [b for b in RECRUITING_BRANCH_NAMES if all(any(_close(w, bw) for bw in norm(b).split()) for w in h.split())]


def find_employees(name: str, branch_hint: str | None = None) -> tuple[list[dict], bool]:
    """(nomzodlar, aniq) — faqat tasdiqlangan xodimlar. ``aniq`` — ism AYNAN mos, nomzod bitta va filial ko'rsatmasi
    (bo'lsa) unga mos. Ism imlo xatosi bilan yozilgan bo'lsa (kirill/lotin farqi, harf xatosi) o'xshash nomzodlar
    qaytadi, lekin ``aniq=False`` — Founder tanlaydi. Yangi xodim HECH QACHON yaratilmaydi."""
    want = _tokens(name)
    if not want:
        return [], False
    profiles = [p for branch in RECRUITING_BRANCH_NAMES for p in employees.list_approved_by_branch(branch)]
    have = lambda p: _tokens(p.get("familiya"), p.get("ism"), p.get("otasining_ismi"))  # noqa: E731
    found = [p for p in profiles if want <= have(p)]
    fuzzy = False
    if not found:
        fuzzy = True
        found = [p for p in profiles if all(any(_close(w, t) for t in have(p)) for w in want)]
    if len(found) != 1 or fuzzy:
        return found, False
    hint_branches = _branch_matches(branch_hint)
    exact = not branch_hint or (hint_branches and found[0]["branch"] in hint_branches)
    return found, bool(exact)
