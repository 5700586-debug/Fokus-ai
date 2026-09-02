# FOKUS AI — replace placeholder recruiting branches: verify-only (retry)

BASE: `8dab58c` (commit `fix: replace placeholder recruiting branches` is already
pushed to this branch and already implements the new default
`RECRUITING_BRANCH_NAMES` = `SATURN Charhiy,SATURN Derizlik,SATURN Navoiy,SATURN Shafran`
in `config.py`, three new `RECRUITING_BRANCH_ADDRESSES` keys, and the corresponding
update to `tests/test_bot_flows.py::test_add_employee_role_and_branch_selection_produces_invite_link`).

A previous verify-only run for this same base (triggered by commit `c13c297`) appears
to have stalled/not completed -- this is a fresh retry, same instructions.

Avval `git log --oneline -1` bilan HEAD `8dab58c` (yoki undan keyingi) ekanini tekshir.

## Maqsad

Faqat quyidagi targeted testni Linuxda ishga tushir va haqiqiy natijani qaytar:

```
python3 -m pytest -q tests/test_bot_flows.py tests/test_recruiting_bot_flow.py
```

## Agar barchasi PASS bo'lsa

Hech qanday kod o'zgartirma — `8dab58c` allaqachon to'g'ri commit. Faqat natijani
(masalan "X passed in Ys") report qil. Yangi commit/push SHART EMAS.

## Agar biror test FAIL bo'lsa

Faqat quyidagi fayllarga minimal tuzatish kirit:

- `config.py`
- `tests/test_bot_flows.py`

Boshqa production fayl kerak bo'lsa (masalan ``main.py``ga tegish kerak bo'lib qolsa)
STOP va aniq sababni yoz -- ``main.py`` bu vazifada ATAYLAB o'zgartirilmaydi. Repo-wide
audit yo'q, full-suite yo'q, refactor yo'q, DB/migration/Render/production o'zgarishi
yo'q. Tuzatgach xuddi shu targeted testni qayta ishga tushir. PASS bo'lsa:
`fix: correct placeholder recruiting branches replacement` nomi bilan bitta commit va
shu feature branchga push qil.

## Yakuniy javob

Faqat:
1. tests: X passed, Y failed (aniq son)
2. agar tuzatish kiritilgan bo'lsa: commit SHA, aks holda "no new commit"
3. `production untouched: yes`

STOP.
