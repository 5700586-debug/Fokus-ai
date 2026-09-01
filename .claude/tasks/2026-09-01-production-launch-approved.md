# FOKUS AI — HAQIQIY PRODUCTION LAUNCH — Founder approved

I/S STRICT MODE.

MUHIM RUNNER CHEGARASI:
Bu task mavjud Claude runner orqali bajariladi. Runnerning yuqori darajadagi `main va productionga tegma` himoyasini BUZMA yoki chetlab o'tma. Agar shu himoya productionga yozishni bloklasa, quyidagi preflight tekshiruvlarini READ-ONLY bajar va natijada `STOP: runner production yozuvini taqiqlaydi` deb aniq yoz. Main/prodga yashirin yo'l bilan tegma.

MAQSAD:
Testda tayyorlangan FOKUS AI holatini haqiqiy FOKUS AI productionga xavfsiz chiqarish.

REPO:
5700586-debug/Fokus-ai

RELEASE CANDIDATE:
39a0c9a9e52ffba2e68382cee9f5ec892cc1c612

KUTILAYOTGAN ESKI MAIN:
8f492e2bd85606779993415b3aad58ae8ed1f509

PRODUCTION RENDER SERVICE:
Fokus-ai
srv-d9q82sh42hec73a0au6g

Founder bu vazifani yuborishni aniq tasdiqlagan. Lekin mavjud runner guard'i undan yuqori xavfsizlik to'sig'i sifatida saqlanadi.

QAT'IY:
- Windows = 0
- faqat Linux/bash
- yangi feature yozma
- refactor qilma
- 188 commitni qayta audit qilma
- secret/token/parol qiymatini ko'rsatma
- production DB ma'lumotini DELETE/TRUNCATE/DROP qilma
- test botni production token/bazaga ulama
- suspend qilingan eski/orphan worker'ni yoqma
- bir vaqtning o'zida ikki production bot instance ishlamasin

1-QADAM — PREFLIGHT, READ-ONLY

A) `39a0c9a9e52ffba2e68382cee9f5ec892cc1c612` mavjudligini tekshir.
B) `main` hali `8f492e2bd85606779993415b3aad58ae8ed1f509`dami tekshir. O'zgargan bo'lsa STOP.
C) `main` release candidate'ning ancestor'i ekanini tekshir. Divergence/conflict bo'lsa STOP.
D) Release candidate production rejimida `BOT_TOKEN` va `DATABASE_URL` ishlatishini tekshir. `TEST_BOT_TOKEN` yoki `TEST_DATABASE_URL` productionda ishlatilmasin.
E) Agar real Render access mavjud bo'lsa, production environmentda faqat VARIABLE NOMLARINI tekshir: `BOT_TOKEN` mavjud, `DATABASE_URL` mavjud, `ENVIRONMENT=production` yoki unset. QIYMATLARNI LOGGA CHIQARMA.
Agar Render access bo'lmasa: `STOP: Render production sozlamalarini tekshirish uchun access yo'q` deb yoz.
F) Agar Render access mavjud bo'lsa, productiondagi oxirgi LIVE deploy/commit va deploy ID'ni rollback nuqtasi sifatida aniqlagin. Eski hujjatga ko'r-ko'rona ishonma.
G) Suspend qilingan eski/orphan production worker hali suspend ekanini tekshir. Uni YOQMA.

2-QADAM — RELEASE GATE

Full test suite ishlatma.
Agar runner/CI orqali mavjud Smoke natijasini ko'rish mumkin bo'lsa, eng yangi real Smoke natijasini ishlat. Keraksiz qayta test ishlatma.
Agar release candidate uchun yangi Smoke shart bo'lsa, faqat `.github/workflows/smoke-tests.yml`dagi Smoke to'plamini BIR MARTA ishlat.
Kutiladigan natija: barcha Smoke PASS, 0 FAIL.
Bitta FAIL bo'lsa main/deploy qilma; birinchi real bloklovchini yoz va STOP.

3-QADAM — PRODUCTIONGA O'TKAZISH

FAQAT runner guard bunga ruxsat bersa VA barcha gate PASS bo'lsa:
- release candidate holatini `main`ga xavfsiz olib chiq
- force push qilma
- yangi kod/refactor qo'shma
- productionga aynan tekshirilgan release holati chiqsin
- Render deployni kuzat

Agar runner guard `main va productionga tegma` desa, BU QADAMNI BAJARMA. Guardni tahrirlama yoki chetlab o'tma. `STOP: runner production yozuvini taqiqlaydi` deb yakunla.

4-QADAM — LIVE TEKSHIRUV

Agar deploy bajarilgan bo'lsa, `LIVE` bo'lmaguncha muvaffaqiyat deb hisoblama. Logda quyidagilar bo'lmasin:
- TelegramConflictError
- BOT_TOKEN xatosi
- DATABASE_URL/Postgres ulanish xatosi
- Traceback
- startup crash
Faqat BIRTA production bot instance ishlayotganini tasdiqla.

5-QADAM — XATO BO'LSA

Agar production deploy bajarilgan va FAILED bo'lsa:
- production DBga tegma
- secretlarni o'zgartirma
- orphan worker'ni yoqma
- ketma-ket yangi deploy qilma
- imkon bo'lsa oldindan aniqlangan oxirgi LIVE deployga rollback qil
Rollback imkonsiz bo'lsa STOP va sababni yoz.

6-QADAM — NATIJA

Faqat shu formatda javob ber:

PRODUCTION:
LIVE / STOP / ROLLBACK

RELEASE COMMIT:
...

SMOKE:
... PASS / ... FAIL / NOT RUN

TOKEN:
PRODUCTION / MUAMMO / TEKSHIRIB BO'LMADI

DATABASE:
PRODUCTION / MUAMMO / TEKSHIRIB BO'LMADI

BOT INSTANCE:
1 TA / MUAMMO / TEKSHIRIB BO'LMADI

RENDER:
LIVE / FAILED / ACCESS YO'Q / NOT TOUCHED

STOP SABABI:
... yoki YO'Q

KEYINGI BITTA QADAM:
...

Keraksiz uzun izoh yozma.