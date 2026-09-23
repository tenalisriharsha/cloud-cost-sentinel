from datetime import date

import pytest
from pydantic import ValidationError

from cloud_cost_sentinel.models import BudgetAlert, BudgetDrift, CostRecord, ForecastPoint


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


def test_forecast_point_rejects_negative_cost():
    with pytest.raises(ValidationError):
        ForecastPoint(
            usage_date=date(2026, 9, 1),
            forecast_cost=-1.0,
            forecast_low=0.0,
            forecast_high=10.0,
        )


def test_forecast_point_is_immutable():
    point = ForecastPoint(
        usage_date=date(2026, 9, 1),
        forecast_cost=42.0,
        forecast_low=35.0,
        forecast_high=50.0,
    )
    with pytest.raises(ValidationError):
        point.forecast_cost = 100.0


def test_budget_drift_requires_positive_budget():
    with pytest.raises(ValidationError):
        BudgetDrift(
            period_start=date(2026, 9, 1),
            period_end=date(2026, 9, 30),
            forecast_total_usd=500.0,
            budget_usd=0.0,
            drift_usd=500.0,
            drift_pct=100.0,
            over_budget=True,
        )


def test_budget_alert_rejects_unknown_source():
    with pytest.raises(ValidationError):
        BudgetAlert(source="not_a_real_source", dedup_key="k", message="m")


def test_budget_alert_is_immutable():
    alert = BudgetAlert(source="anomaly", dedup_key="anomaly:AmazonEC2:2026-08-06:zscore", message="m")
    with pytest.raises(ValidationError):
        alert.message = "changed"
