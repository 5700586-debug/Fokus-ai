# False-green CI tuzatishi

Bazaviy kod commit `390d7eb56f9707aec11d10fe9f7b4c06e0e14627`dan keyingi holatda ishlagin.

## O'zgartirish doirasi

Faqat quyidagi 3 faylni o'zgartir:

1. `.github/workflows/smoke-tests.yml`
2. `.github/workflows/e2e_real_telegram.yml`
3. `tests/test_bot_flows.py`

## 1. Pipeline exit kodini to'g'rila

`.github/workflows/smoke-tests.yml`dagi test `| tee` pipeline'i uchun, ayni `run: |` bash blokida pipeline'dan oldin `set -o pipefail` ishlasin.

Mavjud uzun pytest ro'yxati, `continue-on-error`, diagnostika commenti va yakuniy `exit 1` mantiqini o'zgartirma.

`.github/workflows/e2e_real_telegram.yml`dagi quyidagi 5 ta `| tee` pipeline'ining har biridan oldin, ayni bash blokida `set -o pipefail` ishlasin:

- `e2e.run_e2e`
- `e2e.run_recruiting_e2e`
- `e2e.run_nazoratchi_e2e`
- `e2e.run_cashshift_e2e`
- `e2e.run_supplier_e2e`

Maqsad: Python yoki pytest `exit 1` bersa, step `outcome=failure` bo'lsin; diagnostika ishlasin va final step jobni qizil qilsin.

## 2. Founder menyu testini yangila

`tests/test_bot_flows.py` ichida faqat
`test_founder_start_shows_new_greeting_and_five_menu_buttons`
testini yangila.

Nomini:
`test_founder_start_shows_new_greeting_and_seven_menu_buttons`
qil.

Kutilgan tugmalar tartibi aynan:

1. `👤 Xodim qo'shish`
2. `📢 Ishga e'lon berish`
3. `👥 Xodimlar`
4. `🏬 Do'konlar`
5. `💰 Smenalarni ko'rish`
6. `🚨 Bugungi muammolar`
7. `⚙️ Sozlamalar`

Boshqa 39 ta test xatosini tuzatma.

## Tekshiruv

Faqat:

- `tests/test_founder_today_problems.py`
- `tests/test_bot_flows.py::test_founder_start_shows_new_greeting_and_seven_menu_buttons`
- `tests/test_menu_and_fsm_escape.py::test_start_shows_founder_category_for_founder`
- ikki o'zgargan workflow faylining YAML sintaksisi

Full test, Smoke va E2E'ni qo'lda ishga tushirma. Targeted tekshiruv scope ichida xato chiqsa, faqat yuqoridagi 3 fayl doirasida tuzat.

PASS bo'lsa commit xabari:
`fix: stop CI from masking test failures`

Faqat `feature/hr-conversational-interview` branchiga push qil. Avtomatik workflow natijasini PASS deb taxmin qilma. Keyingi vazifaga o'tma.

Yakuniy javobda faqat commit, o'zgargan 3 fayl, targeted test natijasi va push holatini qisqa yoz.
