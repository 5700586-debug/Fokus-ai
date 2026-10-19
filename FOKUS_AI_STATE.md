# FOKUS AI — joriy holat

Tekshirilgan: 2026-10-19, manba: main HEAD `d824bfa`

Bu fayl faqat tekshirilgan faktlarni saqlaydi. Qarorlar, g'oyalar va qoidalar — `FOKUS_AI_XOTIRA.md` da. Ziddiyat bo'lsa real Git/GitHub/Render holati ustun.

## Joriy holat (git log + faqat MERGE qilingan PR'lar)

- `main` HEAD = `d824bfa` — PR #49 merge'i (2-qadam: baholar eval_date oyiga); oldin #48 (`dd0c492`), #47 (`ea55eb6`), #45 (`9ead58b`).
- Baholash: #48 — baho qo'yilganda xodimga shaxsiy xabar, baho/tarix/balans/ledger bitta tranzaksiyada (SQLite va lokal PostgreSQL 16.15'da sinalgan).
- Kassa: #43 qo'lda yopish (3 rasm, moliyachi tekshiruvi), #44 Asosiy menyu / tozalash / "Qayta yuborish", #45 ochish-yopish soddalashtirildi; #42 kassir menyusi soddalashtirildi.
- Nazoratchi: #37 filial-birinchi kunlik oqim, #38 sodda matnlar, #40 filial yopilganda xodimlar natijalari, #41 oy oxirigacha grafik.
- 2026-10-01..03 oralig'ida kassa va ro'yxat tuzatishlari merge qilingan: #24–#36 (naqd summa o'qish, oldingi qoldiq tasdig'i, yarim tundan keyingi smena, buyurtma ro'yxati oqimlari, ledger xarajatlari, nazoratchidan pul yashirish, rasm tahlili vaqti, qayta boshlash tugmasi).
- Merge qilinmay yopilgan PR: #2 "Release FOKUS AI ! menu simplification" (2026-09-01) — bajarilgan deb hisoblanmaydi.

## Ochiq PR'lar

- #50 — Saturn nizom katalogi va minus oqimi; ochiq, merge/import qilinmagan (oxirgi ko'rilgan head `0ebda4e`).

- #46 — kassa dialog xabarlarini yoshga qarab tozalash + eskirgan `csui_` tugmalar. Holat: ochiq, `MERGEABLE`/`CLEAN`, merge qilinmagan.
- #39 — production read-only smoke E2E (faqat qo'lda ishga tushadi). Holat: ochiq, `MERGEABLE`/`CLEAN`, merge qilinmagan.
- #22 — daftar rasmidan kassa maydonlarini o'qish. Holat: ochiq, `CONFLICTING`/`DIRTY`, merge qilinmagan.

## Deploy / Render

- `9ead58b` live, 2026-10-07 (ChatGPT Render tekshiruvi, 2026-10-18).
- `dd0c492` (PR #48) — Render plagini orqali LIVE ekani tekshirildi, 2026-10-19; deploy `dep-dbauebgae00c73a5rg00`.
- `d824bfa` (PR #49) — Render LIVE, 2026-10-19; deploy `dep-dbb630rm8hqs73evldf0` tekshirildi. Eski instance SIGTERM bilan to‘xtadi, undan keyingi ko‘rilgan loglarda yangi konflikt yo‘q. PR #50 hali deploy/import qilinmagan.

## Bajarilgan ish

- `FOKUS_AI_XOTIRA.md` qo'shildi (PR #47, merge qilingan).
- PR #48 (merge qilingan, `dd0c492`): baho qo'yilgan zahoti xodimga shaxsiy xabar; `bos:grade` va `nzr_grade` ikkalasi `record_daily_grade` → `notify_employee_of_grade`; baho, tarix, bonus balansi va ledger bitta DB tranzaksiyasida (`save_daily_grade`); bir xil baho takrori yangi yozuv/xabar qo'shmaydi; 22:00–07:00 ovozsiz; PostgreSQL 16.15 (`PgConnection`, vaqtincha lokal Docker) bilan rollback/parallel/pool sinalgan.
- 2-qadam (PR #49 merge qilingan, `d824bfa`, Render LIVE): oylik baho hisobi baho sanasi (`eval_date`) oyiga bog'landi. `get_period_point_totals(user_id, year_month=None)` (berilmasa kompaniyaning joriy oyi; `"YYYY-MM"` validatsiyasi, chegara: boshlanish <= sana < keyingi oy boshlanishi, kompaniya vaqt zonasi) → `discipline_repo.get_month_point_totals`: kunlik baho bonusi kanonik `daily_evaluations` jadvalidan (`eval_date` oyi bo'yicha); ledgerdagi `daily_evaluation` yozuvlari qayta qo'shilmaydi; boshqa bonus/haqiqiy minus/qaytarishlar ledgerdan o'z `created_at` oyi bo'yicha (kompaniya zonasida). Baho xabari: eval_date va o'sha oy yig'indisi; joriy oyda "Shu oy …", oldingi oyda "2026-10 uchun …". "Yulduzlarim" dashboardi joriy oy bahosini ko'rsatadi. Eski oy bahosini keyin tuzatish faqat o'sha oyni o'zgartiradi (soxta minus yo'q, ledger/audit saqlanadi, `get_bonus_ledger_totals_since` o'zgarmagan).
- Testlar: 6 ta fayl (bonus ledger, discipline service, bot flows, employee dashboard, nazoratchi daily flow/supervision) SQLite: 218 passed; PostgreSQL 16.15 (`tests/test_discipline_postgres.py`, `PgConnection`, vaqtincha lokal Docker instance, tozalangan): 23 passed, 3 marta takrorlandi.

## Minus va e'tiroz dialogini tozalash (branch `fix/discipline-dialog-cleanup`, PR ochiq, merge/deploy YO'Q)

- Qoida: avval yangi ekran muvaffaqiyatli ko'rsatiladi, KEYIN shu dialogning ID'si qayd etilgan eski ishchi xabarlari o'chiriladi; yuborish xatosida eskisi saqlanadi; o'chirish/tahrirlash xatosi oqimni yiqitmaydi. Yangi `services/dialog_cleanup.py` — mavjud `chat_cleanup.track` va `bot_workflow_messages` jurnali ustida yupqa qatlam (yangi jadval/scheduler yo'q; `chat_cleanup.py`/`bot_messages.py` o'zgartirilmagan — #46 bilan fayl kesishuvi yo'q). Kalit: `minus:chat:dialog` va `appeal:chat:minus_id`; faqat shu chat+dialog xabarlari o'chadi. Qayta ishga tushgach ommaviy qidirib o'chirish yo'q.
- Nazoratchi (`nazoratchi_bot.py`): "Boshqa holat"/"Qayta yozish" savoli mavjud xabarni tahrirlaydi; sabab xabari (FSM'da `penalty_other_text` saqlangach) va eski ishchi xabar yangi ekran (nomzod/yakuniy tasdiq/"Aniq mos band topilmadi") yuborilgach o'chadi. Natija ("qayd etildi") va "Asoschiga yuborildi" xabari qoladi, qolgan ishchi xabarlar o'chadi. Bekor qilish/yangi hodisa eski bir martalik tasdiq tokenini bekor qiladi (token himoyasi o'zgarmagan).
- E'tiroz (`discipline_bot.py`): minus xabaridagi "E'tirozim bor" tugmasi yuborilgunga qadar saqlanadi, savol alohida xabar; sabab bazaga yozilgach tugma olib tashlanadi, savol + sabab xabari faqat "yuborildi" ko'rsatilib Founderga yetgandan keyin o'chadi (Founderga yetmasa saqlanadi). Faqat o'z minusi va hali e'tiroz berilmagani uchun ruxsat; eski/takroriy tugma yangi e'tiroz yaratmaydi. Founder kartasi qaror chiqquncha qoladi; qarordan keyin karta yangilanadi va tugmalar olinadi, eskirgan karta tugmalari ham olinadi.
- Atomik himoya (`repositories/discipline.py`): `set_penalty_appeal` faqat `none` holatda, `decide_penalty_appeal` faqat `pending` holatda (`rowcount`); parallel/takroriy bosishda ball qaytarish yoki qaror ikki marta bo'lmaydi. Baho, minus, balans, ledger, nizom va apellyatsiya tarixi o'chirilmaydi.
- Testlar: SQLite 377 passed (yangi `tests/test_discipline_dialog_cleanup.py` 13 ta: tartib, yuborish/o'chirish xatosi, boshqa chat/dialog, yakuniy xabar, token, e'tiroz va Founder qarori + mavjud minus/e'tiroz/nizom/close-report regressiyalari). PostgreSQL 16 (vaqtincha lokal Docker, `PgConnection`, SKIP emas): `test_discipline_appeal_postgres.py` + `test_discipline_postgres.py` 26 passed; konteyner o'chirilgan. Real Telegram, production va ko'p worker tekshirilmadi; AI e'tiroz matnini qisqartirish bu vazifaga kirmaydi.
- Cheklovlar: Telegram 48 soatdan eski xabarni o'chirmaydi (jim o'tkaziladi, server tugmani baribir rad etadi); tugallanmagan (tashlab ketilgan) dialog yozuvlari jurnalda qoladi, ommaviy tozalanmaydi; xodimning ovozli sabab xabari ham Founderga yetgach o'chadi (fayl ID bazada saqlanadi).

## Saturn nizom katalogi (branch `feature/saturn-rules-catalog`, PR ochiq, merge/deploy YO'Q)

- Yagona manba: `content/saturn_rules/source.txt` (asl `SATURN_NIZOM_CHEKLIST_MANBA.txt`, 1026 qator, 63767 bayt, sha256 `e836d6af…c10`) — matnga TEGILMAGAN (imlo/raqam/ball tuzatilmagan, xulosa yo'q). 1–2-qatorlar metadata, `##########` faqat bo'lim chegarasi — qoida/jarima emas.
- Tuzilma (`content/saturn_rules/manifest.json`, manba qatorlari bo'yicha avtomatik hosil bo'ladi, qo'lda matn yo'q): 10 bo'lim, 97 band (madaniyat 14, nizom 26, bonus modeli 1, chek-listlar 56: omborchi 5, kassir 11, tozalik 2, non 4, kolbasa 8, muzlatilgan 7, oshpaz 7, mevachi 12), 88 ball varianti, 17 ta aniqlanmagan band (ro'yxat: `docs/SATURN_RULES_IMPORT_REVIEW.md`; ball avtomatik qo'llanmaydi).
- Rasmiy 1–26 xarita (Muhammadiy tasdiqlagan tartib) faqat `rule_number`/manifestda; bonus modeli 1-band emas; nizom sarlavhalari soni va tartibi tekshiriladi (mos kelmasa import to'xtaydi).
- Sxema: yangi jadval `company_rule_penalty_options` (ko'p natijali bandlar: 26, 17, Mevachi, Omborchi uchun variantlar) va `company_rules`ga additiv `catalog_kind/source_key/source_name`. Rasmiy 26 ta nizom mavjud o'rganish oqimiga kiradi; madaniyat/bonus modeli/lavozim chek-listlari majburiy o'qitishga qo'shilmaydi; enrollment va snapshotlar o'zgartirilmaydi.
- Importer: `python -m services.company_rules_import` manifestni yangilaydi; Founder `/nizomimport` (mavjud `ACTION_MANAGE_DISCIPLINE_RULES`) — ko'rik (hech narsa yozmaydi) va "Importni qo'llash" (versiya mosligi shart). Bitta tranzaksiya, idempotent, parallel-xavfsiz; mavjud boshqacha matn/ball ustidan YOZMAYDI (konflikt bo'lsa import bajarilmaydi); start paytida avtomatik ishlamaydi.
- Minus oqimi (soddalashtirilgan, Muhammadiy qarori): nazoratchi xodimni tanlab sababni yozadi (bot qayta tergov qilmaydi) -> AI butun katalogdan band VA variant id'sini taklif qiladi (ball/shart/iqtibos bazadan) -> band va variant bitta aniq bo'lsa darhol BITTA yakuniy ekran (xodim, manba+sarlavha, iqtibos, ball, majburiy shart/javobgarlik; tugmalar: Tasdiqlash / Boshqa band / Bekor qilish) -> tasdiqdan keyingina minus saqlanadi va xodimga xabar ketadi. Band yoki variant ajratilmasa — eng ko'pi 3 tanlov (bitta qisqa savol), tanlovdan keyin yakuniy ekran. Mos band yo'q: "Aniq mos band topilmadi" + Qayta yozish / Boshqa band / Asoschiga yuborish. Miqdorsiz bandga minus yozilmaydi, umumiy −10 zaxirasi yo'q. Variantni AI aniq va shu bandga tegishli ko'rsatmasa taxmin qilinmaydi (server tekshiradi). Yakuniy tasdiq tugmasi har ekran uchun yangi tasodifiy bir martalik tokenga ega (`nzr_pa:xodim:band:variant:token`, ≤64 bayt); token FSM'da joriy hodisa+xodim+band+variant bilan saqlanadi, ekran muvaffaqiyatli ko'rsatilgachgina ochiladi va yangi hodisa/qayta yozish/boshqa xodim-band-variant/"Boshqa band"/bekor qilish/ishlatilish bilan o'chadi. Tokensiz, noto'g'ri yoki eski formatdagi tugma minus yozmaydi ("Bu tasdiq eskirgan"). Alohida "shart" (gate) oynasi YO'Q.
- Tuzatishlar (PR #50 review): (1) AI qidiruviga har bir bandning TO'LIQ asl matni va ball variantlari/shartlari beriladi (240 belgilik kesish olib tashlandi; katalog bo'laklanadi, uzun band yo'qolmaydi; nomzod ≤3, noyob, mavjud). (2) 26-nizom −6/−10 variantlarida manbadagi umumiy shart ("Har qanday shikoyatda ikki tomonning gapi eshitiladi. Minus ball dalil, kamera, guvoh yoki aniq tasdiqlangan holat asosida yoziladi.", `source.txt` 394-qator) YAKUNIY TASDIQ ekranida ko'rsatiladi (alohida oyna yo'q); tugma: "Shartlar bajarilganini tasdiqlayman va minusni qo'llayman" (boshqa bandlarning majburiy shartlari/javobgarligi ham shu ekranda). Tasdiq FSM holatida xodim+band+variantga bog'langan. Bu faqat manifestdagi `gate` ko'rsatkichi (`OPTION_META` 388/390) — nizom matni, ballar va `source.txt` o'zgarmagan. (3) `apply_penalty` endi `repositories/discipline.create_penalty_with_balance` orqali jarima + `salaries.bonus_bank` + `bonus_bank_ledger`ni BITTA tranzaksiyada yozadi (`_apply_bonus_delta` qayta ishlatilgan); istalgan bosqichda xato bo'lsa hammasi bekor. Xodimga xabar faqat commitdan keyin; yuborish xatosi minusni bekor qilmaydi. Yangi jadval/migration yo'q.
- Testlar (targeted, mock OpenAI): SQLite 319 passed targeted to'plamda (catalog 39, nazoratchi flow 33 (token testlari qo'shilgan), UI 8, AI to'liq matn/variant 6, tranzaksiya 6 + mavjud discipline/rule-learning/nazoratchi/close-report/schema/migration). PostgreSQL 16.15 (vaqtincha lokal Docker, `PgConnection`, SKIP emas): `test_saturn_rules_postgres.py` + `test_discipline_postgres.py` 27 passed (jumladan har bir yozish bosqichida haqiqiy trigger xatosi -> hech narsa qisman saqlanmaydi); konteyner o'chirilgan (PG testlari oldingi commitda; bu o'zgarishda DB qatlamiga tegilmadi, PG qayta ishga tushirilmadi). Mock testlar AI o'zbek tilini tushunishini isbotlamaydi — real AI testi tekshirilmadi; Supabase/production PG, ko'p worker, real E2E tekshirilmadi.
- Production import QILINMAGAN. Deploy'dan keyin: Founder `/nizomimport` ko'rigini ko'radi (konfliktlar bo'lsa Muhammadiy hal qiladi) -> versiya mosligini tasdiqlab "Importni qo'llash" -> `/listnizom`da bo'limlarni tekshiradi -> nazoratchi kartasidan sinov. To'liq import bo'lmaguncha "minus tizimi to'liq ishlaydi" deb hisoblanmaydi.

## Birlashtirish tekshiruvi (2026-10-20, Asia/Tashkent)

- PR #49 main (`d824bfa`) PR #50 branchiga birlashtirildi; konflikt faqat STATE hujjatida edi. Baholarning eval_date oyi hisobi va Saturn minus oqimi saqlandi.
- Mustaqil targeted SQLite tekshiruvi: 10 fayl, 298 passed, 0 failed (katalog/import, bot UI, nazoratchi katalog/tasdiq tokeni, AI to‘liq matn/variant, minus tranzaksiyasi, baho service/bot/ledger/dashboard va nazoratchi regressiyalari). Real Telegram/OpenAI chaqirilmagan; production DB ulanmagan. Lokal test muhiti uchun socksio o‘rnatildi; repo dependency fayllari o‘zgarmadi.
- Lokal PostgreSQL qayta ishlatilmadi; oldingi robot natijalari yuqorida, bu mustaqil PG tasdig‘i emas.

## Qolgan cheklovlar

- Yopilgan/to'langan oy uchun qulf yo'q: keyin kiritilgan eski oy bahosi yoki tuzatishi o'sha oy yig'indisini o'zgartiradi. Ushbu PR qulf qurmaydi; kelajakdagi 4-qadam (qog'ozdan kiritish) faqat joriy oy bilan cheklanishi kerak.
- 1-qadamdagi shaxsiy xabar va 3→2 tuzatish real Telegram akkauntida sinalgani hali tasdiqlanmagan; avtomatik testlar bu operator tekshiruvini almashtirmaydi.

- Tarixiy ledger-only `daily_evaluation` yozuvlari (`daily_evaluations` qatori bo'lmagan) oylik hisobga kirmaydi va taxmin bilan bahoga aylantirilmagan; production'da bunday yozuvlar bor-yo'qligi tekshirilmagan.
- Boshqa bonus/minus yozuvlari o'z yozilgan oyiga tushadi (sanasi `eval_date`ga ko'chirilmagan): masalan o'tgan oy sanasiga qo'yilgan jarima yozilgan oyda minus bo'ladi.
- Telegram ID'siz xodim: `employees.user_id` PRIMARY KEY va o'zi Telegram ID; Telegram ID'siz xodimni saqlash/baholash mavjud modelda qo'llanmaydi — alohida vazifa. Bloklangan yoki chat topilmagan foydalanuvchida baho saqlanadi (nazoratchiga "Xodim botga ulanmagan — baho saqlandi, xabar yuborilmadi.").
- Ko'p worker (bir nechta bot jarayoni) va Supabase/production PostgreSQL bilan sinov o'tkazilmagan. `PgConnection` pool `maxconn=5`.
- PostgreSQL testi opt-in: `FOKUS_PG_TEST_DSN` o'rnatilmasa 23 ta test SKIP bo'ladi (bu PG PASS emas).
- Real Telegram E2E va deploy — bajarilmagan.

## Keyingi qadam

- 3-qadam: xodimning kunma-kun "Oylik baholarim" oynasi. Muhammadiy belgilaydi.

## Production import tasdiq xatosi (2026-10-20, Asia/Tashkent)

- Main `b6d106f` (PR #50) Render LIVE; keyin `PYTHONUNBUFFERED=1` Render sozlamasi yoqildi, xatolar endi stdout'da darhol ko'rinadi.
- Founder import tugmasini bosganda umumiy xato ko'rindi. Render logidagi aniq sabab: TelegramBadRequest — query is too old / response timeout expired. Eski handler import tugagandan KEYIN callback.answer chaqirgan. Import commit qilingan bo'lishi mumkin; production katalog sonlari mustaqil tekshirilmagan, takroriy import idempotent.
- Fix: callback avval javoblanadi; dry-run va apply asyncio.to_thread orqali event loop'dan tashqarida ishlaydi; yakuniy natija edit_text bilan beriladi. Muddat o'tgan callback javobi importning final hisobotini to'xtatmaydi; versiya/ruxsat/konflikt/idempotent tranzaksiya himoyalari saqlangan.
- Mustaqil targeted SQLite: 55 passed (import UI, catalog va minus tranzaksiya regressiyalari; callback javobi DB ishidan oldin, DB boshqa threadda, expired callbackdan keyin ham yakuniy hisobot tekshirildi). Real Telegram xabari yoki production DB yozuvi bu testlarda yo'q.
- Keyingi amal: deploydan keyin Founder /nizomimport ko'rigida haqiqiy 97 band / 88 variant holatini tekshiradi; konflikt bo'lsa ustidan yozilmaydi.
