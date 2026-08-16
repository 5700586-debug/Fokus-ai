"""Saturn guruhidagi post tarixi — AI xilma-xillik konteksti va
tip-bank navbat uchun xom SQL."""

from datetime import datetime, timezone

from db import get_connection


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_post(post_type: str, post_date: str, content: str, tip_key: str | None = None) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO saturn_posts_log (post_type, post_date, content, tip_key, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (post_type, post_date, content, tip_key, _now()),
        )
        conn.commit()
    finally:
        conn.close()


def get_recent_posts(post_type: str, limit: int = 7) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM saturn_posts_log WHERE post_type = ? "
            "ORDER BY id DESC LIMIT ?",
            (post_type, limit),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_recent_tip_keys(limit: int = 7) -> list[str]:
    return get_recent_content_keys("tip", limit=limit)


def get_recent_content_keys(post_type: str, limit: int = 30) -> list[str]:
    """``get_recent_tip_keys``ning umumlashtirilgan varianti — istalgan
    ``post_type`` uchun (masalan tonggi/tungi rasmli xabar maslahati)
    oxirgi ``limit`` ta postning ``tip_key`` ustunidagi qiymatini
    qaytaradi. ``tip_key`` ustuni nomi tarixiy sababli ("tip"dan qolgan),
    lekin har qanday post turi uchun umumiy "kontent kaliti" sifatida
    ishlatiladi — yangi ustun/jadval shart emas.
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT tip_key FROM saturn_posts_log WHERE post_type = ? "
            "AND tip_key IS NOT NULL ORDER BY id DESC LIMIT ?",
            (post_type, limit),
        ).fetchall()
        return [row["tip_key"] for row in rows]
    finally:
        conn.close()
