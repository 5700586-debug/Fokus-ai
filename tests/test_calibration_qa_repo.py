from repositories import baselines as repo


def test_create_session_creates_row():
    session = repo.create_session(111, "taminotchi", "2026-01-01")

    assert session["user_id"] == 111
    assert session["role_key"] == "taminotchi"
    assert session["status"] == "active"


def test_create_session_is_idempotent():
    first = repo.create_session(111, "taminotchi", "2026-01-01")
    second = repo.create_session(111, "taminotchi", "2026-06-01")

    assert first["id"] == second["id"]
    assert second["start_date"] == "2026-01-01"


def test_get_session_returns_none_when_missing():
    assert repo.get_session(999) is None


def test_record_and_get_active_question():
    session = repo.create_session(111, "taminotchi", "2026-01-01")

    question_id = repo.record_question(
        session["id"], 111, "taminotchi", "2026-01-01", "narx solishtirish",
        "Bugun narxlarni solishtirdingizmi?",
    )

    active = repo.get_active_question(111)
    assert active["id"] == question_id
    assert active["answer_text"] is None


def test_active_question_is_none_after_answered():
    session = repo.create_session(111, "taminotchi", "2026-01-01")
    question_id = repo.record_question(
        session["id"], 111, "taminotchi", "2026-01-01", "narx solishtirish", "Savol?"
    )

    repo.record_answer(question_id, "Ha, 3 ta do'kondan so'radim")

    assert repo.get_active_question(111) is None
    answered = repo.get_question(question_id)
    assert answered["answer_text"] == "Ha, 3 ta do'kondan so'radim"
    assert answered["answered_at"] is not None


def test_active_question_picks_most_recent():
    session = repo.create_session(111, "taminotchi", "2026-01-01")
    first_id = repo.record_question(
        session["id"], 111, "taminotchi", "2026-01-01", "narx solishtirish", "Savol 1?"
    )
    repo.record_answer(first_id, "Javob 1")
    second_id = repo.record_question(
        session["id"], 111, "taminotchi", "2026-01-01", "tashabbus", "Savol 2?"
    )

    active = repo.get_active_question(111)
    assert active["id"] == second_id


def test_get_questions_for_date_filters_correctly():
    session = repo.create_session(111, "taminotchi", "2026-01-01")
    repo.record_question(session["id"], 111, "taminotchi", "2026-01-01", "narx solishtirish", "S1")
    repo.record_question(session["id"], 111, "taminotchi", "2026-01-01", "tashabbus", "S2")
    repo.record_question(session["id"], 111, "taminotchi", "2026-01-02", "vazifani yopish", "S3")

    today_questions = repo.get_questions_for_date(111, "2026-01-01")
    assert len(today_questions) == 2
    assert {q["dimension"] for q in today_questions} == {"narx solishtirish", "tashabbus"}


def test_increment_follow_up_count():
    session = repo.create_session(111, "taminotchi", "2026-01-01")
    question_id = repo.record_question(
        session["id"], 111, "taminotchi", "2026-01-01", "narx solishtirish", "Savol?"
    )

    assert repo.increment_follow_up(question_id) == 1
    assert repo.increment_follow_up(question_id) == 2


def test_parent_question_id_links_follow_up():
    session = repo.create_session(111, "taminotchi", "2026-01-01")
    original_id = repo.record_question(
        session["id"], 111, "taminotchi", "2026-01-01", "narx solishtirish", "Savol?"
    )
    follow_up_id = repo.record_question(
        session["id"], 111, "taminotchi", "2026-01-01", "narx solishtirish", "Aniqroq yozing?",
        parent_question_id=original_id,
    )

    follow_up = repo.get_question(follow_up_id)
    assert follow_up["parent_question_id"] == original_id


def test_is_cross_check_flag_stored():
    session = repo.create_session(111, "taminotchi", "2026-01-01")
    question_id = repo.record_question(
        session["id"], 111, "taminotchi", "2026-01-01", "bozor_hamkorligi", "Savol?",
        is_cross_check=True,
    )

    question = repo.get_question(question_id)
    assert question["is_cross_check"] == 1
