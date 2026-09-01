FOKUS AI — “⭐ Mening natijalarim” menyusini emojili va 2 ustunli qilish.

QAT’IY MUHIT

NATIVE WINDOWS EXECUTION = 0.
Faqat remote Linux va bash ishlat. Windows, PowerShell, CMD yoki local Git Bash ishlatma. Hozirgi runner Linux bo‘lsa davom et; faqat u GitHub Actions muhiti emasligi sabab STOP qilma.

VAZIFA

Faqat `⭐ Mening natijalarim` umumiy menyusini soddalashtir. Telegram Reply Keyboard haqiqiy rasmni qo‘llamaydi, shuning uchun “rasmli” ko‘rinish emoji orqali qilinsin. Rasm, media, WebApp yoki yangi inline tizim yaratma.

Tugmalar aynan quyidagi 4×2 tartibda chiqsin:

1-qator:
- `⭐ Yulduzlarim`
- `💰 Oyligim`

2-qator:
- `📅 Grafik so'rovi`
- `🏆 Bugungi o'rnim`

3-qator:
- `🏅 Oylik reyting`
- `📋 Nizomlar`

4-qator:
- `⚠️ E'tiroz bildirish`
- `🔙 Orqaga`

ICHKI BUYRUQ BOG‘LANISHI

- `⭐ Yulduzlarim` → `/mystars`
- `💰 Oyligim` → `/mymaosh`
- `📅 Grafik so'rovi` → `/grafik`
- `🏆 Bugungi o'rnim` → `/bugungiporga`
- `🏅 Oylik reyting` → `/oylikturnir`
- `📋 Nizomlar` → `/listnizom`
- `⚠️ E'tiroz bildirish` → `/apellyatsiya`

Faqat quyidagi fayllarni o‘zgartir:
- `main.py`
- `tests/test_menu_and_fsm_escape.py`
- `tests/test_role_test_sandbox.py`

AMALGA OSHIRISH

1. `_SHARED_COMMANDS`ni yuqoridagi ekran tartibiga mos joylashtir.
2. Kassir va Nazoratchi patterniga mos `_SHARED_BUTTON_LABELS` xaritasini yarat.
3. Yangi emoji tugmalarni mavjud `_STALE_LABEL_TO_COMMAND` mexanizmi orqali asl buyruqlarga bog‘la. Parallel router yoki yangi handler yaratma.
4. `build_category_menu()`ni minimal kengaytir: faqat shared menyuda oxirgi amal tugmasi bilan `🔙 Orqaga` bir qatorda juftlansin. Default xulq o‘zgarmasin.
5. `category_menu_handler()` shared bo‘limda yangi label xaritasi va juftlash rejimini ishlatsin.
6. Shared xabar tanasida xom slash-buyruqlar ro‘yxatini ko‘rsatma. Mazmun:
   `⭐ Mening natijalarim`
   `Kerakli bo'limni tanlang:`
7. `_preview_category_keyboard()` ham aynan shu emoji tugmalar va 4×2 tartibni ishlatsin. `⬅️ Testdan chiqish` keyingi alohida qatorda qolsin.
8. Sandboxda emoji tugma bosilganda mavjud xavfsizlik saqlansin: haqiqiy handler bajarilmasin va bazaga hech narsa yozilmasin.
9. Qo‘lda yozilgan eski `/buyruq`lar va Telegramda keshlangan eski uzun tugmalar ishlashda davom etsin.

CHEGARALAR

- Mavjud yettita command handlerini o‘zgartirma.
- DB, migratsiya, service, repository, RBAC va biznes mantiqqa tegma.
- Boshqa rol menyularining matni yoki joylashuvini o‘zgartirma.
- Yangi tashqi kutubxona qo‘shma.

TESTLAR

Testlarda quyidagilarni isbotla:
- real shared menyu aynan yuqoridagi 4×2 qatorda chiqadi;
- xabar va tugmalarda xom slash-buyruqlar ko‘rinmaydi;
- yettita emoji nomning hammasi to‘g‘ri ichki buyruqqa bog‘langan;
- `⭐ Yulduzlarim` bosilishi mavjud `/mystars` oqimini ochadi;
- sandbox preview ham shu 4×2 ko‘rinishni beradi;
- preview ichida emoji tugma bloklanadi va haqiqiy amal bajarilmaydi;
- eski uzun `/mystars — Mening yulduzlarim` tugmasi ishlaydi.

Faqat:
`python -m pytest -q tests/test_menu_and_fsm_escape.py tests/test_role_test_sandbox.py`

Full test, Smoke va E2E’ni qo‘lda ishga tushirma.

Targeted testlar PASS bo‘lsa:
- commit: `feat: add friendly paired results menu`
- faqat `feature/hr-conversational-interview` branchiga safe push qil;
- keyingi vazifaga o‘tma;
- avtomatik CI natijasini PASS deb taxmin qilma.

Yakuniy javobda faqat commit, o‘zgargan fayllar, targeted test natijasi va push holatini qisqa yoz.