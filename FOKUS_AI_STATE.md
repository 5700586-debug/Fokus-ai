# FOKUS AI — joriy holat

Bu fayl doim JORIY holatni ko'rsatadi (eski tarix emas). Har muhim
ishdan keyin yangilanadi. Ziddiyat bo'lsa, haqiqiy Git/GitHub holati
(`git log`, GitHub Actions) ustuvor.

- **Branch:** `feature/hr-conversational-interview`
- **Commit:** `f52d960` — "Add multi-worker idempotency guard to post-hire flow"
- **GitHub holati:** Sinxron — lokal HEAD va `origin`dagi shu branch bir xil.
- **Test natijasi:** GitHub Actions "Smoke tests" workflow (`ubuntu-latest`), commit `f52d960` uchun — **PASSED** (run 32600613439: checkout, dependency install, haqiqiy `psycopg2` import, 20 ta test — barchasi muvaffaqiyatli).
- **Test muhiti:** GitHub Actions, Linux (`ubuntu-latest`).
  - `.github/workflows/smoke-tests.yml` — har pushda avtomatik, tez, kichik (haqiqiy `psycopg2` import + 4 ta muhim test).
  - `.github/workflows/tests.yml` — to'liq (900+) to'plam, endi FAQAT qo'lda ishga tushiriladi (Actions -> Tests -> Run workflow), har pushda emas.
  - Windows lokalda endi `pytest`/`pip install`/Python test ISHLATILMAYDI — faqat kod tahrirlash, `git status`/commit/push/pull.
- **Main/production holati:** `main` = `8f492e2`, tegilmagan. Production (`Fokus-ai` Render web service) va Render'ga umuman tegilmagan, deploy qilinmagan.

## Oxirgi tugallangan ish

- Post-hire oqimining multi-worker idempotentligi tuzatildi: `handle_hire` ilgari `employees.submit_profile`ni (har doim statusni `'submitted'`ga qaytaruvchi) `employees.approve_profile`dan OLDIN shartsiz chaqirardi — READ-ONLY tekshiruvda aniqlanganidek, bu ikki parallel worker holatida atomik `approve_profile` himoyasini chetlab o'tishi mumkin edi. Endi `repositories/recruiting.py::set_founder_decision_if(application_id, expected_status, decision, decided_by)` (atomic `UPDATE ... WHERE id = ? AND status = ?`, natija — `rowcount > 0`) arizani `employees.submit_profile`ga yetib borishdan OLDIN "band qiladi" — yutqazgan parallel urinish darhol chiqib ketadi, xodim yozuvini qayta `'submitted'`ga tushirmaydi, rol/menyu/xabar side-effectlarini bajarmaydi.
- 2 ta yangi test qo'shildi: `tests/test_recruiting_permissions.py::test_set_founder_decision_if_only_claims_when_status_matches` (atomic mexanizmning o'zi), `::test_hire_does_not_touch_employees_when_application_already_claimed` (ariza allaqachon band qilingan bo'lsa `employees` jadvaliga umuman tegilmasligi). GitHub Actions Linux'da **PASSED** (run 32600613439, commit `f52d960`).
- Post-hire oqimi (commit `692009b`), HR approval va kassa tafovuti/approval qarorlaridagi race-condition tuzatishlari (commit `9f3af53`, `a7f817a`), kassir menyu routing xatosi, kassir menyusini sodda qilish, HR/Xodim UX 1-bosqich, Saturn moliyaviy guruh xabari muammosi, Founder nomzod kartasiga tug'ilgan sana, Kassa nazorati: Nazoratchi qarori, ish muhitini GitHub Actions Linux'ga o'tkazish — barchasi allaqachon shu branchda va PASSED.

## Hali tugallanmagan ish

- `tests/test_recruiting_bot_flow.py`da bu ishga aloqasi yo'q ~14 ta test avvaldan (mendan oldin ham) muvaffaqiyatsiz edi — hali tuzatilmagan, alohida masala.
- Production'dagi `8f492e2` deploy failure sababini alohida tekshirish hali qilinmagan (eski, mustaqil masala).
- `RECRUITING_BRANCH_NAMES` hamon placeholder qiymatlarda (`Filial-1,Filial-2`) — production'ga chiqishdan oldin haqiqiy filial nomlari kerak.
- `content/daily_greetings/morning_XX.jpg`/`night_XX.jpg` rasmlari hali Founder tomonidan qo'yilmagan.
- Founder menyusidagi "🏪 Do'konlar" tugmasi hozircha `/listusers`ga bog'langan (vaqtinchalik qaror) — haqiqiy filiallar ro'yxatiga bog'lash kerak.
- `fokus-ai-test` Render servisi hozir eski `56e8680`da live (kassir-menyu routing, kassa/HR approval race-condition tuzatishlari, post-hire oqimi va uning multi-worker himoyasining hech birini o'z ichiga OLMAGAN commit) — `f52d960` hali deploy qilinmagan, bu topshiriqda deploy so'ralmagan.
- READ-ONLY tekshiruvda aniqlangan, HALI tuzatilmagan qolgan topilmalar: `handle_hire`ning bir-slotli rol tekshiruvi/karta-yuborish bloki `approval.py:handle_approve`dan umumiy funksiyaga chiqarilmasdan nusxalangan; `handle_hire` `calibration_bot.on_employee_approved`ni chaqirmaydi (hozircha zararsiz — recruiting faqat "kassir"/"sotuvchi" beradi, `_TARGET_ROLES`da yo'q); `roles.set_role`ning qaytgan qiymati tekshirilmaydi (ikkalasida ham, eski kamchilik). Bular alohida so'ralmaguncha tegilmadi.
- Yengil arxitektura tekshiruvida (READ-ONLY) aniqlangan boshqa ochiq topilmalar hali tuzatilmagan: menyu navigatsiya tugmalari ("💰 Kassa" va h.k.) hali `_ClearStaleStateMiddleware`ning qochish-ro'yxatida yo'q; `roles.py:find_user_by_role("nazoratchi")` global birinchi mosni qaytaradi (10+ filialda muammo bo'lishi mumkin).

## Keyingi bitta qadam

`f52d960`ni `fokus-ai-test` Render servisiga deploy qilib, real Telegramda "🎯 Ishga olish" oqimini (rol/filial biriktirilishi, Xodimlar ro'yxati, avtomatik menyu) tekshirish.
