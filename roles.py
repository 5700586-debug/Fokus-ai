"""Fokus AI uchun markazlashgan rol tizimi.

Rol nomlari shu yerda saqlanadi. Ruxsat etilgan foydalanuvchilar (Founder
bundan mustasno — u FOUNDER_ID orqali avtomatik to'liq huquqli) va ularning
rollari saqlanadi:

- ``DATABASE_URL`` o'rnatilmagan bo'lsa (standart): ``allowed_users.json``
  faylida.
- ``DATABASE_URL`` o'rnatilgan bo'lsa (masalan Supabase): ``allowed_users``
  jadvalida (qarang: ``schema/core.py``) — Render kabi platformalarda
  disk deploy/restart'da reset bo'lishi mumkin, lekin tashqi baza
  bo'lmaydi.
"""

import json
import os
from datetime import datetime, timezone

from config import FOUNDER_ID

_DATABASE_URL = os.getenv("DATABASE_URL")

# Rol kaliti -> ko'rinadigan nom. Keyinchalik har bir rolga alohida
# permission biriktirish shu lug'atga tayanadi (masalan ROLE_PERMISSIONS).
ROLES = {
    "founder": "Founder",
    "moliyachi": "Moliyachi",
    "kassir": "Kassir",
    "savdo_boshligi": "Savdo bo'limi boshlig'i",
    "addel_boshligi": "Addel boshlig'i",
    "sotuvchi": "Sotuvchi",
    "taminotchi": "Ta'minotchi",
    "tozalik": "Tozalik xodimasi",
    "shogird": "Shogird",
    "nazoratchi": "Nazoratchi",
    "haydovchi": "Haydovchi",
}

# Bu rollar filialga biriktirilmaydi — barcha filiallar uchun umumiy va
# har birida faqat bitta xodim bo'lishi mumkin.
SINGLE_SLOT_ROLES = {"nazoratchi", "haydovchi", "taminotchi", "moliyachi"}

_ALLOWED_USERS_FILE = os.path.join(
    os.getenv("FOKUS_DATA_DIR") or os.path.dirname(os.path.abspath(__file__)),
    "allowed_users.json",
)


def _load_users_from_db() -> dict[int, dict]:
    from db import get_connection

    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT user_id, role_key, added_by, added_at FROM allowed_users"
        ).fetchall()
    finally:
        conn.close()

    return {
        row["user_id"]: {
            "role": row["role_key"],
            "added_by": row["added_by"],
            "added_at": row["added_at"],
        }
        for row in rows
    }


def _load_users_from_file() -> dict[int, dict]:
    if not os.path.exists(_ALLOWED_USERS_FILE):
        return {}

    with open(_ALLOWED_USERS_FILE, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            return {}

    return {int(user_id): info for user_id, info in data.items()}


def _load_users() -> dict[int, dict]:
    return _load_users_from_db() if _DATABASE_URL else _load_users_from_file()


def _save_users(users: dict[int, dict]) -> None:
    with open(_ALLOWED_USERS_FILE, "w", encoding="utf-8") as f:
        json.dump({str(k): v for k, v in users.items()}, f, indent=2, ensure_ascii=False)


def _persist_set_role(user_id: int, info: dict) -> None:
    if not _DATABASE_URL:
        _save_users(_USERS)
        return

    from db import get_connection

    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO allowed_users (user_id, role_key, added_by, added_at) "
            "VALUES (?, ?, ?, ?) ON CONFLICT(user_id) DO UPDATE SET "
            "role_key = excluded.role_key, added_by = excluded.added_by, "
            "added_at = excluded.added_at",
            (user_id, info["role"], info["added_by"], info["added_at"]),
        )
        conn.commit()
    finally:
        conn.close()


def _persist_remove_user(user_id: int) -> None:
    if not _DATABASE_URL:
        _save_users(_USERS)
        return

    from db import get_connection

    conn = get_connection()
    try:
        conn.execute("DELETE FROM allowed_users WHERE user_id = ?", (user_id,))
        conn.commit()
    finally:
        conn.close()


_USERS: dict[int, dict] = _load_users()


def get_role(user_id: int) -> str | None:
    if user_id == FOUNDER_ID:
        return "founder"

    info = _USERS.get(user_id)
    return info["role"] if info else None


def is_authorized(user_id: int) -> bool:
    return get_role(user_id) is not None


def is_single_slot_role(role_key: str) -> bool:
    return role_key in SINGLE_SLOT_ROLES


def find_user_by_role(role_key: str) -> int | None:
    for user_id, info in _USERS.items():
        if info["role"] == role_key:
            return user_id
    return None


def set_role(user_id: int, role_key: str, set_by: int) -> bool:
    if role_key not in ROLES or role_key == "founder":
        return False

    if role_key in SINGLE_SLOT_ROLES:
        existing = find_user_by_role(role_key)
        if existing is not None and existing != user_id:
            return False

    info = {
        "role": role_key,
        "added_by": set_by,
        "added_at": datetime.now(timezone.utc).isoformat(),
    }
    _USERS[user_id] = info
    _persist_set_role(user_id, info)
    return True


def remove_user(user_id: int) -> bool:
    if user_id not in _USERS:
        return False

    del _USERS[user_id]
    _persist_remove_user(user_id)
    return True


def list_users() -> dict[int, dict]:
    return dict(_USERS)


def role_name(role_key: str | None) -> str:
    if role_key is None:
        return "Noma'lum"
    return ROLES.get(role_key, role_key)
