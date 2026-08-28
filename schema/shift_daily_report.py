"""Kassir kunlik 3 savollik hisobot V1 (prixodi chiqmagan tovar,
"narxi qimmat" mijozlar, xodim ustidan shikoyat) — mavjud kamchilik
gate'idan (``schema/shift_deficiencies.py``) keyin, real
``/closeshift`` yopish jarayonidan oldin ishlaydi.

Bitta smenaga bitta qator, har ustun NULL = savol hali javob
berilmagan (bucket/son har doim aniq qiymat bilan javoblanadi, shuning
uchun alohida progress jadvali shart emas). Mantiq ``services/
shift_daily_report.py``da — bu yerda faqat jadval ta'rifi.
"""

SCHEMA = """
CREATE TABLE IF NOT EXISTS shift_daily_report (
    shift_id INTEGER PRIMARY KEY REFERENCES cash_shifts(id),
    branch TEXT,
    shift_date TEXT NOT NULL,
    no_prixod_count INTEGER,
    price_complaint_bucket TEXT,
    staff_complaint_occurred INTEGER,
    staff_complaint_employee_id INTEGER,
    staff_complaint_type TEXT,
    staff_complaint_note TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""
