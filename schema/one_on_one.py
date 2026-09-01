"""Haftalik 1:1 suhbat (rahbar <-> xodim) — faqat suhbat bo'lgani,
bitta aniq natija turi va (ixtiyoriy) keyingi suhbatga o'tishi kerak
bo'lgan bitta masala saqlanadi. Ball/bonus/minus, psixologik tashxis
yoki baholash bu yerda YO'Q.

Hafta kaliti ``week_start`` — suhbat sanasi tushgan haftaning DUSHANBA
sanasi (yagona kanonik qoida, qarang
``services/one_on_one.py::week_start_for``). Bitta xodimga bitta
haftada bitta yozuv: UNIQUE cheklovi shu kalit ustida, shuning uchun
takroriy yozuv servis tekshiruvidan tashqari DB darajasida ham
bloklanadi.

Follow-up ATAYLAB alohida jadval emas — V1 da bitta suhbatga ko'pi
bilan bitta masala biriktiriladi, shuning uchun u shu qatorning
ustunlari (``followup_text``/``followup_status``). ``employee_id``/
``manager_id`` ``schema/supervision.py``dagi bilan bir xil sababga
ko'ra FK bilan bog'lanmaydi.
"""

SCHEMA = """
CREATE TABLE IF NOT EXISTS employee_one_on_ones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL,
    manager_id INTEGER NOT NULL,
    branch TEXT,
    week_start TEXT NOT NULL,
    meeting_date TEXT NOT NULL,
    outcome TEXT NOT NULL,
    summary TEXT,
    followup_text TEXT,
    followup_status TEXT,
    followup_resolved_by INTEGER,
    followup_resolved_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(employee_id, week_start)
);
"""
