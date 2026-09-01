FOKUS AI ! — 1-QISM: TELEGRAM MENYU VA FOUNDER KNOPKALARINI YAKUNIY YOPISH

I/S STRICT.
Windows = 0. Faqat remote Linux/bash.
Branch: feature/hr-conversational-interview

Hozirgi funksional commit: 0413f511 — `refactor: simplify menu buttons to 2-column emoji layout`.

Maqsad: shu mavjud ishni boshidan qayta yozmasdan tekshir va 1-qismni yop.

QAT'IY TARTIB:
1. Avval faqat `0413f511`dagi real menyu o'zgarishini tekshir.
2. Founder va boshqa role/categorylarda foydalanuvchiga xom `/command` ko'rinmasligini tekshir.
3. Imkon qadar 2 ta knopka bir qatorda ekanini tekshir.
4. `Mening natijalarim` aynan 4x2 bo'lsin:
   [⭐ Yulduzlarim] [💰 Oyligim]
   [📅 Grafik so'rovi] [🏆 Bugungi o'rnim]
   [🏅 Oylik reyting] [📋 Nizomlar]
   [🙋 E'tirozim bor] [🔙 Orqaga]
5. Friendly label -> mavjud real command/handler mapping ishlasin. Eski slash commandlar ishlashda davom etsin.
6. Role/permission, DB va business logicga tegma.
7. Faqat quyidagi targeted testni ishlat:
   `python -m pytest -q tests/test_menu_and_fsm_escape.py tests/test_role_test_sandbox.py`
8. FULL TEST YO'Q.

MUHIM:
- Agar targeted test PASS va yuqoridagi talablar real kodda bajarilgan bo'lsa: HECH NARSANI O'ZGARTIRMA, commit qilma, `1-QISM = DONE` deb STOP qil.
- Faqat aniq test xatosi yoki aniq talab buzilishi topilsa eng kichik tuzatish qil.
- Keraksiz refactor, broad audit, yangi fallback arxitekturasi, boshqa feature YO'Q.
- Boshqa production fayl kerak bo'lsa STOP va sababini ayt.
- 2-QISM nizom oqimiga tegma.
- 3-QISM Mini Appga tegma.

YAKUNIY HISOBOT FAQAT:
1. tekshirilgan commit
2. o'zgargan fayl bo'lsa nomi
3. real xato topildimi/yo'qmi
4. targeted test natijasi
5. commit SHA (agar o'zgarish bo'lsa)
6. `1-QISM = DONE` yoki `BLOCKED`
