"""Founder "🛠 Qoidalar" ekrani: texnik kalitlar o'rniga sodda o'zbekcha nom va birlik."""

from services import rules_display

SEEDED = {
    "bos.day_close_deadline": "20:00",
    "bos.supervisor_late_penalty": "40",
    "bos.grade_points.bajarilmagan": "0",
    "bos.grade_points.chala": "1",
    "bos.grade_points.norma": "2",
    "bos.grade_points.alo": "3",
    "bos.penalty_amounts": "10,20,30",
    "bonus.stars.1": "50000",
    "cash_shift.tolerance": "20000",
    "full_bonus_month.require_attendance_ok": "1",
    "schedule.fixed_2.end": "01:00",
    "star.min": "0",
}


def test_known_rules_are_shown_in_plain_uzbek():
    text = rules_display.rules_text(SEEDED)
    assert "Minus tugmalari: 10, 20, 30 ball" in text
    assert "1 ⭐: 50 000 so'm" in text
    assert "Ruxsat etilgan farq: 20 000 so'm" in text
    assert "Davomat joyida bo'lishi: ha" in text
    assert "2-smena tugashi: 01:00" in text
    assert text.index("A'lo bahosi") < text.index("Norma bahosi") < text.index("Chala bahosi") < text.index("Bajarilmagan bahosi")


def test_technical_keys_and_unused_rules_are_not_shown():
    text = rules_display.rules_text(SEEDED)
    for raw in ("bos.", "bonus.stars", "cash_shift", "star.min", "20:00", "= "):
        assert raw not in text


def test_unknown_new_key_is_not_lost():
    assert "yangi.kalit: 7" in rules_display.rules_text({"yangi.kalit": "7"})


def test_empty():
    assert rules_display.rules_text({"star.min": "0"}) == "Qoidalar topilmadi."
