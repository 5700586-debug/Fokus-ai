"""Kassir smena yopishidan oldingi kunlik 3 savollik hisobot V1:
prixodi chiqmagan tovar soni, "narxi qimmat" mijozlar soni, xodim
ustidan shikoyat — mavjud kamchilik gate'idan (``services/
shift_deficiency.py``) KEYIN, real ``/closeshift`` yopish jarayonidan
OLDIN ishlaydi (ketma-ketlik ``cash_shift_bot.py``da).

Bir smenaga bitta qator, har ustun NULL = savol hali javob
berilmagan. KPI/bonus/jarima/AI/dashboard ATAYLAB YO'Q.
"""

from datetime import datetime, timezone

from repositories import shift_daily_report as repo
from services import cash_shift

COMPLAINT_TYPE_RUDE = "rude"
COMPLAINT_TYPE_INATTENTIVE = "inattentive"
COMPLAINT_TYPE_SLOW = "slow"
COMPLAINT_TYPE_WRONG_INFO = "wrong_info"
COMPLAINT_TYPE_PRODUCT_NOT_FOUND = "product_not_found"
COMPLAINT_TYPE_INDIFFERENT = "indifferent"
COMPLAINT_TYPE_OTHER = "other"
KNOWN_COMPLAINT_TYPES = (
    COMPLAINT_TYPE_RUDE,
    COMPLAINT_TYPE_INATTENTIVE,
    COMPLAINT_TYPE_SLOW,
    COMPLAINT_TYPE_WRONG_INFO,
    COMPLAINT_TYPE_PRODUCT_NOT_FOUND,
    COMPLAINT_TYPE_INDIFFERENT,
    COMPLAINT_TYPE_OTHER,
)

PRICE_COMPLAINT_BUCKETS = ("0", "1", "2", "3", "4", "5", "6-10", "10+")

NO_PRIXOD_SIGNAL_THRESHOLD = 5

STEP_NO_PRIXOD = "no_prixod"
STEP_PRICE_COMPLAINT = "price_complaint"
STEP_STAFF_COMPLAINT = "staff_complaint"
STEP_DONE = "done"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def save_no_prixod_count(shift_id: int, count: int) -> bool:
    if count is None or count < 0:
        return False

    shift = cash_shift.get_shift(shift_id)
    if shift is None:
        return False

    repo.set_no_prixod_count(shift_id, shift.get("branch"), shift["shift_date"], count, _now())
    return True


def is_no_prixod_signal(count: int) -> bool:
    return count >= NO_PRIXOD_SIGNAL_THRESHOLD


def save_price_complaint_bucket(shift_id: int, bucket: str) -> bool:
    if bucket not in PRICE_COMPLAINT_BUCKETS:
        return False

    shift = cash_shift.get_shift(shift_id)
    if shift is None:
        return False

    repo.set_price_complaint_bucket(shift_id, shift.get("branch"), shift["shift_date"], bucket, _now())
    return True


def save_staff_complaint_none(shift_id: int) -> bool:
    shift = cash_shift.get_shift(shift_id)
    if shift is None:
        return False

    repo.set_staff_complaint(shift_id, shift.get("branch"), shift["shift_date"], 0, None, None, None, _now())
    return True


def save_staff_complaint(shift_id: int, employee_id: int, complaint_type: str, note: str | None = None) -> bool:
    if complaint_type not in KNOWN_COMPLAINT_TYPES:
        return False
    if complaint_type == COMPLAINT_TYPE_OTHER and not (note or "").strip():
        return False

    shift = cash_shift.get_shift(shift_id)
    if shift is None:
        return False

    clean_note = note.strip() if complaint_type == COMPLAINT_TYPE_OTHER else None
    repo.set_staff_complaint(
        shift_id, shift.get("branch"), shift["shift_date"], 1, employee_id, complaint_type, clean_note, _now()
    )
    return True


def get_next_step(shift_id: int) -> str:
    row = repo.get(shift_id)
    if row is None or row.get("no_prixod_count") is None:
        return STEP_NO_PRIXOD
    if row.get("price_complaint_bucket") is None:
        return STEP_PRICE_COMPLAINT
    if row.get("staff_complaint_occurred") is None:
        return STEP_STAFF_COMPLAINT
    return STEP_DONE


def is_flow_complete(shift_id: int) -> bool:
    return get_next_step(shift_id) == STEP_DONE
