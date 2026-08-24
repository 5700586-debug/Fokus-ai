@.claude/rules.md
@docs/PROJECT_STATE.md

# Ish tartibi

- 1 prompt = 1 aniq maqsad.
- Avval mavjud holatni bil (git, Render, `docs/PROJECT_STATE.md`) — boshidan boshlama.
- Keraksiz repo audit qilma.
- Keraksiz refactor qilma.
- Full testni faqat Founder aniq so'rasa ishlat.
- Odatda faqat o'zgargan qismga minimal syntax/import tekshiruv yetarli.
- Bir buyruq uzoq cho'zilsa, maqsadni yo'qotib kutib turma.
- `main` va productionga Founder aniq ruxsat bermasa tegma.
- Secret, token, `.env`, API keyni commit/log/chatga chiqarma.
- Kodni imkon qadar minimal o'zgartir.
- Mavjud ishlaydigan arxitekturani sabab bo'lmasa qayta qurma.
- Har muhim commit/deploydan keyin `docs/PROJECT_STATE.md`ni yangila.
- Kerak bo'lsa faqat tegishli `docs/modules/*.md` faylini o'qi — barchasini har safar majburan yuklama.
- Yakunda juda qisqa hisobot ber.

# Native Windows

- Windows'da faqat: file read/search/edit, `git status`/`diff`/`commit`/`push`.
- Windows'da hech qachon: `python`, `pytest`, `pip`, build, local E2E, project runtime ishlatma.
- Barcha test/runtime: GitHub Actions `ubuntu-latest` yoki Render TEST'da.
