import employees


def _submit(user_id: int = 1) -> None:
    employees.submit_profile(
        user_id,
        {
            "familiya": "Familiyev",
            "ism": "Ism",
            "otasining_ismi": "Ota",
            "birth_date": "1995-05-01",
            "age": 30,
            "jinsi": "Erkak",
            "phone": "+998901234567",
            "tuman": "Toshkent",
            "mahalla": "Chilonzor MFY, 12-uy",
            "role_key": "nazoratchi",
            "contacts": [
                {"full_name": "Kontakt Bir", "phone": "+998901111111", "relation": "Aka"},
            ],
            "emergency_contact_index": 0,
        },
    )


def test_get_profile_missing_user_returns_none():
    assert employees.get_profile(999) is None
    assert employees.get_status(999) is None
    assert employees.format_founder_card(999) is None


def test_submit_profile_sets_status_and_contacts():
    _submit(1)

    profile = employees.get_profile(1)
    assert profile["status"] == "submitted"
    assert len(profile["contacts"]) == 1
    assert profile["emergency_contact_id"] == profile["contacts"][0]["id"]
    assert employees.get_status(1) == "submitted"


def test_resubmitting_replaces_contacts():
    _submit(1)
    employees.submit_profile(
        1,
        {
            "familiya": "Familiyev",
            "ism": "Ism",
            "otasining_ismi": "Ota",
            "tuman": "Toshkent",
            "mahalla": "Boshqa",
            "role_key": "nazoratchi",
            "contacts": [
                {"full_name": "Yangi Kontakt", "phone": "+998903333333", "relation": "Ona"},
            ],
            "emergency_contact_index": 0,
        },
    )

    profile = employees.get_profile(1)
    assert len(profile["contacts"]) == 1
    assert profile["contacts"][0]["full_name"] == "Yangi Kontakt"


def test_approve_profile():
    _submit(1)
    approved = employees.approve_profile(1, approved_by=999)

    assert approved is not None
    profile = employees.get_profile(1)
    assert profile["status"] == "approved"
    assert profile["approved_by"] == 999


def test_approve_missing_profile_returns_none():
    assert employees.approve_profile(999, approved_by=1) is None


def test_duplicate_approve_only_succeeds_once():
    """Regressiya: bir xil nomzod ikki marta ketma-ket approve qilinsa
    (masalan ikki marta bosilgan tugma yoki parallel ikkinchi so'rov),
    faqat BIRINCHISI muvaffaqiyatli bo'lishi kerak — ikkinchisi hech
    narsa o'zgartirmasligi (``None`` qaytarishi) kerak, chunki status
    endi ``'submitted'`` emas (atomic ``UPDATE ... WHERE status =
    'submitted'`` tufayli). Chaqiruvchi (``approval.py``) shu ``None``
    natijasiga qarab rolni/kalibratsiyani/xabarni qayta bermaydi.
    """
    _submit(1)

    first = employees.approve_profile(1, approved_by=999)
    second = employees.approve_profile(1, approved_by=888)

    assert first is not None
    assert second is None

    profile = employees.get_profile(1)
    assert profile["status"] == "approved"
    assert profile["approved_by"] == 999  # ikkinchisi qayta yozmadi


def test_reject_profile():
    _submit(1)
    employees.reject_profile(1, rejected_by=999)

    profile = employees.get_profile(1)
    assert profile["status"] == "rejected"
    assert profile["rejected_by"] == 999


def test_format_founder_card_contains_key_fields():
    _submit(1)
    card = employees.format_founder_card(1)

    assert "Familiyev Ism Ota" in card
    assert "Toshkent, Chilonzor MFY, 12-uy" in card
    assert "Nazoratchi" in card
    assert "Kontakt Bir" in card
