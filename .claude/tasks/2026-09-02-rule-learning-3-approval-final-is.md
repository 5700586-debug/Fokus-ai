# FOKUS AI ! — Rule learning 3/3: approval + final gate

I/S STRICT. Linux/bash only. Full test YO'Q. main/productionga tegma.
STEP 1 va STEP 2 commit/test PASS bo'lmasa STOP.

## Maqsad
Yangi tasdiqlangan xodimni avtomatik enrollment qilish va birinchi nizomni boshlash. Edge case: approve bo'lib role assignment fail bo'lsa, keyingi qo'lda `/setrole` success oqimni resume qilsin.

## O'zgartirishga ruxsat
- `approval.py`
- `main.py` FAQAT `set_role_handler` success qismi
- `tests/test_rule_learning_bot_flow.py`

Boshqa production fayl kerak bo'lsa STOP.

## Approval
`employees.approve_profile()` muvaffaqiyatli bo'lgach `ensure_enrollment(user_id)` qil.
Enrollment xatosi approvalni rollback qilmasin; log qilib davom et.
`roles.set_role()` ham muvaffaqiyatli bo'lsa, mavjud tasdiqlash/menu xabaridan keyin rule-learning start/resume qil.
Duplicate approval -> duplicate enrollment/progress/xabar YO'Q.

## Role assignment fail edge case
Approve success, role set fail bo'lsa enrollment saqlansin, nizom yuborilmasin.
Keyin Founder `/setrole` bilan muvaffaqiyatli rol bersa:
- FAQAT oldindan mavjud, finished bo'lmagan enrollment bo'lsa start/resume qil;
- eski mavjud xodimga oddiy `/setrole` yangi enrollment yaratmasin.
`main.py`ning boshqa joyiga tegma.

## Final targeted test
Faqat:
`python -m pytest -q tests/test_rule_learning.py tests/test_rule_learning_bot_flow.py tests/test_learning.py tests/test_schema.py tests/test_discipline_bot_flows.py`

Kamida: approval->enrollment; approval->first rule; duplicate approval idempotent; role fail enrollment qoladi; later setrole resumes; old user setrole enrollment yaratmaydi; old /listnizom saqlanadi; 5/day va double-click regressiya yo'q.

So'ng o'zgargan fayllarni py_compile qil.
`git diff --name-only` bilan scope tekshir. `.env`, token, password, DATABASE_URL qiymati commitga kirmasin.

PASS bo'lsa commit:
`feat: start rule learning after employee approval`

MAINga merge QILMA. Deploy QILMA. Mini Appga o'tma.

Yakuniy javob FAQAT 5 qator:
1. files
2. tests: X passed, 0 failed
3. commits: step1 / step2 / step3 SHA
4. production untouched: yes
5. `2-QISM = DONE` yoki `BLOCKED`
STOP.