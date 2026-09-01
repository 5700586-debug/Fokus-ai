# FOKUS AI — menyu knopkalarini soddalashtirish

I/S STRICT: kam token, kam fayl, faqat bitta UI vazifa.

BRANCH: `feature/hr-conversational-interview`

MAQSAD:
Telegramdagi foydalanuvchiga ko'rinadigan knopkalarni oddiy, qisqa, emoji bilan va imkon qadar 2 tadan yonma-yon qil.

FAQAT SHU FAYLLARGA RUXSAT:
- `main.py`
- `tests/test_menu_and_fsm_escape.py`
- `tests/test_role_test_sandbox.py`

Boshqa fayl kerak bo'lsa STOP.
DB, role/permission, business logic, handlerlarning haqiqiy ishlashiga tegma.

QOIDALAR:
1. Knopkalarda texnik `/buyruq` matni ko'rinmasin. Eski slash commandlar ichkarida ishlashda davom etsin.
2. Friendly label bosilganda hozirgi real handler/command ishlasin.
3. Imkon qadar knopkalarni 2 tadan yonma-yon qil. Juda uzun bo'lsa alohida qator mumkin.
4. Har bir knopka oddiy xodim tushunadigan qisqa nom + mos emoji bo'lsin.
5. `⭐ Mening natijalarim` ichida aynan:
   [⭐ Yulduzlarim] [💰 Oyligim]
   [📅 Grafik so'rovi] [🏆 Bugungi o'rnim]
   [🏅 Oylik reyting] [📋 Nizomlar]
   [🙋 E'tirozim bor] [🔙 Orqaga]
6. `🙋 E'tirozim bor` mavjud `/apellyatsiya` flow'ini ishga tushirsin.
7. Founder/asosiy menyu va boshqa ko'rinadigan menu knopkalarida ham shu prinsipni qo'lla: qisqa, sodda, emoji, imkon qadar 2 ustun. Xom slash-buyruq knopkada ko'rinmasin.
8. Eski cached/friendly label mapping va slash command backward compatibility buzilmasin.
9. Yangi feature, refactor, arxitektura o'zgarishi YO'Q.

TEST FAQAT:
`python -m pytest -q tests/test_menu_and_fsm_escape.py tests/test_role_test_sandbox.py`

Full test YO'Q.

Tekshir:
- 2-column layout
- yangi friendly label -> eski real action
- `🙋 E'tirozim bor` -> mavjud apellyatsiya flow
- eski slash commandlar ishlaydi
- role test/sandbox buzilmagan

Agar test expectationlari eski bo'lsa, faqat shu ikki test faylini yangila. Production business logicni test uchun o'zgartirma.

Windows = 0. Linux/bash only.

PASS bo'lsa commit message:
`refactor: simplify menu buttons to 2-column emoji layout`

YAKUNIY HISOBOT FAQAT:
- o'zgargan fayllar
- yangi knopka ko'rinishi
- targeted test natijasi
- commit SHA

Keraksiz izoh yozma.