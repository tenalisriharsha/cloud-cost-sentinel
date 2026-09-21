from datetime import date
from pathlib import Path

import boto3
import pandas as pd
import pytest
from moto import mock_aws

from cloud_cost_sentinel.ingestion.s3_loader import (
    load_cost_dataframe_from_s3,
    load_cost_records_from_s3,
)

SAMPLE_CUR_PATH = Path(__file__).resolve().parent.parent / "data" / "sample" / "sample_cur.csv"
BUCKET = "cur-reports"
KEY = "reports/sample_cur.csv"


@pytest.fixture
def s3_bucket_with_sample_cur():
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=BUCKET)
        client.put_object(Bucket=BUCKET, Key=KEY, Body=SAMPLE_CUR_PATH.read_bytes())
        yield client


def test_load_cost_records_from_s3_parses_sample_cur(s3_bucket_with_sample_cur):
    records = load_cost_records_from_s3(BUCKET, KEY)
    assert len(records) > 0
    first = records[0]
    assert first.usage_account_id == "111122223333"
    assert first.service == "AmazonEC2"
    assert first.usage_date == date(2026, 8, 1)
    assert first.unblended_cost == pytest.approx(42.10)


def test_load_cost_dataframe_from_s3_matches_records(s3_bucket_with_sample_cur):
    df = load_cost_dataframe_from_s3(BUCKET, KEY)
    records = load_cost_records_from_s3(BUCKET, KEY)
    assert isinstance(df, pd.DataFrame)
    assert len(df) == len(records)
    assert {"usage_account_id", "service", "usage_date", "unblended_cost"}.issubset(df.columns)


def test_load_cost_records_from_s3_missing_key_raises(s3_bucket_with_sample_cur):
    with pytest.raises(Exception):
        load_cost_records_from_s3(BUCKET, "does/not/exist.csv")


def test_load_cost_records_from_s3_empty_file_returns_empty_list():
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=BUCKET)
        header = (
            "lineItem/UsageAccountId,lineItem/ProductCode,lineItem/UsageType,product/region,"
            "lineItem/UsageStartDate,lineItem/UnblendedCost,lineItem/CurrencyCode\n"
        )
        client.put_object(Bucket=BUCKET, Key="empty.csv", Body=header.encode("utf-8"))
        assert load_cost_records_from_s3(BUCKET, "empty.csv") == []


def test_load_cost_dataframe_from_s3_empty_file_returns_empty_dataframe():
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=BUCKET)
        header = (
            "lineItem/UsageAccountId,lineItem/ProductCode,lineItem/UsageType,product/region,"
            "lineItem/UsageStartDate,lineItem/UnblendedCost,lineItem/CurrencyCode\n"
        )
        client.put_object(Bucket=BUCKET, Key="empty.csv", Body=header.encode("utf-8"))
        df = load_cost_dataframe_from_s3(BUCKET, "empty.csv")
        assert df.empty


def test_ingestion_package_lazily_exposes_s3_loader_functions():
    import cloud_cost_sentinel.ingestion as ingestion

    assert ingestion.load_cost_records_from_s3 is load_cost_records_from_s3
    assert ingestion.load_cost_dataframe_from_s3 is load_cost_dataframe_from_s3
    with pytest.raises(AttributeError):
        ingestion.not_a_real_attribute
