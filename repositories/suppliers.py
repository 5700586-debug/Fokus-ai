"""Tashqi ta'minotchi kompaniyalar — taklif, profil, suhbat tarixi va
takliflar (mahsulot/narx/shart) uchun xom SQL."""

import secrets
from datetime import datetime, timedelta, timezone

from db import get_connection

INVITE_TTL_HOURS = 48


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ------------------------------------------------------------- invites --


def create_invite(company_name_hint: str | None, created_by: int) -> str:
    token = secrets.token_urlsafe(16)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=INVITE_TTL_HOURS)

    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO supplier_invites "
            "(token, company_name_hint, created_by, created_at, expires_at, status) "
            "VALUES (?, ?, ?, ?, ?, 'active')",
            (token, company_name_hint, created_by, now.isoformat(), expires_at.isoformat()),
        )
        conn.commit()
    finally:
        conn.close()

    return token


def claim_invite(token: str, telegram_user_id: int) -> dict | None:
    """Taklifni bir martalik band qiladi va ``suppliers`` qatorini
    yaratadi. Token topilmasa, allaqachon ishlatilgan yoki muddati
    o'tgan bo'lsa ``None`` qaytaradi — chaqiruvchi (``main.py``) shu
    holatda oddiy xodim taklifi ekanini tekshirishga o'tishi mumkin.
    """
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM supplier_invites WHERE token = ?", (token,)).fetchone()
        if row is None:
            return None

        invite = dict(row)
        if invite["status"] != "active":
            return None

        expires_at = datetime.fromisoformat(invite["expires_at"])
        if datetime.now(timezone.utc) > expires_at:
            conn.execute("UPDATE supplier_invites SET status = 'expired' WHERE token = ?", (token,))
            conn.commit()
            return None

        now = _now()
        conn.execute(
            "UPDATE supplier_invites SET status = 'claimed', claimed_by = ?, claimed_at = ? "
            "WHERE token = ?",
            (telegram_user_id, now, token),
        )

        cursor = conn.execute(
            "INSERT INTO suppliers "
            "(telegram_user_id, company_name, status, invited_by, invite_token, created_at, updated_at) "
            "VALUES (?, ?, 'active', ?, ?, ?, ?)",
            (
                telegram_user_id,
                invite["company_name_hint"],
                invite["created_by"],
                token,
                now,
                now,
            ),
        )
        conn.commit()

        return get_supplier(cursor.lastrowid, conn=conn)
    finally:
        conn.close()


# ------------------------------------------------------------ suppliers --


def get_supplier(supplier_id: int, conn=None) -> dict | None:
    owns_conn = conn is None
    conn = conn or get_connection()
    try:
        row = conn.execute("SELECT * FROM suppliers WHERE id = ?", (supplier_id,)).fetchone()
        return dict(row) if row else None
    finally:
        if owns_conn:
            conn.close()


def get_supplier_by_telegram_id(telegram_user_id: int) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM suppliers WHERE telegram_user_id = ?", (telegram_user_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_suppliers(status: str = "active") -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM suppliers WHERE status = ? ORDER BY id", (status,)
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def update_supplier_profile(supplier_id: int, **fields) -> None:
    if not fields:
        return

    allowed = {"company_name", "region", "contact_name", "phone", "delivery_notes"}
    updates = {key: value for key, value in fields.items() if key in allowed and value is not None}
    if not updates:
        return

    set_clause = ", ".join(f"{key} = ?" for key in updates)
    params = list(updates.values()) + [_now(), supplier_id]

    conn = get_connection()
    try:
        conn.execute(
            f"UPDATE suppliers SET {set_clause}, updated_at = ? WHERE id = ?", params
        )
        conn.commit()
    finally:
        conn.close()


# ------------------------------------------------------------- messages --


def add_message(supplier_id: int, role: str, content: str) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO supplier_messages (supplier_id, role, content, created_at) "
            "VALUES (?, ?, ?, ?)",
            (supplier_id, role, content, _now()),
        )
        conn.commit()
    finally:
        conn.close()


def get_recent_messages(supplier_id: int, limit: int = 20) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM supplier_messages WHERE supplier_id = ? "
            "ORDER BY id DESC LIMIT ?",
            (supplier_id, limit),
        ).fetchall()
        return [dict(row) for row in reversed(rows)]
    finally:
        conn.close()


# --------------------------------------------------------------- offers --


def upsert_offer(supplier_id: int, product_name: str, **fields) -> None:
    allowed = {
        "price",
        "discount",
        "minimum_order",
        "delivery_time",
        "payment_type",
        "return_terms",
        "notes",
    }
    updates = {key: value for key, value in fields.items() if key in allowed and value is not None}
    now = _now()

    conn = get_connection()
    try:
        columns = ["supplier_id", "product_name", "created_at", "updated_at"] + list(updates)
        placeholders = ", ".join(["?"] * len(columns))
        values = [supplier_id, product_name, now, now] + list(updates.values())

        set_clause = ", ".join(f"{key} = excluded.{key}" for key in updates)
        set_clause = (set_clause + ", " if set_clause else "") + "updated_at = excluded.updated_at"

        conn.execute(
            f"INSERT INTO supplier_offers ({', '.join(columns)}) VALUES ({placeholders}) "
            f"ON CONFLICT(supplier_id, product_name) DO UPDATE SET {set_clause}",
            values,
        )
        conn.commit()
    finally:
        conn.close()


def list_offers(supplier_id: int) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM supplier_offers WHERE supplier_id = ? ORDER BY product_name",
            (supplier_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def list_offers_for_product(product_name: str) -> list[dict]:
    """Founder-only: shu mahsulot bo'yicha BARCHA ta'minotchilarning
    takliflari, kompaniya nomi bilan birga (taqqoslash uchun).
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT supplier_offers.*, suppliers.company_name AS supplier_company_name "
            "FROM supplier_offers JOIN suppliers ON suppliers.id = supplier_offers.supplier_id "
            "WHERE supplier_offers.product_name = ? AND suppliers.status = 'active' "
            "ORDER BY supplier_offers.updated_at DESC",
            (product_name,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


# ------------------------------------------------------------ summaries --


def add_founder_summary(supplier_id: int, summary_text: str) -> int:
    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO supplier_founder_summaries (supplier_id, summary_text, created_at) "
            "VALUES (?, ?, ?)",
            (supplier_id, summary_text, _now()),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_latest_founder_summary(supplier_id: int) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM supplier_founder_summaries WHERE supplier_id = ? "
            "ORDER BY id DESC LIMIT 1",
            (supplier_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()
