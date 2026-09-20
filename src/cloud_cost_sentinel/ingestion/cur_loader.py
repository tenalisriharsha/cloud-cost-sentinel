"""Load AWS Cost and Usage Report (CUR) style CSV data into ``CostRecord`` objects.

The CUR export format uses ``category/FieldName`` column headers (e.g.
``lineItem/UnblendedCost``). This loader maps a practical subset of those
columns onto :class:`~cloud_cost_sentinel.models.CostRecord`.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd
from dateutil import parser as date_parser

from cloud_cost_sentinel.models import CostRecord

CUR_COLUMN_MAP: dict[str, str] = {
    "lineItem/UsageAccountId": "usage_account_id",
    "lineItem/ProductCode": "service",
    "lineItem/UsageType": "usage_type",
    "product/region": "region",
    "lineItem/UsageStartDate": "usage_date",
    "lineItem/UnblendedCost": "unblended_cost",
    "lineItem/CurrencyCode": "currency",
}


def load_cost_records(path: str | Path) -> list[CostRecord]:
    """Parse a CUR-format CSV file into a list of validated ``CostRecord``."""
    csv_path = Path(path)
    with csv_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        missing_columns = set(CUR_COLUMN_MAP) - set(reader.fieldnames or [])
        if missing_columns:
            raise ValueError(f"CUR file is missing required columns: {sorted(missing_columns)}")

        records: list[CostRecord] = []
        for row in reader:
            mapped = {CUR_COLUMN_MAP[key]: value for key, value in row.items() if key in CUR_COLUMN_MAP}
            mapped["usage_date"] = date_parser.isoparse(mapped["usage_date"]).date()
            records.append(CostRecord(**mapped))
        return records


def load_cost_dataframe(path: str | Path) -> pd.DataFrame:
    """Parse a CUR-format CSV file into a flat ``pandas.DataFrame`` of cost records."""
    records = load_cost_records(path)
    if not records:
        return pd.DataFrame(columns=list(CostRecord.model_fields))
    return pd.DataFrame([record.model_dump() for record in records])
