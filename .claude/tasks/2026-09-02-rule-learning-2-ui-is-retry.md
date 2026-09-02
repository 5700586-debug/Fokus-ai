# FOKUS AI ! — 2/3 RETRY: Telegram UI

I/S STRICT. Linux/bash only. Full test YO'Q. main/productionga tegma.
BASE: `420b6e796d1814431be3c28810455d81389304fe`.

Avval `git merge-base --is-ancestor 420b6e796d1814431be3c28810455d81389304fe HEAD`; fail bo'lsa STOP.

## Maqsad
Faqat mavjud `services.rule_learning`ni Telegram oqimiga ulash. Approval va `/setrole` hali YO'Q.

## O'zgartirishga ruxsat
- `discipline_bot.py`
- `tests/test_rule_learning_bot_flow.py` NEW
- `services/chat_cleanup.py` FAQAT mavjud API yetmasa; default o'zgartirma

Read-only: `services/rule_learning.py`, `services/chat_cleanup.py`.
Boshqa production fayl kerak bo'lsa STOP.

## Oqim
Enrollment unfinished user uchun `/listnizom`:
- pending -> snapshotdan resume;
- pending yo'q va bugun 5 -> `✅ Bugungi 5 ta nizom tugadi. Ertaga davom etamiz.`;
- aks holda faqat keyingi BITTA active nizom.
Enrollment yo'q yoki finished -> eski `/listnizom` aynan avvalgidek.

Inline bitta rule xabari:
`[✅ O'qidim] [📖 Hali o'qiyapman]`
- Hali o'qiyapman: DB/next yo'q, callback answer only.
- O'qidim: `confirm_read`, shu xabarni snapshot bilan edit -> `[✅ Tushundim] [❓ Tushunmadim]`.
- Tushunmadim: `confirm_not_understood`, next yo'q; edit -> `[📖 Qayta o'qiyman] [✅ Tushundim]`.
- Qayta o'qiyman: timestamp reset yo'q; shu snapshotni qayta ko'rsat.
- Tushundim: faqat `callback.from_user.id == progress.employee_id`. `confirm_understood` FALSE -> next yo'q. TRUE -> callbackni answer qil, best-effort cleanup, keyin `get_state`: all_done -> `✅ Barcha nizomlarni o'rganib bo'ldingiz.`; limit -> 5 tugadi xabari; aks holda faqat BITTA next.

`services.chat_cleanup`ning mavjud `track(user_id, chat_id, message_id, workflow, workflow_key)` va `cleanup(...)` API sidan foydalan. workflow=`rule_learning`, key=`<employee_id>:<rule_number>`. Cleanup xatosi business flowni to'xtatmasin. DB auditga tegma.

STEP 3 uchun `discipline_bot.py`da bitta kichik module-level reusable async helper chiqar: `start_or_resume_rule_learning(bot, employee_id) -> bool`. Unfinished enrollment bo'lmasa False; handled bo'lsa True. `/listnizom` ham shu helperdan foydalansin. Yangi parallel UI logika yozma.

AI/timer/scheduler/free-text YO'Q.

## Test
FAQAT:
`python -m pytest -q tests/test_rule_learning.py tests/test_rule_learning_bot_flow.py tests/test_learning.py tests/test_schema.py`

Kamida: legacy `/listnizom`, pending resume, Hali o'qiyapman, O'qidim, Tushunmadim block, Tushundim->next, boshqa user callback block, double Tushundim->next once, 5 limit, all done, cleanup DB auditni buzmasin.

Changed Pythonlarni `py_compile` qil. PASS bo'lsa commit: `feat: add rule learning Telegram flow`. Push feature branchga. main/deploy/approval/setrole YO'Q. STOP.

Hisobot faqat: changed files; tests X passed; commit SHA; STEP 2 = DONE/BLOCKED.