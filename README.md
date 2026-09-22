# cloud-cost-sentinel

A FinOps sentinel for AWS spend. It ingests AWS Cost and Usage Report (CUR)
data, detects spending anomalies with statistical methods, forecasts next
month's spend with Prophet, and sends budget-drift alerts to Slack — with a
dashboard to tie it all together.

## Project Status

This project is under active, public, nightly development. See
[PROGRESS.md](PROGRESS.md) for the architecture, the phased build plan, and
exactly what's done vs. what's next.

## Features

- **Ingestion** — load AWS CUR-format billing data from a local CSV or an S3
  bucket (works against real AWS S3 or a LocalStack endpoint).
- **Anomaly detection** — flag unusual daily/service spend with two
  statistical methods: a whole-series z-score and a rolling-window IQR
  detector, so their output can be compared.
- **Forecasting** — project daily spend forward with Prophet, and compare
  the forecast total against the configured monthly budget.
- **Alerting** — post budget-drift and anomaly alerts to Slack. *(planned)*
- **Dashboard** — visualize cost trends, anomalies, and forecasts. *(planned)*

## Getting started

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

`pip install -e ".[dev]"` also pulls in `boto3` + `moto` (via the `aws`
extra) and `prophet` (via the `forecast` extra), so the S3 ingestion path
and the forecasting path are both testable without a real AWS account,
LocalStack, or any extra setup.

## Usage

```python
from cloud_cost_sentinel.ingestion.cur_loader import load_cost_dataframe
from cloud_cost_sentinel.analysis.anomaly import (
    detect_anomalies_zscore,
    detect_anomalies_rolling_iqr,
)

df = load_cost_dataframe("data/sample/sample_cur.csv")

# Flags a day where a service's cost is an outlier vs. its own history.
zscore_anomalies = detect_anomalies_zscore(df, threshold=2.5)

# Flags a day where cost breaks out of the preceding window's IQR range.
rolling_anomalies = detect_anomalies_rolling_iqr(df, window=5)
```

Or load the same CUR format from S3 / LocalStack:

```python
from cloud_cost_sentinel.ingestion.s3_loader import load_cost_dataframe_from_s3

df = load_cost_dataframe_from_s3(
    bucket="my-cur-bucket",
    key="reports/cur.csv",
    endpoint_url="http://localhost:4566",  # omit for real AWS S3
)
```

### A note on the two anomaly detectors

The z-score detector compares each day against that service's *entire*
history. On a small sample with a single large outlier, that outlier
inflates its own standard deviation enough to cap its z-score near (but
under) the classic threshold of 3.0 — a known "masking" limitation of
z-score outlier detection on small samples. The rolling-IQR detector
compares each day only against the *preceding* window, so it isn't affected
by masking and reliably catches the same spike. Both are kept so their
output can be compared; see `tests/test_anomaly.py` for a worked example
against the sample CUR fixture's deliberate EC2 spike.

### Forecasting and budget drift

```python
from cloud_cost_sentinel.forecasting.prophet_forecast import (
    calculate_budget_drift,
    forecast_daily_costs,
)

# One ForecastPoint per day, summed across every service, `periods` days
# beyond the input history's last day (defaults to Settings.forecast_horizon_days).
forecast = forecast_daily_costs(df, periods=30)

# Compares the forecast's total against Settings.monthly_budget_usd.
drift = calculate_budget_drift(forecast)
print(drift.over_budget, drift.drift_usd, drift.drift_pct)
```

`forecast_daily_costs` fits a fresh Prophet model on total daily spend
(`ds`/`y` shaped, summed across services) and requires at least 14 days of
history — Prophet will technically fit on less, but the forecast isn't
meaningful enough to act on, so the function raises `ValueError` instead.
The 10-day sample CUR fixture is intentionally too short for this; forecast
tests build longer synthetic series (see `tests/test_forecast.py`).

## Project layout

```
src/cloud_cost_sentinel/
  config.py             # environment-driven settings
  models.py              # core domain models (CostRecord, Anomaly, ForecastPoint, BudgetDrift, ...)
  ingestion/              # CUR CSV / S3 (LocalStack-compatible) loaders
  analysis/                # anomaly detection (z-score, rolling IQR)
  forecasting/              # Prophet-based daily spend forecast + budget drift
data/sample/               # sample CUR data used by tests and local runs
tests/                      # pytest suite
```

## License

MIT — see [LICENSE](LICENSE).
