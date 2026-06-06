from data_providers import market_data_service


def test_market_data_package_builds_labor_indicators_from_existing_fred_provider(monkeypatch):
    def fake_latest(series_id):
        values = {
            "UNRATE": (4.0, "2026-01-01"),
            "ICSA": (230000.0, "2026-01-04"),
        }
        value, observation_date = values.get(series_id, (1.0, "2026-01-01"))
        return {
            "series_id": series_id,
            "value": value,
            "observation_date": observation_date,
            "source": "FRED",
            "timestamp": "2026-01-05T00:00:00+00:00",
            "status": "ok",
            "error": None,
        }

    monkeypatch.setattr(market_data_service.fred_provider, "get_fred_latest", fake_latest)
    monkeypatch.setattr(market_data_service, "_fred_history", lambda series_id, limit: [])

    config = market_data_service.load_data_source_config("configs/data_sources.yaml")
    package = market_data_service.get_market_data_package(
        config,
        financial_conditions={},
        generated_at="2026-01-05T00:00:00+00:00",
    )
    labor = package["labor_indicators"]

    assert labor["unemployment_rate"]["status"] == "ok"
    assert labor["unemployment_rate"]["source"] == "FRED:UNRATE"
    assert labor["unemployment_rate"]["value"] == 4.0
    assert labor["initial_jobless_claims"]["status"] == "ok"
    assert labor["initial_jobless_claims"]["source"] == "FRED:ICSA"
    assert labor["initial_jobless_claims"]["value"] == 230000.0
