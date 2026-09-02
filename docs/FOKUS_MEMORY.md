# FOKUS AI — doimiy xotira kirish nuqtasi

Bu fayl yangi chat/sessiyada FOKUS AI holatini tez tiklash uchun KANONIK KIRISH NUQTASI.

## Yangi sessiya qoidasi

Foydalanuvchi faqat:

`FOKUS AI, davom et.`

desa, avval quyidagilarni tekshir:

1. `docs/IS_MODE.md` — Iqtisodchi Sodiq rejimi va xarajat/nazorat qoidalari.
2. `docs/NEXT_STEP.md` — aynan qayerda to'xtaganmiz va keyingi bitta qadam.
3. `docs/PROJECT_STATE.md` — joriy loyiha holati, branch/deploy/modullar.
4. `docs/IDEAS.md` — hali bajarilmagan yoki kelajak uchun saqlangan g'oyalar.
5. Real Git/GitHub holati — branch, HEAD, commit/push; ziddiyat bo'lsa Git/GitHub ustuvor.

Shundan keyin:
- foydalanuvchidan eski ma'lumotni qayta so'rama;
- boshidan boshlama;
- eski chatni qayta aytib bermagin;
- faqat eng oxirgi tasdiqlangan nuqtadan davom et;
- bir vaqtda imkon qadar bitta keyingi qadam ber;
- I/S yoqilgan bo'lsa promptni avval tanqid qilib Founderga ko'rsat, `jo'nat` deyilmaguncha Claude'ga bermagin.

## Claude'ga ulanish — KANONIK USUL

Claude bilan FOKUS AI uchun ishlash usuli doim shu:

1. Vazifani `.claude/tasks/<sana>-<qisqa-nom>.md` fayliga yoz.
2. Faylni `feature/hr-conversational-interview` branchiga commit/push qil.
3. `.github/workflows/claude-task-runner.yml` shu pushni avtomatik ushlab, `Claude Task Runner`ni ishga tushiradi.
4. Runner task faylini Claude Code Action'ga yuboradi; Windows ishlatilmaydi, Ubuntu/Linux ishlaydi.
5. Keyin GitHub Actions'dan aynan `Claude Task Runner` runini tekshir: `in_progress`, `success` yoki `failure`.
6. `in_progress` bo'lsa ayni vazifani qayta jo'natma. Tugagach Claude yaratgan commit/test natijasini real tekshir.

Muhim:
- `Claude'ga jo'nat` degani oddiy matn berish emas; yuqoridagi `.claude/tasks/...md` + feature branch push usuli.
- I/S rejimida foydalanuvchi aniq `jo'nat` demaguncha task faylini yaratma/push qilma.
- Claude taski ketayotgan paytda takroriy prompt yuborib ortiqcha xarajat qilma.
- `main`/productionga Claude task runner orqali to'g'ridan-to'g'ri tegma.

## Rejim buyrug'i

### `I/S` yoki `Iqtisodchi Sodiq rejimi`
- `docs/IS_MODE.md`dagi qoidalarni darhol yoq;
- eng kam token, vaqt va pul sarfla;
- faqat bitta kichik vazifa tanla;
- full test o'rniga targeted test ishlat;
- natijani haqiqiy logdan tekshir;
- joriy ish tugamaguncha keyingi vazifaga o'tma.

## Saqlash buyruqlari

### `G'oya:` yoki `G'oyani saqla:`
Foydalanuvchi shu ibora bilan yangi fikr aytsa:
- uni `docs/IDEAS.md`ga qo'sh;
- mavjud g'oyani o'chirma;
- g'oyani `NEW`, `PLANNED`, `IN_PROGRESS`, `DONE`, `REJECTED` holatlaridan biri bilan saqla;
- amalga oshirish boshlanmagan bo'lsa kodga tegma.

### `Oxirgi qadamni saqla:`
Foydalanuvchi shu iborani aytsa:
- `docs/NEXT_STEP.md`ni yangila;
- oldingi yakunlangan qadamni `DONE` tarixiga o'tkaz;
- aynan keyingi BIRTA qadamni yoz;
- branch, HEAD/commit, test/deploy holati ma'lum bo'lsa yoz;
- taxminni fakt sifatida saqlama.

### Muhim ish tugaganda
Har muhim commit/deploy/qarordan keyin:
- `docs/PROJECT_STATE.md`ni yangila;
- `docs/NEXT_STEP.md`ni yangila;
- yangi kelajak g'oyasi paydo bo'lsa `docs/IDEAS.md`ga qo'sh.

## Ustuvorlik

1. Real Git/GitHub/Render holati
2. `docs/IS_MODE.md`
3. `docs/NEXT_STEP.md`
4. `docs/PROJECT_STATE.md`
5. `docs/IDEAS.md`
6. Eski chat xotirasi

Hech qachon eski chatdagi taxmin real repo holatidan ustun bo'lmasin.
