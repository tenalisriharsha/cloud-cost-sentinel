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

- [ ] **Phase 3 — Forecasting** (Night 3)
  - [ ] `forecasting/prophet_forecast.py` — next-month spend forecast
  - [ ] `ForecastPoint` model
  - [ ] Budget-drift calculation (forecast vs. `monthly_budget_usd`)
  - [ ] Tests (forecast shape/sanity checks, drift calculation)

- [ ] **Phase 4 — Alerting** (Night 4)
  - [ ] `alerting/slack.py` — Slack webhook client
  - [ ] Alert formatting for anomalies and budget-drift
  - [ ] Basic alert throttling/dedup
  - [ ] `BudgetAlert` model
  - [ ] Tests (mocked Slack calls, formatting, throttling logic)

- [ ] **Phase 5 — Dashboard & Polish** (Night 5)
  - [ ] Streamlit dashboard: cost trends, anomalies, forecast vs. budget
  - [ ] CLI entrypoint wiring ingestion -> analysis -> forecasting -> alerting
  - [ ] GitHub Actions CI (lint + test)
  - [ ] Final README pass, architecture diagram polish

## Where to resume (Night 3)

Phase 2 landed: `ingestion/s3_loader.py` (S3 / LocalStack CUR loader sharing
`parse_cur_rows` with `cur_loader.py`), `analysis/anomaly.py` (z-score +
rolling-IQR detectors), and the `Anomaly` model. Worth knowing before
building on top of this:

- The sample fixture's deliberate EC2 spike (2026-08-06) is **not** caught by
  `detect_anomalies_zscore` at the default `anomaly_z_threshold` (3.0) — a
  single outlier among 9 uniform points caps its own z-score just under 3.0
  (the "masking" effect, documented in `README.md` and
  `tests/test_anomaly.py`). It *is* caught by `detect_anomalies_rolling_iqr`
  at its defaults (`window=5`, `multiplier=3.0`). Keep this in mind if
  Phase 4's alerting wires up anomaly detection to Slack — prefer the
  rolling-IQR detector, or lower the z-score threshold, for the sample data
  to actually trigger an alert end-to-end.
- `detect_anomalies_rolling_iqr`'s default `multiplier` is 3.0 (Tukey's "far
  out" fence), not the usual 1.5 boxplot fence — 1.5 flags routine
  day-to-day drift on low-variance services (see
  `test_rolling_iqr_default_multiplier_is_less_sensitive_than_boxplot_fence`).
- `pip install -e ".[dev]"` now transitively installs `boto3` + `moto`
  (`dev` extra self-depends on `aws` in `pyproject.toml`) so the S3 loader
  is fully testable without real AWS or LocalStack running.

Start Phase 3 with `forecasting/prophet_forecast.py`: a next-month spend
forecast built on top of `daily_service_costs` (or a similar total-daily-cost
aggregate — Prophet wants a `ds`/`y` shaped frame) from
`analysis/anomaly.py`. Add a `ForecastPoint` model to `models.py` once the
forecasting function is ready to construct instances of it. Then add the
budget-drift calculation (forecast total vs. `Settings.monthly_budget_usd`).
The `data/sample/sample_cur.csv` fixture only spans 10 days, which is too
short for a meaningful Prophet fit — Phase 3 will likely need a second,
longer synthetic fixture (or a generated synthetic series in the test itself)
to exercise forecasting sensibly; don't force the existing 10-day fixture to
do double duty here.

STATUS: IN_PROGRESS
