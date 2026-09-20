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

- [ ] **Phase 2 — Anomaly Detection** (Night 2)
  - [ ] `ingestion/s3_loader.py` — LocalStack S3 CUR ingestion (boto3, `aws` extra)
  - [ ] `analysis/anomaly.py` — z-score based daily/service anomaly detection
  - [ ] `analysis/` rolling-IQR method as a second detector for comparison
  - [ ] `Anomaly` model
  - [ ] Tests for both detectors against synthetic and sample data

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

## Where to resume (Night 2)

Start Phase 2 with `ingestion/s3_loader.py`: a LocalStack-backed S3 CUR
loader that reuses `CUR_COLUMN_MAP` and `CostRecord` validation from
`ingestion/cur_loader.py` (factor the row-parsing logic out of
`load_cost_records` into a shared helper that both the CSV path and the S3
path call, rather than duplicating it). Add the `aws` extra's `boto3` as an
actual runtime import there. Then build `analysis/anomaly.py` on top of
`load_cost_dataframe`, using the existing `data/sample/sample_cur.csv`
fixture (it already has a deliberate EC2 cost spike on 2026-08-06 to exercise
the detector against). Add `Anomaly` to `models.py` once `analysis/` is
ready to construct instances of it — not before.

STATUS: IN_PROGRESS
