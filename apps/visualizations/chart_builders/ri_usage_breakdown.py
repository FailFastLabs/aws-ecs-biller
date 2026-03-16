import pandas as pd
from django.db.models import Sum


def build_ri_usage_breakdown(account_id: str, billing_period: str, instance_type: str = "", region: str = "", limit: int = 100) -> dict:
    from apps.costs.models import LineItem

    base_filter = dict(billing_period=billing_period, service="AmazonEC2")
    if account_id:
        base_filter["linked_account_id"] = account_id

    # RI-covered usage
    discounted_qs = (
        LineItem.objects.filter(**base_filter, line_item_type="DiscountedUsage")
        .values("instance_type", "region")
        .annotate(
            ri_qty=Sum("usage_quantity"),
            ri_cost=Sum("reservation_effective_cost"),
            ri_od_equiv=Sum("public_on_demand_cost"),
        )
    )
    # On-demand usage
    od_qs = (
        LineItem.objects.filter(**base_filter, line_item_type="Usage", pricing_term="OnDemand")
        .values("instance_type", "region")
        .annotate(
            od_qty=Sum("usage_quantity"),
            od_cost=Sum("unblended_cost"),
        )
    )

    disc_df = pd.DataFrame(list(discounted_qs))
    od_df = pd.DataFrame(list(od_qs))

    if disc_df.empty and od_df.empty:
        return {"data": [], "layout": {"title": "No usage data for this period"}}

    if disc_df.empty:
        disc_df = pd.DataFrame(columns=["instance_type", "region", "ri_qty", "ri_cost", "ri_od_equiv"])
    if od_df.empty:
        od_df = pd.DataFrame(columns=["instance_type", "region", "od_qty", "od_cost"])

    merged = pd.merge(disc_df, od_df, on=["instance_type", "region"], how="outer").fillna(0)
    merged["total_qty"] = merged["ri_qty"] + merged["od_qty"]
    merged["total_cost"] = merged["ri_cost"] + merged["od_cost"]
    merged["coverage_pct"] = (merged["ri_qty"] / merged["total_qty"].replace(0, float("nan"))).fillna(0)
    merged["ri_savings"] = merged["ri_od_equiv"] - merged["ri_cost"]
    merged = merged.sort_values("total_qty", ascending=False)

    # Top N for the dropdown — return full list as top_types
    top = merged.head(limit)

    # If filtering to specific instance_type+region, narrow down
    if instance_type and region:
        row = merged[(merged["instance_type"] == instance_type) & (merged["region"] == region)]
        if not row.empty:
            chart_df = row
        else:
            chart_df = top.head(20)
    else:
        chart_df = top.head(20)

    labels = chart_df["instance_type"] + "<br>" + chart_df["region"]

    traces = [
        {
            "type": "bar",
            "name": "RI Covered (hrs)",
            "x": labels.tolist(),
            "y": chart_df["ri_qty"].round(1).tolist(),
            "marker": {"color": "#198754"},
            "hovertemplate": "<b>%{x}</b><br>RI hrs: %{y:.1f}<extra></extra>",
        },
        {
            "type": "bar",
            "name": "On-Demand (hrs)",
            "x": labels.tolist(),
            "y": chart_df["od_qty"].round(1).tolist(),
            "marker": {"color": "#dc3545"},
            "hovertemplate": "<b>%{x}</b><br>OD hrs: %{y:.1f}<extra></extra>",
        },
    ]

    layout = {
        "barmode": "stack",
        "xaxis": {"title": "", "tickangle": -35},
        "yaxis": {"title": "Instance-Hours"},
        "legend": {"orientation": "h", "y": -0.35},
        "margin": {"t": 20, "b": 120, "l": 60, "r": 20},
    }

    # Pass top_types list in layout extras for the dropdown
    top_types = [
        {"instance_type": r["instance_type"], "region": r["region"]}
        for r in merged.head(limit)[["instance_type", "region"]].to_dict("records")
        if r["instance_type"]
    ]

    return {"data": traces, "layout": layout, "top_types": top_types}
