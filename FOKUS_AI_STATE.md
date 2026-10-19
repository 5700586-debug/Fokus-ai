# FOKUS AI — joriy holat

Tekshirilgan: 2026-10-18, manba: main HEAD `dd0c492`

Bu fayl faqat tekshirilgan faktlarni saqlaydi. Qarorlar, g'oyalar va qoidalar — `FOKUS_AI_XOTIRA.md` da. Ziddiyat bo'lsa real Git/GitHub/Render holati ustun.

## Joriy holat (git log + faqat MERGE qilingan PR'lar)

- `main` HEAD = `dd0c492` — PR #48 merge'i (baho xabari + yaxlit tranzaksiya). Undan oldin: #47 (hujjat, `ea55eb6`), #45 (`9ead58b`).
- Baholash: #48 — baho qo'yilganda xodimga shaxsiy xabar, baho/tarix/balans/ledger bitta tranzaksiyada (SQLite va lokal PostgreSQL 16.15'da sinalgan).
- Kassa: #43 qo'lda yopish (3 rasm, moliyachi tekshiruvi), #44 Asosiy menyu / tozalash / "Qayta yuborish", #45 ochish-yopish soddalashtirildi; #42 kassir menyusi soddalashtirildi.
- Nazoratchi: #37 filial-birinchi kunlik oqim, #38 sodda matnlar, #40 filial yopilganda xodimlar natijalari, #41 oy oxirigacha grafik.
- 2026-10-01..03 oralig'ida kassa va ro'yxat tuzatishlari merge qilingan: #24–#36 (naqd summa o'qish, oldingi qoldiq tasdig'i, yarim tundan keyingi smena, buyurtma ro'yxati oqimlari, ledger xarajatlari, nazoratchidan pul yashirish, rasm tahlili vaqti, qayta boshlash tugmasi).
- Merge qilinmay yopilgan PR: #2 "Release FOKUS AI ! menu simplification" (2026-09-01) — bajarilgan deb hisoblanmaydi.

## Ochiq PR'lar

- #46 — kassa dialog xabarlarini yoshga qarab tozalash + eskirgan `csui_` tugmalar. Holat: ochiq, `MERGEABLE`/`CLEAN`, merge qilinmagan.
- #39 — production read-only smoke E2E (faqat qo'lda ishga tushadi). Holat: ochiq, `MERGEABLE`/`CLEAN`, merge qilinmagan.
- #22 — daftar rasmidan kassa maydonlarini o'qish. Holat: ochiq, `CONFLICTING`/`DIRTY`, merge qilinmagan.

## Deploy / Render

- `9ead58b` live, 2026-10-07 (ChatGPT Render tekshiruvi, 2026-10-18).
- `dd0c492` (PR #48) — Muhammadiy xabari bo'yicha Render LIVE; robot tekshirmadi (robotda Render kirish yo'q).
- Quyidagi 2-qadam hali deploy qilinmagan.

## Bajarilgan ish

- `FOKUS_AI_XOTIRA.md` qo'shildi (PR #47, merge qilingan).
- PR #48 (merge qilingan, `dd0c492`): baho qo'yilgan zahoti xodimga shaxsiy xabar; `bos:grade` va `nzr_grade` ikkalasi `record_daily_grade` → `notify_employee_of_grade`; baho, tarix, bonus balansi va ledger bitta DB tranzaksiyasida (`save_daily_grade`); bir xil baho takrori yangi yozuv/xabar qo'shmaydi; 22:00–07:00 ovozsiz; PostgreSQL 16.15 (`PgConnection`, vaqtincha lokal Docker) bilan rollback/parallel/pool sinalgan.
- 2-qadam (branch `feature/grade-month-by-evaluation-date`, PR ochiq, merge/deploy qilinmagan): oylik baho hisobi baho sanasi (`eval_date`) oyiga bog'landi. `get_period_point_totals(user_id, year_month=None)` (berilmasa kompaniyaning joriy oyi; `"YYYY-MM"` validatsiyasi, chegara: boshlanish <= sana < keyingi oy boshlanishi, kompaniya vaqt zonasi) → `discipline_repo.get_month_point_totals`: kunlik baho bonusi kanonik `daily_evaluations` jadvalidan (`eval_date` oyi bo'yicha); ledgerdagi `daily_evaluation` yozuvlari qayta qo'shilmaydi; boshqa bonus/haqiqiy minus/qaytarishlar ledgerdan o'z `created_at` oyi bo'yicha (kompaniya zonasida). Baho xabari: eval_date va o'sha oy yig'indisi; joriy oyda "Shu oy …", oldingi oyda "2026-10 uchun …". "Yulduzlarim" dashboardi joriy oy bahosini ko'rsatadi. Eski oy bahosini keyin tuzatish faqat o'sha oyni o'zgartiradi (soxta minus yo'q, ledger/audit saqlanadi, `get_bonus_ledger_totals_since` o'zgarmagan).
- Testlar: 6 ta fayl (bonus ledger, discipline service, bot flows, employee dashboard, nazoratchi daily flow/supervision) SQLite: 218 passed; PostgreSQL 16.15 (`tests/test_discipline_postgres.py`, `PgConnection`, vaqtincha lokal Docker instance, tozalangan): 23 passed, 3 marta takrorlandi.

## Qolgan cheklovlar

- Tarixiy ledger-only `daily_evaluation` yozuvlari (`daily_evaluations` qatori bo'lmagan) oylik hisobga kirmaydi va taxmin bilan bahoga aylantirilmagan; production'da bunday yozuvlar bor-yo'qligi tekshirilmagan.
- Boshqa bonus/minus yozuvlari o'z yozilgan oyiga tushadi (sanasi `eval_date`ga ko'chirilmagan): masalan o'tgan oy sanasiga qo'yilgan jarima yozilgan oyda minus bo'ladi.
- Telegram ID'siz xodim: `employees.user_id` PRIMARY KEY va o'zi Telegram ID; Telegram ID'siz xodimni saqlash/baholash mavjud modelda qo'llanmaydi — alohida vazifa. Bloklangan yoki chat topilmagan foydalanuvchida baho saqlanadi (nazoratchiga "Xodim botga ulanmagan — baho saqlandi, xabar yuborilmadi.").
- Ko'p worker (bir nechta bot jarayoni) va Supabase/production PostgreSQL bilan sinov o'tkazilmagan. `PgConnection` pool `maxconn=5`.
- PostgreSQL testi opt-in: `FOKUS_PG_TEST_DSN` o'rnatilmasa 23 ta test SKIP bo'ladi (bu PG PASS emas).
- Real Telegram E2E va deploy — bajarilmagan.

## Keyingi qadam

- 3-qadam: xodimning kunma-kun "Oylik baholarim" oynasi. Muhammadiy belgilaydi.
