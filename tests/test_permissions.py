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
