# FOKUS AI ! — 3/3: approval gate + final targeted test

I/S STRICT. Linux/bash only. Full test YO'Q. main/productionga tegma.
BASE: `898217f9469a86327f000a34fef67dfeb245ab33`.
Avval `git merge-base --is-ancestor 898217f9469a86327f000a34fef67dfeb245ab33 HEAD`; fail bo'lsa STOP.

## Maqsad
Nizom Telegramda FAQAT 100% ishga kirgan xodimga chiqsin: Founder approve qilgan VA `roles.set_role(...)` muvaffaqiyatli bo'lganidan keyin.

## O'zgartirishga ruxsat
- `approval.py`
- `main.py` FAQAT `/setrole` success qismi
- `tests/test_rule_learning_bot_flow.py`
Boshqa production fayl kerak bo'lsa STOP.

## Approval oqimi
1. Mavjud `employees.approve_profile()` va `roles.set_role()` tartibini buzma.
2. Approval success bo'lsa `ensure_enrollment(user_id)` idempotent qilinishi mumkin, LEKIN nizom xabari role success bo'lmaguncha HECH QACHON yuborilmasin.
3. `roles.set_role()` success bo'lgach, mavjud tasdiqlash/menu xabaridan KEYIN `discipline_bot.start_or_resume_rule_learning(callback.bot, user_id)` chaqir.
4. Role fail bo'lsa: nizom xabari YO'Q. Keyin Founder `/setrole` bilan muvaffaqiyatli rol bersa, FAQAT oldindan mavjud unfinished enrollment bo'lsa start/resume qil.
5. Eski mavjud xodimga oddiy `/setrole` yangi enrollment yaratmasin.
6. Duplicate approve/callback: duplicate enrollment/progress/nizom xabari YO'Q.
7. Rule-learning xatosi approval yoki setrole business flowni buzmasin; log qilib davom et.

## Test
FAQAT:
`python -m pytest -q tests/test_rule_learning.py tests/test_rule_learning_bot_flow.py tests/test_learning.py tests/test_schema.py tests/test_discipline_bot_flows.py`

Kamida tekshir:
- approve + role success -> enrollment + first rule;
- approve success + role fail -> rule message yo'q;
- keyin `/setrole` success -> mavjud enrollment resume;
- eski user `/setrole` -> enrollment yaratmaydi;
- duplicate approve -> duplicate rule yo'q;
- legacy `/listnizom`, 5/day va double-click regressiya yo'q.

Changed Pythonlarni `py_compile` qil. Scope faqat ruxsat fayllar.
PASS bo'lsa commit: `feat: start rule learning after employee approval` va feature branchga push qil.
MAIN merge YO'Q. Deploy YO'Q. Mini App YO'Q.

Hisobot faqat:
1. files
2. tests: X passed, 0 failed
3. commit SHA
4. production untouched: yes
5. `2-QISM = DONE` yoki `BLOCKED`
STOP.