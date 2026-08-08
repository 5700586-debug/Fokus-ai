"""Xodimlarning onboarding profili va favqulodda aloqa kontaktlari.

Bu yerda shaxsiy ma'lumotlar (telefon raqamlar) saqlanadi, shuning uchun
employees.json git repozitoriyaga kirmaydi (.gitignore).
"""

import json
import os

_EMPLOYEES_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "employees.json"
)


def _load() -> dict[int, dict]:
    if not os.path.exists(_EMPLOYEES_FILE):
        return {}

    with open(_EMPLOYEES_FILE, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            return {}

    return {int(user_id): info for user_id, info in data.items()}


def _save(employees: dict[int, dict]) -> None:
    with open(_EMPLOYEES_FILE, "w", encoding="utf-8") as f:
        json.dump(
            {str(k): v for k, v in employees.items()}, f, indent=2, ensure_ascii=False
        )


_EMPLOYEES: dict[int, dict] = _load()


def has_completed_onboarding(user_id: int) -> bool:
    return user_id in _EMPLOYEES


def get_profile(user_id: int) -> dict | None:
    return _EMPLOYEES.get(user_id)


def save_profile(user_id: int, profile: dict) -> None:
    _EMPLOYEES[user_id] = profile
    _save(_EMPLOYEES)


def format_card(user_id: int) -> str | None:
    profile = _EMPLOYEES.get(user_id)
    if profile is None:
        return None

    age = profile.get("age")
    minor_note = " (voyaga yetmagan)" if profile.get("is_minor") else ""
    lines = [
        f"🎂 Tug‘ilgan sana: {profile.get('birth_date', '-')} — {age} yosh{minor_note}",
        "",
        "📇 Aloqa raqamlari:",
    ]

    for i, contact in enumerate(profile.get("contacts", []), start=1):
        full_name = f"{contact.get('ism', '-')} {contact.get('familiya', '')}".strip()
        lines.append(
            f"{i}. {contact.get('aloqasi', '-')} — {full_name} — {contact.get('telefon', '-')}"
        )

    return "\n".join(lines)
