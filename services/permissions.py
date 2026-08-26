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

Noma'lum, bo'sh yoki ro'yxatdan o'chirilgan rol — ``has_permission()``da
DEFAULT-DENY (qarang funksiya docstringi).

Amal bajarish huquqi (``has_permission``) va filial ma'lumot chegarasi
(``can_access_branch``) ATAYLAB ikki mustaqil tekshiruv — birining
ruxsati ikkinchisini avtomatik bermaydi (masalan savdo bo'limi boshlig'i
``ACTION_SUBMIT_INVENTORY_SNAPSHOT``ga ruxsatli, lekin bu boshqa
filialning hisobotini ko'rish huquqini bermaydi).

Ruxsat berilmaganda ``deny()`` markaziy "Saturncha" xabar katalogidan
(``services/messages.py``) qisqa javob ko'rsatadi va (Founder-only
amalga ro'yxatdan o'tgan-lekin-Founder-bo'lmagan foydalanuvchi urinsa)
``services/audit.py`` orqali audit yozadi.

Founder har doim barcha amallarga ruxsatli.
"""

import time

from aiogram.types import CallbackQuery, Message

from employees import get_profile
from roles import get_role
from services import audit, messages

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
ACTION_DECIDE_ATTENDANCE_PERMISSION = "decide_attendance_permission"

# ADVANCED WORK SCHEDULE + MOBILITY V1 -- hozircha hech qanday
# Telegram handler bu ACTION_*larni chaqirmaydi (UI hali qurilmagan),
# lekin kelajakdagi boshqaruv shu chegaraga mos bo'lishi uchun oldindan
# tayyorlangan. Birortasi ham ROLE_PERMISSIONS'ga qo'shilmagan --
# hozircha faqat Founder bypass orqali ishlaydi; Nazoratchiga (yoki
# kelajakdagi boshqa vakolatli rolga) shu amalni berish alohida,
# ataylab qilinadigan qaror bo'lishi kerak, avtomatik emas.
ACTION_MANAGE_SCHEDULE_POLICY = "manage_schedule_policy"
ACTION_MANAGE_DAILY_SCHEDULE = "manage_daily_schedule"
ACTION_MANAGE_MOBILITY_POLICY = "manage_mobility_policy"
ACTION_MANAGE_BRANCH_VISIT_REQUIREMENTS = "manage_branch_visit_requirements"

# nazoratchi_bot.py — xodimga doimiy vazifa/hudud biriktirish (Founder-only;
# ko'rish — xodim kartasida — ACTION_EVALUATE_EMPLOYEE orqali, nazoratchi
# allaqachon shu amalga ega).
ACTION_MANAGE_TASK_ASSIGNMENTS = "manage_task_assignments"

# nazoratchi_bot.py — xodimni aktiv ro'yxatdan chiqarish (ishdan
# chiqarish). Tarix o'chirilmaydi, faqat ``employees.status`` o'zgaradi.
# Filial chegarasi ALOHIDA tekshiriladi (``can_access_branch``) —
# bu amalga ruxsat o'zi filial chegarasini bermaydi.
ACTION_OFFBOARD_EMPLOYEE = "offboard_employee"

# saturn_group_bot.py (Founder-only).
ACTION_SATURN_TEST = "saturn_test"

# supplier_chat_bot.py — ta'minotchi bilan ishlash (Founder-only).
ACTION_INVITE_SUPPLIER = "invite_supplier"
ACTION_LIST_SUPPLIERS = "list_suppliers"
ACTION_SUPPLIER_REPORT = "supplier_report"
ACTION_COMPARE_SUPPLIERS = "compare_suppliers"

# recruiting_bot.py — Fokus HR nomzod kartalarini ko'rish/qaror qilish
# va vakansiyalarni boshqarish (Founder-only). Nomzodning o'zi bu
# amallarga umuman kirmaydi — u alohida, RBAC'siz "tashqi" oqimda
# (qarang ``recruiting_bot.py`` docstringi, ``supplier_chat_bot.py``
# bilan bir xil naqsh).
ACTION_RECRUITING_REVIEW = "recruiting_review"
ACTION_MANAGE_VACANCIES = "manage_vacancies"

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
        ACTION_MANAGE_DAILY_SCHEDULE,
        ACTION_MANAGE_MOBILITY_POLICY,
        ACTION_MANAGE_BRANCH_VISIT_REQUIREMENTS,
        ACTION_OFFBOARD_EMPLOYEE,
    },
    "taminotchi": {ACTION_LOG_MARKET_OBSERVATION},
    "savdo_boshligi": {ACTION_ENTER_MEAL_PLAN, ACTION_SUBMIT_INVENTORY_SNAPSHOT},
    "haydovchi": {ACTION_DRIVER_DAILY_CHECK},
    "kassir": {ACTION_OPEN_CASH_SHIFT, ACTION_CLOSE_CASH_SHIFT, ACTION_LOG_CASH_EXPENSE},
    "moliyachi": {ACTION_VIEW_CASH_SUMMARY, ACTION_VIEW_INVENTORY_SUMMARY},
}


# Filiallararo (barcha filial) ko'rish huquqi tabiiy ravishda bor rollar
# — ``can_access_branch()`` uchun, ``ROLE_PERMISSIONS``dan ALOHIDA:
# amalni bajarish huquqi (has_permission) va filial ma'lumot chegarasi
# (can_access_branch) ataylab ikki mustaqil tekshiruv, biri ikkinchisini
# avtomatik bermaydi.
_CROSS_BRANCH_ROLES = frozenset({"moliyachi", "nazoratchi"})

# Foydalanuvchi bir necha daqiqa ichida qayta-qayta ruxsatsiz urinsa,
# "yana ko'rdim" ohangidagi xabar ko'rsatiladi — bu jarayon xotirasida
# (in-memory) saqlanadi, restart'da tozalanadi (ishonchli, lekin
# vaqtinchalik signal; token/parol kabi sir emas).
_RECENT_DENIALS: dict[int, float] = {}
_REPEAT_WINDOW_SECONDS = 300


def has_permission(user_id: int, action: str) -> bool:
    """Noma'lum, bo'sh yoki ro'yxatdan o'chirilgan foydalanuvchi (``None``
    rol) va ro'yxatdagi biror rolga biriktirilmagan amal — ikkalasi ham
    standart holatda RAD ETILADI (default-deny): ``.get(role, set())``
    bo'sh to'plam qaytaradi, ``in`` tekshiruvi ``False`` beradi.
    """
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


def can_access_branch(user_id: int, branch: str | None) -> bool:
    """Amal bajarish huquqi (``has_permission``) filial ma'lumot
    chegarasidan ATAYLAB alohida: Founder va filiallararo ko'rish huquqi
    bor rollar (moliyachi, nazoratchi) istalgan filialni ko'radi, qolgan
    HAR QANDAY rol faqat O'Z profilidagi filialga tegishli ma'lumotni
    so'rashi mumkin — hatto tegishli ``ACTION_*``ga ruxsati bo'lsa ham.
    Profili yo'q yoki filiali belgilanmagan foydalanuvchi uchun
    default-deny.
    """
    role = get_role(user_id)
    if role is None:
        return False
    if role == "founder" or role in _CROSS_BRANCH_ROLES:
        return True

    profile = get_profile(user_id)
    own_branch = profile.get("branch") if profile else None
    return own_branch is not None and own_branch == branch


def _is_founder_only_action(action: str) -> bool:
    return not any(action in actions for actions in ROLE_PERMISSIONS.values())


def _is_repeat_offender(user_id: int) -> bool:
    now = time.monotonic()
    last = _RECENT_DENIALS.get(user_id)
    _RECENT_DENIALS[user_id] = now
    return last is not None and (now - last) <= _REPEAT_WINDOW_SECONDS


def _event_chat_id(event: Message | CallbackQuery) -> int | None:
    if isinstance(event, CallbackQuery):
        return event.message.chat.id if event.message else None
    return event.chat.id


async def deny(event: Message | CallbackQuery, action: str) -> None:
    """Ruxsat yo'q bo'lganda ko'rsatiladigan qisqa "Saturncha" javob —
    xabar handlerlariga javob yuboradi, callback handlerlarida bo'sh
    ``answer()`` o'rniga qisqa toast ko'rsatadi (Telegram yuklanish
    indikatorini ham to'xtatadi). Bir xil foydalanuvchi Founder-only
    amalga qayta-qayta (rol egasi bo'lmasa-da) urinsa, bu markaziy
    audit jurnaliga ("muhim ruxsatsiz boshqaruv amali") yoziladi —
    oddiy operatsion amalning tasodifiy rad etilishi (masalan begona
    xato buyruq yozib qo'ysa) audit hajmini shishirmasin uchun faqat
    ro'yxatdan o'tgan (ammo Founder bo'lmagan) foydalanuvchi va
    Founder-only amal birikmasida yoziladi.
    """
    user = event.from_user
    user_id = user.id if user is not None else None
    role = get_role(user_id) if user_id is not None else None

    repeat = _is_repeat_offender(user_id) if user_id is not None else False
    text = messages.denial_text_for_action(action, repeat_offender=repeat)

    if isinstance(event, CallbackQuery):
        await event.answer(text, show_alert=False)
    else:
        await event.answer(text)

    if role is not None and role != "founder" and _is_founder_only_action(action):
        audit.log_event(
            audit.EVENT_UNAUTHORIZED_PRIVILEGED_ACTION,
            actor_id=user_id,
            actor_role=role,
            chat_id=_event_chat_id(event),
            reason=action,
        )


def log_cross_branch_attempt(event: Message | CallbackQuery, requested_branch: str | None) -> None:
    user = event.from_user
    user_id = user.id if user is not None else None
    role = get_role(user_id) if user_id is not None else None

    audit.log_event(
        audit.EVENT_CROSS_BRANCH_ATTEMPT,
        actor_id=user_id,
        actor_role=role,
        chat_id=_event_chat_id(event),
        new_value=requested_branch,
    )


async def ensure_permission(event: Message | CallbackQuery, action: str) -> bool:
    """Handlerlarda takrorlanadigan ruxsat tekshiruvini bitta joyga
    yig'adi: ruxsat bo'lsa ``True``, bo'lmasa ``deny()`` orqali qisqa
    "Saturncha" javob ko'rsatib ``False`` qaytaradi.
    """
    user = event.from_user
    if user is None:
        if isinstance(event, CallbackQuery):
            await event.answer()
        return False

    if has_permission(user.id, action):
        return True

    await deny(event, action)
    return False


async def ensure_any_permission(event: Message | CallbackQuery, *actions: str) -> bool:
    user = event.from_user
    if user is None:
        if isinstance(event, CallbackQuery):
            await event.answer()
        return False

    if has_any_permission(user.id, *actions):
        return True

    await deny(event, actions[0] if actions else "")
    return False
