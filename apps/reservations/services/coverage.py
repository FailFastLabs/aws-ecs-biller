import pandas as pd
from django.db.models import Sum


def compute_ri_coverage(account_id: str, billing_period: str) -> pd.DataFrame:
    from apps.costs.models import LineItem

    # Discounted usage (RI covered) — standard first, then convertible
    discounted = (
        LineItem.objects.filter(
            billing_period=billing_period,
            linked_account_id=account_id,
            line_item_type="DiscountedUsage",
        )
        .values("instance_type", "region", "offering_class")
        .annotate(ri_covered_qty=Sum("usage_quantity"))
    )

    # On-demand usage
    od = (
        LineItem.objects.filter(
            billing_period=billing_period,
            linked_account_id=account_id,
            line_item_type="Usage",
            pricing_term="OnDemand",
            service="AmazonEC2",
        )
        .values("instance_type", "region")
        .annotate(od_qty=Sum("usage_quantity"))
    )

    # RIFee — purchased capacity
    rifee = (
        LineItem.objects.filter(
            billing_period=billing_period,
            linked_account_id=account_id,
            line_item_type="RIFee",
        )
        .values("instance_type", "region")
        .annotate(
            purchased_qty=Sum("usage_quantity"),
            unused_qty=Sum("reservation_unused_quantity"),
        )
    )

    disc_df = pd.DataFrame(list(discounted))
    od_df = pd.DataFrame(list(od))
    rifee_df = pd.DataFrame(list(rifee))

    if disc_df.empty:
        return pd.DataFrame(columns=["instance_type", "region", "coverage_pct", "utilization_pct"])

    merged = disc_df.groupby(["instance_type", "region"], as_index=False)["ri_covered_qty"].sum()
    if not od_df.empty:
        merged = merged.merge(od_df, on=["instance_type", "region"], how="left")
        merged["od_qty"] = merged["od_qty"].fillna(0)
    else:
        merged["od_qty"] = 0

    if not rifee_df.empty:
        merged = merged.merge(rifee_df, on=["instance_type", "region"], how="left")
        merged["purchased_qty"] = merged["purchased_qty"].fillna(0)
        merged["unused_qty"] = merged["unused_qty"].fillna(0)
    else:
        merged["purchased_qty"] = merged["ri_covered_qty"]
        merged["unused_qty"] = 0

    total_usage = merged["ri_covered_qty"] + merged["od_qty"]
    merged["coverage_pct"] = merged["ri_covered_qty"] / total_usage.replace(0, float("nan"))
    merged["utilization_pct"] = (
        (merged["purchased_qty"] - merged["unused_qty"]) / merged["purchased_qty"].replace(0, float("nan"))
    )
    merged["coverage_pct"] = merged["coverage_pct"].fillna(0)
    merged["utilization_pct"] = merged["utilization_pct"].fillna(0)
    return merged
