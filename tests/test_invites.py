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
