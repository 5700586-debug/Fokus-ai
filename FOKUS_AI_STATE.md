# FOKUS AI — joriy holat

Bu fayl doim JORIY holatni ko'rsatadi (eski tarix emas). Har muhim
ishdan keyin yangilanadi. Ziddiyat bo'lsa, haqiqiy Git/GitHub holati
(`git log`, GitHub Actions) ustuvor.

- **Branch:** `feature/hr-conversational-interview`
- **Commit:** `a7f817a` — "Add atomic guard to prevent duplicate cash-shift decision processing"
- **GitHub holati:** Sinxron — lokal HEAD va `origin`dagi shu branch bir xil.
- **Test natijasi:** GitHub Actions "Smoke tests" workflow (`ubuntu-latest`), commit `a7f817a` uchun — **PASSED** (run 32597257032: checkout, dependency install, haqiqiy `psycopg2` import, 15 ta test — barchasi muvaffaqiyatli).
- **Test muhiti:** GitHub Actions, Linux (`ubuntu-latest`).
  - `.github/workflows/smoke-tests.yml` — har pushda avtomatik, tez, kichik (haqiqiy `psycopg2` import + 4 ta muhim test).
  - `.github/workflows/tests.yml` — to'liq (900+) to'plam, endi FAQAT qo'lda ishga tushiriladi (Actions -> Tests -> Run workflow), har pushda emas.
  - Windows lokalda endi `pytest`/`pip install`/Python test ISHLATILMAYDI — faqat kod tahrirlash, `git status`/commit/push/pull.
- **Main/production holati:** `main` = `8f492e2`, tegilmagan. Production (`Fokus-ai` Render web service) va Render'ga umuman tegilmagan, deploy qilinmagan.

## Oxirgi tugallangan ish

- Kassa tafovuti/approval qarorlarida race-condition (bir xil amal ikki marta bajarilishi) yopildi: `repositories/cash_shifts.py`ga atomic `set_shift_status_if(shift_id, expected_status, status, ...)` qo'shildi (`UPDATE ... WHERE id = ? AND status = ?`, natija — `rowcount > 0`). `services/cash_shift.py`dagi `apply_supervisor_decision`/`confirm_handover` endi shu guard'dan foydalanadi va faqat muvaffaqiyatli bo'lganda `record_shift_approval` yozadi. `cash_shift_bot.py`dagi `handle_discrepancy_approve`/`_handle_review_decision` shu natijani tekshirib, muvaffaqiyatsiz bo'lsa "allaqachon hal qilingan" deb javob beradi.
- 3 ta yangi test qo'shildi: `tests/test_cash_shifts_repo.py::test_set_shift_status_if_only_updates_when_status_matches`, `tests/test_cash_shift_service.py::test_duplicate_supervisor_decision_only_applies_once`, `::test_duplicate_confirm_handover_only_succeeds_once` — ikkalasi ham "parallel" ikkinchi chaqiruv faqat bittasi muvaffaqiyatli bo'lishini va faqat bitta approval yozuvi qo'shilishini tasdiqlaydi. GitHub Actions Linux'da **PASSED** (run 32597257032, commit `a7f817a`).
- Kassir menyu routing xatosi (stale-state escape), kassir menyusini sodda qilish, HR/Xodim UX 1-bosqich, Saturn moliyaviy guruh xabari muammosi, Founder nomzod kartasiga tug'ilgan sana, Kassa nazorati: Nazoratchi qarori, ish muhitini GitHub Actions Linux'ga o'tkazish — barchasi allaqachon shu branchda va PASSED.

## Hali tugallanmagan ish

- `tests/test_recruiting_bot_flow.py`da bu ishga aloqasi yo'q ~14 ta test avvaldan (mendan oldin ham) muvaffaqiyatsiz edi — hali tuzatilmagan, alohida masala.
- Production'dagi `8f492e2` deploy failure sababini alohida tekshirish hali qilinmagan (eski, mustaqil masala).
- `RECRUITING_BRANCH_NAMES` hamon placeholder qiymatlarda (`Filial-1,Filial-2`) — production'ga chiqishdan oldin haqiqiy filial nomlari kerak.
- `content/daily_greetings/morning_XX.jpg`/`night_XX.jpg` rasmlari hali Founder tomonidan qo'yilmagan.
- Founder menyusidagi "🏪 Do'konlar" tugmasi hozircha `/listusers`ga bog'langan (vaqtinchalik qaror) — haqiqiy filiallar ro'yxatiga bog'lash kerak.
- `fokus-ai-test` Render servisi hozir eski `56e8680`da live (kassir-menyu routing xatosini ham, endi tuzatilgan race-conditionni ham o'z ichiga OLMAGAN commit) — `a7f817a` hali deploy qilinmagan, bu topshiriqda deploy so'ralmagan.
- Yengil arxitektura tekshiruvida (READ-ONLY) aniqlangan boshqa ochiq topilmalar hali tuzatilmagan: menyu navigatsiya tugmalari ("💰 Kassa" va h.k.) hali `_ClearStaleStateMiddleware`ning qochish-ro'yxatida yo'q (faqat kassir buyruq-tugmalari uchun tuzatilgan); `roles.py:find_user_by_role("nazoratchi")` global birinchi mosni qaytaradi (10+ filialda muammo bo'lishi mumkin).

## Keyingi bitta qadam

`a7f817a`ni `fokus-ai-test` Render servisiga deploy qilib, real Telegramda kassa tafovuti/approval oqimini tekshirish.
