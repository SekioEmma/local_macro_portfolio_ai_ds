from data_providers import official_energy_history_provider as provider


def test_official_energy_history_maps_fred_rows_to_safe_observations():
    config = {
        "deepseek_market_data_package": {
            "oil_and_energy": {
                "wti_oil": {
                    "provider": "fred",
                    "series_id": "DCOILWTICO",
                    "name": "WTI",
                    "unit": "USD per barrel",
                    "source_tier": "official_or_public_data_api",
                },
                "brent_oil": {
                    "provider": "fred",
                    "series_id": "DCOILBRENTEU",
                    "name": "Brent",
                    "unit": "USD per barrel",
                    "source_tier": "official_or_public_data_api",
                },
            }
        }
    }
    energy_config = provider.load_official_energy_history_config(config)
    raw = {
        "wti": {
            "status": "ok",
            "series_id": "DCOILWTICO",
            "timestamp": "2026-03-03T00:00:00+00:00",
            "data": [
                {"date": "2026-03-02", "value": "77.0"},
                {"date": "2026-01-31", "value": "70.0"},
            ],
        }
    }

    normalized = provider.normalize_official_energy_history(
        raw,
        energy_config,
        fetched_at="2026-03-03T00:00:00+00:00",
    )
    observations = provider.build_market_observations(normalized["records"])
    text = str(observations).lower()

    assert normalized["errors"] == []
    assert [item["observation_date"] for item in observations] == ["2026-01-31", "2026-03-02"]
    assert observations[0]["metric_key"] == "wti"
    assert observations[0]["source"] == "FRED:DCOILWTICO"
    assert observations[0]["source_badge"] == "official"
    assert observations[0]["provider"] == "FRED"
    assert observations[0]["ai_context_allowed"] is True
    assert "raw_provider" not in text
    assert "api_key" not in text
    assert "holding" not in text


def test_fetch_official_energy_history_uses_injected_fetcher_without_network():
    config = {"wti": {"series_id": "DCOILWTICO"}}

    def fake_fetcher(series_id, limit):
        assert series_id == "DCOILWTICO"
        assert limit == 2
        return {"status": "ok", "series_id": series_id, "data": []}

    result = provider.fetch_official_energy_history(config, limit=2, fetcher=fake_fetcher)

    assert result["status"] == "ok"
    assert set(result["raw_data"]) == {"wti"}
