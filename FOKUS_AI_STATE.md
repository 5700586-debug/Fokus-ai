# FOKUS AI — joriy holat

Bu fayl doim JORIY holatni ko'rsatadi (eski tarix emas). Har muhim
ishdan keyin yangilanadi. Ziddiyat bo'lsa, haqiqiy Git/GitHub holati
(`git log`, GitHub Actions) ustuvor.

- **Branch:** `feature/hr-conversational-interview`
- **Commit:** `8838ab1` — "Make CI Linux-only and machine-independent: smoke tests on push, full suite on demand"
- **GitHub holati:** Sinxron — lokal HEAD va `origin`dagi shu branch bir xil.
- **Test natijasi:** GitHub Actions "Smoke tests" workflow (`ubuntu-latest`), commit `8838ab1` uchun — **PASSED** (run 32524012097: checkout, dependency install, haqiqiy `psycopg2` import, 4 ta test — barchasi muvaffaqiyatli).
- **Test muhiti:** GitHub Actions, Linux (`ubuntu-latest`).
  - `.github/workflows/smoke-tests.yml` — har pushda avtomatik, tez, kichik (haqiqiy `psycopg2` import + 4 ta muhim test).
  - `.github/workflows/tests.yml` — to'liq (900+) to'plam, endi FAQAT qo'lda ishga tushiriladi (Actions -> Tests -> Run workflow), har pushda emas.
  - Windows lokalda endi `pytest`/`pip install`/Python test ISHLATILMAYDI — faqat kod tahrirlash, `git status`/commit/push/pull.
- **Main/production holati:** `main` = `8f492e2`, tegilmagan. Production (`Fokus-ai` Render web service) va Render'ga umuman tegilmagan, deploy qilinmagan.

## Oxirgi tugallangan ish

- Saturn moliyaviy guruh xabari muammosi tuzatildi (`saturn_group_bot.py`) — dashboard/moliyaviy blok (reja/savdo/foiz/chek) endi xodimlar guruhiga avtomatik yoki `/saturntest` orqali umuman yuborilmaydi.
- Founder nomzod kartasiga tug'ilgan sana + yosh qatori qo'shildi (`services/recruiting_card.py`).
- Ikkala tuzatish uchun 4 ta test yozilgan (`tests/test_saturn_group_bot_flows.py`, `tests/test_recruiting_card.py`) va GitHub Actions (haqiqiy Linux, haqiqiy `psycopg2`, hech qanday stub) da **4/4 PASSED** tasdiqlangan.
- Kassir smena topshirish, Founder UX (yangi menyu/xodim qo'shish oqimi), tugilgan sana parseri kabi oldingi ishlar allaqachon shu branchda.
- Ish muhiti barqarorlashtirildi: doimiy test endi Windows'da emas, GitHub Actions Linux'da; to'liq (900+) to'plam endi har pushda emas, faqat qo'lda.

## Hali tugallanmagan ish

- `tests/test_recruiting_bot_flow.py`da bu ishga aloqasi yo'q ~14 ta test avvaldan (mendan oldin ham) muvaffaqiyatsiz edi — hali tuzatilmagan, alohida masala.
- Production'dagi `8f492e2` deploy failure sababini alohida tekshirish hali qilinmagan (eski, mustaqil masala).
- `RECRUITING_BRANCH_NAMES` hamon placeholder qiymatlarda (`Filial-1,Filial-2`) — production'ga chiqishdan oldin haqiqiy filial nomlari kerak.
- `content/daily_greetings/morning_XX.jpg`/`night_XX.jpg` rasmlari hali Founder tomonidan qo'yilmagan.
- Founder menyusidagi "🏪 Do'konlar" tugmasi hozircha `/listusers`ga bog'langan (vaqtinchalik qaror) — haqiqiy filiallar ro'yxatiga bog'lash kerak.

## Keyingi bitta qadam

`🏪 Do'konlar` tugmasini haqiqiy filiallar ro'yxatiga bog'lash.
