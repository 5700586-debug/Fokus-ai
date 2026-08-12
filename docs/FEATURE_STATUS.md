# Fokus AI — Funksiyalar holati

2026-08 audit asosida, kodni real o'qib tekshirilgan holat (taxmin
qilinmagan). Holatlar: **production** (to'liq ishlaydi, testlangan),
**qisman** (ishlaydi, lekin cheklov/bo'shliq bor), **rejalashtirilgan**
(hali qurilmagan/placeholder), **NEEDS_BUSINESS_DECISION** (kod
ikkilanmoqda, biznes qarori kerak).

## Ro'yxatdan o'tish va vakolatlar

| Funksiya | Holat | Fayl | Izoh |
|---|---|---|---|
| Invite-asosli onboarding | production | `onboarding.py`, `invites.py`, `approval.py` | Faqat bir martalik invite havola orqali; oddiy `/start` begonani ichkariga kiritmaydi |
| Rol/vakolat tizimi | qisman | `roles.py`, `services/permissions.py` | Ishlaydi, testlangan, lekin 3 xil tekshiruv mexanizmi parallel yashaydi (qarang `ARCHITECTURE.md` §7) |
| Xodim profili/anketasi | production | `employees.py` | Favqulodda aloqa ma'lumotlari bilan |
| Founder — barcha komandalar | production | hamma joyda `FOUNDER_ID` tekshiruvi | `/invite`, `/setrole`, `/removeuser`, `/listusers`, `/profile` |

## Smena, savdo, kassa

| Funksiya | Holat | Fayl | Izoh |
|---|---|---|---|
| Kassa smenasi ochish/yopish | production | `cash_shift_bot.py`, `services/cash_shift.py` | `/openshift`, `/closeshift`, nazoratchi tasdiqlashi bilan |
| Kassa xarajati + anomaliya aniqlash | production | `services/cash_expense.py` | `/expense`, baseline'ga nisbatan chetlanish |
| Kassa xulosasi | production | `/cashsummary` | Moliyachi roliga ochiq |
| "O'rtacha chek" hisoblash | **mavjud emas** | — | Kodda topilmadi — README'dagi eski "vision" ro'yxatida bor edi, hech qachon qurilmagan |

## Ombor

| Funksiya | Holat | Fayl | Izoh |
|---|---|---|---|
| Kunlik ombor/qoldiq snapshot | production | `inventory_bot.py`, `services/inventory_snapshot.py` | `/invsnapshot`, rasm + summa, sabab-tafovut oqimi |
| Tafovut nazoratchi tekshiruvi | production | `invvariance_resolve:`/`invvariance_recheck:` | 2026-08: ikki marta bosish himoyasi qo'shildi |
| Ombor xulosasi | production | `/inventorysummary` | |
| Eski "📊 Hisobot" (soxta AI xulosa) | **olib tashlandi** | — | Hardcoded raqamlar bilan har doim bir xil natija chiqarardi (`warehouse_ai.py`) — 2026-08da o'chirildi |

## KPI, bonus, jarima (ikki mustaqil tizim — pastga qarang)

| Funksiya | Holat | Fayl | Izoh |
|---|---|---|---|
| Oylik "to'liq bonus" -> yulduz | production | `services/star_engine.py`, `performance_bot.py` | `/score`, `/processmonth`, `/mystars` |
| BOS: kunlik baho (Chala/Norma/A'lo) | production | `discipline_bot.py`, `services/discipline.py` | `/baholash`, ball qiymatlari `/setrule` orqali sozlanadi |
| BOS: jarima + nizom | production | `discipline_bot.py` | Jarima uchun bazadagi nizom raqami majburiy tasdiqlanadi, AI faqat izoh qo'shadi (qaror bermaydi) |
| BOS: apellyatsiya | production | `/apellyatsiya`, `bos:decide:` | AI rahbarga taklif tayyorlaydi, yakuniy qaror doim Founder'da |
| BOS: kunni yopish + kechikkan nazoratchiga avtomatik jarima | production | `/kunniyop`, `_day_close_tick` scheduler | Deadline `/setrule bos.day_close_deadline` orqali |
| Fiks oylik | production | `/setsalary`, `/maosh`, `/mymaosh` | Faqat Founder o'zgartiradi, BOS bu qiymatga tegmaydi |
| **star_engine vs BOS munosabati** | **NEEDS_BUSINESS_DECISION** | — | Ikkalasi mustaqil ishlaydi, bir-biriga ta'sir qilmaydi. Ataylab shundaymi (ikki alohida mezon) yoki birlashtirilishi kerakmi — aniq emas. Qarang `BUSINESS_RULES.md` |
| Bonus tarixi (`bonus_bank_ledger`) ko'rish | qisman | `services/discipline.get_bonus_ledger` | Backend tayyor va testlangan, lekin hech qanday komanda uni foydalanuvchiga ko'rsatmaydi |

## Xodim kalibratsiyasi (yangi xodim adaptatsiyasi)

| Funksiya | Holat | Fayl | Izoh |
|---|---|---|---|
| 60/30 kunlik kuzatuv davri, kundalik savol | production | `calibration_bot.py`, `services/calibration.py` | Approve bo'lgan zahoti boshlanadi, avtomatik ball/jazo YO'Q (faqat kuzatuv) |
| Ta'minotchi-haydovchi qaros-tekshiruv | production | `services/cross_check.py` | Ikkalasi faol bo'lsagina ishga tushadi |

## Boshqa xodim funksiyalari

| Funksiya | Holat | Fayl | Izoh |
|---|---|---|---|
| Haydovchi kunlik tekshiruv | production | `services/driver_checks.py`, `/drivercheck` | |
| Mashina/servis kuzatuvi | production | `repositories/vehicles.py`, `/addvehicle` | Moy almashtirish intervali `/setrule` orqali |
| Bozor kuzatuvi (ta'minotchi, ichki xodim) | production | `services/market_observation.py`, `/marketlog` | Bu ichki `taminotchi` xodim rolidan — tashqi hamkor ta'minotchilardan FARQLI (qarang pastda) |
| Ovqat rejasi | production | `services/meal_plan.py`, `/mealplan` | |
| Bildirishnomalar (idempotent) | production | `services/notifications.py` | `send_once` — bir kunga bir marta, dublikat yo'q |

## Tashqi ta'minotchi AI chati (2026-08, test muhitida qo'shildi)

`suppliers`/`supplier_offers`/`supplier_messages` — `roles.py`dagi ichki
`taminotchi` xodim rolidan (yagona shtat birligi) BUTUNLAY mustaqil
yangi obyekt: tashqi hamkor kompaniyalar, xohlagancha sonda bo'lishi
mumkin, `allowed_users`ga kirmaydi.

| Funksiya | Holat | Fayl | Izoh |
|---|---|---|---|
| Founder taklif havolasi | production (test) | `/invitesupplier`, `repositories/suppliers.py` | 48 soat amal qiladi, bir martalik |
| Shaxsiy chatdagi AI suhbat | production (test) | `services/supplier_ai.py`, `supplier_chat_bot.py` | Faqat `chat.type == "private"`, hech qachon guruhda ishlamaydi |
| Struktura ma'lumot yig'ish (mahsulot/narx/shart) | production (test) | `supplier_offers` jadvali | AI faqat ANIQ aytilgan maydonni yozadi, hech narsani to'qimaydi |
| Ta'minotchilar taqqoslash + bozor taqqoslash | production (test) | `/supplierscompare`, `services/market_observation.py` bilan birlashtirilgan | Founder-only — ta'minotchining o'ziga boshqa hech kimning ma'lumoti ko'rsatilmaydi |
| Founder xulosasi | production (test) | `/supplierreport` | AI faqat tahlil/tavsiya beradi, narx/hamkorlik qarorini hech qachon o'zi qabul qilmaydi |
| Suhbat konteksti maxfiyligi | production (test), testlangan | `tests/test_supplier_ai.py::test_prompt_never_includes_other_suppliers_data` | Har bir ta'minotchining promptiga faqat O'ZINING tarixi/profili beriladi |

## Saturn umumiy guruh kunlik postlari (2026-08, test muhitida qo'shildi)

| Funksiya | Holat | Fayl | Izoh |
|---|---|---|---|
| Ertalabki salom, kunlik dashboard, foydali ma'lumot, kechqurungi xulosa | production (test) | `services/saturn_group.py`, `saturn_group_bot.py` | Yuborish vaqtlari `/setrule saturn.*` bilan sozlanadi — kodga hardcode qilinmagan |
| Guruh ID avtomatik aniqlash | production (test) | `saturn_group_bot.py` (`saturn_test_handler`) | Founder `/saturntest`ni Saturn guruhining o'zida yuborsa, `chat.id` avtomatik `saturn.group_chat_id` sifatida saqlanadi — qo'lda ID qidirish/`/setrule` shart emas |
| Qayta ishga tushganda dublikat post yubormaslik | production (test), testlangan | `services/notifications.send_once` orqali | `tests/test_saturn_group_service.py::test_send_morning_message_is_idempotent_across_restarts` |
| Foydali ma'lumot (tip) takrorlanmasligi | production (test), testlangan | `_pick_tip`, `saturn_posts_log` | Oxirgi 7 kunlik tip bilan solishtiriladi |
| Kunlik savdo raqamlari (reja/haqiqiy/cheklar/o'rtacha chek) | **rejalashtirilgan** | `providers/sales_data_provider.py` | Loyihada hech qanday POS/kassa tizimi bu raqamlarni markazlashtirmaydi (qarang yuqorida — "O'rtacha chek" mavjud emas). `NullSalesDataProvider` — SMS/ob-havo bilan bir xil naqsh — hech qachon taxminiy raqam bermaydi, dashboard har bo'sh maydon uchun "Ma'lumot kelmadi" ko'rsatadi. Kassa smenasi (`cash_shift`) raqami ataylab ISHLATILMADI — u naqd pul solishtirish, tasdiqlanmagan savdo aylanmasi emas. Haqiqiy manba ulanganda faqat shu provayder almashtiriladi. |
| Ertalabki/kechqurungi post rasm/infografika | **rejalashtirilgan** | — | Loyihada hech qanday rasm generatsiya provayderi yo'q (SMS/ob-havo/OCR kabi barchasi hali ulanmagan) — yangi pullik integratsiya (masalan OpenAI Images) tanlash biznes qarori, shuning uchun qurilmadi. Postlar hozircha faqat matn. |

## AI

| Funksiya | Holat | Fayl | Izoh |
|---|---|---|---|
| "🤖 AI Tahlil" — erkin savol-javob | production | `main.py` | `gpt-5-mini`, xato bo'lsa foydalanuvchiga xabar, botni yiqitmaydi |
| BOS nizom-tasdiqlash/apellyatsiya tavsiyasi | production | `services/discipline_ai.py` | Faqat matn tavsiya beradi, hech qachon jarima/qarorni o'zi qabul qilmaydi (deterministik gate oldindan bor) |
| Kalibratsiya savollari | **AI emas** | `services/calibration.py` | Statik savol banki, OpenAI chaqirmaydi (aniqlik uchun yozildi — ba'zi joyda "AI" deb atalishi mumkin, lekin haqiqiy modelga ulanmagan) |

## Sozlamalar / dashboard

| Funksiya | Holat | Fayl | Izoh |
|---|---|---|---|
| `/setrule`, `/listrules` | production | `performance_bot.py`, `services/rules.py` | Haqiqiy "sozlamalar" — Founder istalgan qoidani o'zgartiradi |
| "⚙️ Sozlamalar" asosiy menyu tugmasi | rejalashtirilgan | `main.py` | Hozircha "tez orada qo'shiladi" placeholder — chalg'ituvchi emas (haqiqatan qurilmagan, shuning uchun matn to'g'ri) |
| Rol-asosli yagona menyu (2026-08) | production | `main.py` (`build_menu`, `build_category_menu`) | Har bir foydalanuvchiga faqat o'z roliga tegishli bo'lim + umumiy bo'limlar; tugmalar mavjud buyruqlarning o'zi (yangi biznes mantiq yo'q) |
| Eski FSM holatidan xavfsiz chiqish (2026-08) | production | `main.py` (`_ClearStaleStateMiddleware`) | `/start` va boshqa har qanday buyruq, "❌ Bekor qilish", "🔙 Orqaga" — qotib qolgan oqimni doim xavfsiz tozalaydi |
| Kunlik/oylik reyting (in-chat dashboard) | production | `/bugungiporga`, `/oylikturnir` | CSV/tashqi eksport yo'q, faqat chatda matn |
| CSV/fayl eksport | **mavjud emas** | — | Kodda topilmadi |

## Provider'lar (tashqi integratsiyalar)

| Funksiya | Holat | Fayl | Izoh |
|---|---|---|---|
| SMS | rejalashtirilgan | `providers/sms_provider.py` | `Null*` stub, `SMS_PROVIDER_ENABLED` flag hali hech narsaga bog'lanmagan |
| Ob-havo | rejalashtirilgan | `providers/weather_provider.py` | Xuddi shu holat |
| Rasm-dan-raqam (OCR/vision) | rejalashtirilgan | `providers/vision_extraction_provider.py` | Xuddi shu holat — bot doim qo'lda kiritishni so'raydi |
