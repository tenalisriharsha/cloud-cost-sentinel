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
- **Forecasting** — project next month's spend with Prophet. *(planned)*
- **Alerting** — post budget-drift and anomaly alerts to Slack. *(planned)*
- **Dashboard** — visualize cost trends, anomalies, and forecasts. *(planned)*

## Getting started

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

`pip install -e ".[dev]"` also pulls in `boto3` and `moto` (via the `aws`
extra) so the S3 ingestion path is testable without a real AWS account or a
running LocalStack container.

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

## Project layout

```
src/cloud_cost_sentinel/
  config.py             # environment-driven settings
  models.py              # core domain models (CostRecord, Anomaly, ...)
  ingestion/              # CUR CSV / S3 (LocalStack-compatible) loaders
  analysis/                # anomaly detection (z-score, rolling IQR)
data/sample/               # sample CUR data used by tests and local runs
tests/                      # pytest suite
```

## License

MIT — see [LICENSE](LICENSE).
