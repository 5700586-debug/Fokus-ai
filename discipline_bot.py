"""BOS (Business Operating System) — Telegram interfeysi.

``services/discipline.py`` (biznes logika) va ``services/discipline_ai.py``
(AI tushuntirish/tavsiya) ustiga qurilgan bot oqimi:

- Nazoratchi: xodimni inline tugmalar orqali tanlaydi -> [Chala-1]/[Norma-2]/
  [A'lo-3] yoki jarima (-10/-20/-30) -> jarimada nizom raqami majburiy
  so'raladi va bazadagi nizom bilan solishtiriladi.
- Kunlik ("Bugungi Poyga") va oylik ("Oylik Turnir") reyting dashboardlari.
- Ish kuni 06:00 da minus va kunlik xabarsiz avtomatik yopiladi.
- Xodim jarimaga e'tiroz bildirsa, AI dalil/nizomni solishtirib Founder'ga
  qaror taklifi tayyorlaydi — yakuniy qarorni doim Founder qabul qiladi.
"""

import asyncio
import logging
import secrets
from datetime import date, datetime, timedelta, timezone as dt_timezone
from zoneinfo import ZoneInfo

from aiogram import Dispatcher, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import company_time
import employees
from config import COMPANY_TIMEZONE, FOUNDER_ID, RECRUITING_BRANCH_NAMES
from roles import is_authorized, list_users
from services import chat_cleanup, dialog_cleanup, discipline, discipline_ai, nazoratchi_close_report as close_report, nazoratchi_day, permissions, rule_learning
from services import company_rules_import as discipline_import
from services import rules as rules_service
from services import salary_agreement

logger = logging.getLogger(__name__)

_PAGE_SIZE = 8
_MEDALS = ["🥇", "🥈", "🥉"]
_MANAGEMENT_ROLES = {"founder", "nazoratchi"}

# ``baholash_enter_rule`` FSM holatni tozalagandan keyin AI tasdig'ini
# (haqiqiy tarmoq so'rovi) kutadi, keyingina jarimani yozadi —
# ``discipline_penalties``da bitta xodimga bir kunda bir nechta HAQIQIY
# jarima qo'llash qonuniy bo'lgani uchun DB darajasida UNIQUE cheklov
# qo'yib bo'lmaydi. Shu oraliqda bir xil nazoratchidan deyarli bir
# vaqtda ikkinchi xabar kelsa (masalan ikki marta yuborilgan/qayta
# urinilgan xabar), ``bonus_bank`` ikki marta kamayib ketmasligi uchun
# — jarayon-ichi (in-process) himoya, sinxron check-then-add uslubida.
# Bitta nazoratchi bir vaqtning o'zida faqat bitta jarima
# yozuvini qayta ishlashi mumkin.
_PENDING_PENALTY_APPLICATIONS: set[int] = set()
_PENDING_CATALOG_IMPORTS: set[int] = set()
_LEGACY_CLOSE_PREVIEWS: dict[tuple[int, int], dict] = {}
_LISTNIZOM_SINGLE_LIMIT = 3800
_LISTNIZOM_PAGE_SIZE = 8


def _resolve_timezone():
    try:
        return ZoneInfo(COMPANY_TIMEZONE)
    except Exception as error:
        message = f"COMPANY_TIMEZONE ({COMPANY_TIMEZONE!r}) yuklanmadi, UTC'ga qaytildi: {error!r}"
        logger.error(message)
        print(message)
        return dt_timezone.utc


def _today() -> date:
    """Server UTC bo'lsa ham, kompaniya vaqt zonasi bo'yicha bugungi sana."""
    return datetime.now(_resolve_timezone()).date()


def _employee_name(user_id: int) -> str:
    profile = employees.get_profile(user_id)
    if profile is None:
        return str(user_id)

    full_name = " ".join(part for part in (profile.get("familiya"), profile.get("ism")) if part)
    return full_name or str(user_id)


_RULE_LEARNING_STATUS_LABELS = {
    "not_learned": "nizom o'rganilishi boshlanmagan",
    "learning_incomplete": "o'rganish tugallanmagan",
    "understood_before_penalty": "ball ayirilishidan oldin tushunilgan",
    "understood_after_penalty": "ball ayirilishidan keyin tushunilgan",
}


def _rule_learning_status(penalty_id: int) -> tuple[dict | None, str]:
    """BITTA ``discipline.get_penalty_learning_context`` chaqiruvidan
    ``(context, status_line)`` qaytaradi. Lookup/format xatosi bo'lsa
    (masalan jarima topilmasa yoki holat noma'lum bo'lsa) log qilinadi
    va ``(None, "")`` qaytariladi -- mavjud oqim shu qatorsiz/alert-siz
    davom etadi (qarang chaqiruvchi joy)."""
    try:
        context = discipline.get_penalty_learning_context(penalty_id)
        status_text = _RULE_LEARNING_STATUS_LABELS[context["status"]]
    except Exception as error:
        print(f"Nizom holatini olishda xato (penalty_id={penalty_id}): {error!r}")
        return None, ""

    return context, f"\n📚 Nizom holati: {status_text}"


def _target_employees() -> list[tuple[int, str]]:
    result = [
        (user_id, _employee_name(user_id))
        for user_id, info in list_users().items()
        if info["role"] not in _MANAGEMENT_ROLES
    ]
    result.sort(key=lambda pair: pair[1])
    return result


def _format_board(title: str, board: list[dict], score_key: str) -> str:
    if not board:
        return f"{title}\n\nHali ma'lumot yo'q."

    lines = [title, ""]
    for index, row in enumerate(board):
        medal = _MEDALS[index] if index < len(_MEDALS) else f"{index + 1}."
        name = _employee_name(row["employee_id"])
        lines.append(f"{medal} {name} — {row[score_key]} ball")

    return "\n".join(lines)


# ----------------------------------------- filial -> xodimlar -> baholash (UI) --
# Sessiya = sana + filial + nazoratchi. Callback'lar sanani ``YYYYMMDD`` ko'rinishida olib yuradi
# (har filial/sana alohida, eski yopilmagan sessiya ham shu orqali ochiladi).


def _ymd(iso_date: str) -> str:
    return iso_date.replace("-", "")


def _iso_from_ymd(text: str) -> str | None:
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    return None


def _branch_short(branch: str) -> str:
    return branch.removeprefix("SATURN ").strip() or branch


def _branch_index(branch: str) -> int | None:
    try:
        return RECRUITING_BRANCH_NAMES.index(branch)
    except ValueError:
        return None


def _now_company() -> datetime:
    return company_time.now()


def _display_date(iso_date: str) -> str:
    year, month, day = iso_date.split("-")
    return f"{day}.{month}.{year}"


def _branch_picker_keyboard(prefix: str, review_date: str, supervisor_id: int | None = None) -> InlineKeyboardMarkup:
    closed: set[str] = set()
    if supervisor_id is not None:
        closed = {
            item["branch"]
            for item in discipline_repo_sessions(supervisor_id, review_date)
            if item["status"] == "closed"
        }
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text=f"{'✅' if name in closed else '📍'} {name}", callback_data=f"{prefix}:{index}:{_ymd(review_date)}"
            )]
            for index, name in enumerate(RECRUITING_BRANCH_NAMES)
        ]
    )


def discipline_repo_sessions(supervisor_id: int, work_date: str) -> list[dict]:
    from repositories import discipline as discipline_repo

    return [
        item for item in discipline_repo.list_branch_sessions_up_to(supervisor_id, work_date)
        if item["session_date"] == work_date
    ]


RESUME_NOTE = "Avval shu ish kunini yakunlaymiz."


def _day_header(day) -> str:
    text = f"📅 Ish kuni: {_display_date(day.work_date)}"
    if day.resumed:
        text += f"\n{RESUME_NOTE}"
    return text


def _day_screen(supervisor_id: int, prefix: str) -> tuple[str, InlineKeyboardMarkup | None]:
    """Nazoratchi sana hisoblamaydi: faol ish kuni avtomatik. Yopilgan kun qayta ochilmaydi."""
    day = nazoratchi_day.active_day(supervisor_id, _now_company())
    if day.closed:
        return (
            f"📅 Ish kuni: {_display_date(day.work_date)}\n✅ Bu ish kuni yopilgan. Yangi ish kuni hali boshlanmagan.",
            None,
        )
    return (
        f"{_day_header(day)}\n\n🏬 Filialni tanlang:",
        _branch_picker_keyboard(prefix, day.work_date, supervisor_id),
    )


_STALE_ANSWER = "Bu tugma eskirgan."
_CLOSED_ANSWER = "Bu ish kuni yopilgan."


async def _guard_active_day(callback: CallbackQuery, review_date: str | None, *, allow_closed: bool = False) -> bool:
    """Eskirgan/kelajak/boshqa kun yoki yopilgan kun tugmalari hech narsa yozmaydi. ``allow_closed`` — faqat
    idempotent "allaqachon yopilgan" javobi uchun (yozuv yaratmaydi)."""
    reason = (
        "stale" if review_date is None
        else nazoratchi_day.check_active(callback.from_user.id, review_date, _now_company())
    )
    if reason is None or (reason == "closed" and allow_closed):
        return True
    await callback.answer(_CLOSED_ANSWER if reason == "closed" else _STALE_ANSWER, show_alert=True)
    return False


def _branch_screen(branch: str, review_date: str, supervisor_id: int, prefix: str = "") -> tuple[str, InlineKeyboardMarkup]:
    statuses = nazoratchi_day.branch_statuses(branch, review_date, exclude_user_id=supervisor_id)
    ymd = _ymd(review_date)
    index = _branch_index(branch)
    pending = sum(1 for item in statuses if item.status in nazoratchi_day.BLOCKING_STATUSES)
    head = f"{prefix}📅 Ish kuni: {_display_date(review_date)}\n🏬 Filial: {branch}\nBaholanmagan: {pending}"
    if not statuses:
        text = f"{head}\n\nHozircha bu filialda aktiv xodim mavjud emas."
    else:
        text = f"{head}\n\n" + "\n".join(item.line() for item in statuses)

    buttons = [
        InlineKeyboardButton(text=f"{item.emoji} {item.name}", callback_data=f"bos:emp:{item.profile['user_id']}:{ymd}")
        for item in statuses
    ]
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    rows.append([InlineKeyboardButton(text="✅ Filialni yopish", callback_data=f"bos:close:{index}:{ymd}")])
    rows.append([InlineKeyboardButton(text="⬅️ Filialni tanlash", callback_data="bos:today")])
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


def _employee_action_keyboard(employee_id: int, review_date: str, branch: str | None) -> InlineKeyboardMarkup:
    ymd = _ymd(review_date)
    index = _branch_index(branch) if branch else None
    rows = [
        [
            InlineKeyboardButton(
                text="Chala - 1", callback_data=f"bos:grade:{employee_id}:{discipline.GRADE_CHALA}:{ymd}"
            ),
            InlineKeyboardButton(
                text="Norma - 2", callback_data=f"bos:grade:{employee_id}:{discipline.GRADE_NORMA}:{ymd}"
            ),
            InlineKeyboardButton(
                text="A'lo - 3", callback_data=f"bos:grade:{employee_id}:{discipline.GRADE_ALO}:{ymd}"
            ),
        ],
        [InlineKeyboardButton(text="🚫 Ball ayirish (-10/-20/-30)", callback_data=f"bos:penalty_menu:{employee_id}")],
    ]
    if index is not None:
        rows.append([InlineKeyboardButton(text="⬅️ Filialga qaytish", callback_data=f"bos:br:{index}:{ymd}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _penalty_amount_keyboard(employee_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=f"-{amount}", callback_data=f"bos:pen:{employee_id}:{amount}")
                for amount in discipline.get_penalty_amounts()
            ]
        ]
    )


def _decision_keyboard(penalty_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Rozi (ball qaytariladi)", callback_data=f"bos:decide:{penalty_id}:{discipline.DECISION_APPROVED}"
                ),
                InlineKeyboardButton(
                    text="❌ Rad etish", callback_data=f"bos:decide:{penalty_id}:{discipline.DECISION_REJECTED}"
                ),
            ]
        ]
    )


# ------------------------------------------------- nizom o'qish auditi (UI) --

_RULE_LEARNING_WORKFLOW = "rule_learning"
_RULE_LEARNING_ALL_DONE = "✅ Barcha nizomlarni o'rganib bo'ldingiz."
_RULE_LEARNING_DAILY_DONE = (
    f"✅ Bugungi {rule_learning.DAILY_LIMIT} ta nizom tugadi. Ertaga davom etamiz."
)


def _rule_learning_key(employee_id: int, rule_number: int) -> str:
    return f"{employee_id}:{rule_number}"


def _rule_learning_text(progress: dict) -> str:
    return (
        f"📖 {progress['rule_number']}-nizom: {progress['title_snapshot']}\n\n"
        f"{progress['content_snapshot']}"
    )


def _rule_learning_read_keyboard(progress_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ O'qidim", callback_data=f"rl:read:{progress_id}"),
                InlineKeyboardButton(
                    text="📖 Hali o'qiyapman", callback_data=f"rl:reading:{progress_id}"
                ),
            ]
        ]
    )


def _rule_learning_understand_keyboard(progress_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Tushundim", callback_data=f"rl:ok:{progress_id}"),
                InlineKeyboardButton(text="❓ Tushunmadim", callback_data=f"rl:nu:{progress_id}"),
            ]
        ]
    )


def _rule_learning_reread_keyboard(progress_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📖 Qayta o'qiyman", callback_data=f"rl:reread:{progress_id}"
                ),
                InlineKeyboardButton(text="✅ Tushundim", callback_data=f"rl:ok:{progress_id}"),
            ]
        ]
    )


async def _send_rule_learning_card(bot, employee_id: int, progress: dict) -> None:
    sent = await bot.send_message(
        employee_id,
        _rule_learning_text(progress),
        reply_markup=_rule_learning_read_keyboard(progress["id"]),
    )
    rule_learning.mark_sent(progress["id"])
    chat_cleanup.track(
        _RULE_LEARNING_WORKFLOW, _rule_learning_key(employee_id, progress["rule_number"]), sent
    )


async def _send_next_rule_or_status(bot, employee_id: int) -> bool:
    """``False`` — ko'rsatadigan band ham, aytadigan holat ham yo'q
    (masalan aktiv nizom umuman kiritilmagan)."""
    progress = rule_learning.get_current_rule(employee_id)
    if progress is not None:
        await _send_rule_learning_card(bot, employee_id, progress)
        return True

    # ``get_current_rule`` aynan shu chaqiruvda auditni yakunlagan bo'lishi
    # mumkin, shuning uchun enrollment qayta o'qiladi.
    enrollment = rule_learning.get_enrollment(employee_id)
    if enrollment is not None and enrollment.get("finished_at"):
        await bot.send_message(employee_id, _RULE_LEARNING_ALL_DONE)
        return True

    if rule_learning.completed_today(employee_id) >= rule_learning.DAILY_LIMIT:
        await bot.send_message(employee_id, _RULE_LEARNING_DAILY_DONE)
        return True

    return False


async def start_or_resume_rule_learning(bot, employee_id: int) -> bool:
    """Yakunlanmagan nizom o'qish auditi bo'lsa xodimga keyingi BITTA
    bandni (yoki bugungi limit xabarini) yuboradi. ``False`` — audit yo'q,
    yakunlangan yoki ko'rsatadigan band yo'q; chaqiruvchi o'z odatiy
    oqimini davom ettiraveradi."""
    enrollment = rule_learning.get_enrollment(employee_id)
    if enrollment is None or enrollment.get("finished_at"):
        return False

    return await _send_next_rule_or_status(bot, employee_id)


def _rule_learning_owned_progress(callback: CallbackQuery) -> dict | None:
    if not callback.from_user:
        return None

    progress = rule_learning.get_progress(int(callback.data.split(":")[2]))
    if progress is None or progress["employee_id"] != callback.from_user.id:
        return None

    return progress


class CloseNoteStates(StatesGroup):
    waiting = State()


class PenaltyStates(StatesGroup):
    waiting_rule = State()


class AppealStates(StatesGroup):
    waiting_reason = State()


class SalaryStates(StatesGroup):
    waiting_amount = State()
    waiting_days = State()
    waiting_hours = State()
    waiting_date = State()


_SAL_CANCEL_ROW = [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="sal:cancel")]
_SAL_PROMPTS = {
    "amount": "💰 Fiks oylik summasini so'mda yozing (masalan: 4 000 000):",
    "days": "📅 Oy uchun kelishilgan ish kunlari sonini yozing (1 dan 31 gacha):",
    "hours": "🕒 Bir kun uchun kelishilgan ish soatini yozing (butun yoki yarim soat, masalan 12 yoki 12.5):",
    "date": "📌 Kelishuv qaysi sanadan amal qiladi? Sanani KK.OO.YYYY ko'rinishida yozing yoki \"Bugundan\"ni bosing:",
}
_SAL_STATE_BY_FIELD = {
    "amount": SalaryStates.waiting_amount,
    "days": SalaryStates.waiting_days,
    "hours": SalaryStates.waiting_hours,
    "date": SalaryStates.waiting_date,
}
_SAL_NEXT = {"amount": "days", "days": "hours", "hours": "date"}


def _sal_card_text(data: dict, saved: bool = False) -> str:
    today = company_time.today().isoformat()
    effective = data["sal_date"]
    lines = [
        "✅ Kelishuv saqlandi" if saved else "💵 Fiks kelishuvi — tekshiring",
        f"👤 {_employee_name(data['sal_emp'])}",
        f"🏬 {data['sal_branch']}",
        f"💰 Fiks summa: {salary_agreement.format_money(data['sal_amount'])}",
        f"📅 Oylik ish kunlari: {data['sal_days']} kun",
        f"🕒 Kunlik ish soati: {salary_agreement.format_minutes(data['sal_minutes'])}",
        f"📌 Amal qilish sanasi: {salary_agreement.format_date(effective)}",
    ]
    if effective > today:
        lines.append("ℹ️ Kelajakdagi sana: bu kelishuv hozirgi fiksni o'zgartirmaydi, sanasi kelganda amal qiladi.")
    elif effective < today:
        lines.append("ℹ️ O'tgan sana: avvalgi baho, bonus, davomat va hisoblar qayta yozilmaydi.")
    return "\n".join(lines)


def _sal_card_keyboard(token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Saqlash", callback_data=f"sal:save:{token}"),
                InlineKeyboardButton(text="✏️ O'zgartirish", callback_data="sal:edit"),
            ],
            _SAL_CANCEL_ROW,
        ]
    )


def _sal_complete(data: dict, need_token: bool = True) -> bool:
    keys = ("sal_emp", "sal_branch", "sal_amount", "sal_days", "sal_minutes", "sal_date") + (("sal_token",) if need_token else ())
    return all(data.get(key) is not None for key in keys)



_APPEAL_PROMPT = "✍️ Sababingizni matn yoki ovozli xabar sifatida yuboring."


async def begin_appeal(callback: CallbackQuery, state: FSMContext, penalty_id: int, *, notice: bool) -> None:
    """E'tiroz sababini so'rash. Faqat shu xodimning, hali e'tiroz berilmagan minusi uchun. ``notice=True`` — minus
    xabaridagi tugma: xabar va tugmalari e'tiroz yuborilgunga qadar saqlanadi, savol alohida xabar bo'ladi (yuborilgach
    eski savol o'chiriladi); aks holda ro'yxat xabari savolga aylanadi (tahrir)."""
    user_id = callback.from_user.id if callback.from_user else None
    penalty = discipline.get_penalty(penalty_id)
    if (
        penalty is not None and penalty["employee_id"] == user_id
        and penalty["appeal_status"] == discipline.APPEAL_PENDING and not penalty.get("appeal_delivered_at")
    ):
        # E'tiroz saqlangan, lekin Founderga yetmagan: sababni qayta yozdirmasdan qayta yuborish taklif qilinadi.
        await callback.answer()
        if callback.message is not None:
            try:
                await callback.message.answer(
                    "⚠️ E'tirozingiz saqlangan, lekin rahbarga yuborilmagan. \"Qayta yuborish\" tugmasini bosing.",
                    reply_markup=InlineKeyboardMarkup(
                        inline_keyboard=[[InlineKeyboardButton(text="🔁 Qayta yuborish", callback_data=f"bos:redeliver:{penalty_id}")]]
                    ),
                )
            except Exception as error:  # noqa: BLE001
                print(f"Qayta yuborish taklifini yuborib bo'lmadi: {error!r}")
        return
    if penalty is None or penalty["employee_id"] != user_id or penalty["appeal_status"] != discipline.APPEAL_NONE:
        await callback.answer("Bu minus uchun e'tiroz berib bo'lmaydi yoki allaqachon yuborilgan.", show_alert=True)
        if callback.message is not None:
            try:
                await callback.message.edit_reply_markup(reply_markup=None)
            except Exception as error:  # noqa: BLE001
                print(f"Eskirgan e'tiroz tugmasini olib bo'lmadi: {error!r}")
        return

    await state.update_data(appeal_penalty_id=penalty_id, appeal_notice_message_id=callback.message.message_id if notice and callback.message else None)
    await state.set_state(AppealStates.waiting_reason)
    await callback.answer()
    if callback.message is None:
        return
    key = dialog_cleanup.appeal_key(callback.message.chat.id, penalty_id)
    if notice:
        try:
            prompt = await callback.message.answer(_APPEAL_PROMPT)
        except Exception as error:  # noqa: BLE001
            print(f"E'tiroz savolini yuborib bo'lmadi: {error!r}")
            return
        await dialog_cleanup.sweep(callback.bot, key, keep=(prompt.chat.id, prompt.message_id))  # takroriy bosish: eski savol
        dialog_cleanup.track(key, prompt)
    else:
        try:
            await callback.message.edit_text(_APPEAL_PROMPT)
        except Exception as error:  # noqa: BLE001
            print(f"E'tiroz savolini tahrirlab bo'lmadi: {error!r}")
            return
        dialog_cleanup.track(key, callback.message)


def _today_board_text() -> str:
    today = _today()
    board = discipline.get_daily_leaderboard(today.isoformat())
    return _format_board(f"🏆 Bugungi Poyga — {today.strftime('%d.%m.%Y')}", board, "grade_points")


def _month_board_text(user_id: int) -> str:
    today = _today()
    board = discipline.get_monthly_leaderboard(today.strftime("%Y-%m"))
    text = _format_board(f"🏆 Oylik Turnir — {today.strftime('%Y-%m')}", board, "net_score")
    if permissions.has_permission(user_id, permissions.ACTION_MANAGE_DISCIPLINE_RULES):
        work_date = date.fromisoformat(nazoratchi_day.current_work_date(company_time.now()))
        first = work_date.replace(day=1)
        if work_date == first:
            end = first
            first = (first - timedelta(days=1)).replace(day=1)
            month_names = ("Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun",
                           "Iyul", "Avgust", "Sentabr", "Oktabr", "Noyabr", "Dekabr")
            label = month_names[first.month - 1] + ": "
        else:
            end = work_date
            label = ""
        days = (end - first).days
        graded = discipline.count_graded_dates(first.isoformat(), end.isoformat())
        text += f"\n\n{label}Nazoratchi {days} kundan {graded} kunini baholadi"
    return text


def discipline_repo_note_exists(supervisor_id: int, work_date: str, branch: str) -> bool:
    from repositories import discipline as discipline_repo
    return (work_date < discipline_repo.strict_close_start() or
            discipline_repo.get_day_close_note(supervisor_id, work_date, branch) is not None)


def register(dp: Dispatcher, openai_client) -> None:

    # ------------------------------------------------------- /baholash --

    @dp.message(Command("baholash"))
    async def baholash_start(message: Message) -> None:
        if not await permissions.ensure_permission(message, permissions.ACTION_EVALUATE_EMPLOYEE):
            return

        text, keyboard = _day_screen(message.from_user.id, "bos:br")
        await message.answer(text, reply_markup=keyboard)

    @dp.callback_query(F.data == "bos:today")
    async def baholash_today(callback: CallbackQuery) -> None:
        if not await permissions.ensure_permission(callback, permissions.ACTION_EVALUATE_EMPLOYEE):
            return

        text, keyboard = _day_screen(callback.from_user.id, "bos:br")
        await callback.message.edit_text(text, reply_markup=keyboard)
        await callback.answer()

    @dp.callback_query(F.data.startswith("bos:br:"))
    async def baholash_pick_branch(callback: CallbackQuery) -> None:
        if not await permissions.ensure_permission(callback, permissions.ACTION_EVALUATE_EMPLOYEE):
            return

        _, _, index_str, ymd = callback.data.split(":")
        review_date = _iso_from_ymd(ymd)
        index = int(index_str)
        if review_date is None or not 0 <= index < len(RECRUITING_BRANCH_NAMES):
            await callback.answer("Filial topilmadi.", show_alert=True)
            return

        if not await _guard_active_day(callback, review_date):
            return

        branch = RECRUITING_BRANCH_NAMES[index]
        session = nazoratchi_day.open_session(callback.from_user.id, branch, review_date)
        if session["status"] == "closed":
            await callback.message.edit_text(
                f"📅 Ish kuni: {_display_date(review_date)}\n🏬 Filial: {branch}\n✅ Bu filial shu ish kunida yopilgan.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="⬅️ Filialni tanlash", callback_data="bos:today")
                ]]),
            )
            await callback.answer()
            return
        text, keyboard = _branch_screen(branch, review_date, callback.from_user.id)
        if (day := nazoratchi_day.active_day(callback.from_user.id, _now_company())).resumed:
            text = f"{RESUME_NOTE}\n\n{text}"
        await callback.message.edit_text(text, reply_markup=keyboard)
        await callback.answer()

    @dp.callback_query(F.data.startswith("bos:emp:"))
    async def baholash_pick_employee(callback: CallbackQuery) -> None:
        if not await permissions.ensure_permission(callback, permissions.ACTION_EVALUATE_EMPLOYEE):
            return

        parts = callback.data.split(":")
        employee_id = int(parts[2])
        review_date = _iso_from_ymd(parts[3]) if len(parts) > 3 else None
        if not await _guard_active_day(callback, review_date):
            return
        profile = employees.get_profile(employee_id)
        name = _employee_name(employee_id)
        branch = profile.get("branch") if profile else None

        lines = [f"👤 {name}"]
        if profile is not None:
            lines.append(nazoratchi_day.employee_status(profile, review_date).line())
        history = discipline.get_grade_history(employee_id, review_date)
        if history:
            lines.append("")
            lines.append("📜 Bugungi baholar:")
            lines += [
                f"• {discipline.GRADE_LABELS.get(row['grade_key'], row['grade_key'])} ({row['grade_points']} ball)"
                for row in history
            ]
        lines += ["", "Baho tanlang yoki ball ayirish kiriting:"]
        await callback.message.edit_text(
            "\n".join(lines), reply_markup=_employee_action_keyboard(employee_id, review_date, branch)
        )
        await callback.answer()

    @dp.callback_query(F.data.startswith("bos:grade:"))
    async def baholash_pick_grade(callback: CallbackQuery) -> None:
        if not await permissions.ensure_permission(callback, permissions.ACTION_EVALUATE_EMPLOYEE):
            return

        parts = callback.data.split(":")
        employee_id = int(parts[2])
        grade_key = parts[3]
        review_date = _iso_from_ymd(parts[4]) if len(parts) > 4 else None
        discipline.log_grade_event(employee_id, review_date, "bos_request", "received")
        if not await _guard_active_day(callback, review_date):
            discipline.log_grade_event(employee_id, review_date, "bos_guard", "inactive_day")
            return
        prepared = discipline.prepare_and_record_grade(
            employee_id, callback.from_user.id, review_date, grade_key
        )
        if prepared.error:
            await callback.answer(prepared.error, show_alert=True)
            return
        result = prepared.result
        try:
            outcome = await discipline.notify_employee_of_grade(callback.bot, employee_id, result)
            if outcome == discipline.NOTICE_UNCHANGED:
                await callback.answer(discipline.grade_notice_reply(outcome))
                return

            name = _employee_name(employee_id)
            label = discipline.GRADE_LABELS[grade_key]
            confirmation = (
                f"✅ {name} — {label} ({result.grade_points} ball) qayd etildi.\n"
                f"💰 Bonus banki: {result.bonus_bank_balance} ball"
            )
            profile = employees.get_profile(employee_id)
            branch = profile.get("branch") if profile else None
            if branch and _branch_index(branch) is not None:
                text, keyboard = _branch_screen(branch, review_date, callback.from_user.id, prefix=confirmation + "\n\n")
                await callback.message.edit_text(text, reply_markup=keyboard)
            else:
                await callback.message.edit_text(confirmation)
            await callback.answer(discipline.grade_notice_reply(outcome))
        except Exception as error:
            discipline.log_grade_event(employee_id, review_date, "handler_after_save", "failed", type(error).__name__)
            raise

    @dp.callback_query(F.data.startswith("bos:penalty_menu:"))
    async def baholash_penalty_menu(callback: CallbackQuery) -> None:
        if not await permissions.ensure_permission(callback, permissions.ACTION_EVALUATE_EMPLOYEE):
            return

        employee_id = int(callback.data.split(":")[2])
        name = _employee_name(employee_id)
        await callback.message.edit_text(
            f"🚫 {name} uchun ball ayirish miqdorini tanlang:",
            reply_markup=_penalty_amount_keyboard(employee_id),
        )
        await callback.answer()

    @dp.callback_query(F.data.startswith("bos:pen:"))
    async def baholash_pick_penalty(callback: CallbackQuery, state: FSMContext) -> None:
        if not await permissions.ensure_permission(callback, permissions.ACTION_EVALUATE_EMPLOYEE):
            return

        _, _, employee_id_str, amount_str = callback.data.split(":")
        await state.update_data(penalty_employee_id=int(employee_id_str), penalty_amount=int(amount_str))
        await state.set_state(PenaltyStates.waiting_rule)
        await callback.message.edit_text(
            "📖 Qaysi nizom bo'yicha? Nizom raqamini kiriting (masalan: \"3-nizom\")."
        )
        await callback.answer()

    @dp.message(StateFilter(PenaltyStates.waiting_rule))
    async def baholash_enter_rule(message: Message, state: FSMContext) -> None:
        if not message.from_user:
            return

        nazoratchi_id = message.from_user.id
        # Atomic band qilish: awaitdan OLDIN, sinxron tekshir+qo'sh — shu
        # nazoratchidan deyarli bir vaqtda kelgan ikkinchi xabar (masalan
        # ikki marta yuborilgan) AI tasdig'ini qayta kutmasdan, jarimani
        # ikkinchi marta qo'llamasdan darhol chiqib ketadi (qarang
        # ``_PENDING_PENALTY_APPLICATIONS`` izohi).
        if nazoratchi_id in _PENDING_PENALTY_APPLICATIONS:
            return
        _PENDING_PENALTY_APPLICATIONS.add(nazoratchi_id)

        try:
            text = (message.text or "").strip()
            rule_number = discipline.extract_rule_number(text)
            if rule_number is None:
                await message.answer("❌ Nizom raqamini aniqlay olmadim. Masalan: \"3-nizom\" deb yozing.")
                return

            rule = discipline.get_rule(rule_number)
            if rule is not None and rule.get("catalog_kind") is not None:
                await message.answer(
                    "ℹ️ Bu band nizom katalogidan — ball variantlari bor. Nazoratchi kartasidan "
                    "\"Ball ayirish\" orqali variantni tanlab tasdiqlang."
                )
                await state.clear()
                return
            if rule is None:
                await message.answer(
                    f"❌ {rule_number}-nizom bazada topilmadi. Boshqa raqam kiriting yoki "
                    "Asoschidan /addnizom orqali qo'shishini so'rang."
                )
                return

            data = await state.get_data()
            employee_id = data["penalty_employee_id"]
            amount = data["penalty_amount"]
            await state.clear()

            waiting = await message.answer("⏳ AI nizomni tasdiqlayapti...")
            ai_note = await discipline_ai.confirm_rule_match(openai_client, text, rule)

            result = discipline.apply_penalty(
                employee_id,
                nazoratchi_id,
                _today().isoformat(),
                amount,
                rule_number,
                comment=text,
                ai_note=ai_note,
            )

            rule_learning_context, rule_learning_line = _rule_learning_status(result["penalty_id"])

            name = _employee_name(employee_id)
            await waiting.edit_text(
                f"{ai_note}\n\n"
                f"🚫 {name} uchun -{amount} ball ayirildi ({rule_number}-nizom).\n"
                f"💰 Bonus banki: {result['bonus_bank_balance']} ball\n"
                "ℹ️ Fiks oylikka ta'sir qilmaydi."
                f"{rule_learning_line}"
            )

            try:
                await message.bot.send_message(
                    employee_id,
                    f"⚠️ Sizga -{amount} ball ayirildi ({rule_number}-nizom: {rule['title']}).\n"
                    "Rozi bo'lmasangiz /apellyatsiya buyrug'i orqali e'tiroz bildiring."
                    f"{rule_learning_line}",
                )
            except Exception as error:
                print(f"Xodimga jarima xabarini yuborib bo'lmadi ({employee_id}): {error!r}")

            if (
                rule_learning_context is not None
                and rule_learning_context["status"] == "understood_before_penalty"
                and nazoratchi_id != FOUNDER_ID
            ):
                founder_text = (
                    f"🚨 Nizom buzilishi\nXodim: {name}\nNizom: {rule_number} — {rule['title']}\n"
                    f"Ball: -{amount}\n📚 Xodim bu nizomni oldin tushunganini tasdiqlagan."
                )
                try:
                    await message.bot.send_message(FOUNDER_ID, founder_text)
                except Exception as error:
                    print(
                        f"Founderga nizom buzilishi ogohlantirishini yuborib bo'lmadi "
                        f"(penalty_id={result['penalty_id']}): {error!r}"
                    )
        finally:
            _PENDING_PENALTY_APPLICATIONS.discard(nazoratchi_id)

    # ------------------------------------------------------- /kunniyop --

    @dp.message(Command("kunniyop"))
    async def close_day_handler(message: Message) -> None:
        if not await permissions.ensure_permission(message, permissions.ACTION_CLOSE_DAY):
            return

        text, keyboard = _day_screen(message.from_user.id, "bos:close")
        if keyboard is not None:
            text = text.replace("🏬 Filialni tanlang:", "✅ Qaysi filial nazoratini yopamiz?")
        await message.answer(text, reply_markup=keyboard)

    @dp.callback_query(F.data.startswith("bos:close:"))
    async def close_branch_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not await permissions.ensure_permission(callback, permissions.ACTION_CLOSE_DAY):
            return

        _, _, index_str, ymd = callback.data.split(":")
        review_date = _iso_from_ymd(ymd)
        index = int(index_str) if index_str.isdigit() else -1
        if review_date is None or not 0 <= index < len(RECRUITING_BRANCH_NAMES):
            await callback.answer("Filial topilmadi.", show_alert=True)
            return

        if not await _guard_active_day(callback, review_date, allow_closed=True):
            return

        branch = RECRUITING_BRANCH_NAMES[index]
        pending = nazoratchi_day.branch_pending_count(branch, review_date, callback.from_user.id)
        if pending and not discipline_repo_note_exists(
            callback.from_user.id, review_date, branch
        ):
            await state.set_state(CloseNoteStates.waiting)
            await state.update_data(close_branch=branch, close_date=review_date)
            await callback.message.answer(
                f"✍️ {branch}: {pending} xodim baholanmagan. "
                "Filialni yopish uchun kamida 5 belgili izoh yozing."
            )
            await callback.answer()
            return
        result = nazoratchi_day.close_session(callback.from_user.id, branch, review_date)

        if result.already_closed:
            await callback.message.edit_text(
                f"📅 Ish kuni: {_display_date(review_date)}\nℹ️ {branch} nazorati allaqachon yopilgan."
            )
        elif result.blockers:
            await callback.message.edit_text(
                f"📅 Ish kuni: {_display_date(review_date)}\n🏬 Filial: {branch}\n"
                + nazoratchi_day.blockers_text(result.blockers),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="📋 Filialga qaytish", callback_data=f"bos:br:{index}:{ymd}"),
                ]]),
            )
        else:
            statuses = nazoratchi_day.branch_statuses(branch, review_date, exclude_user_id=callback.from_user.id, closed=True)
            chunks = close_report.build_close_report(branch, review_date, statuses, result.evaluated, result.total)
            day_closed = nazoratchi_day.day_fully_closed(callback.from_user.id, review_date)
            footer = (
                f"\n\n✅ {_display_date(review_date)} ish kuni yopildi." if day_closed
                else "\n\nIsh kuni hali yopilmadi: boshqa filiallar ham tekshirilishi kerak."
            )
            next_kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text="➡️ Keyingi ish kuni" if day_closed else "🏬 Boshqa filial", callback_data="bos:today"
                )
            ]])
            if len(chunks) == 1:
                await callback.message.edit_text(chunks[0] + footer, reply_markup=next_kb)
            else:
                await callback.message.edit_text(chunks[0])
                for chunk in chunks[1:-1]:
                    await callback.message.answer(chunk)
                await callback.message.answer(chunks[-1] + footer, reply_markup=next_kb)
        await callback.answer()

    @dp.message(StateFilter(CloseNoteStates.waiting))
    async def close_note_reply(message: Message, state: FSMContext) -> None:
        if not await permissions.ensure_permission(message, permissions.ACTION_CLOSE_DAY):
            await state.clear()
            return
        note = (message.text or "").strip()
        if len(note) < 5:
            await message.answer("Izoh kamida 5 belgi bo'lsin.")
            return
        data = await state.get_data()
        branch, review_date = data.get("close_branch"), data.get("close_date")
        if branch not in RECRUITING_BRANCH_NAMES or not review_date:
            await state.clear()
            return
        if nazoratchi_day.check_active(message.from_user.id, review_date, _now_company()):
            await state.clear()
            await message.answer("Bu ish kuni yopilgan yoki eskirgan.")
            return
        result = nazoratchi_day.close_session(message.from_user.id, branch, review_date, note=note)
        await state.clear()
        await message.answer(
            f"✅ {branch} nazorati yopildi. Izoh saqlandi." if result.closed
            else "ℹ️ Filial allaqachon yopilgan." if result.already_closed
            else nazoratchi_day.blockers_text(result.blockers)
        )

    # ------------------------------------------------------- dashboardlar --

    @dp.message(Command("bugungiporga"))
    async def today_board_handler(message: Message) -> None:
        if not message.from_user or not is_authorized(message.from_user.id):
            return
        await message.answer(_today_board_text())

    @dp.message(Command("oylikturnir"))
    async def month_board_handler(message: Message) -> None:
        if not message.from_user or not is_authorized(message.from_user.id):
            return
        await message.answer(_month_board_text(message.from_user.id))

    @dp.callback_query(F.data.startswith("frep:"))
    async def founder_report_callback(callback: CallbackQuery) -> None:
        if not await permissions.ensure_permission(callback, permissions.ACTION_MANAGE_DISCIPLINE_RULES):
            return
        if callback.data == "frep:month":
            text = _month_board_text(callback.from_user.id)
        elif callback.data == "frep:today":
            text = _today_board_text()
        else:
            await callback.answer("Bu tugma eskirgan.", show_alert=True)
            return
        await callback.message.answer(text)
        await callback.answer()

    async def _send_legacy_close_preview(target: Message, user_id: int) -> None:
        if target.chat.type != "private":
            await target.answer("Bu amalni botning shaxsiy chatida oching.")
            return
        key = (user_id, target.chat.id)
        _LEGACY_CLOSE_PREVIEWS.pop(key, None)
        try:
            preview = await asyncio.to_thread(nazoratchi_day.preview_legacy_close, _now_company())
        except ValueError as error:
            await target.answer(str(error))
            return
        if not preview["rows"]:
            await target.answer("Yopilmagan eski kunlar yo'q.")
            return
        # A short one-use token is kept only in memory: preview does not write to DB/FSM.
        token = secrets.token_hex(8)
        pairs = sorted({(row["session_date"], row["branch"]) for row in preview["rows"]})
        text = "🔎 Eski kunlarni yopish ko'rigi (hech narsa yozilmadi):\n" + "\n".join(
            f"• {_display_date(day)} — {branch}" for day, branch in pairs
        )
        text += "\n\nBaholar va tarix saqlanadi. Baholanmaganlarga baho yoki minus yozilmaydi."
        # Chunk without losing any reviewed date/branch; confirmation stays on the final chunk.
        lines, chunks, current = text.splitlines(), [], ""
        for line in lines:
            if len(current) + len(line) + 1 > 3500:
                chunks.append(current)
                current = ""
            current += ("\n" if current else "") + line
        chunks.append(current)
        for chunk in chunks[:-1]:
            await target.answer(chunk)
        sent = await target.answer(chunks[-1], reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Eski kunlarni yopish", callback_data=f"bos:legacy_close:{token}")
        ]]))
        _LEGACY_CLOSE_PREVIEWS[key] = {"token": token, "version": preview["version"], "message_id": sent.message_id}


    @dp.message(Command("eskikunlarniyop"))
    async def legacy_day_close_preview(message: Message) -> None:
        if not await permissions.ensure_permission(message, permissions.ACTION_MANAGE_DISCIPLINE_RULES):
            return
        await _send_legacy_close_preview(message, message.from_user.id)

    @dp.callback_query(F.data == "fset:legacy")
    async def legacy_settings_callback(callback: CallbackQuery) -> None:
        if not await permissions.ensure_permission(callback, permissions.ACTION_MANAGE_DISCIPLINE_RULES):
            return
        await _send_legacy_close_preview(callback.message, callback.from_user.id)
        await callback.answer()

    @dp.callback_query(F.data.startswith("bos:legacy_close:"))
    async def legacy_day_close_confirm(callback: CallbackQuery) -> None:
        if not await permissions.ensure_permission(callback, permissions.ACTION_MANAGE_DISCIPLINE_RULES):
            return
        if callback.message is None or callback.message.chat.type != "private":
            await callback.answer("Shaxsiy chatda qayta oching.", show_alert=True)
            return
        key = (callback.from_user.id, callback.message.chat.id)
        preview = _LEGACY_CLOSE_PREVIEWS.get(key)
        token = callback.data.split(":", 2)[2]
        if (not preview or not secrets.compare_digest(token, preview["token"])
                or callback.message.message_id != preview["message_id"]):
            await callback.answer("Ko'rik eskirgan. /eskikunlarniyop orqali qayta oching.", show_alert=True)
            return
        _LEGACY_CLOSE_PREVIEWS.pop(key)
        await callback.answer()
        try:
            result = await asyncio.to_thread(nazoratchi_day.confirm_legacy_close, _now_company(), preview["version"])
        except ValueError as error:
            await callback.message.edit_text(str(error), reply_markup=None)
            return
        await callback.message.edit_text(
            f"✅ Eski kunlar yopildi: {result['days']} kun, {result['sessions']} filial sessiyasi.\nTarix saqlandi.",
            reply_markup=None,
        )

    # ------------------------------------------------------- nizom/maosh --

    @dp.message(Command("addnizom"))
    async def add_rule_handler(message: Message) -> None:
        if not await permissions.ensure_permission(message, permissions.ACTION_MANAGE_DISCIPLINE_RULES):
            return

        parts = (message.text or "").split(maxsplit=2)
        if len(parts) < 3 or not parts[1].isdigit():
            await message.answer(
                "Foydalanish: /addnizom <raqam> <sarlavha> | <matn>\n"
                "Masalan: /addnizom 3 Ishga kech qolish | Ish boshlanishidan 15 daqiqadan "
                "ko'p kechikish."
            )
            return

        rule_number = int(parts[1])
        rest = parts[2]
        if "|" in rest:
            title, content = (part.strip() for part in rest.split("|", 1))
        else:
            title = content = rest.strip()

        if discipline.add_rule(rule_number, title, content, message.from_user.id):
            await message.answer(f"✅ {rule_number}-nizom qo'shildi: {title}")
        else:
            await message.answer(f"❌ {rule_number}-nizom raqami allaqachon band.")

    @dp.message(Command("setnizombahosi"))
    async def set_rule_amount_handler(message: Message) -> None:
        """Nazoratchi kartasidagi "➖ Ball ayirish" tugma ro'yxatida faqat
        shu buyruq orqali miqdor belgilangan nizom bandlari ko'rinadi —
        yangi nizom standart holatda bu ro'yxatda YO'Q (qarang
        ``repositories/discipline.py::list_rules_with_penalty_amount``)."""
        if not await permissions.ensure_permission(message, permissions.ACTION_MANAGE_DISCIPLINE_RULES):
            return

        parts = (message.text or "").split()
        if len(parts) != 3 or not parts[1].isdigit() or not parts[2].isdigit():
            await message.answer(
                "Foydalanish: /setnizombahosi <nizom raqami> <ball miqdori>\n"
                "Masalan: /setnizombahosi 3 30"
            )
            return

        rule_number = int(parts[1])
        amount = int(parts[2])
        if discipline.set_rule_penalty_amount(rule_number, amount, message.from_user.id):
            await message.answer(f"✅ {rule_number}-nizom uchun standart ball: -{amount}.")
        else:
            await message.answer(f"❌ {rule_number}-nizom topilmadi.")

    async def _send_rule_list(target: Message, user_id: int) -> None:
        if await start_or_resume_rule_learning(target.bot, user_id):
            return

        rules = discipline.list_rules()
        if not rules:
            await target.answer("Hali nizomlar kiritilmagan.")
            return

        lines = [f"{rule['rule_number']}. {rule['title']} — {rule['content']}" for rule in rules]
        text = "📖 Korxona nizomlari:\n\n" + "\n".join(lines)
        if all(rule.get("catalog_kind") is None for rule in rules) and len(text) <= _LISTNIZOM_SINGLE_LIMIT:
            await target.answer(text)
            return
        screen_text, screen_markup = _catalog_sources_screen()
        await target.answer(screen_text, reply_markup=screen_markup)


    @dp.message(Command("listnizom"))
    async def list_rules_handler(message: Message) -> None:
        if not message.from_user or not is_authorized(message.from_user.id):
            return
        await _send_rule_list(message, message.from_user.id)

    @dp.callback_query(F.data == "fset:nizom")
    async def rules_settings_callback(callback: CallbackQuery) -> None:
        if not await permissions.ensure_permission(callback, permissions.ACTION_MANAGE_DISCIPLINE_RULES):
            return
        await _send_rule_list(callback.message, callback.from_user.id)
        await callback.answer()

    def _item_label(entry: dict) -> str:
        title = entry["title"]
        if entry.get("catalog_kind") == "culture":
            title = next((line for line in entry["content"].split("\n") if line.strip()), title)
        prefix = f"№{entry['display_number']} " if entry.get("display_number") else ""
        return (prefix + title)[:56]

    def _catalog_sources_screen() -> tuple[str, InlineKeyboardMarkup]:
        entries = discipline.get_catalog_entries(candidates_only=False)
        rows = [
            [InlineKeyboardButton(text=f"{source['name']} ({source['count']})"[:60], callback_data=f"nzl:l:{source['section']}:0")]
            for source in discipline.list_catalog_sources(entries)
        ]
        return "📖 Korxona nizomlari — manbani tanlang:", InlineKeyboardMarkup(inline_keyboard=rows)

    @dp.callback_query(F.data.startswith("nzl:"))
    async def catalog_reading_handler(callback: CallbackQuery) -> None:
        if not callback.from_user or not is_authorized(callback.from_user.id) or callback.message is None:
            await callback.answer()
            return
        parts = callback.data.split(":")
        entries = discipline.get_catalog_entries(candidates_only=False)
        try:
            if parts[1] == "s":
                text, markup = _catalog_sources_screen()
            elif parts[1] == "l":
                section, page = parts[2], max(0, int(parts[3]))
                items = discipline.entries_in_section(section, entries)
                pages = max(1, -(-len(items) // _LISTNIZOM_PAGE_SIZE))
                page = min(page, pages - 1)
                chunk = items[page * _LISTNIZOM_PAGE_SIZE:(page + 1) * _LISTNIZOM_PAGE_SIZE]
                rows = [[InlineKeyboardButton(text=_item_label(entry), callback_data=f"nzl:i:{entry['rule_number']}:0")] for entry in chunk]
                nav = []
                if page > 0:
                    nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"nzl:l:{section}:{page - 1}"))
                if page < pages - 1:
                    nav.append(InlineKeyboardButton(text="➡️", callback_data=f"nzl:l:{section}:{page + 1}"))
                if nav:
                    rows.append(nav)
                rows.append([InlineKeyboardButton(text="📚 Manbalar", callback_data="nzl:s")])
                text = f"📖 {items[0]['source_name'] if items else section} — {page + 1}/{pages}"
                markup = InlineKeyboardMarkup(inline_keyboard=rows)
            elif parts[1] == "i":
                entry = next((item for item in entries if item["rule_number"] == int(parts[2])), None)
                if entry is None:
                    await callback.answer("Band topilmadi.", show_alert=True)
                    return
                body = [entry["title"]]
                if entry.get("display_number"):
                    body.append(f"Rasmiy raqam: {entry['display_number']}")
                body += ["", entry["content"]]
                if entry["options"]:
                    body += ["", "Ball variantlari (manbadan):"] + [f"−{option['points']}: {option['condition_text']}" for option in entry["options"]]
                elif entry["amount_status"] == "default":
                    body += ["", discipline.entry_amount_text(entry)]
                pages = discipline.split_text_pages("\n".join(body))
                page = min(max(0, int(parts[3])), len(pages) - 1)
                section = entry["section"]
                nav = []
                if page > 0:
                    nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"nzl:i:{entry['rule_number']}:{page - 1}"))
                if page < len(pages) - 1:
                    nav.append(InlineKeyboardButton(text="➡️", callback_data=f"nzl:i:{entry['rule_number']}:{page + 1}"))
                rows = [nav] if nav else []
                rows.append([InlineKeyboardButton(text="⬅️ Ro'yxat", callback_data=f"nzl:l:{section}:0")])
                text = (f"({page + 1}/{len(pages)})\n" if len(pages) > 1 else "") + pages[page]
                markup = InlineKeyboardMarkup(inline_keyboard=rows)
            else:
                await callback.answer()
                return
        except (IndexError, ValueError):
            await callback.answer()
            return
        await callback.message.edit_text(text, reply_markup=markup)
        await callback.answer()

    def _import_report(result: dict, *, applied: bool) -> str:
        lines = [
            "✅ Import bajarildi." if applied else "🔎 Import ko'rigi (hech narsa yozilmagan).",
            f"Versiya: {result['version']}",
            f"Bandlar: yangi {result['rules_inserted']}, mavjud-moslangan {result['rules_adopted']}, o'zgarishsiz {result['rules_unchanged']}",
            f"Variantlar: yangi {result['options_inserted']}, o'zgarishsiz {result['options_unchanged']}",
            f"Aniqlanmagan (ball avtomatik qo'llanmaydi): {result['unresolved']}",
        ]
        if result["conflicts"]:
            lines.append(f"⛔ Konfliktlar ({len(result['conflicts'])}) — import bajarilmaydi, mavjud matn ustidan yozilmaydi:")
            lines += [f"• {item}" for item in result["conflicts"][:15]]
        return "\n".join(lines)

    @dp.message(Command("nizomimport"))
    async def catalog_import_preview(message: Message) -> None:
        if not await permissions.ensure_permission(message, permissions.ACTION_MANAGE_DISCIPLINE_RULES):
            return
        try:
            result = await asyncio.to_thread(discipline_import.run_import, apply=False, created_by=message.from_user.id)
        except discipline_import.ImportBlocked as error:
            await message.answer(f"⛔ Import bloklandi: {error}")
            return
        markup = None
        if not result["conflicts"]:
            markup = InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="✅ Importni qo'llash", callback_data=f"rimp:{result['version']}")]]
            )
        await message.answer(_import_report(result, applied=False), reply_markup=markup)

    @dp.callback_query(F.data.startswith("rimp:"))
    async def catalog_import_apply(callback: CallbackQuery) -> None:
        if not await permissions.ensure_permission(callback, permissions.ACTION_MANAGE_DISCIPLINE_RULES):
            return
        actor_id = callback.from_user.id
        if actor_id in _PENDING_CATALOG_IMPORTS:
            await callback.answer()
            return
        _PENDING_CATALOG_IMPORTS.add(actor_id)
        try:
            try:
                await callback.answer("Import tekshirilmoqda…")
            except TelegramBadRequest as error:
                if "query is too old" not in error.message.lower():
                    raise
                logger.warning("Nizom importi: callback javob muddati o'tgan; natija xabarda ko'rsatiladi")
            try:
                result = await asyncio.to_thread(
                    discipline_import.run_import,
                    apply=True, created_by=actor_id, expected_version=callback.data.split(":", 1)[1]
                )
            except discipline_import.ImportBlocked as error:
                if callback.message:
                    await callback.message.edit_text(f"⛔ Import bloklandi: {error}", reply_markup=None)
                return
            if callback.message:
                await callback.message.edit_text(_import_report(result, applied=result["applied"]), reply_markup=None)
        finally:
            _PENDING_CATALOG_IMPORTS.discard(actor_id)

    @dp.callback_query(F.data.startswith("rl:reading:"))
    async def rule_learning_still_reading(callback: CallbackQuery) -> None:
        await callback.answer("Yaxshi, o'qib bo'lgach \"✅ O'qidim\" tugmasini bosing.")

    @dp.callback_query(F.data.startswith("rl:read:"))
    async def rule_learning_read(callback: CallbackQuery) -> None:
        progress = _rule_learning_owned_progress(callback)
        if progress is None:
            await callback.answer("Bu tugma siz uchun emas.", show_alert=True)
            return

        rule_learning.confirm_read(progress["id"])
        await callback.message.edit_text(
            _rule_learning_text(progress),
            reply_markup=_rule_learning_understand_keyboard(progress["id"]),
        )
        await callback.answer()

    @dp.callback_query(F.data.startswith("rl:nu:"))
    async def rule_learning_not_understood(callback: CallbackQuery) -> None:
        progress = _rule_learning_owned_progress(callback)
        if progress is None:
            await callback.answer("Bu tugma siz uchun emas.", show_alert=True)
            return

        rule_learning.report_not_understood(progress["id"])
        await callback.message.edit_text(
            _rule_learning_text(progress),
            reply_markup=_rule_learning_reread_keyboard(progress["id"]),
        )
        await callback.answer()

    @dp.callback_query(F.data.startswith("rl:reread:"))
    async def rule_learning_reread(callback: CallbackQuery) -> None:
        progress = _rule_learning_owned_progress(callback)
        if progress is None:
            await callback.answer("Bu tugma siz uchun emas.", show_alert=True)
            return

        await callback.message.edit_text(
            _rule_learning_text(progress),
            reply_markup=_rule_learning_understand_keyboard(progress["id"]),
        )
        await callback.answer()

    @dp.callback_query(F.data.startswith("rl:ok:"))
    async def rule_learning_understood(callback: CallbackQuery) -> None:
        progress = _rule_learning_owned_progress(callback)
        if progress is None:
            await callback.answer("Bu tugma siz uchun emas.", show_alert=True)
            return

        employee_id = progress["employee_id"]
        if not rule_learning.confirm_understood(employee_id, progress["id"]):
            await callback.answer()
            return

        await callback.answer()

        try:
            await chat_cleanup.cleanup(
                callback.bot,
                _RULE_LEARNING_WORKFLOW,
                _rule_learning_key(employee_id, progress["rule_number"]),
            )
        except Exception as error:  # noqa: BLE001
            logger.error("Nizom xabarlarini tozalab bo'lmadi: %r", error)

        await _send_next_rule_or_status(callback.bot, employee_id)

    # ----------------------------------------------- fiks oylik kelishuvi (Founder) --

    async def _sal_allowed(event) -> bool:
        """Har yozish/ko'rsatish qadamida server ruxsati qayta tekshiriladi; faqat shaxsiy chat."""
        chat = event.message.chat if isinstance(event, CallbackQuery) else event.chat
        if event.from_user is None or chat.type != "private":
            if isinstance(event, CallbackQuery):
                await event.answer("Bu amal faqat shaxsiy chatda.", show_alert=True)
            return False
        return await permissions.ensure_permission(event, permissions.ACTION_SET_SALARY)

    async def _sal_show_card(target, state: FSMContext, *, edit: bool) -> None:
        import secrets

        # Har yakuniy karta YANGI Saqlash tokeni oladi: oldingi kartalarning tugmalari yaroqsiz bo'ladi.
        token = secrets.token_hex(8)
        await state.update_data(sal_token=token, sal_edit=False)
        data = await state.get_data()
        text, keyboard = _sal_card_text(data), _sal_card_keyboard(token)
        await state.set_state(None)
        if edit:
            await target.message.edit_text(text, reply_markup=keyboard)
        else:
            await target.answer(text, reply_markup=keyboard)

    async def _sal_ask(target, state: FSMContext, field: str, *, edit: bool) -> None:
        await state.set_state(_SAL_STATE_BY_FIELD[field])
        rows = [_SAL_CANCEL_ROW]
        if field == "date":
            rows = [[InlineKeyboardButton(text="📅 Bugundan", callback_data="sal:today")], _SAL_CANCEL_ROW]
        markup = InlineKeyboardMarkup(inline_keyboard=rows)
        if edit:
            await target.message.edit_text(_SAL_PROMPTS[field], reply_markup=markup)
        else:
            await target.answer(_SAL_PROMPTS[field], reply_markup=markup)

    @dp.message(Command("setsalary"))
    async def set_salary_handler(message: Message, state: FSMContext) -> None:
        if not await _sal_allowed(message):
            return

        parts = (message.text or "").split()
        if len(parts) == 1:  # sodda oqim: filial -> xodim -> summa -> kunlar -> soat -> sana -> karta
            await state.clear()
            rows = [
                [InlineKeyboardButton(text=f"📍 {name}", callback_data=f"sal:br:{index}")]
                for index, name in enumerate(RECRUITING_BRANCH_NAMES)
            ]
            rows.append(_SAL_CANCEL_ROW)
            await message.answer("🏬 Qaysi filial xodimiga fiks kelishuvi kiritamiz?", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
            return

        # Eski texnik yo'l: /setsalary <user_id> <fiks_oylik> — bir xil service yozish yo'li.
        if len(parts) != 3 or not parts[1].isdigit() or not parts[2].lstrip("-").isdigit():
            await message.answer("Foydalanish: /setsalary (tugma orqali) yoki /setsalary <user_id> <fiks_oylik>")
            return

        user_id = int(parts[1])
        fixed_salary = int(parts[2])
        try:
            discipline.set_fixed_salary(user_id, fixed_salary, message.from_user.id)
        except salary_agreement.ValidationError as error:
            await message.answer(f"❌ {error}")
            return
        await message.answer(f"✅ {user_id} uchun fiks oylik o'rnatildi: {fixed_salary:,} so'm")

    @dp.callback_query(F.data.startswith("sal:br:"))
    async def salary_pick_branch(callback: CallbackQuery, state: FSMContext) -> None:
        if not await _sal_allowed(callback):
            return
        try:
            branch = RECRUITING_BRANCH_NAMES[int(callback.data.split(":")[2])]
        except (ValueError, IndexError):
            await callback.answer("Filial topilmadi.", show_alert=True)
            return

        staff = employees.list_approved_by_branch(branch)
        if not staff:
            await callback.answer("Bu filialda tasdiqlangan xodim yo'q.", show_alert=True)
            return
        await state.clear()
        await state.update_data(sal_branch=branch)
        buttons = [
            InlineKeyboardButton(text=_employee_name(item["user_id"]), callback_data=f"sal:emp:{item['user_id']}")
            for item in staff
        ]
        rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)] + [_SAL_CANCEL_ROW]
        await callback.message.edit_text(f"🏬 {branch}\n👤 Xodimni tanlang:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
        await callback.answer()

    @dp.callback_query(F.data.startswith("sal:emp:"))
    async def salary_pick_employee(callback: CallbackQuery, state: FSMContext) -> None:
        if not await _sal_allowed(callback):
            return
        data = await state.get_data()
        branch = data.get("sal_branch")
        try:
            employee_id = int(callback.data.split(":")[2])
        except ValueError:
            employee_id = None
        # Qalbaki/eskirgan tugma: xodim shu filialning tasdiqlangan ro'yxatida bo'lishi shart.
        if branch is None or employee_id is None or employee_id not in {
            item["user_id"] for item in employees.list_approved_by_branch(branch)
        }:
            await callback.answer("Bu tugma eskirgan — qaytadan boshlang.", show_alert=True)
            return
        await state.update_data(
            sal_emp=employee_id, sal_token=None, sal_edit=False,
            sal_amount=None, sal_days=None, sal_minutes=None, sal_date=None,
        )
        await _sal_ask(callback, state, "amount", edit=True)
        await callback.answer()

    async def _sal_store_and_continue(message: Message, state: FSMContext, field: str, value) -> None:
        key = {"amount": "sal_amount", "days": "sal_days", "hours": "sal_minutes", "date": "sal_date"}[field]
        await state.update_data(**{key: value})
        data = await state.get_data()
        if data.get("sal_edit") or field == "date":
            await state.update_data(sal_edit=False)
            await _sal_show_card(message, state, edit=False)
        else:
            await _sal_ask(message, state, _SAL_NEXT[field], edit=False)

    def _sal_text_handler(field: str, parser):
        async def handler(message: Message, state: FSMContext) -> None:
            if not await _sal_allowed(message):
                return
            try:
                value = parser((message.text or "").strip())
            except salary_agreement.ValidationError as error:
                await message.answer(f"❌ {error}\n\n{_SAL_PROMPTS[field]}", reply_markup=InlineKeyboardMarkup(inline_keyboard=[_SAL_CANCEL_ROW]))
                return
            await _sal_store_and_continue(message, state, field, value)

        return handler

    dp.message.register(_sal_text_handler("amount", salary_agreement.parse_salary), StateFilter(SalaryStates.waiting_amount), F.text)
    dp.message.register(_sal_text_handler("days", salary_agreement.parse_days), StateFilter(SalaryStates.waiting_days), F.text)
    dp.message.register(_sal_text_handler("hours", salary_agreement.parse_daily_minutes), StateFilter(SalaryStates.waiting_hours), F.text)
    dp.message.register(_sal_text_handler("date", salary_agreement.parse_effective_date), StateFilter(SalaryStates.waiting_date), F.text)

    @dp.callback_query(F.data == "sal:today", StateFilter(SalaryStates.waiting_date))
    async def salary_date_today(callback: CallbackQuery, state: FSMContext) -> None:
        if not await _sal_allowed(callback):
            return
        await state.update_data(sal_date=company_time.today().isoformat(), sal_edit=False)
        await _sal_show_card(callback, state, edit=True)
        await callback.answer()

    @dp.callback_query(F.data == "sal:edit")
    async def salary_edit(callback: CallbackQuery, state: FSMContext) -> None:
        if not await _sal_allowed(callback):
            return
        data = await state.get_data()
        if not _sal_complete(data) or data.get("sal_edit"):
            await callback.answer("Bu tugma eskirgan.", show_alert=True)
            return
        # Tahrirlash boshlanishi bilan oldingi Saqlash tokeni darhol yaroqsiz bo'ladi (tugmani yashirish bilan cheklanmaydi).
        await state.update_data(sal_token=None, sal_edit=True)
        rows = [
            [InlineKeyboardButton(text="💰 Summa", callback_data="sal:fld:amount"), InlineKeyboardButton(text="📅 Kunlar", callback_data="sal:fld:days")],
            [InlineKeyboardButton(text="🕒 Soat", callback_data="sal:fld:hours"), InlineKeyboardButton(text="📌 Sana", callback_data="sal:fld:date")],
            [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="sal:back")],
            _SAL_CANCEL_ROW,
        ]
        await callback.message.edit_text("Nimani o'zgartiramiz?", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
        await callback.answer()

    @dp.callback_query(F.data.startswith("sal:fld:"))
    async def salary_edit_field(callback: CallbackQuery, state: FSMContext) -> None:
        if not await _sal_allowed(callback):
            return
        field = callback.data.split(":")[2]
        data = await state.get_data()
        if field not in _SAL_STATE_BY_FIELD or not _sal_complete(data, need_token=False) or not data.get("sal_edit"):
            await callback.answer("Bu tugma eskirgan.", show_alert=True)
            return
        await _sal_ask(callback, state, field, edit=True)
        await callback.answer()

    @dp.callback_query(F.data == "sal:back")
    async def salary_back_to_card(callback: CallbackQuery, state: FSMContext) -> None:
        if not await _sal_allowed(callback):
            return
        data = await state.get_data()
        if not _sal_complete(data, need_token=False) or not data.get("sal_edit"):
            await callback.answer("Bu tugma eskirgan.", show_alert=True)
            return
        await _sal_show_card(callback, state, edit=True)  # YANGI token bilan; eskisi yaroqsiz qoladi
        await callback.answer()

    @dp.callback_query(F.data == "sal:cancel")
    async def salary_cancel(callback: CallbackQuery, state: FSMContext) -> None:
        if not await _sal_allowed(callback):
            return
        await state.clear()  # saqlanmagan kelishuv DB'ga yozilmaydi
        await callback.message.edit_text("❌ Bekor qilindi. Hech narsa saqlanmadi.")
        await callback.answer()

    @dp.callback_query(F.data.startswith("sal:save:"))
    async def salary_save(callback: CallbackQuery, state: FSMContext) -> None:
        if not await _sal_allowed(callback):
            return
        data = await state.get_data()
        token = callback.data.split(":", 2)[2]
        # Karta tasdiqlashga tayyor bo'lishi shart: maydonlar to'liq, tahrirlash holati yo'q, kutish holati yo'q, token mos.
        if (
            not _sal_complete(data) or data.get("sal_edit") or data["sal_token"] != token
            or await state.get_state() is not None
        ):
            await callback.answer("Bu tugma eskirgan yoki allaqachon saqlangan.", show_alert=True)
            return
        branch_ids = {item["user_id"] for item in employees.list_approved_by_branch(data["sal_branch"])}
        if data["sal_emp"] not in branch_ids:
            await callback.answer("Xodim endi faol emas — qaytadan boshlang.", show_alert=True)
            return
        try:
            result = salary_agreement.save_agreement(
                data["sal_emp"], data["sal_amount"], data["sal_days"], data["sal_minutes"], data["sal_date"],
                callback.from_user.id, token,
            )
        except salary_agreement.ValidationError as error:
            await callback.answer(str(error), show_alert=True)
            return
        await state.clear()
        if not result.created:
            await callback.answer("Bu kelishuv allaqachon saqlangan.", show_alert=True)
            await callback.message.edit_text(_sal_card_text(data, saved=True))
            return
        await callback.message.edit_text(_sal_card_text(data, saved=True))
        await callback.answer("Saqlandi")

    # ------------------------------------------------------------ ko'rish --

    @dp.message(Command("maosh"))
    async def salary_lookup_handler(message: Message) -> None:
        if not await permissions.ensure_permission(message, permissions.ACTION_LOOKUP_ANY_SALARY):
            return
        if message.chat.type != "private":
            await message.answer("Oylik ma'lumoti faqat shaxsiy chatda ko'rsatiladi.")
            return

        parts = (message.text or "").split()
        if len(parts) != 2 or not parts[1].isdigit():
            await message.answer("Foydalanish: /maosh <user_id>")
            return

        user_id = int(parts[1])
        salary = discipline.get_salary(user_id)
        name = _employee_name(user_id)
        lines = [f"👤 {name}", *salary_agreement.view_lines(user_id, salary["fixed_salary"]), f"💰 Bonus banki: {salary['bonus_bank']} ball"]
        await message.answer("\n".join(lines))

    @dp.message(Command("mymaosh"))
    async def my_salary_handler(message: Message) -> None:
        if not message.from_user or not is_authorized(message.from_user.id):
            return
        if message.chat.type != "private":
            await message.answer("Oylik ma'lumoti faqat shaxsiy chatda ko'rsatiladi.")
            return

        salary = discipline.get_salary(message.from_user.id)
        lines = [*salary_agreement.view_lines(message.from_user.id, salary["fixed_salary"]), f"💰 Bonus banki: {salary['bonus_bank']} ball"]
        await message.answer("\n".join(lines))

    # ------------------------------------------------------- apellyatsiya --

    @dp.message(Command("apellyatsiya"))
    async def appeal_start(message: Message) -> None:
        if not message.from_user or not is_authorized(message.from_user.id):
            return

        penalties = discipline.list_appealable_penalties(message.from_user.id)
        undelivered = discipline.list_undelivered_appeals(message.from_user.id)
        if not penalties and not undelivered:
            await message.answer("ℹ️ E'tiroz bildirish mumkin bo'lgan ball ayirish topilmadi.")
            return

        resend_rows = [
            [
                InlineKeyboardButton(
                    text=f"🔁 Qayta yuborish: {penalty['penalty_date']} — -{penalty['amount']} ball",
                    callback_data=f"bos:redeliver:{penalty['id']}",
                )
            ]
            for penalty in undelivered
        ]
        rows = [
            [
                InlineKeyboardButton(
                    text=f"{penalty['penalty_date']} — -{penalty['amount']} ball ({penalty['rule_number']}-nizom)",
                    callback_data=f"bos:appeal:{penalty['id']}",
                )
            ]
            for penalty in penalties
        ] + resend_rows
        await message.answer(
            "Qaysi ball ayirishga e'tiroz bildirasiz?"
            + ("\n\n⚠️ Saqlangan, lekin rahbarga yuborilmagan e'tirozlaringiz ham bor." if undelivered else ""),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
        )

    @dp.callback_query(F.data.startswith("bos:appeal:"))
    async def appeal_pick(callback: CallbackQuery, state: FSMContext) -> None:
        if not callback.from_user:
            await callback.answer()
            return

        await begin_appeal(callback, state, int(callback.data.split(":")[2]), notice=False)

    async def _deliver_appeal(bot, penalty_id: int) -> str:
        """Bazadagi ``pending`` e'tirozni Founderga yetkazadi (matn/ovoz). Qaytadi: ``delivered`` | ``failed`` | ``busy``
        (boshqa urinish ketmoqda) | ``already`` (allaqachon yetkazilgan yoki hal qilingan). Yangi e'tiroz/minus/ledger
        yozmaydi; AI tavsiyasi bazada bo'lsa qayta yaratilmaydi. Telegram javobi yo'qolib natija noma'lum qolsa, qayta
        urinish Founderga dublikat karta yuborishi mumkin (cheklov)."""
        penalty = discipline.get_penalty(penalty_id)
        if penalty is None or penalty["appeal_status"] != discipline.APPEAL_PENDING or penalty.get("appeal_delivered_at"):
            return "already"
        if not discipline.claim_appeal_delivery(penalty_id):
            return "busy"
        try:
            penalty = discipline.get_penalty(penalty_id)
            name = _employee_name(penalty["employee_id"])
            brief = penalty.get("appeal_ai_brief")
            if not brief:
                rule = discipline.get_rule(penalty["rule_number"])
                brief = await discipline_ai.prepare_appeal_brief(
                    openai_client, name, rule, penalty["amount"], penalty["appeal_reason"] or ""
                )
                discipline.save_appeal_brief(penalty_id, brief)

            brief_text = (
                f"🧾 Apellyatsiya: {name}\n"
                f"Ball ayirish: -{penalty['amount']} ball ({penalty['rule_number']}-nizom)\n\n"
                f"🤖 AI taklifi:\n{brief}\n\n"
                f"Xodim sababi: {penalty['appeal_reason']}"
            )
            decide_kb = _decision_keyboard(penalty_id)
            voice_file_id = penalty.get("appeal_voice_file_id")
            if voice_file_id:
                sent = await bot.send_voice(FOUNDER_ID, voice_file_id, caption=brief_text[:1024], reply_markup=decide_kb)
            else:
                sent = await bot.send_message(FOUNDER_ID, brief_text, reply_markup=decide_kb)
        except Exception as error:
            discipline.release_appeal_delivery(penalty_id)
            print(f"Founder'ga apellyatsiya xabarini yuborib bo'lmadi: {error!r}")
            return "failed"
        try:
            discipline.mark_appeal_delivered(penalty_id, getattr(sent, "message_id", None))
        except Exception as error:
            print(f"Yetkazilganlik belgisini yozib bo'lmadi (Founderga yetgan): {error!r}")
        return "delivered"

    def _redeliver_keyboard(penalty_id: int) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🔁 Qayta yuborish", callback_data=f"bos:redeliver:{penalty_id}")]]
        )

    async def _show_delivery_result(bot, chat_id: int, shown: Message | None, penalty_id: int, status: str, key: str) -> None:
        """Natija xabari. "Yuborildi" va eski ishchi xabarlarni tozalash FAQAT Founderga yetgandan keyin VA yangi
        yakuniy ekran ko'rsatilgach. ``shown`` (vaqtinchalik xabar) bo'lmasa yoki tahrirlanmasa yangi xabar yuboriladi.
        Hech bir xabar yuborilmasa ham e'tiroz/yetkazilganlik holati bazada saqlanadi, eski xabarlar o'chmaydi."""
        if status == "delivered":
            text, markup = "✅ E'tirozingiz rahbarga yuborildi, natija haqida xabar beramiz.", None
        elif status == "failed":
            text = (
                "⚠️ E'tirozingiz saqlandi, lekin rahbarga yuborilmadi. Sababni qayta yozish shart emas — "
                "\"Qayta yuborish\" tugmasini bosing."
            )
            markup = _redeliver_keyboard(penalty_id)
        else:
            return

        final: Message | None = None
        if shown is not None:
            try:
                await shown.edit_text(text, reply_markup=markup)
                final = shown
            except Exception as error:
                print(f"Natija xabarini tahrirlab bo'lmadi, yangi xabar yuboriladi: {error!r}")
        if final is None:
            try:
                final = await bot.send_message(chat_id, text, reply_markup=markup)
            except Exception as error:
                print(f"Xodimga natija xabarini yuborib bo'lmadi (holat bazada saqlangan): {error!r}")
                return
        if status == "delivered":
            await dialog_cleanup.sweep(bot, key, keep=(final.chat.id, final.message_id))

    @dp.callback_query(F.data.startswith("bos:redeliver:"))
    async def appeal_redeliver(callback: CallbackQuery) -> None:
        if not callback.from_user or callback.message is None:
            await callback.answer()
            return
        penalty_id = int(callback.data.split(":")[2])
        penalty = discipline.get_penalty(penalty_id)
        if penalty is None or penalty["employee_id"] != callback.from_user.id:
            await callback.answer("Bu e'tiroz sizniki emas yoki topilmadi.", show_alert=True)
            return
        if penalty["appeal_status"] != discipline.APPEAL_PENDING or penalty.get("appeal_delivered_at"):
            await callback.answer("Bu e'tiroz allaqachon yuborilgan yoki hal qilingan.", show_alert=True)
            try:
                await callback.message.edit_reply_markup(reply_markup=None)
            except Exception as error:
                print(f"Eskirgan qayta yuborish tugmasini olib bo'lmadi: {error!r}")
            return

        await callback.answer("⏳ Yuborilmoqda...")  # uzoq ishdan OLDIN tezkor javob
        key = dialog_cleanup.appeal_key(callback.message.chat.id, penalty_id)
        status = await _deliver_appeal(callback.bot, penalty_id)
        if status == "busy":
            return
        await _show_delivery_result(callback.bot, callback.message.chat.id, callback.message, penalty_id, status, key)

    async def _finish_appeal(message: Message, state: FSMContext, reason_text: str, voice_file_id: str | None) -> None:
        data = await state.get_data()
        penalty_id = data.get("appeal_penalty_id")
        notice_message_id = data.get("appeal_notice_message_id")
        await state.clear()

        if penalty_id is None:
            return

        key = dialog_cleanup.appeal_key(message.chat.id, penalty_id)
        dialog_cleanup.track(key, message)  # xodimning sabab xabari: faqat natija ko'rsatilgach o'chadi

        penalty = discipline.get_penalty(penalty_id)
        if penalty is not None and penalty["employee_id"] != (message.from_user.id if message.from_user else None):
            penalty = None
        penalty = discipline.submit_appeal(penalty_id, reason_text, voice_file_id) if penalty is not None else None
        if penalty is None:
            try:
                notice = await message.answer("❌ Bu ball ayirish uchun apellyatsiya topilmadi yoki allaqachon yuborilgan.")
            except Exception as error:  # noqa: BLE001
                print(f"E'tiroz xatosi xabarini yuborib bo'lmadi: {error!r}")
                return
            await dialog_cleanup.sweep(message.bot, key, keep=(notice.chat.id, notice.message_id))
            return

        # Sabab bazada saqlandi; eski minus xabaridagi e'tiroz tugmasi endi yangi e'tiroz yaratmasin.
        if notice_message_id is not None:
            try:
                await message.bot.edit_message_reply_markup(chat_id=message.chat.id, message_id=notice_message_id, reply_markup=None)
            except Exception as error:  # noqa: BLE001
                print(f"Minus xabaridagi e'tiroz tugmasini olib bo'lmadi: {error!r}")

        waiting = None
        try:
            waiting = await message.answer("⏳ Yuborilmoqda...")
        except Exception as error:  # noqa: BLE001
            print(f"'Yuborilmoqda' xabarini yuborib bo'lmadi (yetkazish davom etadi): {error!r}")
        else:
            dialog_cleanup.track(key, waiting)

        status = await _deliver_appeal(message.bot, penalty_id)
        await _show_delivery_result(message.bot, message.chat.id, waiting, penalty_id, status, key)

    @dp.message(StateFilter(AppealStates.waiting_reason), F.voice)
    async def appeal_reason_voice(message: Message, state: FSMContext) -> None:
        await _finish_appeal(message, state, reason_text="(ovozli xabar)", voice_file_id=message.voice.file_id)

    @dp.message(StateFilter(AppealStates.waiting_reason), F.text)
    async def appeal_reason_text(message: Message, state: FSMContext) -> None:
        await _finish_appeal(message, state, reason_text=(message.text or "").strip(), voice_file_id=None)

    @dp.callback_query(F.data.startswith("bos:decide:"))
    async def appeal_decide(callback: CallbackQuery) -> None:
        if not await permissions.ensure_permission(callback, permissions.ACTION_DECIDE_APPEAL):
            return

        _, _, penalty_id_str, decision = callback.data.split(":")
        penalty_id = int(penalty_id_str)

        try:
            penalty = discipline.decide_appeal(penalty_id, decision, callback.from_user.id)
        except ValueError as error:
            await callback.answer(str(error), show_alert=True)
            try:  # allaqachon hal qilingan: eskirgan qaror tugmalari qolmasin
                await callback.message.edit_reply_markup(reply_markup=None)
            except Exception as edit_error:
                print(f"Eskirgan qaror tugmalarini olib bo'lmadi: {edit_error!r}")
            return

        verdict_text = (
            "✅ E'tiroz qondirildi — ball qaytarildi."
            if decision == discipline.DECISION_APPROVED
            else "❌ E'tiroz rad etildi."
        )
        await callback.answer("Qaror saqlandi")

        try:
            if callback.message.text is not None:
                await callback.message.edit_text(f"{callback.message.text}\n\n{verdict_text}", reply_markup=None)
            elif callback.message.caption is not None:
                await callback.message.edit_caption(
                    caption=f"{callback.message.caption}\n\n{verdict_text}"[:1024], reply_markup=None
                )
        except Exception as error:
            print(f"Qaror xabarini yangilab bo'lmadi: {error!r}")

        try:
            await callback.bot.send_message(penalty["employee_id"], f"📋 Apellyatsiya natijasi: {verdict_text}")
        except Exception as error:
            print(f"Xodimga apellyatsiya natijasini yuborib bo'lmadi: {error!r}")


# --------------------------------------------------------------- scheduler --


async def _agreement_issue_reminder_tick(bot) -> None:
    import salary_agreement_bot

    try:
        await salary_agreement_bot.remind_open_issues(bot)
    except Exception as error:  # noqa: BLE001
        logger.error("Kelishuv savollari eslatmasi xatosi: %s", type(error).__name__)


async def _day_close_tick(bot) -> None:
    """Silent close only: no evaluation, supervisor penalty or daily Telegram message."""
    try:
        now = _now_company()
        await asyncio.to_thread(nazoratchi_day.auto_close_expired, now)
        from repositories import discipline as discipline_repo
        from services import notifications
        work_date = (date.fromisoformat(nazoratchi_day.current_work_date(now)) - timedelta(days=1)).isoformat()
        if work_date < discipline_repo.strict_close_start():
            return
        summary = await asyncio.to_thread(discipline_repo.strict_close_day_report, work_date)
        groups = {}
        for session in summary["sessions"]:
            groups.setdefault(session["supervisor_id"], []).append(session)
        if not groups:
            return
        lines = [f"📅 {work_date} kunlik yopish:"]
        for supervisor_id, sessions in sorted(groups.items()):
            audits = {a["event_type"] for a in summary["audits"] if a["supervisor_id"] == supervisor_id}
            notes = [n for n in summary["notes"] if n["supervisor_id"] == supervisor_id]
            ungraded = sum(nazoratchi_day.branch_pending_count(
                s["branch"], work_date, supervisor_id
            ) for s in sessions)
            outcome = "-5" if "auto_close_minus" in audits else "+5" if "day_full_bonus" in audits else "0"
            line = f"{_employee_name(supervisor_id)}: {outcome} ball, baholanmagan {ungraded}"
            if notes:
                line += "; izoh: " + "; ".join(f"{n['branch']}: {n['note']}" for n in notes)
            lines.append(line)
            if "auto_close_minus" in audits or ungraded:
                await notifications.send_once(
                    bot, f"strict_close:{work_date}", supervisor_id,
                    f"⚠️ {work_date}: kunni to'liq yopishingiz kerak edi. Natija: {outcome} ball."
                )
        await notifications.send_once(bot, f"strict_close:{work_date}", FOUNDER_ID, "\n".join(lines))
    except Exception as error:
        logger.error("Ish kunini avtomatik yopish xatosi: %s", type(error).__name__)


def start_scheduler(bot):
    """``main.py`` bot ishga tushganda chaqiradi. ``calibration_bot.start_scheduler``
    bilan bir xil uslub (mustaqil scheduler, kompaniya vaqt zonasida).
    """
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    nazoratchi_day.ensure_auto_close_policy(_now_company())
    scheduler = AsyncIOScheduler(timezone="Asia/Tashkent")
    scheduler.add_job(_day_close_tick, "cron", hour=6, minute=0, args=[bot], id="bos_day_close_audit",
                      next_run_time=_now_company(), coalesce=True, misfire_grace_time=None)
    scheduler.add_job(_agreement_issue_reminder_tick, "interval", minutes=10, args=[bot], id="salary_agreement_issue_reminder")
    scheduler.start()
    return scheduler
