# Gemini konsultant (read-only)

Gemini FOKUS AI'da **faqat konsultant/reviewer**: repo kodini o'qiydi,
ChatGPT (bosh arxitektor) taklifini tahlil qiladi, risk va alternativani
aytadi. **Kod yozmaydi, commit/push qilmaydi, Claude'ga buyruq bermaydi.**

Workflow: `.github/workflows/gemini-consultant.yml`
(Google'ning rasmiy `google-github-actions/run-gemini-cli@v0` actioni).

## ⚠️ Aktivlashtirish (bir marta, Founder qiladi)

Workflow fayli hozircha `docs/gemini-consultant.workflow.yml` sifatida
turibdi. Sabab: `claude-task-runner.yml` bergan `GITHUB_TOKEN`da
`workflows` ruxsati yo'q, shuning uchun Claude `.github/workflows/` ichiga
fayl push qila olmaydi (GitHub push'ni rad etadi).

Founder lokalda (Windows'da ham mumkin — faqat git):

```
git checkout feature/hr-conversational-interview
git pull
git mv docs/gemini-consultant.workflow.yml .github/workflows/gemini-consultant.yml
git commit -m "Activate Gemini consultant workflow"
git push
```

Ixtiyoriy, kelajak uchun: `.github/workflows/claude-task-runner.yml`dagi
`permissions:` blokiga `workflows: write` qo'shilsa, keyingi safar Claude
workflow fayllarini o'zi push qila oladi.

## Ishga tushirish

1. **Qo'lda:** Actions -> "Gemini Consultant (read-only)" -> Run workflow ->
   `savol` maydoniga savol yoki arxitektura taklifini yozish.
2. **Fayl orqali:** `docs/consult/<nom>.md` faylini
   `feature/hr-conversational-interview` branchiga push qilish — o'sha
   faylning matni so'rov bo'ladi.

## Natijani qayerdan o'qish

Uchta joyda (bir xil matn):

- **Commit comment** — shu commit'ga avtomatik yoziladi. Autentifikatsiyasiz,
  oddiy public API orqali o'qiladi (ChatGPT uchun asosiy kanal):
  `GET https://api.github.com/repos/<owner>/<repo>/commits/<sha>/comments`
- **Job summary** — Actions run sahifasida.
- **Artifact** — `gemini-output` (xom stdout/stderr, debugging uchun).

## Read-only kafolati

`run-gemini-cli` gemini CLI'ni `--yolo` (avto-tasdiq) rejimida ishlatadi,
shuning uchun himoya aynan tool allowlist'da:

- `tools.core` — faqat `read_file`, `read_many_files`, `glob`, `grep_search`,
  `list_directory`.
- `tools.exclude` — `write_file`, `replace`, `run_shell_command`, `web_fetch`,
  `google_web_search`, `ask_user`.
- Gemini step'iga `GITHUB_TOKEN` **berilmaydi** — GitHub API'ga yeta olmaydi.

Yangi tool kerak bo'lsa, avval shu ro'yxatga ongli ravishda qo'shilishi
kerak; `run_shell_command` esa umuman qo'shilmasligi kerak.

## Kerakli secret

`GEMINI_API_KEY` (Settings -> Secrets and variables -> Actions).
