import pandas as pd

REQUIRED_FIELDS = ["line_item_id", "billing_period", "usage_start", "service", "linked_account_id", "unblended_cost"]
CREDIT_TYPES = {"Credit", "Refund", "EdpDiscount", "BundledDiscount"}


def validate(df: pd.DataFrame) -> tuple:
    available = [f for f in REQUIRED_FIELDS if f in df.columns]
    if len(available) < len(REQUIRED_FIELDS):
        missing = set(REQUIRED_FIELDS) - set(available)
        # Add missing cols as NaN so null check works
        for col in missing:
            df[col] = None

    mask_null = df[REQUIRED_FIELDS].isnull().any(axis=1)

    if "line_item_type" in df.columns:
        mask_neg = (df["unblended_cost"] < 0) & (~df["line_item_type"].isin(CREDIT_TYPES))
    else:
        mask_neg = pd.Series(False, index=df.index)

    rejected = df[mask_null | mask_neg].copy()
    valid = df[~(mask_null | mask_neg)].copy()
    return valid, rejected
