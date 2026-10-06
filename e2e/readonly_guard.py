"""Production read-only smoke E2E uchun MAJBURIY read-only himoya va javob tahlili.

Telethon yoki tarmoqqa bog'liq EMAS (oddiy Linux CI'da sinaladi, qarang
``tests/test_production_readonly_smoke.py``). ``e2e/run_production_readonly_smoke.py`` botga
HAR BIR xabar/tugma bosishdan OLDIN shu yerdagi tekshiruvlardan o'tadi — read-only prompt'ga emas,
KODga tayanadi. Ruxsat berilmagan har qanday narsa ``ReadOnlyViolation`` bilan darhol to'xtatadi.

Xavfsizlik chegarasi:
- Faqat ``ALLOWED_OUTBOUND_TEXTS`` dagi matnlar yuboriladi (buyruqlar ro'yxati qat'iy, aniq mos kelish).
- Faqat filial tanlash callback'i (``bos:br:<indeks>:<bugungi sana>``) bosiladi. Baho, "Filialni yopish",
  tasdiqlash, ha/yo'q, jarima/minus va xodimga ball yozadigan har qanday callback — bloklanadi.
- Tugma yorlig'i xavfli so'z bo'lsa (baho, yopish, tasdiqlash, ha/yo'q, jarima...) — callback
  ruxsat etilgan ko'rinishda bo'lsa ham bloklanadi.
"""

import re

from services import messages

TARGET_BOT_USERNAME = "Xoqandiy_ai_bot"
EXPECTED_TESTER_TELEGRAM_ID = 7952886089

# Qat'iy ruxsat: faqat shu matnlar yuboriladi. "🧑‍💼 Nazoratchi" — faqat bo'lim menyusini ko'rsatadigan
# navigatsiya tugmasi (ReplyKeyboard), hech narsa yozmaydi/o'zgartirmaydi.
ALLOWED_OUTBOUND_TEXTS = frozenset({"/start", "/baholash", "/kunniyop", "🧑‍💼 Nazoratchi"})

_BRANCH_CALLBACK_RE = re.compile(r"^bos:br:(\d{1,2}):(\d{8})$")

# Tugma yorlig'ida shu so'zlar bo'lsa HECH QACHON bosilmaydi.
_DANGEROUS_LABEL_RE = re.compile(
    r"(baho|chala|norma|a'lo|ball|jarima|minus|yop|tasdiq|rozi|rad\b|\bha\b|yo'q|ayir|o'chir|saqla|"
    r"qo'sh|yubor|bekor|tugat|close|grade|penalty|confirm|approve)",
    re.IGNORECASE,
)

# Nazoratchi ko'radigan matnlarda bo'lmasligi shart bo'lgan inglizcha/tushunarsiz so'zlar.
FORBIDDEN_UI_WORDS_RE = re.compile(
    r"\b(score|review|pending|approve|approved|reject|rejected|time bonus|monthly|dashboard|founder\w*|"
    r"submit|cancel|confirm|oylik ball)\b",
    re.IGNORECASE,
)

# Hech qachon bot javobida ko'rinmasligi kerak bo'lgan xato izlari.
FORBIDDEN_REPLY_SUBSTRINGS = (
    "Kutilmagan xatolik", "query is too old", "response timeout expired", "query ID is invalid",
    "TelegramBadRequest", "Bad Request:", "Traceback", "ProgrammingError", "OperationalError",
)

DENIAL_TEXTS = frozenset({
    messages.GENERIC_DENIAL, messages.CASH_FINANCE_DENIAL,
    messages.MANAGEMENT_DENIAL, messages.REPEAT_OFFENDER_DENIAL,
})

EXPECTED_MENU_LABELS = ("📋 Baholash", "✅ Filialni yopish", "🏬 Filialni tanlash")
_STATUS_LINE_RE = re.compile(r"^(🔵|✅|🔴|⚠️) .+ — (baholanmagan|baholandi|damda|grafik yo'q)( \(Ruxsat: .+\))?$")

ROLE_STRANGER = "stranger"        # rolsiz foydalanuvchi: bot "begona" javob beradi
ROLE_NAZORATCHI = "nazoratchi"
ROLE_FOUNDER = "founder"          # tester uchun HECH QACHON bo'lmasligi kerak — darhol STOP
ROLE_UNKNOWN = "unknown"


class ReadOnlyViolation(Exception):
    """Read-only chegarasi buzilishi — skript darhol to'xtashi shart."""


def check_outbound_text(text: str) -> str:
    if text not in ALLOWED_OUTBOUND_TEXTS:
        raise ReadOnlyViolation(f"ruxsat etilmagan chiquvchi matn: {text!r}")
    return text


def check_callback(data, label: str, today_ymd: str) -> str:
    """``data`` — tugmaning callback_data'si (bytes/str), ``label`` — tugma yorlig'i,
    ``today_ymd`` — bugungi sana ``YYYYMMDD`` (kompaniya vaqt zonasida)."""
    if isinstance(data, bytes):
        data = data.decode("utf-8", errors="replace")
    if not isinstance(data, str):
        raise ReadOnlyViolation("callback_data yo'q — tugma bosilmaydi")

    match = _BRANCH_CALLBACK_RE.match(data)
    if match is None:
        raise ReadOnlyViolation(f"ruxsat etilmagan callback: {data!r} (yorliq: {label!r})")
    if match.group(2) != today_ymd:
        raise ReadOnlyViolation(f"filial callback'i bugungi sana emas: {data!r}")
    if _DANGEROUS_LABEL_RE.search(label or ""):
        raise ReadOnlyViolation(f"xavfli yorliqli tugma bosilmaydi: {label!r}")
    return data


def find_forbidden_reply_text(text: str | None) -> str | None:
    for needle in FORBIDDEN_REPLY_SUBSTRINGS:
        if text and needle in text:
            return needle
    return None


def find_forbidden_ui_word(texts: list[str]) -> str | None:
    for text in texts:
        match = FORBIDDEN_UI_WORDS_RE.search(text or "")
        if match:
            return f"{match.group(0)!r} :: {text!r}"
    return None


def classify_start_reply(reply_text: str | None, button_texts: list[str]) -> str:
    """``/start`` javobidan tester rolini aniqlaydi (faqat ko'rilgan narsa bo'yicha, taxmin emas)."""
    if "👑 Asoschi" in button_texts:
        return ROLE_FOUNDER
    if "🧑‍💼 Nazoratchi" in button_texts:
        return ROLE_NAZORATCHI
    if reply_text in DENIAL_TEXTS:
        return ROLE_STRANGER
    return ROLE_UNKNOWN


def is_denial(reply_text: str | None) -> bool:
    return reply_text in DENIAL_TEXTS


def status_lines_are_valid(branch_screen_text: str) -> tuple[bool, str]:
    """Filial ekranidagi xodim qatorlari faqat kelishilgan holat belgilari bilan chiqadi."""
    lines = [line for line in branch_screen_text.splitlines()[1:] if line.strip()]
    if not lines:
        return True, "xodim qatori yo'q (filialda aktiv xodim bo'lmasligi mumkin)"
    for line in lines:
        if not _STATUS_LINE_RE.match(line) and "Hozircha bu filialda aktiv xodim" not in line:
            return False, f"kutilmagan qator: {line!r}"
    return True, "OK"


def redact(text: str, secrets: list[str]) -> str:
    """Maxfiy qiymatlar (session/hash/id) logga chiqmasligi uchun."""
    for secret in secrets:
        if secret and len(secret) >= 4:
            text = text.replace(secret, "***")
    return text
