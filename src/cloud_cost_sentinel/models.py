"""Core domain models shared across ingestion, analysis, and alerting."""

from __future__ import annotations

from datetime import date

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
