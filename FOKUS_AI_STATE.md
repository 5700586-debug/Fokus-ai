# FOKUS AI — joriy holat

Bu fayl doim JORIY holatni ko'rsatadi (eski tarix emas). Har muhim
ishdan keyin yangilanadi. Ziddiyat bo'lsa, haqiqiy Git/GitHub holati
(`git log`, GitHub Actions) ustuvor.

- **Branch:** `feature/hr-conversational-interview`
- **Commit:** `692009b` — "Add post-hire flow: recruiting candidates become active employees on hire"
- **GitHub holati:** Sinxron — lokal HEAD va `origin`dagi shu branch bir xil.
- **Test natijasi:** GitHub Actions "Smoke tests" workflow (`ubuntu-latest`), commit `692009b` uchun — **PASSED** (run 32599711063: checkout, dependency install, haqiqiy `psycopg2` import, 18 ta test — barchasi muvaffaqiyatli).
- **Test muhiti:** GitHub Actions, Linux (`ubuntu-latest`).
  - `.github/workflows/smoke-tests.yml` — har pushda avtomatik, tez, kichik (haqiqiy `psycopg2` import + 4 ta muhim test).
  - `.github/workflows/tests.yml` — to'liq (900+) to'plam, endi FAQAT qo'lda ishga tushiriladi (Actions -> Tests -> Run workflow), har pushda emas.
  - Windows lokalda endi `pytest`/`pip install`/Python test ISHLATILMAYDI — faqat kod tahrirlash, `git status`/commit/push/pull.
- **Main/production holati:** `main` = `8f492e2`, tegilmagan. Production (`Fokus-ai` Render web service) va Render'ga umuman tegilmagan, deploy qilinmagan.

## Oxirgi tugallangan ish

- Post-hire oqimi yakunlandi: Founder nomzod kartasiga yangi "🎯 Ishga olish" tugmasi qo'shildi (`services/recruiting_card.py::candidate_review_keyboard`, `rec_hire:` callback). `recruiting_bot.py`dagi yangi `handle_hire` MAVJUD xodim mexanizmini to'liq qayta ishlatadi — yangi parallel tizim yo'q: `employees.submit_profile` + (endi atomic) `employees.approve_profile` bilan xuddi invite-onboarding kabi `employees` qatori yaratiladi/tasdiqlanadi, `roles.set_role` orqali lavozim (va single-slot bo'lmasa filial) biriktiriladi, xodim darhol "👥 Xodimlar" ro'yxatida (`roles.list_users()`) ko'rinadi, va `main.greeting_for_user`/`build_menu` orqali `/start` so'ramasdan menyu avtomatik yuboriladi. Recruiting tarixi mavjud `repositories/recruiting.py::set_founder_decision(application_id, "hired", ...)` orqali saqlanadi (ariza yozuvi o'chirilmaydi/qayta yozilmaydi).
- 2 ta yangi test qo'shildi: `tests/test_recruiting_permissions.py::test_founder_hire_creates_active_employee_with_role_branch_and_auto_menu`, `::test_double_hire_click_does_not_crash_or_duplicate`. GitHub Actions Linux'da **PASSED** (run 32599711063, commit `692009b`).
- HR approval va kassa tafovuti/approval qarorlaridagi race-condition tuzatishlari (commit `9f3af53`, `a7f817a`), kassir menyu routing xatosi, kassir menyusini sodda qilish, HR/Xodim UX 1-bosqich, Saturn moliyaviy guruh xabari muammosi, Founder nomzod kartasiga tug'ilgan sana, Kassa nazorati: Nazoratchi qarori, ish muhitini GitHub Actions Linux'ga o'tkazish — barchasi allaqachon shu branchda va PASSED.

## Hali tugallanmagan ish

- `tests/test_recruiting_bot_flow.py`da bu ishga aloqasi yo'q ~14 ta test avvaldan (mendan oldin ham) muvaffaqiyatsiz edi — hali tuzatilmagan, alohida masala.
- Production'dagi `8f492e2` deploy failure sababini alohida tekshirish hali qilinmagan (eski, mustaqil masala).
- `RECRUITING_BRANCH_NAMES` hamon placeholder qiymatlarda (`Filial-1,Filial-2`) — production'ga chiqishdan oldin haqiqiy filial nomlari kerak.
- `content/daily_greetings/morning_XX.jpg`/`night_XX.jpg` rasmlari hali Founder tomonidan qo'yilmagan.
- Founder menyusidagi "🏪 Do'konlar" tugmasi hozircha `/listusers`ga bog'langan (vaqtinchalik qaror) — haqiqiy filiallar ro'yxatiga bog'lash kerak.
- `fokus-ai-test` Render servisi hozir eski `56e8680`da live (kassir-menyu routing, kassa/HR approval race-condition tuzatishlari va post-hire oqimining hech birini o'z ichiga OLMAGAN commit) — `692009b` hali deploy qilinmagan, bu topshiriqda deploy so'ralmagan.
- "Ishga olish" tugmasi faqat ariza `awaiting_review` holatida bo'lsa ishlaydi (sibling qarorlar — interview/reviewing/reject — bilan bir xil qoida); Founder avval "📞 Suhbatga chaqirish"/"🗂 Ko'rib chiqish" bossa, tugmalar o'sha xabardan yo'qoladi va hire endi shu kartadan qilinmaydi — bu eski, mustaqil UX cheklovi, alohida so'ralmaguncha tegilmadi.
- Yengil arxitektura tekshiruvida (READ-ONLY) aniqlangan boshqa ochiq topilmalar hali tuzatilmagan: menyu navigatsiya tugmalari ("💰 Kassa" va h.k.) hali `_ClearStaleStateMiddleware`ning qochish-ro'yxatida yo'q; `roles.py:find_user_by_role("nazoratchi")` global birinchi mosni qaytaradi (10+ filialda muammo bo'lishi mumkin).

## Keyingi bitta qadam

`692009b`ni `fokus-ai-test` Render servisiga deploy qilib, real Telegramda "🎯 Ishga olish" oqimini (rol/filial biriktirilishi, Xodimlar ro'yxati, avtomatik menyu) tekshirish.
