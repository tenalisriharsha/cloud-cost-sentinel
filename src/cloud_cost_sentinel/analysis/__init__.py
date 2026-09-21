"""Statistical analysis over ingested cost data (anomaly detection, and beyond)."""

from cloud_cost_sentinel.analysis.anomaly import (
    daily_service_costs,
    detect_anomalies_rolling_iqr,
    detect_anomalies_zscore,
)

__all__ = [
    "daily_service_costs",
    "detect_anomalies_rolling_iqr",
    "detect_anomalies_zscore",
]
