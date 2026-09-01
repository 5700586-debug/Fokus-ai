"""VAZIFA + NAZORATCHI + BONUS V1 — 3-bosqich: vaqt bonusi tarixi
(``repositories/time_bonus.py``, ``services/time_bonus.py``)."""

from repositories import time_bonus as time_bonus_repo
from services import time_bonus as time_bonus_service


def test_grant_records_source_and_confirmed_by():
    granted = time_bonus_repo.grant(111, "2026-01-01", time_bonus_repo.SOURCE_MANUAL, confirmed_by=999)

    assert granted is True
    row = time_bonus_repo.get_for_date(111, "2026-01-01")
    assert row["source"] == "manual"
    assert row["confirmed_by"] == 999


def test_grant_is_duplicate_safe_for_same_employee_and_date():
    first = time_bonus_repo.grant(111, "2026-01-01", time_bonus_repo.SOURCE_MANUAL, confirmed_by=999)
    second = time_bonus_repo.grant(111, "2026-01-01", time_bonus_repo.SOURCE_MANUAL, confirmed_by=888)

    assert first is True
    assert second is False
    row = time_bonus_repo.get_for_date(111, "2026-01-01")
    assert row["confirmed_by"] == 999  # ikkinchisi birinchisini bosib o'tmadi


def test_manual_grant_does_not_overwrite_existing_auto_grant():
    time_bonus_repo.grant(111, "2026-01-01", time_bonus_repo.SOURCE_AUTO, confirmed_by=None)
    manual_attempt = time_bonus_repo.grant(111, "2026-01-01", time_bonus_repo.SOURCE_MANUAL, confirmed_by=999)

    assert manual_attempt is False
    row = time_bonus_repo.get_for_date(111, "2026-01-01")
    assert row["source"] == "auto"


def test_different_employees_or_dates_do_not_conflict():
    assert time_bonus_repo.grant(111, "2026-01-01", time_bonus_repo.SOURCE_MANUAL, confirmed_by=1) is True
    assert time_bonus_repo.grant(222, "2026-01-01", time_bonus_repo.SOURCE_MANUAL, confirmed_by=1) is True
    assert time_bonus_repo.grant(111, "2026-01-02", time_bonus_repo.SOURCE_MANUAL, confirmed_by=1) is True


def test_service_confirm_manual_uses_todays_date():
    import company_time

    granted = time_bonus_service.confirm_manual(111, confirmed_by=999)
    assert granted is True

    status = time_bonus_service.get_today_status(111)
    assert status["grant_date"] == company_time.today().isoformat()


def test_get_today_status_none_when_not_yet_granted():
    assert time_bonus_service.get_today_status(111) is None
