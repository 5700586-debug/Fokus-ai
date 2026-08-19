# Fokus AI — hozirgi holat

Bu fayl faqat HOZIRGI real holatni saqlaydi — eski tarix yo'q. Har
muhim commit/deploydan keyin yangilanadi (qarang root `CLAUDE.md`).
Ziddiyat bo'lsa, real Git/Render holati (`git log`, `render deploys
list`) ustuvor — bu faylning o'zi emas.

**Oxirgi tekshirilgan sana:** 2026-08-19

## Development

- **Faol branch:** `feature/hr-conversational-interview`
- **Oxirgi commit:** `08bfa2d` — "Add location/timing/retention fields and an explicit recommendation line to the Founder card"

## Render — test muhiti

- **Servis:** `fokus-ai-test` (`srv-d9ts9jad0e5s739ubbcg`, background worker, branch `feature/hr-conversational-interview`)
- **Live commit:** `be84557` — branchdan 2 ta commit orqada (`862cc72`, `08bfa2d` hali deploy qilinmagan)

## Render — production

- **Branch:** `main`, HEAD = `8f492e2`
- **Servis:** `Fokus-ai` (`srv-d9q82sh42hec73a0au6g`, web service)
- **Live commit:** `da43c8b` — **DIQQAT:** `8f492e2`ni deploy qilish urinishi **muvaffaqiyatsiz** (`update_failed`) bo'lgan, production hali eski commitda ishlamoqda. Sabab hali tekshirilmagan.
- **Orfan worker:** `Fokus-ai` / slug `fokus-ai-rl7u` (`srv-d9qdpsqd0e5s73bji7n0`, branch `main`) — `TelegramConflictError`ga sabab bo'lgani uchun **suspend qilingan**, hali shu holatda.

## Tugagan asosiy modullar

- **Saturn kunlik rasmli salom** (tong/tun, ob-havoga mos, haqiqiy fotolar) — `main`ga birlashtirilgan.
- **Recruiting (Fokus HR) — suhbat asosidagi intervyu** — vaqtincha barqaror/yakunlangan (qarang `docs/modules/RECRUITING.md`), faqat test muhitida.

## Hozirgi bitta keyingi qadam

Founder test botda (`fokus-ai-test`) yangi recruiting o'zgarishlarini sinab ko'rgach, tasdiqlansa: (a) qolgan 2 ta commitni (`862cc72`, `08bfa2d`) test servisga deploy qilish, (b) production'dagi `8f492e2` deploy failure sababini alohida tekshirish (bu Recruiting bilan bog'liq emas, mustaqil masala).
