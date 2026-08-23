# FOKUS AI — Real Telegram E2E test robot

Bu papka `fokus-ai-test` (Render'dagi test bot) ustida real Telegram
orqali avtomatik E2E tekshiruv o'tkazadigan robotni saqlaydi.

- `scenario.py` — ssenariyning sof mantiqi (qadamlar, moslik
  tekshiruvi). Telethon yoki tarmoqqa bog'liq emas — oddiy Linux CI'da
  (`tests/test_e2e_scenario.py`) credential'siz test qilinadi.
- `run_e2e.py` — Telethon orqali haqiqiy Telegram'ga ulanib, ssenariyni
  bajaradigan skript. Faqat credential mavjud bo'lganda ishlaydi.
- `.github/workflows/e2e_real_telegram.yml` — GitHub Actions'da FAQAT
  qo'lda ishga tushiriladigan workflow.

## Bir martalik setup (Founder tomonidan, bir marta)

Bu E2E robot Founderning haqiqiy shaxsiy Telegram akkountidan
FOYDALANMAYDI — alohida, faqat test uchun akkaunt kerak.

1. **Alohida Telegram akkaunt tayyorlang** — faqat E2E test uchun,
   Founderning shaxsiy akkountidan mustaqil (masalan ikkinchi SIM/raqam
   bilan).

2. **Telegram API credential oling** — https://my.telegram.org/apps
   saytiga shu (2-band) akkaunt bilan kiring, yangi "App" yarating.
   Natijada `api_id` (raqam) va `api_hash` (matn) beriladi.

3. **Telethon STRING SESSION generatsiya qiling** — bu BITTA marta,
   interaktiv (telefon raqami + Telegram yuborgan kod, 2FA bo'lsa parol
   ham) login talab qiladi — Claude buni bajara olmaydi (interaktiv
   kirish imkoni yo'q). O'zingiz mahalliy kompyuteringizda (yoki
   xavfsiz muhitda) quyidagi skriptni bir marta ishga tushiring:

   ```python
   from telethon.sync import TelegramClient
   from telethon.sessions import StringSession

   api_id = ...      # 2-banddagi qiymat
   api_hash = "..."  # 2-banddagi qiymat

   with TelegramClient(StringSession(), api_id, api_hash) as client:
       print("SESSION:", client.session.save())
       me = client.get_me()
       print("Bu akkauntning Telegram user_id (FOUNDER_ID uchun kerak):", me.id)
   ```

   Chiqadigan `SESSION:` qatoridagi uzun matn — bu `E2E_TELEGRAM_SESSION`
   qiymati. **Bu qiymat parolga teng — hech qachon repo, chat yoki
   logga yozilmasin.** `me.id` — 6-band uchun kerak bo'ladi.

4. **Test botning Telegram username'ini aniqlang** (masalan
   `fokus_ai_test_bot`, "@" belgisisiz ham bo'ladi) — bu
   `E2E_TEST_BOT_USERNAME`.

5. **GitHub Secrets qo'shing** — repo Settings → Secrets and variables
   → Actions → "New repository secret", 4 tasi:
   - `E2E_TELEGRAM_API_ID`
   - `E2E_TELEGRAM_API_HASH`
   - `E2E_TELEGRAM_SESSION`
   - `E2E_TEST_BOT_USERNAME`

6. **`fokus-ai-test` Render xizmatida `FOUNDER_ID`ni yangilang** — 2-band
   akkauntning `me.id` qiymatiga (Render dashboard → `fokus-ai-test` →
   Environment). **FAQAT shu bitta test xizmatida** — production
   (`Fokus-ai`)ning o'z, alohida `FOUNDER_ID` environment o'zgaruvchisi
   bor va u UMUMAN TEGILMAYDI/o'zgarmaydi. Kodga hech qanday o'zgarish
   kerak emas — `config.py` allaqachon `FOUNDER_ID`ni har xizmat o'z
   environment'idan mustaqil o'qiydi.

Shu 6 qadamdan keyin, Actions → "E2E (real Telegram, fokus-ai-test)" →
"Run workflow" orqali real E2E ssenariyni ishga tushirish mumkin.

## Xavfsizlik

- E2E test faqat `E2E_TEST_BOT_USERNAME` orqali ko'rsatilgan botga
  (har doim `fokus-ai-test` bo'lishi kerak) xabar yuboradi — main/
  production botga hech qachon tegmaydi.
- Ssenariy faqat 🧪 Rol testi sandbex ichida ishlaydi — sandbox hech
  qanday DB yozuvini amalga oshirmaydi (qarang `main.py`dagi
  `_SandboxPreviewMiddleware`), shuning uchun E2E test ham hech qanday
  real xodim/moliyaviy ma'lumotni o'zgartirmaydi.
- `E2E_TELEGRAM_SESSION` to'liq akkaunt kirish huquqiga teng — faqat
  GitHub Secrets orqali saqlanadi, hech qachon kodga yoki logga
  yozilmaydi.
