# FOKUS AI — joriy holat

Bu fayl doim JORIY holatni ko'rsatadi (eski tarix emas). Har muhim
ishdan keyin yangilanadi. Ziddiyat bo'lsa, haqiqiy Git/GitHub holati
(`git log`, GitHub Actions) ustuvor.

- **Branch:** `feature/hr-conversational-interview`
- **Commit:** `3b2ab42` — "Fix kassir menu buttons getting swallowed by stale FSM state"
- **GitHub holati:** Sinxron — lokal HEAD va `origin`dagi shu branch bir xil.
- **Test natijasi:** GitHub Actions "Smoke tests" workflow (`ubuntu-latest`), commit `3b2ab42` uchun — **PASSED** (run 32595351643: checkout, dependency install, haqiqiy `psycopg2` import, 12 ta test — barchasi muvaffaqiyatli).
- **Test muhiti:** GitHub Actions, Linux (`ubuntu-latest`).
  - `.github/workflows/smoke-tests.yml` — har pushda avtomatik, tez, kichik (haqiqiy `psycopg2` import + 4 ta muhim test).
  - `.github/workflows/tests.yml` — to'liq (900+) to'plam, endi FAQAT qo'lda ishga tushiriladi (Actions -> Tests -> Run workflow), har pushda emas.
  - Windows lokalda endi `pytest`/`pip install`/Python test ISHLATILMAYDI — faqat kod tahrirlash, `git status`/commit/push/pull.
- **Main/production holati:** `main` = `8f492e2`, tegilmagan. Production (`Fokus-ai` Render web service) va Render'ga umuman tegilmagan, deploy qilinmagan.

## Oxirgi tugallangan ish

- Kassir menyu routing xatosi tuzatildi: `_ClearStaleStateMiddleware` faqat "/" bilan boshlangan matnni "qochish" deb tanirdi — kassirning yangi sodda tugmalari ("🟢 Smenani boshlash" va h.k.) "/" bilan boshlanmagani uchun, kassir eski (masalan `/expense` kategoriya kutish) holatda qolib ketgan bo'lsa, tugma bosilganda bu holat tomonidan noto'g'ri yutib olinardi (haqiqiy `/openshift`/`/closeshift`/`/expense` handleriga yetib bormasdi). Endi `_STALE_LABEL_TO_COMMAND`dagi har qanday matn (shu jumladan yangi kassir tugmalari) ham "qochish" sifatida tan olinadi.
- Shu tuzatish uchun 2 ta yangi test qo'shildi (`tests/test_menu_and_fsm_escape.py::test_kassir_friendly_button_escapes_stale_expense_state` — asosiy regressiya, `::test_start_shows_role_specific_category_for_kassir` — mavjud /start-kassir menyu tekshiruvi qayta tasdiqlash uchun ishlatildi); GitHub Actions Linux'da **PASSED** (run 32595351643, commit `3b2ab42`).
- Kassir menyusini sodda qilish (`/openshift`/`/closeshift`/`/expense` → "🟢 Smenani boshlash"/"🔴 Smenani topshirish"/"💸 Xarajat kiritish", 2 tadan yonma-yon), HR/Xodim UX 1-bosqich, Saturn moliyaviy guruh xabari muammosi, Founder nomzod kartasiga tug'ilgan sana, Kassa nazorati: Nazoratchi qarori, ish muhitini GitHub Actions Linux'ga o'tkazish — barchasi allaqachon shu branchda va PASSED.

## Hali tugallanmagan ish

- `tests/test_recruiting_bot_flow.py`da bu ishga aloqasi yo'q ~14 ta test avvaldan (mendan oldin ham) muvaffaqiyatsiz edi — hali tuzatilmagan, alohida masala.
- Production'dagi `8f492e2` deploy failure sababini alohida tekshirish hali qilinmagan (eski, mustaqil masala).
- `RECRUITING_BRANCH_NAMES` hamon placeholder qiymatlarda (`Filial-1,Filial-2`) — production'ga chiqishdan oldin haqiqiy filial nomlari kerak.
- `content/daily_greetings/morning_XX.jpg`/`night_XX.jpg` rasmlari hali Founder tomonidan qo'yilmagan.
- Founder menyusidagi "🏪 Do'konlar" tugmasi hozircha `/listusers`ga bog'langan (vaqtinchalik qaror) — haqiqiy filiallar ro'yxatiga bog'lash kerak.
- `fokus-ai-test` Render servisi hozir `56e8680`da live — bu commit aynan routing xatosini o'z ichiga oladi, `3b2ab42` (tuzatish) hali deploy qilinmagan.

## Keyingi bitta qadam

`3b2ab42`ni `fokus-ai-test` Render servisiga deploy qilib, real Telegramda kassir menyusini (tugma bosish + eski holatdan qochish) tekshirish.
