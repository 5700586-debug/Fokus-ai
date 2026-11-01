# Grafik xavfsizligi - tasdiqlangan chegaralar (2026-11-01)

Bu hujjat PR #98 qabul mezonlari va keyingi ustuvorliklarni qayd etadi. Kod Draft PR branchida, main/production o'zgarmagan. Founder ruxsatisiz merge/deploy qilinmasin.

## Tasdiqlangan
1. **Doimiy grafik**: xodimga bir marta boshlangan/tugagan ish vaqti belgilanadi; kelajakdagi sanalarga davom etadi. Qat'iy haftalik dam kuni yo'q; alohida sanaga "Dam" istisno sifatida yoziladi.
2. **O'zgartirishning doirasi**: doimiy grafik almashtirilsa faqat kuchga kirish sanasidan boshlab amal qiladi; allaqachon o'tgan kunlarga o'tmaydi. Alohida sana tahriri faqat aynan o'sha sanani o'zgartiradi.
3. **Nazoratchi**: istalgan eski sanani sabab va to'liq audit bilan tahrirlashi mumkin. 2 kunlik cheklov YO'Q. "Eski grafikni tahrirlash" ruxsati Founder Mini App orqali yoqib/o'chirishi mumkin; dastlab yoqilgan bo'ladi. UI yashirish yetmaydi: server/API va legacy Telegram buyruqlari ham tekshirishi shart. Boshqa ruxsatlar o'zgarmaydi.
4. **Filial rahbari**: faqat o'z filiali, boshlanmagan sana, o'zi uchun emas. Nazoratchi vakolati orqali aylanib o'tish yo'q.
5. **Maosh**: bitta kun faqat o'z sanasidagi ish grafigi oralig'ida hisoblanadi: max(0, min(ketish, tugash) - max(kelish, boshlanish)); o'sha kundan ortiq ish boshqa kun kamomadini qoplamaydi. Tarif/kelishuv reja daqiqasi mustaqil saqlanadi.
6. **Vaqt bonusi**: kelish < sanaga tegishli ish boshlanishi bo'lsa 2 ball, aynan boshlanishda 0. Ketishdan qat'i nazar. Tahrir qilingan kunda qayta hisoblash faqat shu xodim-sana uchun; boshqa kunlar o'zgarmaydi.
7. **Audit va atomiklik**: barcha o'zgartirishlar kim, qachon, eski/yangi qiymat, sabab bilan qayd qilinadi. Grafik + revision + bonus sync bitta tranzaksiyada. Optimistic version, boshqa sessiya ziddiyatida rollback.
8. **Yakunlangan oy / ustuvorlik yangilanishi**: mavjud star_history yulduz qarori va audit/ruxsat himoyalari saqlanadi. Yakuniy maosh uchun alohida lock/snapshot hozir majburiy release sharti EMAS; Founder nazoratchiga ishonadi va bu masalani kelajak backlogiga qoldirdi (2026-11-01). star_history payroll approval emas — uni to'liq maosh qulfi deb atash mumkin emas.
9. **Ruxsatli dam**: grafikdagi off va attendance_reasons.manager_permission_approved/force_majeure bir xil narsa EMAS. Kelishuv reja (masalan 28 kun x 10 soat) off bilan avtomatik o'zgarmaydi; ish daqiqasi, kunlik ball va oylik yulduz talabi alohida tekshiriladi.

## Kodda mavjud / mavjud emas (main d7c3404)
- Mavjud: schedule_webapp.save transaction/revision/version, started/old shift nazoratchi sabab, star_history month lock, work_time.compute_day kunlik kesish, resync_day.
- Mavjud emas: permanent effective-dated schedule fallback, Founderdan Mini App ichida eski-grafik edit permission toggle va eski Telegram oqimi bilan umumiy guard.
- Xavf: o'tgan sana smenasi qayta yozilsa payroll_view.month_summary hozirgi schedule row dan qayta hisoblaydi; bu kunlik moliyaviy natijani o'zgartiradi (audit borligi muzlatish emas).

## Majburiy targeted testlar (prod bilan emas)
- Default grafik keyingi hafta/oylarga o'tadi; eski sanaga qaytib ta'sir qilmaydi.
- Kunlik off/override faqat tanlangan kunga; defaultni o'zgartirmaydi.
- 08:30-18:30 vs 08:00-18:00 -> 570 min; ortiqcha vaqt boshqa kunni qoplamaydi.
- 07:59 bonus; 08:00 bonus yo'q; eski kun tahriri faqat o'sha bonusni qayta hisoblaydi.
- Supervisor on/off permission serverda, legacy Telegramda va Mini Appda bir xil; Founder va branch-manager bypass yo'q.
- Missing schedule / ruxsatli dam / no-arrival / no-departure / tungi smena / approved star month.
- Batch ichidagi bittagina xato -> butun transaction rollback; dual-device version conflict -> 409.
- Faqat targeted SQLite va imkon bo'lsa PostgreSQL; DeepSeek PR advisory natijasi bloklamaydi, lekin xavflar ko'rib chiqiladi.

## Ustuvorlik / keyingi ishlar (Founder qarori, 2026-11-01)
- **KELAJAKKA QOLDIRILDI (hozirgi bloklovchi emas):** yakuniy tasdiqlangan maoshni mustaqil lock/snapshot bilan muzlatish. Nazoratchi ishonchli. Mavjud audit, ruxsat va star_history himoyalari bekor qilinmaydi. Buni avtomatik yangi vazifaga aylantirmang.
- **HOZIRGI BLOCKER:** PR #98, HEAD `84c6000` uchun Menu latency regression (PostgreSQL) 8 FAIL / 236 PASS, run #41337335349. `test_db_connection_reuse.py:124`: kutilgan 7 o'rniga 9 so'rov; `test_month_hours_queries.py:169,197`: kutilgan +2 o'rniga +3 so'rov (7 parametr holati). Grafik fallback o'qishida qo'shimcha querylar ko'paygan. Ishlash tezligi va DB so'rovlarini targeted test bilan tuzatish kerak.
- **Keyingi biznes masalasi:** oy o'rtasida kelishuv almashsa qanday hisoblash bo'yicha Founder qarori kerak. Tasdiq bo'lmaguncha taxminiy formula yozilmasin.
- **Qolgan tekshiruv:** haqiqiy bir oyning ma'lumotlarini faqat READ-ONLY ko'rib, qo'lda hisoblangan natijalar bilan solishtirish; DeepSeek Job Summary dagi cheklov/topilmalarni ko'rib chiqish.
