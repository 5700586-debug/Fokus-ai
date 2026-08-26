"""Davomat: hozircha faqat sxema. AttendanceEventProvider ulanguncha
(Face ID, webhook va h.k.) bu jadvallarni to'ldiradigan real oqim yo'q —
``providers/attendance_provider.py`` interfeysiga qarang.
"""

SCHEMA = """
CREATE TABLE IF NOT EXISTS attendance_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    event_time TEXT NOT NULL,
    source TEXT NOT NULL,
    raw_reference TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS attendance_reasons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL,
    event_date TEXT NOT NULL,
    reason_status TEXT NOT NULL,
    note TEXT,
    confirmed_by INTEGER,
    confirmed_at TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(employee_id, event_date)
);

-- Strukturali kunlik smena jadvali -- ``employees.work_schedule``
-- (erkin matn, majburiy format emas) o'rniga reja soatini ISHONCHLI
-- hisoblash uchun. ``status='work'`` bo'lsa ``planned_start``/
-- ``planned_end`` "HH:MM" formatida; ``status='off'`` bo'lsa ikkalasi
-- ham NULL. Bitta xodim/sana uchun bitta qator -- UNIQUE cheklovi
-- ostida, yozuv yo'q sana esa UNKNOWN (OFF DEB TAXMIN QILINMAYDI).
CREATE TABLE IF NOT EXISTS employee_scheduled_shifts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL,
    shift_date TEXT NOT NULL,
    planned_start TEXT,
    planned_end TEXT,
    status TEXT NOT NULL,
    source TEXT NOT NULL,
    created_by INTEGER,
    created_at TEXT NOT NULL,
    UNIQUE(employee_id, shift_date)
);

-- ``employee_scheduled_shifts`` joriy (eng so'nggi) qiymatni saqlaydi --
-- eski qiymat hech qachon yo'qolmasin uchun har bir yozish/o'zgartirish
-- shu yerga alohida audit qatori qo'shadi (qarang
-- ``repositories/attendance.py::set_work_shift``/``set_day_off``).
-- ``is_late_change`` -- smena ALLAQACHON boshlangandan keyin
-- o'zgartirilganmi (faqat belgi, avtomatik jarima/aybdorlik hukmi
-- EMAS -- bu hisob-kitob services/ qatlamida qilinadi).
CREATE TABLE IF NOT EXISTS employee_schedule_revisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL,
    shift_date TEXT NOT NULL,
    old_status TEXT,
    old_planned_start TEXT,
    old_planned_end TEXT,
    new_status TEXT NOT NULL,
    new_planned_start TEXT,
    new_planned_end TEXT,
    changed_by INTEGER,
    changed_at TEXT NOT NULL,
    reason TEXT,
    is_late_change INTEGER NOT NULL DEFAULT 0
);

-- Xodimning umumiy grafik SIYOSATI (fixed_1/fixed_2/flexible) --
-- kunlik ``employee_scheduled_shifts`` yozuvidan ATAYLAB ALOHIDA.
-- Resolution tartibi: employee override -> role default -> UNKNOWN
-- (qarang ``services/attendance.py::resolve_schedule_mode``).
CREATE TABLE IF NOT EXISTS employee_schedule_policy (
    employee_id INTEGER PRIMARY KEY,
    schedule_mode TEXT NOT NULL,
    updated_by INTEGER,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS role_schedule_policy (
    role_key TEXT PRIMARY KEY,
    schedule_mode TEXT NOT NULL,
    updated_by INTEGER,
    updated_at TEXT NOT NULL
);

-- Ko'chma (filiallararo yuradigan) xodim SIYOSATI -- masalan
-- Nazoratchi, lekin hardcode qilinmagan: kelajakda boshqa lavozimga
-- ham berilishi mumkin. Xuddi grafik siyosati bilan bir xil
-- employee-override/role-default naqshi.
CREATE TABLE IF NOT EXISTS employee_mobility_policy (
    employee_id INTEGER PRIMARY KEY,
    mobility_policy TEXT NOT NULL,
    updated_by INTEGER,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS role_mobility_policy (
    role_key TEXT PRIMARY KEY,
    mobility_policy TEXT NOT NULL,
    updated_by INTEGER,
    updated_at TEXT NOT NULL
);

-- Kunlik ANIQ filial talabi (masalan "Nazoratchi A, 2026-08-26,
-- Saturn 1, kamida 30 daqiqa"). ``min_stay_minutes`` har doim ANIQ
-- kiritiladi -- global standart (masalan 30) kodda hech qachon
-- hardcode qilinmaydi.
CREATE TABLE IF NOT EXISTS branch_visit_requirements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL,
    req_date TEXT NOT NULL,
    branch TEXT NOT NULL,
    min_stay_minutes INTEGER NOT NULL,
    created_by INTEGER,
    created_at TEXT NOT NULL,
    UNIQUE(employee_id, req_date, branch)
);

-- ``branch_visit_requirements`` joriy qiymatni saqlaydi -- talab
-- keyinchalik xodim faoliyatini baholashga ta'sir qilishi mumkin,
-- shuning uchun har bir yaratish/o'zgartirish/o'chirish shu yerga
-- alohida audit qatori qo'shadi (qarang
-- ``repositories/attendance.py::set_branch_visit_requirement``/
-- ``remove_branch_visit_requirement``). Faqat tarix -- avtomatik
-- jazo/hukm EMAS.
CREATE TABLE IF NOT EXISTS branch_visit_requirement_revisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL,
    req_date TEXT NOT NULL,
    branch TEXT NOT NULL,
    old_min_stay_minutes INTEGER,
    new_min_stay_minutes INTEGER,
    action TEXT NOT NULL,
    changed_by INTEGER,
    changed_at TEXT NOT NULL
);

-- Filialga kirish/chiqish eventlari -- provider-independent (Face ID
-- keyinchalik ulanadi, hozir qo'lda/boshqa manbadan yoziladi). Hech
-- qachon o'chirilmaydi.
CREATE TABLE IF NOT EXISTS branch_visit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL,
    branch TEXT NOT NULL,
    event_type TEXT NOT NULL,
    event_time TEXT NOT NULL,
    source TEXT NOT NULL,
    raw_reference TEXT,
    created_at TEXT NOT NULL
);
"""
