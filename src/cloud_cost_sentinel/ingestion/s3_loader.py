"""Load AWS CUR-format CSV data from an S3 (or LocalStack S3) bucket.

Reuses the same column mapping and row-parsing path as
:mod:`cloud_cost_sentinel.ingestion.cur_loader` so a CUR object behaves
identically whether it was read from local disk or S3.
"""

from __future__ import annotations

import csv
import io

import boto3
import pandas as pd

from cloud_cost_sentinel.ingestion.cur_loader import parse_cur_rows
from cloud_cost_sentinel.models import CostRecord


def _get_s3_client(endpoint_url: str | None = None):
    return boto3.client("s3", endpoint_url=endpoint_url)


def load_cost_records_from_s3(
    bucket: str,
    key: str,
    *,
    endpoint_url: str | None = None,
) -> list[CostRecord]:
    """Fetch a CUR-format CSV object from S3 and parse it into ``CostRecord`` objects."""
    client = _get_s3_client(endpoint_url)
    response = client.get_object(Bucket=bucket, Key=key)
    body = response["Body"].read().decode("utf-8")
    reader = csv.DictReader(io.StringIO(body))
    return parse_cur_rows(reader.fieldnames, reader)


def load_cost_dataframe_from_s3(
    bucket: str,
    key: str,
    *,
    endpoint_url: str | None = None,
) -> pd.DataFrame:
    """Fetch a CUR-format CSV object from S3 and parse it into a flat ``DataFrame``."""
    records = load_cost_records_from_s3(bucket, key, endpoint_url=endpoint_url)
    if not records:
        return pd.DataFrame(columns=list(CostRecord.model_fields))
    return pd.DataFrame([record.model_dump() for record in records])
