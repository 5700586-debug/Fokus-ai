# FOKUS AI — I/S: close 16 Smoke failures safely

VAZIFA:
Smoke run `33486952046`dagi aynan 16 ta FAIL'ni yop.

ASOSIY QOIDA:
Hozirgi ishlayotgan business logicni eski testga moslashtirib BUZMA.
Avval har bir FAIL testning eskirgan expectation/fixture muammosimi yoki real kod xatosimi aniqlagin.

Manba commit: `32d118bcb7c725ee624640ddffdbbdee4822c9d3`
Smoke natijasi: 452 PASS / 16 FAIL.

WINDOWS = 0. Faqat remote Linux/bash.

FAQAT SHU 6 TEST FAYLIGA O'ZGARTIRISH RUXSAT:
- tests/test_nazoratchi_supervision.py
- tests/test_nazoratchi_attendance_review.py
- tests/test_shift_deficiency_bot_flow.py
- tests/test_shift_daily_report_bot_flow.py
- tests/test_supplier_purchase_entry.py
- tests/test_supplier_purchase_allocation.py

Production/business kodga HOZIR TEGMA. `tests/bot_harness.py`ga ham tegma.

16 FAIL:
1. test_empty_branch_shows_no_data_placeholder
2. test_confirming_time_bonus_updates_card_and_hides_button
3. test_picking_a_grade_updates_the_card
4. test_grading_zero_is_allowed_and_shown_as_bajarilmagan
5. test_penalty_other_no_ai_match_falls_back_to_founder_directly
6. test_bootstrapped_founder_employee_shows_up_in_filiallar_flow
7. test_unjustified_reason_updates_card
8. test_founder_approving_manager_permission_updates_status
9. test_full_gate_with_no_prior_items_reaches_photo_prompt
10. test_yesterday_review_confirm_keeps_still_missing_open
11. test_full_closeshift_still_succeeds_after_clearing_deficiency_gate
12. test_staff_complaint_yes_employee_and_known_type_completes_gate
13. test_staff_complaint_other_type_requires_free_text_note
14. test_natijam_denied_for_unrelated_role
15. test_allocation_branch_can_receive_more_than_requested
16. test_allocation_total_cannot_exceed_purchased_quantity

REAL LOGDAN MA'LUM:
- Callback handler endi ba'zi oqimlarda avval `AnswerCallbackQuery` qaytaradi. Testlar `sent[0]` doim asosiy message deb taxmin qilmasin; kerakli message/reply_markupni returned actions ichidan topib tekshirsin.
- Yangi matnlar: `✅ Vaqt bonusi tasdiqlandi.`, `✅ Baho qayd etildi: ...`, `✅ Qayd etildi: sababsiz kechikish.`, `✅ Qabul qilindi.` Testlar eski matnni majburlamasin; real maqsad/state/resultni tekshirsin.
- Close-shift oqimiga Daily Report ataylab qo'shilgan. Deficiency'dan keyin darhol foto kutadigan eski testlarni yangi real ketma-ketlikka mosla. Daily Reportni olib tashlama.
- `test_natijam_denied_for_unrelated_role` ichidagi `combined is not defined` — testning o'z xatosi. Minimal tuzat.
- Supplier allocation yangi format: `Filial-1 — so'ralgan: ..., hozircha: ...`. Eski expectationni real yangi formatga mosla; allocation business logicni o'zgartirma.
- Staff complaint bo'yicha 2 FAIL uchun faqat tegishli `csdr_staff_*` handlerlarni READ-ONLY tekshir. Agar business qoida faqat active employee'larni ko'rsatsa, test fixture'ni real active employee bilan to'g'rila. Agar haqiqiy valid employee bilan ham oqim ishlamasa — production kodni o'zgartirma; STOP va real bugni aniq yoz.

TEST:
Full test yoki full Smoke'ni qo'lda ISHLATMA. Faqat yuqoridagi 16 failed testni targeted tarzda qayta ishlat.

NATIJA:
Agar 16/16 PASS bo'lsa:
- faqat shu test o'zgarishlarini commit qil;
- `feature/hr-conversational-interview`ga push qil;
- commit SHA va `16 passed` natijasini yoz.

Agar birortasi REAL business-code bug bo'lib chiqsa:
- production kodga tegma;
- qolganini kengaytirib audit qilma;
- aynan bitta real bugni, fayl/funksiya nomi bilan yoz;
- STOP.

QAT'IY:
- main'ga tegma
- production deploy qilma
- DBga tegma
- token/secretga tegma
- refactor qilma
- yangi feature qilma
- full audit qilma
- full test qilma
- muammoni kengaytirma
