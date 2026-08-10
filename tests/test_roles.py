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
