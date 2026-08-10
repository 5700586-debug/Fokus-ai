"""Fokus AI uchun markazlashgan rol tizimi.

Rol nomlari shu yerda saqlanadi. Ruxsat etilgan foydalanuvchilar (Founder
bundan mustasno — u FOUNDER_ID orqali avtomatik to'liq huquqli) va ularning
rollari `allowed_users.json` faylida saqlanadi.
"""

import json
import os
from datetime import datetime, timezone

from config import FOUNDER_ID

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


def _load_users() -> dict[int, dict]:
    if not os.path.exists(_ALLOWED_USERS_FILE):
        return {}

    with open(_ALLOWED_USERS_FILE, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            return {}

    return {int(user_id): info for user_id, info in data.items()}


def _save_users(users: dict[int, dict]) -> None:
    with open(_ALLOWED_USERS_FILE, "w", encoding="utf-8") as f:
        json.dump({str(k): v for k, v in users.items()}, f, indent=2, ensure_ascii=False)


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

    _USERS[user_id] = {
        "role": role_key,
        "added_by": set_by,
        "added_at": datetime.now(timezone.utc).isoformat(),
    }
    _save_users(_USERS)
    return True


def remove_user(user_id: int) -> bool:
    if user_id not in _USERS:
        return False

    del _USERS[user_id]
    _save_users(_USERS)
    return True


def list_users() -> dict[int, dict]:
    return dict(_USERS)


def role_name(role_key: str | None) -> str:
    if role_key is None:
        return "Noma'lum"
    return ROLES.get(role_key, role_key)
