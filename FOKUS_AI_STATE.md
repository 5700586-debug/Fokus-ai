# FOKUS AI — joriy holat

Bu fayl doim JORIY holatni ko'rsatadi (eski tarix emas). Har muhim
ishdan keyin yangilanadi. Ziddiyat bo'lsa, haqiqiy Git/GitHub holati
(`git log`, GitHub Actions) ustuvor.

- **Branch:** `feature/hr-conversational-interview`
- **Commit:** `9f3af53` — "Add atomic guard to prevent duplicate HR approval processing"
- **GitHub holati:** Sinxron — lokal HEAD va `origin`dagi shu branch bir xil.
- **Test natijasi:** GitHub Actions "Smoke tests" workflow (`ubuntu-latest`), commit `9f3af53` uchun — **PASSED** (run 32598951034: checkout, dependency install, haqiqiy `psycopg2` import, 16 ta test — barchasi muvaffaqiyatli).
- **Test muhiti:** GitHub Actions, Linux (`ubuntu-latest`).
  - `.github/workflows/smoke-tests.yml` — har pushda avtomatik, tez, kichik (haqiqiy `psycopg2` import + 4 ta muhim test).
  - `.github/workflows/tests.yml` — to'liq (900+) to'plam, endi FAQAT qo'lda ishga tushiriladi (Actions -> Tests -> Run workflow), har pushda emas.
  - Windows lokalda endi `pytest`/`pip install`/Python test ISHLATILMAYDI — faqat kod tahrirlash, `git status`/commit/push/pull.
- **Main/production holati:** `main` = `8f492e2`, tegilmagan. Production (`Fokus-ai` Render web service) va Render'ga umuman tegilmagan, deploy qilinmagan.

## Oxirgi tugallangan ish

- HR approval'da race-condition (Founder "✅ Tasdiqlash"ni ikki marta bossa rol/kalibratsiya/xabar qayta bajarilishi) yopildi: `employees.py`dagi `approve_profile` endi atomic (`UPDATE ... WHERE user_id = ? AND status = 'submitted'`, natija — `rowcount > 0`), muvaffaqiyatsiz bo'lsa `None` qaytaradi. `approval.py:handle_approve` shu natijani tekshiradi — `None` bo'lsa rol qayta berilmaydi, kalibratsiya qayta ishga tushmaydi, xodimga tasdiqlash xabari qayta yuborilmaydi.
- 1 ta yangi test qo'shildi: `tests/test_employees.py::test_duplicate_approve_only_succeeds_once` — bitta profilni ketma-ket ikki marta approve qilish faqat birinchisi muvaffaqiyatli bo'lishini tasdiqlaydi. GitHub Actions Linux'da **PASSED** (run 32598951034, commit `9f3af53`).
- Kassa tafovuti/approval qarorlaridagi xuddi shu turdagi race-condition oldin tuzatilgan (`repositories/cash_shifts.py::set_shift_status_if`, commit `a7f817a`), kassir menyu routing xatosi, kassir menyusini sodda qilish, HR/Xodim UX 1-bosqich, Saturn moliyaviy guruh xabari muammosi, Founder nomzod kartasiga tug'ilgan sana, Kassa nazorati: Nazoratchi qarori, ish muhitini GitHub Actions Linux'ga o'tkazish — barchasi allaqachon shu branchda va PASSED.

## Hali tugallanmagan ish

- `tests/test_recruiting_bot_flow.py`da bu ishga aloqasi yo'q ~14 ta test avvaldan (mendan oldin ham) muvaffaqiyatsiz edi — hali tuzatilmagan, alohida masala.
- Production'dagi `8f492e2` deploy failure sababini alohida tekshirish hali qilinmagan (eski, mustaqil masala).
- `RECRUITING_BRANCH_NAMES` hamon placeholder qiymatlarda (`Filial-1,Filial-2`) — production'ga chiqishdan oldin haqiqiy filial nomlari kerak.
- `content/daily_greetings/morning_XX.jpg`/`night_XX.jpg` rasmlari hali Founder tomonidan qo'yilmagan.
- Founder menyusidagi "🏪 Do'konlar" tugmasi hozircha `/listusers`ga bog'langan (vaqtinchalik qaror) — haqiqiy filiallar ro'yxatiga bog'lash kerak.
- `fokus-ai-test` Render servisi hozir eski `56e8680`da live (kassir-menyu routing xatosini, kassa va HR approval race-condition tuzatishlarining hech birini o'z ichiga OLMAGAN commit) — `9f3af53` hali deploy qilinmagan, bu topshiriqda deploy so'ralmagan.
- Yengil arxitektura tekshiruvida (READ-ONLY) aniqlangan boshqa ochiq topilmalar hali tuzatilmagan: menyu navigatsiya tugmalari ("💰 Kassa" va h.k.) hali `_ClearStaleStateMiddleware`ning qochish-ro'yxatida yo'q (faqat kassir buyruq-tugmalari uchun tuzatilgan); `roles.py:find_user_by_role("nazoratchi")` global birinchi mosni qaytaradi (10+ filialda muammo bo'lishi mumkin).

## Keyingi bitta qadam

`9f3af53`ni `fokus-ai-test` Render servisiga deploy qilib, real Telegramda HR approval va kassa tafovuti/approval oqimlarini tekshirish.
