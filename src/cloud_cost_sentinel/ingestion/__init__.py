"""Ingestion adapters that turn raw AWS billing data into ``CostRecord`` objects."""

from cloud_cost_sentinel.ingestion.cur_loader import load_cost_dataframe, load_cost_records

__all__ = ["load_cost_dataframe", "load_cost_records"]
