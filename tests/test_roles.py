import json
import os

import pytest

import roles
from config import FOUNDER_ID


def test_founder_role_is_implicit():
    assert roles.get_role(FOUNDER_ID) == "founder"
    assert roles.is_authorized(FOUNDER_ID) is True


def test_unknown_user_has_no_role():
    assert roles.get_role(123) is None
    assert roles.is_authorized(123) is False


def test_set_role_and_get_role():
    assert roles.set_role(123, "nazoratchi", set_by=FOUNDER_ID) is True
    assert roles.get_role(123) == "nazoratchi"


def test_set_role_rejects_invalid_role_key():
    assert roles.set_role(123, "not_a_role", set_by=FOUNDER_ID) is False
    assert roles.set_role(123, "founder", set_by=FOUNDER_ID) is False


def test_single_slot_role_enforced():
    assert roles.set_role(1, "nazoratchi", set_by=FOUNDER_ID) is True
    assert roles.set_role(2, "nazoratchi", set_by=FOUNDER_ID) is False
    assert roles.find_user_by_role("nazoratchi") == 1


def test_single_slot_role_allows_reassigning_same_user():
    roles.set_role(1, "nazoratchi", set_by=FOUNDER_ID)
    assert roles.set_role(1, "nazoratchi", set_by=FOUNDER_ID) is True


def test_non_single_slot_role_allows_multiple_users():
    assert roles.set_role(1, "sotuvchi", set_by=FOUNDER_ID) is True
    assert roles.set_role(2, "sotuvchi", set_by=FOUNDER_ID) is True


def test_remove_user():
    roles.set_role(123, "nazoratchi", set_by=FOUNDER_ID)
    assert roles.remove_user(123) is True
    assert roles.get_role(123) is None
    assert roles.remove_user(123) is False


def test_list_users():
    roles.set_role(1, "nazoratchi", set_by=FOUNDER_ID)
    roles.set_role(2, "haydovchi", set_by=FOUNDER_ID)

    users = roles.list_users()
    assert set(users.keys()) == {1, 2}
    assert users[1]["role"] == "nazoratchi"


@pytest.mark.skipif(bool(os.getenv("DATABASE_URL")), reason="DATABASE_URL rejimida allowed_users jadvali ishlatiladi")
def test_role_persisted_to_file():
    roles.set_role(123, "nazoratchi", set_by=FOUNDER_ID)

    with open(roles._ALLOWED_USERS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["123"]["role"] == "nazoratchi"


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="faqat DATABASE_URL rejimida tekshiriladi")
def test_role_persisted_to_db_and_reloadable():
    """Talab: Render kabi disksiz muhitda ham rol ma'lumoti restart'dan
    omon qolishi kerak — buni ``roles._load_users()``ni qayta chaqirib
    tekshiramiz (jarayon qayta ishga tushganda ``_USERS`` xuddi shu
    funksiyadan qayta to'ldiriladi).
    """
    roles.set_role(123, "nazoratchi", set_by=FOUNDER_ID)

    reloaded = roles._load_users()

    assert reloaded[123]["role"] == "nazoratchi"


def test_role_name_lookup():
    assert roles.role_name("nazoratchi") == "Nazoratchi"
    assert roles.role_name(None) == "Noma'lum"
    assert roles.role_name("unknown_key") == "unknown_key"


# --------------------------------------- nazoratchi=1 race-condition himoyasi --
# ``schema/core.py``dagi qisman UNIQUE indeks (Postgres/production) DB
# darajasida, atomik ravishda single-slot rol duplikatini rad etadi —
# bu yerda ``set_role()``ning shu holatni (``IntegrityError``) to'g'ri
# ushlab, xotiradagi ``_USERS`` keshini buzmasdan ``False`` qaytarishini
# tekshiramiz (haqiqiy Postgres'siz ham, DB xatosini simulyatsiya qilib).


def test_set_role_handles_db_level_race_condition_gracefully(monkeypatch):
    """Ikki jarayon (masalan deploy paytida eski+yangi instance) deyarli
    bir vaqtda ``nazoratchi``ni band qilishga urinsa, ikkinchisi Python
    tekshiruvidan o'tib ketishi mumkin (hali yozmagan bo'lsa) — lekin DB
    yozuvi (``_persist_set_role``) ``IntegrityError`` bilan rad etiladi.
    """
    from db import IntegrityError

    def _boom(user_id, info):
        raise IntegrityError("duplicate key value violates unique constraint")

    monkeypatch.setattr(roles, "_persist_set_role", _boom)

    assert roles.set_role(1, "nazoratchi", set_by=FOUNDER_ID) is False
    assert roles.get_role(1) is None
    assert roles.find_user_by_role("nazoratchi") is None


def test_set_role_race_rejection_does_not_corrupt_cache(monkeypatch):
    roles.set_role(1, "nazoratchi", set_by=FOUNDER_ID)

    from db import IntegrityError

    def _boom(user_id, info):
        raise IntegrityError("duplicate key")

    monkeypatch.setattr(roles, "_persist_set_role", _boom)

    # 1-chi allaqachon nazoratchi — Python darajasidagi tekshiruv buni
    # "o'zini qayta tayinlash" deb topib DB yozuviga o'tkazadi, u yerda
    # (simulyatsiya qilingan) race bilan rad etiladi.
    assert roles.set_role(1, "nazoratchi", set_by=FOUNDER_ID) is False
    assert roles.get_role(1) == "nazoratchi"


# -------------------------------------------------------------------- audit --


def test_role_assignment_is_audited():
    from repositories import audit as audit_repo
    from services import audit

    roles.set_role(123, "nazoratchi", set_by=FOUNDER_ID)

    events = audit_repo.list_events_for_actor(FOUNDER_ID)
    assigned = [e for e in events if e["event_type"] == audit.EVENT_ROLE_ASSIGNED]
    assert len(assigned) == 1
    assert assigned[0]["target_id"] == 123
    assert assigned[0]["new_value"] == "nazoratchi"
    assert assigned[0]["actor_role"] == "founder"


def test_blocked_nazoratchi_assignment_is_audited():
    from repositories import audit as audit_repo
    from services import audit

    roles.set_role(1, "nazoratchi", set_by=FOUNDER_ID)
    roles.set_role(2, "nazoratchi", set_by=FOUNDER_ID)

    events = audit_repo.list_events_for_actor(FOUNDER_ID)
    blocked = [e for e in events if e["event_type"] == audit.EVENT_NAZORATCHI_ASSIGN_BLOCKED]
    assert len(blocked) == 1
    assert blocked[0]["target_id"] == 2


def test_user_removal_is_audited():
    from repositories import audit as audit_repo
    from services import audit

    roles.set_role(123, "sotuvchi", set_by=FOUNDER_ID)
    roles.remove_user(123, removed_by=FOUNDER_ID)

    events = audit_repo.list_events_for_actor(FOUNDER_ID)
    removed = [e for e in events if e["event_type"] == audit.EVENT_USER_REMOVED]
    assert len(removed) == 1
    assert removed[0]["target_id"] == 123
    assert removed[0]["old_value"] == "sotuvchi"
