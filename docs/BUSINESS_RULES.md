# Fokus AI — Biznes qoidalari

Bu yerdagi barcha son/vaqt qiymatlar `rules` jadvalidan olinadi va
Founder `/setrule <kalit> <qiymat>` bilan o'zgartirishi mumkin — kodda
hardcode qilinmagan (istisnolar alohida belgilangan). Joriy qiymatlarni
`/listrules` bilan ko'rish mumkin. Har bir qoidaning kodi:
`services/rules.py`.

## 1. Oylik "to'liq bonus" / yulduz (`services/star_engine.py`)

"To'liq bonusli oy" quyidagilarning HAMMASI bajarilganda bo'ladi
(`full_bonus_month.*` qoidalari yoqilgan bo'lsa):

| Qoida | Standart | Ma'no |
|---|---|---|
| `full_bonus_month.min_supervisor_score` | 80 | O'rtacha nazoratchi bahosi shundan past bo'lmasin |
| `full_bonus_month.require_attendance_ok` | 1 (yoqilgan) | Davomat muammosiz bo'lsin |
| `full_bonus_month.require_no_serious_violation` | 1 (yoqilgan) | Jiddiy buzilish bo'lmasin |
| `full_bonus_month.require_checklist_completed` | 1 (yoqilgan) | Checklist tugallangan bo'lsin |

Natija: to'liq bonusli oy bo'lsa `stars += 1` (`star.max`=5dan oshmaydi),
bo'lmasa `stars -= 1` (`star.min`=0dan kamaymaydi). Yulduz soniga mos
bonus (`bonus.stars.N`): 1★=50,000 / 2★=110,000 / 3★=200,000 /
4★=300,000 / 5★=500,000 so'm. `process_month` bir `year_month`ni ikki
marta qayta ishlamaydi (idempotent — `try_insert_monthly_performance`
UNIQUE constraint orqali).

## 2. BOS — kunlik baho (`services/discipline.py`)

| Baho | Ball (qoida) | Standart |
|---|---|---|
| Chala | `bos.grade_points.chala` | 1 |
| Norma | `bos.grade_points.norma` | 2 |
| A'lo | `bos.grade_points.alo` | 3 |

Bir xodim kuniga bir marta baholanadi (`UNIQUE(employee_id, eval_date)`)
— qayta baholansa, avvalgi ball bilan farqi (`delta`) bonus bankiga
qo'shiladi (ikki marta qo'shilib ketmasligi uchun), delta 0 bo'lsa
(bir xil baho qayta bosilsa) hech narsa yozilmaydi.

## 3. BOS — jarima (`services/discipline.py`, `discipline_bot.py`)

- Ruxsat etilgan miqdorlar: `bos.penalty_amounts` (standart: `10,20,30`
  ball, vergul bilan ajratilgan ro'yxat).
- Jarima FAQAT bazada mavjud nizom raqami bilan qo'llanadi — nazoratchi
  matn kiritadi (masalan "3-nizom"), tizim `company_rules` jadvalidan
  raqamni tekshiradi; topilmasa jarima qo'llanmaydi.
- AI (`services/discipline_ai.py`) nazoratchi yozgan matn bilan
  bazadagi nizom matnini solishtirib **tushuntirish** beradi — bu
  qat'iy shart EMAS, faqat inson o'qishi uchun. Haqiqiy tekshiruv
  (nizom raqami mavjudligi) har doim oldindan, deterministik bajariladi.
- Jarima faqat `bonus_bank`ga ta'sir qiladi — **fiks oylikka
  (`salaries.fixed_salary`) hech qachon tegmaydi**.

## 4. BOS — apellyatsiya (`discipline_bot.py`)

Xodim `/apellyatsiya` bilan e'tiroz bildiradi (matn yoki ovozli xabar).
AI (`prepare_appeal_brief`) nizom+dalilni solishtirib Founder uchun
**tavsiya matni** tayyorlaydi — **AI hech qachon yakuniy qarorni
qabul qilmaydi**, faqat Founder `bos:decide:<id>:approved|rejected`
tugmasi bosgandan keyin:
- `approved` -> jarima miqdori bonus bankiga qaytariladi (refund).
- `rejected` -> hech narsa o'zgarmaydi.

Bitta jarimaga faqat bitta marta apellyatsiya berish mumkin
(`appeal_status`: `none` -> `pending` -> `resolved`).

## 5. BOS — kunni yopish va nazoratchi javobgarligi

- Nazoratchi `/kunniyop` bilan kunni yopadi — bir kunga bir marta
  (`UNIQUE(supervisor_id, closure_date)`).
- Deadline: `bos.day_close_deadline` (standart `20:00`, kompaniya vaqt
  zonasi bo'yicha). Shu vaqtdan keyin (5 daqiqalik scheduler tick
  orqali) agar kun hali yopilmagan bo'lsa, nazoratchidan avtomatik
  `bos.supervisor_late_penalty` (standart 40) ball yechiladi va bir
  marta qayd etiladi (`UNIQUE(supervisor_id, audit_date, event_type)`
  — bir kunga ikki marta jarimalanmaydi).
- **Cheklov:** hisoblash bitta faol nazoratchi farazi bilan ishlaydi
  (qarang `ARCHITECTURE.md` §7).

## 6. Kassa smenasi (`services/cash_shift.py`, `services/cash_expense.py`)

- Yopishda hisob-kitob farqi `cash_shift.tolerance` (standart 20,000
  so'm) dan oshsa, nazoratchi tasdiqlashi talab qilinadi.
- Qayta urinish chegarasi: `cash_shift.retry_limit` (standart 3).
- Xarajat anomaliyasi: kategoriya tarixi kamida
  `cash_expense.baseline_min_observations` (standart 7) ta bo'lishi
  kerak, aks holda hukm chiqarilmaydi (yetarli ma'lumot yo'q). Bo'lsa,
  `amount > o'rtacha * cash_expense.anomaly_multiplier` (standart 1.5)
  bo'lsa anomaliya deb belgilanadi va sabab so'raladi.

## 7. Ombor tafovuti (`services/inventory_snapshot.py`)

- `inventory.variance_threshold` (standart 1,000,000 so'm) dan katta
  imzosiz farq -> `needs_review`; agar sabab-tushuntirish bilan
  qoplanmagan qoldiq (`unexplained_variance`) shu chegaradan baland
  qolsa -> `urgent_review` (nazoratchi/Founder darhol xabar oladi).
- Kunlik eslatma vaqti: `inventory.reminder_time` (standart `20:00`,
  kompaniya vaqt zonasi bo'yicha, 5 daqiqalik tick bilan tekshiriladi).

## 8. Mashina/servis (`repositories/vehicles.py`)

- Moy almashtirish intervali: `vehicle.oil_change_interval_km`
  (standart 5000 km).

## 9. Kalibratsiya / yangi xodim adaptatsiyasi (`services/calibration.py`)

- Kuzatuv davri: 60 kun (`CALIBRATION_WINDOW_DAYS`, kodda konstanta —
  bu mahsulot siklining o'zi, `/setrule` orqali sozlanmaydi).
- Adaptatsiya oynasi: 30 kun (`ADAPTATION_WINDOW_DAYS`).
- Kunlik savol kvotasi: 2 yoki 3 (tasodifiy, `DAILY_QUESTION_QUOTA_CHOICES`).
- Kunlik savol yuborish vaqti: `calibration.daily_question_time`
  (standart `10:00`).
- **Muhim:** kuzatuv davrida hech qanday avtomatik jazo/bonus
  qo'llanmaydi — faqat fakt yig'ish. 60 kundan keyin KPI tavsiyasi
  Founderga MATN sifatida taqdim etiladi, avtomatik qo'llanmaydi.

## 10. NEEDS_BUSINESS_DECISION

- **star_engine (oylik yulduz) vs BOS (kunlik ball/jarima) munosabati.**
  Ikkalasi bugungi kunda to'liq mustaqil — BOS jarimasi yulduz/oylik
  bonusga ta'sir qilmaydi, star_engine ham BOS ballariga qaramaydi.
  Bu ataylab ikki alohida mezon sifatida qolishi kerakmi, yoki BOS
  jarimasi `full_bonus_month.require_no_serious_violation` mezoniga
  ta'sir qilishi kerakmi — aniq emas, kod bu haqda hech narsa
  aytmaydi. **Tuzatilmagan — Founder qarori kerak.**
