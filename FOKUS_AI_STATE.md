# FOKUS AI — joriy holat

Bu fayl doim JORIY holatni ko'rsatadi (eski tarix emas). Har muhim
ishdan keyin yangilanadi. Ziddiyat bo'lsa, haqiqiy Git/GitHub holati
(`git log`, GitHub Actions) ustuvor.

- **Branch:** `feature/hr-conversational-interview`
- **Commit:** `56e8680` — "Simplify kassir menu button labels and pair them two-per-row"
- **GitHub holati:** Sinxron — lokal HEAD va `origin`dagi shu branch bir xil.
- **Test natijasi:** GitHub Actions "Smoke tests" workflow (`ubuntu-latest`), commit `56e8680` uchun — **PASSED** (run 32594291185: checkout, dependency install, haqiqiy `psycopg2` import, 10 ta test — barchasi muvaffaqiyatli).
- **Test muhiti:** GitHub Actions, Linux (`ubuntu-latest`).
  - `.github/workflows/smoke-tests.yml` — har pushda avtomatik, tez, kichik (haqiqiy `psycopg2` import + 4 ta muhim test).
  - `.github/workflows/tests.yml` — to'liq (900+) to'plam, endi FAQAT qo'lda ishga tushiriladi (Actions -> Tests -> Run workflow), har pushda emas.
  - Windows lokalda endi `pytest`/`pip install`/Python test ISHLATILMAYDI — faqat kod tahrirlash, `git status`/commit/push/pull.
- **Main/production holati:** `main` = `8f492e2`, tegilmagan. Production (`Fokus-ai` Render web service) va Render'ga umuman tegilmagan, deploy qilinmagan.

## Oxirgi tugallangan ish

- Kassir menyusini sodda qil: `/openshift`/`/closeshift`/`/expense` tugmalari endi kassir uchun "🟢 Smenani boshlash"/"🔴 Smenani topshirish"/"💸 Xarajat kiritish" sifatida ko'rinadi, 2 tadan yonma-yon; eski buyruqlar orqada o'zgarishsiz ishlaydi (mavjud stale-label normalizatsiya xaritasi orqali). Boshqa rollar menyusiga tegilmagan.
- Shu tuzatish uchun 2 ta test qo'shilgan (`tests/test_menu_and_fsm_escape.py::test_kassir_menu_buttons_are_paired_two_per_row`, `::test_kassir_friendly_button_still_triggers_real_command`) va bir nechta eski kassir-menyu testi yangi matnlarga moslab yangilangan; GitHub Actions Linux'da **PASSED** (run 32594291185, commit `56e8680`).
- HR/Xodim UX 1-bosqich (menyu `is_persistent=True`, tasdiqdan keyin "/start" so'ralmasligi), Saturn moliyaviy guruh xabari muammosi, Founder nomzod kartasiga tug'ilgan sana, Kassa nazorati: Nazoratchi qarori, ish muhitini GitHub Actions Linux'ga o'tkazish — barchasi allaqachon shu branchda va PASSED.

## Hali tugallanmagan ish

- `tests/test_recruiting_bot_flow.py`da bu ishga aloqasi yo'q ~14 ta test avvaldan (mendan oldin ham) muvaffaqiyatsiz edi — hali tuzatilmagan, alohida masala.
- Production'dagi `8f492e2` deploy failure sababini alohida tekshirish hali qilinmagan (eski, mustaqil masala).
- `RECRUITING_BRANCH_NAMES` hamon placeholder qiymatlarda (`Filial-1,Filial-2`) — production'ga chiqishdan oldin haqiqiy filial nomlari kerak.
- `content/daily_greetings/morning_XX.jpg`/`night_XX.jpg` rasmlari hali Founder tomonidan qo'yilmagan.
- Founder menyusidagi "🏪 Do'konlar" tugmasi hozircha `/listusers`ga bog'langan (vaqtinchalik qaror) — haqiqiy filiallar ro'yxatiga bog'lash kerak.
- `fokus-ai-test` Render servisiga `56e8680` hali deploy qilinmagan (bu topshiriqda deploy so'ralmagan).

## Keyingi bitta qadam

`56e8680`ni `fokus-ai-test` Render servisiga deploy qilib, real Telegramda tekshirish (keyin `🏪 Do'konlar` tugmasini haqiqiy filiallar ro'yxatiga bog'lash).
