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
from config import COMPANY_TIMEZONE, FOUNDER_ID
from roles import is_authorized, list_users
from services import discipline, discipline_ai, permissions
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
# — ``main.py``dagi ``ai_users`` bilan bir xil uslubda, jarayon-ichi
# himoya. Bitta nazoratchi bir vaqtning o'zida faqat bitta jarima
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


def _employee_list_keyboard(page: int) -> InlineKeyboardMarkup:
    targets = _target_employees()
    start = page * _PAGE_SIZE
    page_items = targets[start : start + _PAGE_SIZE]

    rows = [
        [InlineKeyboardButton(text=name, callback_data=f"bos:emp:{user_id}:{page}")]
        for user_id, name in page_items
    ]

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"bos:page:{page - 1}"))
    if start + _PAGE_SIZE < len(targets):
        nav_row.append(InlineKeyboardButton(text="Keyingi ➡️", callback_data=f"bos:page:{page + 1}"))
    if nav_row:
        rows.append(nav_row)

    return InlineKeyboardMarkup(inline_keyboard=rows)


def _employee_action_keyboard(employee_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Chala - 1", callback_data=f"bos:grade:{employee_id}:{discipline.GRADE_CHALA}"
                ),
                InlineKeyboardButton(
                    text="Norma - 2", callback_data=f"bos:grade:{employee_id}:{discipline.GRADE_NORMA}"
                ),
                InlineKeyboardButton(
                    text="A'lo - 3", callback_data=f"bos:grade:{employee_id}:{discipline.GRADE_ALO}"
                ),
            ],
            [InlineKeyboardButton(text="🚫 Jarima (-10/-20/-30)", callback_data=f"bos:penalty_menu:{employee_id}")],
        ]
    )


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
                    text="✅ Rozi (jarima bekor)", callback_data=f"bos:decide:{penalty_id}:{discipline.DECISION_APPROVED}"
                ),
                InlineKeyboardButton(
                    text="❌ Rad etish", callback_data=f"bos:decide:{penalty_id}:{discipline.DECISION_REJECTED}"
                ),
            ]
        ]
    )


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

        await message.answer("👥 Xodimni tanlang:", reply_markup=_employee_list_keyboard(0))

    @dp.callback_query(F.data.startswith("bos:page:"))
    async def baholash_page(callback: CallbackQuery) -> None:
        if not await permissions.ensure_permission(callback, permissions.ACTION_EVALUATE_EMPLOYEE):
            return

        page = int(callback.data.split(":")[2])
        await callback.message.edit_text("👥 Xodimni tanlang:", reply_markup=_employee_list_keyboard(page))
        await callback.answer()

    @dp.callback_query(F.data.startswith("bos:emp:"))
    async def baholash_pick_employee(callback: CallbackQuery) -> None:
        if not await permissions.ensure_permission(callback, permissions.ACTION_EVALUATE_EMPLOYEE):
            return

        employee_id = int(callback.data.split(":")[2])
        name = _employee_name(employee_id)
        await callback.message.edit_text(
            f"👤 {name}\nBaho tanlang yoki jarima kiriting:",
            reply_markup=_employee_action_keyboard(employee_id),
        )
        await callback.answer()

    @dp.callback_query(F.data.startswith("bos:grade:"))
    async def baholash_pick_grade(callback: CallbackQuery) -> None:
        if not await permissions.ensure_permission(callback, permissions.ACTION_EVALUATE_EMPLOYEE):
            return

        _, _, employee_id_str, grade_key = callback.data.split(":")
        employee_id = int(employee_id_str)
        eval_date = _today().isoformat()

        result = discipline.record_daily_grade(employee_id, callback.from_user.id, eval_date, grade_key)

        name = _employee_name(employee_id)
        label = discipline.GRADE_LABELS[grade_key]
        await callback.message.edit_text(
            f"✅ {name} — {label} ({result.grade_points} ball) qayd etildi.\n"
            f"💰 Bonus banki: {result.bonus_bank_balance} ball"
        )
        await callback.answer("Saqlandi")

    @dp.callback_query(F.data.startswith("bos:penalty_menu:"))
    async def baholash_penalty_menu(callback: CallbackQuery) -> None:
        if not await permissions.ensure_permission(callback, permissions.ACTION_EVALUATE_EMPLOYEE):
            return

        employee_id = int(callback.data.split(":")[2])
        name = _employee_name(employee_id)
        await callback.message.edit_text(
            f"🚫 {name} uchun jarima miqdorini tanlang:",
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
                    "Founder'dan /addnizom orqali qo'shishini so'rang."
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

            name = _employee_name(employee_id)
            await waiting.edit_text(
                f"{ai_note}\n\n"
                f"🚫 {name} uchun -{amount} ball jarima qo'llanildi ({rule_number}-nizom).\n"
                f"💰 Bonus banki: {result['bonus_bank_balance']} ball\n"
                "ℹ️ Fiks oylikka ta'sir qilmaydi."
            )

            try:
                await message.bot.send_message(
                    employee_id,
                    f"⚠️ Sizga -{amount} ball jarima qo'llanildi ({rule_number}-nizom: {rule['title']}).\n"
                    "Rozi bo'lmasangiz /apellyatsiya buyrug'i orqali e'tiroz bildiring.",
                )
            except Exception as error:
                print(f"Xodimga jarima xabarini yuborib bo'lmadi ({employee_id}): {error!r}")
        finally:
            _PENDING_PENALTY_APPLICATIONS.discard(nazoratchi_id)

    # ------------------------------------------------------- /kunniyop --

    @dp.message(Command("kunniyop"))
    async def close_day_handler(message: Message) -> None:
        if not await permissions.ensure_permission(message, permissions.ACTION_CLOSE_DAY):
            return

        today = _today().isoformat()
        total = len(_target_employees())

        if not discipline.close_day(message.from_user.id, today, total):
            await message.answer(f"ℹ️ {today} allaqachon yopilgan.")
            return

        evaluated = len(discipline.get_daily_leaderboard(today))
        await message.answer(f"✅ {today} kuni yopildi. Baholangan: {evaluated}/{total}")

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

    @dp.message(Command("listnizom"))
    async def list_rules_handler(message: Message) -> None:
        if not message.from_user or not is_authorized(message.from_user.id):
            return

        rules = discipline.list_rules()
        if not rules:
            await message.answer("Hali nizomlar kiritilmagan.")
            return

        lines = [f"{rule['rule_number']}. {rule['title']} — {rule['content']}" for rule in rules]
        await message.answer("📖 Korxona nizomlari:\n\n" + "\n".join(lines))

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
            await message.answer("ℹ️ E'tiroz bildirish mumkin bo'lgan jarima topilmadi.")
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
            "Qaysi jarimaga e'tiroz bildirasiz?", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
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
            await message.answer("❌ Bu jarima uchun apellyatsiya topilmadi yoki allaqachon yuborilgan.")
            return

        waiting = await message.answer("⏳ AI qaror taklifini tayyorlayapti...")

        rule = discipline.get_rule(penalty["rule_number"])
        name = _employee_name(penalty["employee_id"])
        brief = await discipline_ai.prepare_appeal_brief(openai_client, name, rule, penalty["amount"], reason_text)
        discipline.save_appeal_brief(penalty_id, brief)

        await waiting.edit_text("✅ E'tirozingiz rahbarga yuborildi, natija haqida xabar beramiz.")

        brief_text = (
            f"🧾 Apellyatsiya: {name}\n"
            f"Jarima: -{penalty['amount']} ball ({penalty['rule_number']}-nizom)\n\n"
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
            "✅ E'tiroz qondirildi — jarima bekor qilindi."
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
