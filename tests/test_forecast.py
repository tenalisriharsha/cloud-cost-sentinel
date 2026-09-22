from datetime import date, timedelta

import pandas as pd
import pytest

from cloud_cost_sentinel.config import Settings
from cloud_cost_sentinel.forecasting.prophet_forecast import (
    MIN_HISTORY_DAYS,
    calculate_budget_drift,
    daily_total_costs,
    forecast_daily_costs,
)
from cloud_cost_sentinel.models import ForecastPoint


def _synthetic_daily_df(days: int, base: float = 40.0, trend_per_day: float = 0.0) -> pd.DataFrame:
    """Build a synthetic multi-service cost DataFrame spanning ``days`` days.

    Two services per day (so aggregation across services is exercised, not
    just across days), with an optional linear trend so forecast direction
    can be sanity-checked.
    """
    start = date(2026, 1, 1)
    rows = []
    for i in range(days):
        day = start + timedelta(days=i)
        day_base = base + trend_per_day * i
        rows.append(
            {
                "usage_account_id": "111122223333",
                "service": "AmazonEC2",
                "usage_type": "Test",
                "region": "us-east-1",
                "usage_date": day,
                "unblended_cost": day_base * 0.7,
                "currency": "USD",
            }
        )
        rows.append(
            {
                "usage_account_id": "111122223333",
                "service": "AmazonS3",
                "usage_type": "Test",
                "region": "us-east-1",
                "usage_date": day,
                "unblended_cost": day_base * 0.3,
                "currency": "USD",
            }
        )
    return pd.DataFrame(rows)


def _forecast_points(days: int = 7) -> list[ForecastPoint]:
    return [
        ForecastPoint(
            usage_date=date(2026, 3, 1) + timedelta(days=i),
            forecast_cost=100.0,
            forecast_low=90.0,
            forecast_high=110.0,
        )
        for i in range(days)
    ]


def test_daily_total_costs_aggregates_across_services():
    df = pd.DataFrame(
        [
            {"service": "AmazonEC2", "usage_date": date(2026, 1, 1), "unblended_cost": 10.0},
            {"service": "AmazonS3", "usage_date": date(2026, 1, 1), "unblended_cost": 5.0},
            {"service": "AmazonEC2", "usage_date": date(2026, 1, 2), "unblended_cost": 7.0},
        ]
    )
    daily = daily_total_costs(df)
    assert list(daily.columns) == ["ds", "y"]
    assert len(daily) == 2
    day_one = daily[daily["ds"] == date(2026, 1, 1)].iloc[0]
    assert day_one["y"] == pytest.approx(15.0)


def test_daily_total_costs_handles_empty_dataframe():
    df = pd.DataFrame(columns=["service", "usage_date", "unblended_cost"])
    daily = daily_total_costs(df)
    assert daily.empty
    assert list(daily.columns) == ["ds", "y"]


def test_forecast_daily_costs_requires_minimum_history():
    df = _synthetic_daily_df(days=MIN_HISTORY_DAYS - 1)
    with pytest.raises(ValueError, match="at least"):
        forecast_daily_costs(df, periods=7)


def test_forecast_daily_costs_returns_requested_periods_beyond_history():
    df = _synthetic_daily_df(days=40, base=40.0)
    history = daily_total_costs(df)
    last_historical_date = history["ds"].max()

    forecast = forecast_daily_costs(df, periods=7)

    assert len(forecast) == 7
    expected_dates = [last_historical_date + timedelta(days=i) for i in range(1, 8)]
    assert [point.usage_date for point in forecast] == expected_dates
    for point in forecast:
        assert point.forecast_low <= point.forecast_cost <= point.forecast_high
        assert point.forecast_cost >= 0
        assert point.forecast_low >= 0


def test_forecast_daily_costs_defaults_periods_to_settings_horizon():
    df = _synthetic_daily_df(days=30, base=40.0)
    settings = Settings(forecast_horizon_days=5)

    forecast = forecast_daily_costs(df, settings=settings)

    assert len(forecast) == 5


def test_forecast_daily_costs_tracks_upward_trend():
    df = _synthetic_daily_df(days=60, base=40.0, trend_per_day=2.0)

    forecast = forecast_daily_costs(df, periods=7)

    # Last historical day's total is ~40 + 2*59 = 158; a forecast that
    # picked up the trend should continue well above the series' early
    # values (day 0 total ~= 40), not flatten or reverse it.
    assert forecast[-1].forecast_cost > 120.0


def test_calculate_budget_drift_flags_over_budget():
    forecast = _forecast_points(days=10)  # 10 * 100 = 1000
    settings = Settings(monthly_budget_usd=800.0)

    drift = calculate_budget_drift(forecast, settings=settings)

    assert drift.forecast_total_usd == pytest.approx(1000.0)
    assert drift.budget_usd == pytest.approx(800.0)
    assert drift.drift_usd == pytest.approx(200.0)
    assert drift.drift_pct == pytest.approx(25.0)
    assert drift.over_budget is True
    assert drift.period_start == date(2026, 3, 1)
    assert drift.period_end == date(2026, 3, 10)


def test_calculate_budget_drift_flags_under_budget():
    forecast = _forecast_points(days=10)  # 10 * 100 = 1000
    settings = Settings(monthly_budget_usd=2000.0)

    drift = calculate_budget_drift(forecast, settings=settings)

    assert drift.drift_usd == pytest.approx(-1000.0)
    assert drift.drift_pct == pytest.approx(-50.0)
    assert drift.over_budget is False


def test_calculate_budget_drift_rejects_empty_forecast():
    with pytest.raises(ValueError):
        calculate_budget_drift([], settings=Settings())
