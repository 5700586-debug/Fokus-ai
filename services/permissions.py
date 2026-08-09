"""Markazlashtirilgan rol -> amal ruxsat tekshiruvi.

``roles.py`` allaqachon foydalanuvchi rolini boshqaradi (Founder,
allowed_users.json). Bu modul shu ustiga yangi funksionallik uchun
"kim nima qila oladi" jadvalini qo'shadi — mavjud ``main.py``/``approval.py``
dagi ``id == FOUNDER_ID`` tekshiruvlari o'zgartirilmaydi, ular allaqachon
ishlab turibdi. Yangi komandalar (masalan ``/score``) shu modul orqali
ruxsat tekshiradi.

Founder har doim barcha amallarga ruxsatli.
"""

from roles import get_role

ACTION_SCORE_EMPLOYEE = "score_employee"
ACTION_SET_RULE = "set_rule"
ACTION_PROCESS_MONTH = "process_month"
ACTION_LOG_MARKET_OBSERVATION = "log_market_observation"
ACTION_ENTER_MEAL_PLAN = "enter_meal_plan"
ACTION_DRIVER_DAILY_CHECK = "driver_daily_check"

# Founder-only amallar (masalan /setrule, /processmonth) shu ro'yxatga
# kiritilmaydi — ularga faqat Founder ruxsatli, boshqa hech qanday rol
# qo'shilmaydi.
ROLE_PERMISSIONS: dict[str, set[str]] = {
    "nazoratchi": {ACTION_SCORE_EMPLOYEE},
    "taminotchi": {ACTION_LOG_MARKET_OBSERVATION},
    "savdo_boshligi": {ACTION_ENTER_MEAL_PLAN},
    "haydovchi": {ACTION_DRIVER_DAILY_CHECK},
}


def has_permission(user_id: int, action: str) -> bool:
    role = get_role(user_id)
    if role is None:
        return False
    if role == "founder":
        return True

    return action in ROLE_PERMISSIONS.get(role, set())
