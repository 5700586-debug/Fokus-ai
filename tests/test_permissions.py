from services import permissions


def test_founder_has_all_permissions(monkeypatch):
    monkeypatch.setattr(permissions, "get_role", lambda user_id: "founder")

    assert permissions.has_permission(1, permissions.ACTION_SCORE_EMPLOYEE)
    assert permissions.has_permission(1, permissions.ACTION_SET_RULE)


def test_role_only_has_its_own_action(monkeypatch):
    monkeypatch.setattr(permissions, "get_role", lambda user_id: "nazoratchi")

    assert permissions.has_permission(1, permissions.ACTION_SCORE_EMPLOYEE) is True
    assert permissions.has_permission(1, permissions.ACTION_LOG_MARKET_OBSERVATION) is False


def test_unknown_user_has_no_permission(monkeypatch):
    monkeypatch.setattr(permissions, "get_role", lambda user_id: None)

    assert permissions.has_permission(1, permissions.ACTION_SCORE_EMPLOYEE) is False


def test_kassir_can_manage_own_shift_but_not_review_it(monkeypatch):
    monkeypatch.setattr(permissions, "get_role", lambda user_id: "kassir")

    assert permissions.has_permission(1, permissions.ACTION_OPEN_CASH_SHIFT) is True
    assert permissions.has_permission(1, permissions.ACTION_CLOSE_CASH_SHIFT) is True
    assert permissions.has_permission(1, permissions.ACTION_LOG_CASH_EXPENSE) is True
    assert permissions.has_permission(1, permissions.ACTION_REVIEW_CASH_SHIFT) is False


def test_nazoratchi_can_review_cash_and_inventory(monkeypatch):
    monkeypatch.setattr(permissions, "get_role", lambda user_id: "nazoratchi")

    assert permissions.has_permission(1, permissions.ACTION_REVIEW_CASH_SHIFT) is True
    assert permissions.has_permission(1, permissions.ACTION_REVIEW_INVENTORY_VARIANCE) is True
    assert permissions.has_permission(1, permissions.ACTION_OPEN_CASH_SHIFT) is False


def test_savdo_boshligi_can_submit_inventory_snapshot(monkeypatch):
    monkeypatch.setattr(permissions, "get_role", lambda user_id: "savdo_boshligi")

    assert permissions.has_permission(1, permissions.ACTION_SUBMIT_INVENTORY_SNAPSHOT) is True
    assert permissions.has_permission(1, permissions.ACTION_LOG_CASH_EXPENSE) is False


def test_moliyachi_can_view_summaries_only(monkeypatch):
    monkeypatch.setattr(permissions, "get_role", lambda user_id: "moliyachi")

    assert permissions.has_permission(1, permissions.ACTION_VIEW_CASH_SUMMARY) is True
    assert permissions.has_permission(1, permissions.ACTION_VIEW_INVENTORY_SUMMARY) is True
    assert permissions.has_permission(1, permissions.ACTION_OPEN_CASH_SHIFT) is False


def test_sotuvchi_has_no_cash_visibility(monkeypatch):
    monkeypatch.setattr(permissions, "get_role", lambda user_id: "sotuvchi")

    assert permissions.has_permission(1, permissions.ACTION_VIEW_CASH_SUMMARY) is False
    assert permissions.has_permission(1, permissions.ACTION_OPEN_CASH_SHIFT) is False
