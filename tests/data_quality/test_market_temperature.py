from market.market_temperature import (
    classify_equity_temperature,
    classify_inflation_pressure,
    classify_rate_pressure,
    score_market_temperature,
)


def _change(percent_change: float = 0.0, absolute_change: float = 0.0) -> dict:
    return {
        "percent_change": percent_change,
        "absolute_change": absolute_change,
        "status": "ok",
    }


def test_equity_temperature_thresholds():
    assert classify_equity_temperature(
        _change(6),
        _change(13),
        _change(7),
        _change(14),
    )["level"] == "hot"
    assert classify_equity_temperature(
        _change(-9),
        _change(-2),
        _change(-10),
        _change(-1),
    )["level"] == "cold"
    assert classify_equity_temperature(
        _change(1),
        _change(2),
        _change(1),
        _change(2),
    )["level"] == "neutral"


def test_rate_pressure_thresholds():
    assert classify_rate_pressure(4.6, _change(absolute_change=0.1))["level"] == "high"
    assert classify_rate_pressure(4.1, _change(absolute_change=0.1))["level"] == "medium"
    assert classify_rate_pressure(3.8, _change(absolute_change=0.1))["level"] == "low"


def test_inflation_pressure_thresholds():
    high = classify_inflation_pressure(_change(4.1), _change(2.5), _change(), _change())
    medium = classify_inflation_pressure(_change(2.5), _change(3.1), _change(), _change())
    low = classify_inflation_pressure(_change(2.5), _change(2.4), _change(), _change())

    assert high["level"] == "high"
    assert medium["level"] == "medium"
    assert low["level"] == "low"


def test_score_market_temperature_has_stable_regime_and_risk_level():
    result = score_market_temperature(
        {
            "sp500_1m_change": _change(4),
            "sp500_3m_change": _change(9),
            "nasdaq_1m_change": _change(4),
            "nasdaq_3m_change": _change(9),
            "dgs10_latest": 4.6,
            "dgs10_1m_change": _change(absolute_change=0.1),
            "cpi_yoy_change": _change(2.5),
            "pce_yoy_change": _change(2.4),
            "cpi_mom_change": _change(),
            "pce_mom_change": _change(),
            "nonfarm_mom_change": _change(absolute_change=100),
            "usd_cny_1m_change": _change(0.2),
        }
    )

    assert result["overall_regime"] == "warm_but_rate_sensitive"
    assert result["risk_level"] == "high"


def test_missing_inputs_return_unknown_classifications_without_uncaught_exception():
    result = score_market_temperature({})

    assert result["equity_temperature"]["level"] == "unknown"
    assert result["rate_pressure"]["level"] == "unknown"
    assert result["inflation_pressure"]["level"] == "unknown"
    assert result["risk_level"] == "low"
    assert result["data_limitations"]
