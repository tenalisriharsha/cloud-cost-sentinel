from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from cloud_cost_sentinel.dashboard.app import (
    build_daily_trend_frame,
    build_forecast_figure,
    build_trend_figure,
)
from cloud_cost_sentinel.models import Anomaly, ForecastPoint

APP_PATH = Path(__file__).resolve().parent.parent / "src" / "cloud_cost_sentinel" / "dashboard" / "app.py"


def _cost_df() -> pd.DataFrame:
    start = date(2026, 1, 1)
    rows = []
    for i in range(5):
        rows.append(
            {
                "usage_account_id": "111122223333",
                "service": "AmazonEC2",
                "usage_type": "Test",
                "region": "us-east-1",
                "usage_date": start + timedelta(days=i),
                "unblended_cost": 10.0 if i != 2 else 500.0,
                "currency": "USD",
            }
        )
    return pd.DataFrame(rows)


def _anomaly() -> Anomaly:
    return Anomaly(
        service="AmazonEC2",
        usage_date=date(2026, 1, 3),
        actual_cost=500.0,
        expected_cost=10.0,
        score=12.0,
        method="rolling_iqr",
    )


def _forecast() -> list[ForecastPoint]:
    start = date(2026, 2, 1)
    return [
        ForecastPoint(
            usage_date=start + timedelta(days=i),
            forecast_cost=100.0 + i,
            forecast_low=90.0 + i,
            forecast_high=110.0 + i,
        )
        for i in range(5)
    ]


def test_build_daily_trend_frame_flags_only_the_anomaly_day():
    trend = build_daily_trend_frame(_cost_df(), [_anomaly()])

    assert len(trend) == 5
    flagged = trend[trend["is_anomaly"]]
    assert len(flagged) == 1
    assert flagged.iloc[0]["usage_date"] == date(2026, 1, 3)
    assert flagged.iloc[0]["total_cost"] == pytest.approx(500.0)


def test_build_daily_trend_frame_flags_nothing_without_anomalies():
    trend = build_daily_trend_frame(_cost_df(), [])
    assert not trend["is_anomaly"].any()


def test_build_trend_figure_has_a_line_and_an_anomaly_marker_trace():
    trend = build_daily_trend_frame(_cost_df(), [_anomaly()])
    fig = build_trend_figure(trend)

    trace_names = {trace.name for trace in fig.data}
    assert "Daily total" in trace_names
    assert "Anomaly" in trace_names


def test_build_trend_figure_skips_anomaly_trace_when_none_flagged():
    trend = build_daily_trend_frame(_cost_df(), [])
    fig = build_trend_figure(trend)

    trace_names = {trace.name for trace in fig.data}
    assert "Daily total" in trace_names
    assert "Anomaly" not in trace_names


def test_build_forecast_figure_includes_actual_and_forecast_series():
    fig = build_forecast_figure(_cost_df(), _forecast(), budget_usd=1000.0)

    trace_names = {trace.name for trace in fig.data}
    assert "Actual" in trace_names
    assert "Forecast" in trace_names
    assert "Forecast range" in trace_names


def test_build_forecast_figure_draws_a_budget_reference_line():
    fig = build_forecast_figure(_cost_df(), _forecast(), budget_usd=1000.0)
    assert any(shape.y0 == 1000.0 for shape in fig.layout.shapes)


@pytest.mark.slow
def test_dashboard_app_runs_end_to_end_without_error():
    streamlit_testing = pytest.importorskip("streamlit.testing.v1")
    at = streamlit_testing.AppTest.from_file(str(APP_PATH), default_timeout=60)
    at.run()

    assert not at.exception
    assert at.title[0].value == "Cloud Cost Sentinel"
    assert len(at.metric) == 3
