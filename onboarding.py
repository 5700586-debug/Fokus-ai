"""Xodim onboarding oqimi: tug'ilgan sana va 3 ta aloqa raqamini yig'ish.

Struktura har doim bir xil — o'zining raqami + 2 ta qo'shimcha kontakt.
Faqat 2-kontakt uchun talab farqlanadi: voyaga yetmaganlarda ota-ona/vakil
raqami majburiy, voyaga yetganlarda erkinroq (yaqin/ishonchli) kontakt.
"""

from datetime import date, datetime

from aiogram import Dispatcher
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, ReplyKeyboardMarkup, ReplyKeyboardRemove

from employees import save_profile

MINOR_AGE_LIMIT = 18
_CONSENT_YES = {"ha", "ha.", "yes"}
_CONSENT_NO = {"yo'q", "yo‘q", "yoq", "no"}


class OnboardingStates(StatesGroup):
    birth_date = State()
    contact1_phone = State()
    contact2_name = State()
    contact2_surname = State()
    contact2_phone = State()
    contact2_relation = State()
    contact3_name = State()
    contact3_surname = State()
    contact3_phone = State()
    contact3_relation = State()
    consent = State()


def _calculate_age(birth_date: date) -> int:
    today = date.today()
    years = today.year - birth_date.year
    if (today.month, today.day) < (birth_date.month, birth_date.day):
        years -= 1
    return years


def _parse_birth_date(text: str) -> date | None:
    try:
        return datetime.strptime(text.strip(), "%d.%m.%Y").date()
    except ValueError:
        return None


async def start_onboarding(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(OnboardingStates.birth_date)
    await message.answer(
        "👋 Ishga xush kelibsiz! Avval qisqa ro‘yxatdan o‘tamiz — bu bir necha "
        "daqiqa vaqt oladi.\n\n"
        "Tug‘ilgan sanangizni kiriting (KK.OO.YYYY), masalan: 01.05.2005",
        reply_markup=ReplyKeyboardRemove(),
    )


def register(dp: Dispatcher, menu: ReplyKeyboardMarkup) -> None:
    @dp.message(StateFilter(OnboardingStates.birth_date))
    async def handle_birth_date(message: Message, state: FSMContext) -> None:
        birth_date = _parse_birth_date(message.text or "")
        if birth_date is None or birth_date > date.today():
            await message.answer(
                "❌ Sana noto‘g‘ri. Iltimos KK.OO.YYYY formatida qayta kiriting, "
                "masalan: 01.05.2005"
            )
            return

        age = _calculate_age(birth_date)
        await state.update_data(
            birth_date=birth_date.isoformat(), age=age, is_minor=age < MINOR_AGE_LIMIT
        )
        await state.set_state(OnboardingStates.contact1_phone)
        await message.answer(
            "1️⃣ O‘zingizning asosiy telefon raqamingizni kiriting.\n"
            "Masalan: +998901234567"
        )

    @dp.message(StateFilter(OnboardingStates.contact1_phone))
    async def handle_contact1_phone(message: Message, state: FSMContext) -> None:
        phone = (message.text or "").strip()
        if not phone:
            await message.answer("❌ Telefon raqamini kiriting.")
            return

        full_name = message.from_user.full_name if message.from_user else ""
        ism, _, familiya = full_name.partition(" ")

        await state.update_data(
            contact1={
                "turi": "ozi",
                "ism": ism or "-",
                "familiya": familiya or "",
                "telefon": phone,
                "aloqasi": "O‘zi",
            }
        )

        data = await state.get_data()
        if data.get("is_minor"):
            prompt = (
                "2️⃣ Ota-onangiz yoki qonuniy vakilingizning ismini kiriting "
                "(bu raqam majburiy)."
            )
        else:
            prompt = (
                "2️⃣ Yaqin qarindosh yoki favqulodda aloqa uchun shaxsning "
                "ismini kiriting."
            )

        await state.set_state(OnboardingStates.contact2_name)
        await message.answer(prompt)

    @dp.message(StateFilter(OnboardingStates.contact2_name))
    async def handle_contact2_name(message: Message, state: FSMContext) -> None:
        name = (message.text or "").strip()
        if not name:
            await message.answer("❌ Ismni kiriting.")
            return

        await state.update_data(contact2_ism=name)
        await state.set_state(OnboardingStates.contact2_surname)
        await message.answer(
            "Familiyasini kiriting (agar mavjud bo‘lmasa \"-\" deb yozing)."
        )

    @dp.message(StateFilter(OnboardingStates.contact2_surname))
    async def handle_contact2_surname(message: Message, state: FSMContext) -> None:
        surname = (message.text or "").strip()
        await state.update_data(contact2_familiya="" if surname == "-" else surname)
        await state.set_state(OnboardingStates.contact2_phone)
        await message.answer("Telefon raqamini kiriting. Masalan: +998901234567")

    @dp.message(StateFilter(OnboardingStates.contact2_phone))
    async def handle_contact2_phone(message: Message, state: FSMContext) -> None:
        phone = (message.text or "").strip()
        if not phone:
            await message.answer("❌ Telefon raqamini kiriting.")
            return

        await state.update_data(contact2_telefon=phone)

        data = await state.get_data()
        if data.get("is_minor"):
            prompt = "Bu odam sizga kim bo‘ladi? (masalan: Otasi, Onasi, Vakili)"
        else:
            prompt = "Bu odam sizga kim bo‘ladi? (masalan: Akasi, Opasi, Qarindoshi)"

        await state.set_state(OnboardingStates.contact2_relation)
        await message.answer(prompt)

    @dp.message(StateFilter(OnboardingStates.contact2_relation))
    async def handle_contact2_relation(message: Message, state: FSMContext) -> None:
        relation = (message.text or "").strip()
        if not relation:
            await message.answer("❌ Aloqasini yozing (masalan: Otasi).")
            return

        data = await state.get_data()
        contact2 = {
            "turi": "qarindosh_yoki_vakil" if data.get("is_minor") else "yaqin_aloqa",
            "ism": data.get("contact2_ism", "-"),
            "familiya": data.get("contact2_familiya", ""),
            "telefon": data.get("contact2_telefon", ""),
            "aloqasi": relation,
        }
        await state.update_data(contact2=contact2)
        await state.set_state(OnboardingStates.contact3_name)
        await message.answer(
            "3️⃣ Yana bitta ishonchli aloqa uchun shaxsning ismini kiriting."
        )

    @dp.message(StateFilter(OnboardingStates.contact3_name))
    async def handle_contact3_name(message: Message, state: FSMContext) -> None:
        name = (message.text or "").strip()
        if not name:
            await message.answer("❌ Ismni kiriting.")
            return

        await state.update_data(contact3_ism=name)
        await state.set_state(OnboardingStates.contact3_surname)
        await message.answer(
            "Familiyasini kiriting (agar mavjud bo‘lmasa \"-\" deb yozing)."
        )

    @dp.message(StateFilter(OnboardingStates.contact3_surname))
    async def handle_contact3_surname(message: Message, state: FSMContext) -> None:
        surname = (message.text or "").strip()
        await state.update_data(contact3_familiya="" if surname == "-" else surname)
        await state.set_state(OnboardingStates.contact3_phone)
        await message.answer("Telefon raqamini kiriting. Masalan: +998901234567")

    @dp.message(StateFilter(OnboardingStates.contact3_phone))
    async def handle_contact3_phone(message: Message, state: FSMContext) -> None:
        phone = (message.text or "").strip()
        if not phone:
            await message.answer("❌ Telefon raqamini kiriting.")
            return

        await state.update_data(contact3_telefon=phone)
        await state.set_state(OnboardingStates.contact3_relation)
        await message.answer(
            "Bu odam sizga kim bo‘ladi? (masalan: Turmush o‘rtog‘i, Qarindoshi, "
            "Yaqin inson, Boshqa)"
        )

    @dp.message(StateFilter(OnboardingStates.contact3_relation))
    async def handle_contact3_relation(message: Message, state: FSMContext) -> None:
        relation = (message.text or "").strip()
        if not relation:
            await message.answer("❌ Aloqasini yozing.")
            return

        data = await state.get_data()
        contact3 = {
            "turi": "ishonchli",
            "ism": data.get("contact3_ism", "-"),
            "familiya": data.get("contact3_familiya", ""),
            "telefon": data.get("contact3_telefon", ""),
            "aloqasi": relation,
        }
        await state.update_data(contact3=contact3)
        await state.set_state(OnboardingStates.consent)
        await message.answer(
            "🔒 Ushbu ma’lumotlar (shu jumladan uchinchi shaxslarning telefon "
            "raqamlari) faqat favqulodda ish aloqasi maqsadida saqlanadi va "
            "boshqa maqsadda ishlatilmaydi.\n\n"
            "Roziligingizni tasdiqlaysizmi? (Ha / Yo‘q)"
        )

    @dp.message(StateFilter(OnboardingStates.consent))
    async def handle_consent(message: Message, state: FSMContext) -> None:
        answer = (message.text or "").strip().lower()

        if answer in _CONSENT_NO:
            await state.clear()
            await message.answer(
                "Ma’lumotlar saqlanmadi. Qayta boshlash uchun /start bosing."
            )
            return

        if answer not in _CONSENT_YES:
            await message.answer("Iltimos \"Ha\" yoki \"Yo‘q\" deb javob bering.")
            return

        if not message.from_user:
            return

        data = await state.get_data()
        save_profile(
            message.from_user.id,
            {
                "birth_date": data["birth_date"],
                "age": data["age"],
                "is_minor": data["is_minor"],
                "contacts": [data["contact1"], data["contact2"], data["contact3"]],
                "consent_given": True,
            },
        )
        await state.clear()
        await message.answer(
            "✅ Ro‘yxatdan o‘tish yakunlandi! Endi botdan to‘liq foydalanishingiz "
            "mumkin.",
            reply_markup=menu,
        )
