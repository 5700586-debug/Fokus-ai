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

from config import ENVIRONMENT, FOUNDER_ID
# ``db``dagi ENVIRONMENT-asosidagi qarordan (DATABASE_URL vs
# TEST_DATABASE_URL) foydalaniladi — bu yerda mustaqil qayta hisoblanmaydi,
# aks holda ikkisi turli natijaga kelib qolishi mumkin edi.
from db import _DATABASE_URL, IntegrityError

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
    "allowed_users_test.json" if ENVIRONMENT == "test" else "allowed_users.json",
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
    """``_USERS``ni o'zi mutatsiya qilmaydi — chaqiruvchi (``set_role()``)
    faqat shu funksiya muvaffaqiyatli tugagandan keyingina xotiradagi
    keshni yangilaydi, aks holda DB/fayl yozuvi rad etilganda (masalan
    single-slot rol uchun ``IntegrityError``) kesh haqiqiy holatdan
    uzilib qolishi mumkin edi.
    """
    if not _DATABASE_URL:
        merged = dict(_USERS)
        merged[user_id] = info
        _save_users(merged)
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


def _log_role_event(
    event_type: str,
    actor_id: int | None,
    target_id: int | None,
    old_value: str | None = None,
    new_value: str | None = None,
    reason: str | None = None,
) -> None:
    from services import audit

    audit.log_event(
        event_type,
        actor_id=actor_id,
        actor_role=get_role(actor_id) if actor_id is not None else None,
        target_id=target_id,
        old_value=old_value,
        new_value=new_value,
        reason=reason,
    )


def set_role(user_id: int, role_key: str, set_by: int) -> bool:
    if role_key not in ROLES or role_key == "founder":
        return False

    from services import audit

    if role_key in SINGLE_SLOT_ROLES:
        existing = find_user_by_role(role_key)
        if existing is not None and existing != user_id:
            _log_role_event(
                audit.EVENT_NAZORATCHI_ASSIGN_BLOCKED
                if role_key == "nazoratchi"
                else audit.EVENT_ROLE_ASSIGN_DENIED,
                actor_id=set_by,
                target_id=user_id,
                new_value=role_key,
                reason=f"{role_key} lavozimida allaqachon xodim bor (user_id={existing})",
            )
            return False

    old_role = _USERS.get(user_id, {}).get("role")
    info = {
        "role": role_key,
        "added_by": set_by,
        "added_at": datetime.now(timezone.utc).isoformat(),
    }

    # ``_USERS`` faqat yozuv (DB/fayl) muvaffaqiyatli tugagandan keyin
    # yangilanadi — aks holda quyidagi ``IntegrityError`` xotiradagi
    # keshni haqiqiy DB holatidan uzib qo'ygan bo'lardi.
    try:
        _persist_set_role(user_id, info)
    except IntegrityError:
        # Race condition: boshqa jarayon (masalan deploy paytida eski+yangi
        # instance bir vaqtda ishlab qolgan bo'lsa) ayni shu single-slot
        # rolni deyarli bir vaqtda tekshirib, ulgurib band qilgan —
        # ``schema/core.py``dagi qisman UNIQUE indeks DB darajasida,
        # atomik ravishda rad etdi (yuqoridagi Python tekshiruvi buni
        # ko'ra olmaydi, chunki ikkala jarayon ham tekshiruv payti
        # rolni "bo'sh" deb ko'rgan bo'lishi mumkin).
        _log_role_event(
            audit.EVENT_NAZORATCHI_ASSIGN_BLOCKED
            if role_key == "nazoratchi"
            else audit.EVENT_ROLE_ASSIGN_DENIED,
            actor_id=set_by,
            target_id=user_id,
            new_value=role_key,
            reason="DB darajasida rad etildi (race condition)",
        )
        return False

    _USERS[user_id] = info
    _log_role_event(
        audit.EVENT_ROLE_ASSIGNED,
        actor_id=set_by,
        target_id=user_id,
        old_value=old_role,
        new_value=role_key,
    )
    return True


def remove_user(user_id: int, removed_by: int | None = None) -> bool:
    if user_id not in _USERS:
        return False

    from services import audit

    old_role = _USERS[user_id].get("role")
    del _USERS[user_id]
    _persist_remove_user(user_id)
    _log_role_event(
        audit.EVENT_USER_REMOVED, actor_id=removed_by, target_id=user_id, old_value=old_role
    )
    return True


def list_users() -> dict[int, dict]:
    return dict(_USERS)


def role_name(role_key: str | None) -> str:
    if role_key is None:
        return "Noma'lum"
    return ROLES.get(role_key, role_key)
