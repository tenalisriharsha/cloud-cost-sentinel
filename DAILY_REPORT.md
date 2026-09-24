# Daily Report

A five-night build of `cloud-cost-sentinel`, a FinOps sentinel for AWS
spend: ingest AWS Cost and Usage Report (CUR) data, detect anomalies,
forecast spend, alert on budget drift, and visualize all of it. This report
summarizes what was built each night, the final test results, known
limitations, and ideas for future work. See [PROGRESS.md](PROGRESS.md) for
the detailed architecture and phase-by-phase build log this report draws
from.

## Night by night

**Night 1 — Foundation.** Project scaffold (`pyproject.toml` with core deps
plus `forecast`/`alerts`/`dashboard`/`aws`/`dev` extras, `src/` layout, MIT
license), `Settings` (`pydantic-settings`, `CCS_`-prefixed env vars), the
`CostRecord` domain model, and a CUR-format CSV loader
(`ingestion/cur_loader.py`) against a realistic sample fixture.

**Night 2 — Anomaly detection.** An S3/LocalStack CUR loader
(`ingestion/s3_loader.py`) sharing row-parsing with the CSV loader, and two
independent anomaly detectors over daily/service cost aggregates: a
whole-series z-score detector and a rolling-window IQR detector
(`analysis/anomaly.py`), plus the `Anomaly` model. Tests cover both against
synthetic data and the sample fixture's deliberate EC2 spike, and the S3
loader against a `moto`-mocked bucket.

**Night 3 — Forecasting.** Prophet-based daily spend forecasting
(`forecasting/prophet_forecast.py`: `daily_total_costs`, `forecast_daily_costs`),
the `ForecastPoint` model, and budget-drift calculation
(`calculate_budget_drift`, the `BudgetDrift` model) comparing a forecast
against `Settings.monthly_budget_usd`.

**Night 4 — Alerting.** A Slack webhook client (`alerting/slack.py`,
`slack_sdk` imported lazily so formatting/throttling work without the
`alerts` extra), alert formatting for anomalies and budget drift, in-memory
alert throttling (`AlertThrottle`, keyed on `BudgetAlert.dedup_key`), and the
`BudgetAlert` model.

**Night 5 — CLI, dashboard, and CI.** A `cli.py` module (`run_pipeline`,
`format_report`) chaining every prior layer — ingestion, anomaly detection
(rolling-IQR), forecasting, and alerting — into one call, exposed as the
`ccs` console script. A Streamlit dashboard (`dashboard/app.py`) built on
the exact same `run_pipeline`, charting a daily-spend trend with anomalies
marked and a forecast-vs-budget chart with an uncertainty band, using
`plotly`. A new `data/sample/sample_cur_forecast.csv` fixture (45 days,
synthetic upward trend) so the CLI/dashboard have enough history to
demo forecasting without disturbing the original 10-day anomaly fixture. A
GitHub Actions workflow (`.github/workflows/ci.yml`) running `ruff check .`
and `pytest` on push/PR across Python 3.11 and 3.12.

## Test results

75 tests, all passing, across config, models, CUR ingestion (CSV + S3),
anomaly detection, forecasting, alerting, the CLI, and the dashboard:

```
$ pytest
75 passed in ~12s
```

`ruff check .` (E, F, I rule sets) also passes clean. One test
(`test_dashboard_app_runs_end_to_end_without_error`) drives the whole
Streamlit app through `streamlit.testing.v1.AppTest`, fitting a real Prophet
model in the process — marked `@pytest.mark.slow` for visibility but left in
the default run since it still completes in a few seconds.

`pip install -e ".[dev]"` alone installs everything needed for the full
suite: `boto3` + `moto` (S3 loader), `prophet` (forecasting), `slack-sdk`
(alerting), `streamlit` + `plotly` (dashboard), and `ruff` (lint) — no
external services, real AWS account, or real Slack workspace required.

## Known limitations

- **Alert throttling is in-memory only.** `AlertThrottle` is a plain `set`
  living in the calling process; it doesn't survive a restart and isn't
  shared across concurrent runs. A real deployment running `ccs` on a
  schedule would need a persistent store (e.g. a small SQLite table or a
  Redis set keyed on `dedup_key`) to actually dedupe across invocations.
- **Anomaly detection is per-service, not cross-service.** Both detectors
  flag one service's cost against its own history/window; a coordinated
  spend increase spread evenly across many services wouldn't trigger either
  detector even if the total is anomalous.
- **Forecasting is total-spend only.** `forecast_daily_costs` sums across
  every service before fitting Prophet, so there's no per-service forecast
  or budget — only one whole-account number.
- **The CLI's two default fixtures are a demo convenience, not a real
  pipeline shape.** `run_pipeline` reads anomaly data and forecast data from
  two different files by default because the one 10-day sample fixture is
  intentionally too short to forecast from. A real deployment would point
  both at the same, larger CUR export.
- **No real CUR export has been tested against.** Everything here is
  validated against a hand-built sample fixture and a `moto`-mocked S3
  bucket; real AWS CUR exports have additional columns, multiple file parts,
  and Parquet variants that `parse_cur_rows`' fixed column map doesn't
  handle.
- **The dashboard has no filters or interactivity beyond what Streamlit
  gives for free** — no date-range picker, no per-service drill-down, no
  dark mode toggle. It's a single fixed view over the two sample fixtures.

## Future ideas

- Persistent alert throttling (SQLite or Redis) so `ccs` can run on a
  schedule (cron / Lambda) without re-paging every invocation.
- Per-service forecasting and budgets, not just whole-account.
- A real CUR Parquet/manifest loader for the actual multi-part export format
  AWS produces, alongside the existing flat-CSV loader.
- Dashboard filters (date range, service, region) and a live-data mode that
  points at a real S3 bucket instead of the bundled fixtures.
- A third anomaly-detection method (e.g. seasonal decomposition) for
  services with strong weekly/monthly patterns that a static or rolling
  baseline both misread as drift.
