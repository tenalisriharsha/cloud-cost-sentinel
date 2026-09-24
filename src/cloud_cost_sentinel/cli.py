"""CLI entrypoint chaining ingestion -> analysis -> forecasting -> alerting.

Anomaly detection and forecasting read from two different fixtures by
default: the 10-day ``sample_cur.csv`` has a deliberate anomaly but is too
short to forecast from (see ``forecasting.prophet_forecast.MIN_HISTORY_DAYS``),
while the 45-day ``sample_cur_forecast.csv`` exists purely to give
``forecast_daily_costs`` enough history to produce a meaningful demo forecast.
A real deployment would point ``--anomaly-data``/``--forecast-data`` at the
same, larger CUR export.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from cloud_cost_sentinel.alerting.slack import (
    AlertThrottle,
    format_anomaly_alert,
    format_budget_drift_alert,
    send_alert,
)
from cloud_cost_sentinel.analysis.anomaly import detect_anomalies_rolling_iqr
from cloud_cost_sentinel.config import Settings, get_settings
from cloud_cost_sentinel.forecasting.prophet_forecast import calculate_budget_drift, forecast_daily_costs
from cloud_cost_sentinel.ingestion.cur_loader import load_cost_dataframe
from cloud_cost_sentinel.models import Anomaly, BudgetAlert, BudgetDrift, ForecastPoint

if TYPE_CHECKING:
    from slack_sdk.webhook import WebhookClient

DEFAULT_ANOMALY_DATA_PATH = Path("data/sample/sample_cur.csv")
DEFAULT_FORECAST_DATA_PATH = Path("data/sample/sample_cur_forecast.csv")


@dataclass
class PipelineResult:
    """Everything one end-to-end pipeline run produced, for the CLI to report."""

    anomalies: list[Anomaly]
    forecast: list[ForecastPoint]
    drift: BudgetDrift
    alerts_sent: list[BudgetAlert] = field(default_factory=list)
    alerts_skipped: list[BudgetAlert] = field(default_factory=list)


def run_pipeline(
    *,
    anomaly_data_path: str | Path = DEFAULT_ANOMALY_DATA_PATH,
    forecast_data_path: str | Path = DEFAULT_FORECAST_DATA_PATH,
    settings: Settings | None = None,
    throttle: AlertThrottle | None = None,
    webhook_client: "WebhookClient | None" = None,
) -> PipelineResult:
    """Run ingestion -> analysis -> forecasting -> alerting end-to-end.

    Anomalies use :func:`detect_anomalies_rolling_iqr` rather than the
    z-score detector, since the z-score detector's own masking effect means
    it misses the sample fixture's deliberate spike at the default
    threshold (see ``analysis/anomaly.py``). A budget-drift alert is only
    sent when the forecast is actually over budget.
    """
    resolved_settings = settings or get_settings()
    resolved_throttle = throttle or AlertThrottle()

    anomaly_df = load_cost_dataframe(anomaly_data_path)
    anomalies = detect_anomalies_rolling_iqr(anomaly_df)

    forecast_df = load_cost_dataframe(forecast_data_path)
    forecast = forecast_daily_costs(forecast_df, settings=resolved_settings)
    drift = calculate_budget_drift(forecast, settings=resolved_settings)

    alerts_sent: list[BudgetAlert] = []
    alerts_skipped: list[BudgetAlert] = []

    def _dispatch(alert: BudgetAlert) -> None:
        sent = send_alert(
            alert,
            throttle=resolved_throttle,
            settings=resolved_settings,
            webhook_client=webhook_client,
        )
        (alerts_sent if sent else alerts_skipped).append(alert)

    for anomaly in anomalies:
        _dispatch(format_anomaly_alert(anomaly))

    if drift.over_budget:
        _dispatch(format_budget_drift_alert(drift))

    return PipelineResult(
        anomalies=anomalies,
        forecast=forecast,
        drift=drift,
        alerts_sent=alerts_sent,
        alerts_skipped=alerts_skipped,
    )


def format_report(result: PipelineResult) -> str:
    """Render a ``PipelineResult`` as a human-readable text report."""
    lines = ["Cloud Cost Sentinel — pipeline run", "=" * 34, ""]

    lines.append(f"Anomalies detected: {len(result.anomalies)}")
    for anomaly in result.anomalies:
        lines.append(
            f"  - {anomaly.usage_date} {anomaly.service}: actual "
            f"${anomaly.actual_cost:,.2f} vs expected ${anomaly.expected_cost:,.2f} "
            f"({anomaly.method}, score={anomaly.score:.2f})"
        )

    drift = result.drift
    lines.append("")
    lines.append(f"Forecast: {len(result.forecast)} day(s), {drift.period_start} to {drift.period_end}")
    lines.append(f"  Forecast total: ${drift.forecast_total_usd:,.2f}")
    lines.append(f"  Budget:         ${drift.budget_usd:,.2f}")
    status = "OVER budget" if drift.over_budget else "within budget"
    lines.append(f"  Drift:          {drift.drift_pct:+.1f}% (${drift.drift_usd:,.2f}) — {status}")

    lines.append("")
    lines.append(f"Alerts sent: {len(result.alerts_sent)}")
    lines.append(f"Alerts skipped (throttled or no webhook configured): {len(result.alerts_skipped)}")

    return "\n".join(lines)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ccs",
        description="Run the cloud-cost-sentinel pipeline end-to-end: ingest, detect, forecast, alert.",
    )
    parser.add_argument(
        "--anomaly-data",
        type=Path,
        default=DEFAULT_ANOMALY_DATA_PATH,
        help="CUR CSV used for anomaly detection (default: %(default)s)",
    )
    parser.add_argument(
        "--forecast-data",
        type=Path,
        default=DEFAULT_FORECAST_DATA_PATH,
        help="CUR CSV used for forecasting; needs at least 14 days of history (default: %(default)s)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    result = run_pipeline(anomaly_data_path=args.anomaly_data, forecast_data_path=args.forecast_data)
    print(format_report(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
