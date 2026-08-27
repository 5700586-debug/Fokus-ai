# Fokus AI — hozirgi holat

Bu fayl faqat HOZIRGI real holatni saqlaydi — eski tarix yo'q. Har
muhim commit/deploydan keyin yangilanadi (qarang root `CLAUDE.md`).
Ziddiyat bo'lsa, real Git/Render holati (`git log`, `render deploys
list`) ustuvor — bu faylning o'zi emas.

**Oxirgi tekshirilgan sana:** 2026-08-26

## Development

- **Faol branch:** `feature/hr-conversational-interview`
- **Yangi (2026-08-26): Grafik so'rovi qarori bo'yicha xodimga
  BILDIRISHNOMA V1.** `/grafik` oqimi endi yopiq — nazoratchi/Founder
  so'rovni tasdiqlagach yoki rad etgach, xodim Telegramda bitta xabar
  oladi (sana + qaror; tasdiqda so'ralgan grafik xulosasi ham —
  "Dam olish" yoki "10:00–19:00"). Xabar FAQAT kanonik qaror aynan shu
  chaqiruvda yozilgandan keyin yuboriladi (`_decide_schedule_request`
  ichidagi `decided` shoxi, `nazoratchi_bot.py`), shuning uchun
  eskirgan/ikki marta bosilgan tugma dublikat xabar yubormaydi. Yuborish
  xatosi izolyatsiya qilingan `try/except` ichida (mavjud
  `schedule_confirm` naqshi) — DB qarori va schedule natijasi bekor
  QILINMAYDI. Ruxsat, atomik `pending -> approved/rejected` va schedule
  yangilash yo'li o'zgarmagan; yangi jadval/bog'liqlik yo'q.
- **Yangi (2026-08-26): Grafik o'zgartirish so'rovini TASDIQLASH UI V1
  (nazoratchi/Founder tomoni).** Endi xodimning `/grafik` so'rovi
  Telegramda hal qilinadi — avval faqat core mavjud edi. Yangi
  nazoratchi menyusi tugmasi "📅 Grafik so'rovlari" (`/grafiksorov`,
  `main._MENU_ENTRIES` + `_NAZORATCHI_BUTTON_LABELS`, ruxsat mavjud
  `ACTION_MANAGE_DAILY_SCHEDULE` — yangi ACTION_* yo'q). Oqim
  (`nazoratchi_bot.py`): kutilayotgan so'rovlar ro'yxati (xodim ismi +
  sana tugmada) -> so'rov kartasi (xodim, sana, tur, ish uchun
  vaqt, sabab) -> "✅ Tasdiqlash" / "❌ Rad etish" -> ro'yxatga qaytish.
  Ro'yxat FAQAT aktyor haqiqatan hal qila oladigan so'rovlarni
  ko'rsatadi (mavjud `can_access_branch` filial chegarasi + o'z
  so'rovini o'zi hal qila olmaslik, Founder istisno) va har bir amal
  paytida mavjud `_ensure_schedule_access` orqali QAYTA tekshiriladi.
  Qaror FAQAT mavjud `services/attendance.decide_schedule_change_request`
  orqali ketadi — schedule shu kanonik yo'ldan (`set_scheduled_work_shift`/
  `set_scheduled_day_off`, `source=employee_schedule_request`)
  yangilanadi, rad etishda schedule'ga UMUMAN tegilmaydi. So'rov har
  safar DBdan qayta o'qiladi va haqiqiy himoya — servisdagi atomik
  `pending -> approved/rejected` o'tishi: eskirgan/ikki marta bosilgan
  tugma schedule'ni qayta yozmaydi va yangi revision yaratmaydi.
  Xodimga avtomatik bildirishnoma endi BOR (pastga qarang).
  Testlar: `tests/test_schedule_change_approval_ui.py`
  (18 ta, Linux'da PASSED). Yo'l-yo'lakay
  `tests/test_menu_and_fsm_escape.py`dagi 2 ta ESKIRGAN
  nazoratchi-menyu assertion (shu o'zgarishdan OLDIN ham yiqilardi,
  `/filiallar` qo'shilganidan beri) yangi menyu holatiga moslashtirildi
  — faqat test kodi, `main.py` menyu mantig'i o'zgarmadi.
- **Yangi (2026-08-26): Grafik o'zgartirish so'rovi UI V1 (xodim tomoni).**
  Xodim menyusidagi "⭐ Mening natijalarim" bo'limiga bitta yangi amal
  qo'shildi — `/grafik` ("📅 Grafikni o'zgartirish (so'rov)",
  `main._SHARED_COMMANDS`). Oqim (`performance_bot.py`,
  `ScheduleChangeStates`): sana (KK.OO.YYYY) -> "🛌 Dam olish" yoki
  "🕒 Ish vaqti" -> ish uchun boshlanish/tugash vaqti -> ixtiyoriy sabab.
  `schedule_mode` ATAYLAB so'ralmaydi — tasdiqlashda mavjud
  `set_scheduled_work_shift` xodimning o'z siyosatidan aniqlaydi.
  Yozuv FAQAT `services/attendance.create_schedule_change_request`
  orqali (`pending`), schedule'ga to'g'ridan-to'g'ri tegilmaydi.
  Xodim har bir qadamda (boshida va yuborish paytida qayta) kanonik
  `employees.get_profile` + `status == approved` orqali aniqlanadi —
  profilsiz/tasdiqlanmagan/`offboarded` foydalanuvchi bitta tushunarli
  xabar bilan rad etiladi, FSM holati ochilmaydi. Holat muvaffaqiyat/
  bekor qilish/xatolikda tozalanadi (mavjud `_ClearStaleStateMiddleware`
  + `state.clear()` naqshi). Nazoratchi/Founder uchun TASDIQLASH UI endi
  mavjud (yuqoriga qarang, `/grafiksorov`). Testlar:
  `tests/test_schedule_change_request_ui.py` (10 ta, Linux'da PASSED).
- **Yangi (2026-08-26): Grafik o'zgartirish so'rovi core V1.** Xodim
  bitta sanaga grafik o'zgartirish so'rovi yaratadi (`work` +
  start/end/mode yoki `off`, sabab optional) — yangi
  `employee_schedule_change_requests` jadvali `pending` holatda saqlaydi,
  schedule'ning o'ziga tegilmaydi. Vaqt/status/mode validatsiyasi
  YARATISHDA (`services/attendance.create_schedule_change_request`)
  mavjud schedule qoidalari bilan bo'ladi (`_parse_hhmm`, `start != end`,
  `_KNOWN_SCHEDULE_MODES`) — noto'g'ri so'rov umuman yozilmaydi, ya'ni
  tasdiqlovchi validatsiyani chetlab o'ta olmaydi. Qaror
  (`decide_schedule_change_request`) OLDIN atomik
  `UPDATE ... WHERE status = 'pending'` orqali o'tadi, schedule esa faqat
  shundan keyin qo'llanadi — takroriy/parallel approve/reject no-op
  (schedule qayta yozilmaydi, revision dublikat bo'lmaydi). Approve
  mavjud `set_scheduled_work_shift`/`set_scheduled_day_off` orqali
  ishlaydi, shuning uchun natija baribir `employee_scheduled_shifts` +
  `employee_schedule_revisions`ga tushadi — parallel ikkinchi schedule
  tizimi YO'Q. Reject schedule'ga umuman tegmaydi. Hech qanday `DELETE`
  yo'q. Telegram UI, notification, avtomatik minus/bonus ATAYLAB YO'Q
  (V1 faqat core qatlam). Testlar:
  `tests/test_schedule_change_requests.py` (12 ta) —
  `tests/test_scheduled_shifts.py` bilan birga Linux'da 23 PASSED.
  Eslatma: `tests/test_nazoratchi_attendance_review.py`dagi 2 ta
  UI-matn assertion FAILED, lekin bu **shu o'zgarishdan oldin ham**
  yiqilardi (tekshirilgan) — alohida, tegishli bo'lmagan masala.
- **Yangi (2026-08-26): Xodimni ishdan chiqarish V1.** Xodim kartasida
  (`nazoratchi_bot.py`) "🚪 Ishdan chiqarish" -> tasdiqlash ekrani ->
  `employees.status` `approved` -> `offboarded` (yagona kanonik manba,
  atomik `UPDATE ... WHERE status = 'approved'`, shuning uchun ikkinchi
  tasdiq no-op). Hech qanday `DELETE` yo'q — ledger/davomat/vazifa/grafik
  yozuvlari saqlanadi, `get_profile()` ishlayveradi; xodim faqat
  `list_approved_by_branch()` (aktiv ro'yxat)dan chiqadi. Audit — mavjud
  `security_audit_log` (`services/audit.EVENT_EMPLOYEE_OFFBOARDED`: kim,
  qachon, eski/yangi status). Ruxsat — yangi
  `permissions.ACTION_OFFBOARD_EMPLOYEE` (Founder + nazoratchi), filial
  chegarasi mavjud `can_access_branch` orqali; hech kim o'zini ishdan
  chiqara olmaydi (Founder ham). `roles`/`allowed_users`ga TEGILMAGAN —
  bot ruxsatini olib tashlash hamon alohida `/removeuser` orqali
  (V1 ataylab shunday: bitta kanonik status manbai). Testlar:
  `tests/test_employee_offboarding.py` (15 ta, Linux'da PASSED).
- **✅ TUZATILDI (2026-08-26, commit `ed672c9`, faqat test kodi):**
  `tests/test_mobility_management_ui.py` va
  `tests/test_schedule_management_ui.py` — loyihaning AnyIO sozlamasi
  (`pytestmark = pytest.mark.anyio` + `anyio_backend` fixture) qo'shildi
  va ochilgan 8 ta eskirgan assertion tuzatildi: compliance ekrani
  (`nzr_mob_reqs`) `edit_text`dan oldin `callback.answer()` chaqirgani
  uchun `sent[0]` endi `AnswerCallbackQuery` — assertionlar indeks
  o'rniga aktyor chatidagi ekran xabari bo'yicha (`_actor_screen`)
  ishlaydi; `test_founder_has_no_self_*_restriction` esa Founder uchun
  profil yaratmasdan o'z kartasini ochardi (handler to'g'ri "Xodim
  topilmadi." beradi) — profil qo'shildi. `nazoratchi_bot.py`
  o'zgarmadi, haqiqiy defekt topilmadi. Linux'da 67 ta PASSED.
- **Oxirgi commit:** `ec5e45f` — "Post E2E diagnostics as a commit comment on failure". **✅ Real Telegram E2E endi PASSED** (shu commit uchun) — E2E workflow'ga doimiy diagnostika-comment infratuzilma qo'shildi (FAILED bo'lsa avtomatik commit comment orqali to'liq sabab ko'rinadi, Founder aralashuvisiz), va aynan shu push'dagi run PASSED chiqdi. Launch-core status (SMENA/KASSA/NAZORATCHI: TAYYOR, BONUS: qisman, VAZIFA: yo'q) va "jarima" so'zini UI'dan olib tashlash (commit `2d286cb`) `FOKUS_AI_STATE.md`da batafsil.

- **Gemini konsultant (read-only)** — rasmiy `google-github-actions/run-gemini-cli@v0`.
  Gemini faqat kod o'qiydi/tahlil qiladi, yozmaydi va commit qilmaydi.
  Workflow fayli hozircha `docs/gemini-consultant.workflow.yml`da —
  aktivlashtirish uchun Founder uni `.github/workflows/`ga ko'chirishi kerak
  (sabab va aniq buyruq: `docs/GEMINI_CONSULTANT.md`).

## Render — test muhiti

- **Servis:** `fokus-ai-test` (`srv-d9ts9jad0e5s739ubbcg`, background worker, branch `feature/hr-conversational-interview`)
- **Live commit:** `316c577` — branch HEAD'dan 2 ta hujjat/workflow-only commit orqada (bot xatti-harakatiga ta'sir qilmaydi, qayta deploy shart emas).

## Render — production

- **Branch:** `main`, HEAD = `8f492e2`
- **Servis:** `Fokus-ai` (`srv-d9q82sh42hec73a0au6g`, web service)
- **Live commit:** `da43c8b` — **DIQQAT:** `8f492e2`ni deploy qilish urinishi **muvaffaqiyatsiz** (`update_failed`) bo'lgan, production hali eski commitda ishlamoqda. Sabab hali tekshirilmagan.
- **Orfan worker:** `Fokus-ai` / slug `fokus-ai-rl7u` (`srv-d9qdpsqd0e5s73bji7n0`, branch `main`) — `TelegramConflictError`ga sabab bo'lgani uchun **suspend qilingan**, hali shu holatda.

## Tugagan asosiy modullar

- **Saturn kunlik rasmli salom** (tong/tun, ob-havoga mos, haqiqiy fotolar) — `main`ga birlashtirilgan.
- **Recruiting (Fokus HR) — suhbat asosidagi intervyu** — vaqtincha barqaror/yakunlangan (qarang `docs/modules/RECRUITING.md`), faqat test muhitida.
- **Xayrli tong/tun — sodda 30 kunlik kontent** (`content/daily_greetings/`, `services/daily_greetings.py`) — kod tayyor, mavjud Saturn scheduler'ga ulangan (`saturn_group_bot.py` tick), lekin `morning.jpg`/`night.jpg` hali Founder tomonidan qo'yilmagan va hali test servisga deploy qilinmagan.

## Hozirgi bitta keyingi qadam

Founder `content/daily_greetings/morning.jpg` va `night.jpg` fayllarini qo'ygach va test botda (`fokus-ai-test`) yangi recruiting + daily-greetings o'zgarishlarini sinab ko'rgach, tasdiqlansa: (a) branch HEAD'ni (`7d6791c`) test servisga deploy qilish, (b) production'dagi `8f492e2` deploy failure sababini alohida tekshirish (bu Recruiting/daily-greetings bilan bog'liq emas, mustaqil masala).
