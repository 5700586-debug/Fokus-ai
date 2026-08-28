"""Yulduzli bonus/intizom tizimi uchun bot komandalari.

``services/`` qatlami (star_engine, calibration, driver_checks va h.k.)
biznes logikani ushlab turadi — bu modul faqat Telegram interfeysi:
komanda/FSM orqali kirish ma'lumotlarini yig'ib, mos servis funksiyasini
chaqiradi. Ruxsat tekshiruvi butunlay ``services/permissions.py`` orqali
(Founder har doim ruxsatli) — sof Founder-only amallar (``/setrule``,
``/processmonth``, ``/addvehicle``) ham shu yerda ``ACTION_*`` sifatida
ro'yxatlangan, ularga hech qanday rol biriktirilmagani uchun faqat
Founder bypass'i orqali ishlaydi.
"""

from datetime import date, datetime

import company_time
import employees
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

from config import RECRUITING_BRANCH_NAMES
from db import IntegrityError
from repositories import supplier_purchases as supplier_purchases_repo
from repositories import vehicles as vehicles_repo
from roles import is_authorized
from services import driver_checks, employee_dashboard, market_observation, permissions, star_engine, supervisor_scoring
from services import attendance as attendance_service
from services import meal_plan as meal_plan_service
from services import rules as rules_service
from services import shift_deficiency, supplier_purchase

_SKIP_TEXT = "➖ O'tkazib yuborish"


def _kb(*rows: list[str]) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=text) for text in row] for row in rows],
        resize_keyboard=True,
    )


_SKIP_KB = _kb([_SKIP_TEXT])

_SCHEDULE_OFF_TEXT = "🛌 Dam olish"
_SCHEDULE_WORK_TEXT = "🕒 Ish vaqti"
_SCHEDULE_TYPE_KB = _kb([_SCHEDULE_OFF_TEXT, _SCHEDULE_WORK_TEXT])
_SCHEDULE_NOT_EMPLOYEE_TEXT = (
    "❌ Siz tasdiqlangan xodim emassiz — grafik o'zgartirish so'rovini yubora olmaysiz."
)


def _parse_date_ddmmyyyy(text: str) -> date | None:
    try:
        return datetime.strptime(text.strip(), "%d.%m.%Y").date()
    except ValueError:
        return None


def _parse_time_hhmm(text: str) -> str | None:
    try:
        return datetime.strptime(text.strip(), "%H:%M").strftime("%H:%M")
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


class ScheduleChangeStates(StatesGroup):
    shift_date = State()
    change_type = State()
    start_time = State()
    end_time = State()
    reason = State()


class DriverCheckStates(StatesGroup):
    start_km = State()
    end_km = State()
    exterior_photo = State()
    interior_photo = State()
    notes = State()


class SupplierPurchaseStates(StatesGroup):
    quantity = State()
    new_price = State()
    price_flag_reason = State()
    new_product_name = State()
    new_product_quantity = State()
    new_product_price = State()
    allocation_branch_quantity = State()


def _format_qty(value: float) -> str:
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return text or "0"


def _format_money(value: float) -> str:
    return f"{round(value):,}".replace(",", " ")


def _parse_decimal(text: str) -> float | None:
    cleaned = (text or "").strip().replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_price(text: str) -> int | None:
    cleaned = (text or "").strip().replace(" ", "").replace("'", "").replace(",", "")
    if not cleaned.isdigit():
        return None
    return int(cleaned)


def _supplier_products_kb(products: list[dict]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(
            text=f"{product['product_name']} — {_format_qty(product['total_quantity'])} {product['unit']}",
            callback_data=f"sup_pick:{index}",
        )]
        for index, product in enumerate(products)
    ]
    rows.append([InlineKeyboardButton(text="➕ Mahsulot qo'shish", callback_data="sup_add_product")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _price_choice_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="♻️ O'zgarmagan", callback_data="sup_price_same"),
        InlineKeyboardButton(text="✏️ Yangi narx", callback_data="sup_price_new"),
    ]])


def _unit_choice_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text=unit, callback_data=f"sup_new_unit:{unit}")
            for unit in shift_deficiency.KNOWN_UNITS
        ]]
    )


def _allocation_branches_for(product: dict) -> dict[str, dict]:
    """Taqsimot uchun filiallar ro'yxati: bozorlik ro'yxatidan
    kelgan mahsulotda kim so'ragan bo'lsa o'sha filiallar (``by_branch``);
    bozorda esiga tushib qo'shilgan (ad-hoc) mahsulotda hech kim
    so'ramagan, shuning uchun mavjud filial ro'yxati (``RECRUITING_
    BRANCH_NAMES`` — hardcode emas) "so'ralgan: 0" bilan ishlatiladi."""
    by_branch = product.get("by_branch") or {}
    if by_branch:
        return by_branch
    return {branch: {"quantity": 0.0, "item_ids": []} for branch in RECRUITING_BRANCH_NAMES}


def _allocation_summary_text(
    product_name: str, unit: str, purchased_qty: float, by_branch: dict, alloc_values: dict
) -> str:
    lines = [f"🏪 Filiallarga taqsimlash — {product_name} ({_format_qty(purchased_qty)} {unit} olindi)", ""]
    for branch, info in by_branch.items():
        current = alloc_values.get(branch, 0.0)
        lines.append(
            f"{branch} — so'ralgan: {_format_qty(info['quantity'])} {unit}, "
            f"hozircha: {_format_qty(current)} {unit}"
        )
    remaining = purchased_qty - sum(alloc_values.values())
    lines.append("")
    lines.append(f"Qoldi: {_format_qty(remaining)} {unit}")
    return "\n".join(lines)


def _allocation_kb(branches: list[str], unit: str, alloc_values: dict, purchased_qty: float) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(
            text=f"{branch}: {_format_qty(alloc_values.get(branch, 0.0))} {unit}",
            callback_data=f"sup_alloc_branch:{index}",
        )]
        for index, branch in enumerate(branches)
    ]
    remaining = purchased_qty - sum(alloc_values.values())
    if abs(remaining) < 1e-9:
        rows.append([InlineKeyboardButton(text="✅ Yakunlash", callback_data="sup_alloc_finish")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _branch_report_text(report: dict) -> str:
    by_branch = report["by_branch"]
    if not by_branch:
        return "ℹ️ Bugun uchun filiallarga taqsimlangan xarid yo'q."

    sections = []
    for branch, bucket in by_branch.items():
        lines = [f"🏢 {branch}", ""]
        for item in bucket["items"]:
            lines.append(
                f"{item['product_name']} — {_format_qty(item['quantity'])} {item['unit']} × "
                f"{_format_money(item['unit_price'])} = {_format_money(item['item_total'])} so'm"
            )
        lines.append("")
        lines.append(f"💰 Jami: {_format_money(bucket['total'])} so'm")
        sections.append("\n".join(lines))

    sections.append(f"💰 Umumiy bozorlik: {_format_money(report['grand_total'])} so'm")
    return "\n\n\n".join(sections)


def _supplier_summary_text(products: list[dict]) -> str:
    if not products:
        return "ℹ️ Bugun uchun ochiq bozorlik yo'q."

    lines = ["🛒 Bugungi bozorlik", ""]
    for product in products:
        lines.append(f"{product['product_name']} — kerak: {_format_qty(product['total_quantity'])} {product['unit']}")
        last_price = product.get("last_price")
        if last_price is not None:
            lines.append(f"Oxirgi xarid narxi: {_format_money(last_price)} so'm")
        else:
            lines.append("Oldingi narx yo'q")
        lines.append("")
    return "\n".join(lines).rstrip()


def register(dp: Dispatcher, openai_client) -> None:

    # ------------------------------------------------------- /score --

    @dp.message(Command("score"))
    async def score_handler(message: Message) -> None:
        if not await permissions.ensure_permission(message, permissions.ACTION_SCORE_EMPLOYEE):
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

        dashboard = employee_dashboard.build_dashboard(message.from_user.id)
        if dashboard is not None:
            photo_file_id = dashboard["profile"]["photo_file_id"]
            if photo_file_id:
                # Foto o'zining alohida try/except'ida — muvaffaqiyatsiz
                # bo'lsa ham (masalan eskirgan file_id) pastdagi matnli
                # dashboard baribir yuboriladi (qarang recruiting_bot.py
                # dagi bir xil izolyatsiya naqshi).
                try:
                    await message.answer_photo(photo_file_id)
                except Exception as error:  # noqa: BLE001
                    print(f"/mystars fotosini yuborib bo'lmadi ({message.from_user.id}): {error!r}")

            lines.append("")
            lines.append("—" * 10)
            lines.append(employee_dashboard.format_dashboard_text(dashboard))

        await message.answer("\n".join(lines))

    # ------------------------------------------------------- /grafik --

    def _approved_employee_id(user_id: int) -> int | None:
        """So'rov faqat KANONIK, ``approved`` holatdagi xodim profili
        uchun ochiladi — profil yo'q, hali tasdiqlanmagan yoki ishdan
        chiqarilgan (``offboarded``) bo'lsa ``None``."""
        profile = employees.get_profile(user_id)
        if profile is None or profile.get("status") != employees.STATUS_APPROVED:
            return None
        return user_id

    @dp.message(Command("grafik"))
    async def schedule_change_start(message: Message, state: FSMContext) -> None:
        if not message.from_user or not is_authorized(message.from_user.id):
            return

        await state.clear()

        if _approved_employee_id(message.from_user.id) is None:
            await message.answer(_SCHEDULE_NOT_EMPLOYEE_TEXT, reply_markup=ReplyKeyboardRemove())
            return

        await state.set_state(ScheduleChangeStates.shift_date)
        await message.answer(
            "📅 Grafikni o'zgartirish.\nQaysi sana uchun? (masalan 01.09.2026)",
            reply_markup=ReplyKeyboardRemove(),
        )

    @dp.message(StateFilter(ScheduleChangeStates.shift_date))
    async def schedule_change_date(message: Message, state: FSMContext) -> None:
        shift_date = _parse_date_ddmmyyyy(message.text or "")
        if shift_date is None:
            await message.answer("❌ Sanani KK.OO.YYYY ko'rinishida kiriting (masalan 01.09.2026).")
            return

        await state.update_data(shift_date=shift_date.isoformat())
        await state.set_state(ScheduleChangeStates.change_type)
        await message.answer("Shu kunga nima so'raysiz?", reply_markup=_SCHEDULE_TYPE_KB)

    @dp.message(StateFilter(ScheduleChangeStates.change_type))
    async def schedule_change_type(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()

        if text == _SCHEDULE_OFF_TEXT:
            await state.update_data(requested_status=attendance_service.SHIFT_STATUS_OFF)
            await state.set_state(ScheduleChangeStates.reason)
            await message.answer("Sabab (bo'lmasa o'tkazib yuboring):", reply_markup=_SKIP_KB)
            return

        if text != _SCHEDULE_WORK_TEXT:
            await message.answer("❌ Quyidagi tugmalardan birini tanlang.", reply_markup=_SCHEDULE_TYPE_KB)
            return

        await state.update_data(requested_status=attendance_service.SHIFT_STATUS_WORK)
        await state.set_state(ScheduleChangeStates.start_time)
        await message.answer("Ish boshlanish vaqti (masalan 09:00):", reply_markup=ReplyKeyboardRemove())

    @dp.message(StateFilter(ScheduleChangeStates.start_time))
    async def schedule_change_start_time(message: Message, state: FSMContext) -> None:
        start_text = _parse_time_hhmm(message.text or "")
        if start_text is None:
            await message.answer("❌ Vaqtni SS:DD ko'rinishida kiriting (masalan 09:00).")
            return

        await state.update_data(start_text=start_text)
        await state.set_state(ScheduleChangeStates.end_time)
        await message.answer("Ish tugash vaqti (masalan 18:00):")

    @dp.message(StateFilter(ScheduleChangeStates.end_time))
    async def schedule_change_end_time(message: Message, state: FSMContext) -> None:
        end_text = _parse_time_hhmm(message.text or "")
        if end_text is None:
            await message.answer("❌ Vaqtni SS:DD ko'rinishida kiriting (masalan 18:00).")
            return

        data = await state.get_data()
        if end_text == data.get("start_text"):
            await message.answer("❌ Tugash vaqti boshlanish vaqti bilan bir xil bo'lmasin.")
            return

        await state.update_data(end_text=end_text)
        await state.set_state(ScheduleChangeStates.reason)
        await message.answer("Sabab (bo'lmasa o'tkazib yuboring):", reply_markup=_SKIP_KB)

    @dp.message(StateFilter(ScheduleChangeStates.reason))
    async def schedule_change_reason(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        data = await state.get_data()
        await state.clear()

        # Xodim shu daqiqadagi HAQIQIY yuboruvchidan qayta aniqlanadi
        # (oqim davomida saqlangan qiymatdan emas) — oqim o'rtasida
        # profil holati o'zgargan bo'lsa ham so'rov yozilmasin.
        employee_id = _approved_employee_id(message.from_user.id) if message.from_user else None
        shift_date = data.get("shift_date")
        requested_status = data.get("requested_status")

        if employee_id is None:
            await message.answer(_SCHEDULE_NOT_EMPLOYEE_TEXT, reply_markup=ReplyKeyboardRemove())
            return

        request_id = None
        if shift_date and requested_status:
            request_id = attendance_service.create_schedule_change_request(
                employee_id,
                shift_date,
                requested_status,
                start_text=data.get("start_text"),
                end_text=data.get("end_text"),
                reason=None if text == _SKIP_TEXT else (text or None),
            )

        if request_id is None:
            await message.answer(
                "❌ So'rov saqlanmadi. Sana va vaqtni tekshirib, /grafik orqali qaytadan urinib ko'ring.",
                reply_markup=ReplyKeyboardRemove(),
            )
            return

        await message.answer(
            "✅ So'rovingiz qabul qilindi. Rahbar tasdiqlagunicha grafik o'zgarmaydi.",
            reply_markup=ReplyKeyboardRemove(),
        )

    # ----------------------------------------------- /setrule, /listrules --

    @dp.message(Command("setrule"))
    async def setrule_handler(message: Message) -> None:
        if not await permissions.ensure_permission(message, permissions.ACTION_SET_RULE):
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
        if not await permissions.ensure_permission(message, permissions.ACTION_LIST_RULES):
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
        if not await permissions.ensure_permission(message, permissions.ACTION_PROCESS_MONTH):
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
        if not await permissions.ensure_permission(message, permissions.ACTION_MANAGE_VEHICLES):
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
        if not await permissions.ensure_permission(message, permissions.ACTION_ENTER_MEAL_PLAN):
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
        if not await permissions.ensure_permission(message, permissions.ACTION_LOG_MARKET_OBSERVATION):
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
        if not await permissions.ensure_permission(message, permissions.ACTION_DRIVER_DAILY_CHECK):
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

    # ---------------------------------------------------------------- /xarid --

    def _load_products_with_price() -> list[dict]:
        products = shift_deficiency.get_daily_market_shortage()
        for product in products:
            last = supplier_purchases_repo.get_price_history(product["product_name"], product["unit"])
            product["last_price"] = last["unit_price"] if last else None
        return products

    @dp.message(Command("xarid"))
    async def supplier_purchase_list(message: Message, state: FSMContext) -> None:
        if not await permissions.ensure_permission(message, permissions.ACTION_RECORD_SUPPLIER_PURCHASE):
            return

        await state.clear()
        products = _load_products_with_price()
        await state.update_data(supplier_products=products, purchased_by=message.from_user.id, session_total=0.0)

        await message.answer(_supplier_summary_text(products), reply_markup=_supplier_products_kb(products))

    @dp.callback_query(F.data.startswith("sup_pick:"))
    async def supplier_purchase_pick(callback: CallbackQuery, state: FSMContext) -> None:
        if not await permissions.ensure_permission(callback, permissions.ACTION_RECORD_SUPPLIER_PURCHASE):
            return

        index = int(callback.data.split(":", 1)[1])
        data = await state.get_data()
        products = data.get("supplier_products") or []
        if index < 0 or index >= len(products):
            await callback.answer()
            return

        product = products[index]
        await state.update_data(purchase_current=product)
        await state.set_state(SupplierPurchaseStates.quantity)
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(
            f"🛒 {product['product_name']}\nKerak: {_format_qty(product['total_quantity'])} {product['unit']}\n\n"
            "Real olingan miqdorni kiriting (masalan 11.2):"
        )
        await callback.answer()

    @dp.message(StateFilter(SupplierPurchaseStates.quantity))
    async def supplier_purchase_quantity(message: Message, state: FSMContext) -> None:
        quantity = _parse_decimal(message.text or "")
        if quantity is None or quantity <= 0:
            await message.answer("❌ Musbat son kiriting (masalan 11.2):")
            return

        data = await state.get_data()
        product = data.get("purchase_current")
        if product is None:
            await state.clear()
            await message.answer("❌ Bekor qilindi.")
            return

        await state.update_data(purchase_quantity=quantity)
        last_price = product.get("last_price")

        if last_price is None:
            await state.set_state(SupplierPurchaseStates.new_price)
            await message.answer("Birlik narxini kiriting (so'm, masalan 12000):")
            return

        await state.set_state(None)
        await message.answer(f"Oxirgi narx: {_format_money(last_price)} so'm", reply_markup=_price_choice_kb())

    @dp.callback_query(F.data == "sup_price_same")
    async def supplier_purchase_price_same(callback: CallbackQuery, state: FSMContext) -> None:
        if not await permissions.ensure_permission(callback, permissions.ACTION_RECORD_SUPPLIER_PURCHASE):
            return

        data = await state.get_data()
        product = data.get("purchase_current")
        last_price = product.get("last_price") if product else None
        if product is None or last_price is None:
            await callback.answer()
            return

        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.answer()
        await _finish_price_step(callback.message, state, last_price)

    @dp.callback_query(F.data == "sup_price_new")
    async def supplier_purchase_price_new(callback: CallbackQuery, state: FSMContext) -> None:
        if not await permissions.ensure_permission(callback, permissions.ACTION_RECORD_SUPPLIER_PURCHASE):
            return

        await state.set_state(SupplierPurchaseStates.new_price)
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer("Birlik narxini kiriting (so'm, masalan 12000):")
        await callback.answer()

    @dp.message(StateFilter(SupplierPurchaseStates.new_price))
    async def supplier_purchase_new_price(message: Message, state: FSMContext) -> None:
        price = _parse_price(message.text or "")
        if price is None or price <= 0:
            await message.answer("❌ Musbat butun son kiriting (so'm, masalan 12000):")
            return

        await state.set_state(None)
        await _finish_price_step(message, state, price)

    async def _finish_price_step(reply_target: Message, state: FSMContext, unit_price: int) -> None:
        data = await state.get_data()
        product = data.get("purchase_current")
        quantity = data.get("purchase_quantity")
        if product is None or quantity is None:
            await state.clear()
            await reply_target.answer("❌ Bekor qilindi.")
            return

        previous_price = product.get("last_price")
        if supplier_purchase.should_check_price_increase(unit_price, previous_price):
            spike = await supplier_purchase.check_price_spike(
                openai_client, product["product_name"], previous_price, unit_price
            )
            if spike:
                await state.update_data(purchase_unit_price=unit_price)
                await state.set_state(SupplierPurchaseStates.price_flag_reason)
                await reply_target.answer("⚠️ Bu mahsulot narxi odatdagidan ancha oshgan.\nSababi nima?")
                return

        await _save_purchase_and_continue(reply_target, state, unit_price, price_flagged=False, price_flag_reason=None)

    @dp.message(StateFilter(SupplierPurchaseStates.price_flag_reason))
    async def supplier_purchase_price_flag_reason(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        if not text:
            await message.answer("❌ Bo'sh matn qabul qilinmaydi. Qisqacha sababini yozing:")
            return

        data = await state.get_data()
        unit_price = data.get("purchase_unit_price")
        if unit_price is None:
            await state.clear()
            await message.answer("❌ Bekor qilindi.")
            return

        await state.set_state(None)
        await _save_purchase_and_continue(message, state, unit_price, price_flagged=True, price_flag_reason=text)

    async def _save_purchase_and_continue(
        reply_target: Message, state: FSMContext, unit_price: int, *, price_flagged: bool, price_flag_reason: str | None,
    ) -> None:
        data = await state.get_data()
        product = data["purchase_current"]
        quantity = data["purchase_quantity"]
        purchased_by = data["purchased_by"]

        purchase_id = supplier_purchase.record_purchase(
            product["product_name"], quantity, product["unit"], unit_price, purchased_by,
            price_flagged=price_flagged, price_flag_reason=price_flag_reason,
        )
        if purchase_id is None:
            await state.clear()
            await reply_target.answer("❌ Xarid saqlanmadi. Qaytadan /xarid bilan urinib ko'ring.")
            return

        line_total = quantity * unit_price
        await reply_target.answer(
            f"✅ {product['product_name']} — {_format_qty(quantity)} {product['unit']} × "
            f"{_format_money(unit_price)} = {_format_money(line_total)} so'm"
        )

        products = data.get("supplier_products") or []
        remaining = [
            p for p in products
            if not (p["product_name"] == product["product_name"] and p["unit"] == product["unit"])
        ]
        by_branch = _allocation_branches_for(product)
        branch_names = list(by_branch.keys())
        await state.update_data(
            supplier_products=remaining, purchase_current=None, purchase_quantity=None,
            purchase_unit_price=None,
            alloc_purchase_id=purchase_id, alloc_product=product, alloc_branches=branch_names,
            alloc_by_branch=by_branch, alloc_values={}, alloc_purchased_qty=quantity,
        )
        await state.set_state(None)
        await reply_target.answer(
            _allocation_summary_text(product["product_name"], product["unit"], quantity, by_branch, {}),
            reply_markup=_allocation_kb(branch_names, product["unit"], {}, quantity),
        )

    @dp.callback_query(F.data.startswith("sup_alloc_branch:"))
    async def supplier_purchase_alloc_branch_pick(callback: CallbackQuery, state: FSMContext) -> None:
        if not await permissions.ensure_permission(callback, permissions.ACTION_RECORD_SUPPLIER_PURCHASE):
            return

        index = int(callback.data.split(":", 1)[1])
        data = await state.get_data()
        branches = data.get("alloc_branches") or []
        product = data.get("alloc_product")
        if index < 0 or index >= len(branches) or product is None:
            await callback.answer()
            return

        branch = branches[index]
        await state.update_data(alloc_current_branch=branch)
        await state.set_state(SupplierPurchaseStates.allocation_branch_quantity)
        await callback.answer()
        await callback.message.answer(f"{branch} uchun real necha {product['unit']} berildi?")

    @dp.message(StateFilter(SupplierPurchaseStates.allocation_branch_quantity))
    async def supplier_purchase_alloc_quantity(message: Message, state: FSMContext) -> None:
        quantity = _parse_decimal(message.text or "")
        if quantity is None or quantity < 0:
            await message.answer("❌ 0 yoki musbat son kiriting:")
            return

        data = await state.get_data()
        branch = data.get("alloc_current_branch")
        values = dict(data.get("alloc_values") or {})
        purchased_qty = data.get("alloc_purchased_qty")
        product = data.get("alloc_product")
        by_branch = data.get("alloc_by_branch") or {}
        branches = data.get("alloc_branches") or []
        if branch is None or purchased_qty is None or product is None:
            await state.clear()
            await message.answer("❌ Bekor qilindi.")
            return

        other_total = sum(v for b, v in values.items() if b != branch)
        if other_total + quantity > purchased_qty + 1e-9:
            remaining = purchased_qty - other_total
            await message.answer(
                f"❌ Jami taqsimot {_format_qty(purchased_qty)} {product['unit']}dan oshib ketadi. "
                f"Qoldi: {_format_qty(max(remaining, 0))} {product['unit']}."
            )
            return

        values[branch] = quantity
        await state.update_data(alloc_values=values, alloc_current_branch=None)
        await state.set_state(None)

        await message.answer(
            _allocation_summary_text(product["product_name"], product["unit"], purchased_qty, by_branch, values),
            reply_markup=_allocation_kb(branches, product["unit"], values, purchased_qty),
        )

    @dp.callback_query(F.data == "sup_alloc_finish")
    async def supplier_purchase_alloc_finish(callback: CallbackQuery, state: FSMContext) -> None:
        if not await permissions.ensure_permission(callback, permissions.ACTION_RECORD_SUPPLIER_PURCHASE):
            return

        data = await state.get_data()
        purchase_id = data.get("alloc_purchase_id")
        values = data.get("alloc_values") or {}
        purchased_qty = data.get("alloc_purchased_qty")
        product = data.get("alloc_product")
        by_branch = data.get("alloc_by_branch") or {}
        if purchase_id is None or purchased_qty is None or product is None:
            await callback.answer()
            return

        remaining = purchased_qty - sum(values.values())
        if abs(remaining) > 1e-9:
            await callback.answer(f"Hali {_format_qty(remaining)} {product['unit']} taqsimlanmagan.", show_alert=True)
            return

        supplier_purchase.save_allocations(purchase_id, values)
        for branch, quantity in values.items():
            if quantity and quantity > 0:
                item_ids = by_branch.get(branch, {}).get("item_ids") or []
                if item_ids:
                    supplier_purchase.resolve_deficiency_items(item_ids)

        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.answer("✅ Taqsimlandi.")
        await callback.message.answer(f"✅ {product['product_name']} filiallarga taqsimlandi.")
        await _finish_current_product_and_continue(callback.message, state)

    async def _finish_current_product_and_continue(reply_target: Message, state: FSMContext) -> None:
        data = await state.get_data()
        products = data.get("supplier_products") or []
        await state.update_data(
            alloc_purchase_id=None, alloc_product=None, alloc_branches=None,
            alloc_by_branch=None, alloc_values=None, alloc_purchased_qty=None,
        )

        if products:
            await reply_target.answer(_supplier_summary_text(products), reply_markup=_supplier_products_kb(products))
            return

        await state.clear()
        report = supplier_purchase.get_branch_report_for_date(company_time.today().isoformat())
        await reply_target.answer(_branch_report_text(report))

    @dp.callback_query(F.data == "sup_add_product")
    async def supplier_purchase_add_product_start(callback: CallbackQuery, state: FSMContext) -> None:
        if not await permissions.ensure_permission(callback, permissions.ACTION_RECORD_SUPPLIER_PURCHASE):
            return

        data = await state.get_data()
        if "purchased_by" not in data:
            await state.update_data(purchased_by=callback.from_user.id, supplier_products=data.get("supplier_products") or [], session_total=data.get("session_total") or 0.0)

        await state.set_state(SupplierPurchaseStates.new_product_name)
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer("Mahsulot nomini kiriting:")
        await callback.answer()

    @dp.message(StateFilter(SupplierPurchaseStates.new_product_name))
    async def supplier_purchase_add_product_name(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        if not text:
            await message.answer("❌ Mahsulot nomini kiriting:")
            return

        await state.update_data(new_product_name=text)
        await state.set_state(SupplierPurchaseStates.new_product_quantity)
        await message.answer("Real olingan miqdorni kiriting (masalan 5):")

    @dp.message(StateFilter(SupplierPurchaseStates.new_product_quantity))
    async def supplier_purchase_add_product_quantity(message: Message, state: FSMContext) -> None:
        quantity = _parse_decimal(message.text or "")
        if quantity is None or quantity <= 0:
            await message.answer("❌ Musbat son kiriting:")
            return

        await state.update_data(new_product_quantity=quantity)
        await state.set_state(None)
        await message.answer("Birlikni tanlang:", reply_markup=_unit_choice_kb())

    @dp.callback_query(F.data.startswith("sup_new_unit:"))
    async def supplier_purchase_add_product_unit(callback: CallbackQuery, state: FSMContext) -> None:
        unit = callback.data.split(":", 1)[1]
        if unit not in shift_deficiency.KNOWN_UNITS:
            await callback.answer()
            return

        await state.update_data(new_product_unit=unit)
        await state.set_state(SupplierPurchaseStates.new_product_price)
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer("Birlik narxini kiriting (so'm):")
        await callback.answer()

    @dp.message(StateFilter(SupplierPurchaseStates.new_product_price))
    async def supplier_purchase_add_product_price(message: Message, state: FSMContext) -> None:
        price = _parse_price(message.text or "")
        if price is None or price <= 0:
            await message.answer("❌ Musbat butun son kiriting (so'm):")
            return

        data = await state.get_data()
        name = data.get("new_product_name")
        quantity = data.get("new_product_quantity")
        unit = data.get("new_product_unit")
        purchased_by = data.get("purchased_by") or message.from_user.id

        if not name or quantity is None or unit is None:
            await state.clear()
            await message.answer("❌ Bekor qilindi.")
            return

        last = supplier_purchases_repo.get_price_history(name, unit)
        synthetic_product = {
            "product_name": name, "unit": unit, "total_quantity": quantity, "by_branch": {},
            "last_price": last["unit_price"] if last else None,
        }
        await state.update_data(
            purchase_current=synthetic_product, purchase_quantity=quantity, purchased_by=purchased_by,
        )
        await state.set_state(None)
        await _finish_price_step(message, state, price)

    # --------------------------------------------------------------- /natijam --

    @dp.message(Command("natijam"))
    async def supplier_results_handler(message: Message) -> None:
        if not await permissions.ensure_permission(message, permissions.ACTION_VIEW_SUPPLIER_RESULTS):
            return

        today = company_time.today().isoformat()
        stats = shift_deficiency.get_supplier_stats(today, today)
        await message.answer(
            "📊 Bugungi natijangiz\n\n"
            f"Buyurtma: {stats['total']} ta\n"
            f"Keltirildi: {stats['arrived']} ta\n"
            f"Kelmadi: {stats['missing']} ta\n"
            f"Bajarilish: {stats['completion_rate']}%"
        )
