from services import cross_check


def test_start_session_is_idempotent():
    session1 = cross_check.start_session("2026-01-01", employee_a_id=1, employee_b_id=2)
    session2 = cross_check.start_session("2026-01-01", employee_a_id=1, employee_b_id=2)

    assert session1["id"] == session2["id"]
    assert session1["status"] == "pending"


def test_compare_session_no_discrepancy():
    session = cross_check.start_session("2026-01-01", employee_a_id=1, employee_b_id=2)

    cross_check.record_answer(session["id"], 1, "Bugun necha kg kartoshka oldingiz?", "50 kg")
    cross_check.record_answer(session["id"], 2, "Bugun necha kg kartoshka oldingiz?", "50 kg")

    differences = cross_check.compare_session(session["id"], employee_a_id=1, employee_b_id=2)
    assert differences == []


def test_compare_session_finds_discrepancy():
    session = cross_check.start_session("2026-01-01", employee_a_id=1, employee_b_id=2)

    cross_check.record_answer(session["id"], 1, "Narxi qancha edi?", "5000 so'm")
    cross_check.record_answer(session["id"], 2, "Narxi qancha edi?", "6000 so'm")

    differences = cross_check.compare_session(session["id"], employee_a_id=1, employee_b_id=2)
    assert len(differences) == 1
    assert differences[0].answer_a == "5000 so'm"
    assert differences[0].answer_b == "6000 so'm"


def test_format_discrepancy_report():
    no_diff_report = cross_check.format_discrepancy_report([], "Ali", "Vali")
    assert "tafovut aniqlanmadi" in no_diff_report

    diff = cross_check.AnswerDifference(question="Narxi?", answer_a="5000", answer_b="6000")
    report = cross_check.format_discrepancy_report([diff], "Ali", "Vali")
    assert "Ali: 5000" in report
    assert "Vali: 6000" in report
