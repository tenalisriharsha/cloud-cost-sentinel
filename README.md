# cloud-cost-sentinel

A FinOps sentinel for AWS spend. It ingests AWS Cost and Usage Report (CUR)
data, detects spending anomalies with statistical methods, forecasts next
month's spend with Prophet, and sends budget-drift alerts to Slack — with a
dashboard to tie it all together.

## Project Status

This project completed its planned nightly build (Phases 1-5). See
[PROGRESS.md](PROGRESS.md) for the architecture and phased build history, and
[DAILY_REPORT.md](DAILY_REPORT.md) for a summary of what was built each
night, test results, and known limitations.

## Features

- **Ingestion** — load AWS CUR-format billing data from a local CSV or an S3
  bucket (works against real AWS S3 or a LocalStack endpoint).
- **Anomaly detection** — flag unusual daily/service spend with two
  statistical methods: a whole-series z-score and a rolling-window IQR
  detector, so their output can be compared.
- **Forecasting** — project daily spend forward with Prophet, and compare
  the forecast total against the configured monthly budget.
- **Alerting** — format anomaly and budget-drift alerts and post them to
  Slack, with in-memory throttling so the same condition doesn't re-page on
  every run.
- **CLI** — a single `ccs` command chains ingestion, anomaly detection,
  forecasting, and alerting into one end-to-end run.
- **Dashboard** — a Streamlit app visualizing daily spend trends with
  anomalies marked, and a forecast-vs-budget chart, built on the exact same
  functions as the CLI and test suite.

## Getting started

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

`pip install -e ".[dev]"` also pulls in `boto3` + `moto` (via the `aws`
extra), `prophet` (via the `forecast` extra), `slack-sdk` (via the `alerts`
extra), and `streamlit` + `plotly` (via the `dashboard` extra), so the S3
ingestion path, the forecasting path, the Slack alerting path, and the
dashboard are all testable without a real AWS account, LocalStack, a real
Slack workspace, or a browser.

## Running it

```bash
ccs                       # runs the full pipeline against the sample CUR fixtures
streamlit run src/cloud_cost_sentinel/dashboard/app.py   # interactive dashboard
```

`ccs` prints a text report: anomalies found, the forecast vs. budget, and how
many alerts were sent vs. skipped (no Slack webhook is configured by
default, so alerts are formatted and throttled but not actually posted —
set `CCS_SLACK_WEBHOOK_URL` to send for real). Pass `--anomaly-data` /
`--forecast-data` to point either step at a different CUR CSV; see
`ccs --help`.

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
The 10-day `sample_cur.csv` fixture is intentionally too short for this (it's
tuned for the anomaly-detection walkthrough above instead); a separate
45-day `data/sample/sample_cur_forecast.csv` fixture exists purely to give
`forecast_daily_costs` enough history for a meaningful demo forecast, and is
what the CLI and dashboard forecast against by default. Forecast unit tests
build their own longer synthetic series inline instead of using either
fixture (see `tests/test_forecast.py`).

### Alerting

```python
from cloud_cost_sentinel.alerting import (
    AlertThrottle,
    format_anomaly_alert,
    format_budget_drift_alert,
    send_alert,
)

throttle = AlertThrottle()  # in-memory; create once and reuse across runs

for anomaly in rolling_anomalies:
    alert = format_anomaly_alert(anomaly)
    send_alert(alert, throttle=throttle)  # reads CCS_SLACK_WEBHOOK_URL

if drift.over_budget:
    send_alert(format_budget_drift_alert(drift), throttle=throttle)
```

`format_anomaly_alert` and `format_budget_drift_alert` turn an `Anomaly` or
`BudgetDrift` into a `BudgetAlert` — a formatted message plus a `dedup_key`
(`service`/`usage_date`/`method` for anomalies, the forecast period for
budget drift). `send_alert` posts that message to the Slack webhook
configured via `CCS_SLACK_WEBHOOK_URL`, returning `False` without making a
network call if no webhook is configured or if an `AlertThrottle` has
already seen that `dedup_key` — so the same condition doesn't re-page on
every run. There's no persistence layer yet, so a throttle only lives as
long as the process holding it. `slack_sdk` is imported lazily inside
`send_alert`, so formatting and throttling work without the `alerts` extra
installed; pass a `webhook_client` directly to `send_alert` to test against
a fake client instead of a real Slack workspace (see `tests/test_slack.py`).

### CLI

```python
from cloud_cost_sentinel.cli import run_pipeline, format_report

result = run_pipeline()  # anomaly_data_path/forecast_data_path default to the sample fixtures
print(format_report(result))
```

`run_pipeline` is what the `ccs` command wraps: it loads the anomaly-data
CUR CSV and runs `detect_anomalies_rolling_iqr` on it (rather than the
z-score detector, since z-score's own masking effect means it misses the
sample fixture's deliberate spike at the default threshold), loads the
forecast-data CUR CSV and runs `forecast_daily_costs` + `calculate_budget_drift`
on it, then formats and dispatches a `BudgetAlert` for every anomaly and
(only if `drift.over_budget`) one for the budget drift — accepting the same
`throttle` and `webhook_client` injection points as `send_alert`, so it's
tested with a fake client (see `tests/test_cli.py`) exactly like
`alerting/slack.py` is.

### Dashboard

```bash
streamlit run src/cloud_cost_sentinel/dashboard/app.py
```

The dashboard calls `run_pipeline()` for its numbers and reloads the same
two CUR fixtures to build two charts: a daily-spend line with anomaly days
marked, and a forecast line (with its uncertainty band) against a flat
budget reference line, plus the anomalies table and the sent/skipped alert
list. The chart-building functions (`build_daily_trend_frame`,
`build_trend_figure`, `build_forecast_figure`) are plain pandas/plotly and
importable without Streamlit itself, so they're unit-tested directly;
`tests/test_dashboard.py` also drives the whole app through
`streamlit.testing.v1.AppTest` as an end-to-end smoke test.

## Project layout

```
src/cloud_cost_sentinel/
  config.py             # environment-driven settings
  models.py              # core domain models (CostRecord, Anomaly, ForecastPoint, BudgetDrift, ...)
  ingestion/              # CUR CSV / S3 (LocalStack-compatible) loaders
  analysis/                # anomaly detection (z-score, rolling IQR)
  forecasting/              # Prophet-based daily spend forecast + budget drift
  alerting/                 # Slack alert formatting, throttling, and sending
  cli.py                    # `ccs` entrypoint chaining ingestion -> analysis -> forecasting -> alerting
  dashboard/                # Streamlit app visualizing the same pipeline
data/sample/               # sample CUR data used by tests and local runs
tests/                      # pytest suite
.github/workflows/         # CI: lint (ruff) + test (pytest) on push/PR
```

## License

MIT — see [LICENSE](LICENSE).
