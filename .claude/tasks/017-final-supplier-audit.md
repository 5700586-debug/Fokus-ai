BRANCH: feature/hr-conversational-interview
RANGE: f29874b..c53e829

VAZIFA:
Faqat shu range ichidagi yangi o‘zgarishlarni yakuniy READ-ONLY tekshir.
Kod o‘zgartirma. Bu auditda targeted test talab qilinmaydi va mavjud testlarni qayta yugurtirma.

QAT’IY:
- Windows/PowerShell yo‘q
- repo-wide search/audit yo‘q
- full-suite yo‘q
- testlarni qayta yugurtirma
- main/prodga tegma
- docs/history o‘qima
- refactor tavsiya qilma

FAQAT shu diffni o‘qi:
git diff f29874b..c53e829

Quyidagi final qoidalarda REAL xato bormi, tekshir:

1. /xarid:
market open/unresolved only, closed history yo‘q, product+unit jamlanadi, last price chiqadi.

2. Real xarid:
real qty requested dan kam/teng/ko‘p bo‘lishi mumkin; unit price saqlanadi; jami summa to‘g‘ri.

3. Narx AI:
pasayish yoki <20% oshishda AI yo‘q;
faqat >=20% oshishda AI gate;
AI failure = savol yo‘q;
birinchi purchase = AI yo‘q.

4. Qo‘shimcha mahsulot:
supplier nom + qty + unit + unit price kiritadi;
eski tarixiy mahsulotlar ro‘yxati chiqarilmaydi.

5. Filial taqsimoti:
FIFO yo‘q;
real allocation;
branch requestdan ko‘p mumkin;
jami allocation purchased qty dan oshmaydi;
qoldiq ko‘rinadi;
to‘liq taqsimlanmaguncha yakunlanmaydi.

6. /natijam:
mavjud market supplier stats ishlatiladi;
buyurtma/keltirildi/kelmadi/% chiqadi;
KPI/dashboard/scheduler yo‘q.

7. Nazoratchi:
employee yo‘q bo‘lsa oddiy xabar;
technical /score syntax ko‘rinmaydi;
monthly score feature o‘chirilmagan.

8. Recruiting privacy:
real uy manzili misol sifatida yo‘q;
neytral prompt/example ishlatiladi.

Agar hammasi to‘g‘ri:
✅ PASS

Agar real xato bo‘lsa:
❌ XATO
- Fayl:
- Joy:
- Xato:
- Minimal tuzatish:

Kod yozma.
Commit qilma.
Test yugurtirma.
Uzun izoh yozma.
