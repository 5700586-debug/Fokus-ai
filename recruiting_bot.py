"""Fokus HR — nomzod bilan Telegram'da suhbat (jonli HR intervyu uslubida).

Bu oqim ``supplier_chat_bot.py`` bilan bir xil naqsh: FAQAT nomzod
(ro'yxatdan o'tgan xodim/Founder EMAS) uchun, ichki menyu/buyruqlarga
umuman tegmaydi. Nomzod ``/apply`` yoki ``/start apply`` orqali
kiradi (qarang ``main.py``dagi kichik qo'shimcha tekshiruv).

Suhbat holati aiogram FSM (``storage.py``dagi ``SQLiteStorage``) orqali
saqlanadi — worker qayta ishga tushsa ham yo'qolmaydi.

Ko'p sonli o'xshash ketma-ket maydonlar (B/C/D bo'limlari) alohida-
alohida ``State()`` yaratish o'rniga IKKITA umumiy holat orqali
boshqariladi (``collecting_text``/``collecting_choice``) — joriy
maydon FSM ma'lumotida (``step_key``) saqlanadi, qadamlar ro'yxati
(``_STEPS_B_C``/``_STEPS_D``) esa oddiy jadval sifatida yozilgan. Bu
~18 ta deyarli bir xil maydon uchun 18 ta State/handler juftligi
yozishning oldini oladi.

Baholash har doim DETERMINISTIK (``services/recruiting_scoring.py``) —
AI faqat qisqa xulosa matni yozadi, yakuniy natijani AI hech qachon
belgilamaydi. "Talab mosligi" (``services/recruiting_fit.py``) esa
BAHOLASHDAN ATAYLAB ALOHIDA — jadval/yosh mos kelmasligi axloqiy
kamchilik emas. Founder qarori (tugmalar) mustaqil ustunda saqlanadi —
AI tavsiyasi bilan aralashmaydi."""

import logging
import re
from datetime import date

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

from config import (
    FOUNDER_ID,
    RECRUITING_BRANCH_NAMES,
    RECRUITING_MAX_FOLLOW_UPS,
    RECRUITING_MAX_VOICE_SECONDS,
    RECRUITING_MIN_AGE,
)
from repositories import recruiting as recruiting_repo
from services import (
    audit,
    permissions,
    recruiting_card,
    recruiting_fit,
    recruiting_followup,
    recruiting_privacy,
    recruiting_questions,
    recruiting_redflags,
    recruiting_rubric,
    recruiting_scoring,
    recruiting_voice,
)

logger = logging.getLogger(__name__)


class RecruitingStates(StatesGroup):
    consent = State()
    choosing_vacancy = State()
    collecting_text = State()
    collecting_choice = State()
    role_question = State()
    follow_up = State()
    math_question = State()
    motivation = State()
    candidate_photo = State()


# Real Telegram sinovida topilgan muammo: doimiy "❌ Bekor qilish"
# tugmasi tasodifan bosilib, suhbat yo'qolib qolardi. Endi bekor qilish
# FAQAT ataylab yozilgan ``/cancel`` buyrug'i orqali — tasodifan bosib
# bo'lmaydi (qarang ``handle_cancel`` — ``/cancel`` uchun FSM holatiga
# emas, to'g'ridan-to'g'ri DB'ga tayanadi, chunki main.py'dagi global
# middleware "/" bilan boshlangan xabarlar uchun holatni handler
# ishga tushishidan OLDIN allaqachon tozalab yuboradi).
_PHONE_RE = re.compile(r"^\+?\d{7,15}$")

_NO_VACANCY_TEXT = "Hozircha faol vakansiya mavjud emas. Murojaatingiz uchun rahmat."

_CONSENT_TEXT = (
    "Assalomu alaykum 👋\n"
    "Sizni Saturn jamoasida ko'rsak, xursand bo'lamiz 😊\n"
    "Bir nechta oddiy savol beraman. Boshlaymizmi?"
)

_YES_NO_MAP = {"yes": 1, "no": 0}


def _valid_birth_year(text: str) -> bool:
    if not text.strip().isdigit():
        return False
    year = int(text.strip())
    return 1940 <= year <= date.today().year - 10


def _looks_like_phone(text: str) -> bool:
    cleaned = re.sub(r"[\s\-()]", "", text.strip())
    return bool(_PHONE_RE.match(cleaned))


# --------------------------------------------------------------- qadamlar --
# B bo'limi (asosiy ma'lumotlar) + C bo'limi (moslik filtri). ``kind``:
# "text" — erkin matn, "phone" — telefon (tugma/matn), "choice" — tugma.
_STEPS_B_C: list[dict] = [
    {"key": "full_name", "kind": "text", "prompt": "Ism-familiyangizni kiriting:", "column": "full_name"},
    {
        "key": "birth_year", "kind": "text", "prompt": "Tug'ilgan yilingizni yozing (masalan: 2000):",
        "column": "birth_year", "validator": _valid_birth_year,
        "error": "❌ Iltimos, tug'ilgan yilni to'g'ri raqamda yozing (masalan: 2000).", "to_int": True,
    },
    {"key": "phone", "kind": "phone", "prompt": "Telefon raqamingizni yuboring (tugma orqali yoki yozib):", "column": "phone"},
    {"key": "residence_area", "kind": "text", "prompt": "Qaysi hudud yoki tumanda yashaysiz?", "column": "residence_area"},
    {
        "key": "preferred_branch", "kind": "choice", "prompt": "Qaysi filialda ishlamoqchisiz?",
        "column": "preferred_branch",
        "options": [(name, name) for name in RECRUITING_BRANCH_NAMES],
    },
    {"key": "start_date", "kind": "text", "prompt": "Ishni qachondan boshlay olasiz?", "column": "start_date_text"},
    {
        "key": "shift_preference", "kind": "choice", "prompt": "Qaysi smenada ishlay olasiz?", "column": "shift_preference",
        "options": [("kunduzgi", "🌤 Kunduzgi"), ("kechki", "🌙 Kechki"), ("almashinuvli", "🔄 Almashinuvli"), ("farqi_yoq", "🤷 Farqi yo'q")],
    },
    {
        "key": "holiday_available", "kind": "choice", "prompt": "Dam olish va bayram kunlarida ishlay olasizmi?",
        "column": "holiday_available", "options": [("yes", "✅ Ha"), ("no", "❌ Yo'q")], "value_map": _YES_NO_MAP,
    },
    {
        "key": "prev_salary", "kind": "text",
        "prompt": "Oldingi ishingizda oyiga taxminan qancha olardingiz?",
        "column": "prev_salary_text",
    },
    {
        "key": "expected_salary", "kind": "text",
        "prompt": "Bizda ishlasangiz, qancha oylik kutyapsiz?",
        "column": "expected_salary",
    },
    {
        "key": "accommodation_needed", "kind": "choice",
        "prompt": "Ishimizda ko'p vaqt oyoqda turib ishlanadi. Sizga bu to'g'ri keladimi?",
        "column": "accommodation_needed", "options": [("yes", "✅ Ha, to'g'ri keladi"), ("no", "❌ Yo'q, qiynalaman")],
        "value_map": {"yes": 0, "no": 1},
    },
]

# D bo'limi (tajriba) — faqat "talab mosligi" tekshiruvidan o'tgandan
# keyin so'raladi.
_STEPS_D: list[dict] = [
    {
        "key": "prev_employer", "kind": "text",
        "prompt": "Oldingi ish joyingiz va lavozimingiz haqida yozing (bo'lmasa \"yo'q\" deb yozing):",
        "column": "prev_employer_text",
    },
    {"key": "experience_duration", "kind": "text", "prompt": "U yerda necha yil yoki oy ishlagansiz?", "column": "experience_duration_text"},
    {"key": "leave_reason", "kind": "text", "prompt": "Nega ishdan ketgansiz (yoki hozir nega ish qidiryapsiz)?", "column": "leave_reason_text"},
    {
        "key": "pos_experience", "kind": "choice", "prompt": "Kassa yoki POS-terminalda ishlagan tajribangiz bormi?",
        "column": "pos_experience", "options": [("yes", "✅ Ha"), ("no", "❌ Yo'q")], "value_map": _YES_NO_MAP,
    },
    {
        "key": "cash_handling", "kind": "text",
        "prompt": "Naqd pul sanash, qaytim berish yoki smena yopish tajribangiz bormi? Qisqacha yozing:",
        "column": "cash_handling_text",
    },
    {
        "key": "reference_check_consent", "kind": "choice",
        "prompt": "Oldingi ish joyingizdan siz haqingizda so'rab bog'lanishimiz mumkinmi?",
        "column": "reference_check_consent", "options": [("yes", "✅ Mumkin"), ("no", "❌ Yo'q")], "value_map": _YES_NO_MAP,
    },
    {
        "key": "retention_intent", "kind": "choice",
        "prompt": "Taxminan biz bilan qancha vaqt ishlashni rejalashtiryapsiz?",
        "column": "retention_intent",
        "options": [("6oygacha", "6 oygacha"), ("6_12oy", "6-12 oy"), ("1yil_plus", "1 yil va undan ko'p")],
    },
    {
        "key": "attendance_barrier", "kind": "text",
        "prompt": "Bizning ish jadvalimizga muntazam kelishingizga xalaqit berishi mumkin bo'lgan holat bormi? (bo'lmasa \"yo'q\" deb yozing)",
        "column": "attendance_barrier_text",
    },
    {
        "key": "substance_policy", "kind": "choice",
        "prompt": (
            "Ish vaqtida chekish, telefonda o'ynash, reels ko'rish, telefonda uzoq gaplashish yoki "
            "tanishlar bilan uzoq suhbatlashish ishga halal bermasligi biz uchun muhim. Shu tartib "
            "sizga to'g'ri keladimi?"
        ),
        "column": "substance_policy_agree", "options": [("yes", "✅ Ha, to'g'ri keladi"), ("no", "❌ Yo'q")],
        "value_map": _YES_NO_MAP,
    },
    {
        "key": "criminal_record", "kind": "choice",
        "prompt": "Yana bir savol, iltimos hurmat bilan qarang: sudlanganlik tarixingiz bormi?",
        "column": "criminal_record", "options": [("yes", "✅ Ha, bor"), ("no", "❌ Yo'q")], "value_map": _YES_NO_MAP,
    },
]

_ALL_STEPS: list[dict] = _STEPS_B_C + _STEPS_D
_STEP_BY_KEY: dict[str, dict] = {step["key"]: step for step in _ALL_STEPS}
_ACCOMMODATION_TEXT_STEP = {
    "key": "accommodation_text", "kind": "text",
    "prompt": "Qanday qulaylik kerak bo'lishini qisqacha yozib bera olasizmi?",
    "column": "accommodation_text",
}
_RETENTION_REASON_STEP = {
    "key": "retention_intent_reason", "kind": "text",
    "prompt": "Tushunarli 🙂 Bunga biror alohida sabab bormi?",
    "column": "retention_intent_reason",
}
_PHOTO_PROMPT = (
    "So'nggi savol 🙂 Hozirgi oddiy bir rasmingizni yubora olasizmi? "
    "(Yubormoqchi bo'lmasangiz, \"yo'q\" deb yozing)"
)

# "Nega ketgansiz" javobida nomzod o'zi mahsulotni ruxsatsiz olgan/yegan
# holatni bilvosita aytib qo'yishi mumkin — bu kompaniya mulkiga
# munosabat/halollik bo'yicha kritik xavf, lekin yakuniy qarorni har
# doim Founder beradi (qarang services/recruiting_redflags.check_property_honesty).
_PROPERTY_HONESTY_FOLLOWUP_TEXT = (
    "Demak, do'kon mahsulotini ruxsatsiz olganingiz/yeganingiz uchun muammo bo'lgan, to'g'rimi? "
    "Hozir bu holatga qanday qaraysiz?"
)
_LEAVE_REASON_FOLLOWUP_STEP_KEY = "leave_reason_followup"

_MOTIVATION_PROMPT = (
    "Oxirgi savol: nega aynan Saturn jamoasida ishlashni xohlaysiz?\n"
    "Matn bilan yozishingiz yoki ovozli xabar (60 soniyagacha) yuborishingiz mumkin."
)
_MOTIVATION_QUESTION_TEXT = "Nega aynan Saturn jamoasida ishlashni xohlaysiz?"

_RESUME_NOTICE = "Davom etamiz — tugallanmagan arizangiz saqlangan."

_MISMATCH_CLOSING_TEXT = (
    "Javoblaringiz uchun rahmat! 🙏 Hozircha bu lavozimning asosiy shartlariga "
    "to'liq mos kelmayapsiz ko'rinadi. Ma'lumotlaringiz saqlanadi — boshqa mos "
    "imkoniyat bo'lsa, siz bilan albatta bog'lanamiz."
)

# Real Telegram sinovidan keyingi talab: nomzod bezarar hazil qilsa,
# sovuq "Tushunmadim" o'rniga iliq javob berilsin, so'ng javobsiz qolgan
# savol qayta so'raladi (ballga ta'sir qilmaydi — qarang
# services/recruiting_followup.detect_humor).
_HUMOR_ACK_TEXT = "😂 Zo'r hazil ekan. Endi jiddiylashamiz 🙂"


def _phone_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Raqamni yuborish", request_contact=True)]],
        resize_keyboard=True,
    )


def _consent_kb() -> InlineKeyboardMarkup:
    # Faqat "Boshlash" tugmasi — "Bekor qilish" tugmasi ATAYLAB
    # ko'rsatilmaydi (real Telegram sinovi bo'yicha talab). Bekor
    # qilish faqat ``/cancel`` buyrug'i orqali.
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="✅ Boshlash", callback_data="rec_consent:yes")]]
    )


def _vacancy_kb(vacancies: list[dict]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=v["title"], callback_data=f"rec_vacancy:{v['id']}")]
            for v in vacancies
        ]
    )


def _choice_kb(step_key: str, options: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=label, callback_data=f"rec_choice:{step_key}:{value}")] for value, label in options]
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
    first_step = _ALL_STEPS[0]
    recruiting_repo.update_application(application_id, current_step=first_step["key"])

    audit.log_event(
        audit.EVENT_RECRUITING_APPLICATION_STARTED, actor_id=candidate_id, target_id=application_id
    )

    await state.update_data(
        application_id=application_id, vacancy_id=vacancy_id, position_key=vacancy["position_key"], step_index=0
    )
    await callback.answer()
    if callback.message:
        await callback.message.answer(f"Ajoyib! \"{vacancy['title']}\" lavozimiga ariza boshladik.", reply_markup=ReplyKeyboardRemove())
    await _send_step_prompt(callback.message, state, first_step)


async def handle_cancel(message: Message, state: FSMContext) -> None:
    # ``/cancel`` — main.py'dagi ``_ClearStaleStateMiddleware`` "/"
    # bilan boshlangan HAR QANDAY xabar uchun FSM holatini bu handler
    # ishga tushishidan OLDIN allaqachon tozalab yuboradi — shuning
    # uchun ariza ID'sini FSM ma'lumotidan emas, to'g'ridan-to'g'ri
    # DB'dan (nomzod Telegram ID'si bo'yicha) olamiz.
    await state.clear()
    candidate_id = message.from_user.id if message.from_user else None
    application = recruiting_repo.get_in_progress_application(candidate_id) if candidate_id else None
    if application is None:
        await message.answer("Hozircha faol arizangiz yo'q.")
        return

    recruiting_repo.cancel_application(application["id"])
    audit.log_event(
        audit.EVENT_RECRUITING_APPLICATION_CANCELLED,
        actor_id=candidate_id,
        target_id=application["id"],
    )
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
    step_key = application.get("current_step") or _ALL_STEPS[0]["key"]

    if step_key in _STEP_BY_KEY:
        index = _ALL_STEPS.index(_STEP_BY_KEY[step_key])
        await state.update_data(step_index=index)
        await message.answer(_RESUME_NOTICE)
        await _send_step_prompt(message, state, _ALL_STEPS[index])
        return

    if step_key == "role_question":
        questions = recruiting_questions.questions_for(position_key)
        answers = recruiting_repo.get_answers(application["id"])
        question_keys = {key for key, _ in questions}
        answered = sum(1 for a in answers if a["question_key"] in question_keys and not a["is_follow_up"])
        await state.update_data(question_index=answered)
        await message.answer(_RESUME_NOTICE)
        await _advance_role_questions(message, state, await state.get_data(), answered)
        return

    if step_key == "math_question":
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


# ------------------------------------------------------- qadamlar (B/C/D) --


async def _send_step_prompt(message: Message, state: FSMContext, step: dict) -> None:
    await state.update_data(step_key=step["key"])
    if step["kind"] == "phone":
        await state.set_state(RecruitingStates.collecting_text)
        await message.answer(step["prompt"], reply_markup=_phone_kb())
        return
    if step["kind"] == "choice":
        await state.set_state(RecruitingStates.collecting_choice)
        await message.answer(step["prompt"], reply_markup=_choice_kb(step["key"], step["options"]))
        return
    await state.set_state(RecruitingStates.collecting_text)
    await message.answer(step["prompt"])


async def _advance_after_step(message: Message, state: FSMContext, data: dict) -> None:
    """Joriy qadamdan keyingi qadamga o'tadi. C bo'limi (moslik filtri)
    tugagach, bir marta ``fit_result`` hisoblanadi — mos kelmasa D/E
    bo'limlari BUTUNLAY o'tkazib yuboriladi (suhbat behuda cho'zilmaydi)."""
    index = data["step_index"] + 1
    await state.update_data(step_index=index)

    if index == len(_STEPS_B_C):
        mismatched = await _check_fit_and_maybe_finish(message, state, data)
        if mismatched:
            return

    if index < len(_ALL_STEPS):
        recruiting_repo.update_application(data["application_id"], current_step=_ALL_STEPS[index]["key"])
        await _send_step_prompt(message, state, _ALL_STEPS[index])
        return

    # B+C+D tugadi -> vaziyatli savollar (E).
    recruiting_repo.update_application(data["application_id"], current_step="role_question")
    await state.update_data(question_index=0)
    await _advance_role_questions(message, state, await state.get_data(), 0)


async def _check_fit_and_maybe_finish(message: Message, state: FSMContext, data: dict) -> bool:
    """``True`` — talab mosligi MISMATCH, ariza shu yerda (D/E'siz)
    yakunlandi. ``False`` — mos, davom etadi."""
    application_id = data["application_id"]
    application = recruiting_repo.get_application(application_id)
    vacancy = recruiting_repo.get_vacancy(application["vacancy_id"])

    availability_summary = (
        f"Smena: {application.get('shift_preference') or '-'}; "
        f"bayramda: {'ha' if application.get('holiday_available') else 'yo‘q'}"
    )
    recruiting_repo.update_application(application_id, availability_text=availability_summary)
    application["availability_text"] = availability_summary

    fit_result, fit_reason = recruiting_fit.compute_fit(
        birth_year=application.get("birth_year"),
        shift_preference=application.get("shift_preference"),
        holiday_available=application.get("holiday_available"),
        vacancy=vacancy,
        min_age=RECRUITING_MIN_AGE,
    )
    recruiting_repo.update_application(application_id, fit_result=fit_result, fit_reason=fit_reason)

    if fit_result == recruiting_fit.MISMATCH:
        await _finish_mismatch_application(message, state, application_id, application["vacancy_id"], fit_reason)
        return True
    return False


async def handle_text_step_answer(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    step_key = data.get("step_key")
    if step_key is None:
        return

    text = (message.text or "").strip()
    if step_key == "phone" and message.contact is not None:
        text = message.contact.phone_number

    if not text:
        await message.answer("❌ Iltimos, javob yozing.")
        return

    if step_key == "accommodation_text":
        recruiting_repo.update_application(data["application_id"], accommodation_text=text)
        await _advance_after_step(message, state, data)
        return
    if step_key == "retention_intent_reason":
        recruiting_repo.update_application(data["application_id"], retention_intent_reason=text)
        await _advance_after_step(message, state, data)
        return
    if step_key == _LEAVE_REASON_FOLLOWUP_STEP_KEY:
        recruiting_repo.update_application(data["application_id"], leave_reason_followup_text=text)
        await _advance_after_step(message, state, data)
        return
    if step_key == "leave_reason":
        await _handle_leave_reason_answer(message, state, data, text)
        return

    step = _STEP_BY_KEY.get(step_key)
    if step is None:
        return

    if step["kind"] == "phone":
        if not _looks_like_phone(text):
            await message.answer("❌ Telefon raqami noto'g'ri. Masalan: +998901234567", reply_markup=_phone_kb())
            return
    validator = step.get("validator")
    if validator and not validator(text):
        await message.answer(step.get("error", "❌ Noto'g'ri format."))
        return

    value = int(text) if step.get("to_int") else text
    recruiting_repo.update_application(data["application_id"], **{step["column"]: value})
    await _advance_after_step(message, state, data)


async def _handle_leave_reason_answer(message: Message, state: FSMContext, data: dict, text: str) -> None:
    """"Nega ketgansiz" — oddiy erkin savol, lekin real Telegram
    sinovida nomzod bu yerda aloqasiz/tushunarsiz javob berishi (masalan
    savolga umuman bog'liq bo'lmagan gap) yoki bilvosita kompaniya
    mulkini ruxsatsiz olganini aytib qo'yishi mumkin edi. Ikkalasi ham
    keyingi savolga o'tishdan OLDIN BITTA aniqlashtiruvchi savol talab
    qiladi."""
    application_id = data["application_id"]
    leave_reason_prompt = _STEP_BY_KEY["leave_reason"]["prompt"]

    if await recruiting_followup.detect_humor(_CURRENT_OPENAI_CLIENT.get(), leave_reason_prompt, text):
        await message.answer(_HUMOR_ACK_TEXT)
        await message.answer(leave_reason_prompt)
        return

    recruiting_repo.update_application(application_id, leave_reason_text=text)

    if recruiting_redflags.check_property_honesty(text) == recruiting_redflags.RED:
        recruiting_repo.update_application(application_id, property_honesty_flag=1)
        await state.update_data(step_key=_LEAVE_REASON_FOLLOWUP_STEP_KEY)
        await state.set_state(RecruitingStates.collecting_text)
        await message.answer(_PROPERTY_HONESTY_FOLLOWUP_TEXT)
        return

    follow_up_question = await recruiting_followup.decide_follow_up(
        _CURRENT_OPENAI_CLIENT.get(), leave_reason_prompt, text
    )
    if follow_up_question:
        await state.update_data(step_key=_LEAVE_REASON_FOLLOWUP_STEP_KEY)
        await state.set_state(RecruitingStates.collecting_text)
        await message.answer(follow_up_question)
        return

    await _advance_after_step(message, state, data)


async def handle_choice_step_answer(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    step_key = data.get("step_key")
    parts = callback.data.split(":", 2)
    if len(parts) != 3 or step_key is None or parts[1] != step_key:
        # Eskirgan/ikki marta bosilgan tugma — joriy qadamga mos kelmaydi.
        await callback.answer()
        return

    step = _STEP_BY_KEY.get(step_key)
    if step is None:
        await callback.answer()
        return

    raw_value = parts[2]
    value_map = step.get("value_map") or {}
    stored_value = value_map.get(raw_value, raw_value)

    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("Qabul qilindi ✅")

    recruiting_repo.update_application(data["application_id"], **{step["column"]: stored_value})

    if step_key == "accommodation_needed" and raw_value == "no" and callback.message:
        await state.update_data(step_key="accommodation_text")
        await state.set_state(RecruitingStates.collecting_text)
        await callback.message.answer(_ACCOMMODATION_TEXT_STEP["prompt"])
        return

    if step_key == "retention_intent" and raw_value == "6oygacha" and callback.message:
        await state.update_data(step_key="retention_intent_reason")
        await state.set_state(RecruitingStates.collecting_text)
        await callback.message.answer(_RETENTION_REASON_STEP["prompt"])
        return

    if callback.message:
        await _advance_after_step(callback.message, state, data)


# ------------------------------------------------------------- rol savollari --


async def _advance_role_questions(message: Message, state: FSMContext, data: dict, index: int) -> None:
    position_key = data["position_key"]
    questions = recruiting_questions.questions_for(position_key)
    await state.update_data(question_index=index, follow_up_attempt=0)
    await state.set_state(RecruitingStates.role_question)
    if index < len(questions):
        await message.answer(questions[index][1])
    else:
        await _finish_role_questions(message, state, data)


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

    # Hazil bo'lsa, javob umuman SAQLANMAYDI (ballga ta'sir qilmasligi
    # uchun) — iliq javob berilib, o'sha savol qayta so'raladi.
    attempt = data.get("follow_up_attempt", 0)
    if attempt < RECRUITING_MAX_FOLLOW_UPS and await recruiting_followup.detect_humor(
        _CURRENT_OPENAI_CLIENT.get(), q_text, text
    ):
        await state.update_data(follow_up_attempt=attempt + 1)
        await message.answer(_HUMOR_ACK_TEXT)
        await message.answer(q_text)
        return

    recruiting_repo.add_answer(application_id, q_key, q_text, text, answer_source="text")
    await _maybe_ask_follow_up(message, state, data, q_key, q_text, text)


async def _maybe_ask_follow_up(
    message: Message, state: FSMContext, data: dict, q_key: str, q_text: str, answer_text: str
) -> None:
    """Bitta javobga MAKSIMAL ``RECRUITING_MAX_FOLLOW_UPS`` marta
    aniqlashtiruvchi savol beriladi (per-answer, butun suhbatga emas —
    real sinovdan keyingi tuzatuv)."""
    application_id = data["application_id"]
    attempt = data.get("follow_up_attempt", 0)
    index = data["question_index"]

    if attempt < RECRUITING_MAX_FOLLOW_UPS:
        follow_up_question = await recruiting_followup.decide_follow_up(
            _CURRENT_OPENAI_CLIENT.get(), q_text, answer_text, question_key=q_key
        )
        if follow_up_question:
            recruiting_repo.increment_follow_up_count(application_id)
            await state.update_data(
                follow_up_attempt=attempt + 1,
                follow_up_question_key=q_key,
                follow_up_question_text=follow_up_question,
            )
            await state.set_state(RecruitingStates.follow_up)
            await message.answer(follow_up_question)
            return

    await _advance_role_questions(message, state, data, index + 1)


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

    # Asl savol matni bilan (redflag tekshiruvi savol MATNIGA emas,
    # savol KALITIGA qarab ishlaydi) yana bir marta tekshiramiz — agar
    # hali ham noaniq/xavfli bo'lsa va urinish limiti tugamagan bo'lsa,
    # ikkinchi (oxirgi) aniqlashtirish so'raladi.
    original_q_text = next((q for k, q in recruiting_questions.questions_for(data["position_key"]) if k == q_key), q_text)
    await _maybe_ask_follow_up(message, state, data, q_key, original_q_text, text)


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

    recruiting_repo.add_answer(application_id, math_q.key, math_q.text, chosen.label, answer_source="text")

    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("Qabul qilindi ✅")

    if callback.message:
        await _ask_motivation(callback.message, state)


# -------------------------------------------------------------- motivatsiya --


async def _ask_motivation(message: Message, state: FSMContext) -> None:
    await state.set_state(RecruitingStates.motivation)
    await message.answer(_MOTIVATION_PROMPT)


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

    await _ask_for_photo(message, state, transcript, answer_source="voice")


async def handle_motivation_text(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text:
        await message.answer("❌ Iltimos, javob yozing yoki ovozli xabar yuboring.")
        return

    await _ask_for_photo(message, state, text, answer_source="text")


# -------------------------------------------------------------------- rasm --
# Real Telegram sinovidan keyingi qo'shimcha: suhbat oxirida nomzoddan
# oddiy rasm so'raladi. AI rasmni HECH QACHON tahlil qilmaydi — faqat
# ``file_id`` saqlanadi va Founder kartasida alohida yuboriladi, ballga
# yoki qarorga umuman ta'sir qilmaydi (qarang ``_run_assessment_and_notify_founder``).


async def _ask_for_photo(message: Message, state: FSMContext, motivation_text: str, answer_source: str) -> None:
    await state.update_data(motivation_text=motivation_text, motivation_source=answer_source)
    await state.set_state(RecruitingStates.candidate_photo)
    await message.answer(_PHOTO_PROMPT)


async def handle_candidate_photo(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    photo_file_id = message.photo[-1].file_id if message.photo else None
    await _finish_application(
        message, state, data["motivation_text"], data["motivation_source"], photo_file_id
    )


async def _finish_application(
    message: Message, state: FSMContext, motivation_text: str, answer_source: str, photo_file_id: str | None
) -> None:
    data = await state.get_data()
    application_id = data["application_id"]
    position_key = data["position_key"]
    openai_client = _CURRENT_OPENAI_CLIENT.get()

    recruiting_repo.update_application(
        application_id,
        motivation_text=motivation_text,
        candidate_photo_file_id=photo_file_id,
        current_step="submitted",
        status="awaiting_review",
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


async def _finish_mismatch_application(
    message: Message, state: FSMContext, application_id: int, vacancy_id: int, fit_reason: str | None
) -> None:
    """Talab mosligi MISMATCH bo'lsa — suhbat D/E'siz, qisqa va
    neytral yakunlanadi (nomzod "yomon" deb baholanmaydi)."""
    recruiting_repo.update_application(application_id, current_step="submitted", status="awaiting_review")

    audit.log_event(
        audit.EVENT_RECRUITING_APPLICATION_SUBMITTED,
        actor_id=message.chat.id if message.chat else None,
        target_id=application_id,
    )

    await message.answer(_MISMATCH_CLOSING_TEXT, reply_markup=ReplyKeyboardRemove())
    await state.clear()

    try:
        application = recruiting_repo.get_application(application_id)
        vacancy = recruiting_repo.get_vacancy(vacancy_id)
        rubric_version = recruiting_rubric.ensure_rubric_version(vacancy["position_key"])
        recruiting_repo.save_assessment(
            application_id,
            rubric_version["id"],
            recruiting_scoring.RESULT_MISMATCH,
            [],
            [],
            [],
            "Asosiy talab (jadval/yosh)ga mos kelmagani sababli to'liq suhbat o'tkazilmadi.",
            source="deterministic",
        )
        assessment = recruiting_repo.get_assessment(application_id)
        card_text = recruiting_card.format_candidate_card(application, vacancy, assessment, rubric_version, [])
        await message.bot.send_message(
            FOUNDER_ID, card_text, reply_markup=recruiting_card.candidate_review_keyboard(application_id)
        )
    except Exception as error:  # noqa: BLE001
        logger.error("Mismatch karta yuborishda xato (application_id=%s): %r", application_id, error)


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
        red_flags=deterministic_result["red_flags"],
        clarify_questions=deterministic_result["clarify_questions"],
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
    if application.get("candidate_photo_file_id"):
        await message.bot.send_photo(
            FOUNDER_ID, application["candidate_photo_file_id"], caption=f"📷 {application.get('full_name') or '-'}"
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


async def handle_raw_answers(callback: CallbackQuery) -> None:
    if not await permissions.ensure_permission(callback, permissions.ACTION_RECRUITING_REVIEW):
        return

    application_id = int(callback.data.split(":", 1)[1])
    application = recruiting_repo.get_application(application_id)
    if application is None:
        await callback.answer("Ariza topilmadi.", show_alert=True)
        return

    answers = recruiting_repo.get_answers(application_id)
    text = recruiting_card.format_raw_answers(application, answers)
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


class _CurrentClientHolder:
    """``handle_role_question``/``handle_follow_up_answer`` chaqiruv
    zanjirida ``openai_client``ni har bir funksiyaga alohida parametr
    sifatida o'tkazish o'rniga (ko'p bosqichli follow-up mantig'i uchun
    noqulay bo'lardi), ``register()`` chaqirilganda BIR MARTA o'rnatiladi.
    Test/ishlab chiqarishda bitta process bitta ``openai_client``
    bilan ishlaydi — global holat xavfsiz."""

    def __init__(self) -> None:
        self._client: AsyncOpenAI | None = None

    def set(self, client: AsyncOpenAI | None) -> None:
        self._client = client

    def get(self) -> AsyncOpenAI | None:
        return self._client


_CURRENT_OPENAI_CLIENT = _CurrentClientHolder()


def register(dp: Dispatcher, openai_client: AsyncOpenAI) -> None:
    _CURRENT_OPENAI_CLIENT.set(openai_client)

    @dp.message(Command("apply"))
    async def apply_handler(message: Message, state: FSMContext) -> None:
        await cmd_apply(message, state)

    @dp.message(Command("cancel"))
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

    @dp.message(StateFilter(RecruitingStates.collecting_text))
    async def text_step_handler(message: Message, state: FSMContext) -> None:
        await handle_text_step_answer(message, state)

    @dp.callback_query(F.data.startswith("rec_choice:"), StateFilter(RecruitingStates.collecting_choice))
    async def choice_step_handler(callback: CallbackQuery, state: FSMContext) -> None:
        await handle_choice_step_answer(callback, state)

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
        await handle_motivation_text(message, state)

    @dp.message(StateFilter(RecruitingStates.candidate_photo))
    async def candidate_photo_handler(message: Message, state: FSMContext) -> None:
        await handle_candidate_photo(message, state)

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

    @dp.callback_query(F.data.startswith("rec_raw:"))
    async def raw_answers_handler(callback: CallbackQuery) -> None:
        await handle_raw_answers(callback)
