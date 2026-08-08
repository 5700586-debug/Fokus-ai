"""Bir martalik onboarding invite tokenlari.

Har bir taklif havolasi Founder tomonidan oldindan belgilangan rol va
filial bilan yaratiladi, cheklangan muddat amal qiladi va faqat bir marta
ishlatilishi mumkin.
"""

import secrets
from datetime import datetime, timedelta, timezone

from db import get_connection

INVITE_TTL_HOURS = 2


def create_invite(
    role_key: str,
    branch: str | None,
    created_by: int,
    work_schedule: str | None = None,
) -> str:
    token = secrets.token_urlsafe(16)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=INVITE_TTL_HOURS)

    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO invites "
            "(token, role_key, branch, work_schedule, created_by, created_at, expires_at, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'active')",
            (
                token,
                role_key,
                branch,
                work_schedule,
                created_by,
                now.isoformat(),
                expires_at.isoformat(),
            ),
        )
        conn.commit()
    finally:
        conn.close()

    return token


def claim_invite(token: str, user_id: int) -> dict | None:
    """Faol va muddati o'tmagan tokenni bir martalik band qiladi.

    Muvaffaqiyatli bo'lsa taklif ma'lumotlarini, aks holda ``None``
    qaytaradi (token mavjud emas, allaqachon ishlatilgan yoki muddati
    o'tgan).
    """
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM invites WHERE token = ?", (token,)).fetchone()
        if row is None:
            return None

        invite = dict(row)
        if invite["status"] != "active":
            return None

        expires_at = datetime.fromisoformat(invite["expires_at"])
        if datetime.now(timezone.utc) > expires_at:
            conn.execute("UPDATE invites SET status = 'expired' WHERE token = ?", (token,))
            conn.commit()
            return None

        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE invites SET status = 'claimed', claimed_by = ?, claimed_at = ? "
            "WHERE token = ?",
            (user_id, now, token),
        )
        conn.commit()

        invite["status"] = "claimed"
        invite["claimed_by"] = user_id
        invite["claimed_at"] = now
        return invite
    finally:
        conn.close()


def mark_completed(token: str) -> None:
    conn = get_connection()
    try:
        conn.execute("UPDATE invites SET status = 'completed' WHERE token = ?", (token,))
        conn.commit()
    finally:
        conn.close()


def has_pending_invite_for_role(role_key: str) -> bool:
    """Shu rol uchun hali yakunlanmagan (active yoki claimed) taklif bormi."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT 1 FROM invites WHERE role_key = ? AND status IN ('active', 'claimed') LIMIT 1",
            (role_key,),
        ).fetchone()
    finally:
        conn.close()

    return row is not None
