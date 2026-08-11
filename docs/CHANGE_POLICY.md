# Fokus AI — O'zgarish siyosati

Loyiha yana chalkashib ketmasligi uchun har bir yangi o'zgarish shu
tartibda amalga oshiriladi.

## Bosqichlar

1. **Vazifa ta'rifi.** Nima kerak, nega kerak — bir-ikki jumla
   (Issue/topshiriq matnida yoki commit ta'rifida).
2. **Qabul mezoni.** "Qanday holatda bu bajarilgan hisoblanadi" —
   oldindan aniq belgilanadi (masalan "Founder `/setrule` bilan X
   qiymatini o'zgartira olsin va bu darhol keyingi hisoblashda
   ko'rinsin").
3. **Tegishli modulni aniqlash.** `docs/ARCHITECTURE.md` §6 ("Yangi
   funksiya qayerga qo'shiladi") bo'yicha qaysi qatlamga tegishli
   ekanini top — handler/service/repository/schema.
4. **Kod yozish.** Qatlam chegaralariga rioya qilinadi (handlerda SQL
   yo'q, service Telegram obyektini bilmaydi, va h.k. — qarang
   `ARCHITECTURE.md` §2). Yangi son/vaqt/miqdor — `services/rules.py`
   orqali, hardcode qilinmaydi.
5. **Test.** Kamida: yangi biznes mantiq uchun `services/`
   darajasidagi test, yangi handler uchun `bot_dp` fixture bilan oqim
   testi. `python -m pytest -q` to'liq yashil bo'lishi shart.
6. **Review.** O'zi yozgan kodni diff sifatida qayta o'qish — ayniqsa
   qatlam chegaralari, xavfsizlik (SQL parametrlanganmi, secret
   loglanmayaptimi), va `ARCHITECTURE.md §7`dagi bilingan cheklovlarga
   zid kelmasligini tekshirish.
7. **Staging/lokal tekshiruv.** Kamida lokal (SQLite) test to'plami
   yashil; agar SQL naqshi o'zgargan bo'lsa — Postgres bilan ham
   (`DEPLOYMENT.md` §2dagi Docker usuli yoki CI).
8. **Production.** `main` branchga merge, `git push origin main` —
   Render avtomatik deploy qiladi. Deploydan keyin loglarni tekshirish
   (`init_db()` xatosi, `TelegramConflictError` yo'qligi).
9. **Hujjatni yangilash.** Agar yangi funksiya/qoida qo'shilgan bo'lsa
   — `docs/FEATURE_STATUS.md` va/yoki `docs/BUSINESS_RULES.md`ni shu
   PR ichida yangilash (keyinga qoldirilmaydi — aks holda hujjat
   kod bilan mos kelmay qoladi).

## Qat'iy chegaralar (har doim amal qiladi)

- Handler ichida to'g'ridan-to'g'ri SQL yozilmaydi.
- Biznes mantiq Telegram handlerga bog'lanib qolmaydi (Telegram
  obyektlarisiz test qilinadigan bo'lishi kerak).
- AI (OpenAI) hech qachon moliyaviy/biznes qarorni o'zi qabul qilmaydi
  — faqat tavsiya/tushuntirish beradi, deterministik gate/inson
  tasdiqlashi doim oldin yoki keyin turadi.
- Yangi son/vaqt/miqdor kodga hardcode qilinmaydi — `rules` jadvali
  orqali.
- Aniq bo'lmagan biznes qoidasi (mavjud kod bilan zid yoki noaniq)
  taxmin qilib yozilmaydi — `docs/BUSINESS_RULES.md`da
  `NEEDS_BUSINESS_DECISION` deb belgilanadi, Founderdan aniqlik
  so'raladi.
- Production ma'lumotini o'chiradigan/qayta yozadigan migration
  yozilmaydi (`DEPLOYMENT.md` §5).
- Secret/token/parol kodga yoki logga yozilmaydi.
- Force push va git tarixini buzish yo'q; katta o'zgarishdan oldin
  checkpoint commit va (agar xavfli bo'lsa) alohida branch.
