# FOKUS AI ! — Rule learning 1/3: DB + service

I/S STRICT. Linux/bash only. Full test YO'Q. main/productionga tegma.
Branch: `feature/hr-conversational-interview`.

## Maqsad
Faqat nizom o'qish auditining DB + service qatlamini qur. UI/approvalga tegma.

## Manba
`company_rules` yagona nizom manbasi. Eski `services/learning.py` checklist tizimiga tegma.

## O'zgartirishga ruxsat
- `schema/discipline.py`
- `repositories/rule_learning.py` NEW
- `services/rule_learning.py` NEW
- `tests/test_rule_learning.py` NEW
- kerak bo'lsa `tests/test_schema.py`

Boshqa production fayl kerak bo'lsa STOP.

## DB
`rule_learning_enrollments`:
- employee_id PK
- enrolled_at NOT NULL
- finished_at nullable

`rule_learning_progress`:
- id PK autoincrement
- employee_id NOT NULL
- rule_number NOT NULL
- title_snapshot NOT NULL
- content_snapshot NOT NULL
- sent_at nullable
- read_confirmed_at nullable
- not_understood_at nullable
- understood_confirmed_at nullable
- completed_at nullable
- completed_company_date nullable
- UNIQUE(employee_id, rule_number)

Snapshot birinchi progress yaratilganda olinadi va keyin o'zgarmaydi.

## Repository
Minimal funksiyalar:
- ensure_enrollment
- get_enrollment
- get_pending_progress
- ensure_progress
- mark_sent
- mark_read
- mark_not_understood
- mark_understood
- count_completed_for_date
- list_started_rule_numbers
- finish_enrollment

`mark_understood` faqat `read_confirmed_at IS NOT NULL` va hali understood bo'lmasa TRUE qaytarsin. Double clickda FALSE.

## Service
`repositories.discipline.list_active_rules()`dan foydalan.
Tartib `rule_number ASC`.
Company sana: `company_time.today().isoformat()`.
Kunlik limit: 5.
Bir vaqtda faqat bitta incomplete progress.
Pending rule keyin inactive bo'lsa ham snapshotdan davom etadi.
Active rule 0 bo'lsa enrollmentni finished qilma.
Barcha active nizom tugasa finished qil.

## Test
Faqat:
`python -m pytest -q tests/test_rule_learning.py tests/test_schema.py tests/test_learning.py`

Kamida: duplicate enrollment yo'q; active/ASC; snapshot immutable; inactive pending resume; read idempotent; tushunmadim complete emas; read bo'lmasa understood yo'q; understood double-click idempotent; daily limit 5; next company date reset; all complete -> finished; 0 active -> not finished; eski learning testlari PASS.

Keyin o'zgargan fayllarni `py_compile` qil.
PASS bo'lsa commit:
`feat: add rule learning data model and service`

Yakuniy javob FAQAT:
- files
- tests
- commit SHA
- `STEP 1 = DONE` yoki `BLOCKED`
STOP.