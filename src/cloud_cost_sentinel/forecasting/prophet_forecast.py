"""Prophet-based forecasting of total daily AWS spend, plus budget drift.

Ingestion and analysis both key on the ``(service, usage_date)`` grain.
Forecasting instead needs one point per calendar day, summed across every
service, in Prophet's ``ds``/``y`` input shape — the goal here is to project
*total* spend against a single monthly budget, not any one service's trend.
"""

from __future__ import annotations

import logging

import pandas as pd

from cloud_cost_sentinel.config import Settings, get_settings
from cloud_cost_sentinel.models import BudgetDrift, ForecastPoint

MIN_HISTORY_DAYS = 14
"""Prophet will fit on fewer days, but the resulting forecast is too noisy
to act on, so :func:`forecast_daily_costs` refuses instead of returning a
misleading number."""


def daily_total_costs(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate raw cost records into one total-cost row per calendar day.

    Returns a ``ds``/``y`` frame — the column names Prophet requires.
    """
    if df.empty:
        return pd.DataFrame(columns=["ds", "y"])
    daily = df.groupby("usage_date", as_index=False)["unblended_cost"].sum()
    return (
        daily.rename(columns={"usage_date": "ds", "unblended_cost": "y"})
        .sort_values("ds")
        .reset_index(drop=True)
    )


def forecast_daily_costs(
    df: pd.DataFrame,
    *,
    periods: int | None = None,
    settings: Settings | None = None,
) -> list[ForecastPoint]:
    """Forecast total daily spend for ``periods`` days beyond the input history.

    ``periods`` defaults to ``Settings.forecast_horizon_days``. Raises
    ``ValueError`` if there is less than :data:`MIN_HISTORY_DAYS` of history.
    """
    resolved_settings = settings or get_settings()
    resolved_periods = periods if periods is not None else resolved_settings.forecast_horizon_days

    history = daily_total_costs(df)
    if len(history) < MIN_HISTORY_DAYS:
        raise ValueError(
            f"Need at least {MIN_HISTORY_DAYS} days of cost history to forecast, got {len(history)}."
        )

    # Imported lazily: prophet (and its cmdstanpy/matplotlib deps) is a heavy
    # optional dependency (the `forecast` extra), not needed by ingestion,
    # analysis, or anything that doesn't actually call this function.
    from prophet import Prophet

    logging.getLogger("cmdstanpy").setLevel(logging.WARNING)
    logging.getLogger("prophet").setLevel(logging.WARNING)

    model = Prophet(interval_width=0.8)
    model.fit(history)

    future = model.make_future_dataframe(periods=resolved_periods)
    forecast = model.predict(future)
    last_historical_ts = pd.Timestamp(history["ds"].max())
    future_only = forecast[forecast["ds"] > last_historical_ts]

    return [
        ForecastPoint(
            usage_date=row.ds.date(),
            # Prophet's linear trend can extrapolate below zero; spend can't.
            forecast_cost=max(0.0, row.yhat),
            forecast_low=max(0.0, row.yhat_lower),
            forecast_high=max(0.0, row.yhat_upper),
        )
        for row in future_only.itertuples()
    ]


def calculate_budget_drift(
    forecast: list[ForecastPoint],
    *,
    settings: Settings | None = None,
) -> BudgetDrift:
    """Compare a forecast's total spend against ``Settings.monthly_budget_usd``."""
    if not forecast:
        raise ValueError("Cannot calculate budget drift from an empty forecast.")

    budget = (settings or get_settings()).monthly_budget_usd
    total = sum(point.forecast_cost for point in forecast)
    drift = total - budget

    return BudgetDrift(
        period_start=min(point.usage_date for point in forecast),
        period_end=max(point.usage_date for point in forecast),
        forecast_total_usd=total,
        budget_usd=budget,
        drift_usd=drift,
        drift_pct=(drift / budget) * 100,
        over_budget=total > budget,
    )
