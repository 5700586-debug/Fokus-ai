# FOKUS AI — joriy holat

Tekshirilgan: 2026-10-19, manba: origin/main HEAD `dd0c492`

Bu fayl faqat tekshirilgan faktlarni saqlaydi. Qarorlar, g'oyalar va qoidalar — `FOKUS_AI_XOTIRA.md` da. Ziddiyat bo'lsa real Git/GitHub/Render holati ustun.

## Joriy holat (git log + faqat MERGE qilingan PR'lar)

- `main` HEAD = `dd0c492` — PR #48 merge'i (baho zahoti xodimga xabar; Muhammadiy: LIVE). Undan oldin #47 (hujjat).
- Kassa: #43 qo'lda yopish (3 rasm, moliyachi tekshiruvi), #44 Asosiy menyu / tozalash / "Qayta yuborish", #45 ochish-yopish soddalashtirildi; #42 kassir menyusi soddalashtirildi.
- Nazoratchi: #37 filial-birinchi kunlik oqim, #38 sodda matnlar, #40 filial yopilganda xodimlar natijalari, #41 oy oxirigacha grafik.
- 2026-10-01..03 oralig'ida kassa va ro'yxat tuzatishlari merge qilingan: #24–#36 (naqd summa o'qish, oldingi qoldiq tasdig'i, yarim tundan keyingi smena, buyurtma ro'yxati oqimlari, ledger xarajatlari, nazoratchidan pul yashirish, rasm tahlili vaqti, qayta boshlash tugmasi).
- Merge qilinmay yopilgan PR: #2 "Release FOKUS AI ! menu simplification" (2026-09-01) — bajarilgan deb hisoblanmaydi.

## Ochiq PR'lar

- #46 — kassa dialog xabarlarini yoshga qarab tozalash + eskirgan `csui_` tugmalar. Holat: ochiq, `MERGEABLE`/`CLEAN`, merge qilinmagan.
- #39 — production read-only smoke E2E (faqat qo'lda ishga tushadi). Holat: ochiq, `MERGEABLE`/`CLEAN`, merge qilinmagan.
- #22 — daftar rasmidan kassa maydonlarini o'qish. Holat: ochiq, `CONFLICTING`/`DIRTY`, merge qilinmagan.
- #49 — oy yig'indisini `eval_date` bo'yicha hisoblash. Holat: ochiq; bu vazifada TEGILMAGAN.
- Saturn nizom katalogi (`feature/saturn-rules-catalog`) — pastga qarang; merge/deploy/production import QILINMAGAN.

## Deploy / Render

- `9ead58b` live, 2026-10-07 (ChatGPT Render tekshiruvi, 2026-10-18).
- Undan keyingi deploy — tekshirilmadi (robotda Render kirish yo'q).

## Bajarilgan ish

- `FOKUS_AI_XOTIRA.md` qo'shildi (PR #47, merge qilingan).
- Baho qo'yilgan zahoti xodimga shaxsiy xabar (branch `feature/grade-instant-notice`, PR ochiq, merge qilinmagan): `bos:grade` va `nzr_grade` ikkalasi `record_daily_grade` → `notify_employee_of_grade` orqali ishlaydi. Baho, tarix, bonus balansi va ledger BITTA DB tranzaksiyasida (`repositories/discipline.py::save_daily_grade`): istalgan yozuv xato bersa hammasi bekor, qayta bosish noldan to'liq ishlaydi; xabar faqat commit'dan keyin. Balans atomik delta bilan (parallel yangilanish yo'qolmaydi). Xabar: sana, baho nomi/ball, shu oy bonus/minus/jami; tuzatishda "✏️ Tuzatildi: 3 → 2"; 22:00–07:00 (kompaniya vaqti) ovozsiz. Bir xil baho takrori ledger/tarix/xabar qo'shmaydi. Baho tuzatishi (`daily_evaluation`) intizomiy minus sifatida sanalmaydi. Telegram yuborish xatosi commit qilingan bahoni bekor qilmaydi. Targeted test (5 ta fayl): 178 passed (rollback testlari haqiqiy DB trigger xatolari bilan, SQLite); qo'shimcha dashboard/yopish hisoboti/timezone/davomat testlari 48 passed. PostgreSQL 16.15 (vaqtincha lokal Docker instance, production adapteri `PgConnection` orqali) `tests/test_discipline_postgres.py`: 14 passed, 5 marta takrorlandi (rollback haqiqiy PG xatolari bilan, alohida ulanishlardan parallel, pool qayta ishlatilishi); instance tozalangan. Ko'p worker (bir nechta jarayon), Supabase/production PG, real E2E va deploy — tekshirilmagan.

## Saturn nizom katalogi (branch `feature/saturn-rules-catalog`, PR ochiq, merge/deploy YO'Q)

- Yagona manba: `content/saturn_rules/source.txt` (asl `SATURN_NIZOM_CHEKLIST_MANBA.txt`, 1026 qator, 63767 bayt, sha256 `e836d6af…c10`) — matnga TEGILMAGAN (imlo/raqam/ball tuzatilmagan, xulosa yo'q). 1–2-qatorlar metadata, `##########` faqat bo'lim chegarasi — qoida/jarima emas.
- Tuzilma (`content/saturn_rules/manifest.json`, manba qatorlari bo'yicha avtomatik hosil bo'ladi, qo'lda matn yo'q): 10 bo'lim, 97 band (madaniyat 14, nizom 26, bonus modeli 1, chek-listlar 56: omborchi 5, kassir 11, tozalik 2, non 4, kolbasa 8, muzlatilgan 7, oshpaz 7, mevachi 12), 88 ball varianti, 17 ta aniqlanmagan band (ro'yxat: `docs/SATURN_RULES_IMPORT_REVIEW.md`; ball avtomatik qo'llanmaydi).
- Rasmiy 1–26 xarita (Muhammadiy tasdiqlagan tartib) faqat `rule_number`/manifestda; bonus modeli 1-band emas; nizom sarlavhalari soni va tartibi tekshiriladi (mos kelmasa import to'xtaydi).
- Sxema: yangi jadval `company_rule_penalty_options` (ko'p natijali bandlar: 26, 17, Mevachi, Omborchi uchun variantlar) va `company_rules`ga additiv `catalog_kind/source_key/source_name`. Katalog bandlari o'rganish (rule learning) oqimiga kirmaydi, xodimlar majburan yozilmaydi.
- Importer: `python -m services.company_rules_import` manifestni yangilaydi; Founder `/nizomimport` (mavjud `ACTION_MANAGE_DISCIPLINE_RULES`) — ko'rik (hech narsa yozmaydi) va "Importni qo'llash" (versiya mosligi shart). Bitta tranzaksiya, idempotent, parallel-xavfsiz; mavjud boshqacha matn/ball ustidan YOZMAYDI (konflikt bo'lsa import bajarilmaydi); start paytida avtomatik ishlamaydi.
- Minus oqimi: nazoratchi erkin matni -> AI butun katalogdan eng ko'pi 3 ta nomzod (xodim lavozimi chek-listi oldin) -> nomzod/"Boshqa band"/"Hech biri (Asoschiga)"/"Qayta yozish" -> variant -> shart/javobgarlik tasdig'i -> yakuniy "Tasdiqlaysizmi?" -> `apply_penalty` BIR marta. Ball server tomonida bazadagi variantdan; AI xato qilsa qo'lda yo'l ishlaydi.
- Tuzatishlar (PR #50 review): (1) AI qidiruviga har bir bandning TO'LIQ asl matni va ball variantlari/shartlari beriladi (240 belgilik kesish olib tashlandi; katalog bo'laklanadi, uzun band yo'qolmaydi; nomzod ≤3, noyob, mavjud). (2) 26-nizom −6/−10 variantlarida manbadagi umumiy shart ("Har qanday shikoyatda ikki tomonning gapi eshitiladi. Minus ball dalil, kamera, guvoh yoki aniq tasdiqlangan holat asosida yoziladi.", `source.txt` 394-qator) yakuniy tasdiqdan OLDIN ko'rsatiladi va alohida tasdiqlanadi; tasdiq FSM holatida xodim+band+variantga bog'langan (variant/xodim almashsa, bekor qilinsa, yangi hodisa boshlansa yoki eskirgan tugma bosilsa qayta talab qilinadi). Bu faqat manifestdagi `gate` ko'rsatkichi (`OPTION_META` 388/390) — nizom matni, ballar va `source.txt` o'zgarmagan. (3) `apply_penalty` endi `repositories/discipline.create_penalty_with_balance` orqali jarima + `salaries.bonus_bank` + `bonus_bank_ledger`ni BITTA tranzaksiyada yozadi (`_apply_bonus_delta` qayta ishlatilgan); istalgan bosqichda xato bo'lsa hammasi bekor. Xodimga xabar faqat commitdan keyin; yuborish xatosi minusni bekor qilmaydi. Yangi jadval/migration yo'q.
- Testlar (targeted, mock OpenAI): SQLite 329 passed (catalog 39, nazoratchi flow 21, UI 8, AI to'liq matn 4, tranzaksiya 6 + mavjud discipline/rule-learning/nazoratchi/close-report/schema/migration). PostgreSQL 16.15 (vaqtincha lokal Docker, `PgConnection`, SKIP emas): `test_saturn_rules_postgres.py` + `test_discipline_postgres.py` 27 passed (jumladan har bir yozish bosqichida haqiqiy trigger xatosi -> hech narsa qisman saqlanmaydi); konteyner o'chirilgan. Mock testlar AI o'zbek tilini tushunishini isbotlamaydi — real AI testi tekshirilmadi; Supabase/production PG, ko'p worker, real E2E tekshirilmadi.
- Production import QILINMAGAN. Deploy'dan keyin: Founder `/nizomimport` ko'rigini ko'radi (konfliktlar bo'lsa Muhammadiy hal qiladi) -> versiya mosligini tasdiqlab "Importni qo'llash" -> `/listnizom`da bo'limlarni tekshiradi -> nazoratchi kartasidan sinov. To'liq import bo'lmaguncha "minus tizimi to'liq ishlaydi" deb hisoblanmaydi.

## Qolgan cheklovlar (baho xabari)

- Oy yig'indisi `bonus_bank_ledger.created_at` bo'yicha (yozilgan oy), `eval_date` bo'yicha emas: o'tgan oy sanasiga baho qo'yilsa xabardagi "shu oy" joriy oyni ko'rsatadi.
- Telegram ID'siz xodim: `employees.user_id` PRIMARY KEY va o'zi Telegram ID; alohida ichki ID yoki bog'lanish maydoni yo'q. Telegram ID'siz xodimni saqlash/baholash mavjud modelda qo'llanmaydi — alohida vazifa. Bloklangan yoki chat topilmagan Telegram foydalanuvchisida baho saqlanadi (nazoratchiga "Xodim botga ulanmagan — baho saqlandi, xabar yuborilmadi."); navbat/qayta yuborish yo'q. "Bog'lanish None" testi faqat yuborishni tashlab o'tish unit testi.
- Parallel bosish: SQLite va lokal PostgreSQL 16.15'da bir nechta thread/ALOHIDA ulanishlar bilan sinalgan (bitta o'zgarish, bitta tarix/ledger; parallel balans delta yo'qolmaydi). Bir nechta bot jarayoni (ko'p worker) va Supabase bilan real sinov o'tkazilmagan. `PgConnection` pool `maxconn=5` — undan ko'p bir vaqtdagi ulanish `PoolError` beradi (mavjud xatti-harakat, bu vazifada o'zgartirilmagan).
- PostgreSQL testi opt-in: `FOKUS_PG_TEST_DSN` o'rnatilmasa 14 ta test SKIP bo'ladi (bu PG tekshiruvi o'tdi degani emas); ishga tushirish buyrug'i fayl boshidagi docstring'da.

## Keyingi qadam

- 2-qadam: hisobni baholash sanasi/oyiga bog'lash (ledger `eval_date` bo'yicha oyga ajratish). Muhammadiy belgilaydi.
