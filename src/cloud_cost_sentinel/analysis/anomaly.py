"""Statistical anomaly detection over daily, per-service cost aggregates.

Two independent detectors are provided so their output can be compared:

- :func:`detect_anomalies_zscore` — flags days whose cost is an outlier
  against that service's *entire* history (a static baseline).
- :func:`detect_anomalies_rolling_iqr` — flags days whose cost falls outside
  the interquartile range of that service's *preceding* window of days (a
  trend-relative baseline), so it can catch a spike even when the service's
  long-run average has not been established yet.
"""

from __future__ import annotations

import pandas as pd

from cloud_cost_sentinel.config import Settings, get_settings
from cloud_cost_sentinel.models import Anomaly


def daily_service_costs(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate raw cost records into total cost per (service, usage_date)."""
    if df.empty:
        return pd.DataFrame(columns=["service", "usage_date", "unblended_cost"])
    return (
        df.groupby(["service", "usage_date"], as_index=False)["unblended_cost"]
        .sum()
        .sort_values(["service", "usage_date"])
        .reset_index(drop=True)
    )


def detect_anomalies_zscore(
    df: pd.DataFrame,
    *,
    threshold: float | None = None,
    settings: Settings | None = None,
) -> list[Anomaly]:
    """Flag days where a service's cost is more than ``threshold`` standard
    deviations from that service's own mean daily cost.
    """
    resolved_threshold = threshold if threshold is not None else (settings or get_settings()).anomaly_z_threshold
    daily = daily_service_costs(df)
    anomalies: list[Anomaly] = []

    for service, group in daily.groupby("service"):
        costs = group["unblended_cost"]
        mean = costs.mean()
        std = costs.std(ddof=0)
        if not std:
            continue
        for _, row in group.iterrows():
            score = (row["unblended_cost"] - mean) / std
            if abs(score) >= resolved_threshold:
                anomalies.append(
                    Anomaly(
                        service=service,
                        usage_date=row["usage_date"],
                        actual_cost=row["unblended_cost"],
                        expected_cost=mean,
                        score=score,
                        method="zscore",
                    )
                )
    return anomalies


def detect_anomalies_rolling_iqr(
    df: pd.DataFrame,
    *,
    window: int = 5,
    multiplier: float = 3.0,
) -> list[Anomaly]:
    """Flag days whose cost falls outside ``multiplier`` IQRs of the
    preceding ``window`` days for that service.

    The first ``window`` observations of each service are used purely to
    seed the baseline and are never themselves flagged. ``multiplier``
    defaults to Tukey's "far out" fence (3.0) rather than the usual
    boxplot fence (1.5), since 1.5 flags routine day-to-day drift as an
    anomaly on services with very low cost variance.
    """
    daily = daily_service_costs(df)
    anomalies: list[Anomaly] = []

    for service, group in daily.groupby("service"):
        group = group.reset_index(drop=True)
        costs = group["unblended_cost"]
        for i in range(window, len(group)):
            baseline = costs.iloc[i - window : i]
            q1 = baseline.quantile(0.25)
            q3 = baseline.quantile(0.75)
            iqr = q3 - q1
            if not iqr:
                continue
            lower = q1 - multiplier * iqr
            upper = q3 + multiplier * iqr
            cost = costs.iloc[i]
            if cost < lower or cost > upper:
                median = baseline.median()
                anomalies.append(
                    Anomaly(
                        service=service,
                        usage_date=group["usage_date"].iloc[i],
                        actual_cost=cost,
                        expected_cost=median,
                        score=(cost - median) / iqr,
                        method="rolling_iqr",
                    )
                )
    return anomalies
