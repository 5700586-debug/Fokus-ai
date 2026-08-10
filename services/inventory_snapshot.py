"""Kunlik ombor/qoldiq qiymati nazorati — kechagi qiymatga nisbatan
farq, tasdiqlangan sabablar (explained) va tushuntirilmagan qoldiq
(unexplained variance).

MUHIM: mavjud bo'lmagan savdo/prixod integratsiyasi asosida
``expected_closing_inventory`` HOZIR hisoblanmaydi (spec 20-bo'lim) —
faqat snapshot + Savdo bo'limi boshlig'i tomonidan tasdiqlangan sabablar
asosida explained/unexplained ajratiladi.
"""

from dataclasses import dataclass

from repositories import inventory as repo
from services import rules as rules_service

STATUS_NORMAL = "normal"
STATUS_NEEDS_REVIEW = "needs_review"
STATUS_URGENT_REVIEW = "urgent_review"

VARIANCE_CAUSES = [
    "prixod",
    "katta_savdo",
    "hisobdan_chiqarish",
    "qaytarish",
    "narx_correction",
    "kiritish_xatosi",
    "boshqa",
]


@dataclass
class SnapshotOutcome:
    snapshot: dict
    already_existed: bool
    needs_cause_explanation: bool


@dataclass
class VarianceOutcome:
    snapshot: dict
    explained_variance: int
    unexplained_variance: int
    status: str


def _status_for_unexplained(unexplained_variance: int, threshold: int) -> str:
    if unexplained_variance == 0:
        return STATUS_NORMAL
    if abs(unexplained_variance) <= threshold:
        return STATUS_NEEDS_REVIEW
    return STATUS_URGENT_REVIEW


def create_snapshot_for_today(
    branch: str | None, snapshot_date: str, reported_by_employee_id: int,
    total_inventory_value: int, photo_reference: str | None,
) -> SnapshotOutcome:
    existing = repo.get_snapshot_for_date(branch, snapshot_date)
    if existing is not None:
        return SnapshotOutcome(existing, already_existed=True, needs_cause_explanation=False)

    previous = repo.get_previous_snapshot(branch, snapshot_date)
    previous_value = previous["total_inventory_value"] if previous else None
    gross_difference = (
        total_inventory_value - previous_value if previous_value is not None else None
    )
    threshold = rules_service.get_inventory_variance_threshold()

    snapshot = repo.create_snapshot(
        branch, snapshot_date, reported_by_employee_id, total_inventory_value,
        previous_value, gross_difference, threshold, photo_reference,
    )

    if gross_difference is None or gross_difference == 0:
        repo.update_snapshot_variance(snapshot["id"], explained_variance=0, unexplained_variance=0, status=STATUS_NORMAL)
        snapshot = repo.get_snapshot(snapshot["id"])
        return SnapshotOutcome(snapshot, already_existed=False, needs_cause_explanation=False)

    return SnapshotOutcome(snapshot, already_existed=False, needs_cause_explanation=True)


def add_cause_and_recompute(snapshot_id: int, cause: str, amount: int, comment: str | None) -> VarianceOutcome:
    if cause not in VARIANCE_CAUSES:
        raise ValueError(f"Noma'lum sabab: {cause}")

    repo.add_variance_explanation(snapshot_id, cause, amount, comment)

    snapshot = repo.get_snapshot(snapshot_id)
    explanations = repo.get_variance_explanations(snapshot_id)
    explained_variance = sum(row["amount"] for row in explanations)
    gross_difference = snapshot["gross_difference"] or 0
    unexplained_variance = gross_difference - explained_variance

    status = _status_for_unexplained(unexplained_variance, snapshot["threshold"])
    repo.update_snapshot_variance(snapshot_id, explained_variance, unexplained_variance, status)

    return VarianceOutcome(repo.get_snapshot(snapshot_id), explained_variance, unexplained_variance, status)


def get_causes(snapshot_id: int) -> list[dict]:
    return repo.get_variance_explanations(snapshot_id)


def record_supervisor_review(snapshot_id: int, reviewed_by: int, decision: str, comment: str | None) -> None:
    repo.record_variance_review(snapshot_id, reviewed_by, decision, comment)


def get_snapshot(snapshot_id: int) -> dict | None:
    return repo.get_snapshot(snapshot_id)
