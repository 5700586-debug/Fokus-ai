"""60 kunlik KPI oldi kuzatuv/kalibratsiya davri va yangi xodim
adaptatsiya profili (15-30 kun).

Observation davrida hech qanday avtomatik jazo/bonus qo'llanmaydi —
bu servis faqat fakt yig'ish va taqqoslash uchun. KPI tavsiyasi 60
kundan keyin Founderga taqdim etiladi (matn shaklida, avtomatik
qo'llanmaydi).
"""

from datetime import date, datetime

from repositories import baselines as baselines_repo

CALIBRATION_WINDOW_DAYS = 60
ADAPTATION_WINDOW_DAYS = 30

# Bo'lim 13 dagi KPI nomzod yo'nalishlari — hali avtomatik KPI emas,
# faqat 60 kundan keyin Founderga taqdim etiladigan tavsiya ro'yxati.
TAMINOTCHI_KPI_CANDIDATES = [
    "assortiment izlash",
    "yangi mahsulot topish",
    "narx solishtirish",
    "savdolashish",
    "bozorni o'rganish",
    "tashabbus",
    "vazifani yopish",
]

HAYDOVCHI_KPI_CANDIDATES = [
    "ta'minotchiga amaliy yordam",
    "bozor jarayonida ishtirok",
    "avtomobil tozaligi",
    "odometr intizomi",
    "servis intizomi",
    "vaqt/marshrut intizomi",
]


def _parse_date(value: str) -> date:
    return datetime.fromisoformat(value).date()


def day_number_since(start_date: str, today: str | None = None) -> int:
    start = _parse_date(start_date)
    current = _parse_date(today) if today else date.today()
    return (current - start).days + 1


def is_within_calibration_window(start_date: str, today: str | None = None) -> bool:
    return day_number_since(start_date, today) <= CALIBRATION_WINDOW_DAYS


def is_within_adaptation_window(start_date: str, today: str | None = None) -> bool:
    return day_number_since(start_date, today) <= ADAPTATION_WINDOW_DAYS


def get_kpi_candidates(role_key: str) -> list[str]:
    return {
        "taminotchi": TAMINOTCHI_KPI_CANDIDATES,
        "haydovchi": HAYDOVCHI_KPI_CANDIDATES,
    }.get(role_key, [])


def record_role_baseline(role_key: str, dimension: str, description: str, source_note: str | None = None) -> int:
    return baselines_repo.add_role_baseline(role_key, dimension, description, source_note)


def get_role_baselines(role_key: str) -> list[dict]:
    return baselines_repo.get_role_baselines(role_key)


def record_adaptation_rating(
    user_id: int,
    role_key: str,
    start_date: str,
    dimension: str,
    rating: str,
    note: str | None = None,
    today: str | None = None,
) -> int:
    day_number = day_number_since(start_date, today)
    return baselines_repo.record_adaptation_rating(
        user_id, role_key, start_date, day_number, dimension, rating, note
    )


def get_adaptation_profile(user_id: int) -> list[dict]:
    return baselines_repo.get_adaptation_profile(user_id)
