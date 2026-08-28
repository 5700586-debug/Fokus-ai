"""Ta'minotchining REAL bozor xaridi + filiallarga real taqsimoti V1.

``supplier_purchases`` — bitta mahsulot bo'yicha BITTA xarid FAKTI
(kim/qachon/qancha/necha pulga) — ``shift_deficiency_items``ga (kassir
so'ragan miqdor) hech narsa qo'shilmaydi/o'zgarmaydi, faqat REAL xarid
alohida saqlanadi. ``supplier_purchase_allocations`` — shu xaridning
filiallar bo'yicha REAL taqsimoti (bitta filialga bitta qator, FIFO
YO'Q — ta'minotchi o'zi real kiritadi).
"""

SCHEMA = """
CREATE TABLE IF NOT EXISTS supplier_purchases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_name TEXT NOT NULL,
    quantity REAL NOT NULL,
    unit TEXT NOT NULL,
    unit_price INTEGER NOT NULL,
    purchased_by INTEGER NOT NULL,
    purchase_date TEXT NOT NULL,
    price_flagged INTEGER NOT NULL DEFAULT 0,
    price_flag_reason TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS supplier_purchase_allocations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    purchase_id INTEGER NOT NULL REFERENCES supplier_purchases(id),
    branch TEXT NOT NULL,
    quantity REAL NOT NULL,
    created_at TEXT NOT NULL
);
"""
