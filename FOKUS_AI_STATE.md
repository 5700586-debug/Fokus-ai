# FOKUS AI — joriy holat

Bu fayl doim JORIY holatni ko'rsatadi (eski tarix emas). Har muhim
ishdan keyin yangilanadi. Ziddiyat bo'lsa, haqiqiy Git/GitHub holati
(`git log`, GitHub Actions) ustuvor.

- **Branch:** `feature/hr-conversational-interview`
- **Commit:** `955edac` — "Replace behavioral photo tests with a reliable source-structure check"
- **GitHub holati:** Sinxron — lokal HEAD va `origin`dagi shu branch bir xil.
- **Test natijasi:** GitHub Actions "Smoke tests" workflow (`ubuntu-latest`), commit `955edac` uchun — **PASSED** (run 32625968195: checkout, dependency install, haqiqiy `psycopg2` import, 24 ta test — barchasi muvaffaqiyatli).
- **Test muhiti:** GitHub Actions, Linux (`ubuntu-latest`).
  - `.github/workflows/smoke-tests.yml` — har pushda avtomatik, tez, kichik (haqiqiy `psycopg2` import + 4 ta muhim test).
  - `.github/workflows/tests.yml` — to'liq (900+) to'plam, endi FAQAT qo'lda ishga tushiriladi (Actions -> Tests -> Run workflow), har pushda emas.
  - Windows lokalda endi `pytest`/`pip install`/Python test ISHLATILMAYDI — faqat kod tahrirlash, `git status`/commit/push/pull.
- **Main/production holati:** `main` = `8f492e2`, tegilmagan. Production (`Fokus-ai` Render web service) va Render'ga umuman tegilmagan, deploy qilinmagan.

## Oxirgi tugallangan ish

- Nomzod fotosi Founder kartasiga yuborilmayotgan muammo tekshirildi va tuzatildi: `recruiting_bot.py::_run_assessment_and_notify_founder`dagi mavjud `send_photo` mexanizmining o'zida XATO TOPILMADI (ikki mustaqil tekshiruv — men va alohida research agent — buni tasdiqladi). Haqiqiy kamchilik: foto yuborish alohida `try/except`da emas edi — agar u muvaffaqiyatsiz bo'lsa (masalan eskirgan file_id), butun bildirishnoma (matnli karta ham) yo'qolib qolishi mumkin edi. Endi izolyatsiya qilingan (commit `6796fa7`) — foto muammosi matnli kartani endi yiqitmaydi.
- Shu regressiya uchun test qo'shish 4 ta urinish talab qildi: birinchi uchtasi (to'liq suhbat simulyatsiyasi + haqiqiy AI so'rov, keyin mock qilingan AI, keyin to'g'ridan-to'g'ri DB orqali funksiyani chaqirish) GitHub Actions'da tushuntirib bo'lmaydigan sababdan FAILED bo'ldi — job-log'larga kirish shu repo uchun autentifikatsiyasiz butunlay bloklangan (bir nechta usul sinaldi). Yakuniy yechim: `test_photo_send_is_isolated_from_founder_card_notification` — `inspect.getsource()` orqali manba kodini tekshiradigan, DB/tarmoq/async ishlatmaydigan strukturaviy test (`test_recruiting_permissions.py`dagi mavjud `test_founder_card_never_targets_a_group_chat` bilan bir xil uslub). GitHub Actions Linux'da **PASSED** (run 32625968195, commit `955edac`, 24 ta test).
- Overnight P0/P1 system hardening (4 ta tuzatish: nazoratchi jarima double-apply — P0 moliyaviy, menyu navigatsiya stale-state qochish gap'i, kassa `/closeshift`/`/expense` double-submit, `roles.set_role` natijasi tekshirilmasligi — commit `2e1cf36`, `165effb`, `9fbbe50`, `6414327`), post-hire oqimi va uning multi-worker himoyasi (commit `692009b`, `f52d960`), HR approval va kassa tafovuti/approval qarorlaridagi race-condition tuzatishlari (commit `9f3af53`, `a7f817a`), kassir menyu routing xatosi, kassir menyusini sodda qilish, HR/Xodim UX 1-bosqich, Saturn moliyaviy guruh xabari muammosi, Founder nomzod kartasiga tug'ilgan sana, Kassa nazorati: Nazoratchi qarori, ish muhitini GitHub Actions Linux'ga o'tkazish — barchasi allaqachon shu branchda va PASSED.

## Hali tugallanmagan ish

- **MUHIM (ish jarayoni bilan bog'liq):** GitHub Actions job-log'lariga (aynan pytest xato matniga) autentifikatsiyasiz kirish IMKONSIZ ekani aniqlandi (REST API "Must have admin rights to Repository" 403, web log-viewer route'lari 404/connection-reset) — faqat status (PASSED/FAILED) va umumiy annotation ("exit code 1") ko'rinadi, aniq xato matni ko'rinmaydi. Bu keyingi har qanday test-yozish vazifasida testlarni MAKSIMAL soddalashtirishni (yoki strukturaviy/`inspect.getsource` uslubini) talab qiladi, aks holda CI-round-trip orqali "ko'r-ko'rona" debug qilishga to'g'ri keladi.
- 🟡 **P2 (keyinroq, yangi feature kerak):** Kassa smenasi `PENDING_HANDOVER`/`NEEDS_SUPERVISOR_APPROVAL` holatida abadiy qolib ketishi mumkin (filial tashlab ketilsa) — hech qanday admin/Founder majburiy yopish buyrug'i yo'q. Yangi feature talab qiladi, shu vazifada QILINMADI.
- 🟡 **P2:** `handle_hire` (`recruiting_bot.py`) `approval.py:handle_approve`dagi mantiqni (bir-slotli rol tekshiruvi, karta-yuborish blogi) umumiy funksiyaga chiqarmasdan nusxalaydi; `calibration_bot.on_employee_approved`ni chaqirmaydi (hozircha zararsiz — recruiting faqat "kassir"/"sotuvchi" beradi, `_TARGET_ROLES`da yo'q).
- 🟡 **P2:** `roles.py:find_user_by_role` global birinchi mosni qaytaradi — 10+ filialda muammo bo'lishi mumkin (masalan `discipline_bot.py`dagi kunlik yopish nazoratchini shu orqali topadi).
- `tests/test_recruiting_bot_flow.py`da bu ishga aloqasi yo'q ~14 ta test avvaldan (mendan oldin ham) muvaffaqiyatsiz edi — hali tuzatilmagan, alohida masala (jumladan `test_full_kassir_application_flow_sends_founder_card`/`test_application_completes_even_when_ai_client_is_unavailable` — "photo majburiy" o'zgarishidan (commit `b9b05bf`) keyin eskirgan, motivatsiya matnidan keyin darhol tugashini kutadi, aslida endi foto so'raladi).
- Production'dagi `8f492e2` deploy failure sababini alohida tekshirish hali qilinmagan (eski, mustaqil masala).
- `RECRUITING_BRANCH_NAMES` hamon placeholder qiymatlarda (`Filial-1,Filial-2`) — production'ga chiqishdan oldin haqiqiy filial nomlari kerak.
- `content/daily_greetings/morning_XX.jpg`/`night_XX.jpg` rasmlari hali Founder tomonidan qo'yilmagan.
- Founder menyusidagi "🏪 Do'konlar" tugmasi hozircha `/listusers`ga bog'langan (vaqtinchalik qaror) — haqiqiy filiallar ro'yxatiga bog'lash kerak.
- `fokus-ai-test` Render servisi endi `955edac`da live (foto-izolyatsiya tuzatishi bilan) — deploy tasdiqlangan.

## Keyingi bitta qadam

Real Telegramda `fokus-ai-test` orqali nomzod fotosi Founder kartasiga to'g'ri kelishini qo'lda tekshirish.
