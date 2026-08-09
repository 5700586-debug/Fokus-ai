"""60 kunlik kalibratsiya davrida yig'ilgan RoleBaseline va yangi xodim
adaptatsiya profillari — bilim individual xodimga bog'lanib qolmasligi
uchun.
"""

SCHEMA = """
CREATE TABLE IF NOT EXISTS role_baselines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role_key TEXT NOT NULL,
    dimension TEXT NOT NULL,
    description TEXT NOT NULL,
    source_note TEXT,
    established_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS employee_adaptation_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    role_key TEXT NOT NULL,
    start_date TEXT NOT NULL,
    day_number INTEGER NOT NULL,
    dimension TEXT NOT NULL,
    rating TEXT NOT NULL,
    note TEXT,
    evaluated_at TEXT NOT NULL
);
"""
