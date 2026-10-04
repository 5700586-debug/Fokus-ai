"""BOS (Business Operating System) — Telegram interfeysi.

``services/discipline.py`` (biznes logika) va ``services/discipline_ai.py``
(AI tushuntirish/tavsiya) ustiga qurilgan bot oqimi:

- Nazoratchi: xodimni inline tugmalar orqali tanlaydi -> [Chala-1]/[Norma-2]/
  [A'lo-3] yoki jarima (-10/-20/-30) -> jarimada nizom raqami majburiy
  so'raladi va bazadagi nizom bilan solishtiriladi.
- Kunlik ("Bugungi Poyga") va oylik ("Oylik Turnir") reyting dashboardlari.
- Kun o'z vaqtida yopilmasa, ``start_scheduler`` orqali nazoratchidan
  avtomatik -40 ball audit qilinadi (qarang: ``services/rules.py``).
- Xodim jarimaga e'tiroz bildirsa, AI dalil/nizomni solishtirib Founder'ga
  qaror taklifi tayyorlaydi — yakuniy qarorni doim Founder qabul qiladi.
"""

import logging
from datetime import date, datetime, timezone as dt_timezone
from zoneinfo import ZoneInfo

from aiogram import Dispatcher, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import employees
from config import COMPANY_TIMEZONE, FOUNDER_ID, RECRUITING_BRANCH_NAMES
from roles import is_authorized, list_users
from services import chat_cleanup, discipline, discipline_ai, nazoratchi_day, permissions, rule_learning
from services import rules as rules_service

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


def _branch_picker_keyboard(prefix: str, review_date: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"📍 {name}", callback_data=f"{prefix}:{index}:{_ymd(review_date)}")]
            for index, name in enumerate(RECRUITING_BRANCH_NAMES)
        ]
    )


def _day_phrase(session_date: str) -> str:
    from datetime import timedelta

    if session_date == (_today() - timedelta(days=1)).isoformat():
        return "Kecha"
    year, month, day = session_date.split("-")
    return f"{day}.{month}.{year} sanadagi"


def _stale_offer(supervisor_id: int) -> tuple[str, InlineKeyboardMarkup] | None:
    """Oldingi kunlardan yopilmay qolgan filial sessiyalari bo'lsa taklif: avval shuni yopish yoki
    bugungi nazoratga o'tish. Hech narsa majburlanmaydi, sessiya yo'qolmaydi."""
    sessions = nazoratchi_day.stale_open_sessions(supervisor_id, _today().isoformat())
    sessions = [item for item in sessions if _branch_index(item["branch"]) is not None]
    if not sessions:
        return None

    lines = [f"{_day_phrase(item['session_date'])} {_branch_short(item['branch'])} nazorati tugallanmagan." for item in sessions[:3]]
    if len(sessions) > 3:
        lines.append(f"…va yana {len(sessions) - 3} ta.")
    question = "Avval shuni yopamizmi yoki bugungi nazoratga o'tasizmi?"
    if len(lines) == 1:
        lines = [f"{lines[0]} {question}"]
    else:
        lines.append(question)

    rows = [
        [InlineKeyboardButton(
            text=f"🔁 {_branch_short(item['branch'])} {item['session_date'][8:]}.{item['session_date'][5:7]} — avval shuni yopamiz",
            callback_data=f"bos:br:{_branch_index(item['branch'])}:{_ymd(item['session_date'])}",
        )]
        for item in sessions[:3]
    ]
    rows.append([InlineKeyboardButton(text="➡️ Bugungi nazoratga o'tish", callback_data="bos:today")])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


def _branch_screen(branch: str, review_date: str, supervisor_id: int, prefix: str = "") -> tuple[str, InlineKeyboardMarkup]:
    statuses = nazoratchi_day.branch_statuses(branch, review_date, exclude_user_id=supervisor_id)
    ymd = _ymd(review_date)
    index = _branch_index(branch)
    if not statuses:
        text = f"{prefix}🏬 {branch} — {review_date}\n\nHozircha bu filialda aktiv xodim mavjud emas."
    else:
        text = f"{prefix}🏬 {branch} — {review_date}\n\n" + "\n".join(item.line() for item in statuses)

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


class PenaltyStates(StatesGroup):
    waiting_rule = State()


class AppealStates(StatesGroup):
    waiting_reason = State()


def register(dp: Dispatcher, openai_client) -> None:

    # ------------------------------------------------------- /baholash --

    @dp.message(Command("baholash"))
    async def baholash_start(message: Message) -> None:
        if not await permissions.ensure_permission(message, permissions.ACTION_EVALUATE_EMPLOYEE):
            return

        offer = _stale_offer(message.from_user.id)
        if offer is not None:
            await message.answer(offer[0], reply_markup=offer[1])
            return

        await message.answer(
            "🏬 Avval filialni tanlang:", reply_markup=_branch_picker_keyboard("bos:br", _today().isoformat())
        )

    @dp.callback_query(F.data == "bos:today")
    async def baholash_today(callback: CallbackQuery) -> None:
        if not await permissions.ensure_permission(callback, permissions.ACTION_EVALUATE_EMPLOYEE):
            return

        await callback.message.edit_text(
            "🏬 Avval filialni tanlang:", reply_markup=_branch_picker_keyboard("bos:br", _today().isoformat())
        )
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

        branch = RECRUITING_BRANCH_NAMES[index]
        nazoratchi_day.open_session(callback.from_user.id, branch, review_date)
        text, keyboard = _branch_screen(branch, review_date, callback.from_user.id)
        await callback.message.edit_text(text, reply_markup=keyboard)
        await callback.answer()

    @dp.callback_query(F.data.startswith("bos:emp:"))
    async def baholash_pick_employee(callback: CallbackQuery) -> None:
        if not await permissions.ensure_permission(callback, permissions.ACTION_EVALUATE_EMPLOYEE):
            return

        parts = callback.data.split(":")
        employee_id = int(parts[2])
        review_date = (_iso_from_ymd(parts[3]) if len(parts) > 3 else None) or _today().isoformat()
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
        review_date = (_iso_from_ymd(parts[4]) if len(parts) > 4 else None) or _today().isoformat()

        result = discipline.record_daily_grade(employee_id, callback.from_user.id, review_date, grade_key)

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
        await callback.answer("Saqlandi")

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

        offer = _stale_offer(message.from_user.id)
        if offer is not None:
            await message.answer(offer[0], reply_markup=offer[1])
            return

        await message.answer(
            "✅ Qaysi filial nazoratini yopamiz?",
            reply_markup=_branch_picker_keyboard("bos:close", _today().isoformat()),
        )

    @dp.callback_query(F.data.startswith("bos:close:"))
    async def close_branch_handler(callback: CallbackQuery) -> None:
        if not await permissions.ensure_permission(callback, permissions.ACTION_CLOSE_DAY):
            return

        _, _, index_str, ymd = callback.data.split(":")
        review_date = _iso_from_ymd(ymd)
        index = int(index_str) if index_str.isdigit() else -1
        if review_date is None or not 0 <= index < len(RECRUITING_BRANCH_NAMES):
            await callback.answer("Filial topilmadi.", show_alert=True)
            return

        branch = RECRUITING_BRANCH_NAMES[index]
        result = nazoratchi_day.close_session(callback.from_user.id, branch, review_date)

        if result.already_closed:
            await callback.message.edit_text(f"ℹ️ {branch} — {review_date} nazorati allaqachon yopilgan.")
        elif result.blockers:
            await callback.message.edit_text(
                nazoratchi_day.blockers_text(result.blockers),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="📋 Filialga qaytish", callback_data=f"bos:br:{index}:{ymd}"),
                ]]),
            )
        else:
            damda = f"\n🔴 Damda: {result.off_count}" if result.off_count else ""
            await callback.message.edit_text(
                f"✅ {branch} — {review_date} nazorati yopildi. Baholangan: {result.evaluated}/{result.total}{damda}"
            )
        await callback.answer()

    # ------------------------------------------------------- dashboardlar --

    @dp.message(Command("bugungiporga"))
    async def today_board_handler(message: Message) -> None:
        if not message.from_user or not is_authorized(message.from_user.id):
            return

        today = _today()
        board = discipline.get_daily_leaderboard(today.isoformat())
        await message.answer(
            _format_board(f"🏆 Bugungi Poyga — {today.strftime('%d.%m.%Y')}", board, "grade_points")
        )

    @dp.message(Command("oylikturnir"))
    async def month_board_handler(message: Message) -> None:
        if not message.from_user or not is_authorized(message.from_user.id):
            return

        today = _today()
        board = discipline.get_monthly_leaderboard(today.strftime("%Y-%m"))
        await message.answer(
            _format_board(f"🏆 Oylik Turnir — {today.strftime('%Y-%m')}", board, "net_score")
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

    @dp.message(Command("listnizom"))
    async def list_rules_handler(message: Message) -> None:
        if not message.from_user or not is_authorized(message.from_user.id):
            return

        if await start_or_resume_rule_learning(message.bot, message.from_user.id):
            return

        rules = discipline.list_rules()
        if not rules:
            await message.answer("Hali nizomlar kiritilmagan.")
            return

        lines = [f"{rule['rule_number']}. {rule['title']} — {rule['content']}" for rule in rules]
        await message.answer("📖 Korxona nizomlari:\n\n" + "\n".join(lines))

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

    @dp.message(Command("setsalary"))
    async def set_salary_handler(message: Message) -> None:
        if not await permissions.ensure_permission(message, permissions.ACTION_SET_SALARY):
            return

        parts = (message.text or "").split()
        if len(parts) != 3 or not parts[1].isdigit() or not parts[2].lstrip("-").isdigit():
            await message.answer("Foydalanish: /setsalary <user_id> <fiks_oylik>")
            return

        user_id = int(parts[1])
        fixed_salary = int(parts[2])
        discipline.set_fixed_salary(user_id, fixed_salary, message.from_user.id)
        await message.answer(f"✅ {user_id} uchun fiks oylik o'rnatildi: {fixed_salary:,} so'm")

    @dp.message(Command("maosh"))
    async def salary_lookup_handler(message: Message) -> None:
        if not await permissions.ensure_permission(message, permissions.ACTION_LOOKUP_ANY_SALARY):
            return

        parts = (message.text or "").split()
        if len(parts) != 2 or not parts[1].isdigit():
            await message.answer("Foydalanish: /maosh <user_id>")
            return

        user_id = int(parts[1])
        salary = discipline.get_salary(user_id)
        name = _employee_name(user_id)
        await message.answer(
            f"👤 {name}\n💵 Fiks oylik: {salary['fixed_salary']:,} so'm\n"
            f"💰 Bonus banki: {salary['bonus_bank']} ball"
        )

    @dp.message(Command("mymaosh"))
    async def my_salary_handler(message: Message) -> None:
        if not message.from_user or not is_authorized(message.from_user.id):
            return

        salary = discipline.get_salary(message.from_user.id)
        await message.answer(
            f"💵 Fiks oylik: {salary['fixed_salary']:,} so'm\n"
            f"💰 Bonus banki: {salary['bonus_bank']} ball"
        )

    # ------------------------------------------------------- apellyatsiya --

    @dp.message(Command("apellyatsiya"))
    async def appeal_start(message: Message) -> None:
        if not message.from_user or not is_authorized(message.from_user.id):
            return

        penalties = discipline.list_appealable_penalties(message.from_user.id)
        if not penalties:
            await message.answer("ℹ️ E'tiroz bildirish mumkin bo'lgan ball ayirish topilmadi.")
            return

        rows = [
            [
                InlineKeyboardButton(
                    text=f"{penalty['penalty_date']} — -{penalty['amount']} ball ({penalty['rule_number']}-nizom)",
                    callback_data=f"bos:appeal:{penalty['id']}",
                )
            ]
            for penalty in penalties
        ]
        await message.answer(
            "Qaysi ball ayirishga e'tiroz bildirasiz?", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
        )

    @dp.callback_query(F.data.startswith("bos:appeal:"))
    async def appeal_pick(callback: CallbackQuery, state: FSMContext) -> None:
        if not callback.from_user:
            await callback.answer()
            return

        penalty_id = int(callback.data.split(":")[2])
        await state.update_data(appeal_penalty_id=penalty_id)
        await state.set_state(AppealStates.waiting_reason)
        await callback.message.edit_text("✍️ Sababingizni matn yoki ovozli xabar sifatida yuboring.")
        await callback.answer()

    async def _finish_appeal(message: Message, state: FSMContext, reason_text: str, voice_file_id: str | None) -> None:
        data = await state.get_data()
        penalty_id = data.get("appeal_penalty_id")
        await state.clear()

        if penalty_id is None:
            return

        penalty = discipline.submit_appeal(penalty_id, reason_text, voice_file_id)
        if penalty is None:
            await message.answer("❌ Bu ball ayirish uchun apellyatsiya topilmadi yoki allaqachon yuborilgan.")
            return

        waiting = await message.answer("⏳ AI qaror taklifini tayyorlayapti...")

        rule = discipline.get_rule(penalty["rule_number"])
        name = _employee_name(penalty["employee_id"])
        brief = await discipline_ai.prepare_appeal_brief(openai_client, name, rule, penalty["amount"], reason_text)
        discipline.save_appeal_brief(penalty_id, brief)

        await waiting.edit_text("✅ E'tirozingiz rahbarga yuborildi, natija haqida xabar beramiz.")

        brief_text = (
            f"🧾 Apellyatsiya: {name}\n"
            f"Ball ayirish: -{penalty['amount']} ball ({penalty['rule_number']}-nizom)\n\n"
            f"🤖 AI taklifi:\n{brief}\n\n"
            f"Xodim sababi: {reason_text}"
        )
        decide_kb = _decision_keyboard(penalty_id)

        try:
            if voice_file_id:
                await message.bot.send_voice(
                    FOUNDER_ID, voice_file_id, caption=brief_text[:1024], reply_markup=decide_kb
                )
            else:
                await message.bot.send_message(FOUNDER_ID, brief_text, reply_markup=decide_kb)
        except Exception as error:
            print(f"Founder'ga apellyatsiya xabarini yuborib bo'lmadi: {error!r}")

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


async def _day_close_tick(bot) -> None:
    from roles import find_user_by_role

    tz = _resolve_timezone()
    now = datetime.now(tz)
    today = now.date().isoformat()
    deadline = rules_service.get_bos_day_close_deadline()
    if now.strftime("%H:%M") < deadline:
        return

    supervisor_id = find_user_by_role("nazoratchi")
    if supervisor_id is None:
        return

    if discipline.get_closure(supervisor_id, today) is not None:
        return

    penalty_amount = rules_service.get_bos_supervisor_late_penalty()
    if not discipline.penalize_supervisor_for_late_close(supervisor_id, today, penalty_amount):
        return

    try:
        await bot.send_message(
            supervisor_id,
            f"⚠️ Bugungi kunni {deadline} gacha yopmadingiz — sizdan -{penalty_amount} "
            "ball avtomatik yechildi (audit qayd etildi).",
        )
    except Exception as error:
        print(f"Nazoratchiga avtomatik jarima xabarini yuborib bo'lmadi: {error!r}")

    try:
        await bot.send_message(
            FOUNDER_ID,
            f"🔔 Nazoratchi (user_id: {supervisor_id}) bugungi kunni {deadline} gacha "
            f"yopmadi — avtomatik -{penalty_amount} ball audit qilindi.",
        )
    except Exception as error:
        print(f"Founder'ga audit xabarini yuborib bo'lmadi: {error!r}")


def start_scheduler(bot):
    """``main.py`` bot ishga tushganda chaqiradi. ``calibration_bot.start_scheduler``
    bilan bir xil uslub (mustaqil scheduler, kompaniya vaqt zonasida).
    """
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    scheduler = AsyncIOScheduler(timezone=_resolve_timezone())
    scheduler.add_job(_day_close_tick, "interval", minutes=5, args=[bot], id="bos_day_close_audit")
    scheduler.start()
    return scheduler
