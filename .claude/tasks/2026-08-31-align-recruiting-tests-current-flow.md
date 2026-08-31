# Recruiting testlarini hozirgi real oqimga moslash

MUHIT:
- Windows, PowerShell, CMD va local Git Bash ishlatma.
- Faqat remote GitHub Actions `ubuntu-latest` + `bash`.
- Repo: `5700586-debug/Fokus-ai`
- Branch: `feature/hr-conversational-interview`
- Checkpoint: `cad95209de6383d1dcc8f7c8b88c3a0f596a46bf`
- `main`, production, `.env` va secretlarga tegma.

VAZIFA:

Faqat `tests/test_recruiting_bot_flow.py`ni o'zgartir.

Hozir shu fayldagi 22 ta test yiqilmoqda. Ma'lum sabablar:

1. `/apply` boshlanishidan oldin vakansiyaga filial biriktirilmagan.
2. Testlar eski savollar tartibi va faqat `2000` yil javobidan foydalanmoqda.
3. Ayrim testlar hozirgi biznes matniga mos bo'lmagan eski command yoki noto'g'ri substring assertion ishlatmoqda.

Manba sifatida faqat quyidagilarni o'qi:

- `recruiting_bot.py`: `_STEPS_B_C`, `_STEPS_D` va maxsus follow-up qoidalari;
- `repositories/recruiting.py`: mavjud vacancy/branch funksiyalari;
- `main.py`: faqat Founder job-ad funksiyalari;
- `tests/test_recruiting_bot_flow.py`: ishlayotgan `_reach_prev_employer_step()` namunasi.

ANIQ TUZATISHLAR:

1. `_start_and_consent()` ichida `/apply`dan oldin Kassir vakansiyasini aktiv qil va faqat filiali bo'lmasa bitta test filialini biriktir.

   Buni global/autouse fixture'da qilma. Quyidagi test o'zining filialsiz holatini saqlashi shart:

   `test_apply_hides_active_vacancy_with_no_branches`

2. `_answer_basics()`:

   - `birth_year` parametrini `birth_date`ga almashtir;
   - standart qiymat: `12.10.2000`;
   - oddiy oqimlarda faqat yil yuborma.

3. `_answer_fit_filter()`ni real tartibga mosla:

   - `shift_preference`
   - `holiday_available`
   - `prev_salary`
   - `expected_salary`
   - `accommodation_needed`

   Eski `unavailable_days` va `commute_issue` qadamlarini olib tashla.

   `accommodation_needed=yes` — oddiy davom etish.
   `accommodation_needed=no` — qulaylik follow-up'i.

4. `_answer_experience()`ni real tartibga mosla:

   - `prev_employer`
   - `experience_duration`
   - `job_stability`
   - `leave_reason`
   - `pos_experience`
   - `cash_handling`
   - `reference_check_consent`
   - `retention_intent:1yil_plus`
   - `attendance_barrier`
   - `substance_policy:yes`
   - `criminal_record:no`

5. Helperdan tashqarida qolgan oddiy `2000` javoblarini ham `12.10.2000`ga almashtir.

   Yosh bola testida to'liq sana yarat. Faqat yil kiritishni maxsus tekshiradigan test bo'lsa, u kun va oy qayta so'ralishini tekshirishda davom etsin.

6. Bekor qilish testi hozirgi real command — `/cancel`ni ishlatsin. Eski ko'rinadigan bekor qilish matniga tayanmasin.

7. Accommodation follow-up testi `no` variantini yuborsin.

8. Job-ad matnida:

   `"Navoiy" not in ad_text`

   assertionini ishlatma, chunki Derizlik manzilining o'zida “Alisher Navoiy” bor. Tanlanmagan filialning alohida e'lon qatori yo'qligini aniq tekshir.

CHEGARALAR:

- Production kodini o'zgartirma.
- Testni o'chirma yoki `skip` qilma.
- Assertionni ma'nosiz yumshatma.
- Har bir test o'z DB holatini aniq tayyorlasin.
- Agar qolgan failure production kodidagi haqiqiy bug bo'lsa, productionni tuzatma; bitta aniq sabab bilan STOP qil.
- Boshqa 17 ta Smoke va 5 ta E2E xatosiga tegma.

TEKSHIRUV:

Faqat:

`python -m pytest -q tests/test_recruiting_bot_flow.py`

Pytest mavjud bo'lmasa, faqat `requirements-dev.txt`ni o'rnat.

Full test, Smoke va E2E'ni qo'lda ishga tushirma.

PASS bo'lsa:

- commit: `test: align recruiting flow tests with current interview`
- faqat `feature/hr-conversational-interview` branchiga push qil;
- avtomatik workflowni PASS deb taxmin qilma;
- keyingi vazifaga o'tma.

Yakuniy javobda faqat commit, o'zgargan fayl, targeted test natijasi va push holatini yoz.
