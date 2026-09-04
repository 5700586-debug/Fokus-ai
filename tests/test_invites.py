from datetime import datetime, timedelta, timezone

import invites
from db import get_connection


def test_create_and_claim_invite():
    token = invites.create_invite("nazoratchi", branch=None, created_by=1)

    claimed = invites.claim_invite(token, user_id=555)
    assert claimed is not None
    assert claimed["role_key"] == "nazoratchi"
    assert claimed["status"] == "claimed"
    assert claimed["claimed_by"] == 555


def test_claim_unknown_token_returns_none():
    assert invites.claim_invite("does-not-exist", user_id=1) is None


def test_claim_already_claimed_token_returns_none():
    token = invites.create_invite("nazoratchi", branch=None, created_by=1)
    invites.claim_invite(token, user_id=555)

    assert invites.claim_invite(token, user_id=999) is None


def test_same_user_can_reopen_claimed_invite_until_completed():
    token = invites.create_invite("kassir", branch="SATURN Derizlik", created_by=1)
    invites.claim_invite(token, user_id=555)

    reopened = invites.claim_invite(token, user_id=555)
    assert reopened is not None
    assert reopened["status"] == "claimed"
    assert reopened["claimed_by"] == 555

    invites.mark_completed(token)
    assert invites.claim_invite(token, user_id=555) is None


def test_expired_invite_cannot_be_claimed():
    token = invites.create_invite("nazoratchi", branch=None, created_by=1)

    conn = get_connection()
    try:
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        conn.execute("UPDATE invites SET expires_at = ? WHERE token = ?", (past, token))
        conn.commit()
    finally:
        conn.close()

    assert invites.claim_invite(token, user_id=555) is None


def test_has_pending_invite_for_role():
    assert invites.has_pending_invite_for_role("nazoratchi") is False

    token = invites.create_invite("nazoratchi", branch=None, created_by=1)
    assert invites.has_pending_invite_for_role("nazoratchi") is True

    invites.claim_invite(token, user_id=555)
    assert invites.has_pending_invite_for_role("nazoratchi") is True

    invites.mark_completed(token)
    assert invites.has_pending_invite_for_role("nazoratchi") is False


def test_branch_role_invite_stores_branch():
    token = invites.create_invite("sotuvchi", branch="Chilonzor filiali", created_by=1)
    claimed = invites.claim_invite(token, user_id=1)

    assert claimed["branch"] == "Chilonzor filiali"


def test_expired_pending_invite_yields_fresh_token():
    old_token = invites.create_invite("taminotchi", branch=None, created_by=1)

    conn = get_connection()
    try:
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        conn.execute("UPDATE invites SET expires_at = ? WHERE token = ?", (past, old_token))
        conn.commit()
    finally:
        conn.close()

    pending = invites.get_pending_invite_for_role("taminotchi")
    assert pending is None

    new_token = invites.create_invite("taminotchi", branch=None, created_by=1)
    assert new_token != old_token

    conn = get_connection()
    try:
        row = conn.execute("SELECT status FROM invites WHERE token = ?", (old_token,)).fetchone()
    finally:
        conn.close()
    assert row["status"] == "expired"


def test_unexpired_active_pending_returns_same_token_no_duplicate():
    token = invites.create_invite("taminotchi", branch=None, created_by=1)

    pending = invites.get_pending_invite_for_role("taminotchi")
    assert pending is not None
    assert pending["token"] == token
    assert pending["status"] == "active"


def test_unexpired_claimed_pending_returns_same_token_only_original_user():
    token = invites.create_invite("taminotchi", branch=None, created_by=1)
    invites.claim_invite(token, user_id=555)

    pending = invites.get_pending_invite_for_role("taminotchi")
    assert pending is not None
    assert pending["token"] == token
    assert pending["status"] == "claimed"
    assert pending["claimed_by"] == 555

    resumed = invites.claim_invite(token, user_id=555)
    assert resumed is not None
    assert resumed["claimed_by"] == 555

    blocked = invites.claim_invite(token, user_id=999)
    assert blocked is None
