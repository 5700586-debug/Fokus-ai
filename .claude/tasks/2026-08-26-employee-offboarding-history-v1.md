# FOKUS AI — Xodimni ishdan chiqarish / tarixni saqlash V1

Maqsad: mavjud Nazoratchi/Founder xodim kartasiga xavfsiz, tarixni o'chirmaydigan ishdan chiqarish oqimini qo'shish.

## Qat'iy chegaralar

- Faqat `feature/hr-conversational-interview` branchida ishlagin.
- `main` va productionga tegma.
- Avval `CLAUDE.md`, `.claude/rules.md`, `FOKUS_AI_STATE.md`, `docs/PROJECT_STATE.md` va xodim/recruiting/nazoratchi arxitekturasini o'qib, mavjud status va repository/service naqshlarini qayta ishlat.
- Yangi parallel employee modeli yaratma.
- Xodim yozuvini fizik `DELETE` qilma. Tarix, bonus/minus ledger, attendance, task assignment, schedule revision va boshqa tarixiy yozuvlar saqlansin.
- Hech qanday jarima, pul, bonus yoki yangi biznes qoidani o'ylab topma.
- Real Telegram xabar yuborish ikkilamchi: DBdagi holat o'zgarishi xabar yuborish xatosi sabab rollback bo'lmasin.

## V1 funksiyasi

1. Founder/Nazoratchi ko'radigan mavjud xodim kartasida, ruxsat bo'lsa, `🚪 Ishdan chiqarish` tugmasini qo'sh.
2. Tugma bosilganda aniq tasdiqlash ekrani chiqsin: xodim ismi, filial/lavozim, va "tarix o'chmaydi, faqat aktiv holatdan chiqariladi" degan sodda matn.
3. Tasdiqlangandan keyin mavjud employee status/approved/active arxitekturasidagi eng to'g'ri, eng kichik o'zgarish bilan xodimni aktiv ro'yxatdan chiqar. Agar bitta kanonik status manbai bo'lsa o'shani ishlat; ikki joyni qo'lda sinxronlab yuradigan yangi yechim yaratma.
4. Amaliyot audit qilinsin: kim chiqardi, qachon, oldingi holat, yangi holat. Agar mavjud revision/audit infratuzilmasi mos bo'lsa uni qayta ishlat; bo'lmasa minimal alohida audit yozuvi qo'sh.
5. Ikki marta confirm bosilsa faqat bitta real state transition/audit natijasi bo'lsin (idempotent).
6. Ishdan chiqarilgan xodim odatiy `aktiv xodimlar` ro'yxatidan yo'qolsin, lekin tarixiy ma'lumotlarini repository/service orqali o'qish imkoni saqlansin.
7. Founder o'zini ishdan chiqara olmasin. Nazoratchi o'zini ham, o'z ruxsatidan tashqaridagi filial xodimini ham boshqara olmasin; mavjud RBAC/branch-access qoidalarini qayta ishlat.
8. Agar xodimga kelajakdagi schedule yoki branch-visit requirement biriktirilgan bo'lsa, ularni fizik o'chirma. V1da faqat xodimning aktiv statusi o'zgarsin; tarix va reja yozuvlari keyingi tarixiy ko'rish uchun saqlansin.

## Test

Faqat kerakli targeted Linux testlar:
- Founder muvaffaqiyatli offboarding;
- Nazoratchi branch permission;
- self-offboarding blok;
- unauthorized role blok;
- double-confirm idempotency;
- aktiv ro'yxatdan yo'qolishi;
- employee va tarixiy ledger/attendance/task/schedule ma'lumotlari o'chmaganini tekshirish.

Mavjud yaqin regression testlardan faqat zarurlarini qo'sh. Katta full-suite shart emas.

PASS bo'lsa o'zgarishlarni bitta mantiqiy commit qilib shu feature branchga push qil. `.claude/tasks/` fayllarini natija commitida o'zgartirma.
