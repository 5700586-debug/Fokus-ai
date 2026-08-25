# Fokus AI — hozirgi holat

Bu fayl faqat HOZIRGI real holatni saqlaydi — eski tarix yo'q. Har
muhim commit/deploydan keyin yangilanadi (qarang root `CLAUDE.md`).
Ziddiyat bo'lsa, real Git/Render holati (`git log`, `render deploys
list`) ustuvor — bu faylning o'zi emas.

**Oxirgi tekshirilgan sana:** 2026-08-24

## Development

- **Faol branch:** `feature/hr-conversational-interview`
- **Oxirgi commit:** `ec5e45f` — "Post E2E diagnostics as a commit comment on failure". **✅ Real Telegram E2E endi PASSED** (shu commit uchun) — E2E workflow'ga doimiy diagnostika-comment infratuzilma qo'shildi (FAILED bo'lsa avtomatik commit comment orqali to'liq sabab ko'rinadi, Founder aralashuvisiz), va aynan shu push'dagi run PASSED chiqdi. Launch-core status (SMENA/KASSA/NAZORATCHI: TAYYOR, BONUS: qisman, VAZIFA: yo'q) va "jarima" so'zini UI'dan olib tashlash (commit `2d286cb`) `FOKUS_AI_STATE.md`da batafsil.

- **Gemini konsultant (read-only)** — rasmiy `google-github-actions/run-gemini-cli@v0`.
  Gemini faqat kod o'qiydi/tahlil qiladi, yozmaydi va commit qilmaydi.
  Workflow fayli hozircha `docs/gemini-consultant.workflow.yml`da —
  aktivlashtirish uchun Founder uni `.github/workflows/`ga ko'chirishi kerak
  (sabab va aniq buyruq: `docs/GEMINI_CONSULTANT.md`).

## Render — test muhiti

- **Servis:** `fokus-ai-test` (`srv-d9ts9jad0e5s739ubbcg`, background worker, branch `feature/hr-conversational-interview`)
- **Live commit:** `316c577` — branch HEAD'dan 2 ta hujjat/workflow-only commit orqada (bot xatti-harakatiga ta'sir qilmaydi, qayta deploy shart emas).

## Render — production

- **Branch:** `main`, HEAD = `8f492e2`
- **Servis:** `Fokus-ai` (`srv-d9q82sh42hec73a0au6g`, web service)
- **Live commit:** `da43c8b` — **DIQQAT:** `8f492e2`ni deploy qilish urinishi **muvaffaqiyatsiz** (`update_failed`) bo'lgan, production hali eski commitda ishlamoqda. Sabab hali tekshirilmagan.
- **Orfan worker:** `Fokus-ai` / slug `fokus-ai-rl7u` (`srv-d9qdpsqd0e5s73bji7n0`, branch `main`) — `TelegramConflictError`ga sabab bo'lgani uchun **suspend qilingan**, hali shu holatda.

## Tugagan asosiy modullar

- **Saturn kunlik rasmli salom** (tong/tun, ob-havoga mos, haqiqiy fotolar) — `main`ga birlashtirilgan.
- **Recruiting (Fokus HR) — suhbat asosidagi intervyu** — vaqtincha barqaror/yakunlangan (qarang `docs/modules/RECRUITING.md`), faqat test muhitida.
- **Xayrli tong/tun — sodda 30 kunlik kontent** (`content/daily_greetings/`, `services/daily_greetings.py`) — kod tayyor, mavjud Saturn scheduler'ga ulangan (`saturn_group_bot.py` tick), lekin `morning.jpg`/`night.jpg` hali Founder tomonidan qo'yilmagan va hali test servisga deploy qilinmagan.

## Hozirgi bitta keyingi qadam

Founder `content/daily_greetings/morning.jpg` va `night.jpg` fayllarini qo'ygach va test botda (`fokus-ai-test`) yangi recruiting + daily-greetings o'zgarishlarini sinab ko'rgach, tasdiqlansa: (a) branch HEAD'ni (`7d6791c`) test servisga deploy qilish, (b) production'dagi `8f492e2` deploy failure sababini alohida tekshirish (bu Recruiting/daily-greetings bilan bog'liq emas, mustaqil masala).
