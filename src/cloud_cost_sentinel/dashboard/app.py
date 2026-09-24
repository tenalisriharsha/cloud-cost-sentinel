"""Streamlit dashboard: daily spend trend with anomalies, and forecast vs. budget.

Run with::

    streamlit run src/cloud_cost_sentinel/dashboard/app.py

Every number shown here comes from the exact same functions the CLI and test
suite use (`cloud_cost_sentinel.cli.run_pipeline`) -- this module only adds
presentation on top, split into two layers: pure pandas/plotly builders
(importable and unit-testable without Streamlit itself) and a thin
`render()` that calls `st.*`.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from cloud_cost_sentinel.cli import DEFAULT_ANOMALY_DATA_PATH, DEFAULT_FORECAST_DATA_PATH, run_pipeline
from cloud_cost_sentinel.forecasting.prophet_forecast import daily_total_costs
from cloud_cost_sentinel.ingestion.cur_loader import load_cost_dataframe
from cloud_cost_sentinel.models import Anomaly, ForecastPoint

# Colors are fixed categorical/status slots from the project's palette, not
# picked ad hoc: slot 1 (blue) for actuals, slot 2 (orange) for forecast, the
# "critical" status color for anomalies, and muted axis gray for the flat
# budget reference line.
COLOR_ACTUAL = "#2a78d6"
COLOR_FORECAST = "#eb6834"
COLOR_ANOMALY = "#d03b3b"
COLOR_BUDGET_LINE = "#898781"


def build_daily_trend_frame(cost_df: pd.DataFrame, anomalies: list[Anomaly]) -> pd.DataFrame:
    """One row per calendar day of total spend, flagged if any service had an
    anomaly that day.
    """
    daily = daily_total_costs(cost_df).rename(columns={"ds": "usage_date", "y": "total_cost"})
    anomaly_dates = {a.usage_date for a in anomalies}
    daily["is_anomaly"] = daily["usage_date"].apply(lambda d: pd.Timestamp(d).date() in anomaly_dates)
    return daily


def build_trend_figure(trend: pd.DataFrame) -> go.Figure:
    """Total daily spend as a single-axis line, with anomaly days marked."""
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=trend["usage_date"],
            y=trend["total_cost"],
            mode="lines",
            name="Daily total",
            line=dict(color=COLOR_ACTUAL, width=2),
        )
    )
    flagged = trend[trend["is_anomaly"]]
    if not flagged.empty:
        fig.add_trace(
            go.Scatter(
                x=flagged["usage_date"],
                y=flagged["total_cost"],
                mode="markers",
                name="Anomaly",
                marker=dict(color=COLOR_ANOMALY, size=10, symbol="diamond"),
            )
        )
    fig.update_layout(yaxis_title="Total daily spend (USD)", margin=dict(t=20, b=20))
    return fig


def build_forecast_figure(history_df: pd.DataFrame, forecast: list[ForecastPoint], budget_usd: float) -> go.Figure:
    """A single cost-axis chart: historical actual spend, the projected
    forecast with its uncertainty band, and the configured monthly budget as
    a flat reference line.
    """
    history = daily_total_costs(history_df)
    forecast_dates = [point.usage_date for point in forecast]
    forecast_mid = [point.forecast_cost for point in forecast]
    forecast_low = [point.forecast_low for point in forecast]
    forecast_high = [point.forecast_high for point in forecast]

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=history["ds"],
            y=history["y"],
            mode="lines",
            name="Actual",
            line=dict(color=COLOR_ACTUAL, width=2),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[*forecast_dates, *forecast_dates[::-1]],
            y=[*forecast_high, *forecast_low[::-1]],
            fill="toself",
            fillcolor="rgba(235, 104, 52, 0.15)",
            line=dict(color="rgba(0,0,0,0)"),
            hoverinfo="skip",
            name="Forecast range",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=forecast_dates,
            y=forecast_mid,
            mode="lines",
            name="Forecast",
            line=dict(color=COLOR_FORECAST, width=2, dash="dash"),
        )
    )
    fig.add_hline(
        y=budget_usd,
        line=dict(color=COLOR_BUDGET_LINE, dash="dot"),
        annotation_text="Monthly budget",
        annotation_position="top left",
    )
    fig.update_layout(
        yaxis_title="Daily spend (USD)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        margin=dict(t=40, b=20),
    )
    return fig


def render() -> None:
    st.set_page_config(page_title="Cloud Cost Sentinel", layout="wide")
    st.title("Cloud Cost Sentinel")
    st.caption("AWS spend: anomalies, forecast, and budget drift.")

    result = run_pipeline()
    drift = result.drift

    col1, col2, col3 = st.columns(3)
    col1.metric("Forecast total", f"${drift.forecast_total_usd:,.0f}")
    col2.metric("Monthly budget", f"${drift.budget_usd:,.0f}")
    col3.metric(
        "Budget drift",
        f"{drift.drift_pct:+.1f}%",
        delta=f"${drift.drift_usd:,.0f}",
        delta_color="inverse",
    )

    st.subheader("Daily spend & anomalies")
    anomaly_df = load_cost_dataframe(DEFAULT_ANOMALY_DATA_PATH)
    trend = build_daily_trend_frame(anomaly_df, result.anomalies)
    st.plotly_chart(build_trend_figure(trend), width="stretch")

    if result.anomalies:
        st.dataframe(pd.DataFrame([a.model_dump() for a in result.anomalies]), width="stretch")
    else:
        st.info("No anomalies detected in the anomaly-detection dataset.")

    st.subheader("Forecast vs. budget")
    forecast_history_df = load_cost_dataframe(DEFAULT_FORECAST_DATA_PATH)
    st.plotly_chart(
        build_forecast_figure(forecast_history_df, result.forecast, drift.budget_usd),
        width="stretch",
    )

    st.subheader("Alerts")
    st.write(
        f"Sent: {len(result.alerts_sent)}  |  "
        f"Skipped (throttled or no webhook configured): {len(result.alerts_skipped)}"
    )
    for alert in [*result.alerts_sent, *result.alerts_skipped]:
        with st.expander(alert.dedup_key):
            st.write(alert.message)


render()
