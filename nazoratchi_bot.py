"""Nazoratchi kunlik nazorat oqimi: filial -> aktiv xodimlar -> xodim
kartasi. Bosqichlab quriladi (qarang loyihaning "VAZIFA + NAZORATCHI +
BONUS" vazifasi) — bu fayl har bosqichda kengaytiriladi. Hozircha:
1-bosqich (filial/xodim ko'rish), 2-bosqich (kartada doimiy vazifalar,
``/vazifabiriktir``/``/vazifabekor`` orqali Founder boshqaradi, xodim
hech narsa bosmaydi), 3-bosqich (vaqt bonusi — qo'lda fallback
tasdiqlash, ``time_bonus_grants``dagi ``UNIQUE(employee_id,
grant_date)`` orqali duplicate/race-safe; avtomatik davomat manbai
ulanganda ``source=AUTO`` bilan xuddi shu jadvalga yozadi va bu
tugmani ko'rsatishni to'xtatadi — ikkalasi bir-birini bosib
o'tolmaydi) va 4-bosqich (ISH BAHOSI 0/1/2/3 — mavjud
``daily_evaluations``/``record_daily_grade`` qayta ishlatiladi,
faqat yangi "bajarilmagan"=0 daraja qo'shilgan; mavjud
``/baholash``dagi Chala/Norma/A'lo uchtaligi hardcoded bo'lgani
uchun o'zgarishsiz qoladi), 5-bosqich (BALL AYIRISH — faqat Founder
``/setnizombahosi`` bilan miqdor belgilagan nizom bandlari tugma
sifatida chiqadi, xodimga Tushundim/E'tirozim bor tugmali xabar
boradi, E'tiroz mavjud ``discipline_bot.AppealStates``ni qayta
ishlatadi) va 6-bosqich (📝 Boshqa holat — AI
(``services/discipline_ai.match_incident_to_rule``) erkin matnni
FAQAT mavjud, tasdiqlangan nizom bandlari bilan mazmunan
solishtiradi, hech qachon yangi band/miqdor o'ylab topmaydi;
mos topilsa Nazoratchiga albatta tasdiqlatiladi, topilmasa yoki AI
xato bersa 5-bosqichdagi "Founderga to'g'ridan-to'g'ri yuborish"
xatti-harakati o'zgarishsiz davom etadi).

Mavjud naqshlardan qayta foydalanadi: filial nomlari
``RECRUITING_BRANCH_NAMES``dan (config, hardcode emas), aktiv
xodimlar ``employees.list_approved_by_branch()``dan (Founder'ning
"🏬 Do'konlar" filial kartasida ham ishlatiladi). Ruxsat —
``permissions.ACTION_EVALUATE_EMPLOYEE`` (nazoratchi allaqachon shu
amalga ega, ``/baholash`` bilan bir xil ruxsat — yangi ACTION_*
qo'shilmadi).

Founder ham (barcha amallarga ruxsatli bo'lgani uchun) shu oqimni
ishlata oladi — filial-mustaqil ko'rish huquqi
``permissions._CROSS_BRANCH_ROLES``da nazoratchi allaqachon bor."""

from datetime import date, timedelta

from aiogram import Dispatcher, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import company_time
import discipline_bot
import employees
from config import ENVIRONMENT, FOUNDER_ID, RECRUITING_BRANCH_NAMES
from roles import get_role, role_name
from services import attendance as attendance_service
from services import audit
from services import discipline, discipline_ai, permissions, rules as rules_service, tasks as tasks_service, time_bonus as time_bonus_service


class PenaltyOtherStates(StatesGroup):
    waiting_reason = State()
    confirming_match = State()


class AttendanceStates(StatesGroup):
    waiting_arrival_time = State()
    waiting_force_majeure_reason = State()
    waiting_other_reason = State()


class ScheduleStates(StatesGroup):
    waiting_flexible_start = State()
    waiting_flexible_end = State()
    waiting_custom_date = State()


class MobilityStates(StatesGroup):
    waiting_custom_minutes = State()
    waiting_custom_date = State()


_CB_BRANCHES = "nzr_branches"
_CB_BRANCH_PREFIX = "nzr_branch:"
_CB_EMPLOYEE_PREFIX = "nzr_emp:"
_CB_TIME_BONUS_PREFIX = "nzr_timebonus:"
_CB_GRADE_PREFIX = "nzr_grade:"
_CB_PENALTY_PREFIX = "nzr_penalty:"
_CB_PENALTY_APPLY_PREFIX = "nzr_penalty_apply:"
_CB_PENALTY_OTHER_PREFIX = "nzr_penalty_other:"
_CB_ACK_PREFIX = "nzr_ack:"
_CB_APPEAL_PREFIX = "nzr_appeal:"
_CB_MATCH_CONFIRM_PREFIX = "nzr_match_yes:"
_CB_MATCH_REJECT_PREFIX = "nzr_match_no:"
_CB_ATTENDANCE_PREFIX = "nzr_att:"
_CB_ATT_REASON_PREFIX = "nzr_attreason:"
_CB_ATT_MGR_DECIDE_PREFIX = "nzr_attmgr:"
_CB_SCHEDULE_PREFIX = "nzr_sched:"
_CB_SCHEDULE_FIXED_PREFIX = "nzr_sched_fixed:"
_CB_SCHEDULE_FLEX_PREFIX = "nzr_sched_flex:"
_CB_SCHEDULE_OFF_PREFIX = "nzr_sched_off:"
_CB_SCHEDULE_DATE_PREFIX = "nzr_sched_date:"
_CB_SCHEDULE_CONFIRM_PREFIX = "nzr_sched_confirm:"
_CB_SCHEDULE_CANCEL_PREFIX = "nzr_sched_cancel:"

# Grafik o'zgartirish so'rovlari (xodimning `/grafik` oqimi yaratadi).
# Prefikslar ATAYLAB ":" bilan tugaydi -- shu sababli "nzr_schedreq:5"
# yuqoridagi "nzr_sched:" filtriga (startswith) tushmaydi.
_CB_SCHEDULE_REQUESTS = "nzr_schedreqs"
_CB_SCHEDULE_REQ_PREFIX = "nzr_schedreq:"
_CB_SCHEDULE_REQ_APPROVE_PREFIX = "nzr_schedreq_yes:"
_CB_SCHEDULE_REQ_REJECT_PREFIX = "nzr_schedreq_no:"

_SCHEDULE_SOURCE = "nazoratchi_ui"
_SCHEDULE_MODE_LABELS = {
    attendance_service.SCHEDULE_MODE_FIXED_1: "1-smena",
    attendance_service.SCHEDULE_MODE_FIXED_2: "2-smena",
    attendance_service.SCHEDULE_MODE_FLEXIBLE: "Erkin grafik",
}

_CB_MOBILITY_PREFIX = "nzr_mob:"
_CB_MOBILITY_REQS_PREFIX = "nzr_mob_reqs:"
_CB_MOBILITY_ADD_PREFIX = "nzr_mob_add:"
_CB_MOBILITY_BRANCH_PREFIX = "nzr_mob_branch:"
_CB_MOBILITY_MIN_PREFIX = "nzr_mob_min:"
_CB_MOBILITY_CUSTOM_PREFIX = "nzr_mob_custom:"
_CB_MOBILITY_CONFIRM_PREFIX = "nzr_mob_confirm:"
_CB_MOBILITY_CANCEL_PREFIX = "nzr_mob_cancel:"
_CB_MOBILITY_EDIT_PREFIX = "nzr_mob_edit:"
_CB_MOBILITY_REMOVE_PREFIX = "nzr_mob_remove:"
_CB_MOBILITY_REMOVE_YES_PREFIX = "nzr_mob_remove_yes:"
_CB_MOBILITY_REMOVE_NO_PREFIX = "nzr_mob_remove_no:"
_CB_MOBILITY_MODE_PREFIX = "nzr_mob_mode:"
_CB_MOBILITY_MODE_SET_PREFIX = "nzr_mob_mode_set:"
_CB_MOBILITY_DATE_PREFIX = "nzr_mob_date:"

_CB_OFFBOARD_PREFIX = "nzr_offb:"
_CB_OFFBOARD_YES_PREFIX = "nzr_offb_yes:"
_CB_OFFBOARD_NO_PREFIX = "nzr_offb_no:"

_MOBILITY_SOURCE = "nazoratchi_ui"
_MOBILITY_QUICK_MINUTES = (20, 30, 45, 60)
_MOBILITY_MODE_LABELS = {
    attendance_service.MOBILITY_BRANCH_VISIT_REQUIRED: "Ko'chma nazorat",
    attendance_service.MOBILITY_NONE: "Oddiy rejim",
}

# Callback_data ichida qisqa bo'lishi uchun sabab kalitlari — to'liq
# ``services/attendance`` doimiylariga shu yerda moslashtiriladi.
_ATT_REASON_KEYS = {
    "unjustified": attendance_service.REASON_UNJUSTIFIED,
    "manager": attendance_service.REASON_MANAGER_PERMISSION_PENDING,
    "force": attendance_service.REASON_FORCE_MAJEURE,
    "other": attendance_service.REASON_OTHER,
}

_SOURCE_LABELS = {
    time_bonus_service.SOURCE_AUTO: "AVTO",
    time_bonus_service.SOURCE_MANUAL: "QO'LDA",
}

# Ish bahosi: 0/1/2/3 tugmalari mavjud discipline.GRADE_* darajalarga
# mos keladi ("bajarilmagan" 4-daraja sifatida qo'shilgan — mavjud
# /baholash oqimidagi Chala/Norma/A'lo uchtaligiga TEGILMAGAN, u
# o'zgarishsiz qoladi, bu FAQAT yangi kartaning o'z tugma to'plami).
_GRADE_BUTTONS: tuple[tuple[str, str], ...] = (
    ("0", discipline.GRADE_BAJARILMAGAN),
    ("1", discipline.GRADE_CHALA),
    ("2", discipline.GRADE_NORMA),
    ("3", discipline.GRADE_ALO),
)


def _branches_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"📍 {name}", callback_data=f"{_CB_BRANCH_PREFIX}{i}")]
            for i, name in enumerate(RECRUITING_BRANCH_NAMES)
        ]
    )


def _branch_by_index(index: int) -> str | None:
    if 0 <= index < len(RECRUITING_BRANCH_NAMES):
        return RECRUITING_BRANCH_NAMES[index]
    return None


def _branch_index(branch: str) -> int | None:
    try:
        return RECRUITING_BRANCH_NAMES.index(branch)
    except ValueError:
        return None


def _employee_label(profile: dict) -> str:
    full_name = " ".join(part for part in (profile.get("familiya"), profile.get("ism")) if part) or "-"
    return f"👤 {full_name}"


def _employees_keyboard(branch: str) -> InlineKeyboardMarkup | None:
    """Filialdagi aktiv xodimlar — yonma-yon (2 tadan qatorda), o'qishga
    qulay tartibda (familiya/ism bo'yicha, ``list_approved_by_branch``
    allaqachon shunday saralaydi)."""
    active_employees = employees.list_approved_by_branch(branch)
    if not active_employees:
        return None

    buttons = [
        InlineKeyboardButton(text=_employee_label(profile), callback_data=f"{_CB_EMPLOYEE_PREFIX}{profile['user_id']}")
        for profile in active_employees
    ]
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    rows.append([InlineKeyboardButton(text="⬅️ Filiallar", callback_data=_CB_BRANCHES)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _simple_employee_card_text(profile: dict) -> str:
    full_name = " ".join(part for part in (profile.get("familiya"), profile.get("ism")) if part) or "-"
    lines = [
        f"👤 {full_name}",
        f"🏷 Lavozim: {role_name(profile.get('role_key'))}",
        f"🏬 Filial: {profile.get('branch') or '-'}",
    ]

    assigned_tasks = tasks_service.list_tasks_for_employee(profile["user_id"])
    lines.append("")
    if assigned_tasks:
        lines.append("📌 Doimiy vazifalar:")
        lines.extend(f"  • {title}" for title in assigned_tasks)
    else:
        lines.append("📌 Doimiy vazifalar: Ma'lumot yo'q")

    lines.append("")
    time_bonus = time_bonus_service.get_today_status(profile["user_id"])
    if time_bonus is None:
        lines.append("🕒 Bugungi vaqt bonusi: hali tasdiqlanmagan")
    else:
        source_label = _SOURCE_LABELS.get(time_bonus["source"], time_bonus["source"])
        lines.append(f"🕒 Bugungi vaqt bonusi: ✅ berildi ({source_label})")

    lines.append("")
    today = company_time.today().isoformat()
    grade = discipline.get_daily_grade(profile["user_id"], today)
    if grade is None:
        lines.append("⭐ Bugungi ish bahosi: hali qo'yilmagan")
    else:
        label = discipline.GRADE_LABELS.get(grade["grade_key"], grade["grade_key"])
        lines.append(f"⭐ Bugungi ish bahosi: {grade['grade_points']} ({label})")

    lines.append("")
    yesterday = attendance_service.get_yesterday_summary(profile["user_id"])
    if yesterday["arrival_time"]:
        lines.append(f"⏰ Kechagi davomat: {yesterday['arrival_time']} — {yesterday['label']}")
    else:
        lines.append("⏰ Kechagi davomat: Ma'lumot yo'q")

    return "\n".join(lines)


def _employee_card_keyboard(branch: str | None, user_id: int, *, show_time_bonus_button: bool) -> InlineKeyboardMarkup:
    back_data = _CB_BRANCHES
    if branch is not None:
        index = _branch_index(branch)
        if index is not None:
            back_data = f"{_CB_BRANCH_PREFIX}{index}"

    rows = []
    if show_time_bonus_button:
        rows.append(
            [InlineKeyboardButton(text="➕ Vaqt bonusini tasdiqlash", callback_data=f"{_CB_TIME_BONUS_PREFIX}{user_id}")]
        )
    rows.append(
        [
            InlineKeyboardButton(text=label, callback_data=f"{_CB_GRADE_PREFIX}{user_id}:{grade_key}")
            for label, grade_key in _GRADE_BUTTONS
        ]
    )
    rows.append([InlineKeyboardButton(text="➖ Ball ayirish", callback_data=f"{_CB_PENALTY_PREFIX}{user_id}")])
    rows.append([InlineKeyboardButton(text="⏰ Davomat", callback_data=f"{_CB_ATTENDANCE_PREFIX}{user_id}")])
    rows.append([InlineKeyboardButton(text="🗓 Ish grafigi", callback_data=f"{_CB_SCHEDULE_PREFIX}{user_id}")])
    rows.append([InlineKeyboardButton(text="📍 Filial nazorati", callback_data=f"{_CB_MOBILITY_PREFIX}{user_id}")])
    rows.append([InlineKeyboardButton(text="🚪 Ishdan chiqarish", callback_data=f"{_CB_OFFBOARD_PREFIX}{user_id}")])
    rows.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data=back_data)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _attendance_reason_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Sababsiz kech qoldi", callback_data=f"{_CB_ATT_REASON_PREFIX}{user_id}:unjustified")],
            [InlineKeyboardButton(text="✅ Rahbar ruxsat bergan", callback_data=f"{_CB_ATT_REASON_PREFIX}{user_id}:manager")],
            [InlineKeyboardButton(text="⚠️ Fors-major holat", callback_data=f"{_CB_ATT_REASON_PREFIX}{user_id}:force")],
            [InlineKeyboardButton(text="📝 Boshqa sabab", callback_data=f"{_CB_ATT_REASON_PREFIX}{user_id}:other")],
            [InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"{_CB_EMPLOYEE_PREFIX}{user_id}")],
        ]
    )


def _attendance_screen_text(profile: dict, summary: dict) -> str:
    full_name = " ".join(part for part in (profile.get("familiya"), profile.get("ism")) if part) or "-"
    lines = [f"👤 {full_name}", f"📅 Kecha ({summary['date']}):"]
    if summary["arrival_time"]:
        lines.append(f"⏰ Kelgan vaqti: {summary['arrival_time']}")
        lines.append(f"Holat: {summary['label']}")
        if summary.get("note"):
            lines.append(f"Izoh: {summary['note']}")
    else:
        lines.append("Ma'lumot yo'q.")
    return "\n".join(lines)


def _attendance_manual_entry_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"{_CB_EMPLOYEE_PREFIX}{user_id}")]]
    )


def _schedule_menu_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="1-smena", callback_data=f"{_CB_SCHEDULE_FIXED_PREFIX}{user_id}:fixed_1"),
                InlineKeyboardButton(text="2-smena", callback_data=f"{_CB_SCHEDULE_FIXED_PREFIX}{user_id}:fixed_2"),
            ],
            [InlineKeyboardButton(text="🕐 Erkin vaqt", callback_data=f"{_CB_SCHEDULE_FLEX_PREFIX}{user_id}")],
            [InlineKeyboardButton(text="🛌 Dam olish", callback_data=f"{_CB_SCHEDULE_OFF_PREFIX}{user_id}")],
            [InlineKeyboardButton(text="📅 Boshqa sana", callback_data=f"{_CB_SCHEDULE_DATE_PREFIX}{user_id}")],
            [InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"{_CB_EMPLOYEE_PREFIX}{user_id}")],
        ]
    )


def _schedule_screen_text(profile: dict, schedule_date: str) -> str:
    full_name = " ".join(part for part in (profile.get("familiya"), profile.get("ism")) if part) or "-"
    user_id = profile["user_id"]

    existing = attendance_service.get_shift_for_date(user_id, schedule_date)
    if existing is None:
        mode_label = _SCHEDULE_MODE_LABELS.get(attendance_service.resolve_schedule_mode(user_id), "Noma'lum")
        plan_line = "Ma'lumot yo'q"
    elif existing["status"] == attendance_service.SHIFT_STATUS_OFF:
        mode_label = "Dam olish"
        plan_line = "Dam olish kuni"
    else:
        mode_label = _SCHEDULE_MODE_LABELS.get(existing.get("schedule_mode"), "Noma'lum")
        plan_line = f"{existing['planned_start']}–{existing['planned_end']}"

    return (
        f"👤 {full_name}\n"
        f"📅 Sana: {schedule_date}\n"
        f"📌 Grafik turi: {mode_label}\n"
        f"🕒 Reja: {plan_line}"
    )


def _schedule_confirm_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"{_CB_SCHEDULE_CONFIRM_PREFIX}{user_id}"),
                InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"{_CB_SCHEDULE_CANCEL_PREFIX}{user_id}"),
            ]
        ]
    )


def _schedule_confirm_text(full_name: str, schedule_date: str, pending: dict) -> str:
    if pending["status"] == attendance_service.SHIFT_STATUS_OFF:
        plan_line = "Dam olish"
    else:
        plan_line = f"{pending['start']}–{pending['end']}"

    return (
        f"👤 Xodim: {full_name}\n"
        f"📅 Sana: {schedule_date}\n"
        f"🕒 Yangi grafik: {plan_line}"
    )


def _schedule_result_text(full_name: str, schedule_date: str, pending: dict) -> str:
    if pending["status"] == attendance_service.SHIFT_STATUS_OFF:
        plan_line = "Dam olish"
        mode_label = "Dam olish"
    else:
        plan_line = f"{pending['start']}–{pending['end']}"
        mode_label = _SCHEDULE_MODE_LABELS.get(pending.get("mode"), "Noma'lum")

    formatted_date = schedule_date
    try:
        parsed_date = date.fromisoformat(schedule_date)
        formatted_date = parsed_date.strftime("%d.%m.%Y")
    except ValueError:
        pass

    return (
        "✅ Grafik saqlandi\n\n"
        f"👤 {full_name}\n"
        f"📅 {formatted_date}\n"
        f"🕒 {plan_line}\n"
        f"📌 {mode_label}"
    )


def _format_date_display(iso_date: str) -> str:
    try:
        return date.fromisoformat(iso_date).strftime("%d.%m.%Y")
    except ValueError:
        return iso_date


def _schedule_request_plan(request: dict) -> str:
    if request["requested_status"] == attendance_service.SHIFT_STATUS_OFF:
        return "🛌 Dam olish"
    return f"🕒 Ish vaqti: {request['requested_start']}–{request['requested_end']}"


def _schedule_requests_text(requests: list[dict]) -> str:
    if not requests:
        return "📅 Grafik o'zgartirish so'rovlari\n\nKutilayotgan so'rov yo'q."
    return "📅 Grafik o'zgartirish so'rovlari\n\nKo'rib chiqish uchun so'rovni tanlang:"


def _schedule_requests_keyboard(requests: list[dict]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"{_employee_label(employees.get_profile(request['employee_id']) or {})} — "
                    f"{_format_date_display(request['shift_date'])}",
                    callback_data=f"{_CB_SCHEDULE_REQ_PREFIX}{request['id']}",
                )
            ]
            for request in requests
        ]
    )


def _schedule_request_text(request: dict, profile: dict) -> str:
    lines = [
        "📅 Grafik o'zgartirish so'rovi",
        "",
        f"👤 Xodim: {' '.join(part for part in (profile.get('familiya'), profile.get('ism')) if part) or '-'}",
        f"📅 Sana: {_format_date_display(request['shift_date'])}",
        f"🔄 So'ralgan: {_schedule_request_plan(request)}",
    ]
    if request.get("reason"):
        lines.append(f"✍️ Sabab: {request['reason']}")
    return "\n".join(lines)


def _schedule_request_decision_keyboard(request_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Tasdiqlash", callback_data=f"{_CB_SCHEDULE_REQ_APPROVE_PREFIX}{request_id}"
                ),
                InlineKeyboardButton(
                    text="❌ Rad etish", callback_data=f"{_CB_SCHEDULE_REQ_REJECT_PREFIX}{request_id}"
                ),
            ],
            [InlineKeyboardButton(text="⬅️ Orqaga", callback_data=_CB_SCHEDULE_REQUESTS)],
        ]
    )


def _mobility_screen_text(profile: dict, mobility_date: str) -> str:
    full_name = " ".join(part for part in (profile.get("familiya"), profile.get("ism")) if part) or "-"
    user_id = profile["user_id"]

    mode = attendance_service.resolve_mobility_policy(user_id)
    mode_label = _MOBILITY_MODE_LABELS.get(mode, "Noma'lum")

    lines = [
        f"👤 {full_name}",
        f"📅 Sana: {_format_date_display(mobility_date)}",
        f"🚶 Rejim: {mode_label}",
        "",
    ]

    requirements = attendance_service.get_branch_visit_requirements(user_id, mobility_date)
    if requirements:
        lines.append("📍 Bugungi talablar:")
        lines.extend(f"• {req['branch']} — {req['min_stay_minutes']} daqiqa" for req in requirements)
    else:
        lines.append("📍 Bu sana uchun filial talabi belgilanmagan")

    return "\n".join(lines)


def _mobility_menu_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📍 Talablar", callback_data=f"{_CB_MOBILITY_REQS_PREFIX}{user_id}"),
                InlineKeyboardButton(text="➕ Filial qo'shish", callback_data=f"{_CB_MOBILITY_ADD_PREFIX}{user_id}"),
            ],
            [InlineKeyboardButton(text="🚶 Rejim", callback_data=f"{_CB_MOBILITY_MODE_PREFIX}{user_id}")],
            [InlineKeyboardButton(text="📅 Boshqa sana", callback_data=f"{_CB_MOBILITY_DATE_PREFIX}{user_id}")],
            [InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"{_CB_EMPLOYEE_PREFIX}{user_id}")],
        ]
    )


def _mobility_compliance_text(profile: dict, mobility_date: str) -> str:
    full_name = " ".join(part for part in (profile.get("familiya"), profile.get("ism")) if part) or "-"
    user_id = profile["user_id"]
    compliance = attendance_service.get_daily_branch_compliance(user_id, mobility_date)

    lines = [f"👤 {full_name}", f"📅 {_format_date_display(mobility_date)}", ""]
    if not compliance:
        lines.append("📍 Bu sana uchun filial talabi belgilanmagan")
        return "\n".join(lines)

    for item in compliance:
        lines.append(f"🏬 {item['branch']}")
        lines.append(f"Talab: {item['required_minutes']} daqiqa")
        if item["status"] == "incomplete":
            lines.append("⏳ Ma'lumot to'liq emas")
        else:
            lines.append(f"Haqiqiy: {item['actual_minutes']:g} daqiqa")
            lines.append("✅ Bajarildi" if item["met"] else "⚠️ Yetarli emas")
        lines.append("")

    return "\n".join(lines).rstrip()


def _mobility_requirements_keyboard(user_id: int, requirements: list[dict]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{req['branch']} — {req['min_stay_minutes']} min",
                callback_data=f"{_CB_MOBILITY_EDIT_PREFIX}{user_id}:{req['branch']}",
            )
        ]
        for req in requirements
    ]
    rows.append([InlineKeyboardButton(text="➕ Filial qo'shish", callback_data=f"{_CB_MOBILITY_ADD_PREFIX}{user_id}")])
    rows.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"{_CB_MOBILITY_PREFIX}{user_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _mobility_branch_picker_keyboard(user_id: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"📍 {branch}", callback_data=f"{_CB_MOBILITY_BRANCH_PREFIX}{user_id}:{branch}")]
        for branch in RECRUITING_BRANCH_NAMES
    ]
    rows.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"{_CB_MOBILITY_PREFIX}{user_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _mobility_minutes_keyboard(user_id: int) -> InlineKeyboardMarkup:
    quick_buttons = [
        InlineKeyboardButton(text=f"{minutes} daqiqa", callback_data=f"{_CB_MOBILITY_MIN_PREFIX}{user_id}:{minutes}")
        for minutes in _MOBILITY_QUICK_MINUTES
    ]
    rows = [quick_buttons[:2], quick_buttons[2:]]
    rows.append([InlineKeyboardButton(text="✍️ Boshqa", callback_data=f"{_CB_MOBILITY_CUSTOM_PREFIX}{user_id}")])
    rows.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"{_CB_MOBILITY_PREFIX}{user_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _mobility_requirement_confirm_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"{_CB_MOBILITY_CONFIRM_PREFIX}{user_id}"),
                InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"{_CB_MOBILITY_CANCEL_PREFIX}{user_id}"),
            ]
        ]
    )


def _mobility_requirement_confirm_text(full_name: str, mobility_date: str, branch: str, minutes: int) -> str:
    return (
        f"👤 Xodim: {full_name}\n"
        f"📅 Sana: {_format_date_display(mobility_date)}\n"
        f"🏬 Filial: {branch}\n"
        f"⏱ Minimal vaqt: {minutes} daqiqa"
    )


def _mobility_branch_detail_text(branch: str, minutes: int) -> str:
    return f"🏬 {branch}\n⏱ {minutes} daqiqa"


def _mobility_branch_detail_keyboard(user_id: int, branch: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Vaqtni o'zgartirish", callback_data=f"{_CB_MOBILITY_BRANCH_PREFIX}{user_id}:{branch}")],
            [InlineKeyboardButton(text="🗑 Talabni olib tashlash", callback_data=f"{_CB_MOBILITY_REMOVE_PREFIX}{user_id}:{branch}")],
            [InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"{_CB_MOBILITY_REQS_PREFIX}{user_id}")],
        ]
    )


def _mobility_remove_confirm_keyboard(user_id: int, branch: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Ha", callback_data=f"{_CB_MOBILITY_REMOVE_YES_PREFIX}{user_id}:{branch}"),
                InlineKeyboardButton(text="❌ Yo'q", callback_data=f"{_CB_MOBILITY_REMOVE_NO_PREFIX}{user_id}:{branch}"),
            ]
        ]
    )


def _mobility_mode_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Ko'chma nazorat",
                    callback_data=f"{_CB_MOBILITY_MODE_SET_PREFIX}{user_id}:{attendance_service.MOBILITY_BRANCH_VISIT_REQUIRED}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⛔ Oddiy rejim",
                    callback_data=f"{_CB_MOBILITY_MODE_SET_PREFIX}{user_id}:{attendance_service.MOBILITY_NONE}",
                )
            ],
            [InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"{_CB_MOBILITY_PREFIX}{user_id}")],
        ]
    )


def _offboard_confirm_text(profile: dict) -> str:
    full_name = " ".join(part for part in (profile.get("familiya"), profile.get("ism")) if part) or "-"
    return "\n".join(
        [
            "🚪 Ishdan chiqarish",
            "",
            f"👤 {full_name}",
            f"🏬 Filial: {profile.get('branch') or '-'}",
            f"🏷 Lavozim: {role_name(profile.get('role_key'))}",
            "",
            "ℹ️ Tarix o'chmaydi: baholar, ballar, davomat, vazifalar va ish "
            "grafigi yozuvlari saqlanib qoladi. Xodim faqat aktiv xodimlar "
            "ro'yxatidan chiqariladi.",
            "",
            "Tasdiqlaysizmi?",
        ]
    )


def _offboard_confirm_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Ha, ishdan chiqarish", callback_data=f"{_CB_OFFBOARD_YES_PREFIX}{user_id}"),
                InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"{_CB_OFFBOARD_NO_PREFIX}{user_id}"),
            ]
        ]
    )


def _offboard_result_text(profile: dict) -> str:
    full_name = " ".join(part for part in (profile.get("familiya"), profile.get("ism")) if part) or "-"
    return (
        f"🚪 {full_name} aktiv xodimlar ro'yxatidan chiqarildi.\n\n"
        "📚 Barcha tarixiy ma'lumotlari saqlanib qoldi."
    )


def _penalty_rule_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Faqat Founder tomonidan ball miqdori belgilangan ("tasdiqlangan")
    nizom bandlari — AI ham, Nazoratchi ham yangi miqdorni o'zi
    o'ylab topmaydi (qarang ``discipline.list_rules_with_penalty_amount``)."""
    rules = discipline.list_rules_with_penalty_amount()
    rows = [
        [
            InlineKeyboardButton(
                text=f"{rule['title']} — -{rule['default_penalty_amount']} ball",
                callback_data=f"{_CB_PENALTY_APPLY_PREFIX}{user_id}:{rule['rule_number']}",
            )
        ]
        for rule in rules
    ]
    rows.append([InlineKeyboardButton(text="📝 Boshqa holat", callback_data=f"{_CB_PENALTY_OTHER_PREFIX}{user_id}")])
    rows.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"{_CB_EMPLOYEE_PREFIX}{user_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _employee_notice_keyboard(penalty_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Tushundim", callback_data=f"{_CB_ACK_PREFIX}{penalty_id}"),
                InlineKeyboardButton(text="✋ E'tirozim bor", callback_data=f"{_CB_APPEAL_PREFIX}{penalty_id}"),
            ]
        ]
    )


def _match_confirm_keyboard(user_id: int, rule_number: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Ha, qo'llash", callback_data=f"{_CB_MATCH_CONFIRM_PREFIX}{user_id}:{rule_number}"
                ),
                InlineKeyboardButton(text="❌ Yo'q, Founderga yubor", callback_data=f"{_CB_MATCH_REJECT_PREFIX}{user_id}"),
            ]
        ]
    )


def register(dp: Dispatcher, openai_client) -> None:
    async def _notify_founder_unmatched(bot, employee_id: int, reported_by: int, text: str) -> None:
        discipline.report_unmatched_incident(employee_id, reported_by, text)
        profile = employees.get_profile(employee_id)
        full_name = (
            " ".join(part for part in (profile.get("familiya"), profile.get("ism")) if part) if profile else None
        ) or f"user_id {employee_id}"
        try:
            await bot.send_message(
                FOUNDER_ID,
                f"📝 Nazoratchi tomonidan yozilgan, tasdiqlangan nizomga mos kelmagan holat:\n\n"
                f"👤 Xodim: {full_name}\n"
                f"✍️ Nazoratchi yozuvi: {text}",
            )
        except Exception as error:  # noqa: BLE001
            print(f"Founderga 'boshqa holat' xabarini yuborib bo'lmadi: {error!r}")

    @dp.message(Command("e2exodim"))
    async def e2e_bootstrap_employee_handler(message: Message) -> None:
        """FAQAT test muhitida (``ENVIRONMENT == "test"``) va FAQAT
        Founder uchun — real Telegram E2E skriptlari shu buyruq bilan
        chaqiruvchi akkauntning O'ZINI (odatda shu test akkaunt,
        ``fokus-ai-test``da ``FOUNDER_ID`` sifatida tanilgan) filialga
        biriktirilgan, tasdiqlangan "xodim" sifatida ro'yxatga qo'shadi
        — FAQAT ``employees`` jadvaliga, ``roles``/``allowed_users``ga
        UMUMAN tegilmaydi (``roles.get_role()`` FOUNDER_ID uchun har
        doim "founder" qaytaradi, bu buyruq bilan o'zgarmaydi; "kassir"
        ham single-slot rol emas — qarang ``roles.SINGLE_SLOT_ROLES``).
        Shu orqali Nazoratchi xodim-karta oqimini (filial->xodim->
        karta->baho->ball->xodimga xabar->e'tiroz) ikkinchi Telegram
        akkauntsiz, ANIQ shu test akkaunt ustida real E2E orqali TO'LIQ
        sinash mumkin bo'ladi. Idempotent — necha marta chaqirilsa ham
        xavfsiz."""
        if message.from_user is None or message.from_user.id != FOUNDER_ID or ENVIRONMENT != "test":
            return

        branch = RECRUITING_BRANCH_NAMES[0] if RECRUITING_BRANCH_NAMES else "Filial-1"
        employees.submit_profile(
            message.from_user.id,
            {"familiya": "E2E", "ism": "Sinov", "branch": branch, "role_key": "kassir", "contacts": []},
        )
        employees.approve_profile(message.from_user.id, approved_by=FOUNDER_ID)
        await message.answer(f"✅ E2E sinov xodimi tayyorlandi ({branch}).")

    @dp.message(Command("filiallar"))
    async def filiallar_start(message: Message) -> None:
        if not await permissions.ensure_permission(message, permissions.ACTION_EVALUATE_EMPLOYEE):
            return

        await message.answer("🏬 Filiallar:", reply_markup=_branches_keyboard())

    @dp.callback_query(F.data == _CB_BRANCHES)
    async def branches_back(callback: CallbackQuery) -> None:
        if not await permissions.ensure_permission(callback, permissions.ACTION_EVALUATE_EMPLOYEE):
            return

        if callback.message:
            await callback.message.edit_text("🏬 Filiallar:", reply_markup=_branches_keyboard())
        await callback.answer()

    @dp.callback_query(F.data.startswith(_CB_BRANCH_PREFIX))
    async def branch_pick(callback: CallbackQuery) -> None:
        if not await permissions.ensure_permission(callback, permissions.ACTION_EVALUATE_EMPLOYEE):
            return

        index = int(callback.data.split(":", 1)[1])
        branch = _branch_by_index(index)
        if branch is None:
            await callback.answer("Filial topilmadi.", show_alert=True)
            return

        keyboard = _employees_keyboard(branch)
        if keyboard is None:
            await callback.answer()
            if callback.message:
                await callback.message.edit_text(
                    f"🏬 {branch}\n\n👥 Aktiv xodimlar: Ma'lumot yo'q",
                    reply_markup=InlineKeyboardMarkup(
                        inline_keyboard=[[InlineKeyboardButton(text="⬅️ Filiallar", callback_data=_CB_BRANCHES)]]
                    ),
                )
            return

        if callback.message:
            await callback.message.edit_text(f"🏬 {branch}\n\n👥 Xodimni tanlang:", reply_markup=keyboard)
        await callback.answer()

    async def _render_employee_card(callback: CallbackQuery, profile: dict) -> None:
        user_id = profile["user_id"]
        if callback.message:
            await callback.message.edit_text(
                _simple_employee_card_text(profile),
                reply_markup=_employee_card_keyboard(
                    profile.get("branch"), user_id, show_time_bonus_button=time_bonus_service.get_today_status(user_id) is None
                ),
            )

    @dp.callback_query(F.data.startswith(_CB_EMPLOYEE_PREFIX))
    async def employee_pick(callback: CallbackQuery) -> None:
        if not await permissions.ensure_permission(callback, permissions.ACTION_EVALUATE_EMPLOYEE):
            return

        user_id = int(callback.data.split(":", 1)[1])
        profile = employees.get_profile(user_id)
        if profile is None:
            await callback.answer("Xodim topilmadi.", show_alert=True)
            return

        await _render_employee_card(callback, profile)
        await callback.answer()

    @dp.callback_query(F.data.startswith(_CB_TIME_BONUS_PREFIX))
    async def time_bonus_confirm(callback: CallbackQuery) -> None:
        if not await permissions.ensure_permission(callback, permissions.ACTION_EVALUATE_EMPLOYEE):
            return

        user_id = int(callback.data.split(":", 1)[1])
        profile = employees.get_profile(user_id)
        if profile is None:
            await callback.answer("Xodim topilmadi.", show_alert=True)
            return

        granted = time_bonus_service.confirm_manual(user_id, callback.from_user.id)
        await callback.answer("✅ Vaqt bonusi tasdiqlandi." if granted else "ℹ️ Bugun uchun allaqachon tasdiqlangan.")

        if callback.message:
            await callback.message.edit_text(
                _simple_employee_card_text(profile),
                reply_markup=_employee_card_keyboard(profile.get("branch"), user_id, show_time_bonus_button=False),
            )

    @dp.callback_query(F.data.startswith(_CB_GRADE_PREFIX))
    async def grade_pick(callback: CallbackQuery) -> None:
        if not await permissions.ensure_permission(callback, permissions.ACTION_EVALUATE_EMPLOYEE):
            return

        parts = callback.data.split(":", 2)
        if len(parts) != 3:
            await callback.answer()
            return

        user_id = int(parts[1])
        grade_key = parts[2]
        profile = employees.get_profile(user_id)
        if profile is None:
            await callback.answer("Xodim topilmadi.", show_alert=True)
            return

        today = company_time.today().isoformat()
        discipline.record_daily_grade(user_id, callback.from_user.id, today, grade_key)
        await callback.answer(f"✅ Baho qayd etildi: {discipline.GRADE_LABELS[grade_key]}")

        if callback.message:
            await callback.message.edit_text(
                _simple_employee_card_text(profile),
                reply_markup=_employee_card_keyboard(
                    profile.get("branch"), user_id, show_time_bonus_button=time_bonus_service.get_today_status(user_id) is None
                ),
            )

    # --------------------------------------------------------- ball ayirish --

    @dp.callback_query(F.data.startswith(_CB_PENALTY_PREFIX))
    async def penalty_menu(callback: CallbackQuery) -> None:
        if not await permissions.ensure_permission(callback, permissions.ACTION_EVALUATE_EMPLOYEE):
            return

        user_id = int(callback.data.split(":", 1)[1])
        profile = employees.get_profile(user_id)
        if profile is None:
            await callback.answer("Xodim topilmadi.", show_alert=True)
            return

        full_name = " ".join(part for part in (profile.get("familiya"), profile.get("ism")) if part) or "-"
        keyboard = _penalty_rule_keyboard(user_id)
        text = f"👤 {full_name}\n\n➖ Qaysi nizom bandi bo'yicha ball ayiriladi?"
        if len(keyboard.inline_keyboard) <= 2:
            text += "\n\nℹ️ Hozircha tasdiqlangan ball miqdori bilan nizom bandi yo'q — Founder /setnizombahosi orqali belgilashi kerak."

        if callback.message:
            await callback.message.edit_text(text, reply_markup=keyboard)
        await callback.answer()

    @dp.callback_query(F.data.startswith(_CB_PENALTY_APPLY_PREFIX))
    async def penalty_apply(callback: CallbackQuery) -> None:
        if not await permissions.ensure_permission(callback, permissions.ACTION_EVALUATE_EMPLOYEE):
            return

        nazoratchi_id = callback.from_user.id
        # Bir tugmani ikki marta bosish/parallel callback ikki marta ball
        # ayirmasin — mavjud discipline_bot.py naqshi bilan bir xil
        # jarayon-ichi guard (qarang o'sha faylning
        # ``_PENDING_PENALTY_APPLICATIONS`` izohi), ikkala modul BITTA
        # to'plamni ulashadi (bitta nazoratchi bir vaqtda faqat bitta
        # ball-ayirish yozuvini qayta ishlaydi, qaysi oqim orqali
        # boshlangani muhim emas).
        if nazoratchi_id in discipline_bot._PENDING_PENALTY_APPLICATIONS:
            await callback.answer()
            return
        discipline_bot._PENDING_PENALTY_APPLICATIONS.add(nazoratchi_id)

        try:
            parts = callback.data.split(":", 2)
            if len(parts) != 3:
                await callback.answer()
                return

            user_id = int(parts[1])
            rule_number = int(parts[2])
            profile = employees.get_profile(user_id)
            rule = discipline.get_rule(rule_number)
            if profile is None or rule is None or rule.get("default_penalty_amount") is None:
                await callback.answer("Xodim yoki nizom bandi topilmadi.", show_alert=True)
                return

            amount = rule["default_penalty_amount"]
            today = company_time.today().isoformat()
            result = discipline.apply_penalty(
                user_id, nazoratchi_id, today, amount, rule_number, comment=None, ai_note=None
            )
            await callback.answer(f"✅ -{amount} ball qayd etildi ({rule['title']}).")

            full_name = " ".join(part for part in (profile.get("familiya"), profile.get("ism")) if part) or "-"
            if callback.message:
                await callback.message.edit_text(
                    f"👤 {full_name}\n\n🚫 -{amount} ball ayirildi ({rule['title']}).\n"
                    f"💰 Bonus banki: {result['bonus_bank_balance']} ball\n"
                    "ℹ️ Fiks oylikka ta'sir qilmaydi.",
                    reply_markup=_employee_card_keyboard(
                        profile.get("branch"), user_id, show_time_bonus_button=time_bonus_service.get_today_status(user_id) is None
                    ),
                )

            try:
                await callback.bot.send_message(
                    user_id,
                    f"⚠️ Sizga -{amount} ball ayirildi.\nQoida: {rule['title']}\nSabab: {rule['content']}",
                    reply_markup=_employee_notice_keyboard(result["penalty_id"]),
                )
            except Exception as error:  # noqa: BLE001
                print(f"Xodimga ball ayirish xabarini yuborib bo'lmadi ({user_id}): {error!r}")
        finally:
            discipline_bot._PENDING_PENALTY_APPLICATIONS.discard(nazoratchi_id)

    @dp.callback_query(F.data.startswith(_CB_PENALTY_OTHER_PREFIX))
    async def penalty_other_start(callback: CallbackQuery, state: FSMContext) -> None:
        if not await permissions.ensure_permission(callback, permissions.ACTION_EVALUATE_EMPLOYEE):
            return

        user_id = int(callback.data.split(":", 1)[1])
        if employees.get_profile(user_id) is None:
            await callback.answer("Xodim topilmadi.", show_alert=True)
            return

        await state.update_data(penalty_other_employee_id=user_id)
        await state.set_state(PenaltyOtherStates.waiting_reason)
        await callback.answer()
        if callback.message:
            await callback.message.answer("✍️ Holatni qisqacha yozing (masalan: \"Nazoratchini haqorat qildi\"):")

    @dp.message(StateFilter(PenaltyOtherStates.waiting_reason))
    async def penalty_other_reason(message: Message, state: FSMContext) -> None:
        data = await state.get_data()
        user_id = data.get("penalty_other_employee_id")

        text = (message.text or "").strip()
        if not text or user_id is None:
            await state.clear()
            await message.answer("❌ Bekor qilindi.")
            return

        # AI faqat MAVJUD, ball miqdori belgilangan ("tasdiqlangan")
        # nizom bandlaridan birini taklif qiladi (yoki hech birini) —
        # yakuniy qo'llashdan oldin Nazoratchiga ALBATTA tasdiqlatiladi
        # (qarang services/discipline_ai.match_incident_to_rule).
        eligible_rules = discipline.list_rules_with_penalty_amount()
        matched_rule_number = await discipline_ai.match_incident_to_rule(openai_client, text, eligible_rules)

        if matched_rule_number is not None:
            rule = discipline.get_rule(matched_rule_number)
            await state.update_data(penalty_other_text=text)
            await state.set_state(PenaltyOtherStates.confirming_match)
            await message.answer(
                f"🤖 Bu holat quyidagi nizom bandiga mos kelishi mumkin:\n"
                f"{matched_rule_number}-nizom: {rule['title']} — -{rule['default_penalty_amount']} ball\n\n"
                "Tasdiqlaysizmi?",
                reply_markup=_match_confirm_keyboard(user_id, matched_rule_number),
            )
            return

        await state.clear()
        await _notify_founder_unmatched(message.bot, user_id, message.from_user.id, text)
        await message.answer(
            "✅ Qabul qilindi — bu holat tasdiqlangan nizom bandiga mos kelmagani uchun "
            "ball ayirilmadi, Founder ko'rib chiqishi uchun yuborildi."
        )

    @dp.callback_query(F.data.startswith(_CB_MATCH_CONFIRM_PREFIX))
    async def match_confirm(callback: CallbackQuery, state: FSMContext) -> None:
        if not await permissions.ensure_permission(callback, permissions.ACTION_EVALUATE_EMPLOYEE):
            return

        nazoratchi_id = callback.from_user.id
        if nazoratchi_id in discipline_bot._PENDING_PENALTY_APPLICATIONS:
            await callback.answer()
            return
        discipline_bot._PENDING_PENALTY_APPLICATIONS.add(nazoratchi_id)

        try:
            parts = callback.data.split(":", 2)
            if len(parts) != 3:
                await callback.answer()
                return

            user_id = int(parts[1])
            rule_number = int(parts[2])
            # Asl erkin matn ("sabab") audit trail'da saqlanib qolishi
            # uchun state tozalanishidan OLDIN o'qiladi.
            original_text = (await state.get_data()).get("penalty_other_text")
            await state.clear()

            profile = employees.get_profile(user_id)
            rule = discipline.get_rule(rule_number)
            if profile is None or rule is None or rule.get("default_penalty_amount") is None:
                await callback.answer("Xodim yoki nizom bandi topilmadi.", show_alert=True)
                return

            amount = rule["default_penalty_amount"]
            today = company_time.today().isoformat()
            result = discipline.apply_penalty(
                user_id, nazoratchi_id, today, amount, rule_number,
                comment=original_text, ai_note="AI 'Boshqa holat' matnini shu nizom bandiga mos topdi.",
            )
            await callback.answer(f"✅ -{amount} ball qayd etildi ({rule['title']}).")

            if callback.message:
                await callback.message.edit_text(
                    f"✅ {rule['title']} bo'yicha -{amount} ball qayd etildi.\n"
                    f"💰 Bonus banki: {result['bonus_bank_balance']} ball",
                    reply_markup=None,
                )

            try:
                await callback.bot.send_message(
                    user_id,
                    f"⚠️ Sizga -{amount} ball ayirildi.\nQoida: {rule['title']}\nSabab: {rule['content']}",
                    reply_markup=_employee_notice_keyboard(result["penalty_id"]),
                )
            except Exception as error:  # noqa: BLE001
                print(f"Xodimga ball ayirish xabarini yuborib bo'lmadi ({user_id}): {error!r}")
        finally:
            discipline_bot._PENDING_PENALTY_APPLICATIONS.discard(nazoratchi_id)

    @dp.callback_query(F.data.startswith(_CB_MATCH_REJECT_PREFIX))
    async def match_reject(callback: CallbackQuery, state: FSMContext) -> None:
        if not await permissions.ensure_permission(callback, permissions.ACTION_EVALUATE_EMPLOYEE):
            return

        data = await state.get_data()
        user_id = data.get("penalty_other_employee_id")
        text = data.get("penalty_other_text")
        await state.clear()

        if user_id is None or text is None:
            await callback.answer("Ma'lumot topilmadi (eskirgan holat).", show_alert=True)
            return

        await _notify_founder_unmatched(callback.bot, user_id, callback.from_user.id, text)
        await callback.answer("✅ Founderga yuborildi.")
        if callback.message:
            await callback.message.edit_text(
                "✅ Qabul qilindi — ball ayirilmadi, Founder ko'rib chiqishi uchun yuborildi.",
                reply_markup=None,
            )

    @dp.callback_query(F.data.startswith(_CB_ACK_PREFIX))
    async def employee_ack(callback: CallbackQuery) -> None:
        await callback.answer("✅ Qabul qilindi.")
        if callback.message:
            await callback.message.edit_reply_markup(reply_markup=None)

    @dp.callback_query(F.data.startswith(_CB_APPEAL_PREFIX))
    async def employee_appeal_start(callback: CallbackQuery, state: FSMContext) -> None:
        penalty_id = int(callback.data.split(":", 1)[1])
        await state.update_data(appeal_penalty_id=penalty_id)
        await state.set_state(discipline_bot.AppealStates.waiting_reason)
        await callback.answer()
        if callback.message:
            await callback.message.edit_reply_markup(reply_markup=None)
            await callback.message.answer("✍️ Sababingizni matn yoki ovozli xabar sifatida yuboring.")

    # -------------------------------------------------------------- davomat --

    def _yesterday_iso() -> str:
        return (company_time.today() - timedelta(days=1)).isoformat()

    async def _render_attendance_screen(callback: CallbackQuery, profile: dict) -> None:
        user_id = profile["user_id"]
        summary = attendance_service.get_day_summary(user_id, _yesterday_iso())

        if summary["arrival_time"] is None:
            await callback.message.edit_text(
                _attendance_screen_text(profile, summary) + "\n\n🕐 Kelish vaqtini HH:MM formatida yuboring:",
                reply_markup=_attendance_manual_entry_keyboard(user_id),
            )
            return

        if summary["reason_status"] is None:
            await callback.message.edit_text(
                _attendance_screen_text(profile, summary) + "\n\nSabab tanlansinmi?",
                reply_markup=_attendance_reason_keyboard(user_id),
            )
            return

        await callback.message.edit_text(
            _attendance_screen_text(profile, summary),
            reply_markup=_attendance_manual_entry_keyboard(user_id),
        )

    @dp.callback_query(F.data.startswith(_CB_ATTENDANCE_PREFIX))
    async def attendance_review(callback: CallbackQuery, state: FSMContext) -> None:
        if not await permissions.ensure_permission(callback, permissions.ACTION_EVALUATE_EMPLOYEE):
            return

        user_id = int(callback.data.split(":", 1)[1])
        profile = employees.get_profile(user_id)
        if profile is None:
            await callback.answer("Xodim topilmadi.", show_alert=True)
            return

        summary = attendance_service.get_day_summary(user_id, _yesterday_iso())
        if summary["arrival_time"] is None:
            await state.update_data(attendance_employee_id=user_id)
            await state.set_state(AttendanceStates.waiting_arrival_time)

        if callback.message:
            await _render_attendance_screen(callback, profile)
        await callback.answer()

    @dp.message(StateFilter(AttendanceStates.waiting_arrival_time))
    async def attendance_arrival_time_input(message: Message, state: FSMContext) -> None:
        data = await state.get_data()
        user_id = data.get("attendance_employee_id")
        profile = employees.get_profile(user_id) if user_id is not None else None
        if profile is None:
            await state.clear()
            await message.answer("❌ Bekor qilindi.")
            return

        text = (message.text or "").strip()
        if not attendance_service.record_manual_arrival(user_id, _yesterday_iso(), text):
            await message.answer("❌ Vaqtni HH:MM formatida kiriting (masalan 07:58):")
            return

        await state.clear()
        summary = attendance_service.get_day_summary(user_id, _yesterday_iso())
        await message.answer(
            _attendance_screen_text(profile, summary) + "\n\nSabab tanlansinmi?",
            reply_markup=_attendance_reason_keyboard(user_id),
        )

    @dp.callback_query(F.data.startswith(_CB_ATT_REASON_PREFIX))
    async def attendance_reason_pick(callback: CallbackQuery, state: FSMContext) -> None:
        if not await permissions.ensure_permission(callback, permissions.ACTION_EVALUATE_EMPLOYEE):
            return

        parts = callback.data.split(":", 2)
        if len(parts) != 3:
            await callback.answer()
            return

        user_id = int(parts[1])
        reason_key = parts[2]
        profile = employees.get_profile(user_id)
        if profile is None or reason_key not in _ATT_REASON_KEYS:
            await callback.answer("Xodim yoki sabab topilmadi.", show_alert=True)
            return

        event_date = _yesterday_iso()

        if reason_key == "unjustified":
            attendance_service.mark_unjustified(user_id, event_date)
            await callback.answer("✅ Qayd etildi: sababsiz kechikish.")
            if callback.message:
                await _render_attendance_screen(callback, profile)
            return

        if reason_key == "manager":
            attendance_service.request_manager_permission(user_id, event_date)
            await callback.answer("✅ Rahbarga so'rov yuborildi.")
            full_name = " ".join(part for part in (profile.get("familiya"), profile.get("ism")) if part) or "-"
            try:
                await callback.bot.send_message(
                    FOUNDER_ID,
                    f"❓ {full_name} bugun kechroq kelishga ruxsat berdingizmi?",
                    reply_markup=InlineKeyboardMarkup(
                        inline_keyboard=[
                            [
                                InlineKeyboardButton(
                                    text="✅ Ha", callback_data=f"{_CB_ATT_MGR_DECIDE_PREFIX}{user_id}:yes"
                                ),
                                InlineKeyboardButton(
                                    text="❌ Yo'q", callback_data=f"{_CB_ATT_MGR_DECIDE_PREFIX}{user_id}:no"
                                ),
                            ]
                        ]
                    ),
                )
            except Exception as error:  # noqa: BLE001
                print(f"Founderga rahbar-ruxsati so'rovini yuborib bo'lmadi ({user_id}): {error!r}")
            if callback.message:
                await _render_attendance_screen(callback, profile)
            return

        state_by_key = {
            "force": AttendanceStates.waiting_force_majeure_reason,
            "other": AttendanceStates.waiting_other_reason,
        }
        await state.update_data(attendance_employee_id=user_id)
        await state.set_state(state_by_key[reason_key])
        await callback.answer()
        if callback.message:
            await callback.message.answer("✍️ Qisqacha sababni yozing:")

    @dp.message(StateFilter(AttendanceStates.waiting_force_majeure_reason))
    async def attendance_force_majeure_reason(message: Message, state: FSMContext) -> None:
        data = await state.get_data()
        user_id = data.get("attendance_employee_id")
        await state.clear()

        text = (message.text or "").strip()
        if not text or user_id is None:
            await message.answer("❌ Bekor qilindi.")
            return

        attendance_service.mark_force_majeure(user_id, _yesterday_iso(), text)
        await message.answer("✅ Qayd etildi: fors-major holat.")

    @dp.message(StateFilter(AttendanceStates.waiting_other_reason))
    async def attendance_other_reason(message: Message, state: FSMContext) -> None:
        data = await state.get_data()
        user_id = data.get("attendance_employee_id")
        await state.clear()

        text = (message.text or "").strip()
        if not text or user_id is None:
            await message.answer("❌ Bekor qilindi.")
            return

        attendance_service.mark_other_reason(user_id, _yesterday_iso(), text)
        await message.answer("✅ Qayd etildi: boshqa sabab.")

    @dp.callback_query(F.data.startswith(_CB_ATT_MGR_DECIDE_PREFIX))
    async def attendance_manager_decide(callback: CallbackQuery) -> None:
        if not await permissions.ensure_permission(callback, permissions.ACTION_DECIDE_ATTENDANCE_PERMISSION):
            return

        parts = callback.data.split(":", 2)
        if len(parts) != 3:
            await callback.answer()
            return

        user_id = int(parts[1])
        approved = parts[2] == "yes"
        decided = attendance_service.decide_manager_permission(
            user_id, _yesterday_iso(), approved, callback.from_user.id
        )
        if not decided:
            await callback.answer("Bu so'rov allaqachon hal qilingan.", show_alert=True)
            return

        await callback.answer("✅ Qabul qilindi.")
        if callback.message:
            result_text = "✅ Ruxsat tasdiqlandi." if approved else "❌ Ruxsat tasdiqlanmadi."
            await callback.message.edit_text(result_text, reply_markup=None)

    # -------------------------------------------------------- ish grafigi --

    async def _ensure_schedule_access(callback: CallbackQuery, employee_id: int) -> dict | None:
        """Ruxsat + o'z-o'ziga tegmaslik + filial chegarasi -- bitta
        joyda. Muvaffaqiyatli bo'lsa xodim profili qaytadi, aks holda
        ``None`` (``callback.answer()`` allaqachon chaqirilgan bo'ladi).
        Founder o'zining grafigini ham o'zgartira oladi (self-edit
        cheklovi FAQAT Founder bo'lmagan foydalanuvchiga tegishli)."""
        if not await permissions.ensure_permission(callback, permissions.ACTION_MANAGE_DAILY_SCHEDULE):
            return None

        actor_id = callback.from_user.id
        profile = employees.get_profile(employee_id)
        if profile is None:
            await callback.answer("Xodim topilmadi.", show_alert=True)
            return None

        if employee_id == actor_id and actor_id != FOUNDER_ID:
            await callback.answer("O'z grafigingizni o'zingiz o'zgartira olmaysiz.", show_alert=True)
            return None

        if not permissions.can_access_branch(actor_id, profile.get("branch")):
            await callback.answer("Bu xodim boshqa filialga tegishli.", show_alert=True)
            return None

        return profile

    async def _render_schedule_menu(callback: CallbackQuery, profile: dict, schedule_date: str) -> None:
        if callback.message:
            await callback.message.edit_text(
                _schedule_screen_text(profile, schedule_date),
                reply_markup=_schedule_menu_keyboard(profile["user_id"]),
            )

    async def _show_schedule_confirm(callback: CallbackQuery, state: FSMContext, profile: dict, schedule_date: str, pending: dict) -> None:
        await state.update_data(schedule_pending=pending)
        full_name = " ".join(part for part in (profile.get("familiya"), profile.get("ism")) if part) or "-"
        if callback.message:
            await callback.message.edit_text(
                _schedule_confirm_text(full_name, schedule_date, pending),
                reply_markup=_schedule_confirm_keyboard(profile["user_id"]),
            )

    @dp.callback_query(F.data.startswith(_CB_SCHEDULE_PREFIX))
    async def schedule_open(callback: CallbackQuery, state: FSMContext) -> None:
        user_id = int(callback.data.split(":", 1)[1])
        profile = await _ensure_schedule_access(callback, user_id)
        if profile is None:
            return

        today = company_time.today().isoformat()
        await state.update_data(schedule_employee_id=user_id, schedule_date=today, schedule_pending=None)
        await _render_schedule_menu(callback, profile, today)
        await callback.answer()

    @dp.callback_query(F.data.startswith(_CB_SCHEDULE_FIXED_PREFIX))
    async def schedule_pick_fixed(callback: CallbackQuery, state: FSMContext) -> None:
        parts = callback.data.split(":", 2)
        if len(parts) != 3:
            await callback.answer()
            return

        user_id = int(parts[1])
        mode = parts[2]
        profile = await _ensure_schedule_access(callback, user_id)
        if profile is None:
            return

        template = rules_service.get_fixed_shift_template(mode)
        if template is None:
            await callback.answer("Shablon topilmadi.", show_alert=True)
            return

        start_text, end_text = template
        data = await state.get_data()
        schedule_date = data.get("schedule_date") or company_time.today().isoformat()

        pending = {
            "status": attendance_service.SHIFT_STATUS_WORK, "start": start_text, "end": end_text, "mode": mode,
        }
        await callback.answer()
        await _show_schedule_confirm(callback, state, profile, schedule_date, pending)

    @dp.callback_query(F.data.startswith(_CB_SCHEDULE_FLEX_PREFIX))
    async def schedule_pick_flexible_start(callback: CallbackQuery, state: FSMContext) -> None:
        user_id = int(callback.data.split(":", 1)[1])
        profile = await _ensure_schedule_access(callback, user_id)
        if profile is None:
            return

        await state.update_data(schedule_employee_id=user_id)
        await state.set_state(ScheduleStates.waiting_flexible_start)
        await callback.answer()
        if callback.message:
            await callback.message.edit_text("🕐 Boshlanish vaqtini kiriting (HH:MM):", reply_markup=None)

    @dp.message(StateFilter(ScheduleStates.waiting_flexible_start))
    async def schedule_flexible_start_input(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        if not attendance_service.is_valid_hhmm(text):
            await message.answer("❌ Noto'g'ri format. Vaqtni HH:MM ko'rinishida kiriting (masalan 10:00):")
            return

        await state.update_data(schedule_flex_start=text)
        await state.set_state(ScheduleStates.waiting_flexible_end)
        await message.answer("🕐 Tugash vaqtini kiriting (HH:MM):")

    @dp.message(StateFilter(ScheduleStates.waiting_flexible_end))
    async def schedule_flexible_end_input(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        if not attendance_service.is_valid_hhmm(text):
            await message.answer("❌ Noto'g'ri format. Vaqtni HH:MM ko'rinishida kiriting (masalan 20:00):")
            return

        data = await state.get_data()
        start_text = data.get("schedule_flex_start")
        user_id = data.get("schedule_employee_id")
        schedule_date = data.get("schedule_date") or company_time.today().isoformat()

        if start_text == text:
            await message.answer("❌ Boshlanish va tugash vaqti bir xil bo'lishi mumkin emas. Tugash vaqtini qayta kiriting:")
            return

        profile = employees.get_profile(user_id) if user_id is not None else None
        if profile is None:
            await state.clear()
            await message.answer("❌ Bekor qilindi.")
            return

        await state.set_state(None)
        full_name = " ".join(part for part in (profile.get("familiya"), profile.get("ism")) if part) or "-"
        pending = {
            "status": attendance_service.SHIFT_STATUS_WORK, "start": start_text, "end": text,
            "mode": attendance_service.SCHEDULE_MODE_FLEXIBLE,
        }
        await state.update_data(schedule_pending=pending)
        await message.answer(
            _schedule_confirm_text(full_name, schedule_date, pending),
            reply_markup=_schedule_confirm_keyboard(user_id),
        )

    @dp.callback_query(F.data.startswith(_CB_SCHEDULE_OFF_PREFIX))
    async def schedule_pick_off(callback: CallbackQuery, state: FSMContext) -> None:
        user_id = int(callback.data.split(":", 1)[1])
        profile = await _ensure_schedule_access(callback, user_id)
        if profile is None:
            return

        data = await state.get_data()
        schedule_date = data.get("schedule_date") or company_time.today().isoformat()

        pending = {"status": attendance_service.SHIFT_STATUS_OFF}
        await callback.answer()
        await _show_schedule_confirm(callback, state, profile, schedule_date, pending)

    @dp.callback_query(F.data.startswith(_CB_SCHEDULE_DATE_PREFIX))
    async def schedule_pick_other_date(callback: CallbackQuery, state: FSMContext) -> None:
        user_id = int(callback.data.split(":", 1)[1])
        profile = await _ensure_schedule_access(callback, user_id)
        if profile is None:
            return

        await state.update_data(schedule_employee_id=user_id)
        await state.set_state(ScheduleStates.waiting_custom_date)
        await callback.answer()
        if callback.message:
            await callback.message.edit_text("📅 Sanani YYYY-MM-DD formatida kiriting:", reply_markup=None)

    @dp.message(StateFilter(ScheduleStates.waiting_custom_date))
    async def schedule_custom_date_input(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        try:
            parsed = date.fromisoformat(text)
        except ValueError:
            await message.answer("❌ Sanani aniq YYYY-MM-DD formatida kiriting (masalan 2026-08-26):")
            return

        data = await state.get_data()
        user_id = data.get("schedule_employee_id")
        profile = employees.get_profile(user_id) if user_id is not None else None
        if profile is None:
            await state.clear()
            await message.answer("❌ Bekor qilindi.")
            return

        await state.set_state(None)
        await state.update_data(schedule_date=parsed.isoformat(), schedule_pending=None)
        await message.answer(
            _schedule_screen_text(profile, parsed.isoformat()),
            reply_markup=_schedule_menu_keyboard(user_id),
        )

    @dp.callback_query(F.data.startswith(_CB_SCHEDULE_CONFIRM_PREFIX))
    async def schedule_confirm(callback: CallbackQuery, state: FSMContext) -> None:
        user_id = int(callback.data.split(":", 1)[1])
        profile = await _ensure_schedule_access(callback, user_id)
        if profile is None:
            return

        actor_id = callback.from_user.id
        if actor_id in discipline_bot._PENDING_PENALTY_APPLICATIONS:
            await callback.answer()
            return
        discipline_bot._PENDING_PENALTY_APPLICATIONS.add(actor_id)

        try:
            data = await state.get_data()
            pending = data.get("schedule_pending")
            schedule_date = data.get("schedule_date") or company_time.today().isoformat()
            if not pending:
                await callback.answer("Ma'lumot topilmadi (eskirgan holat).", show_alert=True)
                return

            if pending["status"] == attendance_service.SHIFT_STATUS_OFF:
                attendance_service.set_scheduled_day_off(user_id, schedule_date, _SCHEDULE_SOURCE, created_by=actor_id)
            else:
                attendance_service.set_scheduled_work_shift(
                    user_id, schedule_date, pending["start"], pending["end"], _SCHEDULE_SOURCE,
                    created_by=actor_id, schedule_mode=pending.get("mode"),
                )

            await state.update_data(schedule_pending=None)
            full_name = " ".join(part for part in (profile.get("familiya"), profile.get("ism")) if part) or "-"
            await callback.answer("✅ Saqlandi.")
            if callback.message:
                await callback.message.edit_text(
                    _schedule_result_text(full_name, schedule_date, pending), reply_markup=None
                )

            try:
                if pending["status"] == attendance_service.SHIFT_STATUS_OFF:
                    notice_plan = "Dam olish"
                else:
                    notice_plan = f"{pending['start']}–{pending['end']}"
                await callback.bot.send_message(
                    user_id,
                    f"🗓 Ish grafigingiz belgilandi/o'zgartirildi\n\n📅 Sana: {schedule_date}\n🕒 Vaqt: {notice_plan}",
                )
            except Exception as error:  # noqa: BLE001
                print(f"Xodimga grafik xabarini yuborib bo'lmadi ({user_id}): {error!r}")
        finally:
            discipline_bot._PENDING_PENALTY_APPLICATIONS.discard(actor_id)

    @dp.callback_query(F.data.startswith(_CB_SCHEDULE_CANCEL_PREFIX))
    async def schedule_cancel(callback: CallbackQuery, state: FSMContext) -> None:
        user_id = int(callback.data.split(":", 1)[1])
        profile = await _ensure_schedule_access(callback, user_id)
        if profile is None:
            return

        data = await state.get_data()
        schedule_date = data.get("schedule_date") or company_time.today().isoformat()
        await state.update_data(schedule_pending=None)
        await callback.answer("Bekor qilindi.")
        await _render_schedule_menu(callback, profile, schedule_date)

    # ---------------------------------- grafik o'zgartirish so'rovlari --

    def _visible_pending_requests(actor_id: int) -> list[dict]:
        """Kutilayotgan so'rovlardan FAQAT shu aktyor haqiqatan hal qila
        oladiganlari — mavjud ``can_access_branch`` filial chegarasi va
        o'z so'rovini o'zi hal qilmaslik qoidasi (Founder istisno,
        ``_ensure_schedule_access``dagi bilan bir xil)."""
        visible = []
        for request in attendance_service.list_schedule_change_requests(
            status=attendance_service.SCHEDULE_REQUEST_PENDING
        ):
            employee_id = request["employee_id"]
            if employee_id == actor_id and actor_id != FOUNDER_ID:
                continue
            profile = employees.get_profile(employee_id)
            if profile is None or not permissions.can_access_branch(actor_id, profile.get("branch")):
                continue
            visible.append(request)
        return visible

    async def _render_schedule_requests(callback: CallbackQuery) -> None:
        requests = _visible_pending_requests(callback.from_user.id)
        if callback.message:
            await callback.message.edit_text(
                _schedule_requests_text(requests), reply_markup=_schedule_requests_keyboard(requests)
            )

    async def _load_request_for_actor(callback: CallbackQuery, request_id: int) -> tuple[dict, dict] | tuple[None, None]:
        """So'rov HAR safar (ochishda ham, qaror paytida ham) DBdan
        qaytadan o'qiladi va ruxsat qayta tekshiriladi — eskirgan tugma
        eski holatga tayanib qaror qabul qildira olmaydi."""
        request = attendance_service.get_schedule_change_request(request_id)
        if request is None:
            await callback.answer("So'rov topilmadi.", show_alert=True)
            return None, None

        profile = await _ensure_schedule_access(callback, request["employee_id"])
        if profile is None:
            return None, None

        return request, profile

    async def _decide_schedule_request(callback: CallbackQuery, request_id: int, approved: bool) -> None:
        request, _profile = await _load_request_for_actor(callback, request_id)
        if request is None:
            return

        # Haqiqiy himoya — ``decide_schedule_change_request``ning atomik
        # ``pending -> approved/rejected`` o'tishi: ikkinchi/parallel
        # bosish hech narsani qayta yozmaydi (schedule ham tegilmaydi).
        decided = request["status"] == attendance_service.SCHEDULE_REQUEST_PENDING and (
            attendance_service.decide_schedule_change_request(
                request_id, approved=approved, decided_by=callback.from_user.id
            )
        )
        if decided:
            await callback.answer("✅ Tasdiqlandi." if approved else "❌ Rad etildi.")
        else:
            await callback.answer("Bu so'rov allaqachon hal qilingan.", show_alert=True)

        await _render_schedule_requests(callback)

    @dp.message(Command("grafiksorov"))
    async def schedule_requests_start(message: Message) -> None:
        if not await permissions.ensure_permission(message, permissions.ACTION_MANAGE_DAILY_SCHEDULE):
            return

        requests = _visible_pending_requests(message.from_user.id)
        await message.answer(
            _schedule_requests_text(requests), reply_markup=_schedule_requests_keyboard(requests)
        )

    @dp.callback_query(F.data == _CB_SCHEDULE_REQUESTS)
    async def schedule_requests_back(callback: CallbackQuery) -> None:
        if not await permissions.ensure_permission(callback, permissions.ACTION_MANAGE_DAILY_SCHEDULE):
            return

        await callback.answer()
        await _render_schedule_requests(callback)

    @dp.callback_query(F.data.startswith(_CB_SCHEDULE_REQ_APPROVE_PREFIX))
    async def schedule_request_approve(callback: CallbackQuery) -> None:
        await _decide_schedule_request(callback, int(callback.data.split(":", 1)[1]), approved=True)

    @dp.callback_query(F.data.startswith(_CB_SCHEDULE_REQ_REJECT_PREFIX))
    async def schedule_request_reject(callback: CallbackQuery) -> None:
        await _decide_schedule_request(callback, int(callback.data.split(":", 1)[1]), approved=False)

    @dp.callback_query(F.data.startswith(_CB_SCHEDULE_REQ_PREFIX))
    async def schedule_request_open(callback: CallbackQuery) -> None:
        request_id = int(callback.data.split(":", 1)[1])
        request, profile = await _load_request_for_actor(callback, request_id)
        if request is None:
            return

        if request["status"] == attendance_service.SCHEDULE_REQUEST_PENDING:
            keyboard = _schedule_request_decision_keyboard(request_id)
        else:
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="⬅️ Orqaga", callback_data=_CB_SCHEDULE_REQUESTS)]]
            )

        await callback.answer()
        if callback.message:
            await callback.message.edit_text(_schedule_request_text(request, profile), reply_markup=keyboard)

    # ------------------------------------------------------ filial nazorati --

    async def _ensure_mobility_access(callback: CallbackQuery, employee_id: int, action: str) -> dict | None:
        """``_ensure_schedule_access``dagi bilan bir xil naqsh -- ruxsat
        + o'z-o'ziga tegmaslik (Founder istisno) + mavjud
        ``can_access_branch`` qoidasi. ``action`` chaqiruvchiga qarab
        ``ACTION_MANAGE_MOBILITY_POLICY`` yoki
        ``ACTION_MANAGE_BRANCH_VISIT_REQUIREMENTS`` bo'lishi mumkin."""
        if not await permissions.ensure_permission(callback, action):
            return None

        actor_id = callback.from_user.id
        profile = employees.get_profile(employee_id)
        if profile is None:
            await callback.answer("Xodim topilmadi.", show_alert=True)
            return None

        if employee_id == actor_id and actor_id != FOUNDER_ID:
            await callback.answer("O'zingizga tegishli sozlamani o'zgartira olmaysiz.", show_alert=True)
            return None

        if not permissions.can_access_branch(actor_id, profile.get("branch")):
            await callback.answer("Bu xodim boshqa filialga tegishli.", show_alert=True)
            return None

        return profile

    async def _render_mobility_menu(callback: CallbackQuery, profile: dict, mobility_date: str) -> None:
        if callback.message:
            await callback.message.edit_text(
                _mobility_screen_text(profile, mobility_date),
                reply_markup=_mobility_menu_keyboard(profile["user_id"]),
            )

    async def _notify_employee_mobility(callback: CallbackQuery, employee_id: int, text: str) -> None:
        try:
            await callback.bot.send_message(employee_id, text)
        except Exception as error:  # noqa: BLE001
            print(f"Xodimga filial nazorati xabarini yuborib bo'lmadi ({employee_id}): {error!r}")

    @dp.callback_query(F.data.startswith(_CB_MOBILITY_PREFIX))
    async def mobility_open(callback: CallbackQuery, state: FSMContext) -> None:
        user_id = int(callback.data.split(":", 1)[1])
        profile = await _ensure_mobility_access(callback, user_id, permissions.ACTION_MANAGE_BRANCH_VISIT_REQUIREMENTS)
        if profile is None:
            return

        today = company_time.today().isoformat()
        await state.update_data(mobility_employee_id=user_id, mobility_date=today, mobility_pending=None, mobility_pending_branch=None)
        await _render_mobility_menu(callback, profile, today)
        await callback.answer()

    @dp.callback_query(F.data.startswith(_CB_MOBILITY_REQS_PREFIX))
    async def mobility_requirements(callback: CallbackQuery, state: FSMContext) -> None:
        user_id = int(callback.data.split(":", 1)[1])
        profile = await _ensure_mobility_access(callback, user_id, permissions.ACTION_MANAGE_BRANCH_VISIT_REQUIREMENTS)
        if profile is None:
            return

        data = await state.get_data()
        mobility_date = data.get("mobility_date") or company_time.today().isoformat()
        requirements = attendance_service.get_branch_visit_requirements(user_id, mobility_date)

        await callback.answer()
        if callback.message:
            await callback.message.edit_text(
                _mobility_compliance_text(profile, mobility_date),
                reply_markup=_mobility_requirements_keyboard(user_id, requirements),
            )

    @dp.callback_query(F.data.startswith(_CB_MOBILITY_ADD_PREFIX))
    async def mobility_add_start(callback: CallbackQuery, state: FSMContext) -> None:
        user_id = int(callback.data.split(":", 1)[1])
        profile = await _ensure_mobility_access(callback, user_id, permissions.ACTION_MANAGE_BRANCH_VISIT_REQUIREMENTS)
        if profile is None:
            return

        await callback.answer()
        if callback.message:
            await callback.message.edit_text("📍 Filialni tanlang:", reply_markup=_mobility_branch_picker_keyboard(user_id))

    @dp.callback_query(F.data.startswith(_CB_MOBILITY_BRANCH_PREFIX))
    async def mobility_branch_pick(callback: CallbackQuery, state: FSMContext) -> None:
        parts = callback.data.split(":", 2)
        if len(parts) != 3:
            await callback.answer()
            return

        user_id = int(parts[1])
        branch = parts[2]
        profile = await _ensure_mobility_access(callback, user_id, permissions.ACTION_MANAGE_BRANCH_VISIT_REQUIREMENTS)
        if profile is None:
            return

        await state.update_data(mobility_pending_branch=branch)
        await callback.answer()
        if callback.message:
            await callback.message.edit_text(
                f"🏬 {branch}\n⏱ Minimal turish vaqtini tanlang:", reply_markup=_mobility_minutes_keyboard(user_id)
            )

    async def _show_mobility_confirm(callback: CallbackQuery, state: FSMContext, profile: dict, mobility_date: str, branch: str, minutes: int) -> None:
        await state.update_data(mobility_pending={"branch": branch, "minutes": minutes})
        full_name = " ".join(part for part in (profile.get("familiya"), profile.get("ism")) if part) or "-"
        if callback.message:
            await callback.message.edit_text(
                _mobility_requirement_confirm_text(full_name, mobility_date, branch, minutes),
                reply_markup=_mobility_requirement_confirm_keyboard(profile["user_id"]),
            )

    @dp.callback_query(F.data.startswith(_CB_MOBILITY_MIN_PREFIX))
    async def mobility_minutes_quick(callback: CallbackQuery, state: FSMContext) -> None:
        parts = callback.data.split(":", 2)
        if len(parts) != 3:
            await callback.answer()
            return

        user_id = int(parts[1])
        try:
            minutes = int(parts[2])
        except ValueError:
            await callback.answer()
            return

        profile = await _ensure_mobility_access(callback, user_id, permissions.ACTION_MANAGE_BRANCH_VISIT_REQUIREMENTS)
        if profile is None:
            return

        data = await state.get_data()
        branch = data.get("mobility_pending_branch")
        mobility_date = data.get("mobility_date") or company_time.today().isoformat()
        if not branch:
            await callback.answer("Ma'lumot topilmadi (eskirgan holat).", show_alert=True)
            return

        await callback.answer()
        await _show_mobility_confirm(callback, state, profile, mobility_date, branch, minutes)

    @dp.callback_query(F.data.startswith(_CB_MOBILITY_CUSTOM_PREFIX))
    async def mobility_minutes_custom_start(callback: CallbackQuery, state: FSMContext) -> None:
        user_id = int(callback.data.split(":", 1)[1])
        profile = await _ensure_mobility_access(callback, user_id, permissions.ACTION_MANAGE_BRANCH_VISIT_REQUIREMENTS)
        if profile is None:
            return

        await state.set_state(MobilityStates.waiting_custom_minutes)
        await callback.answer()
        if callback.message:
            await callback.message.edit_text("✍️ Minimal turish vaqtini daqiqada kiriting (musbat butun son):", reply_markup=None)

    @dp.message(StateFilter(MobilityStates.waiting_custom_minutes))
    async def mobility_minutes_custom_input(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        if not text.isdigit() or int(text) <= 0:
            await message.answer("❌ Musbat butun son kiriting (masalan 25, 35, 90):")
            return

        data = await state.get_data()
        user_id = data.get("mobility_employee_id")
        branch = data.get("mobility_pending_branch")
        mobility_date = data.get("mobility_date") or company_time.today().isoformat()
        profile = employees.get_profile(user_id) if user_id is not None else None
        if profile is None or not branch:
            await state.clear()
            await message.answer("❌ Bekor qilindi.")
            return

        await state.set_state(None)
        minutes = int(text)
        await state.update_data(mobility_pending={"branch": branch, "minutes": minutes})
        full_name = " ".join(part for part in (profile.get("familiya"), profile.get("ism")) if part) or "-"
        await message.answer(
            _mobility_requirement_confirm_text(full_name, mobility_date, branch, minutes),
            reply_markup=_mobility_requirement_confirm_keyboard(user_id),
        )

    @dp.callback_query(F.data.startswith(_CB_MOBILITY_CONFIRM_PREFIX))
    async def mobility_requirement_confirm(callback: CallbackQuery, state: FSMContext) -> None:
        user_id = int(callback.data.split(":", 1)[1])
        profile = await _ensure_mobility_access(callback, user_id, permissions.ACTION_MANAGE_BRANCH_VISIT_REQUIREMENTS)
        if profile is None:
            return

        data = await state.get_data()
        pending = data.get("mobility_pending")
        if not pending:
            await callback.answer("Ma'lumot topilmadi (eskirgan holat).", show_alert=True)
            return

        # Pending'ni DARHOL iste'mol qilamiz (yozishdan OLDIN) -- ikkinchi
        # (eskirgan) confirm bosilishi endi shunchaki "eskirgan holat"
        # sifatida no-op bo'ladi, DB UNIQUE esa oxirgi himoya bo'lib qoladi.
        await state.update_data(mobility_pending=None)

        actor_id = callback.from_user.id
        mobility_date = data.get("mobility_date") or company_time.today().isoformat()
        branch = pending["branch"]
        minutes = pending["minutes"]

        existing_before = attendance_service.get_branch_visit_requirements(user_id, mobility_date)
        was_existing = any(r["branch"] == branch for r in existing_before)

        accepted = attendance_service.set_branch_visit_requirement(user_id, mobility_date, branch, minutes, created_by=actor_id)
        if not accepted:
            await callback.answer("❌ Noto'g'ri qiymat.", show_alert=True)
            return

        full_name = " ".join(part for part in (profile.get("familiya"), profile.get("ism")) if part) or "-"
        await callback.answer("✅ Saqlandi.")
        if callback.message:
            await callback.message.edit_text(
                "✅ Talab saqlandi\n\n" + _mobility_requirement_confirm_text(full_name, mobility_date, branch, minutes),
                reply_markup=None,
            )

        if was_existing:
            notice = (
                "📍 Filial vazifangiz o'zgartirildi\n\n"
                f"📅 {_format_date_display(mobility_date)}\n🏬 {branch}\n⏱ Yangi talab: {minutes} daqiqa"
            )
        else:
            notice = (
                "📍 Filial vazifangiz belgilandi\n\n"
                f"📅 {_format_date_display(mobility_date)}\n🏬 {branch}\n⏱ Kamida {minutes} daqiqa"
            )
        await _notify_employee_mobility(callback, user_id, notice)

    @dp.callback_query(F.data.startswith(_CB_MOBILITY_CANCEL_PREFIX))
    async def mobility_requirement_cancel(callback: CallbackQuery, state: FSMContext) -> None:
        user_id = int(callback.data.split(":", 1)[1])
        profile = await _ensure_mobility_access(callback, user_id, permissions.ACTION_MANAGE_BRANCH_VISIT_REQUIREMENTS)
        if profile is None:
            return

        data = await state.get_data()
        mobility_date = data.get("mobility_date") or company_time.today().isoformat()
        await state.update_data(mobility_pending=None, mobility_pending_branch=None)
        await callback.answer("Bekor qilindi.")
        await _render_mobility_menu(callback, profile, mobility_date)

    @dp.callback_query(F.data.startswith(_CB_MOBILITY_EDIT_PREFIX))
    async def mobility_edit_branch(callback: CallbackQuery, state: FSMContext) -> None:
        parts = callback.data.split(":", 2)
        if len(parts) != 3:
            await callback.answer()
            return

        user_id = int(parts[1])
        branch = parts[2]
        profile = await _ensure_mobility_access(callback, user_id, permissions.ACTION_MANAGE_BRANCH_VISIT_REQUIREMENTS)
        if profile is None:
            return

        data = await state.get_data()
        mobility_date = data.get("mobility_date") or company_time.today().isoformat()
        requirements = attendance_service.get_branch_visit_requirements(user_id, mobility_date)
        requirement = next((r for r in requirements if r["branch"] == branch), None)
        if requirement is None:
            await callback.answer("Bu talab topilmadi.", show_alert=True)
            return

        await callback.answer()
        if callback.message:
            await callback.message.edit_text(
                _mobility_branch_detail_text(branch, requirement["min_stay_minutes"]),
                reply_markup=_mobility_branch_detail_keyboard(user_id, branch),
            )

    @dp.callback_query(F.data.startswith(_CB_MOBILITY_REMOVE_YES_PREFIX))
    async def mobility_remove_yes(callback: CallbackQuery, state: FSMContext) -> None:
        parts = callback.data.split(":", 2)
        if len(parts) != 3:
            await callback.answer()
            return

        user_id = int(parts[1])
        branch = parts[2]
        profile = await _ensure_mobility_access(callback, user_id, permissions.ACTION_MANAGE_BRANCH_VISIT_REQUIREMENTS)
        if profile is None:
            return

        data = await state.get_data()
        mobility_date = data.get("mobility_date") or company_time.today().isoformat()
        actor_id = callback.from_user.id

        removed = attendance_service.remove_branch_visit_requirement(user_id, mobility_date, branch, removed_by=actor_id)
        if not removed:
            await callback.answer("Bu talab allaqachon olib tashlangan.", show_alert=True)
            if callback.message:
                await _render_mobility_menu(callback, profile, mobility_date)
            return

        await callback.answer("✅ Olib tashlandi.")
        if callback.message:
            await callback.message.edit_text(f"✅ Talab olib tashlandi\n\n🏬 {branch}", reply_markup=None)

        await _notify_employee_mobility(
            callback, user_id,
            "📍 Filial vazifangiz bekor qilindi\n\n"
            f"📅 {_format_date_display(mobility_date)}\n🏬 {branch}",
        )

    @dp.callback_query(F.data.startswith(_CB_MOBILITY_REMOVE_NO_PREFIX))
    async def mobility_remove_no(callback: CallbackQuery, state: FSMContext) -> None:
        parts = callback.data.split(":", 2)
        if len(parts) != 3:
            await callback.answer()
            return

        user_id = int(parts[1])
        profile = await _ensure_mobility_access(callback, user_id, permissions.ACTION_MANAGE_BRANCH_VISIT_REQUIREMENTS)
        if profile is None:
            return

        data = await state.get_data()
        mobility_date = data.get("mobility_date") or company_time.today().isoformat()
        requirements = attendance_service.get_branch_visit_requirements(user_id, mobility_date)

        await callback.answer("Bekor qilindi.")
        if callback.message:
            await callback.message.edit_text(
                _mobility_compliance_text(profile, mobility_date),
                reply_markup=_mobility_requirements_keyboard(user_id, requirements),
            )

    @dp.callback_query(F.data.startswith(_CB_MOBILITY_REMOVE_PREFIX))
    async def mobility_remove_start(callback: CallbackQuery, state: FSMContext) -> None:
        parts = callback.data.split(":", 2)
        if len(parts) != 3:
            await callback.answer()
            return

        user_id = int(parts[1])
        branch = parts[2]
        profile = await _ensure_mobility_access(callback, user_id, permissions.ACTION_MANAGE_BRANCH_VISIT_REQUIREMENTS)
        if profile is None:
            return

        data = await state.get_data()
        mobility_date = data.get("mobility_date") or company_time.today().isoformat()
        requirements = attendance_service.get_branch_visit_requirements(user_id, mobility_date)
        requirement = next((r for r in requirements if r["branch"] == branch), None)
        if requirement is None:
            await callback.answer("Bu talab topilmadi.", show_alert=True)
            return

        await callback.answer()
        if callback.message:
            await callback.message.edit_text(
                _mobility_branch_detail_text(branch, requirement["min_stay_minutes"]) + "\n\nBu talabni olib tashlaysizmi?",
                reply_markup=_mobility_remove_confirm_keyboard(user_id, branch),
            )

    @dp.callback_query(F.data.startswith(_CB_MOBILITY_MODE_PREFIX))
    async def mobility_mode_open(callback: CallbackQuery, state: FSMContext) -> None:
        user_id = int(callback.data.split(":", 1)[1])
        profile = await _ensure_mobility_access(callback, user_id, permissions.ACTION_MANAGE_MOBILITY_POLICY)
        if profile is None:
            return

        await callback.answer()
        if callback.message:
            await callback.message.edit_text("🚶 Rejimni tanlang:", reply_markup=_mobility_mode_keyboard(user_id))

    @dp.callback_query(F.data.startswith(_CB_MOBILITY_MODE_SET_PREFIX))
    async def mobility_mode_set(callback: CallbackQuery, state: FSMContext) -> None:
        parts = callback.data.split(":", 2)
        if len(parts) != 3:
            await callback.answer()
            return

        user_id = int(parts[1])
        mode = parts[2]
        profile = await _ensure_mobility_access(callback, user_id, permissions.ACTION_MANAGE_MOBILITY_POLICY)
        if profile is None:
            return

        attendance_service.set_employee_mobility_mode(user_id, mode, updated_by=callback.from_user.id)

        data = await state.get_data()
        mobility_date = data.get("mobility_date") or company_time.today().isoformat()
        await callback.answer("✅ Rejim yangilandi.")
        await _render_mobility_menu(callback, profile, mobility_date)

    @dp.callback_query(F.data.startswith(_CB_MOBILITY_DATE_PREFIX))
    async def mobility_pick_other_date(callback: CallbackQuery, state: FSMContext) -> None:
        user_id = int(callback.data.split(":", 1)[1])
        profile = await _ensure_mobility_access(callback, user_id, permissions.ACTION_MANAGE_BRANCH_VISIT_REQUIREMENTS)
        if profile is None:
            return

        await state.update_data(mobility_employee_id=user_id)
        await state.set_state(MobilityStates.waiting_custom_date)
        await callback.answer()
        if callback.message:
            await callback.message.edit_text("📅 Sanani YYYY-MM-DD formatida kiriting:", reply_markup=None)

    @dp.message(StateFilter(MobilityStates.waiting_custom_date))
    async def mobility_custom_date_input(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        try:
            parsed = date.fromisoformat(text)
        except ValueError:
            await message.answer("❌ Sanani aniq YYYY-MM-DD formatida kiriting (masalan 2026-08-28):")
            return

        data = await state.get_data()
        user_id = data.get("mobility_employee_id")
        profile = employees.get_profile(user_id) if user_id is not None else None
        if profile is None:
            await state.clear()
            await message.answer("❌ Bekor qilindi.")
            return

        await state.set_state(None)
        await state.update_data(mobility_date=parsed.isoformat(), mobility_pending=None, mobility_pending_branch=None)
        await message.answer(
            _mobility_screen_text(profile, parsed.isoformat()),
            reply_markup=_mobility_menu_keyboard(user_id),
        )

    # ---------------------------------------------------- ishdan chiqarish --

    async def _ensure_offboard_access(callback: CallbackQuery, employee_id: int) -> dict | None:
        """``_ensure_mobility_access`` bilan bir xil naqsh, BITTA farq
        bilan: bu yerda Founder uchun ham o'z-o'ziga tegmaslik cheklovi
        amal qiladi (Founder o'zini ishdan chiqara olmaydi)."""
        if not await permissions.ensure_permission(callback, permissions.ACTION_OFFBOARD_EMPLOYEE):
            return None

        actor_id = callback.from_user.id
        profile = employees.get_profile(employee_id)
        if profile is None:
            await callback.answer("Xodim topilmadi.", show_alert=True)
            return None

        if employee_id == actor_id:
            await callback.answer("O'zingizni ishdan chiqara olmaysiz.", show_alert=True)
            return None

        if not permissions.can_access_branch(actor_id, profile.get("branch")):
            await callback.answer("Bu xodim boshqa filialga tegishli.", show_alert=True)
            return None

        return profile

    @dp.callback_query(F.data.startswith(_CB_OFFBOARD_PREFIX))
    async def offboard_start(callback: CallbackQuery) -> None:
        user_id = int(callback.data.split(":", 1)[1])
        profile = await _ensure_offboard_access(callback, user_id)
        if profile is None:
            return

        if callback.message:
            await callback.message.edit_text(
                _offboard_confirm_text(profile),
                reply_markup=_offboard_confirm_keyboard(user_id),
            )
        await callback.answer()

    @dp.callback_query(F.data.startswith(_CB_OFFBOARD_NO_PREFIX))
    async def offboard_cancel(callback: CallbackQuery) -> None:
        user_id = int(callback.data.split(":", 1)[1])
        profile = await _ensure_offboard_access(callback, user_id)
        if profile is None:
            return

        await _render_employee_card(callback, profile)
        await callback.answer("Bekor qilindi.")

    @dp.callback_query(F.data.startswith(_CB_OFFBOARD_YES_PREFIX))
    async def offboard_confirm(callback: CallbackQuery) -> None:
        user_id = int(callback.data.split(":", 1)[1])
        profile = await _ensure_offboard_access(callback, user_id)
        if profile is None:
            return

        # Atomik ``UPDATE ... WHERE status = 'approved'`` — ikkinchi
        # (takroriy bosilgan) tasdiq ``None`` qaytaradi, shuning uchun
        # audit ham, xabar ham faqat bir marta bo'ladi.
        offboarded = employees.offboard_profile(user_id)
        if offboarded is None:
            await callback.answer("ℹ️ Bu xodim allaqachon aktiv ro'yxatda emas.", show_alert=True)
            return

        audit.log_event(
            audit.EVENT_EMPLOYEE_OFFBOARDED,
            actor_id=callback.from_user.id,
            actor_role=get_role(callback.from_user.id),
            chat_id=callback.message.chat.id if callback.message else None,
            target_id=user_id,
            old_value=employees.STATUS_APPROVED,
            new_value=employees.STATUS_OFFBOARDED,
        )

        await callback.answer("✅ Xodim aktiv ro'yxatdan chiqarildi.")
        if callback.message:
            await callback.message.edit_text(
                _offboard_result_text(offboarded),
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[InlineKeyboardButton(text="⬅️ Filiallar", callback_data=_CB_BRANCHES)]]
                ),
            )

        # Xabar yuborish ikkinchi darajali — DB'dagi holat o'zgarishi
        # allaqachon yakunlangan, xato bo'lsa ham qaytarilmaydi.
        try:
            await callback.bot.send_message(
                user_id,
                "🚪 Siz aktiv xodimlar ro'yxatidan chiqarildingiz.\n\n"
                "📚 Ish tarixingiz saqlanib qoladi. Savollaringiz bo'lsa rahbariyatga murojaat qiling.",
            )
        except Exception as error:  # noqa: BLE001
            print(f"Xodimga ishdan chiqarish xabarini yuborib bo'lmadi ({user_id}): {error!r}")

    # ----------------------------------------------------- vazifa biriktirish --

    @dp.message(Command("vazifabiriktir"))
    async def assign_task_handler(message: Message) -> None:
        if not await permissions.ensure_permission(message, permissions.ACTION_MANAGE_TASK_ASSIGNMENTS):
            return

        parts = (message.text or "").split(maxsplit=2)
        if len(parts) < 3 or not parts[1].isdigit():
            await message.answer(
                "Foydalanish: /vazifabiriktir <user_id> <vazifa nomi>\n"
                "Masalan: /vazifabiriktir 123456789 Ombor"
            )
            return

        employee_id = int(parts[1])
        title = parts[2].strip()
        if employees.get_profile(employee_id) is None:
            await message.answer("❌ Bu user_id bilan xodim topilmadi.")
            return

        task = tasks_service.assign_task_to_employee(title, employee_id, message.from_user.id)
        await message.answer(f"✅ \"{task['title']}\" vazifasi xodimga biriktirildi.")

    @dp.message(Command("vazifabekor"))
    async def unassign_task_handler(message: Message) -> None:
        if not await permissions.ensure_permission(message, permissions.ACTION_MANAGE_TASK_ASSIGNMENTS):
            return

        parts = (message.text or "").split(maxsplit=2)
        if len(parts) < 3 or not parts[1].isdigit():
            await message.answer(
                "Foydalanish: /vazifabekor <user_id> <vazifa nomi>\n"
                "Masalan: /vazifabekor 123456789 Ombor"
            )
            return

        employee_id = int(parts[1])
        title = parts[2].strip()
        if tasks_service.unassign_task_from_employee(title, employee_id):
            await message.answer(f"✅ \"{title}\" vazifasi xodimdan olib tashlandi.")
        else:
            await message.answer("❌ Bu nomdagi vazifa topilmadi.")
