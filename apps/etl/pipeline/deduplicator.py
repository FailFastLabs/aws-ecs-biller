import pandas as pd


def deduplicate(df: pd.DataFrame, existing_ids: set) -> pd.DataFrame:
    if "line_item_id" not in df.columns or "billing_period" not in df.columns:
        return df
    df = df.drop_duplicates(subset=["line_item_id", "billing_period"])
    mask = df["line_item_id"].isin(existing_ids)
    return df[~mask]
