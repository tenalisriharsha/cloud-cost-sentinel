"""Runtime configuration for cloud-cost-sentinel.

All settings are overridable via environment variables prefixed with
``CCS_`` (e.g. ``CCS_MONTHLY_BUDGET_USD=5000``).
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for ingestion, analysis, and alerting."""

    model_config = SettingsConfigDict(env_prefix="CCS_", env_file=".env", extra="ignore")

    monthly_budget_usd: float = Field(default=1000.0, gt=0)
    anomaly_z_threshold: float = Field(default=3.0, gt=0)
    forecast_horizon_days: int = Field(default=30, gt=0)
    currency: str = "USD"

    sample_data_dir: Path = Path("data/sample")

    slack_webhook_url: str | None = None

    aws_s3_endpoint_url: str | None = None
    aws_cur_bucket: str | None = None


def get_settings() -> Settings:
    """Return a freshly loaded ``Settings`` instance.

    Not cached, so tests can mutate environment variables between calls
    without needing to reset process-wide state.
    """
    return Settings()
