FOKUS AI — I/S REJIMI.

MAQSAD:
`feature/hr-conversational-interview` branchidagi tayyor tizimni `main` productionga xavfsiz o'tkazish mumkinmi — faqat shuni aniqlagin.

HOZIR HECH NARSANI O'ZGARTIRMA.

QAT'IY:
- Windows = 0
- faqat Linux/bash
- kod yozma
- commit/push/merge qilma
- deploy qilma
- production DBga yozma
- secret/token/parol qiymatini ko'rsatma
- full test ishlatma
- yangi audit boshlama
- eski tarixni keng o'qima

FAQAT QUYIDAGILARNI TEKSHIR:

1. Real HEAD:
   - `feature/hr-conversational-interview`
   - `main`

2. Test va production ajratilganmi:
   - `TEST_BOT_TOKEN` / `BOT_TOKEN`
   - `TEST_DATABASE_URL` / `DATABASE_URL`
   - `ENVIRONMENT`

3. Productionga o'tishda DB bo'yicha ma'lumotni o'chiradigan yoki buzadigan migration bormi?
   - faqat schema/migration yo'lini tekshir
   - barcha biznes kodni audit qilma

4. Oxirgi mavjud Smoke/E2E natijasini QAYTA ISHLAT.
   Testlarni qayta yugurtirma.
   FAIL'larni faqat 3 guruhga ajrat:
   - REAL production xatosi
   - eskirgan test
   - test muhiti/sozlama xatosi

5. Faqat production launchni haqiqatan bloklaydigan muammoni top.

JAVOB FAQAT SHU FORMATDA:

PRODUCTIONGA CHIQISH:
HA / YO'Q

BLOKLOVCHI REAL MUAMMO:
- yo'q
yoki
- maksimal 3 ta aniq muammo

TOKEN:
AJRATILGAN / MUAMMO BOR

DATABASE:
AJRATILGAN / MUAMMO BOR

DB MIGRATION:
XAVFSIZ / XAVF BOR

KEYINGI BITTA QADAM:
faqat bitta aniq amal

Agar productionga chiqish xavfsizligini aniqlash uchun yana katta audit yoki full test kerak deb o'ylasang — UNI BOSHLAMA.
Nima yetishmayotganini bir gapda yoz va STOP.

Founder ruxsatisiz hech narsani o'zgartirma.