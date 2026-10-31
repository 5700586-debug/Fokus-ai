"""💰 Xodim maoshi (Founder): xodimni ro'yxatdan tanlash → joriy yoki o'tgan oy maoshining to'liq tarkibi.
Faqat o'qiydi (``services/payroll_view.month_view``)."""

from datetime import timedelta

from aiogram import Dispatcher, F
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

import company_time
import employees
from services import payroll_view, permissions

PAGE_SIZE = 10


def _kb(*rows: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=t, callback_data=d) for t, d in row] for row in rows]
    )


def _name(profile: dict) -> str:
    return " ".join(p for p in (profile.get("familiya"), profile.get("ism")) if p) or str(profile["user_id"])


def _som(value) -> str:
    return "—" if value is None else f"{int(value):,}".replace(",", " ") + " so'm"


def employee_list(page: int) -> tuple[str, InlineKeyboardMarkup]:
    people = employees.list_approved()
    pages = max(1, -(-len(people) // PAGE_SIZE))
    page = min(max(page, 0), pages - 1)
    rows = [[(f"{_name(p)} · {p.get('branch') or '—'}"[:60], f"pay:emp:{p['user_id']}:0")]
            for p in people[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]]
    nav = []
    if page > 0:
        nav.append(("⬅️", f"pay:list:{page - 1}"))
    if page < pages - 1:
        nav.append(("➡️", f"pay:list:{page + 1}"))
    if nav:
        rows.append(nav)
    text = "💰 Xodim maoshi — kimni ko'ramiz?" + (f"\nSahifa {page + 1}/{pages}" if pages > 1 else "")
    if not people:
        text += "\n\nTasdiqlangan xodim yo'q."
    return text, _kb(*rows)


def _month(offset: int) -> str:
    today = company_time.today()
    first = today.replace(day=1)
    if offset:
        first = (first - timedelta(days=1)).replace(day=1)
    return first.strftime("%Y-%m")


def salary_text(profile: dict, year_month: str) -> str:
    v = payroll_view.month_view(profile["user_id"], year_month)
    star = payroll_view.STAR_VALUE_SOM
    lines = [f"💰 {_name(profile)} — {year_month}" + ("" if v["final"] else " (oy davom etmoqda)")]
    if v.get("worked_minutes") is not None and v.get("plan_minutes"):
        lines.append(f"🕒 Ishlagan: {v['worked_minutes'] // 60} soat / reja {v['plan_minutes'] // 60} soat")
    lines.append(f"📌 Fiks: {_som(v['fixed_amount'])}")
    grade_points = (v["work_bonus"] or 0) - v.get("time_bonus", 0)
    lines.append(f"⭐ Ish bonusi: {grade_points} ball")
    lines.append(f"⏰ Vaqt bonusi: {v.get('time_bonus_days', 0)} kun × {payroll_view.TIME_BONUS_POINTS} = {v.get('time_bonus', 0)} ball")
    lines.append(f"➖ Minus: {v['minus'] or 0} ball (ayirildi: {v['minus_applied'] or 0})")
    lines.append(f"➕ Qo'shimcha ish: {v['extra_work'] or 0} ball (minus tegmaydi)")
    if v["total_stars"] is not None:
        lines.append(f"= Bonus jami: {v['total_stars']} ball × {star:,} = {_som(v['total_stars'] * star)}".replace(",", " "))
    if v.get("tariff") == 3:
        lines.append(f"🏅 3-tarif mukofoti: {_som(v['tariff_award'])}" + (f" ({v['tariff_note']})" if v.get("tariff_note") else ""))
    if v.get("star_bonus"):
        lines.append(f"🌟 Oylik yulduz bonusi: {_som(v['star_bonus'])}")
    lines.append(f"\n💵 JAMI: {_som(v['total_amount'])}")
    notes = list(v["unavailable"].values()) + v["limitations"]
    if notes:
        lines.append("\nℹ️ " + "\nℹ️ ".join(dict.fromkeys(notes)))
    return "\n".join(lines)


def register(dp: Dispatcher) -> None:
    @dp.callback_query(F.data.startswith("pay:"))
    async def payroll_callbacks(callback: CallbackQuery) -> None:
        if not await permissions.ensure_permission(callback, permissions.ACTION_MANAGE_DISCIPLINE_RULES):
            return
        parts = callback.data.split(":")
        await callback.answer()
        if len(parts) == 3 and parts[1] == "list" and parts[2].isdigit():
            text, markup = employee_list(int(parts[2]))
            await callback.message.answer(text, reply_markup=markup)
            return
        if len(parts) == 4 and parts[1] == "emp" and parts[2].lstrip("-").isdigit() and parts[3] in ("0", "1"):
            profile = employees.get_profile(int(parts[2]))
            if profile is None:
                await callback.message.answer("Xodim topilmadi.")
                return
            offset = int(parts[3])
            other = 1 - offset
            await callback.message.answer(
                salary_text(profile, _month(offset)),
                reply_markup=_kb([("📅 O'tgan oy" if other else "📅 Joriy oy", f"pay:emp:{profile['user_id']}:{other}"),
                                  ("⬅️ Xodimlar", "pay:list:0")]),
            )
            return
        await callback.message.answer("Bu tugma eskirgan.")
