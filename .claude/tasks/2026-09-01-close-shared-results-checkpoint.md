FOKUS AI — I/S REJIMI.

MAQSAD:
Faqat `⭐ Mening natijalarim` vazifasining qolgan yakuniy tekshiruvini yop.

QAT'IY:
- Windows = 0; faqat shu remote Linux/bash muhitidan foydalan.
- `main` va productionga tegma.
- Yangi feature boshlama.
- Full test, Smoke va E2E ishlatma.
- Keraksiz fayl o'qima.

Branch: `feature/hr-conversational-interview`
Funksional commit: `78a4fee`

1. Real branch, HEAD va working tree holatini tekshir.
2. `78a4fee` joriy branch tarixida borligini tekshir.
3. Faqat shu testni ishlat:

`python -m pytest -q tests/test_menu_and_fsm_escape.py tests/test_role_test_sandbox.py`

4. Test FAIL bo'lsa:
- kodni tuzatma;
- faqat birinchi haqiqiy xatoni yoz;
- STOP.

5. Test PASS bo'lsa:
- funksional kodga tegma;
- `docs/NEXT_STEP.md`da bu vazifani DONE deb belgilab, haqiqiy test natijasini yoz;
- faqat `docs/NEXT_STEP.md`ni commit qil: `docs: close shared results menu checkpoint`;
- shu feature branchga safe push qil;
- keyingi vazifaga o'tma.

Yakuniy javob faqat:
Branch:
HEAD:
Working tree:
78a4fee tarixda:
Targeted test:
Commit:
Push:
Vazifa yopildi: HA/YO'Q
Sabab:
