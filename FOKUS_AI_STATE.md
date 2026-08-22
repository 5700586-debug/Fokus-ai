# FOKUS AI — joriy holat

Bu fayl doim JORIY holatni ko'rsatadi (eski tarix emas). Har muhim
ishdan keyin yangilanadi. Ziddiyat bo'lsa, haqiqiy Git/GitHub holati
(`git log`, GitHub Actions) ustuvor.

- **Branch:** `feature/hr-conversational-interview`
- **Commit:** `6414327` — "Check roles.set_role return value in approval/hire flows (P1 HR consistency)"
- **GitHub holati:** Sinxron — lokal HEAD va `origin`dagi shu branch bir xil.
- **Test natijasi:** GitHub Actions "Smoke tests" workflow (`ubuntu-latest`), commit `6414327` uchun — **PASSED** (run 32602076023: checkout, dependency install, haqiqiy `psycopg2` import, 24 ta test — barchasi muvaffaqiyatli).
- **Test muhiti:** GitHub Actions, Linux (`ubuntu-latest`).
  - `.github/workflows/smoke-tests.yml` — har pushda avtomatik, tez, kichik (haqiqiy `psycopg2` import + 4 ta muhim test).
  - `.github/workflows/tests.yml` — to'liq (900+) to'plam, endi FAQAT qo'lda ishga tushiriladi (Actions -> Tests -> Run workflow), har pushda emas.
  - Windows lokalda endi `pytest`/`pip install`/Python test ISHLATILMAYDI — faqat kod tahrirlash, `git status`/commit/push/pull.
- **Main/production holati:** `main` = `8f492e2`, tegilmagan. Production (`Fokus-ai` Render web service) va Render'ga umuman tegilmagan, deploy qilinmagan.

## Oxirgi tugallangan ish

**Overnight P0/P1 system hardening** (Senior Backend Architect uslubida to'liq audit + tuzatish, 4 ta alohida commit):

- 🔴 **P0 (moliyaviy):** `discipline_bot.py::baholash_enter_rule` FSM holatni tozalab, haqiqiy AI so'rovini kutgach jarima yozardi — DB darajasida UNIQUE cheklov yo'q (bir kunda bir nechta HAQIQIY jarima qonuniy), shuning uchun bir xil nazoratchidan deyarli bir vaqtda kelgan ikkinchi xabar `bonus_bank`ni ikki marta kamaytirishi mumkin edi. Jarayon-ichi atomic guard (`_PENDING_PENALTY_APPLICATIONS`) qo'shildi (commit `2e1cf36`).
- 🟠 **P1 (routing):** Asosiy menyu navigatsiya tugmalari ("💰 Kassa", "👥 Xodimlar" va h.k.) `_ClearStaleStateMiddleware`ning qochish-ro'yxatida yo'q edi — foydalanuvchi ko'p bosqichli oqimda qolib ketib shu tugmalarni bossa, eski holat yutib olardi. `_TOP_LEVEL_NAV_TEXTS` qo'shildi (commit `165effb`).
- 🟠 **P1 (kassa):** `/closeshift` tasdiqlash va `/expense` yakunlash bosqichlarida double-submit himoyasi yo'q edi (ikki marta bosish `retry_count`ni ikki marta oshirishi yoki xarajatni ikki marta yozishi mumkin edi). Jarayon-ichi guard qo'shildi (commit `9fbbe50`).
- 🟠 **P1 (HR):** `approval.py`/`recruiting_bot.py` `roles.set_role`ning qaytgan qiymatini tekshirmasdi — DB darajasidagi race holatida xodim "approved" bo'lib qolib, lekin rolisiz, unga baribir muvaffaqiyat xabari/menyu yuborilardi. Endi natija tekshiriladi (commit `6414327`).
- 6 ta yangi regression test qo'shildi (har biri o'z commitida). GitHub Actions Linux'da **PASSED** (run 32602076023, commit `6414327`, 24 ta test).
- Read-only audit (3 parallel research agent orqali) shuni ham tasdiqladi: Saturn moliyaviy guruh xabari muammosi hali tuzatilgan holatda qoladi (regressiya yo'q); scheduler'lar duplicate-run'dan APScheduler'ning o'zi (`max_instances=1`) himoyalaydi; cross-branch ma'lumot aralashuvi topilmadi.
- Post-hire oqimi va uning multi-worker himoyasi (commit `692009b`, `f52d960`), HR approval va kassa tafovuti/approval qarorlaridagi race-condition tuzatishlari (commit `9f3af53`, `a7f817a`), kassir menyu routing xatosi, kassir menyusini sodda qilish, HR/Xodim UX 1-bosqich, Saturn moliyaviy guruh xabari muammosi, Founder nomzod kartasiga tug'ilgan sana, Kassa nazorati: Nazoratchi qarori, ish muhitini GitHub Actions Linux'ga o'tkazish — barchasi allaqachon shu branchda va PASSED.

## Hali tugallanmagan ish

- 🟡 **P2 (keyinroq, yangi feature kerak):** Kassa smenasi `PENDING_HANDOVER`/`NEEDS_SUPERVISOR_APPROVAL` holatida abadiy qolib ketishi mumkin (filial tashlab ketilsa) — hech qanday admin/Founder majburiy yopish buyrug'i yo'q. Yangi feature talab qiladi, shu vazifada QILINMADI.
- 🟡 **P2:** `handle_hire` (`recruiting_bot.py`) `approval.py:handle_approve`dagi mantiqni (bir-slotli rol tekshiruvi, karta-yuborish blogi) umumiy funksiyaga chiqarmasdan nusxalaydi; `calibration_bot.on_employee_approved`ni chaqirmaydi (hozircha zararsiz — recruiting faqat "kassir"/"sotuvchi" beradi, `_TARGET_ROLES`da yo'q).
- 🟡 **P2:** `roles.py:find_user_by_role` global birinchi mosni qaytaradi — 10+ filialda muammo bo'lishi mumkin (masalan `discipline_bot.py`dagi kunlik yopish nazoratchini shu orqali topadi).
- `tests/test_recruiting_bot_flow.py`da bu ishga aloqasi yo'q ~14 ta test avvaldan (mendan oldin ham) muvaffaqiyatsiz edi — hali tuzatilmagan, alohida masala.
- Production'dagi `8f492e2` deploy failure sababini alohida tekshirish hali qilinmagan (eski, mustaqil masala).
- `RECRUITING_BRANCH_NAMES` hamon placeholder qiymatlarda (`Filial-1,Filial-2`) — production'ga chiqishdan oldin haqiqiy filial nomlari kerak.
- `content/daily_greetings/morning_XX.jpg`/`night_XX.jpg` rasmlari hali Founder tomonidan qo'yilmagan.
- Founder menyusidagi "🏪 Do'konlar" tugmasi hozircha `/listusers`ga bog'langan (vaqtinchalik qaror) — haqiqiy filiallar ro'yxatiga bog'lash kerak.
- `fokus-ai-test` Render servisi hozir eski `56e8680`da live (shu overnight hardening'dagi TO'RTTA tuzatishning hech birini, post-hire oqimi va uning multi-worker himoyasini ham o'z ichiga OLMAGAN commit) — `6414327` hali deploy qilinmagan, bu topshiriqda deploy so'ralmagan.

## Keyingi bitta qadam

`6414327`ni `fokus-ai-test` Render servisiga deploy qilib, real Telegramda barcha tuzatilgan oqimlarni (nazoratchi jarimasi, kassa yopish/xarajat, HR approval/hire) tekshirish.
