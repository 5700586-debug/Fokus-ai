"""Mavjud asosiy jadvallar — o'zgarishsiz, faqat db.py dan ko'chirilgan."""

SCHEMA = """
CREATE TABLE IF NOT EXISTS invites (
    token TEXT PRIMARY KEY,
    role_key TEXT NOT NULL,
    branch TEXT,
    work_schedule TEXT,
    created_by INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    claimed_by INTEGER,
    claimed_at TEXT
);

CREATE TABLE IF NOT EXISTS employees (
    user_id INTEGER PRIMARY KEY,
    invite_token TEXT REFERENCES invites(token),
    telegram_username TEXT,
    familiya TEXT,
    ism TEXT,
    otasining_ismi TEXT,
    birth_date TEXT,
    age INTEGER,
    jinsi TEXT,
    phone TEXT,
    marital_status TEXT,
    viloyat TEXT,
    tuman TEXT,
    mahalla TEXT,
    kocha TEXT,
    uy_raqami TEXT,
    xonadon_raqami TEXT,
    branch TEXT,
    role_key TEXT,
    hire_date TEXT,
    work_schedule TEXT,
    planned_duration TEXT,
    motivation TEXT,
    prior_experience TEXT,
    emergency_contact_id INTEGER REFERENCES employee_contacts(id),
    photo_file_id TEXT,
    extra_note TEXT,
    status TEXT NOT NULL DEFAULT 'draft',
    submitted_at TEXT,
    approved_at TEXT,
    approved_by INTEGER,
    rejected_at TEXT,
    rejected_by INTEGER,
    prior_employer_reference_consent INTEGER,
    prior_employer_contact TEXT
);

CREATE TABLE IF NOT EXISTS employee_contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES employees(user_id),
    full_name TEXT NOT NULL,
    phone TEXT NOT NULL,
    relation TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fsm_storage (
    storage_key TEXT PRIMARY KEY,
    state TEXT,
    data TEXT
);

-- ``roles.py``dagi ruxsat etilgan foydalanuvchilar (rol xaritasi).
-- ``DATABASE_URL`` o'rnatilganda ``allowed_users.json`` o'rniga shu
-- jadval ishlatiladi (qarang: ``roles.py``), chunki fayl ham
-- ``fokus.db`` kabi Render'ning doimiy bo'lmagan diskida yo'qolib
-- ketishi mumkin.
CREATE TABLE IF NOT EXISTS allowed_users (
    user_id INTEGER PRIMARY KEY,
    role_key TEXT NOT NULL,
    added_by INTEGER NOT NULL,
    added_at TEXT NOT NULL
);

-- ``roles.py``dagi ``SINGLE_SLOT_ROLES`` (nazoratchi/haydovchi/taminotchi/
-- moliyachi — filialga bog'lanmagan, faqat 1 kishi) uchun ilova
-- darajasidagi tekshiruv (``roles.set_role()``) yagona himoya EMAS: ikki
-- alohida jarayon (masalan deploy paytida eski+yangi instance bir vaqtda
-- ishlab qolsa) bir xil rolni deyarli bir vaqtda tekshirib, ikkalasi ham
-- "bo'sh" deb topib, ikkalasi ham yozib qo'yishi mumkin (race condition).
-- Shu qisman UNIQUE indeks buni DB darajasida, atomik ravishda oldini
-- oladi — ikkinchi yozuv ``IntegrityError`` bilan rad etiladi
-- (``roles.py``dagi ``set_role()`` shu xatoni ushlab ``False`` qaytaradi).
-- Ro'yxat ``roles.SINGLE_SLOT_ROLES`` bilan qo'lda sinxron ushlanadi.
CREATE UNIQUE INDEX IF NOT EXISTS idx_allowed_users_single_slot_role
    ON allowed_users(role_key)
    WHERE role_key IN ('nazoratchi', 'haydovchi', 'taminotchi', 'moliyachi');
"""
