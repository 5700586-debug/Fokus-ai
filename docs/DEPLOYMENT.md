# Fokus AI — Deploy yo'riqnomasi

## 1. Lokal ishga tushirish

```bash
git clone <repo>
cd Fokus-ai
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env   # keyin haqiqiy BOT_TOKEN/OPENAI_API_KEY yoz
python main.py
```

`DATABASE_URL` `.env`da bo'lmasa, bot avtomatik SQLite (`fokus.db`,
loyiha papkasida) bilan ishlaydi — Supabase/Postgres kerak emas.

## 2. Testlarni ishga tushirish

```bash
python -m pytest -q
```

Postgres yo'lini (`db_postgres.py`) ham tekshirish uchun (ixtiyoriy,
lokal Docker bilan):

```bash
docker run -d --name fokus-test-pg -e POSTGRES_PASSWORD=testpass \
  -e POSTGRES_DB=fokus_test -p 55432:5432 postgres:16-alpine
DATABASE_URL="postgresql://postgres:testpass@localhost:55432/fokus_test" \
  python -m pytest -q
docker rm -f fokus-test-pg
```

CI (`.github/workflows/tests.yml`) buni har push/PRda avtomatik ikkala
backend uchun ham bajaradi.

## 3. Environment o'zgaruvchilari

To'liq ro'yxat va izohlar: `.env.example`. Majburiy: `BOT_TOKEN`,
`OPENAI_API_KEY`. Qolgani ixtiyoriy, standart qiymat bilan ishlaydi.

## 4. Test muhiti (alohida test bot, prodga tegmaydi)

Production botdan BUTUNLAY ajratilgan test bot (masalan
`@Saturn_FokusAI_Testbot`) ishga tushirish uchun:

1. **Lokal sinash** (eng tez yo'l): `.env` faylida `ENVIRONMENT=production`
   qatorini `ENVIRONMENT=test`ga o'zgartiring, va `TEST_BOT_TOKEN=`
   qatoriga (allaqachon tayyorlangan, bo'sh) @BotFather'dan olingan test
   bot tokenini yozing. `python main.py` — bot endi `TEST_BOT_TOKEN`
   bilan ishlaydi, `BOT_TOKEN` (production) hech qachon o'qilmaydi, va
   ma'lumotlar alohida `fokus_test.db` fayliga yoziladi (production
   `fokus.db`ga tegmaydi).
2. **Alohida Render servisi** (production servisidan mustaqil, doim
   ishlab turishi uchun): Render dashboardida **yangi** Web Service
   yarating (xuddi productiondagi kabi sozlamalar — start command
   `python main.py`), lekin uning Environment bo'limida:
   - `ENVIRONMENT` = `test`
   - `TEST_BOT_TOKEN` = (test bot tokeningiz — **faqat shu yerga**,
     boshqa hech qayerga yozilmaydi)
   - `OPENAI_API_KEY` = (productiondagi bilan bir xil bo'lishi mumkin)
   - `DATABASE_URL` — **qo'ymang** (yoki productiondagi qiymatni aslo
     nusxalamang) — shunda test avtomatik ajratilgan SQLite bilan
     ishlaydi
   - `TEST_DATABASE_URL` — faqat agar kelajakda Supabase'da alohida
     test schema/baza ochilsa, o'sha connection stringni shu yerga
   - `COMPANY_TIMEZONE`, `FOUNDER_ID` — xohlasangiz productiondagi bilan
     bir xil (test uchun ahamiyati yo'q)

   Bu ikkinchi, mustaqil Render servisi bo'lgani uchun production
   servisi bilan bir vaqtda, bir-biriga tegmasdan ishlaydi — ikkalasi
   ham o'z tokeni bilan alohida polling qiladi.

**Muhim:** `ENVIRONMENT`, `TEST_BOT_TOKEN`, `TEST_DATABASE_URL` —
production nomlaridan (`BOT_TOKEN`, `DATABASE_URL`) BUTUNLAY BOSHQA
o'zgaruvchi nomlari. Shuning uchun ikkalasi bir xil `.env`da yoki bir
xil Render loyihasida tursa ham, bitta jarayon ikkinchisining
tokeni/bazasiga tasodifan ulanib qololmaydi — bu strukturaviy himoya,
qo'lda ehtiyot bo'lishga tayanmaydi.

## 5. Render deploy (prod)

- **Servis turi:** Web Service (Render Free tarifida Background Worker
  yo'q). Bot Telegramga **long polling** orqali ulanadi — HTTP so'rov
  qabul qilmaydi, lekin Render "Web Service" `$PORT`ga bog'lanishni
  kutadi. Shu sabab `health_server.py` polling bilan bir vaqtda
  ahamiyatsiz `GET /` -> `200 OK` server ochadi. Agar bu server
  ishlamasa, deploy ~15 daqiqadan keyin "Timed out"/"No open ports
  detected" bilan muvaffaqiyatsiz tugaydi — bot polling orqali to'liq
  ishlab tursa ham.
- **Start command:** `python main.py`
- **Kerakli environment variable'lar (Render dashboard):**
  - `BOT_TOKEN` (majburiy)
  - `OPENAI_API_KEY` (majburiy)
  - `DATABASE_URL` (Supabase Postgres connection string — **Session
    Pooler** manzilidan foydalaning, Render kabi ko'p-qisqa-ulanishli
    muhitlar uchun mo'ljallangan; oxirida bo'sh joy/qator ko'chirish
    bo'lmasin — bo'lsa avtomatik tozalanadi, lekin baribir toza
    qo'yish tavsiya etiladi)
  - `COMPANY_TIMEZONE` (ixtiyoriy, standart `Asia/Tashkent`)
  - `FOUNDER_ID` (ixtiyoriy — qo'yilmasa kodda yozilgan avvalgi
    Founder bilan ishlaydi, o'zgartirish uchun qo'yiladi)
- **Bitta instance qoidasi:** bir xil TOKEN (`BOT_TOKEN` YOKI
  `TEST_BOT_TOKEN`, ikkisi mustaqil — masalan test botni lokal +
  Render'da bir vaqtda ishga tushirish ham xuddi shu qoidaga tegishli)
  bilan ikki joyda bir vaqtda polling ishlatilmasin — Telegram 409
  conflict qaytaradi. aiogram buni o'zi ushlab oladi va cheksiz qayta
  uradi (botni yiqitmaydi), lekin loglarda ketma-ket
  `TelegramConflictError` ko'rinsa — bu aynan shu holat, ikkinchi
  instance'ni to'xtatish kerak. Production (`BOT_TOKEN`) va test
  (`TEST_BOT_TOKEN`) esa BUTUNLAY BOSHQA tokenlar bo'lgani uchun
  ikkalasi bir vaqtda, alohida-alohida polling qilib ishlashi
  MUTLAQO NORMAL — bir-biriga umuman ta'sir qilmaydi.

## 6. Migration

Sxema o'zgarishlari `schema/*.py`da `CREATE TABLE IF NOT EXISTS` +
kerak bo'lsa `INSERT OR IGNORE` seed qatorlar sifatida yoziladi —
alohida migration fayllari/raqamlash yo'q, `init_db()` har ishga
tushishda barcha sxemani qayta ta'minlaydi (idempotent, mavjud
jadval/qatorga tegmaydi). Yangi ustun qo'shish kerak bo'lsa:
- SQLite: `ALTER TABLE ... ADD COLUMN` (agar ustun yo'q bo'lsa) —
  qayta ishga tushirilganda xato bermasligi uchun avval ustun
  mavjudligini tekshirish kerak.
- Postgres: xuddi shunday, lekin `db_postgres.py`dagi tarjima
  qoidalarini yangi naqsh uchun tekshirish kerak.

**Production ma'lumotini o'chiradigan migration yozilmaydi.** Ustun/
jadval o'chirish kerak bo'lsa, avval eskisini saqlab, yangisini
qo'shib, kod to'liq ko'chgandan keyin alohida bosqichda o'chiriladi.

## 7. Rollback

Bu loyiha alohida migration versiyalash ishlatmaydi (yuqoridagi
"idempotent sxema" yondashuvi), shuning uchun rollback = **oldingi git
commit'ga qaytish + qayta deploy**:

```bash
git log --oneline          # muammoli commit'dan oldingisini top
git revert <commit>        # yoki: git checkout <oldingi-commit> -- .
git push origin main       # Render avtomatik qayta deploy qiladi
```

Agar muammoli o'zgarish yangi ustun/jadval qo'shgan bo'lsa (lekin
o'chirmagan), kodni oldingi holatga qaytarish xavfsiz — yangi
ustun/jadval shunchaki ishlatilmay qoladi, ma'lumot yo'qolmaydi.

## 8. Xatolik yuz bersa — tiklash

- **`init_db()` muvaffaqiyatsiz** (`main.py` darhol to'xtaydi, aniq
  xabar bilan): `DATABASE_URL`ni tekshiring (host/port/foydalanuvchi/
  parol, bo'sh joy yo'q), Supabase Session Pooler ishlab turganini
  tasdiqlang.
- **`BOT_TOKEN`/`OPENAI_API_KEY` yo'q:** bot darhol aniq xato bilan
  to'xtaydi (startup validatsiyasi) — Render dashboardida env var
  borligini tekshiring.
- **Ketma-ket `TelegramConflictError`:** ikkinchi instance ishlab
  turibdi — §5ga qarang.
- **`COMPANY_TIMEZONE` noto'g'ri/`tzdata` yo'q:** bot yiqilmaydi,
  avtomatik UTC'ga qaytadi va aniq log yozadi (`_resolve_timezone()`
  har bir bot faylida) — lekin bu holatda kunlik chegaralar UTC
  bo'yicha hisoblanadi, shuning uchun log'ni ko'rib muammoni tuzatish
  kerak.
