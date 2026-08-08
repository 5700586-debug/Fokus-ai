"""Xodim onboarding profili — SQLite orqali saqlanadi (fokus.db).

Onboarding bosqichlaridagi javoblar FSM storage (storage.py) orqali
saqlanadi, bot qayta ishga tushsa ham yo'qolmaydi. employees va
employee_contacts jadvallariga faqat xodim anketani "✅ Ma'lumotlar
to'g'ri" bilan yakunlagandan keyin yoziladi.
"""

from datetime import datetime, timezone

from db import get_connection
from roles import role_name

_EMPLOYEE_FIELDS = [
    "invite_token",
    "telegram_username",
    "familiya",
    "ism",
    "otasining_ismi",
    "birth_date",
    "age",
    "jinsi",
    "phone",
    "marital_status",
    "viloyat",
    "tuman",
    "mahalla",
    "kocha",
    "uy_raqami",
    "xonadon_raqami",
    "branch",
    "role_key",
    "hire_date",
    "work_schedule",
    "planned_duration",
    "motivation",
    "prior_experience",
    "photo_file_id",
    "extra_note",
]


def get_status(user_id: int) -> str | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT status FROM employees WHERE user_id = ?", (user_id,)
        ).fetchone()
    finally:
        conn.close()

    return row["status"] if row else None


def submit_profile(user_id: int, data: dict) -> None:
    now = datetime.now(timezone.utc).isoformat()
    values = {field: data.get(field) for field in _EMPLOYEE_FIELDS}
    columns = ["user_id", *values.keys(), "status", "submitted_at"]
    placeholders = ", ".join("?" for _ in columns)
    update_clause = ", ".join(f"{col} = excluded.{col}" for col in columns if col != "user_id")

    conn = get_connection()
    try:
        conn.execute(
            f"INSERT INTO employees ({', '.join(columns)}) VALUES ({placeholders}) "
            f"ON CONFLICT(user_id) DO UPDATE SET {update_clause}",
            (user_id, *values.values(), "submitted", now),
        )

        conn.execute("DELETE FROM employee_contacts WHERE user_id = ?", (user_id,))

        contact_ids = []
        for contact in data.get("contacts", []):
            cursor = conn.execute(
                "INSERT INTO employee_contacts (user_id, full_name, phone, relation) "
                "VALUES (?, ?, ?, ?)",
                (user_id, contact["full_name"], contact["phone"], contact["relation"]),
            )
            contact_ids.append(cursor.lastrowid)

        emergency_index = data.get("emergency_contact_index")
        if emergency_index is not None and 0 <= emergency_index < len(contact_ids):
            conn.execute(
                "UPDATE employees SET emergency_contact_id = ? WHERE user_id = ?",
                (contact_ids[emergency_index], user_id),
            )

        conn.commit()
    finally:
        conn.close()


def get_profile(user_id: int) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM employees WHERE user_id = ?", (user_id,)).fetchone()
        if row is None:
            return None

        profile = dict(row)
        contacts = conn.execute(
            "SELECT * FROM employee_contacts WHERE user_id = ?", (user_id,)
        ).fetchall()
        profile["contacts"] = [dict(c) for c in contacts]
        return profile
    finally:
        conn.close()


def approve_profile(user_id: int, approved_by: int) -> dict | None:
    profile = get_profile(user_id)
    if profile is None:
        return None

    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE employees SET status = 'approved', approved_at = ?, approved_by = ? "
            "WHERE user_id = ?",
            (now, approved_by, user_id),
        )
        conn.commit()
    finally:
        conn.close()

    return profile


def reject_profile(user_id: int, rejected_by: int) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE employees SET status = 'rejected', rejected_at = ?, rejected_by = ? "
            "WHERE user_id = ?",
            (now, rejected_by, user_id),
        )
        conn.commit()
    finally:
        conn.close()


def format_founder_card(user_id: int) -> str | None:
    profile = get_profile(user_id)
    if profile is None:
        return None

    full_name = " ".join(
        part
        for part in (profile.get("familiya"), profile.get("ism"), profile.get("otasining_ismi"))
        if part
    ) or "-"

    address = ", ".join(
        part
        for part in (
            profile.get("viloyat"),
            profile.get("tuman"),
            profile.get("mahalla"),
            profile.get("kocha"),
            profile.get("uy_raqami"),
            f"xonadon {profile['xonadon_raqami']}" if profile.get("xonadon_raqami") else None,
        )
        if part
    ) or "-"

    contacts = profile.get("contacts", [])
    contacts_lines = (
        "\n".join(
            f"  {i}. {c['full_name']} ({c['relation']}) — {c['phone']}"
            for i, c in enumerate(contacts, start=1)
        )
        or "  -"
    )

    emergency = next(
        (c for c in contacts if c["id"] == profile.get("emergency_contact_id")), None
    )
    emergency_line = (
        f"{emergency['full_name']} ({emergency['relation']}) — {emergency['phone']}"
        if emergency
        else "-"
    )

    username = f"@{profile['telegram_username']}" if profile.get("telegram_username") else "-"

    lines = [
        f"👤 {full_name}",
        f"🎂 {profile.get('birth_date', '-')} — {profile.get('age', '-')} yosh, {profile.get('jinsi', '-')}",
        f"📞 {profile.get('phone', '-')}",
        "",
        "📇 Qo'shimcha kontaktlar:",
        contacts_lines,
        "",
        f"🏠 Manzil: {address}",
        f"🏢 Filial: {profile.get('branch', '-')}",
        f"💼 Lavozim: {role_name(profile.get('role_key'))}",
        f"📅 Ish boshlagan sana: {profile.get('hire_date', '-')}",
        f"🕒 Ish grafigi: {profile.get('work_schedule', '-')}",
        f"⏳ Rejalashtirilgan muddat: {profile.get('planned_duration', '-')}",
        f"💬 Nega bu kompaniya: {profile.get('motivation', '-')}",
        f"📋 Oldingi tajriba: {profile.get('prior_experience') or '-'}",
        f"🚨 Favqulodda kontakt: {emergency_line}",
        f"💍 Oilaviy holat: {profile.get('marital_status', '-')}",
        f"📱 Username: {username}",
        f"🆔 user_id: {user_id}",
    ]

    if profile.get("extra_note"):
        lines.append(f"📝 Izoh: {profile['extra_note']}")

    return "\n".join(lines)
