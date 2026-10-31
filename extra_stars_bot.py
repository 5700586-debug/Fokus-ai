"""➕ Qo'shimcha ish yulduzi: xodim → yulduz soni → sabab → tasdiq. Faqat ``extra_stars.can_give`` (Founder + ruxsatli
rollar). Yozilgach xodimga xabar boradi. Minus bu yulduzlardan ayrilmaydi (``services/payroll_view``)."""

import logging
import secrets

from aiogram import Dispatcher, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import employees
from services import extra_stars

logger = logging.getLogger(__name__)

PAGE_SIZE = 10
STAR_CHOICES = (1, 2, 3, 4, 5, 6, 8, 10)
STAR_VALUE_SOM = 5000


class ExtraStarsStates(StatesGroup):
    waiting_reason = State()


def _kb(*rows: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=t, callback_data=d) for t, d in row] for row in rows]
    )


def _name(profile: dict) -> str:
    return " ".join(p for p in (profile.get("familiya"), profile.get("ism")) if p) or str(profile["user_id"])


def _money(stars: int) -> str:
    return f"{stars * STAR_VALUE_SOM:,}".replace(",", " ") + " so'm"


def employee_list(giver_id: int, page: int) -> tuple[str, InlineKeyboardMarkup]:
    people = [p for p in employees.list_approved() if p["user_id"] != giver_id and extra_stars.can_give_to(giver_id, p)]
    pages = max(1, -(-len(people) // PAGE_SIZE))
    page = min(max(page, 0), pages - 1)
    rows = [[(f"{_name(p)} · {p.get('branch') or '—'}"[:60], f"xs:pick:{p['user_id']}")]
            for p in people[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]]
    nav = []
    if page > 0:
        nav.append(("⬅️", f"xs:list:{page - 1}"))
    if page < pages - 1:
        nav.append(("➡️", f"xs:list:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([("❌ Bekor qilish", "xs:cancel")])
    text = "➕ Qo'shimcha ish yulduzi — kimga?"
    if pages > 1:
        text += f"\nSahifa {page + 1}/{pages}"
    if not people:
        text += "\n\nTasdiqlangan xodim yo'q."
    return text, _kb(*rows)


def register(dp: Dispatcher) -> None:
    async def _deny(target) -> None:
        if isinstance(target, CallbackQuery):
            await target.answer("Ruxsat yo'q.", show_alert=True)
        else:
            await target.answer("Ruxsat yo'q.")

    @dp.message(Command("qoshimchaish"))
    async def start_command(message: Message, state: FSMContext) -> None:
        if not message.from_user or not extra_stars.can_give(message.from_user.id):
            await _deny(message)
            return
        await state.clear()
        text, markup = employee_list(message.from_user.id, 0)
        await message.answer(text, reply_markup=markup)

    @dp.callback_query(F.data.startswith("xs:"))
    async def callbacks(callback: CallbackQuery, state: FSMContext) -> None:
        user_id = callback.from_user.id
        if not extra_stars.can_give(user_id):
            await _deny(callback)
            return
        parts = callback.data.split(":")
        action = parts[1] if len(parts) > 1 else ""
        await callback.answer()
        if action == "cancel":
            await state.clear()
            await callback.message.answer("❌ Bekor qilindi — hech narsa yozilmadi.")
            return
        if action == "list":
            await state.clear()
            page = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
            text, markup = employee_list(user_id, page)
            await callback.message.answer(text, reply_markup=markup)
            return
        if action == "pick" and len(parts) == 3 and parts[2].lstrip("-").isdigit():
            employee_id = int(parts[2])
            profile = employees.get_profile(employee_id)
            if not extra_stars.can_give_to(user_id, profile):
                await callback.message.answer("Faqat o'z filialingiz xodimlariga yulduz bera olasiz.")
                return
            rows = [[(f"{n} ⭐", f"xs:n:{employee_id}:{n}") for n in STAR_CHOICES[:4]],
                    [(f"{n} ⭐", f"xs:n:{employee_id}:{n}") for n in STAR_CHOICES[4:]],
                    [("⬅️ Xodimlar", "xs:list:0"), ("❌ Bekor qilish", "xs:cancel")]]
            await callback.message.answer(
                f"{_name(profile)} — necha yulduz? (1 ⭐ = {STAR_VALUE_SOM:,} so'm)".replace(",", " "),
                reply_markup=_kb(*rows),
            )
            return
        if action == "n" and len(parts) == 4 and parts[2].lstrip("-").isdigit() and parts[3].isdigit():
            employee_id, stars = int(parts[2]), int(parts[3])
            if stars not in STAR_CHOICES or not extra_stars.can_give_to(user_id, employees.get_profile(employee_id)):
                await callback.message.answer("Bu tugma eskirgan.")
                return
            await state.clear()
            await state.update_data(xs={"employee_id": employee_id, "stars": stars, "token": secrets.token_hex(8)})
            await state.set_state(ExtraStarsStates.waiting_reason)
            await callback.message.answer(
                "✍️ Qanday qo'shimcha ish uchun? Qisqa yozing (masalan: \"2 soat inventarizatsiyada qoldi\").",
                reply_markup=_kb([("❌ Bekor qilish", "xs:cancel")]),
            )
            return
        if action == "ok" and len(parts) == 3:
            data = (await state.get_data()).get("xs") or {}
            if data.get("token") != parts[2] or not data.get("reason"):
                await callback.message.answer("Tasdiq eskirgan — qaytadan boshlang.")
                return
            await state.clear()
            try:
                created = extra_stars.give(data["employee_id"], data["stars"], data["reason"], user_id, data["token"])
            except extra_stars.ExtraStarsError as error:
                await callback.message.answer(str(error))
                return
            if callback.message:
                try:
                    await callback.message.edit_reply_markup(reply_markup=None)
                except Exception:  # noqa: BLE001 - eski xabar
                    pass
            if not created:
                await callback.message.answer("Bu yozuv allaqachon saqlangan.")
                return
            stars = data["stars"]
            try:
                await callback.bot.send_message(
                    data["employee_id"],
                    f"⭐ Qo'shimcha ish uchun +{stars} yulduz ({_money(stars)}).\nSabab: {data['reason']}\n"
                    "Bu yulduzlar oy oxirida maoshingizga qo'shiladi va ulardan minus ayrilmaydi.",
                )
                delivered = True
            except Exception as error:  # noqa: BLE001 - yozuv saqlangan; yetkazish xatosi uni bekor qilmaydi
                logger.info("Qo'shimcha ish xabari yetmadi: %s", type(error).__name__)
                delivered = False
            await callback.message.answer(
                f"✅ Saqlandi: +{stars} ⭐ ({_money(stars)})." + ("" if delivered else "\nXodimga xabar yetib bormadi.")
            )
            return
        await callback.message.answer("Bu tugma eskirgan.")

    @dp.message(StateFilter(ExtraStarsStates.waiting_reason))
    async def reason_message(message: Message, state: FSMContext) -> None:
        if not message.from_user or not extra_stars.can_give(message.from_user.id):
            await state.clear()
            return
        reason = (message.text or "").strip()
        data = (await state.get_data()).get("xs") or {}
        if not data:
            await state.clear()
            await message.answer("Jarayon eskirgan — qaytadan boshlang.")
            return
        if len(reason) < extra_stars.MIN_REASON_CHARS:
            await message.answer("Sababini aniqroq yozing (kamida 5 belgi).")
            return
        data["reason"] = reason[:500]
        await state.update_data(xs=data)
        profile = employees.get_profile(data["employee_id"]) or {"user_id": data["employee_id"]}
        await message.answer(
            f"Tekshiring:\n👤 {_name(profile)}\n⭐ {data['stars']} yulduz ({_money(data['stars'])})\n📝 {data['reason']}",
            reply_markup=_kb([("✅ Saqlash", f"xs:ok:{data['token']}"), ("❌ Bekor qilish", "xs:cancel")]),
        )
