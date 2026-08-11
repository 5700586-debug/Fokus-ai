"""Yulduzli bonus/intizom tizimi uchun bot komandalari.

``services/`` qatlami (star_engine, calibration, driver_checks va h.k.)
biznes logikani ushlab turadi — bu modul faqat Telegram interfeysi:
komanda/FSM orqali kirish ma'lumotlarini yig'ib, mos servis funksiyasini
chaqiradi. Ruxsat tekshiruvi ``services/permissions.py`` orqali (Founder
har doim ruxsatli), sof Founder-only amallar (``/setrule``,
``/processmonth``, ``/addvehicle``) esa mavjud ``main.py`` uslubida
to'g'ridan-to'g'ri ``FOUNDER_ID`` bilan tekshiriladi.
"""

from datetime import date, datetime

import company_time
from aiogram import Dispatcher, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup, ReplyKeyboardRemove

from config import FOUNDER_ID
from db import IntegrityError
from repositories import vehicles as vehicles_repo
from roles import is_authorized
from services import driver_checks, market_observation, permissions, star_engine, supervisor_scoring
from services import meal_plan as meal_plan_service
from services import rules as rules_service

_SKIP_TEXT = "➖ O'tkazib yuborish"


def _kb(*rows: list[str]) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=text) for text in row] for row in rows],
        resize_keyboard=True,
    )


_SKIP_KB = _kb([_SKIP_TEXT])


def _parse_date_ddmmyyyy(text: str) -> date | None:
    try:
        return datetime.strptime(text.strip(), "%d.%m.%Y").date()
    except ValueError:
        return None


class MarketLogStates(StatesGroup):
    product = State()
    variety = State()
    wholesale_price = State()
    supplier_seller = State()
    origin = State()
    quality = State()
    minimum_batch = State()
    notes = State()
    photo = State()


class DriverCheckStates(StatesGroup):
    start_km = State()
    end_km = State()
    exterior_photo = State()
    interior_photo = State()
    notes = State()


def register(dp: Dispatcher) -> None:

    # ------------------------------------------------------- /score --

    @dp.message(Command("score"))
    async def score_handler(message: Message) -> None:
        if not message.from_user or not permissions.has_permission(
            message.from_user.id, permissions.ACTION_SCORE_EMPLOYEE
        ):
            return

        parts = (message.text or "").split(maxsplit=3)
        if len(parts) < 3 or not parts[1].lstrip("-").isdigit() or not parts[2].isdigit():
            await message.answer(
                "Foydalanish: /score <user_id> <ball 0-100> [izoh]\n"
                "Masalan: /score 123456789 85 Yaxshi ishladi"
            )
            return

        user_id = int(parts[1])
        score = int(parts[2])
        comment = parts[3] if len(parts) > 3 else None

        if not 0 <= score <= 100:
            await message.answer("❌ Ball 0 dan 100 gacha bo'lishi kerak.")
            return

        score_date = company_time.today().isoformat()
        supervisor_scoring.record_score(user_id, message.from_user.id, score_date, score, comment)
        await message.answer(f"✅ {user_id} uchun {score_date} kuni ball qayd etildi: {score}")

    # ------------------------------------------------------ /mystars --

    @dp.message(Command("mystars"))
    async def mystars_handler(message: Message) -> None:
        if not message.from_user or not is_authorized(message.from_user.id):
            return

        stars = star_engine.get_current_stars(message.from_user.id)
        bonus_history = star_engine.get_bonus_history(message.from_user.id)

        lines = [f"⭐ Joriy yulduzlar: {star_engine.format_star_progress(stars)} ({stars}/5)", ""]
        if bonus_history:
            lines.append("💰 Bonus tarixi:")
            for row in bonus_history:
                lines.append(f"{row['year_month']}: {row['stars']}⭐ — {row['bonus_amount']} so'm")
        else:
            lines.append("Hali bonus tarixi yo'q.")

        await message.answer("\n".join(lines))

    # ----------------------------------------------- /setrule, /listrules --

    @dp.message(Command("setrule"))
    async def setrule_handler(message: Message) -> None:
        if not message.from_user or message.from_user.id != FOUNDER_ID:
            return

        parts = (message.text or "").split(maxsplit=2)
        if len(parts) < 3:
            await message.answer(
                "Foydalanish: /setrule <rule_key> <qiymat>\n\n/listrules — mavjud qoidalarni ko'rish"
            )
            return

        rule_key, rule_value = parts[1].strip(), parts[2].strip()
        rules_service.set_rule(rule_key, rule_value, message.from_user.id)
        await message.answer(f"✅ Qoida yangilandi: {rule_key} = {rule_value}")

    @dp.message(Command("listrules"))
    async def listrules_handler(message: Message) -> None:
        if not message.from_user or message.from_user.id != FOUNDER_ID:
            return

        rules = rules_service.list_rules()
        if not rules:
            await message.answer("Qoidalar topilmadi.")
            return

        lines = "\n".join(f"{key} = {value}" for key, value in sorted(rules.items()))
        await message.answer(f"⚙️ Joriy qoidalar:\n{lines}")

    # -------------------------------------------------------- /processmonth --

    @dp.message(Command("processmonth"))
    async def processmonth_handler(message: Message) -> None:
        if not message.from_user or message.from_user.id != FOUNDER_ID:
            return

        parts = (message.text or "").split()
        if len(parts) != 6 or not parts[1].lstrip("-").isdigit():
            await message.answer(
                "Foydalanish:\n"
                "/processmonth <user_id> <YYYY-MM> <davomat_ok:1/0> "
                "<jiddiy_buzilish_yoq:1/0> <checklist_tugallandi:1/0>\n\n"
                "Masalan: /processmonth 123456789 2026-08 1 1 1"
            )
            return

        user_id = int(parts[1])
        year_month = parts[2]

        if parts[3] not in ("0", "1") or parts[4] not in ("0", "1") or parts[5] not in ("0", "1"):
            await message.answer("❌ Oxirgi 3 qiymat 1 yoki 0 bo'lishi kerak.")
            return

        attendance_ok, no_violation, checklist_ok = (bool(int(p)) for p in parts[3:6])

        avg_score = supervisor_scoring.get_month_average(user_id, year_month)
        result = star_engine.process_month(
            user_id,
            year_month,
            star_engine.MonthInputs(
                avg_supervisor_score=avg_score,
                attendance_ok=attendance_ok,
                no_serious_violation=no_violation,
                checklist_completed=checklist_ok,
            ),
        )

        if result.already_processed:
            await message.answer(f"ℹ️ {year_month} uchun {user_id} allaqachon qayta ishlangan.")
            return

        verdict = "✅ To'liq bonusli oy" if result.full_bonus_month else "❌ Mezon bajarilmadi"
        await message.answer(
            f"{verdict}\n"
            f"O'rtacha ball: {avg_score if avg_score is not None else '-'}\n"
            f"Yulduz: {result.previous_stars} → {result.new_stars}\n"
            f"Bonus: {result.bonus_amount} so'm"
        )

    # ------------------------------------------------------- /addvehicle --

    @dp.message(Command("addvehicle"))
    async def addvehicle_handler(message: Message) -> None:
        if not message.from_user or message.from_user.id != FOUNDER_ID:
            return

        parts = (message.text or "").split(maxsplit=3)
        if len(parts) < 3 or not parts[2].lstrip("-").isdigit():
            await message.answer("Foydalanish: /addvehicle <davlat raqami> <haydovchi user_id> [model]")
            return

        plate_number = parts[1].strip()
        driver_id = int(parts[2])
        model = parts[3].strip() if len(parts) > 3 else None

        try:
            vehicle_id = vehicles_repo.create_vehicle(plate_number, model, driver_id)
        except IntegrityError:
            await message.answer(f"❌ '{plate_number}' raqamli avtomobil allaqachon mavjud.")
            return

        await message.answer(
            f"✅ Avtomobil qo'shildi (id: {vehicle_id}, raqam: {plate_number}) → haydovchi {driver_id}"
        )

    # ------------------------------------------------------------ /mealplan --

    @dp.message(Command("mealplan"))
    async def mealplan_handler(message: Message) -> None:
        if not message.from_user or not permissions.has_permission(
            message.from_user.id, permissions.ACTION_ENTER_MEAL_PLAN
        ):
            return

        parts = (message.text or "").split(maxsplit=2)
        if len(parts) < 3:
            await message.answer(
                "Foydalanish: /mealplan <KK.OO.YYYY> <ovqat tavsifi>\nMasalan: /mealplan 10.08.2026 Osh"
            )
            return

        plan_date = _parse_date_ddmmyyyy(parts[1])
        if plan_date is None:
            await message.answer("❌ Sanani KK.OO.YYYY formatida kiriting.")
            return

        description = parts[2].strip()
        meal_plan_service.set_meal_for_date(plan_date.isoformat(), description, message.from_user.id)
        await message.answer(f"✅ {parts[1]} uchun ovqat rejasi saqlandi: {description}")

    # ------------------------------------------------------------ /marketlog --

    @dp.message(Command("marketlog"))
    async def marketlog_start(message: Message, state: FSMContext) -> None:
        if not message.from_user or not permissions.has_permission(
            message.from_user.id, permissions.ACTION_LOG_MARKET_OBSERVATION
        ):
            return

        await state.set_state(MarketLogStates.product)
        await message.answer(
            "🧾 Bozor kuzatuvi. Mahsulot nomini kiriting:", reply_markup=ReplyKeyboardRemove()
        )

    @dp.message(StateFilter(MarketLogStates.product))
    async def marketlog_product(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        if not text:
            await message.answer("❌ Mahsulot nomini kiriting.")
            return

        await state.update_data(product=text)
        await state.set_state(MarketLogStates.variety)
        await message.answer("Nav/turi (bo'lmasa o'tkazib yuboring):", reply_markup=_SKIP_KB)

    @dp.message(StateFilter(MarketLogStates.variety))
    async def marketlog_variety(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        await state.update_data(variety=None if text == _SKIP_TEXT else text)
        await state.set_state(MarketLogStates.wholesale_price)
        await message.answer("Ulgurji narxi (bo'lmasa o'tkazib yuboring):", reply_markup=_SKIP_KB)

    @dp.message(StateFilter(MarketLogStates.wholesale_price))
    async def marketlog_price(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        await state.update_data(wholesale_price=None if text == _SKIP_TEXT else text)
        await state.set_state(MarketLogStates.supplier_seller)
        await message.answer("Sotuvchi/ta'minotchi (bo'lmasa o'tkazib yuboring):", reply_markup=_SKIP_KB)

    @dp.message(StateFilter(MarketLogStates.supplier_seller))
    async def marketlog_supplier(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        await state.update_data(supplier_seller=None if text == _SKIP_TEXT else text)
        await state.set_state(MarketLogStates.origin)
        await message.answer("Kelib chiqishi/mintaqasi (bo'lmasa o'tkazib yuboring):", reply_markup=_SKIP_KB)

    @dp.message(StateFilter(MarketLogStates.origin))
    async def marketlog_origin(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        await state.update_data(origin=None if text == _SKIP_TEXT else text)
        await state.set_state(MarketLogStates.quality)
        await message.answer("Sifati (bo'lmasa o'tkazib yuboring):", reply_markup=_SKIP_KB)

    @dp.message(StateFilter(MarketLogStates.quality))
    async def marketlog_quality(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        await state.update_data(quality=None if text == _SKIP_TEXT else text)
        await state.set_state(MarketLogStates.minimum_batch)
        await message.answer("Minimal partiya hajmi (bo'lmasa o'tkazib yuboring):", reply_markup=_SKIP_KB)

    @dp.message(StateFilter(MarketLogStates.minimum_batch))
    async def marketlog_batch(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        await state.update_data(minimum_batch=None if text == _SKIP_TEXT else text)
        await state.set_state(MarketLogStates.notes)
        await message.answer("Qo'shimcha izoh (bo'lmasa o'tkazib yuboring):", reply_markup=_SKIP_KB)

    @dp.message(StateFilter(MarketLogStates.notes))
    async def marketlog_notes(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        await state.update_data(notes=None if text == _SKIP_TEXT else text)
        await state.set_state(MarketLogStates.photo)
        await message.answer("Mahsulot rasmini yuboring (bo'lmasa o'tkazib yuboring):", reply_markup=_SKIP_KB)

    async def _finish_marketlog(message: Message, state: FSMContext) -> None:
        data = await state.get_data()
        await state.clear()

        market_observation.log_observation(
            employee_id=message.from_user.id,
            observation_date=company_time.today().isoformat(),
            product=data["product"],
            variety=data.get("variety"),
            photo_reference=data.get("photo_reference"),
            wholesale_price=data.get("wholesale_price"),
            supplier_seller=data.get("supplier_seller"),
            origin=data.get("origin"),
            quality=data.get("quality"),
            minimum_batch=data.get("minimum_batch"),
            notes=data.get("notes"),
        )
        await message.answer("✅ Bozor kuzatuvi saqlandi.", reply_markup=ReplyKeyboardRemove())

    @dp.message(StateFilter(MarketLogStates.photo), F.photo)
    async def marketlog_photo(message: Message, state: FSMContext) -> None:
        await state.update_data(photo_reference=message.photo[-1].file_id)
        await _finish_marketlog(message, state)

    @dp.message(StateFilter(MarketLogStates.photo))
    async def marketlog_photo_skip(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        if text != _SKIP_TEXT:
            await message.answer("📷 Rasm yuboring yoki o'tkazib yuboring.", reply_markup=_SKIP_KB)
            return

        await state.update_data(photo_reference=None)
        await _finish_marketlog(message, state)

    # ----------------------------------------------------------- /drivercheck --

    @dp.message(Command("drivercheck"))
    async def drivercheck_start(message: Message, state: FSMContext) -> None:
        if not message.from_user or not permissions.has_permission(
            message.from_user.id, permissions.ACTION_DRIVER_DAILY_CHECK
        ):
            return

        vehicle = vehicles_repo.get_vehicle_for_driver(message.from_user.id)
        if vehicle is None:
            await message.answer("❌ Sizga biriktirilgan avtomobil topilmadi. Asoschiga murojaat qiling.")
            return

        await state.set_state(DriverCheckStates.start_km)
        await message.answer(
            f"🚗 Kunlik tekshiruv — {vehicle['plate_number']}.\nSpidometr (boshlanish, km):",
            reply_markup=ReplyKeyboardRemove(),
        )

    @dp.message(StateFilter(DriverCheckStates.start_km))
    async def drivercheck_start_km(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        if not text.isdigit():
            await message.answer("❌ Faqat raqam kiriting.")
            return

        await state.update_data(start_km=int(text))
        await state.set_state(DriverCheckStates.end_km)
        await message.answer("Spidometr (tugash, km) — hali bo'lmasa o'tkazib yuboring:", reply_markup=_SKIP_KB)

    @dp.message(StateFilter(DriverCheckStates.end_km))
    async def drivercheck_end_km(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        if text == _SKIP_TEXT:
            await state.update_data(end_km=None)
        elif text.isdigit():
            await state.update_data(end_km=int(text))
        else:
            await message.answer("❌ Faqat raqam kiriting yoki o'tkazib yuboring.", reply_markup=_SKIP_KB)
            return

        await state.set_state(DriverCheckStates.exterior_photo)
        await message.answer("Tashqi ko'rinish rasmi (bo'lmasa o'tkazib yuboring):", reply_markup=_SKIP_KB)

    @dp.message(StateFilter(DriverCheckStates.exterior_photo), F.photo)
    async def drivercheck_exterior_photo(message: Message, state: FSMContext) -> None:
        await state.update_data(exterior_photo_ref=message.photo[-1].file_id)
        await state.set_state(DriverCheckStates.interior_photo)
        await message.answer("Ichki ko'rinish rasmi (bo'lmasa o'tkazib yuboring):", reply_markup=_SKIP_KB)

    @dp.message(StateFilter(DriverCheckStates.exterior_photo))
    async def drivercheck_exterior_photo_skip(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        if text != _SKIP_TEXT:
            await message.answer("📷 Rasm yuboring yoki o'tkazib yuboring.", reply_markup=_SKIP_KB)
            return

        await state.update_data(exterior_photo_ref=None)
        await state.set_state(DriverCheckStates.interior_photo)
        await message.answer("Ichki ko'rinish rasmi (bo'lmasa o'tkazib yuboring):", reply_markup=_SKIP_KB)

    @dp.message(StateFilter(DriverCheckStates.interior_photo), F.photo)
    async def drivercheck_interior_photo(message: Message, state: FSMContext) -> None:
        await state.update_data(interior_photo_ref=message.photo[-1].file_id)
        await state.set_state(DriverCheckStates.notes)
        await message.answer("Qo'shimcha izoh (bo'lmasa o'tkazib yuboring):", reply_markup=_SKIP_KB)

    @dp.message(StateFilter(DriverCheckStates.interior_photo))
    async def drivercheck_interior_photo_skip(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        if text != _SKIP_TEXT:
            await message.answer("📷 Rasm yuboring yoki o'tkazib yuboring.", reply_markup=_SKIP_KB)
            return

        await state.update_data(interior_photo_ref=None)
        await state.set_state(DriverCheckStates.notes)
        await message.answer("Qo'shimcha izoh (bo'lmasa o'tkazib yuboring):", reply_markup=_SKIP_KB)

    @dp.message(StateFilter(DriverCheckStates.notes))
    async def drivercheck_notes(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        data = await state.get_data()
        await state.clear()

        notes = None if text == _SKIP_TEXT else text

        try:
            driver_checks.record_daily_check(
                driver_id=message.from_user.id,
                check_date=company_time.today().isoformat(),
                exterior_photo_ref=data.get("exterior_photo_ref"),
                interior_photo_ref=data.get("interior_photo_ref"),
                start_km=data.get("start_km"),
                end_km=data.get("end_km"),
                notes=notes,
            )
        except ValueError as error:
            await message.answer(f"❌ {error}", reply_markup=ReplyKeyboardRemove())
            return

        reminder = ""
        vehicle = vehicles_repo.get_vehicle_for_driver(message.from_user.id)
        if vehicle and data.get("end_km") is not None and driver_checks.needs_oil_change_reminder(
            vehicle["id"], data["end_km"]
        ):
            reminder = "\n\n🛠 Diqqat: moy almashtirish vaqti keldi."

        await message.answer("✅ Kunlik tekshiruv saqlandi." + reminder, reply_markup=ReplyKeyboardRemove())
