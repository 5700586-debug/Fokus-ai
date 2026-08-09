from services import market_observation


def test_log_and_list_recent_observations():
    market_observation.log_observation(
        employee_id=1,
        observation_date="2026-01-01",
        product="Kartoshka",
        wholesale_price="3000",
    )

    recent = market_observation.recent_observations()
    assert len(recent) == 1
    assert recent[0]["product"] == "Kartoshka"
    assert recent[0]["wholesale_price"] == "3000"


def test_price_trend_filters_by_product():
    market_observation.log_observation(
        employee_id=1, observation_date="2026-01-01", product="Kartoshka", wholesale_price="3000"
    )
    market_observation.log_observation(
        employee_id=1, observation_date="2026-01-05", product="Kartoshka", wholesale_price="3200"
    )
    market_observation.log_observation(
        employee_id=1, observation_date="2026-01-03", product="Pomidor", wholesale_price="5000"
    )

    trend = market_observation.price_trend("Kartoshka")
    assert [row["wholesale_price"] for row in trend] == ["3000", "3200"]
