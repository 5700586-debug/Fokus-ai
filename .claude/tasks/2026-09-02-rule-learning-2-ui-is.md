# FOKUS AI ! — Rule learning 2/3: Telegram UI

I/S STRICT. Linux/bash only. Full test YO'Q. main/productionga tegma.
STEP 1 commit mavjud va testlari PASS bo'lmasa STOP.

## Maqsad
Faqat Telegram nizom oqimini ulash. Approval/setrole hali YO'Q.

## O'zgartirishga ruxsat
- `discipline_bot.py`
- `tests/test_rule_learning_bot_flow.py` NEW
- kerak bo'lsa `services/chat_cleanup.py` FAQAT mavjud API yetmasa

Boshqa production fayl kerak bo'lsa STOP.

## Oqim
Enrollment bor va finished emas user uchun `/listnizom`:
- pending bo'lsa resume;
- pending yo'q, bugun <5 bo'lsa keyingi active nizom;
- bugun 5 bo'lsa `✅ Bugungi 5 ta nizom tugadi. Ertaga davom etamiz.`
Enrollment yo'q/finished bo'lsa eski `/listnizom` 100% saqlansin.

Nizom INLINE keyboardda, imkon qadar bitta xabar:
1. `✅ O'qidim` | `📖 Hali o'qiyapman`
2. O'qidim -> shu xabar edit: `✅ Tushundim` | `❓ Tushunmadim`
3. Hali o'qiyapman -> DB complete yo'q, next yo'q, faqat callback answer.
4. Tushunmadim -> not_understood yoz, next yo'q; shu snapshotni qayta o'qish holati.
5. Tushundim -> faqat progress.employee_id == callback user; `mark_understood` TRUE bo'lsa cleanup va keyingi bitta nizom. FALSE bo'lsa next yuborma.
6. 5-tadan keyin 6-si shu kuni chiqmasin.
7. Barcha active tugasa finished + `✅ Barcha nizomlarni o'rganib bo'ldingiz.`
8. Active rule 0 -> `Hozircha faol nizom kiritilmagan.`

AI YO'Q. Timer YO'Q. Erkin matn YO'Q.
Pending ko'rsatishda doim snapshotdan foydalan.

## Cleanup
Mavjud `services/chat_cleanup.py`dan foydalan:
workflow=`rule_learning`, key=`<employee_id>:<rule_number>`.
Yuborilganda track; muvaffaqiyatli Tushundimdan keyin cleanup. Cleanup xatosi flow'ni to'xtatmasin. DB audit o'chmasin.

## Test
Faqat:
`python -m pytest -q tests/test_rule_learning.py tests/test_rule_learning_bot_flow.py tests/test_discipline_bot_flows.py`

Kamida: resume; old UI backward-compatible; Hali o'qiyapman -> next yo'q; O'qidim -> second buttons; Tushunmadim -> next yo'q; other-user callback blocked; double Tushundim -> next bir marta; 5 limit; snapshot resume; cleanup DB auditga tegmaydi.

O'zgargan fayllarni py_compile qil.
PASS bo'lsa commit:
`feat: add rule learning telegram flow`

Yakuniy javob FAQAT:
- files
- tests
- commit SHA
- `STEP 2 = DONE` yoki `BLOCKED`
STOP.