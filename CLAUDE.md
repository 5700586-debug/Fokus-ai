Har yangi vazifadan oldin FOKUS_AI_XOTIRA.md va FOKUS_AI_STATE.md ni o'qi.

@.claude/rules.md
@FOKUS_AI_XOTIRA.md
@FOKUS_AI_STATE.md

# Ish tartibi

- Yangi sessiyada avval `FOKUS_AI_XOTIRA.md` qoidalariga amal qil.
- `I/S` yoki `Iqtisodchi Sodiq rejimi` deyilsa `FOKUS_AI_XOTIRA.md` 2-bo'limi (I/S1) darhol yoqiladi va barcha keyingi ishda ustuvor bo'ladi.
- `FOKUS AI, davom et.` deyilsa `FOKUS_AI_STATE.md` + `FOKUS_AI_XOTIRA.md` + real Git/GitHub holatidan oxirgi nuqtani tikla; boshidan boshlama va foydalanuvchidan eski ma'lumotni qayta so'rama.
- `G'oya:` yoki `G'oyani saqla:` deyilsa g'oyani `FOKUS_AI_XOTIRA.md` ning 5-bo'limiga (💡, sana, manba) yo'qolmaydigan qilib qo'sh; kodni avtomatik boshlama.
- `Oxirgi qadamni saqla:` deyilsa `FOKUS_AI_STATE.md`ni real checkpoint bilan yangila.
- 1 prompt = 1 aniq maqsad.
- Avval mavjud holatni bil (git, Render, `FOKUS_AI_STATE.md`) — boshidan boshlama.
- Keraksiz repo audit qilma.
- Keraksiz refactor qilma.
- Full testni faqat Founder aniq so'rasa ishlat.
- Odatda faqat o'zgargan qismga minimal syntax/import tekshiruv yetarli.
- Bir buyruq uzoq cho'zilsa, maqsadni yo'qotib kutib turma.
- `main` va productionga Founder aniq ruxsat bermasa tegma.
- Secret, token, `.env`, API keyni commit/log/chatga chiqarma.
- Kodni imkon qadar minimal o'zgartir.
- Mavjud ishlaydigan arxitekturani sabab bo'lmasa qayta qurma.
- Har PR ichida `FOKUS_AI_STATE.md` ni yangila (bajarilgan ish + keyingi qadam).
- Kelajak g'oyasi paydo bo'lsa `FOKUS_AI_XOTIRA.md` ga qo'sh.
- Kerak bo'lsa faqat tegishli `docs/modules/*.md` faylini o'qi — barchasini har safar majburan yuklama.
- Yakunda juda qisqa hisobot ber.

# Windows

- Windows / PowerShell / CMD = 0. Faqat remote Linux, GitHub Actions `ubuntu-latest`, Codespaces.
