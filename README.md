# cloud-cost-sentinel

A FinOps sentinel for AWS spend. It ingests AWS Cost and Usage Report (CUR)
data, detects spending anomalies with statistical methods, forecasts next
month's spend with Prophet, and sends budget-drift alerts to Slack — with a
dashboard to tie it all together.

## Project Status

This project is under active, public, nightly development. See
[PROGRESS.md](PROGRESS.md) for the architecture, the phased build plan, and
exactly what's done vs. what's next.

## Features (planned)

- **Ingestion** — load AWS CUR-format billing data from CSV or LocalStack S3.
- **Anomaly detection** — flag unusual daily/service spend using statistical
  methods (z-score, rolling IQR).
- **Forecasting** — project next month's spend with Prophet.
- **Alerting** — post budget-drift and anomaly alerts to Slack.
- **Dashboard** — visualize cost trends, anomalies, and forecasts.

## Getting started

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## Project layout

```
src/cloud_cost_sentinel/
  config.py           # environment-driven settings
  models.py            # core domain models (CostRecord, ...)
  ingestion/            # CUR CSV / LocalStack S3 loaders
data/sample/            # sample CUR data used by tests and local runs
tests/                   # pytest suite
```

## License

MIT — see [LICENSE](LICENSE).
