"""Invite-asosli xodim onboarding anketasi.

Onboarding FAQAT maxsus bir martalik invite havolasi (/start <token>)
orqali boshlanadi — oddiy /start bosgan begona foydalanuvchi bu yerga
kirmaydi (buni main.py tekshiradi). Filial va lavozim invite orqali
oldindan belgilanadi va anketada so'ralmaydi; ish grafigi ham invite'da
berilgan bo'lsa so'ralmaydi.

Barcha javoblar anketa yakunlangunga qadar FSM storage (storage.py,
SQLite) orqali saqlanadi — bot qayta ishga tushsa ham yo'qolmaydi.

Kontakt: xodimning o'z telefon raqamidan tashqari aniq 2 ta qo'shimcha
ishonchli aloqa kontakti so'raladi (F.I.Sh., telefon, kim bo'lishi).
Manzil: faqat 2 savol — shahar/tuman va mahalla+uy — mavjud
``employees.tuman``/``employees.mahalla`` ustunlariga yoziladi (yangi
ustun kerak emas). Oldingi ish joyidan tavsif so'rash — ixtiyoriy,
roziliksiz eski ish beruvchiga murojaat qilinmaydi.
"""

import re
from datetime import date, datetime

from aiogram import Dispatcher, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup, ReplyKeyboardRemove

import approval
import employees
import invites
from roles import role_name

MINOR_AGE_LIMIT = 18
EXTRA_CONTACTS_COUNT = 2

_SKIP_TEXT = "➖ O'tkazib yuborish"
_CONFIRM_TEXT = "✅ Ma'lumotlar to'g'ri"
_EDIT_TEXT = "✏️ Tahrirlash"
_YES_TEXT = "Ha"
_NO_TEXT = "Yo'q"

_INVALID_INVITE_TEXT = (
    "Bu taklif havolasi yaroqli emas yoki muddati tugagan. "
    "Iltimos, Foundardan yangi havola so'rang."
)

_PRESERVED_INVITE_KEYS = (
    "invite_token",
    "role_key",
    "branch",
    "preset_work_schedule",
    "telegram_username",
)


class OnboardingStates(StatesGroup):
    familiya = State()
    ism = State()
    otasining_ismi = State()
    birth_date = State()
    jinsi = State()
    phone_own = State()
    contact_full_name = State()
    contact_phone = State()
    contact_relation = State()
    marital_status = State()
    address_city = State()
    address_mahalla_uy = State()
    hire_date = State()
    work_schedule = State()
    night_shift = State()
    teamwork_agreement = State()
    authority_agreement = State()
    planned_duration = State()
    motivation = State()
    prior_experience = State()
    prior_employer_consent = State()
    prior_employer_contact = State()
    emergency_contact = State()
    photo = State()
    extra_note = State()
    summary = State()


def _kb(*rows: list[str]) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t) for t in row] for row in rows],
        resize_keyboard=True,
        is_persistent=True,
        one_time_keyboard=False,
    )


_JINSI_KB = _kb(["Erkak", "Ayol"])
_MARITAL_KB = _kb(["Turmush qurmagan", "Turmush qurgan"], ["Ajrashgan", "Beva"], ["Boshqa"])
_SKIP_KB = _kb([_SKIP_TEXT])
_YES_NO_KB = _kb([_YES_TEXT, _NO_TEXT])
_PLANNED_DURATION_KB = _kb(
    ["3–6 oy", "6–12 oy"], ["1–2 yil", "2 yildan ko'p"], ["Aniq bilmayman"]
)
_SUMMARY_KB = _kb([_CONFIRM_TEXT], [_EDIT_TEXT])

_WORK_SCHEDULE_PROMPT = "Asosiy (odatdagi) ish grafigingizni kiriting. Masalan: 09:00–18:00"

_NIGHT_SHIFT_PROMPT = "Tungi smenada ishlay olasizmi?"
_NIGHT_SHIFT_OPTIONS = {
    "✅ Ha, doim ishlay olaman": "always",
    "🔄 Ba'zan ishlay olaman": "sometimes",
    "❌ Yo'q, faqat kunduzgi smena": "day_only",
}
_NIGHT_SHIFT_LABELS = {
    "always": "Ha, doim ishlay olaman",
    "sometimes": "Ba'zan ishlay olaman",
    "day_only": "Yo'q, faqat kunduzgi smena",
}
_NIGHT_SHIFT_KB = _kb(*[[text] for text in _NIGHT_SHIFT_OPTIONS])

_AGREE_YES_TEXT = "✅ Ha, roziman"
_AGREE_NO_TEXT = "❌ Yo'q, rozimasman"
_AGREEMENT_VALUES = {_AGREE_YES_TEXT: 1, _AGREE_NO_TEXT: 0}
_AGREEMENT_KB = _kb([_AGREE_YES_TEXT], [_AGREE_NO_TEXT])

_TEAMWORK_PROMPT = (
    "Bizda ‘bu mening ishim emas’ degan gap qabul qilinmaydi. Zarurat bo'lsa, "
    "o'z vazifangizdan tashqari jamoaga yordam berishga rozimisiz?"
)
_AUTHORITY_PROMPT = (
    "Bizda yosh emas, vazifa va mas'uliyat muhim. Sizdan yoshroq bo'lsa ham, "
    "vakolati bor rahbar yoki sizga ish o'rgatayotgan xodim topshiriq bersa, "
    "‘sen menga xo'jayin emassan’ demasdan bajarishga rozimisiz? Teng lavozimdagi "
    "sherigingiz ish yuzasidan yordam so'rasa, hamkorlik qilishingiz shart."
)

# Har bir qadamning savol matni nomlangan konstantaga chiqarilgan --
# shu bilan asl yuborish joyi VA anketa uzilib qolganda qayta
# yuboriladigan joy (``resend_current_step``) ANIQ bir xil matnni
# ishlatishi kafolatlanadi (qarang shu faylning oxiridagi funksiya).
_FAMILIYA_PROMPT = "Familiyangizni kiriting:"
_ISM_PROMPT = "Ismingizni kiriting:"
_OTASINING_ISMI_PROMPT = "Otangizning ismini kiriting:"
_BIRTH_DATE_PROMPT = "Tug'ilgan sanangizni kiriting (KK.OO.YYYY), masalan: 01.05.2000"
_JINSI_PROMPT = "Jinsingizni tanlang:"
_PHONE_OWN_PROMPT = "Asosiy telefon raqamingizni kiriting. Masalan: +998901234567"
_CONTACT_PHONE_PROMPT = "Telefon raqamini kiriting. Masalan: +998901234567"
_CONTACT_RELATION_PROMPT = (
    "Bu odam xodimga kim bo'ladi? (masalan: ota, ona, aka, opa, turmush o'rtog'i, qarindosh)"
)
_MARITAL_STATUS_PROMPT = "Oilaviy holatingizni tanlang:"
_ADDRESS_CITY_PROMPT = "Qaysi shahar yoki tumanda yashaysiz?\nMasalan: Qo'qon"
_ADDRESS_MAHALLA_UY_PROMPT = "Uy manzilingizni kiriting.\nMasalan: Alisher Navoiy ko‘chasi, 15-uy."
_HIRE_DATE_PROMPT = "Ish boshlagan (yoki boshlaydigan) sanangizni kiriting (KK.OO.YYYY):"
_PLANNED_DURATION_PROMPT = "Kompaniyada qancha muddat ishlashni rejalashtiryapsiz?"
_MOTIVATION_PROMPT = "Nima sababdan aynan bizning kompaniyada ishlamoqchisiz?"
_PRIOR_EXPERIENCE_PROMPT = (
    "Oldingi ish tajribangiz haqida yozing (qayerda, qanday vazifada). "
    "Agar bo'lmasa, o'tkazib yuboring:"
)
_PRIOR_EMPLOYER_CONSENT_PROMPT = (
    "Zarurat bo'lsa, avvalgi ish joyingizdan siz haqingizda tavsif so'rashimiz mumkinmi?"
)
_PRIOR_EMPLOYER_CONTACT_PROMPT = (
    "Avvalgi ish joyingiz yoki rahbaringizning aloqa raqamini qoldirishingiz "
    "mumkin. Bo'lmasa, o'tkazib yuboring:"
)
_PHOTO_PROMPT = "Endi rasmingizni yuboring (Telegram orqali surat sifatida):"
_EXTRA_NOTE_PROMPT = "Qo'shimcha izohingiz bo'lsa yozing. Bo'lmasa, o'tkazib yuboring:"

_PHONE_RE = re.compile(r"^\+?\d{7,15}$")


def _parse_date(text: str) -> date | None:
    try:
        return datetime.strptime(text.strip(), "%d.%m.%Y").date()
    except ValueError:
        return None


def _calculate_age(birth_date: date) -> int:
    today = date.today()
    years = today.year - birth_date.year
    if (today.month, today.day) < (birth_date.month, birth_date.day):
        years -= 1
    return years


def _looks_like_phone(text: str) -> bool:
    cleaned = re.sub(r"[\s\-()]", "", text.strip())
    return bool(_PHONE_RE.match(cleaned))


def _contact_prompt(index: int) -> str:
    return f"{index}-kontakt uchun F.I.Sh. kiriting:"


async def start_onboarding_from_invite(message: Message, state: FSMContext, token: str) -> None:
    if not message.from_user:
        return

    invite = invites.claim_invite(token, message.from_user.id)
    if invite is None:
        await message.answer(_INVALID_INVITE_TEXT, reply_markup=ReplyKeyboardRemove())
        return

    await state.clear()
    await state.update_data(
        invite_token=token,
        role_key=invite["role_key"],
        branch=invite["branch"],
        preset_work_schedule=invite.get("work_schedule"),
        telegram_username=message.from_user.username,
    )
    await state.set_state(OnboardingStates.familiya)
    await message.answer(
        "👋 Xush kelibsiz! Ishga qabul anketasini to'ldiramiz — bu bir necha "
        f"daqiqa vaqt oladi.\n\n{_FAMILIYA_PROMPT}",
        reply_markup=ReplyKeyboardRemove(),
    )


async def _prompt_night_shift(message: Message, state: FSMContext) -> None:
    await state.set_state(OnboardingStates.night_shift)
    await message.answer(_NIGHT_SHIFT_PROMPT, reply_markup=_NIGHT_SHIFT_KB)


def _agreement_label(value) -> str:
    if value is None:
        return "-"
    return "Ha" if value else "Yo'q"


async def _prompt_emergency_contact(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    contacts = data.get("contacts", [])
    names_kb = _kb(*[[c["full_name"]] for c in contacts])
    await state.set_state(OnboardingStates.emergency_contact)
    await message.answer(
        "Favqulodda vaziyatda birinchi kimga qo'ng'iroq qilamiz?",
        reply_markup=names_kb,
    )


def _build_summary(data: dict) -> str:
    full_name = " ".join(
        part for part in (data.get("familiya"), data.get("ism"), data.get("otasining_ismi")) if part
    )
    address = ", ".join(
        part
        for part in (
            data.get("viloyat"),
            data.get("tuman"),
            data.get("mahalla"),
            data.get("kocha"),
            data.get("uy_raqami"),
            f"xonadon {data['xonadon_raqami']}" if data.get("xonadon_raqami") else None,
        )
        if part
    )
    contacts = data.get("contacts", [])
    contacts_lines = "\n".join(
        f"  {i}. {c['full_name']} ({c['relation']}) — {c['phone']}"
        for i, c in enumerate(contacts, start=1)
    )
    emergency_index = data.get("emergency_contact_index")
    emergency = (
        contacts[emergency_index]
        if emergency_index is not None and 0 <= emergency_index < len(contacts)
        else None
    )

    prior_employer_consent = data.get("prior_employer_reference_consent")
    prior_employer_line = "Ha" if prior_employer_consent else "Yo'q"
    if prior_employer_consent and data.get("prior_employer_contact"):
        prior_employer_line += f" ({data['prior_employer_contact']})"

    lines = [
        "📋 Anketangizni tekshiring:",
        "",
        f"👤 F.I.Sh.: {full_name}",
        f"🎂 Tug'ilgan sana: {data.get('birth_date')} ({data.get('age')} yosh)",
        f"⚧ Jinsi: {data.get('jinsi')}",
        f"📞 Asosiy telefon: {data.get('phone')}",
        "",
        "📇 Qo'shimcha ishonchli kontaktlar:",
        contacts_lines,
        "",
        f"💍 Oilaviy holat: {data.get('marital_status')}",
        f"🏠 Manzil: {address}",
        f"🏢 Filial: {data.get('branch') or 'Umumiy (barcha filiallar)'}",
        f"💼 Lavozim: {role_name(data.get('role_key'))}",
        f"📅 Ish boshlagan sana: {data.get('hire_date')}",
        f"🕒 Ish grafigi: {data.get('work_schedule')}",
        f"🌙 Tungi smena: {_NIGHT_SHIFT_LABELS.get(data.get('night_shift_availability'), '-')}",
        f"🤝 Jamoaga yordam: {_agreement_label(data.get('teamwork_agreement'))}",
        f"🧭 Rahbar/ustoz topshirig'i: {_agreement_label(data.get('authority_cooperation_agreement'))}",
        f"⏳ Rejalashtirilgan muddat: {data.get('planned_duration')}",
        f"💬 Nega bu kompaniya: {data.get('motivation')}",
        f"📋 Oldingi tajriba: {data.get('prior_experience') or '-'}",
        f"🔓 Avvalgi ish joyidan tavsif so'rash mumkinmi: {prior_employer_line}",
        f"🚨 Favqulodda kontakt: {emergency['full_name'] if emergency else '-'}",
        "📷 Rasm: yuborilgan" if data.get("photo_file_id") else "📷 Rasm: -",
    ]

    if data.get("extra_note"):
        lines.append(f"📝 Izoh: {data['extra_note']}")

    return "\n".join(lines)


# Aksariyat qadamlar uchun -- matn va tugma o'zgarmas (statik). Ikkita
# dinamik qadam (``contact_full_name``, ``emergency_contact``,
# ``summary``) ``resend_current_step``da alohida ishlanadi, chunki
# ularning matni/tugmasi mavjud FSM ma'lumotidan quriladi.
_RESUMABLE_STATIC_STEPS: dict[str, tuple[str, ReplyKeyboardMarkup | None]] = {
    OnboardingStates.familiya.state: (_FAMILIYA_PROMPT, None),
    OnboardingStates.ism.state: (_ISM_PROMPT, None),
    OnboardingStates.otasining_ismi.state: (_OTASINING_ISMI_PROMPT, None),
    OnboardingStates.birth_date.state: (_BIRTH_DATE_PROMPT, None),
    OnboardingStates.jinsi.state: (_JINSI_PROMPT, _JINSI_KB),
    OnboardingStates.phone_own.state: (_PHONE_OWN_PROMPT, None),
    OnboardingStates.contact_phone.state: (_CONTACT_PHONE_PROMPT, None),
    OnboardingStates.contact_relation.state: (_CONTACT_RELATION_PROMPT, None),
    OnboardingStates.marital_status.state: (_MARITAL_STATUS_PROMPT, _MARITAL_KB),
    OnboardingStates.address_city.state: (_ADDRESS_CITY_PROMPT, None),
    OnboardingStates.address_mahalla_uy.state: (_ADDRESS_MAHALLA_UY_PROMPT, None),
    OnboardingStates.hire_date.state: (_HIRE_DATE_PROMPT, None),
    OnboardingStates.work_schedule.state: (_WORK_SCHEDULE_PROMPT, None),
    OnboardingStates.night_shift.state: (_NIGHT_SHIFT_PROMPT, _NIGHT_SHIFT_KB),
    OnboardingStates.teamwork_agreement.state: (_TEAMWORK_PROMPT, _AGREEMENT_KB),
    OnboardingStates.authority_agreement.state: (_AUTHORITY_PROMPT, _AGREEMENT_KB),
    OnboardingStates.planned_duration.state: (_PLANNED_DURATION_PROMPT, _PLANNED_DURATION_KB),
    OnboardingStates.motivation.state: (_MOTIVATION_PROMPT, None),
    OnboardingStates.prior_experience.state: (_PRIOR_EXPERIENCE_PROMPT, _SKIP_KB),
    OnboardingStates.prior_employer_consent.state: (_PRIOR_EMPLOYER_CONSENT_PROMPT, _YES_NO_KB),
    OnboardingStates.prior_employer_contact.state: (_PRIOR_EMPLOYER_CONTACT_PROMPT, _SKIP_KB),
    OnboardingStates.photo.state: (_PHOTO_PROMPT, None),
    OnboardingStates.extra_note.state: (_EXTRA_NOTE_PROMPT, _SKIP_KB),
}


async def resend_current_step(message: Message, state: FSMContext, current_state: str) -> bool:
    """Xodim onboarding davomida bir martalik havolani qayta bossa,
    mavjud FSM ma'lumotini O'ZGARTIRMASDAN aynan joriy savolni va
    uning tugmasini qaytadan yuboradi (anketa boshidan boshlanmaydi,
    invite qayta band qilinmaydi). ``current_state`` --
    ``state.get_state()`` natijasi (masalan ``"OnboardingStates:jinsi"``).
    ``True`` -- taniqli onboarding qadami topilib qayta yuborildi;
    ``False`` -- bu holat onboarding'ga tegishli emas, chaqiruvchi o'z
    zaxira xatti-harakatini davom ettiraveradi."""
    if current_state == OnboardingStates.contact_full_name.state:
        data = await state.get_data()
        contacts = data.get("contacts", [])
        await message.answer(_contact_prompt(len(contacts) + 1), reply_markup=ReplyKeyboardRemove())
        return True

    if current_state == OnboardingStates.emergency_contact.state:
        await _prompt_emergency_contact(message, state)
        return True

    if current_state == OnboardingStates.summary.state:
        data = await state.get_data()
        await message.answer(_build_summary(data), reply_markup=_SUMMARY_KB)
        return True

    step = _RESUMABLE_STATIC_STEPS.get(current_state)
    if step is None:
        return False

    prompt, keyboard = step
    await message.answer(prompt, reply_markup=keyboard or ReplyKeyboardRemove())
    return True


def register(dp: Dispatcher) -> None:
    @dp.message(StateFilter(OnboardingStates.familiya))
    async def handle_familiya(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        if not text:
            await message.answer("❌ Familiyangizni kiriting.")
            return

        await state.update_data(familiya=text)
        await state.set_state(OnboardingStates.ism)
        await message.answer(_ISM_PROMPT)

    @dp.message(StateFilter(OnboardingStates.ism))
    async def handle_ism(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        if not text:
            await message.answer("❌ Ismingizni kiriting.")
            return

        await state.update_data(ism=text)
        await state.set_state(OnboardingStates.otasining_ismi)
        await message.answer(_OTASINING_ISMI_PROMPT)

    @dp.message(StateFilter(OnboardingStates.otasining_ismi))
    async def handle_otasining_ismi(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        if not text:
            await message.answer("❌ Otangizning ismini kiriting.")
            return

        await state.update_data(otasining_ismi=text)
        await state.set_state(OnboardingStates.birth_date)
        await message.answer(_BIRTH_DATE_PROMPT)

    @dp.message(StateFilter(OnboardingStates.birth_date))
    async def handle_birth_date(message: Message, state: FSMContext) -> None:
        birth_date = _parse_date(message.text or "")
        if birth_date is None or birth_date > date.today():
            await message.answer(
                "❌ Sana noto'g'ri. Iltimos KK.OO.YYYY formatida qayta kiriting, "
                "masalan: 01.05.2000"
            )
            return

        await state.update_data(
            birth_date=birth_date.isoformat(), age=_calculate_age(birth_date)
        )
        await state.set_state(OnboardingStates.jinsi)
        await message.answer(_JINSI_PROMPT, reply_markup=_JINSI_KB)

    @dp.message(StateFilter(OnboardingStates.jinsi))
    async def handle_jinsi(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        if text not in ("Erkak", "Ayol"):
            await message.answer("Iltimos, tugmalardan birini tanlang.", reply_markup=_JINSI_KB)
            return

        await state.update_data(jinsi=text)
        await state.set_state(OnboardingStates.phone_own)
        await message.answer(_PHONE_OWN_PROMPT, reply_markup=ReplyKeyboardRemove())

    @dp.message(StateFilter(OnboardingStates.phone_own))
    async def handle_phone_own(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        if not _looks_like_phone(text):
            await message.answer("❌ Telefon raqami noto'g'ri. Masalan: +998901234567")
            return

        await state.update_data(phone=text, contacts=[])
        await state.set_state(OnboardingStates.contact_full_name)
        await message.answer(
            f"Endi {EXTRA_CONTACTS_COUNT} ta qo'shimcha ishonchli aloqa kontaktini "
            "kiritamiz (o'zingizning raqamingiz bundan alohida saqlanadi).\n\n"
            + _contact_prompt(1)
        )

    @dp.message(StateFilter(OnboardingStates.contact_full_name))
    async def handle_contact_full_name(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        if not text:
            await message.answer("❌ F.I.Sh.ni kiriting.")
            return

        await state.update_data(_pending_contact_name=text)
        await state.set_state(OnboardingStates.contact_phone)
        await message.answer(_CONTACT_PHONE_PROMPT)

    @dp.message(StateFilter(OnboardingStates.contact_phone))
    async def handle_contact_phone(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        if not _looks_like_phone(text):
            await message.answer("❌ Telefon raqami noto'g'ri. Masalan: +998901234567")
            return

        await state.update_data(_pending_contact_phone=text)
        await state.set_state(OnboardingStates.contact_relation)
        await message.answer(_CONTACT_RELATION_PROMPT)

    @dp.message(StateFilter(OnboardingStates.contact_relation))
    async def handle_contact_relation(message: Message, state: FSMContext) -> None:
        relation = (message.text or "").strip()
        if not relation:
            await message.answer("❌ Aloqasini yozing.")
            return

        data = await state.get_data()
        contacts = list(data.get("contacts", []))
        contacts.append(
            {
                "full_name": data.get("_pending_contact_name", ""),
                "phone": data.get("_pending_contact_phone", ""),
                "relation": relation,
            }
        )
        await state.update_data(
            contacts=contacts, _pending_contact_name=None, _pending_contact_phone=None
        )

        if len(contacts) < EXTRA_CONTACTS_COUNT:
            await state.set_state(OnboardingStates.contact_full_name)
            await message.answer(_contact_prompt(len(contacts) + 1))
            return

        await state.set_state(OnboardingStates.marital_status)
        await message.answer(
            f"✅ {len(contacts)} ta kontakt qo'shildi.\n\n{_MARITAL_STATUS_PROMPT}",
            reply_markup=_MARITAL_KB,
        )

    @dp.message(StateFilter(OnboardingStates.marital_status))
    async def handle_marital_status(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        if not text:
            await message.answer("❌ Oilaviy holatingizni tanlang.", reply_markup=_MARITAL_KB)
            return

        await state.update_data(marital_status=text)
        await state.set_state(OnboardingStates.address_city)
        await message.answer(_ADDRESS_CITY_PROMPT, reply_markup=ReplyKeyboardRemove())

    @dp.message(StateFilter(OnboardingStates.address_city))
    async def handle_address_city(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        if not text:
            await message.answer("❌ Qaysi shahar yoki tumanda yashashingizni kiriting.")
            return

        await state.update_data(tuman=text)
        await state.set_state(OnboardingStates.address_mahalla_uy)
        await message.answer(_ADDRESS_MAHALLA_UY_PROMPT)

    @dp.message(StateFilter(OnboardingStates.address_mahalla_uy))
    async def handle_address_mahalla_uy(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        if not text:
            await message.answer("❌ Mahalla va uy manzilingizni kiriting.")
            return

        await state.update_data(mahalla=text)
        await state.set_state(OnboardingStates.hire_date)
        await message.answer(_HIRE_DATE_PROMPT)

    @dp.message(StateFilter(OnboardingStates.hire_date))
    async def handle_hire_date(message: Message, state: FSMContext) -> None:
        hire_date = _parse_date(message.text or "")
        if hire_date is None:
            await message.answer("❌ Sana noto'g'ri. Iltimos KK.OO.YYYY formatida kiriting.")
            return

        await state.update_data(hire_date=hire_date.isoformat())

        data = await state.get_data()
        preset_schedule = data.get("preset_work_schedule")
        if preset_schedule:
            await state.update_data(work_schedule=preset_schedule)
            await _prompt_night_shift(message, state)
            return

        await state.set_state(OnboardingStates.work_schedule)
        await message.answer(_WORK_SCHEDULE_PROMPT)

    @dp.message(StateFilter(OnboardingStates.work_schedule))
    async def handle_work_schedule(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        if not text:
            await message.answer(f"❌ {_WORK_SCHEDULE_PROMPT}")
            return

        await state.update_data(work_schedule=text)
        await _prompt_night_shift(message, state)

    @dp.message(StateFilter(OnboardingStates.night_shift))
    async def handle_night_shift(message: Message, state: FSMContext) -> None:
        value = _NIGHT_SHIFT_OPTIONS.get((message.text or "").strip())
        if value is None:
            await message.answer(
                "Iltimos, tugmalardan birini tanlang.", reply_markup=_NIGHT_SHIFT_KB
            )
            return

        await state.update_data(night_shift_availability=value)
        await state.set_state(OnboardingStates.teamwork_agreement)
        await message.answer(_TEAMWORK_PROMPT, reply_markup=_AGREEMENT_KB)

    @dp.message(StateFilter(OnboardingStates.teamwork_agreement))
    async def handle_teamwork_agreement(message: Message, state: FSMContext) -> None:
        value = _AGREEMENT_VALUES.get((message.text or "").strip())
        if value is None:
            await message.answer(
                "Iltimos, tugmalardan birini tanlang.", reply_markup=_AGREEMENT_KB
            )
            return

        # "Yo'q" javobi anketani rad etmaydi — faqat saqlanadi va Founder
        # yakuniy qarorni o'zi qabul qiladi.
        await state.update_data(teamwork_agreement=value)
        await state.set_state(OnboardingStates.authority_agreement)
        await message.answer(_AUTHORITY_PROMPT, reply_markup=_AGREEMENT_KB)

    @dp.message(StateFilter(OnboardingStates.authority_agreement))
    async def handle_authority_agreement(message: Message, state: FSMContext) -> None:
        value = _AGREEMENT_VALUES.get((message.text or "").strip())
        if value is None:
            await message.answer(
                "Iltimos, tugmalardan birini tanlang.", reply_markup=_AGREEMENT_KB
            )
            return

        await state.update_data(authority_cooperation_agreement=value)
        await state.set_state(OnboardingStates.planned_duration)
        await message.answer(_PLANNED_DURATION_PROMPT, reply_markup=_PLANNED_DURATION_KB)

    @dp.message(StateFilter(OnboardingStates.planned_duration))
    async def handle_planned_duration(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        valid_options = {"3–6 oy", "6–12 oy", "1–2 yil", "2 yildan ko'p", "Aniq bilmayman"}
        if text not in valid_options:
            await message.answer("Iltimos, tugmalardan birini tanlang.", reply_markup=_PLANNED_DURATION_KB)
            return

        await state.update_data(planned_duration=text)
        await state.set_state(OnboardingStates.motivation)
        await message.answer(_MOTIVATION_PROMPT, reply_markup=ReplyKeyboardRemove())

    @dp.message(StateFilter(OnboardingStates.motivation))
    async def handle_motivation(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        if not text:
            await message.answer("❌ Iltimos, javob yozing.")
            return

        await state.update_data(motivation=text)
        await state.set_state(OnboardingStates.prior_experience)
        await message.answer(_PRIOR_EXPERIENCE_PROMPT, reply_markup=_SKIP_KB)

    @dp.message(StateFilter(OnboardingStates.prior_experience))
    async def handle_prior_experience(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        await state.update_data(prior_experience=None if text == _SKIP_TEXT else text)

        await state.set_state(OnboardingStates.prior_employer_consent)
        await message.answer(_PRIOR_EMPLOYER_CONSENT_PROMPT, reply_markup=_YES_NO_KB)

    @dp.message(StateFilter(OnboardingStates.prior_employer_consent))
    async def handle_prior_employer_consent(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        if text not in (_YES_TEXT, _NO_TEXT):
            await message.answer("Iltimos, tugmalardan birini tanlang.", reply_markup=_YES_NO_KB)
            return

        if text == _NO_TEXT:
            await state.update_data(
                prior_employer_reference_consent=False, prior_employer_contact=None
            )
            await _prompt_emergency_contact(message, state)
            return

        await state.update_data(prior_employer_reference_consent=True)
        await state.set_state(OnboardingStates.prior_employer_contact)
        await message.answer(_PRIOR_EMPLOYER_CONTACT_PROMPT, reply_markup=_SKIP_KB)

    @dp.message(StateFilter(OnboardingStates.prior_employer_contact))
    async def handle_prior_employer_contact(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        await state.update_data(prior_employer_contact=None if text == _SKIP_TEXT else text)
        await _prompt_emergency_contact(message, state)

    @dp.message(StateFilter(OnboardingStates.emergency_contact))
    async def handle_emergency_contact(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        data = await state.get_data()
        contacts = data.get("contacts", [])
        names = [c["full_name"] for c in contacts]

        if text not in names:
            names_kb = _kb(*[[n] for n in names])
            await message.answer("Iltimos, ro'yxatdan birini tanlang.", reply_markup=names_kb)
            return

        await state.update_data(emergency_contact_index=names.index(text))
        await state.set_state(OnboardingStates.photo)
        await message.answer(_PHOTO_PROMPT, reply_markup=ReplyKeyboardRemove())

    @dp.message(StateFilter(OnboardingStates.photo), F.photo)
    async def handle_photo(message: Message, state: FSMContext) -> None:
        photo_file_id = message.photo[-1].file_id
        await state.update_data(photo_file_id=photo_file_id)
        await state.set_state(OnboardingStates.extra_note)
        await message.answer(_EXTRA_NOTE_PROMPT, reply_markup=_SKIP_KB)

    @dp.message(StateFilter(OnboardingStates.photo))
    async def handle_photo_missing(message: Message) -> None:
        await message.answer("❌ Iltimos, rasmingizni surat (photo) sifatida yuboring.")

    @dp.message(StateFilter(OnboardingStates.extra_note))
    async def handle_extra_note(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        await state.update_data(extra_note=None if text == _SKIP_TEXT else text)

        data = await state.get_data()
        await state.set_state(OnboardingStates.summary)
        await message.answer(_build_summary(data), reply_markup=_SUMMARY_KB)

    @dp.message(StateFilter(OnboardingStates.summary))
    async def handle_summary(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()

        if text == _EDIT_TEXT:
            data = await state.get_data()
            preserved = {k: data.get(k) for k in _PRESERVED_INVITE_KEYS}
            await state.set_data(preserved)
            await state.set_state(OnboardingStates.familiya)
            await message.answer(
                "Anketani boshidan to'ldiramiz.\n\nFamiliyangizni kiriting:",
                reply_markup=ReplyKeyboardRemove(),
            )
            return

        if text != _CONFIRM_TEXT:
            await message.answer("Iltimos, tugmalardan birini tanlang.", reply_markup=_SUMMARY_KB)
            return

        if not message.from_user:
            return

        data = await state.get_data()
        user_id = message.from_user.id

        employees.submit_profile(user_id, data)

        invite_token = data.get("invite_token")
        if invite_token:
            invites.mark_completed(invite_token)

        await state.clear()
        await message.answer(
            "✅ Anketangiz qabul qilindi va Founderga ko'rib chiqish uchun yuborildi. "
            "Javobni kuting.",
            reply_markup=ReplyKeyboardRemove(),
        )

        await approval.send_for_review(message.bot, user_id)
