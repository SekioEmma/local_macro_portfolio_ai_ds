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


def test_market_data_package_includes_investment_grade_spread_from_existing_fred_provider(monkeypatch):
    def fake_latest(series_id):
        values = {
            "BAMLH0A0HYM2": (3.4, "2026-01-02"),
            "BAMLC0A0CM": (1.2, "2026-01-02"),
            "VIXCLS": (18.0, "2026-01-02"),
            "DFII10": (2.0, "2026-01-02"),
            "T10YIE": (2.3, "2026-01-02"),
            "T10Y2Y": (0.4, "2026-01-02"),
        }
        value, observation_date = values.get(series_id, (1.0, "2026-01-02"))
        return {
            "series_id": series_id,
            "value": value,
            "observation_date": observation_date,
            "source": "FRED",
            "timestamp": "2026-01-03T00:00:00+00:00",
            "status": "ok",
            "error": None,
        }

    monkeypatch.setattr(market_data_service.fred_provider, "get_fred_latest", fake_latest)
    monkeypatch.setattr(market_data_service, "_fred_history", lambda series_id, limit: [])

    config = market_data_service.load_data_source_config("configs/data_sources.yaml")
    financial_conditions = {
        key: market_data_service.get_financial_condition_item(key, config)
        for key in market_data_service.FINANCIAL_CONDITION_KEYS
    }
    package = market_data_service.get_market_data_package(
        config,
        financial_conditions=financial_conditions,
        generated_at="2026-01-03T00:00:00+00:00",
    )
    existing = package["existing_financial_conditions"]

    assert financial_conditions["investment_grade_spread"]["status"] == "ok"
    assert financial_conditions["investment_grade_spread"]["source"] == "FRED"
    assert financial_conditions["investment_grade_spread"]["series_id"] == "BAMLC0A0CM"
    assert existing["investment_grade_spread"]["source_tier"] == "official_or_public_data_api"
    assert existing["investment_grade_spread"]["value"] == 1.2
