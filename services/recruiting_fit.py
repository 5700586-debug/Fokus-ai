"""Vaqtni tejaydigan moslik filtri — jadval/asosiy talablar tekshiruvi.

BU MODUL BAHOLASH RUBRIKASIDAN (``recruiting_scoring.py``) ATAYLAB
ALOHIDA: talab mosligi (masalan smena yoki bayram kunlari ishlash)
axloqiy/kompetensiya bahosi EMAS — faqat vakansiyaning e'lon qilingan
talabiga texnik moslik (qarang loyihaning rekruting talab hujjati:
"jadval mos kelmasligi axloqiy minus emas, alohida 'talab mosligi'
natijasi bo'lsin"). Mos kelmasa ham nomzod "yomon" deb baholanmaydi —
natija neytral ``MISMATCH`` deb belgilanadi, suhbat behuda cho'zilmasin
degan maqsadda erta va qisqa yakunlanadi (qarang ``recruiting_bot.py``).

Noaniq holatlar (masalan nomzod smena tanlovini bermagan yoki vakansiya
uchun aniq talab sozlanmagan) HECH QACHON avtomatik "mos emas" deb
hukm qilinmaydi — faqat aniq ziddiyat bo'lganda ``MISMATCH``."""

from datetime import date

FIT = "fit"
MISMATCH = "mismatch"

SHIFT_DAY = "kunduzgi"
SHIFT_EVENING = "kechki"
SHIFT_ROTATING = "almashinuvli"
SHIFT_ANY = "farqi_yoq"


def check_min_age(birth_year: int | None, min_age: int, today: date | None = None) -> tuple[bool, str | None]:
    if birth_year is None:
        return True, None
    today = today or date.today()
    age = today.year - birth_year
    if age < min_age:
        return False, f"Yoshi (taxminan {age}) qonuniy minimal ishga qabul yoshidan ({min_age}) kichik."
    return True, None


def check_shift(shift_preference: str | None, required_shift: str | None) -> tuple[bool, str | None]:
    if not required_shift or not shift_preference:
        return True, None
    if shift_preference == SHIFT_ANY:
        return True, None
    if shift_preference != required_shift:
        return False, f"Vakansiya faqat \"{required_shift}\" smenani talab qiladi, nomzod \"{shift_preference}\"ni tanladi."
    return True, None


def check_weekends(holiday_available: int | None, requires_weekends: bool) -> tuple[bool, str | None]:
    if not requires_weekends or holiday_available is None:
        return True, None
    if holiday_available == 0:
        return False, "Vakansiya dam olish/bayram kunlarida ishlashni talab qiladi, nomzod ishlay olmasligini aytdi."
    return True, None


def compute_fit(
    *,
    birth_year: int | None,
    shift_preference: str | None,
    holiday_available: int | None,
    vacancy: dict,
    min_age: int,
    today: date | None = None,
) -> tuple[str, str | None]:
    """``(fit_result, fit_reason)`` — ``fit_result`` doim ``FIT`` yoki
    ``MISMATCH``, ``fit_reason`` faqat ``MISMATCH``da to'ldiriladi."""
    checks = (
        check_min_age(birth_year, min_age, today),
        check_shift(shift_preference, vacancy.get("required_shift")),
        check_weekends(holiday_available, bool(vacancy.get("requires_weekends"))),
    )
    for ok, reason in checks:
        if not ok:
            return MISMATCH, reason
    return FIT, None
