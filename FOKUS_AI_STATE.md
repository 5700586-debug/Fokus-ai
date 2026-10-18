# FOKUS AI — joriy holat

Tekshirilgan: 2026-10-18, manba: main HEAD `ea55eb6`

Bu fayl faqat tekshirilgan faktlarni saqlaydi. Qarorlar, g'oyalar va qoidalar — `FOKUS_AI_XOTIRA.md` da. Ziddiyat bo'lsa real Git/GitHub/Render holati ustun.

## Joriy holat (git log + faqat MERGE qilingan PR'lar)

- `main` HEAD = `ea55eb6` — PR #47 merge'i (faqat hujjat: FOKUS_AI_XOTIRA.md, STATE, CLAUDE.md). Bot kodiga oxirgi o'zgarish: PR #45 (`9ead58b`, 2026-10-06).
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
- Undan keyingi deploy — tekshirilmadi (robotda Render kirish yo'q).

## Bajarilgan ish

- `FOKUS_AI_XOTIRA.md` qo'shildi (PR #47, merge qilingan).
- Baho qo'yilgan zahoti xodimga shaxsiy xabar (branch `feature/grade-instant-notice`, PR ochiq, merge qilinmagan): `bos:grade` va `nzr_grade` ikkalasi `record_daily_grade` → `notify_employee_of_grade` orqali ishlaydi. Baho, tarix, bonus balansi va ledger BITTA DB tranzaksiyasida (`repositories/discipline.py::save_daily_grade`): istalgan yozuv xato bersa hammasi bekor, qayta bosish noldan to'liq ishlaydi; xabar faqat commit'dan keyin. Balans atomik delta bilan (parallel yangilanish yo'qolmaydi). Xabar: sana, baho nomi/ball, shu oy bonus/minus/jami; tuzatishda "✏️ Tuzatildi: 3 → 2"; 22:00–07:00 (kompaniya vaqti) ovozsiz. Bir xil baho takrori ledger/tarix/xabar qo'shmaydi. Baho tuzatishi (`daily_evaluation`) intizomiy minus sifatida sanalmaydi. Telegram yuborish xatosi commit qilingan bahoni bekor qilmaydi. Targeted test (5 ta fayl): 178 passed (rollback testlari haqiqiy DB trigger xatolari bilan, SQLite); qo'shimcha dashboard/yopish hisoboti/timezone/davomat testlari 48 passed. PostgreSQL, ko'p worker, real E2E va deploy — tekshirilmagan.

## Qolgan cheklovlar (baho xabari)

- Oy yig'indisi `bonus_bank_ledger.created_at` bo'yicha (yozilgan oy), `eval_date` bo'yicha emas: o'tgan oy sanasiga baho qo'yilsa xabardagi "shu oy" joriy oyni ko'rsatadi.
- Telegram ID'siz xodim: `employees.user_id` PRIMARY KEY va o'zi Telegram ID; alohida ichki ID yoki bog'lanish maydoni yo'q. Telegram ID'siz xodimni saqlash/baholash mavjud modelda qo'llanmaydi — alohida vazifa. Bloklangan yoki chat topilmagan Telegram foydalanuvchisida baho saqlanadi (nazoratchiga "Xodim botga ulanmagan — baho saqlandi, xabar yuborilmadi."); navbat/qayta yuborish yo'q. "Bog'lanish None" testi faqat yuborishni tashlab o'tish unit testi.
- Parallel bosish: SQLite'da bir nechta thread/ulanish bilan sinalgan (bitta o'zgarish, bitta tarix); PostgreSQL va ko'p worker bilan real sinov o'tkazilmagan (kod PG sintaksisiga mos yozilgan, tekshirilmagan).

## Keyingi qadam

- 2-qadam: hisobni baholash sanasi/oyiga bog'lash (ledger `eval_date` bo'yicha oyga ajratish). Muhammadiy belgilaydi.
