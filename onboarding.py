"""Invite-asosli xodim onboarding anketasi.

Onboarding FAQAT maxsus bir martalik invite havolasi (/start <token>)
orqali boshlanadi — oddiy /start bosgan begona foydalanuvchi bu yerga
kirmaydi (buni main.py tekshiradi). Filial va lavozim invite orqali
oldindan belgilanadi va anketada so'ralmaydi; ish grafigi ham invite'da
berilgan bo'lsa so'ralmaydi.

Barcha javoblar anketa yakunlangunga qadar FSM storage (storage.py,
SQLite) orqali saqlanadi — bot qayta ishga tushsa ham yo'qolmaydi.
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
MIN_CONTACTS = 3

_SKIP_TEXT = "➖ O'tkazib yuborish"
_ADD_MORE_TEXT = "➕ Yana qo'shish"
_CONTINUE_TEXT = "➡️ Davom etish"
_CONFIRM_TEXT = "✅ Ma'lumotlar to'g'ri"
_EDIT_TEXT = "✏️ Tahrirlash"

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
    contact_more = State()
    marital_status = State()
    address_viloyat = State()
    address_tuman = State()
    address_mahalla = State()
    address_kocha = State()
    address_uy = State()
    address_xonadon = State()
    hire_date = State()
    work_schedule = State()
    planned_duration = State()
    motivation = State()
    prior_experience = State()
    emergency_contact = State()
    photo = State()
    extra_note = State()
    summary = State()


def _kb(*rows: list[str]) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t) for t in row] for row in rows],
        resize_keyboard=True,
    )


_JINSI_KB = _kb(["Erkak", "Ayol"])
_MARITAL_KB = _kb(["Turmush qurmagan", "Turmush qurgan"], ["Ajrashgan", "Beva"], ["Boshqa"])
_SKIP_KB = _kb([_SKIP_TEXT])
_CONTACT_MORE_KB = _kb([_ADD_MORE_TEXT, _CONTINUE_TEXT])
_PLANNED_DURATION_KB = _kb(
    ["3–6 oy", "6–12 oy"], ["1–2 yil", "2 yildan ko'p"], ["Aniq bilmayman"]
)
_SUMMARY_KB = _kb([_CONFIRM_TEXT], [_EDIT_TEXT])

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
        "daqiqa vaqt oladi.\n\nFamiliyangizni kiriting:",
        reply_markup=ReplyKeyboardRemove(),
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

    lines = [
        "📋 Anketangizni tekshiring:",
        "",
        f"👤 F.I.Sh.: {full_name}",
        f"🎂 Tug'ilgan sana: {data.get('birth_date')} ({data.get('age')} yosh)",
        f"⚧ Jinsi: {data.get('jinsi')}",
        f"📞 Asosiy telefon: {data.get('phone')}",
        "",
        "📇 Qo'shimcha kontaktlar:",
        contacts_lines,
        "",
        f"💍 Oilaviy holat: {data.get('marital_status')}",
        f"🏠 Manzil: {address}",
        f"🏢 Filial: {data.get('branch') or 'Umumiy (barcha filiallar)'}",
        f"💼 Lavozim: {role_name(data.get('role_key'))}",
        f"📅 Ish boshlagan sana: {data.get('hire_date')}",
        f"🕒 Ish grafigi: {data.get('work_schedule')}",
        f"⏳ Rejalashtirilgan muddat: {data.get('planned_duration')}",
        f"💬 Nega bu kompaniya: {data.get('motivation')}",
        f"📋 Oldingi tajriba: {data.get('prior_experience') or '-'}",
        f"🚨 Favqulodda kontakt: {emergency['full_name'] if emergency else '-'}",
        "📷 Rasm: yuborilgan" if data.get("photo_file_id") else "📷 Rasm: -",
    ]

    if data.get("extra_note"):
        lines.append(f"📝 Izoh: {data['extra_note']}")

    return "\n".join(lines)


def register(dp: Dispatcher) -> None:
    @dp.message(StateFilter(OnboardingStates.familiya))
    async def handle_familiya(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        if not text:
            await message.answer("❌ Familiyangizni kiriting.")
            return

        await state.update_data(familiya=text)
        await state.set_state(OnboardingStates.ism)
        await message.answer("Ismingizni kiriting:")

    @dp.message(StateFilter(OnboardingStates.ism))
    async def handle_ism(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        if not text:
            await message.answer("❌ Ismingizni kiriting.")
            return

        await state.update_data(ism=text)
        await state.set_state(OnboardingStates.otasining_ismi)
        await message.answer("Otangizning ismini kiriting:")

    @dp.message(StateFilter(OnboardingStates.otasining_ismi))
    async def handle_otasining_ismi(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        if not text:
            await message.answer("❌ Otangizning ismini kiriting.")
            return

        await state.update_data(otasining_ismi=text)
        await state.set_state(OnboardingStates.birth_date)
        await message.answer("Tug'ilgan sanangizni kiriting (KK.OO.YYYY), masalan: 01.05.2000")

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
        await message.answer("Jinsingizni tanlang:", reply_markup=_JINSI_KB)

    @dp.message(StateFilter(OnboardingStates.jinsi))
    async def handle_jinsi(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        if text not in ("Erkak", "Ayol"):
            await message.answer("Iltimos, tugmalardan birini tanlang.", reply_markup=_JINSI_KB)
            return

        await state.update_data(jinsi=text)
        await state.set_state(OnboardingStates.phone_own)
        await message.answer(
            "Asosiy telefon raqamingizni kiriting. Masalan: +998901234567",
            reply_markup=ReplyKeyboardRemove(),
        )

    @dp.message(StateFilter(OnboardingStates.phone_own))
    async def handle_phone_own(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        if not _looks_like_phone(text):
            await message.answer("❌ Telefon raqami noto'g'ri. Masalan: +998901234567")
            return

        await state.update_data(phone=text, contacts=[])
        await state.set_state(OnboardingStates.contact_full_name)
        await message.answer(
            "Endi kamida 3 ta qo'shimcha aloqa kontaktini kiritamiz "
            "(o'zingizning raqamingiz bundan alohida saqlanadi).\n\n" + _contact_prompt(1)
        )

    @dp.message(StateFilter(OnboardingStates.contact_full_name))
    async def handle_contact_full_name(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        if not text:
            await message.answer("❌ F.I.Sh.ni kiriting.")
            return

        await state.update_data(_pending_contact_name=text)
        await state.set_state(OnboardingStates.contact_phone)
        await message.answer("Telefon raqamini kiriting. Masalan: +998901234567")

    @dp.message(StateFilter(OnboardingStates.contact_phone))
    async def handle_contact_phone(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        if not _looks_like_phone(text):
            await message.answer("❌ Telefon raqami noto'g'ri. Masalan: +998901234567")
            return

        await state.update_data(_pending_contact_phone=text)
        await state.set_state(OnboardingStates.contact_relation)
        await message.answer(
            "Bu odam sizga kim bo'ladi? (masalan: ota, ona, aka, opa, turmush o'rtog'i, qarindosh)"
        )

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

        if len(contacts) < MIN_CONTACTS:
            await state.set_state(OnboardingStates.contact_full_name)
            await message.answer(_contact_prompt(len(contacts) + 1))
            return

        await state.set_state(OnboardingStates.contact_more)
        await message.answer(
            f"✅ {len(contacts)} ta kontakt qo'shildi. Yana qo'shasizmi?",
            reply_markup=_CONTACT_MORE_KB,
        )

    @dp.message(StateFilter(OnboardingStates.contact_more))
    async def handle_contact_more(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()

        if text == _ADD_MORE_TEXT:
            data = await state.get_data()
            next_index = len(data.get("contacts", [])) + 1
            await state.set_state(OnboardingStates.contact_full_name)
            await message.answer(_contact_prompt(next_index), reply_markup=ReplyKeyboardRemove())
            return

        if text != _CONTINUE_TEXT:
            await message.answer("Iltimos, tugmalardan birini tanlang.", reply_markup=_CONTACT_MORE_KB)
            return

        await state.set_state(OnboardingStates.marital_status)
        await message.answer(
            "Oilaviy holatingizni tanlang:", reply_markup=_MARITAL_KB
        )

    @dp.message(StateFilter(OnboardingStates.marital_status))
    async def handle_marital_status(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        if not text:
            await message.answer("❌ Oilaviy holatingizni tanlang.", reply_markup=_MARITAL_KB)
            return

        await state.update_data(marital_status=text)
        await state.set_state(OnboardingStates.address_viloyat)
        await message.answer(
            "Endi uy manzilingizni bosqichma-bosqich kiritamiz.\n\nViloyatni kiriting:",
            reply_markup=ReplyKeyboardRemove(),
        )

    @dp.message(StateFilter(OnboardingStates.address_viloyat))
    async def handle_address_viloyat(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        if not text:
            await message.answer("❌ Viloyatni kiriting.")
            return

        await state.update_data(viloyat=text)
        await state.set_state(OnboardingStates.address_tuman)
        await message.answer("Tuman/shaharni kiriting:")

    @dp.message(StateFilter(OnboardingStates.address_tuman))
    async def handle_address_tuman(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        if not text:
            await message.answer("❌ Tuman/shaharni kiriting.")
            return

        await state.update_data(tuman=text)
        await state.set_state(OnboardingStates.address_mahalla)
        await message.answer("Mahallani kiriting:")

    @dp.message(StateFilter(OnboardingStates.address_mahalla))
    async def handle_address_mahalla(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        if not text:
            await message.answer("❌ Mahallani kiriting.")
            return

        await state.update_data(mahalla=text)
        await state.set_state(OnboardingStates.address_kocha)
        await message.answer("Ko'chani kiriting:")

    @dp.message(StateFilter(OnboardingStates.address_kocha))
    async def handle_address_kocha(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        if not text:
            await message.answer("❌ Ko'chani kiriting.")
            return

        await state.update_data(kocha=text)
        await state.set_state(OnboardingStates.address_uy)
        await message.answer("Uy raqamini kiriting:")

    @dp.message(StateFilter(OnboardingStates.address_uy))
    async def handle_address_uy(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        if not text:
            await message.answer("❌ Uy raqamini kiriting.")
            return

        await state.update_data(uy_raqami=text)
        await state.set_state(OnboardingStates.address_xonadon)
        await message.answer(
            "Xonadon raqamini kiriting (agar mavjud bo'lmasa, o'tkazib yuboring):",
            reply_markup=_SKIP_KB,
        )

    @dp.message(StateFilter(OnboardingStates.address_xonadon))
    async def handle_address_xonadon(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        await state.update_data(xonadon_raqami=None if text == _SKIP_TEXT else text)
        await state.set_state(OnboardingStates.hire_date)
        await message.answer(
            "Ish boshlagan (yoki boshlaydigan) sanangizni kiriting (KK.OO.YYYY):",
            reply_markup=ReplyKeyboardRemove(),
        )

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
            await state.set_state(OnboardingStates.planned_duration)
            await message.answer(
                "Kompaniyada qancha muddat ishlashni rejalashtiryapsiz?",
                reply_markup=_PLANNED_DURATION_KB,
            )
            return

        await state.set_state(OnboardingStates.work_schedule)
        await message.answer("Ish grafigingizni kiriting. Masalan: 09:00–18:00")

    @dp.message(StateFilter(OnboardingStates.work_schedule))
    async def handle_work_schedule(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        if not text:
            await message.answer("❌ Ish grafigini kiriting. Masalan: 09:00–18:00")
            return

        await state.update_data(work_schedule=text)
        await state.set_state(OnboardingStates.planned_duration)
        await message.answer(
            "Kompaniyada qancha muddat ishlashni rejalashtiryapsiz?",
            reply_markup=_PLANNED_DURATION_KB,
        )

    @dp.message(StateFilter(OnboardingStates.planned_duration))
    async def handle_planned_duration(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        valid_options = {"3–6 oy", "6–12 oy", "1–2 yil", "2 yildan ko'p", "Aniq bilmayman"}
        if text not in valid_options:
            await message.answer("Iltimos, tugmalardan birini tanlang.", reply_markup=_PLANNED_DURATION_KB)
            return

        await state.update_data(planned_duration=text)
        await state.set_state(OnboardingStates.motivation)
        await message.answer(
            "Nima sababdan aynan bizning kompaniyada ishlamoqchisiz?",
            reply_markup=ReplyKeyboardRemove(),
        )

    @dp.message(StateFilter(OnboardingStates.motivation))
    async def handle_motivation(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        if not text:
            await message.answer("❌ Iltimos, javob yozing.")
            return

        await state.update_data(motivation=text)
        await state.set_state(OnboardingStates.prior_experience)
        await message.answer(
            "Oldingi ish tajribangiz haqida yozing (qayerda, qanday vazifada). "
            "Agar bo'lmasa, o'tkazib yuboring:",
            reply_markup=_SKIP_KB,
        )

    @dp.message(StateFilter(OnboardingStates.prior_experience))
    async def handle_prior_experience(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        await state.update_data(prior_experience=None if text == _SKIP_TEXT else text)

        data = await state.get_data()
        contacts = data.get("contacts", [])
        names_kb = _kb(*[[c["full_name"]] for c in contacts])
        await state.set_state(OnboardingStates.emergency_contact)
        await message.answer(
            "Favqulodda vaziyatda birinchi kimga qo'ng'iroq qilamiz?",
            reply_markup=names_kb,
        )

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
        await message.answer(
            "Endi rasmingizni yuboring (Telegram orqali surat sifatida):",
            reply_markup=ReplyKeyboardRemove(),
        )

    @dp.message(StateFilter(OnboardingStates.photo), F.photo)
    async def handle_photo(message: Message, state: FSMContext) -> None:
        photo_file_id = message.photo[-1].file_id
        await state.update_data(photo_file_id=photo_file_id)
        await state.set_state(OnboardingStates.extra_note)
        await message.answer(
            "Qo'shimcha izohingiz bo'lsa yozing. Bo'lmasa, o'tkazib yuboring:",
            reply_markup=_SKIP_KB,
        )

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
