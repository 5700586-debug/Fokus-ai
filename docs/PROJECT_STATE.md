# Fokus AI — hozirgi holat

Bu fayl faqat HOZIRGI real holatni saqlaydi — eski tarix yo'q. Har
muhim commit/deploydan keyin yangilanadi (qarang root `CLAUDE.md`).
Ziddiyat bo'lsa, real Git/Render holati (`git log`, `render deploys
list`) ustuvor — bu faylning o'zi emas.

**Oxirgi tekshirilgan sana:** 2026-08-23

## Development

- **Faol branch:** `feature/hr-conversational-interview`
- **Oxirgi commit:** `5ebb8d1` — "Step 5: replace generic bot welcome text with a Saturn team greeting" — FOUNDER UX & STORE MANAGEMENT AUTONOMOUS HARDENING'ning 5-bosqichi (Do'konlar per-branch tugmalar / filial kartasi / xodimlar kartasi / kassir texnik matnlari tozalash / Saturn welcome matni), barchasi GitHub Actions Linux'da PASSED, `fokus-ai-test` hozir `fa5dac0`da live (🧪 ROL TESTI bilan), bu 5 bosqich hali deploy qilinmagan

## Render — test muhiti

- **Servis:** `fokus-ai-test` (`srv-d9ts9jad0e5s739ubbcg`, background worker, branch `feature/hr-conversational-interview`)
- **Live commit:** `fa5dac0` — 🧪 ROL TESTI sandbox deploy qilindi. Branch HEAD (`5ebb8d1`, FOUNDER UX & STORE MANAGEMENT HARDENING) hali deploy qilinmagan.

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
