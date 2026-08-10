# Fokus-ai — loyiha qoidalari

## Texnologiyalar steki
- **Til:** Python, to'liq `async/await` uslubida.
- **Bot freymvorki:** Aiogram 3.x (`aiogram==3.22.0`).
- **Vazifa rejalashtiruvchi:** APScheduler (masalan, ta'minotchilarga soat 06:00 va 10:00 da avtomatik xabar).
- **Ma'lumotlar bazasi:** ikki backend qo'llab-quvvatlanadi:
  - Lokal/dev — SQLite (`fokus.db`).
  - Prod (Render) — PostgreSQL (Supabase), `psycopg2-binary` orqali.
  - Backend tanlovi `DATABASE_URL` muhit o'zgaruvchisi orqali amalga oshadi (`db.py`).
  - `db_postgres.py` — Postgres ustida sqlite3'ga o'xshash sirtqi interfeys (`conn.execute(...).fetchone()/fetchall()`, `row["col"]`, `cursor.lastrowid` va h.k.). Chaqiruvchi kod (`repositories/*.py`, `employees.py`, `storage.py`, `invites.py`) backend qaysi bo'lishidan qat'i nazar o'zgarishsiz qoladi.
  - Ma'lumotlar joylashuvi `FOKUS_DATA_DIR` orqali sozlanadi.
- **Deploy:** Render.com (Free tarif), `health_server.py` orqali minimal health-check porti ochiladi.

## Muhim arxitektura invariantlari
- `main.py`da `load_dotenv()` va `init_db()` boshqa har qanday loyiha modulidan **oldin** chaqirilishi shart — aks holda `.env` qiymatlari e'tiborga olinmaydi yoki hali yaratilmagan jadvalga so'rov ketadi.
- Yangi DB so'rovlari `repositories/` papkasidagi mavjud naqsh bo'yicha yoziladi, to'g'ridan-to'g'ri SQL botning handler fayllariga yozilmaydi.
- SQLite -> Postgres tarjimasi faqat haqiqatda ishlatiladigan naqshlar uchun (`?` -> `%s`, `INSERT OR IGNORE` -> `ON CONFLICT DO NOTHING` va h.k.) — umumiy SQL parser emas. Yangi SQL naqshi qo'shilsa, `db_postgres.py`dagi tarjima qoidalari ham yangilanishi kerak bo'lishi mumkin.
- Xatoliklarni backend-agnostik tarzda ushlash kerak (SQLite `IntegrityError` va Postgres `IntegrityError` ikkalasi ham).

## Kod yozish qoidalari
- Aiogram handler'lar va DB chaqiruvlari **async/await** uslubida yoziladi, sinxron bloklovchi chaqiruvlardan qochiladi.
- Ortiqcha izoh (comment) yozilmaydi — faqat nima uchun (WHY) aniq bo'lmagan joylarda, qisqa izoh qoldiriladi (masalan, `db_postgres.py`dagi dumaloq bog'lanish yoki import tartibi haqidagi izohlar kabi).
- Bot xabarlari va foydalanuvchiga ko'rinadigan matnlar o'zbek tilida yoziladi (loyihaning mavjud konventsiyasi).
- Yangi abstraksiya/wrapper faqat aniq zarurat bo'lganda qo'shiladi — spekulyativ "kelajakda kerak bo'lishi mumkin" kodi yozilmaydi.

## Claude bilan ishlash tartibi (token tejash)
- Fayllarni to'liq qayta yozish o'rniga, faqat o'zgargan qism (diff/patch) ko'rsatiladi — agar butun faylni ko'rsatish so'ralmasa.
- Har safar asosiy tushunchalar (async/await nima, Postgres qanday ishlaydi va h.k.) boshidan tushuntirilmaydi — bu qoidalar doim yodda saqlanadi.
- Katta o'zgarishlardan oldin qisqa reja va sabab (nega bu yondashuv) taqdim etiladi, keyin amalga oshiriladi.
