"""Oylik kelishuvini sodda kiritish (Founder), xodimga yuborish va xodim roziligini qayd etish.

Saqlash yo'li — mavjud ``services/salary_agreement.save_agreement`` (tarix o'chirilmaydi, har o'zgarish yangi versiya).
Rozilik maosh hisobiga ta'sir qilmaydi: alohida ``salary_agreement_consents``da. Summalar faqat shaxsiy chatda;
loglarga matn/summa chiqmaydi."""

import logging
import secrets

from aiogram import Dispatcher, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import company_time
import employees
from config import FOUNDER_ID
from services import discipline, permissions
from services import salary_agreement as sa
from services import salary_agreement_text as sat

logger = logging.getLogger(__name__)

FOUNDER_BUTTON = "💵 Oylik kelishuvi"
EMPLOYEE_BUTTON = "💵 Oylik kelishuvim"

SAMPLE = (
    "Eshmat Shermatov — Saturn Charhiy\n"
    "Tarif: 3\n"
    "Fiks: 1.800.000 so'm\n"
    "Oyiga: 28 ish kuni\n"
    "Kuniga: 11 soat\n"
    "Kelishuv boshlanishi: 01.10.2026\n"
    "Natija bonusi: oyiga 700.000 so'mgacha"
)
_INTRO = (
    "💵 Oylik kelishuvi.\n\nShu namunadagidek bitta xabarda yozing (tartib va tinish belgilari muhim emas):\n\n"
    f"{SAMPLE}\n\nYetishmagan qismini keyin qisqa so'rayman."
)
_ASK = {
    "employee": "👤 Qaysi xodim? Ism-familiyani yozing (masalan: Eshmat Shermatov — Saturn Charhiy).",
    "tariff": "🏷 Tarif raqami? (1, 2 yoki 3)",
    "fixed_salary": "💵 Fiks oylik qancha? (masalan: 1 800 000 yoki 1,8 mln)",
    "work_days": "📅 Oyiga necha ish kuni? (masalan: 28)",
    "daily_minutes": "🕒 Kuniga necha soat? (masalan: 11)",
    "effective_from": "📌 Kelishuv qaysi sanadan boshlanadi? (KK.OO.YYYY)",
    "result_bonus_cap": "🎯 Natija bonusi oyiga eng ko'pi bilan qancha? (masalan: 700 000)",
}
_ORDER = ("employee", "tariff", "fixed_salary", "work_days", "daily_minutes", "effective_from", "result_bonus_cap")


class AgreementStates(StatesGroup):
    collecting = State()


def _kb(*rows: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=t, callback_data=d) for t, d in row] for row in rows]
    )


_CANCEL_ROW = [("❌ Bekor qilish", "sagr:cancel")]


def _full_name(profile: dict) -> str:
    return " ".join(p for p in (profile.get("familiya"), profile.get("ism")) if p) or str(profile["user_id"])


def _missing(data: dict) -> str | None:
    for key in _ORDER:
        if key == "employee":
            if data.get("employee_id") is None:
                return key
        elif key == "result_bonus_cap":
            if key not in data and not data.get("bonus_none"):
                return key
        elif data.get(key) is None:
            return key
    return None


def _card_text(data: dict) -> str:
    cap = data.get("result_bonus_cap")
    return "\n".join(
        [
            "📝 Oylik kelishuvi — tekshiring:",
            f"👤 Xodim: {data['employee_name']}",
            f"🏬 Filial: {data['branch']}",
            f"🏷 Tarif: {data['tariff']}",
            f"💵 Fiks oylik: {sa.format_money(data['fixed_salary'])}",
            f"📅 Oylik ish kunlari: {data['work_days']} kun",
            f"🕒 Kunlik ish soati: {sa.format_minutes(data['daily_minutes'])}",
            f"📌 Kelishuv boshlanishi: {sa.format_date(data['effective_from'])}",
            f"🎯 Natija bonusi: {'oyiga ' + sa.format_money(cap) + 'gacha' if cap else 'Belgilanmagan'}",
            "\nSaqlanmaguncha xodimga hech narsa yuborilmaydi.",
        ]
    )


def _employee_text(agreement: dict, employee_id: int, title: str = "💵 Oylik kelishuvi") -> str:
    version = sa.version_number(employee_id, agreement["id"])
    return "\n".join(
        [
            f"{title} (versiya {version})",
            f"💵 Fiks oylik: {sa.format_money(agreement['fixed_salary'])}",
            *sa.agreement_lines(agreement),
        ]
    )


def _consent_kb(agreement_id: int, *, with_question: bool = True) -> InlineKeyboardMarkup:
    row = [("✅ Roziman", f"sagr:ok:{agreement_id}")]
    if with_question:
        row.append(("❓ Tushunmadim", f"sagr:no:{agreement_id}"))
    return _kb(row)


REMIND_HOUR = 21  # kun oxiri (Asia/Tashkent); mavjud discipline scheduler'ga job sifatida ulanadi


async def remind_open_issues(bot, now=None) -> int:
    """Kun oxirida yopilmagan "Tushunmadim" savollari haqida Founderga (summasiz) eslatma; har savol kuniga bir marta."""
    now = now or company_time.now()
    if now.hour < REMIND_HOUR:
        return 0
    today = now.date().isoformat()
    pending = [i for i in sa.open_issues() if i["due_date"] <= today and i.get("reminded_on") != today]
    if not pending:
        return 0
    lines = ["⏰ Yopilmagan oylik kelishuvi savollari:"]
    for issue in pending:
        profile = employees.get_profile(issue["employee_id"], include_contacts=False) or {"user_id": issue["employee_id"]}
        lines.append(f"• {_full_name(profile)} — {issue.get('branch') or '-'} (muddat: {sa.format_date(issue['due_date'])})")
    try:
        await bot.send_message(FOUNDER_ID, "\n".join(lines))
    except Exception as error:  # noqa: BLE001
        logger.warning("Kelishuv savollari eslatmasi ketmadi: %s", type(error).__name__)
        return 0
    for issue in pending:
        sa.mark_issue_reminded(issue["id"], today)
    return len(pending)


def _private(event) -> bool:
    chat = event.message.chat if isinstance(event, CallbackQuery) else event.chat
    return event.from_user is not None and chat.type == "private"


def register(dp: Dispatcher) -> None:
    async def _allowed(event) -> bool:
        """Har qadamda: faqat shaxsiy chat va mavjud ``ACTION_SET_SALARY`` (Founder)."""
        if not _private(event):
            if isinstance(event, CallbackQuery):
                await event.answer("Bu amal faqat shaxsiy chatda.", show_alert=True)
            return False
        return await permissions.ensure_permission(event, permissions.ACTION_SET_SALARY)

    async def _reply(target, text, markup=None, *, edit=False):
        if edit:
            await target.message.edit_text(text, reply_markup=markup)
        else:
            await target.answer(text, reply_markup=markup)

    async def _next_step(target, state: FSMContext, *, edit: bool = False, note: str | None = None) -> None:
        data = await state.get_data()
        ag = data.get("ag", {})
        key = _missing(ag)
        if key is None:
            token = secrets.token_hex(8)  # har karta yangi token: eski karta tugmalari yaroqsiz
            await state.update_data(ag_token=token, ag_ask=None)
            await state.set_state(None)
            text = _card_text(ag)
            markup = _kb(
                [("✅ Saqlash va xodimga yuborish", f"sagr:save:{token}")],
                [("✏️ Tuzatish", "sagr:edit"), ("❌ Bekor qilish", "sagr:cancel")],
            )
            await _reply(target, text, markup, edit=edit)
            return
        await state.update_data(ag_ask=key, ag_token=None)
        await state.set_state(AgreementStates.collecting)
        rows = [_CANCEL_ROW]
        if key == "effective_from":
            rows = [[("📅 Bugundan", "sagr:today")], _CANCEL_ROW]
        elif key == "result_bonus_cap":
            rows = [[("Bonus yo'q", "sagr:nobonus")], _CANCEL_ROW]
        text = (note + "\n\n" if note else "") + (data.get("ag_problem_text") or "") + _ASK[key]
        await _reply(target, text, _kb(*rows), edit=edit)

    async def _resolve_employee(target, state: FSMContext, name: str, branch_hint: str | None) -> str | None:
        """Qaytadi: Founderga ko'rsatiladigan izoh (yoki ``None`` — aniq topildi)."""
        data = await state.get_data()
        ag = dict(data.get("ag", {}))
        candidates, exact = sat.find_employees(name, branch_hint)
        if exact:
            profile = candidates[0]
            ag.update(employee_id=profile["user_id"], employee_name=_full_name(profile), branch=profile["branch"])
            await state.update_data(ag=ag, ag_cands=[])
            return None
        await state.update_data(ag_cands=[c["user_id"] for c in candidates])
        if not candidates:
            return "Bunday tasdiqlangan xodim topilmadi. Yangi xodim yaratilmaydi — ism-familiyani qayta yozing."
        rows = [[(f"{_full_name(c)} — {c['branch']}", f"sagr:pick:{c['user_id']}")] for c in candidates[:8]]
        await target.answer("Qaysi xodim? Tanlang:", reply_markup=_kb(*rows, _CANCEL_ROW))
        return ""

    async def _ingest(message: Message, state: FSMContext) -> None:
        data = await state.get_data()
        ask = data.get("ag_ask")
        parsed = sat.parse_text(message.text or "", name_words=1 if ask == "employee" else 2)
        if ask and ask not in parsed.values and ask not in parsed.problems:
            bare = sat.parse_bare(ask, message.text or "")
            parsed.values.update(bare.values)
            parsed.problems.update(bare.problems)
        ag = dict(data.get("ag", {}))
        employee = parsed.values.pop("employee", None)
        bonus_none = parsed.values.pop("bonus_none", False)
        for key, value in parsed.values.items():
            ag[key] = value
        if bonus_none:
            ag["bonus_none"] = True
            ag["result_bonus_cap"] = None
        elif parsed.values.get("result_bonus_cap"):
            ag.pop("bonus_none", None)
        await state.update_data(ag=ag)

        problem_lines = [text for key, text in parsed.problems.items()]
        await state.update_data(ag_problem_text=("⚠️ " + " ".join(problem_lines) + "\n\n") if problem_lines else "")
        if employee:
            outcome = await _resolve_employee(message, state, employee["name"], employee["branch_hint"])
            if outcome == "":
                return
            if outcome:
                await state.update_data(ag_problem_text=f"⚠️ {outcome}\n\n")
        await _next_step(message, state)

    @dp.message(Command("kelishuv"))
    @dp.message(F.text == FOUNDER_BUTTON)
    async def agreement_start(message: Message, state: FSMContext) -> None:
        if not await _allowed(message):
            return
        await state.clear()
        await state.set_state(AgreementStates.collecting)
        await state.update_data(ag={}, ag_ask=None, ag_token=None, ag_cands=[], ag_problem_text="")
        await message.answer(_INTRO, reply_markup=_kb(_CANCEL_ROW))

    @dp.message(StateFilter(AgreementStates.collecting), F.text)
    async def agreement_text(message: Message, state: FSMContext) -> None:
        if not await _allowed(message):
            return
        await _ingest(message, state)

    @dp.callback_query(F.data.startswith("sagr:pick:"))
    async def agreement_pick(callback: CallbackQuery, state: FSMContext) -> None:
        if not await _allowed(callback):
            return
        data = await state.get_data()
        try:
            picked = int(callback.data.split(":")[2])
        except ValueError:
            picked = None
        profile = employees.get_profile(picked) if picked in data.get("ag_cands", []) else None
        if profile is None or profile.get("status") != "approved":
            await callback.answer("Tugma eskirgan.", show_alert=True)
            return
        ag = dict(data["ag"])
        ag.update(employee_id=profile["user_id"], employee_name=_full_name(profile), branch=profile["branch"])
        await state.update_data(ag=ag, ag_cands=[], ag_problem_text="")
        await callback.answer()
        await _next_step(callback, state, edit=True)

    @dp.callback_query(F.data == "sagr:today")
    async def agreement_today(callback: CallbackQuery, state: FSMContext) -> None:
        if not await _allowed(callback):
            return
        data = await state.get_data()
        if data.get("ag_ask") != "effective_from":
            await callback.answer("Tugma eskirgan.", show_alert=True)
            return
        await state.update_data(ag={**data["ag"], "effective_from": company_time.today().isoformat()}, ag_problem_text="")
        await callback.answer()
        await _next_step(callback, state, edit=True)

    @dp.callback_query(F.data == "sagr:nobonus")
    async def agreement_nobonus(callback: CallbackQuery, state: FSMContext) -> None:
        if not await _allowed(callback):
            return
        data = await state.get_data()
        if data.get("ag_ask") != "result_bonus_cap":
            await callback.answer("Tugma eskirgan.", show_alert=True)
            return
        await state.update_data(ag={**data["ag"], "bonus_none": True, "result_bonus_cap": None}, ag_problem_text="")
        await callback.answer()
        await _next_step(callback, state, edit=True)

    @dp.callback_query(F.data == "sagr:edit")
    async def agreement_edit(callback: CallbackQuery, state: FSMContext) -> None:
        if not await _allowed(callback):
            return
        data = await state.get_data()
        if not data.get("ag_token"):
            await callback.answer("Karta eskirgan.", show_alert=True)
            return
        await state.update_data(ag_token=None, ag_ask=None, ag_problem_text="")  # eski "Saqlash" tugmasi o'chadi
        await state.set_state(AgreementStates.collecting)
        await callback.answer()
        await callback.message.edit_text(
            "✏️ Tuzatiladigan qismini yozing, masalan «Fiks: 2.000.000» yoki «Kuniga: 10 soat». "
            "Qolganlari o'zgarmaydi.",
            reply_markup=_kb(_CANCEL_ROW),
        )

    @dp.callback_query(F.data == "sagr:cancel")
    async def agreement_cancel(callback: CallbackQuery, state: FSMContext) -> None:
        if not await _allowed(callback):
            return
        await state.clear()
        await callback.answer()
        await callback.message.edit_text("❌ Bekor qilindi. Hech narsa saqlanmadi va xodimga yuborilmadi.")

    async def _send_to_employee(bot, agreement: dict) -> bool:
        employee_id = agreement["employee_id"]
        try:
            await bot.send_message(employee_id, _employee_text(agreement, employee_id), reply_markup=_consent_kb(agreement["id"]))
        except Exception as error:  # noqa: BLE001
            logger.warning("Kelishuvni xodimga yuborib bo'lmadi (id=%s): %s", agreement["id"], type(error).__name__)
            sa.mark_delivery(agreement["id"], False)
            return False
        sa.mark_delivery(agreement["id"], True)
        return True

    def _delivery_report(sent: bool, agreement: dict) -> tuple[str, InlineKeyboardMarkup | None]:
        if sent:
            return (
                "✅ Saqlandi va xodimga yuborildi.\nHolat: Xodim tasdig'i kutilmoqda.",
                None,
            )
        return (
            "✅ Saqlandi, lekin xodimga YUBORIB BO'LMADI (xodim botni ochmagan bo'lishi mumkin).\n"
            "Holat: Xodim tasdig'i kutilmoqda. Xodim botda «💵 Oylik kelishuvim» orqali o'zi ochib tasdiqlashi mumkin.",
            _kb([("🔁 Qayta yuborish", f"sagr:resend:{agreement['id']}")]),
        )

    @dp.callback_query(F.data.startswith("sagr:save:"))
    async def agreement_save(callback: CallbackQuery, state: FSMContext) -> None:
        if not await _allowed(callback):
            return
        data = await state.get_data()
        token = callback.data.split(":", 2)[2]
        ag = data.get("ag", {})
        if (
            not data.get("ag_token") or token != data["ag_token"] or await state.get_state() is not None
            or _missing(ag) is not None
        ):
            await callback.answer("Karta eskirgan yoki allaqachon ishlatilgan.", show_alert=True)
            return
        profile = employees.get_profile(ag["employee_id"])
        if profile is None or profile.get("status") != "approved":
            await state.clear()
            await callback.answer("Xodim endi tasdiqlangan ro'yxatda emas.", show_alert=True)
            return
        try:
            result = sa.save_agreement(
                ag["employee_id"], ag["fixed_salary"], ag["work_days"], ag["daily_minutes"], ag["effective_from"],
                callback.from_user.id, token, tariff=ag["tariff"], result_bonus_cap=ag.get("result_bonus_cap"),
                with_consent=True,
            )
        except sa.ValidationError as error:
            await callback.answer(str(error), show_alert=True)
            return
        await state.clear()
        await callback.answer()
        if not result.created or result.agreement is None:
            await callback.message.edit_text("ℹ️ Bu kelishuv allaqachon saqlangan; qayta yozilmadi.")
            return
        sent = await _send_to_employee(callback.bot, result.agreement)
        text, markup = _delivery_report(sent, result.agreement)
        await callback.message.edit_text("\n".join(_card_text(ag).split("\n")[:-2]) + f"\n\n{text}", reply_markup=markup)

    @dp.callback_query(F.data.startswith("sagr:resend:"))
    async def agreement_resend(callback: CallbackQuery) -> None:
        if not await _allowed(callback):
            return
        agreement = sa.get_agreement(int(callback.data.split(":")[2]))
        if agreement is None or not sa.pending_consent(agreement):
            await callback.answer("Bu versiya eskirgan yoki tasdiqlangan.", show_alert=True)
            return
        sent = await _send_to_employee(callback.bot, agreement)
        text, markup = _delivery_report(sent, agreement)
        await callback.answer()
        await callback.message.edit_text(text, reply_markup=markup)

    # ------------------------------------------------------------ xodim --

    @dp.callback_query(F.data.startswith("sagr:ok:"))
    async def agreement_consent(callback: CallbackQuery) -> None:
        if callback.from_user is None or not _private(callback):
            await callback.answer("Bu amal faqat shaxsiy chatda.", show_alert=True)
            return
        try:
            agreement_id = int(callback.data.split(":")[2])
        except ValueError:
            await callback.answer()
            return
        outcome = sa.record_consent(agreement_id, callback.from_user.id)
        if outcome == sa.CONSENT_RECORDED:
            await callback.answer("Rozilik qayd etildi.")
            await callback.message.edit_text(f"{callback.message.text or ''}\n\n✅ Rozilik qayd etildi.")
            agreement = sa.get_agreement(agreement_id)
            profile = employees.get_profile(callback.from_user.id) or {"user_id": callback.from_user.id}
            try:
                await callback.bot.send_message(
                    FOUNDER_ID,
                    f"✅ {_full_name(profile)} oylik kelishuvga (versiya {sa.version_number(agreement['employee_id'], agreement_id)}) rozilik berdi.",
                )
            except Exception as error:  # noqa: BLE001
                logger.warning("Founderga rozilik xabari ketmadi: %s", type(error).__name__)
            return
        messages = {
            sa.CONSENT_ALREADY: "Bu kelishuv allaqachon tasdiqlangan.",
            sa.CONSENT_NOT_OWNER: "Bu tugma siz uchun emas.",
            sa.CONSENT_SUPERSEDED: "Bu kelishuv yangilangan. Yangi versiyani «💵 Oylik kelishuvim» orqali oching.",
            sa.CONSENT_UNKNOWN: "Kelishuv topilmadi.",
        }
        await callback.answer(messages[outcome], show_alert=True)

    async def _notify_issue(bot, issue: dict, agreement: dict) -> int:
        profile = employees.get_profile(issue["employee_id"], include_contacts=False) or {"user_id": issue["employee_id"]}
        managers = sa.branch_managers(issue["branch"])
        names = ", ".join(_full_name(employees.get_profile(m, include_contacts=False) or {"user_id": m}) for m in managers)
        text = "\n".join(
            [
                "❓ Xodim oylik kelishuvini tushunmadi",
                f"👤 Xodim: {_full_name(profile)}",
                f"🏬 Filial: {issue.get('branch') or '-'}",
                f"📄 Kelishuv versiyasi: {sa.version_number(issue['employee_id'], agreement['id'])}",
                f"👔 Mas'ul: filial rahbari{' — ' + names if names else ' (belgilanmagan — Founder)'}",
                f"⏰ Muddat: bugun, {sa.format_date(issue['due_date'])}",
            ]
        )
        markup = _kb(
            [("📄 Kelishuvni ochish", f"sagr:view:{agreement['id']}")],
            [("✅ Tushuntirildi", f"sagr:res:{issue['id']}:explained")],
            [("📝 Yangi kelishuv", f"sagr:res:{issue['id']}:new_agreement")],
            [("🤝 Kelishilmadi", f"sagr:res:{issue['id']}:disagreed")],
        )
        delivered = 0
        for recipient in dict.fromkeys([FOUNDER_ID, *managers]):
            try:
                await bot.send_message(recipient, text, reply_markup=markup)
                delivered += 1
            except Exception as error:  # noqa: BLE001
                logger.warning("Kelishuv savoli xabari ketmadi (issue=%s): %s", issue["id"], type(error).__name__)
        sa.set_issue_notified(issue["id"], delivered)
        return delivered

    @dp.callback_query(F.data.startswith("sagr:no:"))
    async def agreement_not_understood(callback: CallbackQuery) -> None:
        if callback.from_user is None or not _private(callback):
            await callback.answer("Bu amal faqat shaxsiy chatda.", show_alert=True)
            return
        try:
            agreement_id = int(callback.data.split(":")[2])
        except ValueError:
            await callback.answer()
            return
        outcome, issue = sa.ask_not_understood(agreement_id, callback.from_user.id)
        if outcome == sa.ISSUE_OPENED:
            await callback.answer("Savolingiz qabul qilindi.")
            delivered = await _notify_issue(callback.bot, issue, sa.get_agreement(agreement_id))
            note = (
                "❓ Savolingiz rahbarga yuborildi. Tushuntirishgach shu yerda rozilik bera olasiz."
                if delivered
                else "❓ Savolingiz saqlandi, lekin rahbarga xabar yetkazib bo'lmadi. Iltimos, rahbaringizga o'zingiz murojaat qiling."
            )
            await callback.message.edit_text(
                f"{callback.message.text or ''}\n\n{note}", reply_markup=_consent_kb(agreement_id, with_question=False)
            )
            return
        messages = {
            sa.ISSUE_ALREADY: "Savolingiz allaqachon yuborilgan.",
            sa.ISSUE_CONSENTED: "Siz bu kelishuvga allaqachon rozilik bergansiz.",
            sa.CONSENT_NOT_OWNER: "Bu tugma siz uchun emas.",
            sa.CONSENT_SUPERSEDED: "Bu kelishuv yangilangan. Yangi versiyani «💵 Oylik kelishuvim» orqali oching.",
            sa.CONSENT_UNKNOWN: "Kelishuv topilmadi.",
        }
        await callback.answer(messages[outcome], show_alert=True)

    @dp.callback_query(F.data.startswith("sagr:res:"))
    async def agreement_issue_resolve(callback: CallbackQuery) -> None:
        if callback.from_user is None or not _private(callback):
            await callback.answer("Bu amal faqat shaxsiy chatda.", show_alert=True)
            return
        try:
            _, _, raw_id, code = callback.data.split(":")
            issue_id = int(raw_id)
        except ValueError:
            await callback.answer()
            return
        result = sa.resolve_issue(issue_id, callback.from_user.id, code)
        if result == "resolved":
            await callback.answer("Hal qilindi.")
            await callback.message.edit_text(
                f"{callback.message.text or ''}\n\n✅ Hal qilindi: {sa.ISSUE_OUTCOMES[code]}. "
                "Eslatma: bu xodim roziligini almashtirmaydi."
            )
            return
        await callback.answer(
            {"already": "Bu savol allaqachon yopilgan.", "denied": "Bu amal siz uchun emas."}.get(result, "Savol topilmadi."),
            show_alert=True,
        )

    @dp.callback_query(F.data.startswith("sagr:view:"))
    async def agreement_view(callback: CallbackQuery) -> None:
        if callback.from_user is None or not _private(callback):
            await callback.answer("Bu amal faqat shaxsiy chatda.", show_alert=True)
            return
        try:
            agreement = sa.get_agreement(int(callback.data.split(":")[2]))
        except ValueError:
            agreement = None
        profile = employees.get_profile(agreement["employee_id"], include_contacts=False) if agreement else None
        if agreement is None or profile is None or not sa.can_view(callback.from_user.id, agreement["employee_id"], profile.get("branch")):
            await callback.answer("Bu kelishuvni ko'rishga ruxsatingiz yo'q.", show_alert=True)
            return
        await callback.answer()
        await callback.message.answer(
            f"👤 {_full_name(profile)}\n{_employee_text(agreement, agreement['employee_id'])}\n\nHolat: {sa.consent_status_text(agreement)}"
        )

    @dp.message(Command("filialkelishuv"))
    async def branch_agreements(message: Message) -> None:
        """Rahbar (o'z filiali) / Founder: xodimlarning joriy kelishuv versiyasini ochish tugmalari."""
        if message.from_user is None or not _private(message):
            return
        viewer = message.from_user.id
        from config import RECRUITING_BRANCH_NAMES

        rows = []
        for branch in RECRUITING_BRANCH_NAMES:
            for profile in employees.list_approved_by_branch(branch):
                latest = sa.latest_agreement_id(profile["user_id"])
                if latest and sa.can_view(viewer, profile["user_id"], profile.get("branch")) and profile["user_id"] != viewer:
                    rows.append([(f"{_full_name(profile)} — {branch}", f"sagr:view:{latest}")])
        if not rows:
            await message.answer("Ko'rsatish mumkin bo'lgan kelishuv topilmadi.")
            return
        await message.answer("📄 Kelishuvni oching:", reply_markup=_kb(*rows[:30]))

    @dp.message(Command("mykelishuv"))
    @dp.message(F.text == EMPLOYEE_BUTTON)
    async def my_agreement(message: Message) -> None:
        if message.from_user is None:
            return
        if not _private(message):
            await message.answer("Oylik kelishuvi faqat shaxsiy chatda ko'rsatiladi.")
            return
        user_id = message.from_user.id
        profile = employees.get_profile(user_id)
        if not sa.can_view(user_id, user_id, profile.get("branch") if profile else None):
            return
        current, upcoming = sa.get_current(user_id), sa.get_all_upcoming(user_id)
        if current is None and not upcoming:
            salary = discipline.get_salary(user_id)
            await message.answer("\n".join(sa.view_lines(user_id, salary["fixed_salary"])))
            return
        cards = []
        if current is not None:
            cards.append((current, "💵 Amaldagi kelishuv"))
        for item in upcoming:
            cards.append((item, f"⏭ Kelajakdagi kelishuv ({sa.format_date(item['effective_from'])} dan; hozirgi shartlarni o'zgartirmaydi)"))
        for agreement, title in cards:
            # Tugmalar aynan shu kartaning versiyasiga bog'langan; boshqa versiyaga rozilik yozilmaydi.
            text = f"{_employee_text(agreement, user_id, title)}\n\nHolat: {sa.consent_status_text(agreement)}"
            markup = (
                _consent_kb(agreement["id"], with_question=sa.issue_for_agreement(agreement["id"]) is None)
                if sa.pending_consent(agreement)
                else None
            )
            await message.answer(text, reply_markup=markup)
