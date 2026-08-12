"""Tashqi ta'minotchi kompaniyalar — Founder shaxsiy taklif havolasi
yuboradi, ta'minotchi botning shaxsiy chatida AI bilan suhbatlashadi.

Bu ``roles.py``dagi ichki ``taminotchi`` xodim rolidan (yagona shtat
birligi, ``/marketlog`` orqali bozor razvedkasi qiladi) BUTUNLAY
mustaqil — tashqi hamkor kompaniya, Fokus AI xodimi emas, shuning
uchun ``allowed_users``/``SINGLE_SLOT_ROLES`` tizimiga tegmaydi va
istalgan sonda bo'lishi mumkin.
"""

SCHEMA = """
CREATE TABLE IF NOT EXISTS supplier_invites (
    token TEXT PRIMARY KEY,
    company_name_hint TEXT,
    created_by INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    claimed_by INTEGER,
    claimed_at TEXT
);

CREATE TABLE IF NOT EXISTS suppliers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_user_id INTEGER NOT NULL UNIQUE,
    company_name TEXT,
    region TEXT,
    contact_name TEXT,
    phone TEXT,
    delivery_notes TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    invited_by INTEGER NOT NULL,
    invite_token TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS supplier_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    supplier_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS supplier_offers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    supplier_id INTEGER NOT NULL,
    product_name TEXT NOT NULL,
    price TEXT,
    discount TEXT,
    minimum_order TEXT,
    delivery_time TEXT,
    payment_type TEXT,
    return_terms TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(supplier_id, product_name)
);

CREATE TABLE IF NOT EXISTS supplier_founder_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    supplier_id INTEGER NOT NULL,
    summary_text TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""
