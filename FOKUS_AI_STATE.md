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
- Baho qo'yilgan zahoti xodimga shaxsiy xabar (branch `feature/grade-instant-notice`, PR ochiq, merge qilinmagan): `bos:grade` va `nzr_grade` ikkalasi `record_daily_grade` → `notify_employee_of_grade` orqali ishlaydi. Xabar: sana, baho nomi/ball, shu oy bonus/minus/jami; tuzatishda "✏️ Tuzatildi: 3 → 2"; 22:00–07:00 (kompaniya vaqti) ovozsiz. Bir xil baho takrori ledger/tarix/xabar qo'shmaydi (DBda atomik `claim_daily_evaluation`). Baho tuzatishi (`daily_evaluation`) intizomiy minus sifatida sanalmaydi. Telegram yuborish xatosi bahoni bekor qilmaydi. Targeted test (5 ta fayl): 169 passed; qo'shimcha: dashboard/yopish hisoboti/timezone/scheduler testlari 34 passed. Real E2E va deploy — bajarilmagan.

## Qolgan cheklovlar (baho xabari)

- Oy yig'indisi `bonus_bank_ledger.created_at` bo'yicha (yozilgan oy), `eval_date` bo'yicha emas: o'tgan oy sanasiga baho qo'yilsa xabardagi "shu oy" joriy oyni ko'rsatadi.
- Telegram bog'lanishi: `employees.user_id` — Telegram ID (alohida bog'lanish maydoni yo'q). "Botga ulanmagan" = bot bloklangan yoki chat topilmadi; navbat/qayta yuborish yo'q.
- Parallel bosish: bitta jarayonda va DB darajasida (optimistik `UPDATE ... WHERE grade_key/ball`) himoyalangan; ko'p worker bilan real sinov o'tkazilmagan.

## Keyingi qadam

- 2-qadam: hisobni baholash sanasi/oyiga bog'lash (ledger `eval_date` bo'yicha oyga ajratish). Muhammadiy belgilaydi.
