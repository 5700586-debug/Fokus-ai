"""60 kunlik KPI oldi kuzatuv/kalibratsiya davri va yangi xodim
adaptatsiya profili (15-30 kun).

Observation davrida hech qanday avtomatik jazo/bonus qo'llanmaydi —
bu servis faqat fakt yig'ish va taqqoslash uchun. KPI tavsiyasi 60
kundan keyin Founderga taqdim etiladi (matn shaklida, avtomatik
qo'llanmaydi).
"""

import random
from datetime import date, datetime

from repositories import baselines as baselines_repo
from services import learning as learning_service

CALIBRATION_WINDOW_DAYS = 60
ADAPTATION_WINDOW_DAYS = 30
MAX_FOLLOW_UPS = 2
DAILY_QUESTION_QUOTA_CHOICES = (2, 3)

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


# ---------------------------------------------------- kunlik savol-javob --

# Ta'minotchi va haydovchi bir kunda birga ishlagan holatlarni mustaqil
# tasdiqlashi uchun — ikkalasiga ham AYNAN BIR XIL matn bilan boriladi,
# chunki ``cross_check._normalize`` moslashtirish shu matn tengligiga
# tayanadi (qarang: services/cross_check.py).
CROSS_CHECK_DIMENSION = "bozor_hamkorligi"
CROSS_CHECK_QUESTION_TEXT = "Bugun ta'minotchi va haydovchi birga qaysi bozorga bordi va nima sotib olindi?"

# Har bir dimension uchun kamida 2 ta frazalash varianti — bir xil savol
# matni har kuni takrorlanmasligi uchun (talab: "bir xil matnda
# takrorlanmasin").
QUESTION_TEMPLATES: dict[str, list[str]] = {
    "assortiment izlash": [
        "Bugun qanday yangi assortiment variantlarini ko'rib chiqdingiz?",
        "Assortimentni kengaytirish uchun bugun nima qildingiz?",
    ],
    "yangi mahsulot topish": [
        "Bugun yangi mahsulot yoki yetkazib beruvchi topdingizmi? Qaysi?",
        "Bugungi qidiruvda diqqatingizni tortgan yangi mahsulot bo'ldimi?",
    ],
    "narx solishtirish": [
        "Bugun narxlarni nechta joydan solishtirdingiz?",
        "Bugungi xaridda eng arzon narxni qanday aniqladingiz?",
    ],
    "savdolashish": [
        "Bugun savdolashib, boshlang'ich narxdan pasaytira oldingizmi?",
        "Bugungi savdolashuvda qanday natijaga erishdingiz?",
    ],
    "bozorni o'rganish": [
        "Bugun qaysi bozor/do'konlarni o'rgandingiz?",
        "Bugungi bozor kuzatuvida nimani bilib oldingiz?",
    ],
    "tashabbus": [
        "Bugun sizdan so'ralmagan holda o'zingiz nima taklif qildingiz?",
        "Bugun qaysi masalada o'z tashabbusingizni ko'rsatdingiz?",
    ],
    "vazifani yopish": [
        "Bugungi barcha topshiriqlarni yakunladingizmi? Qaysi biri qoldi?",
        "Bugungi vazifalardan qay birini to'liq yopdingiz?",
    ],
    "ta'minotchiga amaliy yordam": [
        "Bugun ta'minotchiga qanday amaliy yordam berdingiz?",
        "Bugungi safarda ta'minotchi bilan qanday hamkorlik qildingiz?",
    ],
    "bozor jarayonida ishtirok": [
        "Bugun bozor jarayonida (yuklash/tanlash) qanday ishtirok etdingiz?",
        "Bugungi bozor tashrifida qaysi ishlarda qatnashdingiz?",
    ],
    "avtomobil tozaligi": [
        "Bugun avtomobilni tozaladingizmi? Ichi/tashqarisi qanday holatda?",
        "Bugungi avtomobil tozaligi haqida qisqacha yozing.",
    ],
    "odometr intizomi": [
        "Bugun spidometr ko'rsatkichlarini boshida/oxirida qayd qildingizmi?",
        "Bugungi km hisobini qanday yozib bordingiz?",
    ],
    "servis intizomi": [
        "Avtomobil servisga muhtoj joylari bormi? Bugun tekshirdingizmi?",
        "Bugun avtomobil texnik holatida e'tiborga oladigan narsa bo'ldimi?",
    ],
    "vaqt/marshrut intizomi": [
        "Bugungi marshrutni rejalashtirilgan vaqtda yakunladingizmi?",
        "Bugun marshrutda kechikish yoki og'ish bo'ldimi?",
    ],
}


def build_daily_question_plan(
    user_id: int, role_key: str, question_date: str, cross_check_available: bool = False
) -> list[dict]:
    """Bugungi kunning to'liq savol rejasini qaytaradi (deterministik —
    bir xil ``user_id``+``question_date`` doim bir xil natija beradi,
    shuning uchun scheduler qayta ishga tushsa ham xatti-harakat
    o'zgarmaydi). Chaqiruvchi (``calibration_bot.py``) shu ro'yxatdan
    hali yuborilmagan keyingi savolni tanlab oladi.
    """
    rng = random.Random(f"{user_id}:{question_date}")
    quota = rng.choice(DAILY_QUESTION_QUOTA_CHOICES)

    plan: list[dict] = []
    if cross_check_available:
        plan.append(
            {"dimension": CROSS_CHECK_DIMENSION, "question_text": CROSS_CHECK_QUESTION_TEXT, "is_cross_check": True}
        )

    candidates = list(get_kpi_candidates(role_key))
    rng.shuffle(candidates)

    for dimension in candidates[: max(quota - len(plan), 0)]:
        variants = QUESTION_TEMPLATES.get(dimension, [f"{dimension} bo'yicha bugun nima qildingiz?"])
        plan.append(
            {"dimension": dimension, "question_text": rng.choice(variants), "is_cross_check": False}
        )

    return plan


def is_vague_answer(text: str) -> bool:
    """Javob mavhum/mazmunsiz bo'lsa follow-up berish kerakligini
    aniqlaydi — mavjud ``learning.is_meaningful_understanding()``ni
    qayta ishlatadi (bir xil "faqat 'ha' qabul qilinmaydi" mezoni).
    """
    return not learning_service.is_meaningful_understanding(text)


def build_follow_up_text(dimension: str) -> str:
    if dimension == CROSS_CHECK_DIMENSION:
        return "Biroz aniqroq yozing: qaysi bozorga bordingiz va nima sotib olindi?"

    return f"Biroz aniqroq yozing: '{dimension}' bo'yicha aniq nima qildingiz?"


def ensure_session(user_id: int, role_key: str, start_date: str | None = None) -> dict:
    """Sessiya mavjud bo'lmasa yaratadi (idempotent), hech qanday xabar
    yubormaydi — approval callback ichida chaqirilishi mumkin, chunki
    uzoq interview shu yerda BOSHLANMAYDI.
    """
    resolved_start_date = start_date or date.today().isoformat()
    return baselines_repo.create_session(user_id, role_key, resolved_start_date)


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
