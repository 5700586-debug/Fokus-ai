# FOKUS AI — Part 3 Step 1: verify-only targeted test run

BASE: `6707551` (commit `feat: link penalties to learned rules` is already pushed to
this branch and already implements `get_progress_for_rule` in
`repositories/rule_learning.py`, `get_penalty_learning_context` in
`services/discipline.py`, and the new `tests/test_rule_compliance.py`).

Avval `git log --oneline -1` bilan HEAD `6707551` (yoki undan keyingi) ekanini tekshir.

## Maqsad

Faqat quyidagi targeted testni Linuxda ishga tushir va haqiqiy natijani qaytar:

```
python -m pytest -q tests/test_rule_compliance.py tests/test_rule_learning.py tests/test_discipline_service.py
```

## Agar barchasi PASS bo'lsa

Hech qanday kod o'zgartirma — `6707551` allaqachon to'g'ri commit. Faqat natijani
(masalan "X passed in Ys") report qil. Yangi commit/push SHART EMAS.

## Agar biror test FAIL bo'lsa

Faqat quyidagi fayllarga minimal tuzatish kirit:

- `repositories/rule_learning.py`
- `services/discipline.py`
- `tests/test_rule_compliance.py`

Boshqa production fayl kerak bo'lsa STOP va aniq sababni yoz. Repo-wide audit yo'q,
full-suite yo'q, refactor yo'q, yangi jadval yo'q. Tuzatgach xuddi shu targeted
testni qayta ishga tushir. PASS bo'lsa: `fix: correct penalty-to-rule-learning link`
nomi bilan bitta commit va shu feature branchga push qil.

## Yakuniy javob

Faqat:
1. tests: X passed, Y failed (aniq son)
2. agar tuzatish kiritilgan bo'lsa: commit SHA, aks holda "no new commit"
3. `production untouched: yes`

STOP.
