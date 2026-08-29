BRANCH: feature/hr-conversational-interview

Faqat:
- onboarding.py
- schema/core.py
- db.py
- employees.py
- tests/test_bot_flows.py

o‘zgartir.

QAT’IY:
- main/prodga tegma
- Windows/PowerShell yo‘q
- repo-wide search/audit yo‘q
- refactor yo‘q
- full-suite yo‘q
- faqat shu vazifani bajar

VAZIFA — onboardingga 4 ta o‘zgarish:

1) MANZIL

Real/shaxsiy manzil misolini olib tashla.

Prompt:
“Uy manzilingizni kiriting.
Masalan: Alisher Navoiy ko‘chasi, 15-uy.”

2) ASOSIY GRAFIK + TUNGI SMENA

Mavjud work_schedule saqlansin.

Qo‘lda so‘raladigan prompt:
“Asosiy (odatdagi) ish grafigingizni kiriting. Masalan: 09:00–18:00”

Preset grafik bo‘lsa ham, qo‘lda kiritilsa ham undan keyin so‘ra:

“Tungi smenada ishlay olasizmi?”

Tugmalar va DB qiymatlari:
✅ Ha, doim ishlay olaman → always
🔄 Ba’zan ishlay olaman → sometimes
❌ Yo‘q, faqat kunduzgi smena → day_only

DB:
employees.night_shift_availability TEXT

3) JAMOAGA YORDAM KELISHUVI

Tungi smena savolidan keyin so‘ra:

“Bizda ‘bu mening ishim emas’ degan gap qabul qilinmaydi. Zarurat bo‘lsa, o‘z vazifangizdan tashqari jamoaga yordam berishga rozimisiz?”

Tugmalar:
✅ Ha, roziman → 1
❌ Yo‘q, rozimasman → 0

DB:
employees.teamwork_agreement INTEGER

“Yo‘q” avtomatik rad qilmasin, faqat saqlansin.

4) RAHBAR/USTOZ BILAN ISHLASH KELISHUVI

Jamoaga yordam savolidan keyin so‘ra:

“Bizda yosh emas, vazifa va mas’uliyat muhim. Sizdan yoshroq bo‘lsa ham, vakolati bor rahbar yoki sizga ish o‘rgatayotgan xodim topshiriq bersa, ‘sen menga xo‘jayin emassan’ demasdan bajarishga rozimisiz? Teng lavozimdagi sherigingiz ish yuzasidan yordam so‘rasa, hamkorlik qilishingiz shart.”

Tugmalar:
✅ Ha, roziman → 1
❌ Yo‘q, rozimasman → 0

DB:
employees.authority_cooperation_agreement INTEGER

“Yo‘q” avtomatik rad qilmasin, faqat saqlansin.

F.I.Sh.:
Mavjud Familiya → Ism → Otasining ismi oqimi allaqachon to‘g‘ri.
TEGMA.

SUMMARY:

Yakuniy anketa kartasiga qo‘sh:

🌙 Tungi smena:
always → Ha, doim ishlay olaman
sometimes → Ba’zan ishlay olaman
day_only → Yo‘q, faqat kunduzgi smena

🤝 Jamoaga yordam: Ha/Yo‘q
🧭 Rahbar/ustoz topshirig‘i: Ha/Yo‘q

DB:

Yangi 3 ustunni:
- schema/core.py
- db.py::_ADDITIVE_COLUMNS
- employees.py::_EMPLOYEE_FIELDS

ga to‘g‘ri qo‘sh.

TEST:

tests/test_bot_flows.py ichida faqat shu o‘zgarishlar uchun targeted test yarat/kengaytir.

Tekshir:
- real/shaxsiy manzil misoli yo‘q
- neutral manzil misoli bor
- preset grafikdan keyin tungi smena savoli chiqadi
- oddiy grafikdan keyin ham chiqadi
- always/sometimes/day_only to‘g‘ri saqlanadi
- ikki kelishuv 1/0 sifatida saqlanadi
- “Yo‘q” avtomatik rad qilmaydi
- summaryda uchala yangi ma’lumot ko‘rinadi

Target test nomi:
tests/test_bot_flows.py::test_onboarding_new_agreements_and_night_shift

Faqat shu targeted testni GitHub Actions ubuntu-latest da ishlat.
Full-suite ishlatma.

Green bo‘lsa 1 commit qil.

Scope kattalashsa yoki ko‘rsatilmagan faylni o‘zgartirish kerak bo‘lsa STOP:

[STOP sababi: ... | Kerakli fayl/ruxsat: ...]

YAKUNDA FAQAT:
✅/❌
Test: PASS/FAIL
Commit SHA
main/prod: tegilmadi