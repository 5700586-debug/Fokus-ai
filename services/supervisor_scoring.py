"""Nazoratchi kunlik ballari — DB'da saqlanadi, dashboard/star engine
shu yerdan o'qiydi.
"""

from repositories import performance as performance_repo


def record_score(user_id: int, scored_by: int, score_date: str, score: int, comment: str | None = None) -> None:
    if not 0 <= score <= 100:
        raise ValueError("ball 0 dan 100 gacha bo'lishi kerak")

    performance_repo.record_score(user_id, scored_by, score_date, score, comment)


def get_month_average(user_id: int, year_month: str) -> float | None:
    start_date = f"{year_month}-01"
    end_date = f"{year_month}-31"

    scores = performance_repo.get_scores_in_range(user_id, start_date, end_date)
    if not scores:
        return None

    return sum(row["score"] for row in scores) / len(scores)


def get_scores_for_month(user_id: int, year_month: str) -> list[dict]:
    return performance_repo.get_scores_in_range(user_id, f"{year_month}-01", f"{year_month}-31")
