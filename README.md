# Fokus AI

Tadbirkorlik/xodimlar boshqaruvi uchun Telegram bot: onboarding,
rol-asosli vakolatlar, kassa smenasi, ombor nazorati, xodim
kalibratsiyasi, KPI/bonus, va BOS (kunlik baho + jarima + apellyatsiya)
tizimi. Python + [aiogram 3.x](https://docs.aiogram.dev/), SQLite (dev)
yoki Supabase PostgreSQL (prod), OpenAI (AI tahlil/tavsiya).

Kodning haqiqiy holati va arxitekturasi haqida to'liq ma'lumot:
**[`docs/`](docs/)** papkasida (pastga qarang).

## Tezkor boshlash

```bash
git clone <repo>
cd Fokus-ai
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
# .env faylini ochib haqiqiy BOT_TOKEN va OPENAI_API_KEY yozing
python main.py
```

`DATABASE_URL` `.env`da bo'lmasa, bot avtomatik lokal SQLite
(`fokus.db`) bilan ishlaydi — hech qanday tashqi baza kerak emas.

## Testlar

```bash
python -m pytest -q
```

CI (`.github/workflows/tests.yml`) har push/PRda testlarni ikkala
backend — SQLite va real Postgres konteyner — bilan ishga tushiradi.

## Hujjatlar

| Fayl | Nima haqida |
|---|---|
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Qatlamlar, ma'lumot oqimi, yangi funksiya qayerga qo'shiladi |
| [`docs/FEATURE_STATUS.md`](docs/FEATURE_STATUS.md) | Har bir funksiya — ishlaydi/qisman/rejalashtirilgan |
| [`docs/BUSINESS_RULES.md`](docs/BUSINESS_RULES.md) | KPI, bonus, jarima, smena qoidalari va standart qiymatlar |
| [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) | Lokal/Render deploy, migration, rollback |
| [`docs/CHANGE_POLICY.md`](docs/CHANGE_POLICY.md) | Yangi o'zgarish qanday bosqichlarda kiritiladi |

---

Created by Muhammadiy & Sodiq
