# Yangi kompyuterda FOKUS AI bilan davom etish

Kod GitHub'da — bu yerdagi tartib har qanday kompyuterda (uy, ofis,
boshqa Windows/Mac/Linux) bir xil ishlaydi. Test Windows'da EMAS,
GitHub Actions (Linux)da ishlaydi — shuning uchun Windows'ning
Smart App Control/xavfsizlik siyosati (psycopg2/Pillow blokini)
loyihaga umuman ta'sir qilmaydi.

## 1. Repo'ni klonlash

```
git clone https://github.com/5700586-debug/Fokus-ai.git
cd Fokus-ai
```

(Agar HTTPS ishlamasa — masalan Git'ning bog'langan `libcurl` DLL'i
xavfsizlik siyosati tomonidan bloklansa — SSH orqali kloning:
`git clone git@github.com:5700586-debug/Fokus-ai.git`, kerak bo'lsa
Windows'ning o'z SSH klientidan foydalaning:
`$env:GIT_SSH = "C:\Windows\System32\OpenSSH\ssh.exe"`.)

## 2. Joriy feature branchga o'tish

```
git checkout feature/hr-conversational-interview
git pull
```

Qaysi branch va commitda ekaningizni `FOKUS_AI_STATE.md`dan bilib
oling.

## 3. Lokal `.env`ni xavfsiz joydan qo'yish

`.env` hech qachon Git'ga kirmaydi (`.gitignore`da). Uni faqat
xavfsiz, shaxsiy joydan (parol menejeri, shifrlangan zaxira va h.k.)
qo'lda ko'chirib qo'ying — namuna uchun `.env.example`ga qarang.
Tokenlarni chatga yoki boshqa joyga yozmang.

## 4. VS Code / Claude bilan ishlash

Kodni oddiy tahrirlang. Katta/to'liq test to'plamini lokalda ishga
tushirishga URINMANG — bu endi GitHub Actions'ning ishi (qarang
4-band). Lokalda faqat: kod yozish, `git status`, commit, push, pull.

## 5. Ish tugagach — commit va push

```
git add <o'zgargan fayllar>
git commit -m "qisqa va aniq xabar"
git push
```

(Agar HTTPS push `libcurl` xatosi bilan yiqilsa, SSH orqali push
qiling: `$env:GIT_SSH = "C:\Windows\System32\OpenSSH\ssh.exe"; git
push git@github.com:5700586-debug/Fokus-ai.git feature/hr-conversational-interview`.)

## 6. Test natijasini GitHub Actions'dan ko'rish

Push qilingach GitHub avtomatik "Smoke tests" workflow'ini ishga
tushiradi (tez, kichik — psycopg2 haqiqiy import qilinadi, hech
qanday stub yo'q). Natijani shu yerdan ko'ring:

https://github.com/5700586-debug/Fokus-ai/actions

To'liq (900+) test to'plami ("Tests" workflow) endi HAR pushda emas —
faqat kerak bo'lganda qo'lda ishga tushiriladi: Actions -> Tests ->
"Run workflow".

## 7. `FOKUS_AI_STATE.md`dan davom etish

Bu fayl doim joriy holatni ko'rsatadi: qaysi branch/commit, GitHub
bilan sinxronmi, oxirgi tugallangan ish, hali tugallanmagan ish va
keyingi bitta qadam. Har safar shu fayldan boshlang.

## Muhim eslatmalar

- `main` va production'ga faqat Muhammadiy aniq ruxsat berganda
  tegiladi.
- Renderga hech qachon avtomatik deploy qilinmaydi — faqat aniq
  so'ralganda.
- Secret/token/parol hech qachon commitga yoki chatga yozilmaydi.
