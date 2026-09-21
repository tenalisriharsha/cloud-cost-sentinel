"""Ingestion adapters that turn raw AWS billing data into ``CostRecord`` objects."""

from cloud_cost_sentinel.ingestion.cur_loader import load_cost_dataframe, load_cost_records

__all__ = [
    "load_cost_dataframe",
    "load_cost_records",
    "load_cost_dataframe_from_s3",
    "load_cost_records_from_s3",
]


def __getattr__(name: str):
    """Lazily expose the S3 loader so importing this package doesn't require boto3."""
    if name in ("load_cost_dataframe_from_s3", "load_cost_records_from_s3"):
        from cloud_cost_sentinel.ingestion import s3_loader

        return getattr(s3_loader, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
