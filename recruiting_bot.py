"""Fokus HR — nomzod bilan Telegram'da suhbat (ishga qabul anketasi).

Bu oqim ``supplier_chat_bot.py`` bilan bir xil naqsh: FAQAT nomzod
(ro'yxatdan o'tgan xodim/Founder EMAS) uchun, ichki menyu/buyruqlarga
umuman tegmaydi. Nomzod ``/apply`` yoki ``/start apply`` orqali
kiradi (qarang ``main.py``dagi kichik qo'shimcha tekshiruv).

Suhbat holati aiogram FSM (``storage.py``dagi ``SQLiteStorage``) orqali
saqlanadi — worker qayta ishga tushsa ham yo'qolmaydi (qarang
``onboarding.py`` bilan bir xil naqsh). Alohida "session" jadvali shu
sabab kerak emas (qarang ``schema/recruiting.py`` docstringi).

Baholash har doim DETERMINISTIK (``services/recruiting_scoring.py``) —
AI faqat qisqa xulosa matni yozadi, yakuniy natijani AI hech qachon
belgilamaydi. Founder qarori (tugmalar) esa alohida, mustaqil ustunda
saqlanadi — AI tavsiyasi bilan aralashmaydi.
"""

import logging
import re

from aiogram import Dispatcher, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from openai import AsyncOpenAI

from config import FOUNDER_ID, RECRUITING_MAX_FOLLOW_UPS, RECRUITING_MAX_VOICE_SECONDS
from repositories import recruiting as recruiting_repo
from services import (
    audit,
    permissions,
    recruiting_card,
    recruiting_followup,
    recruiting_privacy,
    recruiting_questions,
    recruiting_rubric,
    recruiting_scoring,
    recruiting_voice,
)

logger = logging.getLogger(__name__)


class RecruitingStates(StatesGroup):
    consent = State()
    choosing_vacancy = State()
    full_name = State()
    phone = State()
    experience = State()
    leave_reason = State()
    availability = State()
    start_date = State()
    role_question = State()
    follow_up = State()
    math_question = State()
    motivation = State()


_ALL_STATES = tuple(RecruitingStates.__all_states__)


# ATAYLAB ``main.py``dagi umumiy ``CANCEL_TEXT``/``BACK_TEXT``dan FARQLI
# matn: main.py'da ``_ClearStaleStateMiddleware`` xuddi shu matnlarni
# ko'rib, HAR QANDAY oqim uchun FSM holatini yo'nalishga yetib
# borishidan OLDIN tozalab yuboradi (global "qochish" mexanizmi). Agar
# bu yerda ham AYNAN o'sha matn ishlatilsa, rekruting arizasini DB'da
# "bekor qilindi" deb belgilaydigan handler HECH QACHON ishga
# tushmaydi — chunki state allaqachon ``None``ga aylantirilgan bo'ladi.
_CANCEL_TEXT = "🚫 Arizani bekor qilish"
_CANCEL_KB = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=_CANCEL_TEXT)]], resize_keyboard=True)

_PHONE_RE = re.compile(r"^\+?\d{7,15}$")

_NO_VACANCY_TEXT = "Hozircha faol vakansiya mavjud emas. Murojaatingiz uchun rahmat."

_CONSENT_TEXT = (
    "Assalomu alaykum! 👋 Men Saturn jamoasining Fokus HR yordamchisiman.\n\n"
    "Ishga qabul jarayonida bir nechta savol beraman:\n"
    "• Javoblaringiz FAQAT ishga qabul jarayonida ishlatiladi.\n"
    "• AI yordamchi javoblaringizni tahlil qiladi.\n"
    "• Yakuniy qarorni FAQAT inson (Saturn jamoasi vakili) qabul qiladi.\n"
    "• Istalgan vaqtda jarayonni bekor qilishingiz mumkin.\n\n"
    "Davom etamizmi?"
)

_FIELD_PROMPTS: dict[str, str] = {
    "full_name": "Ism-familiyangizni kiriting:",
    "phone": "Telefon raqamingizni yuboring (tugma orqali yoki yozib):",
    "experience": "Oldingi ish tajribangiz haqida qisqacha yozing (bo'lmasa \"yo'q\" deb yozing):",
    "leave_reason": "Oldingi ish joyingizdan nega ketgansiz (yoki hozir nega ish qidiryapsiz)?",
    "availability": "Qanday ish jadvali sizga qulay? (masalan: har kuni, smenama-smena, faqat kunduzi)",
    "start_date": "Qachondan ishga chiqishingiz mumkin?",
}

_FIELD_STATE: dict[str, State] = {
    "full_name": RecruitingStates.full_name,
    "phone": RecruitingStates.phone,
    "experience": RecruitingStates.experience,
    "leave_reason": RecruitingStates.leave_reason,
    "availability": RecruitingStates.availability,
    "start_date": RecruitingStates.start_date,
}
_STATE_TO_FIELD: dict[str, str] = {state.state: field for field, state in _FIELD_STATE.items()}

# field -> (DB ustuni, keyingi qadam nomi)
_FIELD_NEXT: dict[str, tuple[str, str]] = {
    "full_name": ("full_name", "phone"),
    "phone": ("phone", "experience"),
    "experience": ("experience_text", "leave_reason"),
    "leave_reason": ("leave_reason_text", "availability"),
    "availability": ("availability_text", "start_date"),
    "start_date": ("start_date_text", "role_question"),
}

_MOTIVATION_PROMPT = (
    "Oxirgi savol: nega aynan Saturn jamoasida ishlashni xohlaysiz?\n"
    "Matn bilan yozishingiz yoki ovozli xabar (60 soniyagacha) yuborishingiz mumkin."
)
_MOTIVATION_QUESTION_TEXT = "Nega aynan Saturn jamoasida ishlashni xohlaysiz?"

_RESUME_NOTICE = "Davom etamiz — tugallanmagan arizangiz saqlangan."


def _looks_like_phone(text: str) -> bool:
    cleaned = re.sub(r"[\s\-()]", "", text.strip())
    return bool(_PHONE_RE.match(cleaned))


def _phone_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Raqamni yuborish", request_contact=True)],
            [KeyboardButton(text=_CANCEL_TEXT)],
        ],
        resize_keyboard=True,
    )


def _consent_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Davom etish", callback_data="rec_consent:yes"),
                InlineKeyboardButton(text="❌ Bekor qilish", callback_data="rec_consent:no"),
            ]
        ]
    )


def _vacancy_kb(vacancies: list[dict]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=v["title"], callback_data=f"rec_vacancy:{v['id']}")]
            for v in vacancies
        ]
    )


def _math_keyboard(application_id: int, math_q: recruiting_questions.MathQuestion) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=choice.label, callback_data=f"rec_math:{application_id}:{choice.key}")]
            for choice in math_q.choices
        ]
    )


# --------------------------------------------------------- kirish / rozilik --


async def cmd_apply(message: Message, state: FSMContext) -> None:
    if not message.from_user:
        return

    existing = recruiting_repo.get_in_progress_application(message.from_user.id)
    if existing is not None:
        await _resume_application(message, state, existing)
        return

    vacancies = recruiting_repo.list_vacancies(active_only=True)
    if not vacancies:
        await message.answer(_NO_VACANCY_TEXT)
        return

    await state.clear()
    await state.set_state(RecruitingStates.consent)
    await message.answer(_CONSENT_TEXT, reply_markup=_consent_kb())


async def handle_consent(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=None)

    if callback.data == "rec_consent:no":
        await state.clear()
        await callback.answer()
        if callback.message:
            await callback.message.answer(
                "Tushunarli. Xohlagan vaqtingizda /apply orqali qaytishingiz mumkin."
            )
        return

    vacancies = recruiting_repo.list_vacancies(active_only=True)
    if not vacancies:
        await state.clear()
        await callback.answer()
        if callback.message:
            await callback.message.answer(_NO_VACANCY_TEXT)
        return

    await state.set_state(RecruitingStates.choosing_vacancy)
    await callback.answer()
    if callback.message:
        await callback.message.answer("Qaysi lavozimga ariza topshirmoqchisiz?", reply_markup=_vacancy_kb(vacancies))


async def handle_vacancy_choice(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user:
        await callback.answer()
        return

    vacancy_id = int(callback.data.split(":", 1)[1])
    vacancy = recruiting_repo.get_vacancy(vacancy_id)
    if vacancy is None or not vacancy["is_active"]:
        await callback.answer("Bu vakansiya endi mavjud emas.", show_alert=True)
        return

    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=None)

    candidate_id = callback.from_user.id
    retention_expires_at = recruiting_privacy.compute_retention_expiry()
    application_id = recruiting_repo.create_application(candidate_id, vacancy_id, retention_expires_at)
    recruiting_repo.record_consent(application_id)
    recruiting_repo.update_application(application_id, current_step="full_name")

    audit.log_event(
        audit.EVENT_RECRUITING_APPLICATION_STARTED, actor_id=candidate_id, target_id=application_id
    )

    await state.update_data(
        application_id=application_id, vacancy_id=vacancy_id, position_key=vacancy["position_key"]
    )
    await state.set_state(RecruitingStates.full_name)
    await callback.answer()
    if callback.message:
        await callback.message.answer(
            f"Ajoyib! \"{vacancy['title']}\" lavozimiga ariza boshladik.\n\n{_FIELD_PROMPTS['full_name']}",
            reply_markup=_CANCEL_KB,
        )


async def handle_cancel(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    application_id = data.get("application_id")
    if application_id:
        recruiting_repo.cancel_application(application_id)
        audit.log_event(
            audit.EVENT_RECRUITING_APPLICATION_CANCELLED,
            actor_id=message.from_user.id if message.from_user else None,
            target_id=application_id,
        )
    await state.clear()
    await message.answer(
        "Ariza bekor qilindi. Xohlasangiz, /apply orqali qaytadan boshlashingiz mumkin.",
        reply_markup=ReplyKeyboardRemove(),
    )


# ------------------------------------------------------------- davom ettirish --


async def _resume_application(message: Message, state: FSMContext, application: dict) -> None:
    await state.clear()
    vacancy = recruiting_repo.get_vacancy(application["vacancy_id"])
    position_key = vacancy["position_key"] if vacancy else None
    await state.update_data(
        application_id=application["id"], vacancy_id=application["vacancy_id"], position_key=position_key
    )
    step = application.get("current_step") or "full_name"

    if step in _FIELD_STATE:
        await state.set_state(_FIELD_STATE[step])
        await message.answer(_RESUME_NOTICE)
        kb = _phone_kb() if step == "phone" else _CANCEL_KB
        await message.answer(_FIELD_PROMPTS[step], reply_markup=kb)
        return

    if step == "role_question":
        questions = recruiting_questions.questions_for(position_key)
        answers = recruiting_repo.get_answers(application["id"])
        question_keys = {key for key, _ in questions}
        answered = sum(1 for a in answers if a["question_key"] in question_keys and not a["is_follow_up"])
        await state.update_data(question_index=answered, follow_up_count=application.get("follow_up_count", 0))
        await message.answer(_RESUME_NOTICE)
        await _advance_to_step(message, state, await state.get_data(), "role_question", index_override=answered)
        return

    if step == "math_question":
        math_q = recruiting_questions.math_question_for(position_key)
        await message.answer(_RESUME_NOTICE)
        if math_q:
            await state.set_state(RecruitingStates.math_question)
            await message.answer(math_q.text, reply_markup=_math_keyboard(application["id"], math_q))
        else:
            await _ask_motivation(message, state)
        return

    await message.answer(_RESUME_NOTICE)
    await _ask_motivation(message, state)


# --------------------------------------------------------------- oddiy maydonlar --


async def handle_field_answer(message: Message, state: FSMContext) -> None:
    current_state = await state.get_state()
    field = _STATE_TO_FIELD.get(current_state)
    if field is None:
        return

    if field == "phone" and message.contact is not None:
        text = message.contact.phone_number
    else:
        text = (message.text or "").strip()

    if not text:
        await message.answer("❌ Iltimos, javob yozing.")
        return
    if field == "phone" and not _looks_like_phone(text):
        await message.answer("❌ Telefon raqami noto'g'ri. Masalan: +998901234567", reply_markup=_phone_kb())
        return

    data = await state.get_data()
    application_id = data["application_id"]
    db_column, next_step = _FIELD_NEXT[field]
    recruiting_repo.update_application(application_id, **{db_column: text, "current_step": next_step})

    await _advance_to_step(message, state, data, next_step)


async def _advance_to_step(
    message: Message, state: FSMContext, data: dict, step: str, index_override: int | None = None
) -> None:
    if step in _FIELD_STATE:
        await state.set_state(_FIELD_STATE[step])
        kb = _phone_kb() if step == "phone" else _CANCEL_KB
        await message.answer(_FIELD_PROMPTS[step], reply_markup=kb)
        return

    if step == "role_question":
        position_key = data["position_key"]
        questions = recruiting_questions.questions_for(position_key)
        index = index_override if index_override is not None else 0
        await state.update_data(question_index=index, follow_up_count=data.get("follow_up_count", 0))
        await state.set_state(RecruitingStates.role_question)
        recruiting_repo.update_application(data["application_id"], current_step="role_question")
        if index < len(questions):
            await message.answer(questions[index][1], reply_markup=_CANCEL_KB)
        else:
            await _finish_role_questions(message, state, data)
        return


# ------------------------------------------------------------- rol savollari --


async def handle_role_question(message: Message, state: FSMContext, openai_client: AsyncOpenAI | None) -> None:
    text = (message.text or "").strip()
    if not text:
        await message.answer("❌ Iltimos, javob yozing.")
        return

    data = await state.get_data()
    application_id = data["application_id"]
    position_key = data["position_key"]
    questions = recruiting_questions.questions_for(position_key)
    index = data["question_index"]
    q_key, q_text = questions[index]

    recruiting_repo.add_answer(application_id, q_key, q_text, text, answer_source="text")

    follow_up_count = data.get("follow_up_count", 0)
    if follow_up_count < RECRUITING_MAX_FOLLOW_UPS:
        follow_up_question = await recruiting_followup.decide_follow_up(openai_client, q_text, text)
        if follow_up_question:
            new_count = recruiting_repo.increment_follow_up_count(application_id)
            await state.update_data(
                follow_up_count=new_count,
                follow_up_question_key=q_key,
                follow_up_question_text=follow_up_question,
            )
            await state.set_state(RecruitingStates.follow_up)
            await message.answer(follow_up_question, reply_markup=_CANCEL_KB)
            return

    await _advance_to_step(message, state, data, "role_question", index_override=index + 1)


async def handle_follow_up_answer(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text:
        await message.answer("❌ Iltimos, javob yozing.")
        return

    data = await state.get_data()
    application_id = data["application_id"]
    q_key = data["follow_up_question_key"]
    q_text = data["follow_up_question_text"]
    recruiting_repo.add_answer(application_id, q_key, q_text, text, answer_source="text", is_follow_up=True)

    index = data["question_index"]
    await _advance_to_step(message, state, data, "role_question", index_override=index + 1)


async def _finish_role_questions(message: Message, state: FSMContext, data: dict) -> None:
    position_key = data["position_key"]
    math_q = recruiting_questions.math_question_for(position_key)
    if math_q:
        await state.set_state(RecruitingStates.math_question)
        await message.answer(math_q.text, reply_markup=_math_keyboard(data["application_id"], math_q))
        return

    await _ask_motivation(message, state)


async def handle_math_choice(callback: CallbackQuery, state: FSMContext) -> None:
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer()
        return
    _, application_id_str, choice_key = parts
    application_id = int(application_id_str)

    data = await state.get_data()
    if data.get("application_id") != application_id:
        await callback.answer("Bu savol sizga tegishli emas yoki eskirgan.", show_alert=True)
        return

    position_key = data["position_key"]
    math_q = recruiting_questions.math_question_for(position_key)
    if math_q is None:
        await callback.answer()
        return

    chosen = next((c for c in math_q.choices if c.key == choice_key), None)
    if chosen is None:
        await callback.answer()
        return

    correct = choice_key == math_q.correct_key
    recruiting_repo.add_answer(application_id, math_q.key, math_q.text, chosen.label, answer_source="text")

    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("Qabul qilindi ✅")

    if callback.message:
        await _ask_motivation(callback.message, state)


# -------------------------------------------------------------- motivatsiya --


async def _ask_motivation(message: Message, state: FSMContext) -> None:
    await state.set_state(RecruitingStates.motivation)
    await message.answer(_MOTIVATION_PROMPT, reply_markup=_CANCEL_KB)


async def handle_motivation_voice(
    message: Message, state: FSMContext, openai_client: AsyncOpenAI | None
) -> None:
    voice = message.voice
    if voice is None:
        return

    if voice.duration and voice.duration > RECRUITING_MAX_VOICE_SECONDS:
        await message.answer(
            f"❌ Ovozli xabar {RECRUITING_MAX_VOICE_SECONDS} soniyadan uzun bo'lmasligi kerak. "
            "Iltimos, qisqaroq ovozli xabar yoki matn yuboring."
        )
        return

    transcript = await recruiting_voice.transcribe_voice(message.bot, voice, openai_client)
    if not transcript:
        await message.answer(
            "Ovozingizni tanib bo'lmadi. Iltimos, javobingizni matn ko'rinishida yozib yuboring."
        )
        return

    await _finish_application(message, state, transcript, answer_source="voice", openai_client=openai_client)


async def handle_motivation_text(
    message: Message, state: FSMContext, openai_client: AsyncOpenAI | None
) -> None:
    text = (message.text or "").strip()
    if not text:
        await message.answer("❌ Iltimos, javob yozing yoki ovozli xabar yuboring.")
        return

    await _finish_application(message, state, text, answer_source="text", openai_client=openai_client)


async def _finish_application(
    message: Message, state: FSMContext, motivation_text: str, answer_source: str, openai_client: AsyncOpenAI | None
) -> None:
    data = await state.get_data()
    application_id = data["application_id"]
    position_key = data["position_key"]

    recruiting_repo.update_application(
        application_id, motivation_text=motivation_text, current_step="submitted", status="awaiting_review"
    )
    recruiting_repo.add_answer(
        application_id, "motivation", _MOTIVATION_QUESTION_TEXT, motivation_text, answer_source=answer_source
    )

    audit.log_event(
        audit.EVENT_RECRUITING_APPLICATION_SUBMITTED,
        actor_id=message.from_user.id if message.from_user else None,
        target_id=application_id,
    )

    await message.answer(
        "Rahmat! Javoblaringiz qabul qilindi. Saturn jamoasi vakili natija bo'yicha siz bilan bog'lanadi.",
        reply_markup=ReplyKeyboardRemove(),
    )
    await state.clear()

    # Baholash/karta xatosi nomzodga yuborilgan yakuniy xabarni orqaga
    # qaytarmaydi — u allaqachon jo'natildi. Xato faqat log qilinadi.
    try:
        await _run_assessment_and_notify_founder(message, application_id, position_key, openai_client)
    except Exception as error:  # noqa: BLE001
        logger.error("Rekruting tahlili/karta yuborishda xato (application_id=%s): %r", application_id, error)


async def _run_assessment_and_notify_founder(
    message: Message, application_id: int, position_key: str, openai_client: AsyncOpenAI | None
) -> None:
    application = recruiting_repo.get_application(application_id)
    vacancy = recruiting_repo.get_vacancy(application["vacancy_id"])
    answers = recruiting_repo.get_answers(application_id)

    math_q = recruiting_questions.math_question_for(position_key)
    math_correct: bool | None = None
    if math_q:
        math_answer = next((a for a in answers if a["question_key"] == math_q.key), None)
        if math_answer:
            correct_label = next(c.label for c in math_q.choices if c.key == math_q.correct_key)
            math_correct = math_answer["answer_text"] == correct_label

    deterministic_result = recruiting_scoring.score_application(position_key, application, answers, math_correct)
    ai_summary = await recruiting_scoring.summarize(openai_client, position_key, answers, deterministic_result)

    rubric_version = recruiting_rubric.ensure_rubric_version(position_key)
    recruiting_repo.save_assessment(
        application_id,
        rubric_version["id"],
        deterministic_result["overall_result"],
        deterministic_result["criteria_scores"],
        deterministic_result["strengths"],
        deterministic_result["risks"],
        ai_summary,
        source="ai" if openai_client is not None else "deterministic",
    )
    audit.log_event(
        audit.EVENT_RECRUITING_ASSESSMENT_COMPLETED,
        target_id=application_id,
        new_value=deterministic_result["overall_result"],
    )

    assessment = recruiting_repo.get_assessment(application_id)
    follow_up_questions = [a["question_text"] for a in answers if a["is_follow_up"]]
    card_text = recruiting_card.format_candidate_card(
        application, vacancy, assessment, rubric_version, follow_up_questions
    )
    await message.bot.send_message(
        FOUNDER_ID, card_text, reply_markup=recruiting_card.candidate_review_keyboard(application_id)
    )


# --------------------------------------------------------- Founder ko'rib chiqishi --


async def _handle_founder_decision(callback: CallbackQuery, decision: str, confirmation_text: str) -> None:
    if not await permissions.ensure_permission(callback, permissions.ACTION_RECRUITING_REVIEW):
        return

    application_id = int(callback.data.split(":", 1)[1])
    application = recruiting_repo.get_application(application_id)
    if application is None or application["status"] != "awaiting_review":
        await callback.answer("Ariza topilmadi yoki allaqachon ko'rib chiqilgan.", show_alert=True)
        return

    decided_by = callback.from_user.id if callback.from_user else FOUNDER_ID
    recruiting_repo.set_founder_decision(application_id, decision, decided_by)
    audit.log_event(
        audit.EVENT_RECRUITING_FOUNDER_DECISION, actor_id=decided_by, target_id=application_id, new_value=decision
    )

    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer(confirmation_text)


async def handle_more_questions(callback: CallbackQuery) -> None:
    if not await permissions.ensure_permission(callback, permissions.ACTION_RECRUITING_REVIEW):
        return

    application_id = int(callback.data.split(":", 1)[1])
    application = recruiting_repo.get_application(application_id)
    if application is None:
        await callback.answer("Ariza topilmadi.", show_alert=True)
        return

    answers = recruiting_repo.get_answers(application_id)
    follow_ups = [a["question_text"] for a in answers if a["is_follow_up"]]
    if follow_ups:
        body = "Suhbatda so'rash mumkin bo'lgan qo'shimcha savollar:\n" + "\n".join(f"- {q}" for q in follow_ups)
    else:
        body = "Qo'shimcha aniqlashtiruvchi savol qayd etilmagan — nomzod bilan to'g'ridan-to'g'ri bog'lanib so'rashingiz mumkin."

    text = f"📞 Nomzod telefon raqami: {application.get('phone') or '-'}\n\n{body}"
    if callback.message:
        await callback.message.answer(text)
    await callback.answer()


# -------------------------------------------------------------- vakansiyalar --


async def cmd_vacancies(message: Message) -> None:
    if not await permissions.ensure_permission(message, permissions.ACTION_MANAGE_VACANCIES):
        return

    vacancies = recruiting_repo.list_vacancies(active_only=False)
    if not vacancies:
        await message.answer("Vakansiyalar topilmadi.")
        return

    for vacancy in vacancies:
        status = "✅ Faol" if vacancy["is_active"] else "⛔ Nofaol"
        toggle_text = "⛔ O'chirish" if vacancy["is_active"] else "✅ Yoqish"
        kb = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text=toggle_text, callback_data=f"rec_vac_toggle:{vacancy['id']}")]]
        )
        await message.answer(f"{status} — {vacancy['title']} ({vacancy['position_key']})", reply_markup=kb)


async def handle_vacancy_toggle(callback: CallbackQuery) -> None:
    if not await permissions.ensure_permission(callback, permissions.ACTION_MANAGE_VACANCIES):
        return

    vacancy_id = int(callback.data.split(":", 1)[1])
    vacancy = recruiting_repo.get_vacancy(vacancy_id)
    if vacancy is None:
        await callback.answer("Vakansiya topilmadi.", show_alert=True)
        return

    new_active = not bool(vacancy["is_active"])
    recruiting_repo.set_vacancy_active(vacancy_id, new_active)
    status = "✅ Faol" if new_active else "⛔ Nofaol"
    toggle_text = "⛔ O'chirish" if new_active else "✅ Yoqish"
    if callback.message:
        await callback.message.edit_text(
            f"{status} — {vacancy['title']} ({vacancy['position_key']})",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text=toggle_text, callback_data=f"rec_vac_toggle:{vacancy_id}")]]
            ),
        )
    await callback.answer("Yangilandi ✅")


# ---------------------------------------------------------------------- API --


async def start_application_from_deeplink(message: Message, state: FSMContext) -> None:
    """``main.py``dagi ``/start apply`` deep-link uchun — ``/apply``
    bilan bir xil oqim."""
    await cmd_apply(message, state)


def register(dp: Dispatcher, openai_client: AsyncOpenAI) -> None:
    @dp.message(Command("apply"))
    async def apply_handler(message: Message, state: FSMContext) -> None:
        await cmd_apply(message, state)

    @dp.message(StateFilter(*_ALL_STATES), F.text == _CANCEL_TEXT)
    async def cancel_handler(message: Message, state: FSMContext) -> None:
        await handle_cancel(message, state)

    @dp.callback_query(F.data.in_(("rec_consent:yes", "rec_consent:no")), StateFilter(RecruitingStates.consent))
    async def consent_handler(callback: CallbackQuery, state: FSMContext) -> None:
        await handle_consent(callback, state)

    @dp.message(StateFilter(RecruitingStates.consent))
    async def consent_reminder_handler(message: Message) -> None:
        await message.answer("Iltimos, yuqoridagi tugmalardan birini tanlang.")

    @dp.callback_query(F.data.startswith("rec_vacancy:"), StateFilter(RecruitingStates.choosing_vacancy))
    async def vacancy_choice_handler(callback: CallbackQuery, state: FSMContext) -> None:
        await handle_vacancy_choice(callback, state)

    @dp.message(StateFilter(*_FIELD_STATE.values()))
    async def field_answer_handler(message: Message, state: FSMContext) -> None:
        await handle_field_answer(message, state)

    @dp.message(StateFilter(RecruitingStates.role_question))
    async def role_question_handler(message: Message, state: FSMContext) -> None:
        await handle_role_question(message, state, openai_client)

    @dp.message(StateFilter(RecruitingStates.follow_up))
    async def follow_up_handler(message: Message, state: FSMContext) -> None:
        await handle_follow_up_answer(message, state)

    @dp.callback_query(F.data.startswith("rec_math:"), StateFilter(RecruitingStates.math_question))
    async def math_choice_handler(callback: CallbackQuery, state: FSMContext) -> None:
        await handle_math_choice(callback, state)

    @dp.message(StateFilter(RecruitingStates.motivation), F.voice)
    async def motivation_voice_handler(message: Message, state: FSMContext) -> None:
        await handle_motivation_voice(message, state, openai_client)

    @dp.message(StateFilter(RecruitingStates.motivation))
    async def motivation_text_handler(message: Message, state: FSMContext) -> None:
        await handle_motivation_text(message, state, openai_client)

    @dp.message(Command("vacancies"))
    async def vacancies_handler(message: Message) -> None:
        await cmd_vacancies(message)

    @dp.callback_query(F.data.startswith("rec_vac_toggle:"))
    async def vacancy_toggle_handler(callback: CallbackQuery) -> None:
        await handle_vacancy_toggle(callback)

    @dp.callback_query(F.data.startswith("rec_interview:"))
    async def decision_interview_handler(callback: CallbackQuery) -> None:
        await _handle_founder_decision(callback, "interview", "📞 Suhbatga chaqirish belgilandi.")

    @dp.callback_query(F.data.startswith("rec_reviewing:"))
    async def decision_reviewing_handler(callback: CallbackQuery) -> None:
        await _handle_founder_decision(callback, "reviewing", "🗂 Ko'rib chiqilmoqda deb belgilandi.")

    @dp.callback_query(F.data.startswith("rec_reject:"))
    async def decision_reject_handler(callback: CallbackQuery) -> None:
        await _handle_founder_decision(callback, "rejected", "❌ Rad etildi deb belgilandi.")

    @dp.callback_query(F.data.startswith("rec_question:"))
    async def more_questions_handler(callback: CallbackQuery) -> None:
        await handle_more_questions(callback)
