# FOKUS AI — joriy holat

Bu fayl doim JORIY holatni ko'rsatadi (eski tarix emas). Har muhim
ishdan keyin yangilanadi. Ziddiyat bo'lsa, haqiqiy Git/GitHub holati
(`git log`, GitHub Actions) ustuvor.

- **Branch:** `feature/hr-conversational-interview`
- **Commit:** `3027936` — "Make new-hire/cashier menu persistent and auto-send it after HR approval"
- **GitHub holati:** Sinxron — lokal HEAD va `origin`dagi shu branch bir xil.
- **Test natijasi:** GitHub Actions "Smoke tests" workflow (`ubuntu-latest`), commit `3027936` uchun — **PASSED** (run 32593788131: checkout, dependency install, haqiqiy `psycopg2` import, 8 ta test — barchasi muvaffaqiyatli).
- **Test muhiti:** GitHub Actions, Linux (`ubuntu-latest`).
  - `.github/workflows/smoke-tests.yml` — har pushda avtomatik, tez, kichik (haqiqiy `psycopg2` import + 4 ta muhim test).
  - `.github/workflows/tests.yml` — to'liq (900+) to'plam, endi FAQAT qo'lda ishga tushiriladi (Actions -> Tests -> Run workflow), har pushda emas.
  - Windows lokalda endi `pytest`/`pip install`/Python test ISHLATILMAYDI — faqat kod tahrirlash, `git status`/commit/push/pull.
- **Main/production holati:** `main` = `8f492e2`, tegilmagan. Production (`Fokus-ai` Render web service) va Render'ga umuman tegilmagan, deploy qilinmagan.

## Oxirgi tugallangan ish

- HR/Xodim UX 1-bosqich: `main.py`dagi `build_menu`/`build_category_menu` klaviaturalari endi `is_persistent=True` (ishga kiruvchi va kassir menyusi doim ko'rinadi, alohida buyruq shart emas).
- `approval.py`da Founder "✅ Tasdiqlash" bosgach, xodimga endi "/start ni bosing" deyilmaydi — greeting + `build_menu` avtomatik yuboriladi (`main.greeting_for_user`/`main.build_menu`, funksiya ichidagi deferred import orqali aylanma import oldi olingan).
- Ikkala tuzatish uchun 2 ta test qo'shilgan (`tests/test_bot_flows.py::test_approve_sends_employee_menu_without_requiring_start`, `::test_build_menu_and_category_menu_are_persistent`) va GitHub Actions Linux'da **PASSED** (run 32593788131, commit `3027936`).
- Saturn moliyaviy guruh xabari muammosi, Founder nomzod kartasiga tug'ilgan sana, Kassa nazorati: Nazoratchi qarori (qabul qilish/qayta sanash tugmalari), ish muhitini GitHub Actions Linux'ga o'tkazish — barchasi allaqachon shu branchda va PASSED.

## Hali tugallanmagan ish

- `tests/test_recruiting_bot_flow.py`da bu ishga aloqasi yo'q ~14 ta test avvaldan (mendan oldin ham) muvaffaqiyatsiz edi — hali tuzatilmagan, alohida masala.
- Production'dagi `8f492e2` deploy failure sababini alohida tekshirish hali qilinmagan (eski, mustaqil masala).
- `RECRUITING_BRANCH_NAMES` hamon placeholder qiymatlarda (`Filial-1,Filial-2`) — production'ga chiqishdan oldin haqiqiy filial nomlari kerak.
- `content/daily_greetings/morning_XX.jpg`/`night_XX.jpg` rasmlari hali Founder tomonidan qo'yilmagan.
- Founder menyusidagi "🏪 Do'konlar" tugmasi hozircha `/listusers`ga bog'langan (vaqtinchalik qaror) — haqiqiy filiallar ro'yxatiga bog'lash kerak.
- `fokus-ai-test` Render servisiga `3027936` hali deploy qilinmagan (bu topshiriqda deploy so'ralmagan).

## Keyingi bitta qadam

`3027936`ni `fokus-ai-test` Render servisiga deploy qilib, real Telegramda tekshirish (keyin `🏪 Do'konlar` tugmasini haqiqiy filiallar ro'yxatiga bog'lash).
