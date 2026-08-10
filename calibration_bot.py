"""Ta'minotchi/haydovchi kunlik kalibratsiya savol-javobi — bot oqimi.

``services/calibration.py`` (savol rejasi, mavhum javob aniqlash),
``repositories/baselines.py`` (sessiya/savol saqlash) va mavjud
``services/cross_check.py`` (ta'minotchi/haydovchi javoblarini
solishtirish) ustiga qurilgan Telegram interfeysi.

Approval callback ichida faqat sessiya yaratiladi (``on_employee_approved``)
— hech qanday savol darhol yuborilmaydi. Kunlik savollar alohida
scheduler orqali (``start_scheduler``) yuboriladi.
"""

import logging
from datetime import date, datetime, timezone as dt_timezone
from zoneinfo import ZoneInfo

from aiogram import Dispatcher
from aiogram.filters import Filter, StateFilter
from aiogram.types import Message

import employees
from config import COMPANY_TIMEZONE, FOUNDER_ID
from repositories import baselines as baselines_repo
from services import calibration, cross_check, notifications
from services import rules as rules_service

logger = logging.getLogger(__name__)

_TARGET_ROLES = ("taminotchi", "haydovchi")


def _resolve_timezone():
    """``ZoneInfo`` IANA tzdata bazasiga muhtoj — ba'zi minimal Docker
    imidjlarida (masalan Render'ning ba'zi Python bazaviy imidjlari)
    ``tzdata`` paketi yo'q bo'lsa ``ZoneInfoNotFoundError`` ko'taradi.
    Bu ``main.py``ning butun ishga tushishini yiqitmasligi kerak —
    xato bo'lsa UTC'ga (hech qanday tzdata'ga muhtoj bo'lmagan sof
    stdlib) qaytiladi va log qilinadi.
    """
    try:
        return ZoneInfo(COMPANY_TIMEZONE)
    except Exception as error:
        message = f"COMPANY_TIMEZONE ({COMPANY_TIMEZONE!r}) yuklanmadi, UTC'ga qaytildi: {error!r}"
        logger.error(message)
        print(message)
        return dt_timezone.utc


def _partner_role(role_key: str) -> str:
    return "haydovchi" if role_key == "taminotchi" else "taminotchi"


def _get_daily_plan(user_id: int, role_key: str, question_date: str) -> list[dict]:
    from roles import find_user_by_role

    partner_active = find_user_by_role(_partner_role(role_key)) is not None
    return calibration.build_daily_question_plan(
        user_id, role_key, question_date, cross_check_available=partner_active
    )


def _resolve_start_date(user_id: int) -> str:
    """Sessiya yo'q holatda (masalan avvaldan approve qilingan xodim)
    tiklanadigan boshlanish sanasi — ``employees.approved_at`` mavjud
    bo'lsa shu ishlatiladi, aks holda bugun.
    """
    profile = employees.get_profile(user_id)
    approved_at = profile.get("approved_at") if profile else None
    if approved_at:
        return approved_at[:10]
    return date.today().isoformat()


def on_employee_approved(user_id: int, role_key: str) -> None:
    """``approval.py``dagi ``handle_approve`` chaqiradi. Faqat sessiya
    yaratadi — hech qanday xabar yubormaydi (uzun interview shu yerda
    BOSHLANMAYDI).
    """
    if role_key not in _TARGET_ROLES:
        return

    calibration.ensure_session(user_id, role_key)


class HasActiveCalibrationQuestion(Filter):
    """Foydalanuvchida DB'da javob kutayotgan kalibratsiya savoli bo'lsagina
    ishlaydi — aks holda boshqa ``F.text`` handlerlari (masalan AI Tahlil)
    ishlashda davom etadi.
    """

    async def __call__(self, message: Message) -> bool | dict:
        if not message.from_user or not message.text:
            return False

        question = baselines_repo.get_active_question(message.from_user.id)
        if question is None:
            return False

        return {"active_question": question}


async def _send_question(bot, session: dict, question_date: str, question_spec: dict) -> dict:
    await bot.send_message(session["user_id"], question_spec["question_text"])
    question_id = baselines_repo.record_question(
        session["id"], session["user_id"], session["role_key"], question_date,
        question_spec["dimension"], question_spec["question_text"],
        is_cross_check=question_spec["is_cross_check"],
    )
    return baselines_repo.get_question(question_id)


async def _advance_to_next_question(bot, user_id: int, role_key: str, question_date: str) -> None:
    session = baselines_repo.get_session(user_id)
    if session is None:
        return

    plan = _get_daily_plan(user_id, role_key, question_date)
    asked_today = baselines_repo.get_questions_for_date(user_id, question_date)

    if len(asked_today) >= len(plan):
        await bot.send_message(user_id, "✅ Bugungi savollar tugadi, rahmat!")
        return

    await _send_question(bot, session, question_date, plan[len(asked_today)])


async def _try_cross_check(bot, answered_question: dict) -> None:
    if not answered_question["is_cross_check"] or answered_question["answer_text"] is None:
        return

    from roles import find_user_by_role

    role_key = answered_question["role_key"]
    partner_role = _partner_role(role_key)
    partner_id = find_user_by_role(partner_role)
    if partner_id is None:
        return

    question_date = answered_question["question_date"]
    partner_questions = baselines_repo.get_questions_for_date(partner_id, question_date)
    partner_answer = next(
        (q for q in partner_questions if q["is_cross_check"] and q["answer_text"] is not None), None
    )
    if partner_answer is None:
        return  # boshqa tomon hali javob bermagan — u javob berganda qayta chaqiriladi

    taminotchi_id = answered_question["user_id"] if role_key == "taminotchi" else partner_id
    haydovchi_id = partner_id if role_key == "taminotchi" else answered_question["user_id"]
    taminotchi_answer = answered_question if role_key == "taminotchi" else partner_answer
    haydovchi_answer = partner_answer if role_key == "taminotchi" else answered_question

    session = cross_check.start_session(question_date, taminotchi_id, haydovchi_id)
    cross_check.record_answer(
        session["id"], taminotchi_id, calibration.CROSS_CHECK_QUESTION_TEXT, taminotchi_answer["answer_text"]
    )
    cross_check.record_answer(
        session["id"], haydovchi_id, calibration.CROSS_CHECK_QUESTION_TEXT, haydovchi_answer["answer_text"]
    )

    differences = cross_check.compare_session(session["id"], taminotchi_id, haydovchi_id)
    if not differences:
        return

    name_a = _employee_name(taminotchi_id)
    name_b = _employee_name(haydovchi_id)
    report = cross_check.format_discrepancy_report(differences, name_a, name_b)

    recipients = {FOUNDER_ID}
    nazoratchi_id = find_user_by_role("nazoratchi")
    if nazoratchi_id is not None:
        recipients.add(nazoratchi_id)

    for recipient_id in recipients:
        await bot.send_message(recipient_id, f"🔎 Ta'minotchi/haydovchi kross-tekshiruvi:\n\n{report}")


def _employee_name(user_id: int) -> str:
    profile = employees.get_profile(user_id)
    if profile is None:
        return str(user_id)

    full_name = " ".join(part for part in (profile.get("familiya"), profile.get("ism")) if part)
    return full_name or str(user_id)


def register(dp: Dispatcher) -> None:
    @dp.message(StateFilter(None), HasActiveCalibrationQuestion())
    async def handle_calibration_answer(message: Message, active_question: dict) -> None:
        text = (message.text or "").strip()
        if not text:
            return

        if calibration.is_vague_answer(text) and active_question["follow_up_count"] < calibration.MAX_FOLLOW_UPS:
            baselines_repo.increment_follow_up(active_question["id"])
            await message.answer(calibration.build_follow_up_text(active_question["dimension"]))
            return

        baselines_repo.record_answer(active_question["id"], text)
        answered = baselines_repo.get_question(active_question["id"])

        await _try_cross_check(message.bot, answered)
        await _advance_to_next_question(
            message.bot, answered["user_id"], answered["role_key"], answered["question_date"]
        )


# --------------------------------------------------------------- scheduler --


async def _daily_tick(bot) -> None:
    from roles import list_users

    tz = _resolve_timezone()
    today = datetime.now(tz).date().isoformat()
    question_time = rules_service.get_calibration_daily_question_time()
    current_hm = datetime.now(tz).strftime("%H:%M")
    if current_hm < question_time:
        return

    for user_id, info in list_users().items():
        role_key = info["role"]
        if role_key not in _TARGET_ROLES:
            continue

        try:
            await _start_daily_questions_if_needed(bot, user_id, role_key, today)
        except Exception as error:  # noqa: BLE001 - bitta xodim xatosi butun tickni to'xtatmasin
            logger.error("Kalibratsiya savol yuborishda xato (user_id=%s): %r", user_id, error)
            print(f"Kalibratsiya savol yuborishda xato (user_id={user_id}): {error!r}")


async def _start_daily_questions_if_needed(bot, user_id: int, role_key: str, today: str) -> None:
    session = calibration.ensure_session(user_id, role_key, start_date=_resolve_start_date(user_id))

    if not calibration.is_within_calibration_window(session["start_date"], today):
        return

    plan = _get_daily_plan(user_id, role_key, today)
    if not plan:
        return

    first_question = plan[0]
    sent = await notifications.send_once(
        bot, f"calibration_start:{today}:{user_id}", user_id, first_question["question_text"]
    )
    if sent:
        baselines_repo.record_question(
            session["id"], user_id, role_key, today, first_question["dimension"],
            first_question["question_text"], is_cross_check=first_question["is_cross_check"],
        )


def start_scheduler(bot):
    """``main.py`` bot ishga tushganda chaqiradi. Mavjud
    ``inventory_bot.start_scheduler`` bilan bir xil uslub, lekin
    mustaqil scheduler sifatida (ishlab turgan ombor eslatmasiga
    tegilmaydi) va kompaniya vaqt zonasida (``config.COMPANY_TIMEZONE``).
    """
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    scheduler = AsyncIOScheduler(timezone=_resolve_timezone())
    scheduler.add_job(_daily_tick, "interval", minutes=5, args=[bot], id="calibration_daily_questions")
    scheduler.start()
    return scheduler
