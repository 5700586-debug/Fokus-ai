"""Kassir smena yopishidan oldingi kamchilik hisoboti V1: bozor
(market) va firma (company) zakazlari alohida yoziladi, "kechagi
kelmaganlar" bir xil filial ichida smenadan smenaga davom etadi
(``services/shift_deficiency.py``dagi ``source_date < shift_date``
filtri orqali — alohida rollover yozuvi shart emas).

``shift_deficiency_progress`` — har bir smena uchun 3 qadamning
(bozor/firma/kechagi ko'rib chiqish) qachon bajarilganini belgilaydi,
shuning uchun bo'sh ro'yxat holati ham item borligidan emas, aniq
tasdiqlashdan xulosa qilinadi. Formulalar/gate mantiq ``services/
shift_deficiency.py``da — bu yerda faqat jadval ta'rifi.
"""

SCHEMA = """
CREATE TABLE IF NOT EXISTS shift_deficiency_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    shift_id INTEGER NOT NULL REFERENCES cash_shifts(id),
    employee_id INTEGER NOT NULL,
    branch TEXT,
    category TEXT NOT NULL,
    product_name TEXT NOT NULL,
    quantity REAL NOT NULL,
    unit TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    source_date TEXT NOT NULL,
    created_at TEXT NOT NULL,
    resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS shift_deficiency_progress (
    shift_id INTEGER PRIMARY KEY REFERENCES cash_shifts(id),
    market_done_at TEXT,
    company_done_at TEXT,
    yesterday_review_done_at TEXT
);
"""
