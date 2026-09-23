# PROGRESS

## Vision

`cloud-cost-sentinel` is a FinOps sentinel for AWS spend: it ingests AWS Cost
and Usage Report (CUR) data (sample CUR fixtures for local dev/tests, with a
LocalStack S3 path for a more realistic pipeline), detects spending anomalies
using statistical methods, forecasts next month's spend with Prophet, and
sends budget-drift alerts to Slack. Fully tested Python, with a dashboard to
tie ingestion, analysis, forecasting, and alerting together into something a
FinOps team could actually look at.

## Architecture

```
                +-------------------+
 CUR CSV /  --> |    ingestion      | --> CostRecord[] / DataFrame
 LocalStack S3  +-------------------+
                          |
                          v
                +-------------------+
                |     analysis       | --> Anomaly[]
                | (z-score / IQR)     |
                +-------------------+
                          |
                          v
                +-------------------+
                |    forecasting      | --> ForecastPoint[]
                |     (Prophet)        |
                +-------------------+
                          |
                          v
                +-------------------+
                |  budget drift +     | --> BudgetAlert[]
                |     alerting         |     -> Slack
                +-------------------+
                          |
                          v
                +-------------------+
                |     dashboard        |
                |   (Streamlit)          |
                +-------------------+
```

- **config** — a single `pydantic-settings` `Settings` object, overridable via
  `CCS_*` environment variables (budget, anomaly threshold, Slack webhook,
  data paths, LocalStack endpoint).
- **models** — Pydantic domain models shared by every layer, starting with
  `CostRecord`. Later phases add `Anomaly`, `ForecastPoint`, and
  `BudgetAlert` as those layers are built, so every model in the codebase is
  actually used by something.
- **ingestion** — adapters that normalize AWS billing data into
  `CostRecord` objects. Phase 1 ships a CUR-format CSV loader against a
  realistic sample fixture; Phase 2 adds a LocalStack S3 loader using the
  same validation path.
- **analysis** — statistical anomaly detection over daily/service cost
  aggregates (z-score first, rolling IQR as a second method for comparison).
- **forecasting** — Prophet-based monthly spend forecasting, plus a
  budget-drift calculation (forecast vs. configured budget).
- **alerting** — formats anomalies and budget-drift into Slack messages,
  with basic throttling so the same anomaly doesn't page twice.
- **dashboard** — Streamlit app that visualizes cost trends, anomalies, and
  forecasts against budget, driven by the same modules used by the CLI/tests.

Every phase below lands with its own tests; nothing is considered "done"
until `pytest` is green for it.

## Phased build plan

- [x] **Phase 1 — Foundation** (Night 1)
  - [x] Project scaffold: `pyproject.toml` (core deps + `forecast`/`alerts`/`dashboard`/`aws`/`dev` extras), `.gitignore`, MIT `LICENSE`, `src/` layout
  - [x] `config.py` — `Settings` via `pydantic-settings`, `CCS_` env prefix
  - [x] `models.py` — `CostRecord` domain model
  - [x] `ingestion/cur_loader.py` — CUR-format CSV loader (`load_cost_records`, `load_cost_dataframe`)
  - [x] Realistic sample CUR fixture at `data/sample/sample_cur.csv`
  - [x] Unit tests for config, models, and the CUR loader
  - [x] README with Project Status pointing here

- [x] **Phase 2 — Anomaly Detection** (Night 2)
  - [x] `ingestion/s3_loader.py` — S3 / LocalStack CUR ingestion (boto3, `aws` extra), sharing row-parsing with `cur_loader.py` via a new `parse_cur_rows` helper
  - [x] `analysis/anomaly.py` — z-score based daily/service anomaly detection
  - [x] `analysis/anomaly.py` rolling-IQR method as a second detector for comparison
  - [x] `Anomaly` model
  - [x] Tests for both detectors against synthetic and sample data, plus S3 loader tests against a `moto`-mocked bucket (`moto` added to `dev` extra, which now self-depends on `aws` so `pip install -e ".[dev]"` alone is sufficient)

- [x] **Phase 3 — Forecasting** (Night 3)
  - [x] `forecasting/prophet_forecast.py` — daily spend forecast (`daily_total_costs`, `forecast_daily_costs`)
  - [x] `ForecastPoint` model
  - [x] Budget-drift calculation (`calculate_budget_drift`, forecast vs. `monthly_budget_usd`) + `BudgetDrift` model
  - [x] `forecast_horizon_days` setting (`CCS_FORECAST_HORIZON_DAYS`, default 30)
  - [x] Tests (forecast shape/sanity checks against synthetic series, minimum-history guard, drift calculation, model validation)

- [x] **Phase 4 — Alerting** (Night 4)
  - [x] `alerting/slack.py` — Slack webhook client (`slack_sdk` `WebhookClient`, imported lazily)
  - [x] Alert formatting for anomalies and budget-drift (`format_anomaly_alert`, `format_budget_drift_alert`)
  - [x] Basic alert throttling/dedup (`AlertThrottle`, keyed on `BudgetAlert.dedup_key`)
  - [x] `BudgetAlert` model
  - [x] Tests (fake webhook client for formatting/send/throttle logic, one real-`WebhookClient`-construction test via monkeypatch)

- [ ] **Phase 5 — Dashboard & Polish** (Night 5)
  - [ ] Streamlit dashboard: cost trends, anomalies, forecast vs. budget
  - [ ] CLI entrypoint wiring ingestion -> analysis -> forecasting -> alerting
  - [ ] GitHub Actions CI (lint + test)
  - [ ] Final README pass, architecture diagram polish

## Where to resume (Night 5)

Phase 4 landed: `alerting/slack.py` (`format_anomaly_alert`,
`format_budget_drift_alert`, `AlertThrottle`, `send_alert`), and the
`BudgetAlert` model. Worth knowing before building on top of this:

- `send_alert` takes an optional `webhook_client` for dependency injection.
  When omitted, it lazily imports `slack_sdk.webhook.WebhookClient` and
  builds one from `Settings.slack_webhook_url` — so importing
  `cloud_cost_sentinel.alerting` (or calling `format_*`/`AlertThrottle`)
  never requires `slack_sdk` to be installed; only actually sending without
  an injected client does. Tests pass a fake client instead of monkeypatching
  network calls (see `tests/test_slack.py`), except for one test that
  verifies the real-`WebhookClient`-construction path via `monkeypatch`.
- `AlertThrottle` is in-memory only (a `set` of `dedup_key` strings) and only
  marks a key sent *after* a successful (HTTP 200) send — a failed send can
  be retried on the next run. There's no persistence layer, so a throttle
  instance needs to be created once and reused across calls (e.g. one per
  CLI/dashboard process) to be useful; a fresh one is created per call in the
  wild and it'll just never dedupe anything.
- `format_budget_drift_alert` formats regardless of `drift.over_budget` —
  callers are expected to check that flag themselves before calling it,
  since a routine under-budget forecast isn't page-worthy. (Phase 5's CLI
  wiring is the natural place to add that check once, rather than baking it
  into the formatter.)
- `alerts` extra (`slack-sdk`) was added to `dev`'s dependency chain in
  `pyproject.toml` (alongside `aws` and `forecast`, following the Phase 2/3
  precedent), so `pip install -e ".[dev]"` alone is sufficient for the full
  test suite — no separate Slack setup needed.

Start Phase 5 by wiring a CLI entrypoint that chains ingestion -> analysis
-> forecasting -> alerting end-to-end against `data/sample/sample_cur.csv`
(remembering the two fixture gotchas below: use the rolling-IQR detector or
a lower z-score threshold for the anomaly to fire, and the sample fixture is
too short to forecast from directly — generate a longer synthetic series or
extend the fixture). Then build the Streamlit dashboard on top of the same
functions the CLI and tests use, add GitHub Actions CI (lint + test), and do
a final README/architecture-diagram pass. Once the dashboard, CLI, and CI
are in and the full suite is green, write `DAILY_REPORT.md` and flip STATUS
to COMPLETE.

Older context, still true:

- The sample fixture's deliberate EC2 spike (2026-08-06) is **not** caught by
  `detect_anomalies_zscore` at the default `anomaly_z_threshold` (3.0) — a
  single outlier among 9 uniform points caps its own z-score just under 3.0
  (the "masking" effect, documented in `README.md` and
  `tests/test_anomaly.py`). It *is* caught by `detect_anomalies_rolling_iqr`
  at its defaults (`window=5`, `multiplier=3.0`). Keep this in mind for
  Phase 5's CLI/dashboard wiring — prefer the rolling-IQR detector, or
  lower the z-score threshold, for the sample data to actually trigger an
  alert end-to-end.
- `detect_anomalies_rolling_iqr`'s default `multiplier` is 3.0 (Tukey's "far
  out" fence), not the usual 1.5 boxplot fence — 1.5 flags routine
  day-to-day drift on low-variance services (see
  `test_rolling_iqr_default_multiplier_is_less_sensitive_than_boxplot_fence`).
- `pip install -e ".[dev]"` now transitively installs `boto3` + `moto` +
  `prophet` (`dev` extra self-depends on `aws` and `forecast` in
  `pyproject.toml`), so both the S3 loader and the forecasting path are
  fully testable with no external services and no extra setup.
- `forecast_daily_costs` requires at least `MIN_HISTORY_DAYS` (14) days of
  input history and raises `ValueError` below that — the 10-day
  `sample_cur.csv` fixture is too short to forecast from as-is. Tests build
  longer synthetic series inline (`tests/test_forecast.py`,
  `_synthetic_daily_df`) rather than adding a second fixture file. If Phase
  5's dashboard/CLI wants to demo forecasting against the sample data, it
  will need a longer fixture (or synthetic generation) too — the existing
  `sample_cur.csv` shouldn't be stretched to do both jobs.
- `forecast_daily_costs` clamps `forecast_cost`/`forecast_low`/
  `forecast_high` at 0 — Prophet's linear trend can extrapolate slightly
  negative for low-cost/short series, which isn't physically meaningful for
  spend.
- `BudgetDrift` lives in `models.py` alongside `ForecastPoint` (not a
  separate dataclass in the forecasting module) to keep the "domain models
  live in models.py" convention from Phase 1/2 consistent — `Anomaly` set
  that precedent and `BudgetDrift` follows it, even though the original
  Night 2 plan only mentioned adding `ForecastPoint`. `BudgetAlert` follows
  the same convention in Phase 4.

STATUS: IN_PROGRESS
