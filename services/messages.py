"""Ruxsatsiz urinishlarda foydalanuvchiga ko'rsatiladigan qisqa, hazilkash
("Saturncha") xabarlar katalogi.

Ruxsatli tugmalar oddiy holatda umuman ko'rsatilmaydi (qarang ``main.py``
``build_menu``/``build_category_menu`` — markaziy permission-matrixdan
shakllanadi). Bu yerdagi matnlar FAQAT eski (endi ishlamaydigan) tugma,
callback, deep-link yoki qo'lda yozilgan buyruq orqali kirishga
urinishda ishlatiladi — shuning uchun rasmiy/sovuq emas, qisqa va
hazilkash, lekin haqoratsiz.

Matnlar shu yerda markazlashgan — handlerlarga tarqatilmaydi, faqat
``services/permissions.py`` (``ensure_permission``/``ensure_any_permission``)
orqali ishlatiladi.
"""

GENERIC_DENIAL = "🤨 Adashib qoldizmi? Yo'lingizni ko'rsatvoraymi…"
CASH_FINANCE_DENIAL = "🪄 Sim-sim, kassani och! Bo'lmasa qoch 😄"
MANAGEMENT_DENIAL = "🧐 Sizga nima? Siz uxlang…"
REPEAT_OFFENDER_DENIAL = "🤨 Sizni oldin ham ko'rganman… hamma joyga burningizni suqib yurasiz-a?"

# Har bir ACTION_* qaysi ohangdagi xabar olishini belgilaydi. Ro'yxatga
# kiritilmagan amal standart ravishda ``GENERIC_DENIAL`` oladi.
CASH_FINANCE_ACTIONS = frozenset(
    {
        "open_cash_shift",
        "close_cash_shift",
        "log_cash_expense",
        "review_cash_shift",
        "view_cash_summary",
        "set_salary",
        "lookup_any_salary",
    }
)

MANAGEMENT_ACTIONS = frozenset(
    {
        "manage_invites",
        "manage_roles",
        "remove_user",
        "list_users",
        "view_profile",
        "approve_applicant",
        "manage_discipline_rules",
        "decide_appeal",
        "set_rule",
        "list_rules",
        "process_month",
        "manage_vehicles",
        "saturn_test",
        "invite_supplier",
        "list_suppliers",
        "supplier_report",
        "compare_suppliers",
        "evaluate_employee",
        "close_day",
        "score_employee",
    }
)


def denial_text_for_action(action: str, *, repeat_offender: bool) -> str:
    if repeat_offender:
        return REPEAT_OFFENDER_DENIAL
    if action in CASH_FINANCE_ACTIONS:
        return CASH_FINANCE_DENIAL
    if action in MANAGEMENT_ACTIONS:
        return MANAGEMENT_DENIAL
    return GENERIC_DENIAL
