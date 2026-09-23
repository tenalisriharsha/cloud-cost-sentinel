"""Core domain models shared across ingestion, analysis, and alerting."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CostRecord(BaseModel):
    """A single normalized line item from an AWS Cost and Usage Report."""

    model_config = ConfigDict(frozen=True)

    usage_account_id: str
    service: str
    usage_type: str | None = None
    region: str | None = None
    usage_date: date
    unblended_cost: float = Field(ge=0)
    currency: str = "USD"


class Anomaly(BaseModel):
    """A flagged unusual cost observation for one service on one day."""

    model_config = ConfigDict(frozen=True)

    service: str
    usage_date: date
    actual_cost: float = Field(ge=0)
    expected_cost: float = Field(ge=0)
    score: float
    method: str


class ForecastPoint(BaseModel):
    """A single day's forecasted total spend (all services), with an
    uncertainty interval, produced by the Prophet forecasting model.
    """

    model_config = ConfigDict(frozen=True)

    usage_date: date
    forecast_cost: float = Field(ge=0)
    forecast_low: float = Field(ge=0)
    forecast_high: float = Field(ge=0)


class BudgetDrift(BaseModel):
    """A forecasted period's total spend compared against the configured
    monthly budget.
    """

    model_config = ConfigDict(frozen=True)

    period_start: date
    period_end: date
    forecast_total_usd: float = Field(ge=0)
    budget_usd: float = Field(gt=0)
    drift_usd: float
    drift_pct: float
    over_budget: bool


class BudgetAlert(BaseModel):
    """A formatted Slack message built from an :class:`Anomaly` or a
    :class:`BudgetDrift`, plus the key used to dedupe repeated sends of the
    same underlying condition.
    """

    model_config = ConfigDict(frozen=True)

    source: Literal["anomaly", "budget_drift"]
    dedup_key: str
    message: str
