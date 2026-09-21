from datetime import date, timedelta

import pandas as pd
import pytest

from cloud_cost_sentinel.analysis.anomaly import (
    daily_service_costs,
    detect_anomalies_rolling_iqr,
    detect_anomalies_zscore,
)
from cloud_cost_sentinel.ingestion.cur_loader import load_cost_dataframe

SAMPLE_CUR_PATH = "data/sample/sample_cur.csv"


@pytest.fixture
def sample_df() -> pd.DataFrame:
    return load_cost_dataframe(SAMPLE_CUR_PATH)


def _flat_series_df(
    service: str, cost: float, days: int, spike_day: int | None = None, spike_cost: float = 0.0, jitter: float = 0.0
) -> pd.DataFrame:
    """Build a synthetic one-service cost series, optionally with one spike day.

    ``jitter`` adds a small deterministic wobble to non-spike days so a
    rolling baseline window has nonzero IQR (a perfectly flat baseline is
    unrealistic and would otherwise make every bound-based check degenerate).
    """
    rows = []
    start = date(2026, 1, 1)
    for i in range(days):
        day_cost = spike_cost if i == spike_day else cost + jitter * (i % 3 - 1)
        rows.append(
            {
                "usage_account_id": "111122223333",
                "service": service,
                "usage_type": "Test",
                "region": "us-east-1",
                "usage_date": start + timedelta(days=i),
                "unblended_cost": day_cost,
                "currency": "USD",
            }
        )
    return pd.DataFrame(rows)


def test_daily_service_costs_aggregates_multiple_rows_per_day():
    df = pd.DataFrame(
        [
            {"service": "AmazonEC2", "usage_date": date(2026, 1, 1), "unblended_cost": 10.0},
            {"service": "AmazonEC2", "usage_date": date(2026, 1, 1), "unblended_cost": 5.0},
            {"service": "AmazonEC2", "usage_date": date(2026, 1, 2), "unblended_cost": 7.0},
        ]
    )
    daily = daily_service_costs(df)
    assert len(daily) == 2
    day_one = daily[daily["usage_date"] == date(2026, 1, 1)].iloc[0]
    assert day_one["unblended_cost"] == pytest.approx(15.0)


def test_daily_service_costs_handles_empty_dataframe():
    df = pd.DataFrame(columns=["service", "usage_date", "unblended_cost"])
    daily = daily_service_costs(df)
    assert daily.empty


def test_zscore_flags_clear_outlier_in_synthetic_series():
    df = _flat_series_df("AmazonEC2", cost=10.0, days=20, spike_day=10, spike_cost=500.0)
    anomalies = detect_anomalies_zscore(df, threshold=3.0)
    assert len(anomalies) == 1
    anomaly = anomalies[0]
    assert anomaly.service == "AmazonEC2"
    assert anomaly.usage_date == date(2026, 1, 11)
    assert anomaly.actual_cost == pytest.approx(500.0)
    assert anomaly.method == "zscore"
    assert anomaly.score > 3.0


def test_zscore_flags_nothing_for_constant_cost_series():
    df = _flat_series_df("AmazonS3", cost=8.5, days=10)
    assert detect_anomalies_zscore(df, threshold=3.0) == []


def test_zscore_respects_custom_threshold():
    df = _flat_series_df("AmazonEC2", cost=10.0, days=20, spike_day=10, spike_cost=30.0)
    assert detect_anomalies_zscore(df, threshold=10.0) == []
    assert len(detect_anomalies_zscore(df, threshold=1.0)) == 1


def test_zscore_uses_settings_default_threshold_when_not_given(monkeypatch):
    monkeypatch.setenv("CCS_ANOMALY_Z_THRESHOLD", "1.0")
    df = _flat_series_df("AmazonEC2", cost=10.0, days=20, spike_day=10, spike_cost=30.0)
    assert len(detect_anomalies_zscore(df)) == 1


def test_zscore_on_sample_fixture_does_not_flag_the_spike_at_default_threshold(sample_df):
    """A single large outlier among 9 uniform points inflates its own
    standard deviation enough that its z-score tops out near (but under)
    the classic threshold of 3.0 -- this is the well-known "masking"
    limitation of z-score outlier detection on small samples, and part of
    why a second, rolling-window method exists alongside it.
    """
    anomalies = detect_anomalies_zscore(sample_df, threshold=3.0)
    assert anomalies == []

    anomalies = detect_anomalies_zscore(sample_df, threshold=2.5)
    assert any(a.service == "AmazonEC2" and a.usage_date == date(2026, 8, 6) for a in anomalies)


def test_rolling_iqr_flags_clear_outlier_in_synthetic_series():
    df = _flat_series_df("AmazonEC2", cost=10.0, days=20, spike_day=10, spike_cost=500.0, jitter=0.2)
    anomalies = detect_anomalies_rolling_iqr(df, window=5, multiplier=3.0)
    assert len(anomalies) == 1
    anomaly = anomalies[0]
    assert anomaly.service == "AmazonEC2"
    assert anomaly.usage_date == date(2026, 1, 11)
    assert anomaly.method == "rolling_iqr"


def test_rolling_iqr_does_not_flag_the_seed_window():
    df = _flat_series_df("AmazonEC2", cost=10.0, days=5, spike_day=0, spike_cost=500.0)
    assert detect_anomalies_rolling_iqr(df, window=5) == []


def test_rolling_iqr_flags_nothing_for_constant_cost_series():
    df = _flat_series_df("AmazonS3", cost=8.5, days=15)
    assert detect_anomalies_rolling_iqr(df, window=5) == []


def test_rolling_iqr_on_sample_fixture_catches_the_deliberate_ec2_spike(sample_df):
    anomalies = detect_anomalies_rolling_iqr(sample_df, window=5)
    assert len(anomalies) == 1
    anomaly = anomalies[0]
    assert anomaly.service == "AmazonEC2"
    assert anomaly.usage_date == date(2026, 8, 6)
    assert anomaly.actual_cost == pytest.approx(187.44)


def test_rolling_iqr_default_multiplier_is_less_sensitive_than_boxplot_fence(sample_df):
    lenient = detect_anomalies_rolling_iqr(sample_df, window=5, multiplier=1.5)
    strict = detect_anomalies_rolling_iqr(sample_df, window=5, multiplier=3.0)
    assert len(strict) <= len(lenient)
