from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from pydantic import ValidationError

from cloud_cost_sentinel.ingestion.cur_loader import load_cost_dataframe, load_cost_records

SAMPLE_CUR_PATH = Path(__file__).resolve().parent.parent / "data" / "sample" / "sample_cur.csv"

CUR_HEADER = (
    "lineItem/UsageAccountId,lineItem/ProductCode,lineItem/UsageType,product/region,"
    "lineItem/UsageStartDate,lineItem/UnblendedCost,lineItem/CurrencyCode\n"
)


def test_sample_cur_file_loads_without_error():
    records = load_cost_records(SAMPLE_CUR_PATH)
    assert len(records) > 0


def test_loaded_record_fields_are_mapped_correctly():
    records = load_cost_records(SAMPLE_CUR_PATH)
    first = records[0]
    assert first.usage_account_id == "111122223333"
    assert first.service == "AmazonEC2"
    assert first.usage_type == "BoxUsage:t3.medium"
    assert first.region == "us-east-1"
    assert first.usage_date == date(2026, 8, 1)
    assert first.unblended_cost == pytest.approx(42.10)
    assert first.currency == "USD"


def test_load_cost_dataframe_returns_dataframe_with_expected_columns():
    df = load_cost_dataframe(SAMPLE_CUR_PATH)
    assert isinstance(df, pd.DataFrame)
    assert len(df) == len(load_cost_records(SAMPLE_CUR_PATH))
    assert {"usage_account_id", "service", "usage_date", "unblended_cost"}.issubset(df.columns)


def test_missing_required_column_raises(tmp_path):
    bad_csv = tmp_path / "bad.csv"
    bad_csv.write_text("lineItem/UsageAccountId,lineItem/ProductCode\n111,AmazonEC2\n")
    with pytest.raises(ValueError, match="missing required columns"):
        load_cost_records(bad_csv)


def test_empty_cur_file_returns_empty_list(tmp_path):
    empty_csv = tmp_path / "empty.csv"
    empty_csv.write_text(CUR_HEADER)
    assert load_cost_records(empty_csv) == []


def test_empty_cur_file_returns_empty_dataframe(tmp_path):
    empty_csv = tmp_path / "empty.csv"
    empty_csv.write_text(CUR_HEADER)
    df = load_cost_dataframe(empty_csv)
    assert df.empty


def test_negative_cost_in_source_file_is_rejected(tmp_path):
    bad_csv = tmp_path / "negative.csv"
    bad_csv.write_text(
        CUR_HEADER + "111122223333,AmazonEC2,BoxUsage:t3.medium,us-east-1,2026-08-01T00:00:00Z,-5.00,USD\n"
    )
    with pytest.raises(ValidationError):
        load_cost_records(bad_csv)
