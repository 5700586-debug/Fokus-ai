# Fokus AI — Arxitektura

Bu hujjat kodning **hozirgi haqiqiy holatini** tasvirlaydi (2026-08 audit
asosida yangilangan). Yangi narsa qo'shishdan oldin shu yerni o'qing —
"qayerga qo'shish kerak" bo'limi eng muhim.

## 1. Yuqori darajadagi ko'rinish

```
Telegram (long polling)
        |
        v
   main.py  --- Dispatcher (aiogram 3.x), global error handler
        |
        +--> onboarding.py, approval.py        (ro'yxatdan o'tish)
        +--> performance_bot.py                (KPI/reyting/mashina)
        +--> cash_shift_bot.py                 (kassa smenasi)
        +--> inventory_bot.py                  (ombor snapshot/tafovut)
        +--> calibration_bot.py                (yangi xodim adaptatsiyasi)
        +--> discipline_bot.py                 (BOS: baho/jarima/apellyatsiya)
        |
        v
   services/*.py   <-- biznes mantiq (bu yerda handler yo'q, Telegram bilmaydi)
        |
        v
   repositories/*.py  <-- xom SQL (faqat shu qatlamda SQL yoziladi)
        |
        v
   db.py -> (SQLite | db_postgres.py) -> fokus.db yoki Supabase Postgres

Alohida: config.py (env o'qish), roles.py (kim qanday rolda),
providers/*.py (SMS/ob-havo/vision — hozircha barchasi stub),
health_server.py (Render uchun HTTP port), company_time.py (TZ helper).
```

**Muhim invariant:** `main.py`ning eng boshida `load_dotenv()` va
`init_db()` boshqa har qanday loyiha modulidan OLDIN chaqiriladi —
aks holda `.env` o'qilmaydi yoki hali yaratilmagan jadvalga so'rov ketadi
(qarang `main.py`dagi izoh).

## 2. Qatlamlar va mas'uliyat

| Qatlam | Fayllar | Nima qiladi | Nima qilmasligi kerak |
|---|---|---|---|
| Bot/handler | `*_bot.py`, `onboarding.py`, `approval.py`, `main.py` | Telegram xabar/callback qabul qilish, klaviatura chiqarish, FSM holatini boshqarish | To'g'ridan-to'g'ri SQL, murakkab hisob-kitob |
| Biznes mantiq | `services/*.py` | Qoidalar, hisob-kitoblar (ball, bonus, jarima, tafovut), tashqi servis (OpenAI) chaqiruvi | Telegram obyektlarini bilish (`Message`, `CallbackQuery`) |
| Ma'lumot | `repositories/*.py` | Xom SQL (parametrli query), CRUD | Biznes qoida (masalan "jarima qaysi miqdorlar bilan bo'lishi mumkin" — bu `services/discipline.py`da) |
| Sxema | `schema/*.py` | `CREATE TABLE IF NOT EXISTS ...` + boshlang'ich `INSERT OR IGNORE` seed qatorlar | — |
| Konfiguratsiya | `config.py`, `.env` | Barcha muhit o'zgaruvchilarini o'qish | Hardcoded qiymat (Founder ID kabi) |
| Provider | `providers/*.py` | Tashqi servislarga (SMS/ob-havo/OCR) abstraksiya — hozircha hammasi `Null*` stub | — |

Bu chegaralar **audit qilingan va asosan to'g'ri saqlanadi** — yagona
istisno: `employees.py` va `roles.py` (loyihaning eng eski qismlari)
`repositories/`dan oldin yozilgan va o'zlarida xom SQL saqlaydi. Ular
ishlaydi va testlangan — qayta yozish rejalashtirilmagan, lekin **yangi**
DB so'rovlari doim `repositories/`ga qo'shiladi, bu ikki eski faylga emas.

## 3. Ma'lumotlar bazasi

- **Dev/lokal:** SQLite, `fokus.db` (yo'li `FOKUS_DATA_DIR` orqali
  sozlanadi, standart — loyiha papkasi).
- **Prod (Render):** PostgreSQL (Supabase), `DATABASE_URL` orqali.
  Backend tanlovi `db.py`da: `DATABASE_URL` bo'lsa Postgres, bo'lmasa
  SQLite — chaqiruvchi kod (`repositories/*.py`) buni bilmaydi.
- `db_postgres.py` — Postgres ustida sqlite3'ga o'xshash interfeys
  (`conn.execute(...).fetchone()/fetchall()`, `row["col"]`,
  `cursor.lastrowid`). SQLite-only naqshlarni (`INSERT OR IGNORE`,
  `AUTOINCREMENT`, `?` placeholder, `IS ?`) Postgres ekvivalentiga
  tarjima qiladi — **umumiy SQL parser emas**, faqat haqiqatda
  ishlatiladigan naqshlar. Yangi SQL naqshi qo'shilsa, shu fayldagi
  tarjima qoidalari ham tekshirilishi/yangilanishi kerak.
- Har ikki backend ham CI'da haqiqiy ishga tushiriladi (qarang
  `.github/workflows/tests.yml` — SQLite va real `postgres:16-alpine`
  konteyner bilan to'liq test to'plami).

## 4. Vaqt zonasi

Barcha "bugungi kun" hisob-kitoblari `company_time.py` (yoki
`calibration_bot.py`/`discipline_bot.py`ning o'z `_resolve_timezone()`
nusxasi) orqali `COMPANY_TIMEZONE` (standart: `Asia/Tashkent`, UTC+5)
bo'yicha olinadi — server (Render, UTC) soatiga emas. Bu 2026-08
auditida topilgan va tuzatilgan sistemali xato edi (server UTC'da,
19:00-23:59 oralig'ida Toshkentda allaqachon ertangi kun edi).

**Qoida:** yangi kod hech qachon `datetime.now()` yoki `date.today()`ni
to'g'ridan-to'g'ri "bugungi biznes kuni" sifatida ishlatmasin — doim
`company_time.today()`/`company_time.now()` (yoki mavjud bot faylidagi
`_resolve_timezone()`) orqali.

## 5. Telegram <-> Render <-> Supabase <-> OpenAI aloqasi

- **Telegram:** long polling (`dp.start_polling(bot)`), webhook EMAS.
- **Render:** Free tarifda faqat "Web Service" mavjud (Background
  Worker pullik), va Web Service `$PORT`ga bog'lanishni kutadi — aks
  holda deploy "Timed out"/"No open ports detected" bo'ladi. Shuning
  uchun `health_server.py` polling bilan bir vaqtda ahamiyatsiz HTTP
  server ochadi (`GET /` -> `200 OK`). Bot HTTP so'rov qabul qilmaydi —
  bu faqat Render health-check uchun.
- **Supabase:** faqat `DATABASE_URL` orqali (Postgres protokoli,
  `psycopg2-binary`). Session Pooler manzili tavsiya etiladi (Render
  kabi ko'p-qisqa-connection muhitlar uchun).
- **OpenAI:** `openai_client` (`AsyncOpenAI`) `main.py`da yaratiladi va
  handler modullariga (`discipline_bot.register(dp, openai_client)`
  kabi) parametr sifatida uzatiladi — global emas. Har bir AI
  chaqiruvi `try/except` bilan o'ralgan va xato bo'lsa oddiy fallback
  matn bilan davom etadi (hech qachon botni yiqitmaydi).

## 5.1. Test va production muhitini ajratish (2026-08)

`config.ENVIRONMENT` ("production" standart, yoki "test") — butun
tizimning yagona manba nuqtasi:

- `main.py`: `ENVIRONMENT=test` bo'lsa `TEST_BOT_TOKEN` o'qiladi,
  `BOT_TOKEN` emas (ikkisi BUTUNLAY BOSHQA nomli o'zgaruvchi).
- `db.py`: xuddi shunday `TEST_DATABASE_URL` (yoki topilmasa alohida
  `fokus_test.db`) vs `DATABASE_URL`/`fokus.db`.
- `roles.py`: `db._DATABASE_URL`dan (mustaqil qayta hisoblamaydi —
  oldin shunday edi, ikkisi divergensiya xavfi bor edi) va
  `allowed_users_test.json` vs `allowed_users.json`.

Bu ikkisi bir xil `.env`da yoki bir xil Render loyihasida tursa ham,
o'zgaruvchi NOMI boshqa bo'lgani uchun bitta jarayon ikkinchisiga
tasodifan ulanib qololmaydi (qo'lda ehtiyotkorlikka tayanmaydigan
strukturaviy himoya). To'liq sozlash: `DEPLOYMENT.md` §4.

## 5.2. Eski FSM holatidan xavfsiz chiqish + yagona menyu (2026-08)

**Muammo edi:** foydalanuvchi ko'p-bosqichli oqimda (masalan BOS jarima
uchun nizom raqami kutilayotgan holatda) "qotib qolsa", keyingi
buyruq (`/start` yoki boshqasi) eski `StateFilter`ga tayanadigan
handler tomonidan "matn kiritish" deb noto'g'ri yutib olinardi.

**Yechim:** `main.py`dagi `_ClearStaleStateMiddleware`,
`dp.update.outer_middleware(...)` orqali ro'yxatdan o'tadi (BU MUHIM —
`dp.message.outer_middleware` YETARLI EMAS, chunki u faqat filtr
ALLAQACHON handlerni tanlagandan keyin ishga tushadi, ya'ni kech
qoladi). Har bir kelayotgan xabar matn "/" bilan boshlansa yoki
"❌ Bekor qilish"/"🔙 Orqaga" bo'lsa, boshqa hech qanday handler
tekshirilishidan OLDIN foydalanuvchining FSM holati tozalanadi (va
`StateFilter`ning keshlangan `raw_state` qiymati ham yangilanadi —
aks holda kesh eski qiymatni ko'rsatib qolardi).

**Yagona menyu:** `build_menu(role_key)` — har bir foydalanuvchiga
FAQAT o'z roliga tegishli bo'lim (masalan kassirga "💰 Kassa",
nazoratchiga "🧑‍💼 Nazoratchi") + umumiy "⭐ Mening natijalarim" +
"⚙️ Sozlamalar" ko'rsatadi (erkin/umumiy AI-chat menyusi yo'q — AI
faqat aniq belgilangan ichki vazifalarda, masalan recruiting va
intizom oqimlarida, ishlatiladi). Bo'lim ichidagi tugmalar
mavjud buyruqning O'ZI (masalan "/openshift — Kassa smenasini ochish")
— bosilganda aynan shu buyruqning o'zgartirilmagan handleri ishga
tushadi, hech qanday yangi biznes mantiq yozilmagan, faqat
navigatsiya. "🔙 Orqaga" asosiy menyuga qaytaradi, "❌ Bekor qilish"
esa (middleware bilan birga) istalgan qotib qolgan oqimni bekor qilib,
asosiy menyuga qaytaradi.

## 6. Yangi funksiya qayerga qo'shiladi

1. Yangi jadval kerak bo'lsa: `schema/<mavzu>.py` (`CREATE TABLE IF NOT
   EXISTS` + kerak bo'lsa seed `INSERT OR IGNORE`), `schema/__init__.py`
   ro'yxatiga qo'sh.
2. Xom SQL: `repositories/<mavzu>.py` — parametrli query, `?`
   placeholder (Postgres tarjimasi avtomatik).
3. Biznes qoida/hisob-kitob: `services/<mavzu>.py` — Telegram
   obyektlarisiz, mustaqil test qilinadigan sof funksiyalar.
4. Threshold/sana/miqdor kabi sozlanishi kerak bo'lgan qiymatlar:
   hardcode qilinmasin — `services/rules.py` + `rules` jadvali orqali
   (Founder `/setrule` bilan o'zgartiradi).
5. Telegram interfeysi: yangi `<mavzu>_bot.py` (yoki mavjud modulga
   qo'shimcha `register()` ichida) — faqat chaqiruv, hisoblamaydi.
6. Ruxsat: yangi amal bo'lsa `services/permissions.py`ga
   `ACTION_*` qo'sh va tegishli rolga biriktir.
7. `main.py`da import qil va `register(dp)` chaqir (kerak bo'lsa
   scheduler ham `start_scheduler`/`shutdown` bilan).
8. Test yoz: `tests/test_<mavzu>_service.py` (biznes mantiq) va
   `tests/test_<mavzu>_bot_flows.py` (Telegram oqimi, `bot_dp` fixture).
9. `docs/FEATURE_STATUS.md` va kerak bo'lsa `docs/BUSINESS_RULES.md`ni
   yangila.

## 6.1. Ruxsat tekshiruvi — markazlashtirilgan (2026-08, RBAC refaktori)

Ilgari uch xil uslub aralash ishlatilgan edi: `id == FOUNDER_ID`
(to'g'ridan-to'g'ri), `roles.is_authorized`/`get_role` ("har qanday
ro'yxatdan o'tgan foydalanuvchi"), `services/permissions.has_permission`
(granular amal-asosli). Endi barcha buyruq/callback handlerlar
(main.py, approval.py, discipline_bot.py, performance_bot.py,
saturn_group_bot.py, supplier_chat_bot.py, cash_shift_bot.py,
inventory_bot.py) `services/permissions.py` orqali ruxsat tekshiradi —
hech qayerda to'g'ridan-to'g'ri `id != FOUNDER_ID` bilan qaror
qilinmaydi. Ikki daraja qoladi (ataylab, ikkalasi ham markazlashgan):

- **Amal-asosli** (`has_permission()`/`ensure_permission()`): har bir
  buyruq/callback bitta `ACTION_*`ga bog'langan, `ROLE_PERMISSIONS`
  qaysi rol qaysi amalga ruxsatli ekanini belgilaydi. Sof Founder-only
  buyruqlar (masalan `/setrule`, `/invite`) ham oddiy `ACTION_*`
  sifatida ro'yxatlangan — ularga hech qanday rol biriktirilmagani
  uchun faqat Founder bypass orqali ishlaydi. Noma'lum/bo'sh/o'chirilgan
  rol va ro'yxatga kiritilmagan amal — DEFAULT-DENY (`has_permission()`
  docstringi).
- **"Har qanday ro'yxatdan o'tgan foydalanuvchi"** (`roles.is_authorized`):
  asosiy menyu, `/mystars`, `/apellyatsiya` kabi rol farqi bo'lmagan
  komandalar uchun — bu ataylab alohida, chunki amal-jadvali kerak emas.

Ikki komanda (`/cashsummary`, `/inventorysummary`) "o'zining resursi
har doim ruxsatli, boshqasiniki uchun ikkinchi amal kerak" tarzida
filiallanadi — bular uchun `has_any_permission()` (OR-kompozit
tekshiruv) ishlatiladi, `ensure_permission()` emas (filiallanish
handler ichida davom etadi).

**Ruxsatsiz urinishga javob endi jim EMAS** (2026-08 yangilanishi):
avval hech narsa yuborilmasdi, endi `ensure_permission()`/
`ensure_any_permission()`/`deny()` markaziy "Saturncha" xabar
katalogidan (`services/messages.py`) qisqa, hazilkash javob ko'rsatadi
— xabar handlerlariga oddiy javob, callback handlerlariga toast
(`show_alert=False`). Buning sababi: ruxsatli tugmalar ENDI umuman
ko'rsatilmaydi (pastga qarang, `main.py` menyusi), shuning uchun bu
javob faqat eski (keshlangan) tugma/callback/deep-link/qo'lda yozilgan
buyruq orqali kirishga urinishda ko'rinadi.

## 6.2. Ruxsat va ma'lumot chegarasi — ataylab ajratilgan (2026-08)

`has_permission()` (amalni bajarish huquqi) va `can_access_branch()`
(filial ma'lumot chegarasi) MUSTAQIL tekshiruvlar — birining ruxsati
ikkinchisini avtomatik bermaydi. Founder va filiallararo rollar
(`moliyachi`, `nazoratchi`) istalgan filialni ko'radi; boshqa har
qanday rol faqat o'z profilidagi (`employees.get_profile()['branch']`)
filialga tegishli ma'lumotni so'rashi mumkin. Hozircha faqat
`inventory_bot.py`da (`/inventorysummary <filial>`) real hodisa sifatida
ulangan — filial argumenti bilan chaqirilganda amal ruxsati (yuqorida)
VA `can_access_branch()` ikkalasi ham tekshiriladi, ikkinchisi rad
etsa `services/audit.EVENT_CROSS_BRANCH_ATTEMPT` yoziladi. Boshqa
funksiyalarda (masalan `/mealplan`) filial tushunchasi umuman yo'q
(kompaniya bo'yicha umumiy) — ularga sun'iy filial-cheklov qo'shilmadi.

## 6.3. Xavfsizlik audit jurnali (2026-08, `services/audit.py`)

`security_audit_log` jadvali (`schema/audit.py`) — rol berish/
almashtirish, nazoratchi tayinlashga urinish (muvaffaqiyatli va rad
etilgan), foydalanuvchini ro'yxatdan o'chirish, filiallararo kirishga
urinish va Founder-only amalga (ro'yxatdan o'tgan, lekin Founder
bo'lmagan foydalanuvchi tomonidan) ruxsatsiz urinish shu yerga yoziladi
(`roles.set_role()`/`remove_user()`, `services/permissions.deny()`/
`log_cross_branch_attempt()`). Oddiy operatsion amalning tasodifiy rad
etilishi (masalan begona xato buyruq yozsa) AUDIT QILINMAYDI — faqat
ro'yxatdan o'tgan-lekin-Founder-bo'lmagan foydalanuvchi + Founder-only
amal birikmasida (audit hajmi shishmasin uchun). Token/parol/`.env`
qiymati bu jurnalga hech qachon yozilmaydi. Audit yozuvi ikkinchi
darajali amal — DB xatosi asosiy handler oqimini to'xtatmaydi (print +
davom etish, mavjud loyiha konvensiyasi).

## 6.4. `nazoratchi=1` — endi DB darajasida ham kafolatlangan (2026-08)

Ilgari faqat `roles.set_role()`dagi Python check-then-act (`find_user_by_role`
+ `if existing: return False`) himoya qilardi — bu ikki JARAYON (masalan
deploy paytida eski+yangi instance bir vaqtda ishlab qolsa) deyarli bir
vaqtda tekshirsa, ikkalasi ham "bo'sh" deb topib, ikkalasi ham yozib
qo'yishi mumkin edi (race condition; bitta jarayon ichida esa xavf yo'q,
chunki `set_role()` sinxron va `await` nuqtasisiz ishlaydi). Endi
`schema/core.py`da qisman UNIQUE indeks (`idx_allowed_users_single_slot_role`,
`allowed_users(role_key) WHERE role_key IN ('nazoratchi','haydovchi',
'taminotchi','moliyachi')`) — barcha 4 ta single-slot rol uchun — DB
darajasida, atomik ravishda ikkinchi yozuvni rad etadi.
`roles.set_role()` bu holatni (`db.IntegrityError`) ushlab xotiradagi
keshni buzmasdan `False` qaytaradi va `services/audit.py`ga yozadi.
**Cheklov:** bu himoya faqat `allowed_users` HAQIQIY DB jadvali
ishlatilganda (production — `DATABASE_URL`/Postgres) amal qiladi; lokal
SQLite-fayl rejimida (odatiy dev, `DATABASE_URL` yo'q) rollar
`allowed_users.json` faylida saqlanadi va bu fayl yozuvi atomik emas —
production yagona haqiqiy ko'p-jarayonli muhit bo'lgani uchun bu
qabul qilingan cheklov.

## 6.5. Saturn kunlik rasmli salom — RESERVE-FIRST idempotency (2026-08)

`services/saturn_group.py`dagi `send_morning_image_message`/
`send_night_image_message` (2026-08, `feature/saturn-daily-greetings`)
`services/notifications.send_once()`dan farqli, KUCHLIROQ idempotency
naqshidan foydalanadi: `try_reserve(job_key, target)` — atomik
`INSERT OR IGNORE ... status='pending'` — AI/ob-havo/rasm generatsiyasi
kabi QIMMAT (`await`li) ishlardan OLDIN chaqiriladi, keyin `mark_sent()`
(muvaffaqiyatli) yoki `release_reservation()` (xato — keyingi urinishga
ochiq qoldiradi).

Bu farq muhim: `send_once()`da tekshiruv ("yuborilganmi?") va yuborish
orasida `await` yo'q edi (matn tayyor holda keladi), shuning uchun
race deyarli imkonsiz edi. Rasmli xabarda esa tekshiruv bilan haqiqiy
yuborish orasida bir nechta `await` nuqtasi bor (AI chaqiruvi, ob-havo
so'rovi, rasm chizish) — shu oraliqda ikkinchi parallel chaqiruv
(masalan qayta-tushgan scheduler tick'i) ham "hali yuborilmagan" deb
ko'rishi va ikkalasi ham yuborib yuborishi mumkin edi. RESERVE-FIRST
buni yopadi: ikkinchi chaqiruv `try_reserve()`dan `False` oladi va
darhol to'xtaydi, qimmat ishni umuman boshlamaydi.

Rasm generatsiyasi (`services/saturn_image.py`, Pillow) butunlay
xotirada (`io.BytesIO`) — vaqtinchalik faylga yozish/tozalash shart
emas, aiogram `BufferedInputFile` orqali to'g'ridan-to'g'ri baytlardan
yuboradi. Matn AI-generatsiya qilingan rasmning ichiga yozdirilmaydi —
sarlavha/maslahat/ob-havo/logotip hammasi dastur orqali (`ImageDraw`)
aniq koordinatada chiziladi, shuning uchun imlo/logotip buzilish xavfi
yo'q. Maslahat matni (`services/saturn_content.py`) qo'lda yozilgan,
tekshirilgan banklardan (35 tonggi + 31 tungi) keladi — AI faqat
TANLANGAN matnni ixtiyoriy ravishda qayta ifodalaydi (yangi mavzu
o'ylab topmaydi), natija uzunlik bo'yicha tekshiriladi, mos kelmasa
original bank matni ishlatiladi.

## 7. Bilingan cheklovlar (qasddan tuzatilmagan)

Bular audit paytida topildi, lekin hozircha **ataylab** tegilmagan —
sabab har birida yozilgan. Kelajakda qo'l urishdan oldin shu ro'yxatni
o'qing:

- **Ikki mustaqil xodim-baholash tizimi:** `services/star_engine.py`
  (oylik "to'liq bonus" -> yulduz) va yangi BOS (`services/discipline.py`,
  kunlik ball/jarima banki) bir-biridan bexabar ishlaydi — biri
  ikkinchisiga ta'sir qilmaydi. Bu ataylab shundayligi yoki ular
  birlashtirilishi kerakligi biznes qarori — `docs/BUSINESS_RULES.md`da
  `NEEDS_BUSINESS_DECISION` deb belgilangan.
- **Bitta nazoratchi — Founder qarori bilan tasdiqlangan (2026-08).**
  Kompaniyada bu yil faqat bitta nazoratchi ishlaydi va Founder buni
  ataylab shunday qoldirishga qaror qildi — ko'p-nazoratchi
  funksionalligi HOZIR qurilmaydi (database, murakkab vakolat,
  yangi funksiya yaratilmadi). Amaldagi himoya (allaqachon mavjud,
  testlangan):
  - Nazoratchini FAQAT Founder tayinlaydi — `/setrole` (`main.py`,
    `ACTION_MANAGE_ROLES`) va `/invite` -> onboarding approve
    (`approval.py`, `ACTION_APPROVE_APPLICANT`) ikkalasi ham
    `services/permissions.py` orqali Founderdan boshqa hech kimga
    ochilmagan (qarang yuqoridagi "Ruxsat tekshiruvi markazlashtirilgan").
  - `roles.py`dagi `SINGLE_SLOT_ROLES` ro'yxatida `"nazoratchi"` bor —
    `roles.set_role()`ning o'zi (Telegram qatlamidan mustaqil,
    ikkinchi himoya qatlami) ikkinchi nazoratchi tayinlanishini rad
    etadi, mavjudini almashtirmaydi. **2026-08:** endi UCHINCHI qatlam
    ham bor — DB darajasidagi qisman UNIQUE indeks, qarang §6.4 (ikki
    JARAYON bir vaqtda tekshirib ulgurgan race holatini ham yopadi,
    Python-qatlam buni ko'ra olmaydi).
  - `/kunniyop`dagi "baholangan xodimlar soni" barcha nazoratchilar
    bo'yicha umumiy hisoblanadi (bittaga filtrlanmagan) — bitta
    nazoratchi bilan bu to'g'ri ishlaydi, muammo yo'q.
  - Test bilan qulflangan: `tests/test_bot_flows.py::test_only_founder_can_assign_nazoratchi`,
    `::test_second_nazoratchi_assignment_is_rejected`, `tests/test_roles.py`
    (shu jumladan DB-race simulyatsiyasi), `tests/test_db_migration.py`
    (UNIQUE indeksning o'zi).
  - **Moliyaviy ma'lumot va nazoratchi — 2026-08 audit qarori:**
    "Nazoratchi moliyaviy ma'lumotlarni ko'rmaydi" talabi bilan mavjud,
    testlangan `ACTION_REVIEW_CASH_SHIFT`/`ACTION_REVIEW_INVENTORY_VARIANCE`
    (kassir smenasi/ombor tafovutini tasdiqlash — shu ish uchun raqamlarni
    ko'rish shart) o'rtasida ziddiyat bor edi. Xavfsizroq, mavjud
    funksiyani buzmaydigan yo'l tanlandi: bu ikkala amal **operatsion
    nazorat** deb hisoblanadi (moliyaviy dashboard/tarix EMAS) va
    saqlanib qoldi — nazoratchiga hech qanday YANGI moliyaviy ko'rish
    huquqi (masalan `ACTION_VIEW_CASH_SUMMARY`/`ACTION_VIEW_INVENTORY_SUMMARY`,
    bular moliyachiga xos) berilmadi va berilmaydi.

  **Kelajak rejasi (hozir qilinmagan, faqat qayd etilgan):** agar
  kompaniya kelajakda ikkinchi nazoratchi qo'shishga qaror qilsa, kamida
  quyidagilar qayta ko'rib chiqilishi kerak — `SINGLE_SLOT_ROLES`dan
  `"nazoratchi"`ni olib tashlash; `discipline_bot.py`/`services/discipline.py`
  ichida `close_day`/`get_evaluations_for_date`ni har bir nazoratchiga
  filtrlash (hozir global); `_day_close_tick` scheduleri
  `find_user_by_role("nazoratchi")` (bitta natija) o'rniga barcha
  nazoratchilarni aylanishi; filial-nazoratchi bog'lanishi kerak bo'lsa
  (kim qaysi filialga mas'ul) yangi ustun/jadval. Bu ish HOZIR
  boshlanmagan — faqat "qayerdan boshlash kerak" xaritasi sifatida
  yozildi.
- **Logging hali birxil emas:** ko'pchilik joyda `print()` ishlatiladi,
  faqat bir nechta faylda (`discipline_bot.py`, `calibration_bot.py`)
  qisman `logging.getLogger(__name__)`. Xavfsizlik talabi (parol/token
  hech qachon loglanmasin) allaqachon bajarilgan — `db.py`dagi
  `_redact_dsn()` va h.k. Global exception handler mavjud (`main.py`,
  `@dp.errors()`), spam qilmaydi. Lekin yagona strukturali `logging`
  formatiga (vaqt/modul/daraja/user_id) o'tish hali qilinmagan — bu
  ~15 faylni qamrab oladigan, sof kosmetik/observability o'zgarish,
  audit paytida ataylab keyingi navbatga qoldirilgan (xavfsizlik yoki
  to'g'rilik xatosi emas).
- **Provider'lar (`providers/*.py`) hali ulanmagan:** `SMS_PROVIDER_ENABLED`
  va shu kabi flag'lar `config.py`da bor, lekin `get_sms_provider()`
  va boshqalar hozircha SHART-SIZ doim `Null*` qaytaradi — flag'ga
  qaramaydi. Bu qasddan (real provider ulanmagan), lekin flag hozircha
  hech narsaga ta'sir qilmaydi — chalkashlikka olib kelmasin uchun shu
  yerda aniq yozilgan.
