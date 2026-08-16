from datetime import date

from services import saturn_season


def test_every_month_maps_to_a_season():
    expected = {
        1: saturn_season.WINTER, 2: saturn_season.WINTER, 3: saturn_season.SPRING,
        4: saturn_season.SPRING, 5: saturn_season.SPRING, 6: saturn_season.SUMMER,
        7: saturn_season.SUMMER, 8: saturn_season.SUMMER, 9: saturn_season.AUTUMN,
        10: saturn_season.AUTUMN, 11: saturn_season.AUTUMN, 12: saturn_season.WINTER,
    }
    for month, season in expected.items():
        assert saturn_season.season_for_date(date(2026, month, 15)) == season


def test_boundary_feb_28_is_winter_non_leap_year():
    assert saturn_season.season_for_date(date(2026, 2, 28)) == saturn_season.WINTER


def test_boundary_feb_29_is_winter_leap_year():
    assert saturn_season.season_for_date(date(2024, 2, 29)) == saturn_season.WINTER


def test_boundary_march_1_is_spring():
    assert saturn_season.season_for_date(date(2026, 3, 1)) == saturn_season.SPRING


def test_boundary_may_31_is_spring():
    assert saturn_season.season_for_date(date(2026, 5, 31)) == saturn_season.SPRING


def test_boundary_june_1_is_summer():
    assert saturn_season.season_for_date(date(2026, 6, 1)) == saturn_season.SUMMER


def test_boundary_august_31_is_summer():
    assert saturn_season.season_for_date(date(2026, 8, 31)) == saturn_season.SUMMER


def test_boundary_september_1_is_autumn():
    assert saturn_season.season_for_date(date(2026, 9, 1)) == saturn_season.AUTUMN


def test_boundary_november_30_is_autumn():
    assert saturn_season.season_for_date(date(2026, 11, 30)) == saturn_season.AUTUMN


def test_boundary_december_1_is_winter():
    assert saturn_season.season_for_date(date(2026, 12, 1)) == saturn_season.WINTER


def test_current_season_uses_company_time_today(monkeypatch):
    import company_time

    monkeypatch.setattr(company_time, "today", lambda: date(2026, 7, 10))
    assert saturn_season.current_season() == saturn_season.SUMMER
