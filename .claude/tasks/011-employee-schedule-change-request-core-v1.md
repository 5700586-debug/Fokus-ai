# Employee schedule-change request core V1

Maqsad: xodim smena/grafik o‘zgarishini so‘rashi va Nazoratchi tasdiqlasa mavjud schedule tizimi yangilanishi uchun minimal core qatlamni qur.

Qat’iy:
- Native Windows execution = 0. Test/runtime faqat GitHub Actions `ubuntu-latest`.
- `main`/productionga tegma. Feature branchda ishlagin.
- Faqat tegishli attendance/schedule schema, repository/service va yangi targeted testlarni o‘qi/o‘zgartir. Repo-wide audit/refactor yo‘q, yangi dependency yo‘q.
- Mavjud `employee_scheduled_shifts` + schedule revision mexanizmini qayta ishlat; parallel ikkinchi schedule tizimi yaratma.

V1:
1. Xodim uchun bitta sana va so‘ralgan grafik (work: start/end/mode yoki off) bilan `pending` request yaratish.
2. Nazoratchi/Founder qarori: approve yoki reject. Qaror faqat `pending`dan bir marta o‘tsin; takroriy/race qaror no-op bo‘lsin.
3. Approve bo‘lsa mavjud schedule yozuvi yangilansin va mavjud revision/audit tarixi saqlansin; reject bo‘lsa schedule o‘zgarmasin.
4. Requestda employee, sana, so‘ralgan qiymatlar, sabab (optional), status, created/decided by/at saqlansin. Hech narsani DELETE qilma.
5. Hozir Telegram UI, avtomatik minus/bonus, notification va yangi biznes qoidalarini qurma.

Acceptance:
- yangi request pending holatda saqlanadi;
- approve schedule’ni to‘g‘ri qo‘llaydi va audit revision qoladi;
- reject schedule’ga tegmaydi;
- ikkinchi approve/reject schedule’ni qayta yozmaydi/revision dublikat qilmaydi;
- noto‘g‘ri vaqt/status validatsiyasi mavjud schedule service qoidalarini chetlab o‘tmaydi.

Faqat eng tor targeted Linux testlarni ishlat. PASS bo‘lsa minimal commit/push qil va `docs/PROJECT_STATE.md`ni faqat real natija bilan yangila. Task faylini natija commitida o‘zgartirma.