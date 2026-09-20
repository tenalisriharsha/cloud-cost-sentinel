from datetime import date

import pytest
from pydantic import ValidationError

from cloud_cost_sentinel.models import CostRecord


def test_cost_record_accepts_valid_data():
    record = CostRecord(
        usage_account_id="111122223333",
        service="AmazonEC2",
        usage_type="BoxUsage:t3.medium",
        region="us-east-1",
        usage_date=date(2026, 8, 1),
        unblended_cost=42.10,
    )
    assert record.service == "AmazonEC2"
    assert record.currency == "USD"


def test_cost_record_defaults_optional_fields_to_none():
    record = CostRecord(
        usage_account_id="111122223333",
        service="AmazonS3",
        usage_date=date(2026, 8, 1),
        unblended_cost=8.32,
    )
    assert record.usage_type is None
    assert record.region is None


def test_cost_record_rejects_negative_cost():
    with pytest.raises(ValidationError):
        CostRecord(
            usage_account_id="111122223333",
            service="AmazonEC2",
            usage_date=date(2026, 8, 1),
            unblended_cost=-1.0,
        )


def test_cost_record_is_immutable():
    record = CostRecord(
        usage_account_id="111122223333",
        service="AmazonEC2",
        usage_date=date(2026, 8, 1),
        unblended_cost=42.10,
    )
    with pytest.raises(ValidationError):
        record.unblended_cost = 100.0
