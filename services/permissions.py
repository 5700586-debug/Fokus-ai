"""Markazlashtirilgan rol -> amal ruxsat tekshiruvi.

``roles.py`` foydalanuvchi rolini boshqaradi (Founder, allowed_users.json).
Bu modul BUTUN botdagi "kim nima qila oladi" qarorining YAGONA joyi —
har bir buyruq/callback handler ruxsatni to'g'ridan-to'g'ri
``id == FOUNDER_ID`` yoki ``is_authorized()`` bilan emas, shu yerdagi
``has_permission()``/``ensure_permission()`` orqali tekshiradi. Faqat
Founderga tegishli buyruqlar (masalan ``/setrule``, ``/invite``) ham
oddiy ``ACTION_*`` sifatida ro'yxatlangan — ular ``ROLE_PERMISSIONS``da
hech qanday rolga biriktirilmagani uchun pastdagi Founder bypass'idan
tashqari hech kim ularga ruxsat ololmaydi.

"Har qanday ro'yxatdan o'tgan foydalanuvchi" darajasidagi tekshiruvlar
(masalan asosiy menyu, /mystars, /apellyatsiya) bu modulga kirmaydi —
ular ``roles.is_authorized()`` orqali, alohida, allaqachon markazlashgan
tarzda tekshiriladi (rol farqi yo'q, shuning uchun amal-jadvali kerak emas).

Founder har doim barcha amallarga ruxsatli.
"""

from aiogram.types import CallbackQuery, Message

from roles import get_role

ACTION_SCORE_EMPLOYEE = "score_employee"
ACTION_SET_RULE = "set_rule"
ACTION_LIST_RULES = "list_rules"
ACTION_PROCESS_MONTH = "process_month"
ACTION_MANAGE_VEHICLES = "manage_vehicles"
ACTION_LOG_MARKET_OBSERVATION = "log_market_observation"
ACTION_ENTER_MEAL_PLAN = "enter_meal_plan"
ACTION_DRIVER_DAILY_CHECK = "driver_daily_check"

ACTION_OPEN_CASH_SHIFT = "open_cash_shift"
ACTION_CLOSE_CASH_SHIFT = "close_cash_shift"
ACTION_LOG_CASH_EXPENSE = "log_cash_expense"
ACTION_REVIEW_CASH_SHIFT = "review_cash_shift"
ACTION_SUBMIT_INVENTORY_SNAPSHOT = "submit_inventory_snapshot"
ACTION_REVIEW_INVENTORY_VARIANCE = "review_inventory_variance"
ACTION_VIEW_CASH_SUMMARY = "view_cash_summary"
ACTION_VIEW_INVENTORY_SUMMARY = "view_inventory_summary"

ACTION_EVALUATE_EMPLOYEE = "evaluate_employee"
ACTION_CLOSE_DAY = "close_day"

# main.py — foydalanuvchi/rol boshqaruvi (hammasi Founder-only).
ACTION_MANAGE_INVITES = "manage_invites"
ACTION_MANAGE_ROLES = "manage_roles"
ACTION_REMOVE_USER = "remove_user"
ACTION_LIST_USERS = "list_users"
ACTION_VIEW_PROFILE = "view_profile"

# approval.py — onboarding anketasini ko'rib chiqish (Founder-only).
ACTION_APPROVE_APPLICANT = "approve_applicant"

# discipline_bot.py — nizom/maosh/apellyatsiya qarori (Founder-only).
ACTION_MANAGE_DISCIPLINE_RULES = "manage_discipline_rules"
ACTION_SET_SALARY = "set_salary"
ACTION_LOOKUP_ANY_SALARY = "lookup_any_salary"
ACTION_DECIDE_APPEAL = "decide_appeal"

# saturn_group_bot.py (Founder-only).
ACTION_SATURN_TEST = "saturn_test"

# supplier_chat_bot.py — ta'minotchi bilan ishlash (Founder-only).
ACTION_INVITE_SUPPLIER = "invite_supplier"
ACTION_LIST_SUPPLIERS = "list_suppliers"
ACTION_SUPPLIER_REPORT = "supplier_report"
ACTION_COMPARE_SUPPLIERS = "compare_suppliers"

# Founder-only amallar (masalan /setrule, /processmonth, /invite) shu
# ro'yxatga kiritilmaydi — ularga faqat Founder ruxsatli (pastdagi
# ``has_permission()``dagi bypass orqali), boshqa hech qanday rol
# qo'shilmaydi.
ROLE_PERMISSIONS: dict[str, set[str]] = {
    "nazoratchi": {
        ACTION_SCORE_EMPLOYEE,
        ACTION_REVIEW_CASH_SHIFT,
        ACTION_REVIEW_INVENTORY_VARIANCE,
        ACTION_EVALUATE_EMPLOYEE,
        ACTION_CLOSE_DAY,
    },
    "taminotchi": {ACTION_LOG_MARKET_OBSERVATION},
    "savdo_boshligi": {ACTION_ENTER_MEAL_PLAN, ACTION_SUBMIT_INVENTORY_SNAPSHOT},
    "haydovchi": {ACTION_DRIVER_DAILY_CHECK},
    "kassir": {ACTION_OPEN_CASH_SHIFT, ACTION_CLOSE_CASH_SHIFT, ACTION_LOG_CASH_EXPENSE},
    "moliyachi": {ACTION_VIEW_CASH_SUMMARY, ACTION_VIEW_INVENTORY_SUMMARY},
}


def has_permission(user_id: int, action: str) -> bool:
    role = get_role(user_id)
    if role is None:
        return False
    if role == "founder":
        return True

    return action in ROLE_PERMISSIONS.get(role, set())


def has_any_permission(user_id: int, *actions: str) -> bool:
    """Bir nechta amaldan kamida bittasiga ruxsat bo'lsa ``True``
    (masalan ``/cashsummary``da boshqa xodimning smenasini moliyachi HAM,
    nazoratchi HAM ko'ra oladi — ikkalasi alohida amal, lekin bittasi
    yetarli).
    """
    return any(has_permission(user_id, action) for action in actions)


async def ensure_permission(event: Message | CallbackQuery, action: str) -> bool:
    """Handlerlarda takrorlanadigan "ruxsat yo'q bo'lsa jim rad et"
    naqshini bitta joyga yig'adi: xabar handlerlariga hech narsa
    yubormaydi (jim ``return``), callback handlerlarida esa bo'sh
    ``answer()`` bilan Telegramdagi yuklanish indikatorini to'xtatadi —
    bu ikkalasi ham mavjud, allaqachon test qilingan konvensiya, shu
    sababli o'zgartirilmaydi.
    """
    user = event.from_user
    if user is not None and has_permission(user.id, action):
        return True

    if isinstance(event, CallbackQuery):
        await event.answer()
    return False


async def ensure_any_permission(event: Message | CallbackQuery, *actions: str) -> bool:
    user = event.from_user
    if user is not None and has_any_permission(user.id, *actions):
        return True

    if isinstance(event, CallbackQuery):
        await event.answer()
    return False
