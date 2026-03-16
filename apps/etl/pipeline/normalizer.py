import json
import pandas as pd
from apps.etl.column_mappings.cur_columns import CUR_TO_INTERNAL

COST_COLS = [
    "unblended_cost", "blended_cost", "net_unblended_cost",
    "public_on_demand_cost", "reservation_effective_cost",
    "reservation_amortized_upfront_cost", "reservation_recurring_fee",
    "sp_effective_cost", "split_cost",
]

NUMERIC_COLS = [
    "usage_quantity", "reservation_unused_quantity", "reservation_unused_recurring_fee",
    "reservation_norm_units", "reservation_count", "normalization_factor",
    "normalized_usage_amount", "sp_used_commitment", "sp_total_commitment",
    "total_discount", "split_actual_usage", "split_usage_ratio",
]


def normalize_schema(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns={k: v for k, v in CUR_TO_INTERNAL.items() if k in df.columns})

    for col in ("usage_start", "usage_end", "billing_period_start", "billing_period_end"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], utc=True, errors="coerce")

    if "billing_period_start" in df.columns:
        df["billing_period"] = df["billing_period_start"].dt.strftime("%Y-%m")
    elif "usage_start" in df.columns:
        df["billing_period"] = df["usage_start"].dt.strftime("%Y-%m")

    for col in COST_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    for col in NUMERIC_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    if "tags" in df.columns:
        df["tags"] = df["tags"].apply(_parse_tags_json)

    return df


def _parse_tags_json(raw) -> dict:
    if not raw or (isinstance(raw, float)):
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
