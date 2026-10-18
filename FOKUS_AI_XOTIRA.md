FOKUS_AI_XOTIRA.md
Maqsad: loyiha qarorlari, g'oyalari va bekor qilingan ishlar. Yangi chat/robot avval shu faylni, keyin FOKUS_AI_STATE.md ni o'qiydi. Bu fayl HOLAT emas. Joriy commit, ochiq PR, keyingi qadam — faqat FOKUS_AI_STATE.md da. Belgilar: ✅ QAROR · 💡 G'OYA · ⏸ KEYINGA · ❌ BEKOR · ⚠️ MA'LUM CHEKLOV Yozilmaydi: token, parol, API kalit, karta, maosh summasi, xodim shaxsiy ma'lumoti. Yangilash: faqat yangi muhim qaror/g'oya Muhammadiy tasdiqlagandan keyin, robot joriy PR ichida qo'shadi.

## 1. O'zgarmas tamoyillar
✅ AI yakuniy qaror chiqarmaydi: ishga olish, ishdan chiqarish, jarima, apellyatsiya, katta moliyaviy qaror — faqat vakolatli inson. AI: yig'adi, solishtiradi, xavf ko'rsatadi, tavsiya beradi. Avtomatik jarima/hukm yo'q.
✅ Rollar: ChatGPT — arxitektor/prompt; Claude Code (robot) — bajaruvchi; Sodiq (Claude in Chrome) — tekshiruvchi; Muhammadiy — yakuniy tasdiq.
✅ Bir vaqtda 1 vazifa, 1 PR. Vazifa tugamaguncha boshqasiga o'tilmaydi. Konfliktni robot hal qiladi. Istisno: faqat .md hujjat PR'i — ochiq kod PR'lari bilan bir xil faylga tegmasa ochilishi mumkin. (2026-10-18)
✅ main / merge / deploy / production DB / secret / .env — faqat Muhammadiyning aniq tasdig'i bilan (maxsus so'z shart emas). Force push yo'q.
✅ Robotga prompt faqat Muhammadiy "JO'NAT" degandan keyin yuboriladi. Prompt avval tanqid qilinadi.
✅ Natija "yashil belgi" bilan emas, real diff + test logi + GitHub/Render jonli holati bilan tasdiqlanadi. Robot hisobotiga ko'r-ko'rona ishonilmaydi. Tekshirib bo'lmasa — "noma'lum/tekshirilmadi" deyiladi, taxmin qilinmaydi.
✅ Faqat real (production) bot. Test botga tegilmaydi, unga oid eski yozuvlar tarix hisoblanadi (ko'chirishda 40-50% qayta ish chiqqan). (Sodiq bilan suhbat, 2026-10)
✅ Real bot sinovi: haqiqiy xodimga baho berilmaydi, filial yopilmaydi, minus/jarima yozilmaydi.
✅ Hujjat va real GitHub holati zid bo'lsa — real holat ustun.
✅ Yangi sessiya: Muhammadiy faqat "FOKUS AI, davom et." desa — eski ma'lumot qayta so'ralmaydi, boshidan boshlanmaydi, eski chat qayta aytib berilmaydi; faqat oxirgi tasdiqlangan nuqtadan davom etiladi, bir vaqtda imkon qadar bitta keyingi qadam beriladi. (manba: eski docs/FOKUS_MEMORY.md)
✅ Ustuvorlik tartibi: 1) real Git/GitHub/Render holati, 2) FOKUS_AI_XOTIRA.md qoidalari (I/S), 3) FOKUS_AI_STATE.md, 4) eski chat xotirasi. Eski chatdagi taxmin real repo holatidan ustun bo'lmaydi. (manba: eski docs/FOKUS_MEMORY.md)
✅ Saqlash buyruqlari: "G'oya:"/"G'oyani saqla:" — yangi fikr FOKUS_AI_XOTIRA.md ning 5-bo'limiga (💡, sana, manba) qo'shiladi, mavjud g'oya o'chirilmaydi, holati NEW/PLANNED/IN_PROGRESS/DONE/REJECTED dan biri, amalga oshirish boshlanmagan bo'lsa kodga tegilmaydi; "Oxirgi qadamni saqla:" — FOKUS_AI_STATE.md real checkpoint bilan yangilanadi, taxmin fakt sifatida saqlanmaydi; har PR ichida FOKUS_AI_STATE.md yangilanadi (bajarilgan ish + keyingi qadam). (manba: eski docs/FOKUS_MEMORY.md)
✅ G'oyalar bajarilmaguncha o'chirilmaydi; faqat holati o'zgartiriladi (REJECTED bo'lsa sabab yoziladi). (manba: eski docs/IDEAS.md)
- ✅ Nizom — kompaniya qonuni: AI/robot uni o'zgartirmaydi, faqat Muhammadiyga taklif beradi. *(Muhammadiy, 2026-10-18)*
## 2. I/S1 rejimi ("Iqtisodchi Sodiq", "s i", "FOKUS-IS1") — robot promptlari uchun majburiy
Manba: Autopilot (2026-08-31), PR tekshiruvi (2026-09-19).

✅ Windows / PowerShell / CMD / local Git Bash = 0. Faqat remote Linux, GitHub Actions ubuntu-latest, Codespaces.
✅ Har promptda: Maqsad (1 gap) · Natija · Chegara (Touch ONLY / tegilmaydi) · PASS mezoni · repo · branch · checkpoint commit · qaysi test.
✅ Robot: reja yozib to'xtamaydi, maqsadsiz qidirmaydi, umumiy audit qilmaydi, yangi arxitektura o'ylab topmaydi, mavjud kodni qayta ishlatadi, dublikat service/jadval yaratmaydi.
✅ Test: har pushda smoke + o'zgargan modul targeted test. Istisno: faqat .md hujjat o'zgargan PR da test talab qilinmaydi. Full test faqat Muhammadiy aniq so'raganda; release oldidan avtomatik emas. Real Telegram oqimi o'zgarsa — tegishli E2E.
✅ Katta prompt ketma-ket: 1-qadam → tekshiruv → 2-qadam. Parallel yarimta ish yo'q.
✅ To'siq: [STOP sababi: … | Kerakli narsa: …]. AskUserQuestion ishlatilmaydi.
✅ Remote oldinda bo'lsa: safe fetch + rebase.
✅ Yakuniy hisobot qisqa (5 qator): PR link · head commit · test natijasi · mergeable · qolgan xavf.
✅ Oldingi promptga qo'shimcha kerak bo'lsa avval so'raladi: "Oldingi prompt robotga berildimi?" Ha → faqat qo'shimcha. Yo'q → hammasi bitta yangi to'liq prompt.
✅ Chetlashilsa ogohlantirish: "⚠️ I/S1 buzilyapti".
✅ Tamoyil: kam xarajat, aniq vazifa, nazoratli natija. Avval FOKUS_AI_STATE.md va real Git/GitHub holati tekshiriladi, keyin faqat bitta navbatdagi vazifa tanlanadi; ish tugagach real natija tekshirilib checkpoint yangilanadi. (manba: eski docs/IS_MODE.md)
✅ I/S rejimida task fayli (.claude/tasks/…) ham Muhammadiy aniq "jo'nat" demaguncha yaratilmaydi/push qilinmaydi; robot ishlayotgan paytda takroriy prompt yuborilmaydi. (manba: eski docs/FOKUS_MEMORY.md)
✅ Bir xil xato ikki marta takrorlansa — yangi dalil yig'iladi; uchinchi taxminiy fix qilinmaydi. (manba: eski FOKUS_AI_STATE.md)
## 3. Arxitektura qarorlari
✅ Stack: Python, aiogram 3, PostgreSQL/Supabase (prod), SQLite (lokal test), Render, OpenAI API, GitHub.
✅ Qatlamlar: Telegram handler (faqat oqim/tugma) → service (biznes hisob) → repository (yagona SQL joyi) → DB.
✅ Ruxsatlar markazlashgan ACTION_* RBAC + filial bo'yicha kirish cheklovi.
✅ Render: hozirgi servis fokus-ai-singapore — Web Service (Singapore), auto-deploy main'dan; uyg'oq turishi uchun GitHub Actions "Keep Render Bot Awake" ping ishlatiladi. Tarix: eski Oregon servisi Background Worker'ga o'tkazilgan edi (Web Service port kutib "Timed out" bergan). (Render tekshiruvi, 2026-10-18; oxirgi live deploy 9ead58b, 2026-10-07)
✅ Robot muhitida Render API kaliti yo'q → deploy holatini robot ko'rmaydi. Deploy tekshiruvi: ChatGPT Render plagini yoki Muhammadiy qo'lda (Render → Events).
⚠️ Deploy paytida TelegramConflictError (ikki nusxa polling). ⏸ Webhook'ga o'tish keyinroq.
⚠️ Supabase (Mumbai) ↔ Render orasidagi masofa har DB so'rovda kechikish beradi. Tezlik: DB pool, FSM, N+1 tuzatishlari qilingan.
✅ AI ulanishi: mavjud bitta OpenAI API ulanishi kengaytiriladi; ikkinchi AI/provayder kerak emas. ChatGPT obunasi ≠ OpenAI API balansi (bot API balansiga bog'liq).
✅ Bonus/minus ball: yangi alohida ledger yaratilmaydi — mavjud bonus_bank_ledger ball semantikasida; davr yopilishi cron talab qilmaydi (yangi oy 0/0/0 dan boshlanadi, eski yozuvlar o'chirilmaydi). Fiks oylik bu modul orqali hech qachon o'zgarmaydi. (manba: eski FOKUS_AI_STATE.md)
✅ Apellyatsiyani nazoratchi hal qila olmaydi: qaror faqat Founder rolida (ACTION_DECIDE_APPEAL). (manba: eski FOKUS_AI_STATE.md)
✅ Foydalanuvchiga ko'rinadigan matnlarda "jarima" o'rniga "ball ayirish"/"ball qaytariladi" ishlatiladi (faqat matn; biznes mantiq o'zgarmaydi). (manba: eski FOKUS_AI_STATE.md)
✅ Erkin umumiy AI chat ("🤖 AI Tahlil") menyudan olib tashlangan — bot umumiy chatbot emas; ichki aniq AI avtomatizatsiyalari (rekruting scoring, nizom yordamchisi) qoladi. (manba: eski FOKUS_AI_STATE.md)
✅ Davomat: nazoratchi kelish vaqtini qo'lda kiritadi (manba manual_nazoratchi_entry); kechikish sababi tugmalari: sababsiz · rahbar ruxsati (Founderga avtomatik Ha/Yo'q) · fors-major · boshqa. Minus miqdori o'ylab topilmaydi — Founder aniqlaydi. (manba: eski FOKUS_AI_STATE.md)
✅ Real Telegram E2E FAILED bo'lsa sabab commit comment sifatida avtomatik yoziladi (session/token hech qachon chiqmaydi). GitHub job-log'lariga autentifikatsiyasiz kirib bo'lmaydi — shuning uchun testlar imkon qadar sodda/strukturaviy yoziladi. (manba: eski FOKUS_AI_STATE.md)
## 4. Biznes qarorlari
✅ Kamida 1 yil faqat 1 Nazoratchi (single-slot ataylab). (Autopilot, 2026-08-31) Ko'p nazoratchiga o'tishga to'sqinlik qiluvchi kod yozilmaydi.
✅ Nazoratchi baholashni kun oxirida qiladi; smena bo'yicha alohida nazorat qurilmaydi. Ish/vaqt = 0 ham baho hisoblanadi. (Sodiq bilan suhbat, 2026-10-05)
✅ Filiallar bittadan qo'shiladi: sinov → tuzatish → keyingi filial. (Autopilot, 2026-08-31)
✅ Grafik: 1-smena 08:00–18:00; 2-smena 14:00–01:00 (keyingi kun). Erkin grafik = rahbar kunlik vaqtni belgilaydi, xodim shunga javob beradi ("xohlagan payt" emas).
✅ Ta'minot: ichki taminotchi (xodim, bozor narxi, xarid) va tashqi hamkor ta'minotchi (taklif havolasi, faqat o'z ma'lumoti, AI ma'lumot to'qimaydi) alohida. Buyurtmani inson tasdiqlaydi.
✅ Xodimni ishdan chiqarish tarixini o'chirmaydi. (Autopilot, 2026-08-31)
✅ Umumiy xodimlar guruhi: 08:00 "Xayrli tong" va 21:00 "Kun yakuni" — 3-5 qator, moliyaviy raqam (savdo, foyda, xarajat, o'rtacha chek, qarz) YO'Q. (2026-08-19)
Kassa oqimi (PR #45, merge 9ead58b, 2026-10-07)
✅ Smena ochish: oldingi qoldiq bo'lsa "Kassada … so'm bor deb qabul qilyapsizmi?" → [✅ Ha] / [✏️ Summani o'zgartirish]; o'zgartirilsa moliyachiga xabar.
✅ Smena yopish: 3 rasm (daftar, POS/programma, cheklar) + faqat "Kassada qancha naqd qoldiryapsiz?". AI rasmdan pul HISOBLAMAYDI (1 352 435,00 ni 135 243 500 deb o'qigan holat bo'lgan).
✅ Yuborilgach kassir kutmaydi: "Smena yopildi, moliyachiga yuborildi" + Asosiy menyu. Moliyachi tasdiq/rad; rad → "🔄 Qayta yuborish".
✅ Kassir menyusi: faqat Smenani boshlash / topshirish / Orqaga. Xarajat kiritish kassirdan yashirilgan (Founder uchun ishlaydi). (PR #42)
✅ Chat tozalash (PR #46): har 30 daq, 8 soatdan eski kassa dialog xabarlari o'chadi; needs_finance_review rasmlari saqlanadi; pul tarixi/tasdiqlarga tegilmaydi; eskirgan csui_ tugma → "Bu tugma eskirgan". Tartib: #45 real sinovdan keyin #46. ⚠️ 2026-10-18 holati: PR #46 OCHIQ, merge qilinmagan.
⚠️ Bir kassir bir kunda 2-smena ocholmaydi (UNIQUE(employee, shift_date)) — alohida ish.
Nizom o'rganish (2-qism, 2026-09-02)
✅ Nizom xodimga FAQAT 100% ishga qabul qilingandan keyin chiqadi: Founder approve → rol muvaffaqiyatli biriktirildi → keyin nizom. Rol xato bersa nizom ko'rinmaydi (enrollment DB da yashirin bo'lishi mumkin).
✅ Kuniga maks 5 nizom. Nizomlar soni 26 ta; kuniga 5 tadan — taxminan 6 kun. Ketma-ket: Nizom → "O'qidim" → "Tushundim" → keyingi. "❓ Tushunmadim" bosilsa keyingisi ochilmaydi.
✅ AI imtihon olmaydi, xodimni baholamaydi.
✅ Yagona manba company_rules; checklist tizimiga nusxalanmaydi; yangi scheduler qo'shilmaydi. Davom: 📋 Nizomlar yoki /listnizom.
✅ Rule snapshot va vaqtlar DB da (audit); Telegram xabarlari keyin tozalanishi mumkin.
✅ /setrole eski xodimga yangi enrollment yaratmaydi; faqat tugallanmagan enrollment bo'lsa davom ettiradi. Rule-learning xatosi approval//setrole ni yiqitmaydi (log + davom).
Xodim menyusi "Mening natijalarim" (4×2)
✅ [⭐ Yulduzlarim] [💰 Oyligim] / [📅 Grafik so'rovi] [🏆 Bugungi o'rnim] / [🏅 Oylik reyting] [📋 Nizomlar] / [🙋 E'tirozim bor] [🔙 Orqaga]. Eski slash komandalar ham ishlaydi.
Robot (Claude Code) ishga tushirish usuli
✅ Usul 1 (kanonik): .claude/tasks/<task>.md → commit/push → .github/workflows/claude-task-runner.yml (ubuntu) → real log → robot commiti → targeted test. ⚠️ Bu workflow hozir FAQAT feature/hr-conversational-interview branchida ishlaydi — boshqa branchda ishlamaydi. (GitHub tekshiruvi, 2026-10-18)
✅ Usul 2 (zaxira): Codespaces ichidagi Claude Code — istalgan branchda, prompt to'g'ridan-to'g'ri beriladi.
✅ Run in_progress bo'lsa qayta jo'natilmaydi. Xato bo'lsa avval log → sabab → minimal retry; ko'r-ko'rona qayta yuborish yo'q (token isrofi bo'lgan).
✅ Eng arzon yetarli model ishlatiladi (katta model economy rejimiga zid).
❌ Aniq so'm-asosidagi kunlik bonus formulasi (STAGE 9) BEKOR qilingan — ball tizimi tanlangan (12-bo'lim). (manba: eski FOKUS_AI_STATE.md; Muhammadiy, 2026-10-18)
⚠️ Bonus/minus bo'yicha ochiq biznes qarorlari (o'ylab topilmaydi, Founder tasdig'i kerak; 1 ball qiymati va kechikish qoidalari 12-bo'limda hal qilingan, qolganini Muhammadiy tekshiradi): vaqtida/erta kelish bonusi; kechikish minuslari; nazoratchi noto'g'ri tasdiqlasa minus; takroriy fors-major qoidasi. (manba: eski docs/IDEAS.md)
## 5. Kelajak g'oyalari (tasdiqlanmagan yoki qisman)
💡 Bot + Mini App bo'linishi (3-qism). Bot: xabar beradi, eslatadi, savol beradi, tasdiqlaydi. Mini App: ko'rsatadi, boshqaradi, taqqoslaydi. Hozir Mini App ga tegilmaydi.
💡 Bugungi muammolar — Founder oynasi. Barcha modullar muammosi bitta ekranda. Holat: 🔴 shoshilinch · 🟡 bugun · ⏳ kutilmoqda · 🟢 hal. Tugma: 👀 ko'rdim · ➡️ mas'ulga · ✅ hal · ⏰ keyin eslat. Quruq qo'rqinchli ro'yxat emas. V1: faqat Founder, moliya yo'q, guruhga yubormaydi, AI hukm yo'q. (V1 qurilgan)
💡 Saturn AI nazoratchi ("miya"). Nizomlar (25+), lavozim cheklistlari, ball tizimi, polka standartlari bir marta beriladi. Xodim rasm/hisobot yuborsa AI xatoni topadi, vazifa yozadi, ertasi tuzatilganini tekshiradi, rahbarga faqat muhimini chiqaradi. FOKUS AI ichida alohida almashtiriladigan modul (Saturn/Shafran/mijoz o'z qoidalari). Boshida AI ball ayirmaydi — faqat tavsiya. Navbat: sandbox + asosiy oqimlar sinovidan KEYIN. (menedjer, 2026-09-26)
💡 Kamera/audio "Nazoratchi AI" (ko'z-quloq). Kamera: xodim telefonda uzoq, xaridorga xizmat ko'rsatmadi, ish joyida yo'q. Har 10 s skrinshot emas — lokal AI uzluksiz kuzatadi, shubhali hodisada kuchli AI 10-20 s klipni tahlil qiladi, rahbarga dalil bilan yuboradi; hukmni rahbar chiqaradi. Audio (har kassaga mikrofon) — kamera ishonchli bo'lgach. Boshlanish: 1 kamera, 1 do'kon, 3 qoida. Huquqiy (maxfiylik, ovoz yozish) tekshiruv shart. Yuz/biometrik ma'lumot O'zbekistonda saqlanishi kerak. Alohida tijoriy loyiha, keyin FOKUS AI bilan birlashadi. (Nazoratchi, 2026-08-12)
💡 Rol testi sandbox. Founder istalgan rol bo'lib real handlerlarni sinaydi, production DB ga 0 yozuv. (Holati sanali: 2026-09-30 da tugallanmagan — joriy holat STATE da.) Talablar: alohida PostgreSQL; SANDBOX_DATABASE_URL yo'q yoki prod bilan bir xil → fail-closed; faqat sintetik ma'lumot; rol almashganda FSM tozalanadi; tashqi Telegram xabarlari faqat Founderga; CI da OpenAI mock; zero-write isboti. (Sandbox DB routing map + PR tekshiruvi chatlari, 2026-09-19/30; branch feature/role-test-sandbox-db-routing)
💡 Rekruting → jahon darajasi (~8/10 → 9.5). Yangi funksiya emas, 3 ta yopish: AI balli real ish natijasi bilan validatsiya; yosh/jins bo'yicha bias audit; nomzodga AI ishlatilayotganini aytish + HR yakuniy qaror. Mavjud: moslashuvchan suhbat, fit-filter, rubric, RED/GREEN/UNCLEAR, NEEDS_HUMAN_REVIEW, fallback. (2026-08-18)
💡 Recruitment Mode. Maxsus havola orqali nomzod; oddiy menyu ko'rinmaydi; AI bahosi faqat rahbarga; tugmalar: Suhbatga chaqirish / Rad / Keyinroq.
💡 Kunlik hisobot (ESKI g'oya, cheklangan). Asl g'oya: kassir daftar rasmini yuboradi, AI o'qiydi. 2026-10 kassa qarori bilan cheklandi: AI rasmdan pul HISOBLAMAYDI, rasm moliyachiga dalil sifatida boradi. AI Direktor: yetkazib beruvchilar (taksi, Coca-Cola) odatiy tartibdan chetga chiqsa shubhali deb belgilaydi; adaptive.
💡 Xodim kelishuvi (PR-C). Fiks oylik, ish vaqti, tarif tugmalari + erkin summa; xodim "Ha, tushundim"; summa faqat xodim/Founder/filial rahbariga; o'zgarsa yangi versiya.
💡 Vaqt bonusi +2 yoki 0 ("tasdiqlanmagan" emas). Baho qo'yilgach xodimga natija + shaxsiy dashboard yangilanadi (pul faqat o'ziga).
💡 Memory Engine. Har foydalanuvchiga alohida xotira; sensitive yozilmaydi; "Buni unut" → o'chadi.
💡 Tijoriy model (hozir emas — mijozlarga berilmaydi). Avval o'z do'konlarida isbot. 1-mijozlar: har biriga alohida bot + DB + server + secret. Umumiy multi-tenant SaaS (tenant_id, RLS) faqat bir nechta mijozdan keyin.
💡 Jamoa (kerak bo'lganda). Navbat: 1) Senior Python Tech Lead, 2) Middle Python, 3) QA (yarim stavka), 4) DevOps/xavfsizlik (loyiha asosida), 5) Frontend (keyin), 6) Support (3-5 mijozdan keyin). ML mutaxassis shart emas. Shartlar: NDA, 3 kunlik pullik sinov → 1 oy; to'lov haftalik natija bo'yicha; kod/akkauntlar FOKUS AI nomida; prod parollari boshida berilmaydi; kodni yozgan o'zi prodga chiqarmaydi. (2026-09-11)
💡 Haftalik 1:1 suhbat. Rahbar va xodim haftalik qisqa suhbati; asosiy oqim qurilgan, kengaytirish g'oyalari shu 5-bo'limda. (manba: docs/IDEAS.md — robot to'liq matnni birlashtiradi)
💡 Face ID davomat. Xodim kelib-ketishini yuz orqali qayd etish. ⚠️ Biometrik ma'lumot O'zbekistonda saqlanishi shart; huquqshunos va xavfsizlik tekshiruvisiz xorijiy server/AI ga yuborilmaydi. (manba: docs/IDEAS.md; Mutaxassislar e'loni, 2026-09-11)
💡 Integratsiyalar: 1C (avval Excel eksport, keyin OData), Web Dashboard, mobil, ovozli yordamchi, Gmail/Calendar.
💡 Haftalik 1:1 suhbat — to'liq: asosiy oqim (Core V1) mavjud; kelajak: rahbar UI, xodim bilan haftalik suhbat, follow-up va kerakli bildirishnomalar. (manba: eski docs/IDEAS.md)
💡 Face ID davomat — qo'shimcha: hozir qo'lda nazoratchi kiritish qatlami bor; haqiqiy avtomatik manba shu mavjud attendance qatlamiga ulanadi, parallel davomat tizimi qurilmaydi. (manba: eski docs/IDEAS.md)
💡 Kamera nazoratchi — qo'shimcha: xodim sustligi, telefon ishlatishi, polka bilan ishlamasligi, xaridorga e'tiborsizlik aniqlanadi; rahbarga faqat kerakli hodisa yuboriladi; maxfiylik, huquqiy talablar va false-positive nazorati alohida ishlab chiqiladi. (manba: eski docs/IDEAS.md)
💡 AI audio nazoratchi: do'kondagi audio oqimini matnga aylantirish, xodim muomalasi va nomaqbul gaplarni aniqlash, rahbarga tegishli qisqa hodisa yuborish; maxfiylik va qonuniy rozilik talablari amalga oshirishdan oldin tekshiriladi. (manba: eski docs/IDEAS.md)
💡 Tijoriy mahsulot (hozir emas — mijozlarga berilmaydi; alohida direktor/do'kon uchun izolyatsiyalangan ishlash; bir nechta real biznesda parallel sinash; multi-tenant arxitektura va yuklama chegaralari alohida rejalashtiriladi) — holati NEW. (manba: eski docs/IDEAS.md)
💡 Gemini konsultant (read-only): faqat kodni o'qiydi/tahlil qiladi, yozmaydi, commit qilmaydi; workflow fayli docs/gemini-consultant.workflow.yml da turardi, .github/workflows/ ga ko'chirish Founder tomonidan. Joriy holati TEKSHIRILMAGAN. (manba: eski FOKUS_AI_STATE.md)
## 6. Keyinga qoldirilgan
⏸ Authenticator 6 xonali kod — faqat Founder umumiy moliyaviy ma'lumotni ochganda. Oddiy HR/grafik/davomat/nazoratda yo'q. Kod: 30 s, 3 xato → 15 daq blok, logga/bazaga yozilmaydi, chatdan o'chadi, maxfiy kalit Render secret'da, tiklash kodlari. Loyiha oxirida.
⏸ main branch protection + repo private — production/tijoriy tayyorgarlikda.
⏸ Ko'p nazoratchi — kamida 1 yildan keyin.
⏸ Webhook'ga o'tish.
⏸ _day_close_tick: 20:00 dan keyin yopilmagan kun uchun nazoratchiga avtomatik minus — 2-smena ~01:00 gacha ishlaydi, to'qnashuv. Yangi muddat Muhammadiy qaroriga bog'liq.
⏸ Kassa/ombor/moshina/market fotolari retention: muddat e'lon qilingan, haqiqiy avtomatik o'chirish yoqilmagan. Telegram'da faylni abadiy o'chirish API'si yo'q, faqat xabarni o'chirish mumkin. (manba: eski FOKUS_AI_STATE.md)
⏸ Admin/Founder majburiy smena yopish buyrug'i — filial tashlab ketilsa smena PENDING_HANDOVER/NEEDS_SUPERVISOR_APPROVAL da qolib ketishi mumkin (holati TEKSHIRILMAGAN). (manba: eski FOKUS_AI_STATE.md)
## 7. Bekor qilingan / kerak emas
❌ Test botda ishlash.
❌ Eski Oregon servisi (Web Service → Background Worker → keyin Singapore Web Service'ga ko'chirilgan).
❌ Windows'da Claude ishlatish (→ Codespaces Linux).
❌ Genora AI va shunga o'xshash pullik "hammasi bir joyda" ilovalar.
❌ ChatGPT suhbatini to'g'ridan-to'g'ri botga "ulash" — imkonsiz; bot faqat OpenAI API + berilgan bilim orqali ishlaydi.
- ❌ So'm-asosidagi kunlik bonus formulasi (STAGE 9) — ball tizimi tanlandi (2026-10-18).
## 8. Kod nuqsonlari (2026-10-06/07 holati — joriy holati TEKSHIRILMAGAN; tekshiruv alohida vazifa)
⚠️ "🏬 Filiallar" (eski karta oqimi) va /baholash parallel; xodimlar ro'yxati farq qiladi.
⚠️ Bitta filial yopilsa butun kun "yopildi" bo'ladi, jarima tushmaydi.
⚠️ Founder menyusidagi "Rol testi" 2 ta testi yiqilgan (PR #46 hisoboti, 2026-10-07).
⚠️ (eski, TEKSHIRILMAGAN) handle_hire (recruiting_bot.py) approval.py dagi mantiqni umumiy funksiyaga chiqarmasdan nusxalaydi. (manba: eski FOKUS_AI_STATE.md)
⚠️ (eski, TEKSHIRILMAGAN) roles.find_user_by_role global birinchi mosni qaytaradi — 10+ filialda muammo bo'lishi mumkin (kunlik yopish nazoratchini shu orqali topadi). (manba: eski FOKUS_AI_STATE.md)
⚠️ (eski, TEKSHIRILMAGAN) decide_penalty_appeal da atomik "WHERE status = expected" guard yo'q; hozircha await yo'qligi sababli xavfsiz, lekin kelajakda AI-qadam qo'shilsa guard kerak. (manba: eski FOKUS_AI_STATE.md)
⚠️ (eski, TEKSHIRILMAGAN) employees.photo_file_id (doimiy profil foto) tasdiqdan keyin hech qachon qayta o'qilmaydi. (manba: eski FOKUS_AI_STATE.md)
⚠️ (eski, TEKSHIRILMAGAN) tests/test_recruiting_bot_flow.py da ~14 ta eski test yiqilgan (photo majburiy bo'lgandan keyin eskirgan). (manba: eski FOKUS_AI_STATE.md)
⚠️ (eski, TEKSHIRILMAGAN) RECRUITING_BRANCH_NAMES placeholder (Filial-1, Filial-2) — production uchun haqiqiy filial nomlari kerak; content/daily_greetings rasmlarini Founder qo'yishi kerak. (manba: eski FOKUS_AI_STATE.md)
## 9. Eski hujjatlar
⚠️ Repo'da (2026-09-02 holatiga ko'ra) allaqachon bor: docs/FOKUS_MEMORY.md, docs/NEXT_STEP.md, docs/PROJECT_STATE.md, docs/IDEAS.md, docs/IS_MODE.md, CLAUDE.md. Robot bu faylni qo'shishdan OLDIN ularni tekshiradi: dublikat yaratilmaydi — mavjud fayllarga birlashtiriladi yoki eskilari shu faylga ishora qiladi. Hozirgi STATE fayli: FOKUS_AI_STATE.md.
FOKUS_AI_BOSHQARUV_MARKAZI.md (ChatGPT Space, 2026-09-30) va FOKUS_AI_texnik_hulosa_2026-09-19.pdf — eskirgan. Qoidalari shu faylga ko'chirildi. Holat uchun ishlatilmaydi.
## 10. Alohida loyihalar (FOKUS AI emas — aralashtirilmaydi)
VAQT AFANDI: Sales Doctor (sagbanqoqon.salesdoc.io) API → prixod/sotuv. Alohida papka, FOKUS AI fayllariga tegilmaydi.
Xodimlar viktorinasi (Telegram Mini App), nizom audio, Saturn multfilm, KPI dashboard.
Manba chatlar (1-2 bosqich): FOKUS AI Autopilot ×2 · Rekruting · menedjer · Rejim yoqildi · Fokus rejimi yoqildi ×2 · Sandbox DB routing map · PR tekshiruvi tasdiqlandi · Еженедельный статус · FOKUS release/production/1-qism · Mutaxassislar e'loni · AI Nazoratchi G'oyasi · Tong va tun xabarlari · Sales Doctor va AI · FOKUS AI keragi Bormi · Tanqid va fikr-mulohaza · BOSHQARUV_MARKAZI.md · Render to'lov eslatmasi (6a95e32d) Qolgan (3-bosqich): Render to'lov eslatmasi (6abb2fca) · Bot token xavfsizligi · Claude automation blocked · GitHub Actions Failure Check · Loyiha holatini yangilash · Salomlashuv javobi · Javob bermaslik · ro'yxat oxiridagi eski chatlar.
## 11. Hal qilingan ziddiyatlar (Muhammadiy, 2026-10-18)
1. Claude'ga ulanish usuli. A) docs/FOKUS_MEMORY.md: KANONIK usul — .claude/tasks/<sana>-<nom>.md ni feature/hr-conversational-interview branchiga push qilish (claude-task-runner). B) FOKUS_AI_XOTIRA.md (4-bo'lim): hozirgi asosiy usul — Codespaces ichidagi Claude Code (Usul 2); Usul 1 faqat shu bitta branchda ishlaydi. (manba: eski docs/FOKUS_MEMORY.md ↔ FOKUS_AI_XOTIRA.md) QAROR: eski usul (A) kanonik: `.claude/tasks/<sana>-<nom>.md` → `feature/hr-conversational-interview` → claude-task-runner. Codespaces usuli (B) — zaxira. ⚠️ Usul A faqat shu branchda ishlaydi.
2. Full test. A) CLAUDE.md va docs/IS_MODE.md: full test faqat Founder aniq so'rasa/odatda ishlatilmaydi. B) FOKUS_AI_XOTIRA.md (2-bo'lim): full test release oldidan ham ishlatilishi mumkin. (manba: eski docs/IS_MODE.md ↔ FOKUS_AI_XOTIRA.md) QAROR: (A) faqat Muhammadiy aniq so'raganda. Release oldidan avtomatik emas.
3. Tijoriy mahsulot yo'li. A) docs/IDEAS.md: bir nechta real biznesda parallel sinash orqali xato topish. B) FOKUS_AI_XOTIRA.md (5-bo'lim): avval o'z do'konlarida isbot, 1-mijozlarga alohida bot+DB, multi-tenant faqat bir nechta mijozdan keyin. (manba: eski docs/IDEAS.md ↔ FOKUS_AI_XOTIRA.md) QAROR: hozir mijozlarga berilmaydi. Avval o'z do'konlarida to'liq sinovdan o'tadi; tijoriy bosqich vaqti kelganda alohida hal qilinadi.
4. Test muhiti. A) FOKUS_AI_XOTIRA.md (1-bo'lim): faqat production bot, test botga qaytilmaydi. B) eski FOKUS_AI_STATE.md: real Telegram E2E va deploylar fokus-ai-test botida yuritilgan (test muhiti keng ishlatilgan). (manba: eski FOKUS_AI_STATE.md ↔ FOKUS_AI_XOTIRA.md) QAROR: (A) faqat real (production) bot. Test botga tegilmaydi, unga oid eski yozuvlar tarix hisoblanadi.
5. Bonus modeli. A) eski FOKUS_AI_STATE.md: Founder tasdiqlashi kutilgan aniq so'm-asosidagi kunlik bonus formulasi (STAGE 9). B) docs/IDEAS.md va amaldagi kod: ball-asosidagi bonus/minus tizimi, "1 ball necha so'm" hali ochiq. Ikki model aralashtirilmaydi — qaysi biri tanlanishini Muhammadiy hal qiladi. (manba: eski FOKUS_AI_STATE.md ↔ docs/IDEAS.md) QAROR: BALL tizimi (B). So'm-asosidagi kunlik bonus formulasi (STAGE 9) bekor. Ball qiymati — 12-bo'limda.

## 12. Bonus va minus ball modeli (ichki nizom, 2026-08-26 — Muhammadiy tasdiqlagan)
Manba: Saturn ichki tartib qoidalari. Nizom matnlarining yagona manbasi — `company_rules` (bu yerga nusxalanmaydi).
- ✅ NIZOM — KOMPANIYA QONUNI. AI, ChatGPT, Sodiq yoki robot nizom matnini, ballarini yoki qoidasini O'ZGARTIRMAYDI. Faqat Muhammadiyga sababli taklif beriladi; o'zgarish yoki qo'shimchani faqat Muhammadiy kiritadi.
- Quyidagi bandlar nizomning qisqa xulosasi (bot hisob-kitobi uchun); nizom matni bilan farq bo'lsa — NIZOM ustun.
- ✅ 1 ball = 5 000 so'm (ichki hisob).
- ✅ Maqsad — jazolash emas, bonus orqali intizom. Bonus: vaqtida kelish, vazifani to'g'ri bajarish.
- ✅ Minus ball faqat SHU OYDA ishlab topilgan bonusdan ayriladi. Asosiy oylikdan olinmaydi, naqd talab qilinmaydi, qarz yozilmaydi.
- ✅ Bonus yetmasa — faqat mavjud bonus nolga tushadi; ortig'i kechiriladi (qarz emas, keyingi oyga o'tmaydi, xayriyaga/kompaniyaga o'tmaydi).
  Misol: bonus 100 000, minus −6 ball (30 000) → beriladi 70 000. Bonus 20 000, minus 30 000 → beriladi 0, qolgan 10 000 kechiriladi.
- ✅ Har oy oxirida hisob yopiladi, yangi oy noldan. Qoidabuzarlik esa xodim tarixida SAQLANADI.
- ✅ Bitta qoidabuzarlik — bitta minus. Har minus dalil bilan qayd etiladi va sababi xodimga tushuntiriladi.
- ✅ Har qanday muammo nizom asosida hal qilinadi; rahbar ham, xodim ham taxmin bilan chora ko'rmaydi. Nizom davlat qonuni yoki diniy qadriyatlarga zid bo'lsa qo'llanmaydi — direktorga taqdim etiladi.
- ✅ Faqat nizomda aniq yozilgan qoidabuzarlik uchun minus; har bandning balli o'sha bandda. Nizom hamma uchun bir xil (direktor ham).
- ✅ O'zi tan olsa (inspektor aniqlashidan oldin, guruhga yozsa) — minus 50%.
- ✅ "Noaniq": xodim rozi bo'lmasa tortishmaydi, "noaniq" deb belgilaydi; inspektor eslatma yozadi (yozmasa −10); oy oxirida bonus hisobidan OLDIN direktor/vakolatli rahbar hal qiladi. Tortishuv chiqargan xodim yoki inspektorga −60.
- ✅ Buyruq bajarilmasa: buyruqda ball ko'rsatilmagan bo'lsa — −10; buyruqda boshqa ball ko'rsatilgan bo'lsa — o'sha miqdor.
- ✅ Jiddiy/takroriy buzilishda — alohida ogohlantirish; zarur bo'lsa ishda qolishi qayta ko'rib chiqiladi.
- ✅ Vaqtida kelib, erta ketmaydigan xodimga maxsus bonus; miqdorini savdo bo'limi rahbari belgilaydi.
- ✅ Kechikkan vaqt ishlangan vaqt hisoblanmaydi (haq faqat ishlangan vaqt uchun).
- ✅ Bir hafta ichida 3 marta kechiksa — haftalik bonus berilmaydi. Ruxsatsiz, sababsiz va xabarsiz 1–2 soat kechiksa — −6.
- ✅ Nizomlar: 26 ta band (26-band 2026-08-29 qo'shilgan).
- ✅ (Bot qoidasi, nizom emas) AI ball yozmaydi — faqat tavsiya; ballni inspektor/nazoratchi yozadi.
