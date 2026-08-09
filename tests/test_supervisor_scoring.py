import pytest

from services import supervisor_scoring


def test_record_and_average_scores():
    supervisor_scoring.record_score(1, scored_by=99, score_date="2026-01-05", score=80)
    supervisor_scoring.record_score(1, scored_by=99, score_date="2026-01-10", score=100)

    assert supervisor_scoring.get_month_average(1, "2026-01") == 90


def test_average_is_none_when_no_scores():
    assert supervisor_scoring.get_month_average(1, "2026-02") is None


def test_recording_same_day_twice_overwrites():
    supervisor_scoring.record_score(1, scored_by=99, score_date="2026-01-05", score=80)
    supervisor_scoring.record_score(1, scored_by=99, score_date="2026-01-05", score=60)

    scores = supervisor_scoring.get_scores_for_month(1, "2026-01")
    assert len(scores) == 1
    assert scores[0]["score"] == 60


def test_score_out_of_range_rejected():
    with pytest.raises(ValueError):
        supervisor_scoring.record_score(1, scored_by=99, score_date="2026-01-05", score=101)
