# Fokus HR — suhbatdosh darajasiga olib chiqish (WIP checkpoint)

Branch: `feature/hr-conversational-interview` (asosi: `main`, hozircha main/Render/production'ga tegilmagan).

## Nima uchun bu ish boshlandi

Real Telegram sinovida topilgan muammolar (foydalanuvchi xabaridan):
1. Bot oddiy anketa kabi ishladi, jonli HR suhbati bo'lmadi.
2. Imloviy xato/sheva/tushunarsiz javobni AI aniqlashtirmadi.
3. Qo'shimcha savollar rasmiy chiqdi ("protsedura", "protokol").
4. Nomzod yozgan xom matn rahbarga aynan ko'chirildi.
5. Kamomadda javobgarlikdan qochgan javob ijobiy baholandi.
6. Muddati o'tgan mahsulotni sotish mumkin degan javob natijaga ta'sir qilmadi.
7. Yakuniy ball/"Suhbatga tavsiya" haddan tashqari yumshoq chiqdi.
8. AI texnik ishlagan, lekin insondek tinglash/aniqlashtirish sezilmadi.

Root cause (kod o'qilgach aniqlandi): eski `recruiting_scoring.py`dagi
`_score_by_length()` FAQAT javob uzunligiga qarab ball berardi — mazmunga
(xavfli/to'g'ri) umuman qaramasdi. Shu sabab #5 va #6 aynan shu funksiyadan
kelib chiqqan edi.

## Hozirgacha bajarilgan (commit qilindi)

1. **`config.py`** — `RECRUITING_MAX_FOLLOW_UPS` endi izohi bo'yicha
   BITTA javobga nisbatan (avval butun suhbatga edi, kod hali
   yangilanmagan — pastga qarang). Yangi `RECRUITING_MIN_AGE = 18`
   konstantasi qo'shildi (faqat qonuniy yosh tekshiruvi uchun, ballga
   ta'sir qilmaydi).

2. **`db.py`** — `_ADDITIVE_COLUMNS` ro'yxatiga yangi ustunlar qo'shildi
   (production'da mavjud jadvalga xavfsiz `ALTER TABLE` bilan qo'shiladi):
   `recruiting_vacancies.required_shift/requires_weekends`,
   `recruiting_applications.*` (birth_year, residence_area,
   preferred_branch, shift_preference, unavailable_days_text,
   holiday_available, expected_salary, commute_issue,
   accommodation_needed/text, fit_result/reason, prev_employer_text,
   experience_duration_text, pos_experience, cash_handling_text,
   reference_check_consent), `recruiting_assessments.red_flags_json`,
   `recruiting_assessments.clarify_questions_json`.

3. **`schema/recruiting.py`** — `CREATE TABLE` (yangi/fresh install
   uchun) yuqoridagi barcha ustunlar bilan yangilandi.

4. **`services/recruiting_questions.py`** — savollar endi yanada
   xalqchil (masalan "kamomad" so'zi saqlangan, lekin savol matnlari
   soddalashtirildi); ikkala lavozim uchun umumiy
   `COMMON_QUESTIONS` ("ishga kech qolish" savoli) qo'shildi;
   `EXPIRED_PRODUCT_QUESTION_KEYS`, `SHORTAGE_QUESTION_KEYS`,
   `CREDENTIAL_SHARING_QUESTION_KEYS`, `CUSTOMER_CONFLICT_QUESTION_KEYS`
   to'plamlari qo'shildi — bular `recruiting_followup.py` va
   keyinchalik `recruiting_scoring.py` uchun savol->kategoriya xaritasi.
   `QUESTION_BANK_VERSION = 2`.

5. **`services/recruiting_redflags.py`** (YANGI fayl) — mazmunga
   asoslangan (uzunlikka emas) 4 ta kritik tekshiruv:
   `check_expired_product`, `check_shortage_response`,
   `check_credential_sharing`, `check_customer_conflict`. Har biri
   `RED`/`GREEN`/`UNCLEAR` qaytaradi. Bu — #5 va #6 muammolarining
   asosiy tuzatuvi bo'ladi (hali `recruiting_scoring.py`ga ULANMAGAN —
   pastga qarang).

6. **`services/recruiting_followup.py`** (to'liq qayta yozildi) —
   AI ko'rsatmasi endi: imloviy xato/shevani jazolamaslikni aniq
   talab qiladi, "protsedura/protokol/eskalatsiya" so'zlarini taqiqlaydi
   (AI chiqishi ham shu so'zlarga tekshiriladi), past ishonch holatida
   AI `null` qaytarishga yo'naltirilgan. `deterministic_follow_up()`
   endi ixtiyoriy `question_key` parametrini qabul qiladi va mos
   bo'lsa `recruiting_redflags`dagi tekshiruvlarni ishlatadi (RED yoki
   UNCLEAR — ikkalasi ham aniqlashtiruvchi savol so'raydi); umumiy
   "juda qisqa/bo'sh javob" tekshiruvi ham qo'shildi. Eski chaqiruv
   imzosi (faqat `answer_text`) hali ham ishlaydi (backward compatible).

**Barcha 6 fayl syntax jihatdan tekshirildi (`py_compile`) — xato yo'q.**
Uzoq test svitasi ATAYLAB ishga tushirilmadi (foydalanuvchi so'rovi
bo'yicha — ertaga davom etilganda ishga tushiriladi).

## Hali TUGALLANMAGAN (ertaga davom etish tartibi)

**Birinchi navbatda shu qadamdan boshlash kerak:**

1. **`services/recruiting_scoring.py`** — `recruiting_redflags` bilan
   ULANMAGAN hali. Kerak:
   - `_score_by_length()`ni content-aware qilish (yoki yangi
     `_score_situational_answer(question_key, text)` yozish) —
     RED bo'lsa 0 + red_flag qayd, GREEN bo'lsa 2, UNCLEAR bo'lsa
     ball berilmasin (`None`, o'rtachaga qo'shilmasin — talab: "javobsiz
     savolga ball berilmaydi", "bitta yaxshi kalit so'z butun javobni
     avtomatik yaxshilamasin").
   - `_overall_result()`ga YANGI qoida: agar biror kritik red_flag
     (expired_product/shortage_coverup/credential_sharing/
     customer_conflict = RED) mavjud bo'lsa, natija HECH QACHON
     `INTERVIEW_RECOMMENDED` bo'lmasin — majburiy `NEEDS_HUMAN_REVIEW`
     (o'rtacha ball yuqori bo'lsa ham).
   - `score_application()` natijasiga `red_flags` ro'yxati qo'shilsin
     (har biri: kalit, label — `recruiting_redflags.label_for()`,
     evidence) — Founder kartasida alohida ko'rsatish uchun.

2. **`services/recruiting_rubric.py`** — `RUBRIC_VERSION = 2`ga
   oshirish kerakmi, kriteriyalar ro'yxatini qayta ko'rib chiqish
   (masalan `muddat_xavfsizlik` alohida kriteriy sifatida qo'shilishi
   mumkin, hozir `muammo_yechish` ichida yashiringan).

3. **`services/recruiting_card.py`** — Founder kartasi v2:
   - Yangi maydonlar: tug'ilgan yil (ballga ta'sir qilmasligi yozilgan
     holda), hudud, filial, smena, ishlay olmaydigan kunlar, bayram
     ishlashi, kutilayotgan oylik, fit_result/fit_reason alohida qator.
   - Qizil xavflar (`red_flags`) alohida, ko'zga tashlanadigan blok.
   - 2-4 ta "suhbatda aniqlashtirilishi kerak" savol (assessment'dagi
     `clarify_questions_json`dan).
   - Uzun xom matn KARTAGA emas — qisqartirilgan (mavjud `_evidence()`
     uslubida, ~110 belgi) ko'rinishda, TO'LIQ asl javoblar alohida
     "📄 Asl javoblar" tugmasi orqali (yangi callback: `rec_raw:{id}`,
     faqat Founder/RBAC ruxsatiga ega, DB'dan `get_answers()` orqali
     to'liq matn — DB'da javob HECH QACHON o'zgartirilmaydi, faqat
     kartada qisqartiriladi).

4. **`repositories/recruiting.py`** — `_UPDATABLE_APPLICATION_FIELDS`
   ro'yxatiga barcha yangi ustunlarni qo'shish kerak (aks holda
   `update_application()` ularni jimgina e'tiborsiz qoldiradi — bu
   silent-bug xavfi, ALBATTA birinchi navbatda tekshirilsin).
   `save_assessment()` imzosiga `red_flags` va `clarify_questions`
   parametrlarini qo'shish kerak.

5. **`recruiting_bot.py`** — ENG KATTA qolgan ish, to'liq FSM qayta
   qurish:
   - Yangi holatlar: `birth_year`, `residence_area`, `preferred_branch`
     (B bo'limi kengaytmasi); `shift_preference` (tugma: kunduzgi/
     kechki/almashinuvli), `unavailable_days`, `holiday_available`
     (tugma ha/yo'q), `expected_salary`, `commute_issue` (tugma),
     `accommodation_needed` (tugma, odob bilan so'ralgan, nogironlik/
     kasallik so'zi ISHLATILMASIN) — C bo'limi (moslik filtri).
   - C bo'limidan keyin **fit_result hisoblash** (vakansiyaning
     `required_shift`/`requires_weekends` bilan taqqoslash + yosh
     tekshiruvi `RECRUITING_MIN_AGE` bilan) — agar MISMATCH bo'lsa,
     D/E bo'limlarini BUTUNLAY o'tkazib yuborib, qisqa neytral yakun
     xabari + Founder'ga qisqa (to'liq bo'lmagan) karta.
   - D bo'limi: `prev_employer_text`, `experience_duration_text`,
     `leave_reason` (mavjud), `pos_experience` (tugma), `cash_handling_text`,
     `reference_check_consent` (tugma).
   - E bo'limi (vaziyatli savollar): mavjud `role_question`/`follow_up`
     holatlarini ISHLATISH mumkin, lekin follow-up hisoblagichini
     GLOBAL (`application.follow_up_count`)dan PER-QUESTION holatga
     o'tkazish kerak (state data: `current_follow_up_attempt`, har
     yangi asosiy savolda 0ga reset) — `RECRUITING_MAX_FOLLOW_UPS`
     endi "bitta javobga maksimal" ma'nosida ishlatiladi.
   - `decide_follow_up()` chaqiruviga endi `question_key` uzatilishi
     kerak (hozir uzatilmayapti — `recruiting_followup.py` buni allaqachon
     qabul qiladi, faqat `recruiting_bot.py` hali yangilanmagan).
   - Kassir uchun qaytim savoli (mavjud `math_question` holati) —
     o'zgarishsiz qoladi (allaqachon tugma orqali, deterministik).
   - Yangi "Asl javoblar" callback handler qo'shish (`rec_raw:{id}`).

6. **`main.py`** — agar yangi callback (`rec_raw:`) yoki yangi
   handler kerak bo'lsa, ro'yxatdan o'tkazish (`recruiting_bot.register()`
   allaqachon chaqirilgan, faqat ichidagi yangi handlerlar qo'shilishi
   kifoya — `main.py`ga alohida o'zgartirish shart emas, agar
   `register()` ichida bo'lsa).

7. **Testlar** — ko'p mavjud `tests/test_recruiting_bot_flow.py`
   testlari YANGI FSM tartibiga mos KELMAYDI (masalan
   `_answer_common_fields()` helper endi yetarli emas — yangi
   maydonlar qo'shilgani uchun). Bularni yangi oqimga moslab qayta
   yozish, PLUS foydalanuvchi so'ragan regression testlarni qo'shish
   kerak (imloviy xato tushunarli qabul qilinadi, tushunarsiz javobda
   aniqlashtirish, AI ma'no to'qimaydi, muddati o'tgan mahsulot = qizil
   xavf, kamomadni yashirish ijobiy baholanmaydi, qaytim to'g'ri
   yoziladi, javobsiz savolga ball berilmaydi, jadval/bayram moslik
   boshida tekshiriladi, tug'ilgan yil ballga ta'sir qilmaydi, Founder
   kartasida tozalangan mazmun+DB'da asl javob, AI ishlamaganda
   fallback davom etadi, oddiy foydalanuvchiga Founder kartasi ketmaydi).

## Ma'lum xavf/eslatmalar

- **`repositories/recruiting.py`dagi `_UPDATABLE_APPLICATION_FIELDS`
  eng katta "sukut xato" xavfi** — yangi ustun qo'shilib, lekin shu
  ro'yxatga kiritilmasa, `update_application()` uni JIMGINA e'tiborsiz
  qoldiradi (xato bermaydi). Ertaga BIRINCHI shu ro'yxatni to'ldirish
  kerak, aks holda keyingi FSM ishida ma'lumot "yo'qolib" ketishi mumkin
  edi va aniqlash qiyin bo'lardi.
- `recruiting_followup.deterministic_follow_up()` imzosi o'zgardi
  (yangi ixtiyoriy `question_key` param) — eski chaqiruv joyi
  (`recruiting_scoring.py`dagi `_score_kassa_xavfsizlik`) hali eski
  imzo bilan ishlaydi (backward compatible), lekin `recruiting_scoring.py`
  qayta yozilganda buni ham `question_key="kassir_login"` bilan
  chaqirish yaxshiroq bo'ladi.
- Hozircha **hech qanday DB migratsiya productionda ishga tushirilmadi**
  — bu branch main'ga merge qilinmaguncha va Render deploy qilinmaguncha
  hech narsa amalda o'zgarmaydi.
- To'liq test svitasi ATAYLAB ishga tushirilmadi (uzoq test yo'q degan
  so'rov bo'yicha) — ertaga davom etishda schema/routing o'zgarishlari
  tugagach, avval targeted testlar, keyin (agar schema/routing
  o'zgargani tasdiqlansa) to'liq svita BIR MARTA ishga tushirilishi kerak.

## Ertaga BOSHLASH kerak bo'lgan aniq birinchi qadam

`repositories/recruiting.py`ni ochib, `_UPDATABLE_APPLICATION_FIELDS`
ro'yxatiga barcha yangi `recruiting_applications` ustunlarini qo'shishdan
boshlash (yuqoridagi ro'yxat), keyin `services/recruiting_scoring.py`ga
o'tish (red-flag integratsiyasi).
