# FOKUS AI — oxirgi nuqta va keyingi bitta qadam

Bu fayl yangi chat/sessiyada QAYERDAN DAVOM ETISHNI ko'rsatadigan kanonik checkpoint.

## Oxirgi tasdiqlangan nuqta

- Branch: `feature/hr-conversational-interview`
- Hozirgi HEAD (tekshiruvdan oldin): `51beb28` — `task: close shared results menu checkpoint`.
- Working tree: toza.
- Oxirgi funksional ish: `⭐ Mening natijalarim` menyusini sodda, emojili va 2 ustunli qilish — **DONE**.
- Funksional commit: `78a4fee` — `feat: add friendly paired results menu`; lokal va `origin/feature/hr-conversational-interview` tarixida mavjudligi tasdiqlandi.
- `78a4fee`dan keyingi commitlar FOKUS AI doimiy xotira tizimi hujjatlari uchun.
- Doimiy xotira tizimi yaratildi: `docs/FOKUS_MEMORY.md`, `docs/NEXT_STEP.md`, `docs/IDEAS.md`; `CLAUDE.md`da foydalanish qoidasi majburiy qilindi.
- `main`/production bu ishlar doirasida o'zgartirilmagan.

## Yopilgan tekshiruv (2026-09-01)

`⭐ Mening natijalarim` vazifasining yakuniy targeted tekshiruvi remote Linux/bash muhitida bajarildi:

```
python -m pytest -q tests/test_menu_and_fsm_escape.py tests/test_role_test_sandbox.py
52 passed in 10.94s
```

Funksional kodga tegilmadi. Full test, Smoke va E2E ishlatilmadi. GitHub Actions run masalasi endi bloklovchi emas — targeted test lokal Linux muhitida PASS.

## Production launch preflight (2026-09-01) — GATE PASS, DEPLOY BAJARILMADI

Release candidate: `39a0c9a`.

- A) `39a0c9a` mavjud — OK.
- B) `origin/main` = `8f492e2` — kutilgan holat, o'zgarmagan.
- C) `8f492e2` `39a0c9a`ning ancestor'i — divergence yo'q.
- D) `config.py:21` — `ENVIRONMENT` unset bo'lsa `production`; `main.py:79` production'da `BOT_TOKEN`, `db.py:39-41` production'da `DATABASE_URL` o'qiydi. `TEST_BOT_TOKEN`/`TEST_DATABASE_URL` faqat `ENVIRONMENT=test`da.
- E/F/G) Render CLI yo'q, `RENDER_API_KEY` yo'q — **STOP: Render production sozlamalarini tekshirish uchun access yo'q**. Orphan worker holati ham shu sababdan tekshirilmadi (va YOQILMADI).
- Release gate: `.github/workflows/smoke-tests.yml` to'plami ubuntu Linux'da BIR MARTA ishlatildi — **88 passed, 0 failed** (53.45s). Full suite ishlatilmadi.
- 3-QADAM BAJARILMADI: runner guard `main`/production yozuvini taqiqlaydi. `main` va Render production'ga TEGILMADI, guard tahrirlanmadi.

## KEYINGI BITTA QADAM

Founder Render access berishi (yoki `main`ga merge + production deployni o'zi bajarishi) kerak — `39a0c9a` gate'lari PASS, faqat yozuv ruxsati yetishmayapti. Bungacha yangi feature boshlanmaydi.

## Keyingi qadam bajarilgach

- Shu faylni yangi real checkpoint bilan yangila.
- `docs/PROJECT_STATE.md`ni ham real holatga mos yangila.
- Keyingi BIRTA vazifani shu yerga yoz.

## DONE tarixi

- `78a4fee`: shared `Mening natijalarim` menyusining 4x2 emojili UI kodi commit qilingan va branchga push qilingan; targeted-test yakuniy tasdig'i 2026-09-01 da olindi (52 passed) — vazifa YOPILDI.
- `72e5ec34`: FOKUS AI doimiy xotira protokoli yaratildi va Claude ish tartibiga majburiy bog'landi.
