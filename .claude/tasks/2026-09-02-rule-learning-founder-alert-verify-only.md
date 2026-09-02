# FOKUS AI — Part 3 Step 3/3: verify-only targeted test run

BASE: `95ea07c` (commit `feat: alert founder on learned-rule violations` is already
pushed to this branch and already implements the Founder alert in
`discipline_bot.py` (refactored `_rule_learning_status` returning
`(context, status_line)`, and the Founder alert sent once when
`status == "understood_before_penalty"` and the acting supervisor is not
Founder) plus the corresponding tests in `tests/test_discipline_bot_flows.py`.

Avval `git log --oneline -1` bilan HEAD `95ea07c` (yoki undan keyingi) ekanini tekshir.

## Maqsad

Faqat quyidagi targeted testni Linuxda ishga tushir va haqiqiy natijani qaytar:

```
python3 -m pytest -q tests/test_discipline_bot_flows.py tests/test_rule_compliance.py
```

## Agar barchasi PASS bo'lsa

Hech qanday kod o'zgartirma — `95ea07c` allaqachon to'g'ri commit. Faqat natijani
(masalan "X passed in Ys") report qil. Yangi commit/push SHART EMAS.

## Agar biror test FAIL bo'lsa

Faqat quyidagi fayllarga minimal tuzatish kirit:

- `discipline_bot.py`
- `tests/test_discipline_bot_flows.py`

Boshqa production fayl kerak bo'lsa STOP va aniq sababni yoz. Repo-wide audit yo'q,
full-suite yo'q, refactor yo'q, yangi jadval yo'q, penalty/points/AI/appeal/scheduler/
permissions mantig'iga tegma. Tuzatgach xuddi shu targeted testni qayta ishga tushir.
PASS bo'lsa: `fix: correct founder alert on learned-rule violations` nomi bilan
bitta commit va shu feature branchga push qil.

## Yakuniy javob

Faqat:
1. tests: X passed, Y failed (aniq son)
2. agar tuzatish kiritilgan bo'lsa: commit SHA, aks holda "no new commit"
3. `production untouched: yes`

STOP.
