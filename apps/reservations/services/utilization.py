import pandas as pd
from django.db.models import Sum


def compute_ri_utilization(account_id: str, billing_period: str) -> pd.DataFrame:
    from apps.costs.models import LineItem

    rifee = list(
        LineItem.objects.filter(
            billing_period=billing_period,
            linked_account_id=account_id,
            line_item_type="RIFee",
        )
        .values("reservation_arn", "instance_type", "region", "offering_class")
        .annotate(
            purchased_units=Sum("normalized_usage_amount"),
            total_fee=Sum("unblended_cost"),
            unused_qty=Sum("reservation_unused_quantity"),
            unused_fee=Sum("reservation_unused_recurring_fee"),
        )
    )

    discounted = list(
        LineItem.objects.filter(
            billing_period=billing_period,
            linked_account_id=account_id,
            line_item_type="DiscountedUsage",
        )
        .values("reservation_arn")
        .annotate(used_units=Sum("normalized_usage_amount"))
    )

    rifee_df = pd.DataFrame(rifee)
    disc_df = pd.DataFrame(discounted)

    if rifee_df.empty:
        return pd.DataFrame()

    if not disc_df.empty:
        rifee_df = rifee_df.merge(disc_df, on="reservation_arn", how="left")
        rifee_df["used_units"] = rifee_df["used_units"].fillna(0)
    else:
        rifee_df["used_units"] = 0

    rifee_df["utilization_pct"] = (
        rifee_df["used_units"] / rifee_df["purchased_units"].replace(0, float("nan"))
    ).fillna(0)
    rifee_df["unused_hours"] = rifee_df["unused_qty"]
    rifee_df["unused_cost"] = rifee_df["unused_fee"]
    return rifee_df
