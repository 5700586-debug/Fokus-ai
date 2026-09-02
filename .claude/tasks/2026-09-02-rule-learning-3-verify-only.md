# FOKUS AI — rule learning 3/3: verify-only targeted test run

BASE: `dee6e2e` (commit `feat: start rule learning after employee approval` is already
pushed to this branch and already implements the approval-gate + /setrole resume logic
in `approval.py`, `main.py`, and `tests/test_rule_learning_bot_flow.py`).

Avval `git log --oneline -1` bilan HEAD `dee6e2e` (yoki undan keyingi) ekanini tekshir.

## Maqsad

Faqat quyidagi targeted testni Linuxda ishga tushir va haqiqiy natijani qaytar:

```
python -m pytest -q tests/test_rule_learning.py tests/test_rule_learning_bot_flow.py tests/test_learning.py tests/test_schema.py tests/test_discipline_bot_flows.py
```

## Agar barchasi PASS bo'lsa

Hech qanday kod o'zgartirma — `dee6e2e` allaqachon to'g'ri commit. Faqat natijani
(masalan "X passed in Ys") report qil. Yangi commit/push SHART EMAS.

## Agar biror test FAIL bo'lsa

Faqat quyidagi fayllarga minimal tuzatish kirit:

- `approval.py`
- `main.py` (FAQAT `/setrole` success qismi)
- `tests/test_rule_learning_bot_flow.py`

Boshqa production fayl kerak bo'lsa STOP va aniq sababni yoz. Repo-wide audit yo'q,
full-suite yo'q, refactor yo'q. Tuzatgach xuddi shu targeted testni qayta ishga tushir.
PASS bo'lsa: `fix: correct rule learning approval gate` nomi bilan bitta commit va shu
feature branchga push qil.

## Yakuniy javob

Faqat:
1. tests: X passed, Y failed (aniq son)
2. agar tuzatish kiritilgan bo'lsa: commit SHA, aks holda "no new commit"
3. `production untouched: yes`

STOP.
