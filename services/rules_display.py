"""Founder uchun ``rules`` jadvalini SODDA ko'rinishda chiqarish ("⚙️ Sozlamalar → 🛠 Qoidalar" va ``/listrules``).

Texnik kalitlar (``bos.penalty_amounts`` kabi) o'rniga o'zbekcha nom va birligi bilan qiymat ko'rsatiladi.
Kodda endi ishlatilmaydigan yoki faqat ichki texnik kalitlar ko'rsatilmaydi. Noma'lum (yangi) kalit yo'qolib
qolmasin deb "Boshqa" bo'limida xom holda chiqadi. Qiymatlar O'ZGARTIRILMAYDI — faqat ko'rinish.
"""

# Ko'rsatilmaydi: kod ularni o'qimaydi (eski/o'chirilgan) yoki faqat ichki texnik qiymat.
HIDDEN_KEYS = frozenset({
    "bos.day_close_deadline",        # eski 20:00 muddati — ish kuni endi 06:00 da almashadi
    "bos.supervisor_late_penalty",   # kech yopish jarimasi o'chirilgan
    "bos.work_day_start",            # kodda o'qilmaydi
    "bos.auto_close_start_date",     # ichki texnik sana
    "star.min",
    "star.max",
    "saturn.group_chat_id",
    "saturn.dashboard_times",
    "saturn.morning_image_enabled",
    "saturn.night_image_enabled",
})

_GRADE_NAMES = {"alo": "A'lo", "norma": "Norma", "chala": "Chala", "bajarilmagan": "Bajarilmagan"}
_SHIFT_NAMES = {"fixed_1": "1-smena", "fixed_2": "2-smena"}


def _money(value: str) -> str:
    try:
        return f"{int(float(value)):,}".replace(",", " ") + " so'm"
    except ValueError:
        return value


def _yes_no(value: str) -> str:
    return {"1": "ha", "0": "yo'q"}.get(value.strip(), value)


def _suffix(unit: str):
    return lambda value: f"{value} {unit}"


def _ball_list(value: str) -> str:
    parts = [part.strip() for part in value.split(",") if part.strip()]
    return ", ".join(parts) + " ball" if parts else value


# kalit -> (bo'lim, nom, qiymat formati)
_LABELS: dict[str, tuple[str, str, object]] = {
    "bos.penalty_amounts": ("Baholash", "Minus tugmalari", _ball_list),
    "bos.strict_close_start": ("Baholash", "Qat'iy kun yopish boshlanadigan sana", str),
    "full_bonus_month.min_supervisor_score": ("Oylik to'liq bonus shartlari", "Nazoratchi bahosi kamida", _suffix("ball")),
    "full_bonus_month.require_attendance_ok": ("Oylik to'liq bonus shartlari", "Davomat joyida bo'lishi", _yes_no),
    "full_bonus_month.require_no_serious_violation": (
        "Oylik to'liq bonus shartlari", "Jiddiy qoidabuzarlik bo'lmasligi", _yes_no,
    ),
    "full_bonus_month.require_checklist_completed": ("Oylik to'liq bonus shartlari", "Chek-list bajarilishi", _yes_no),
    "cash_shift.tolerance": ("Kassa", "Ruxsat etilgan farq", _money),
    "cash_shift.retry_limit": ("Kassa", "Summani qayta kiritish", _suffix("marta")),
    "cash_shift.manual_close_review": ("Kassa", "Smena yopilishini moliyachi tekshiradi", _yes_no),
    "cash_expense.baseline_min_observations": ("Kassa", "Xarajat odatini bilish uchun kamida", _suffix("kun")),
    "cash_expense.anomaly_multiplier": ("Kassa", "Xarajat odatdagidan oshsa shubhali", _suffix("barobar")),
    "inventory.variance_threshold": ("Ombor", "Sanoq farqi chegarasi", _money),
    "inventory.reminder_time": ("Ombor", "Sanoq eslatmasi vaqti", str),
    "calibration.daily_question_time": ("Boshqa", "Kunlik savol vaqti", str),
    "vehicle.oil_change_interval_km": ("Mashina", "Moy almashtirish oralig'i", _suffix("km")),
    "saturn.morning_time": ("Saturn guruhi", "Ertalabki xabar vaqti", str),
    "saturn.evening_time": ("Saturn guruhi", "Kechki xabar vaqti", str),
    "saturn.tip_time": ("Saturn guruhi", "Maslahat xabari vaqti", str),
}

_SECTION_ORDER = (
    "Baholash", "Yulduz bonuslari", "Oylik to'liq bonus shartlari", "Smenalar", "Kassa", "Ombor", "Mashina",
    "Saturn guruhi", "Boshqa",
)


def _describe(key: str, value: str) -> tuple[str, str, str] | None:
    if key in HIDDEN_KEYS:
        return None
    if key in _LABELS:
        section, name, fmt = _LABELS[key]
        return section, name, fmt(value)
    head, _, tail = key.rpartition(".")
    if head == "bos.grade_points" and tail in _GRADE_NAMES:
        return "Baholash", f"{_GRADE_NAMES[tail]} bahosi", f"{value} ball"
    if head == "bonus.stars" and tail.isdigit():
        return "Yulduz bonuslari", f"{tail} ⭐", _money(value)
    if key.startswith("schedule.") and tail in ("start", "end"):
        mode = key.split(".")[1]
        name = _SHIFT_NAMES.get(mode, mode)
        return "Smenalar", f"{name} {'boshlanishi' if tail == 'start' else 'tugashi'}", value
    return "Boshqa", key, value  # noma'lum yangi kalit — yashirilmaydi


def rules_text(rules: dict[str, str]) -> str:
    grouped: dict[str, list[tuple[str, str]]] = {}
    grade_order = {f"bos.grade_points.{name}": f"bos.grade_points.{index}" for index, name in enumerate(_GRADE_NAMES)}
    for key, value in sorted(rules.items(), key=lambda item: grade_order.get(item[0], item[0])):
        described = _describe(key, value)
        if described is None:
            continue
        section, name, shown = described
        grouped.setdefault(section, []).append((name, shown))
    if not grouped:
        return "Qoidalar topilmadi."
    order = {name: index for index, name in enumerate(_SECTION_ORDER)}
    blocks = []
    for section in sorted(grouped, key=lambda name: order.get(name, len(order))):
        lines = "\n".join(f"• {name}: {shown}" for name, shown in grouped[section])
        blocks.append(f"📌 {section}\n{lines}")
    return "⚙️ Joriy sozlamalar\n\n" + "\n\n".join(blocks)
