from datetime import date, timedelta
from django.db.models import Sum
from django.db.models.functions import TruncHour


def build_ri_hourly_usage(
    account_id: str,
    instance_type: str,
    region: str,
    n_days: int = 7,
) -> dict:
    """
    Stacked area chart of hourly EC2 usage for a specific instance_type+region.

    SP and Spot layers come from real CUR data.  The RI/OD split is
    *re-computed* using the **current** RI capacity (instance_count) so the
    blue dotted capacity line always sits exactly at the RI ↔ OD boundary.

    Stack order (bottom → top):
      Reserved (green) → SP (purple) → On-Demand (red) → Spot (yellow)
    """
    from apps.costs.models import LineItem
    from apps.reservations.models import ReservedInstance

    if not instance_type or not region:
        return {"data": [], "layout": {"title": "Select an instance type and region"}}

    end_date = date.today()
    start_date = end_date - timedelta(days=n_days)

    base = dict(
        instance_type=instance_type,
        region=region,
        service="AmazonEC2",
        usage_start__date__gte=start_date,
        usage_start__date__lt=end_date,
    )
    if account_id:
        base["linked_account_id"] = account_id

    def hourly_qty(extra_filter):
        return (
            LineItem.objects.filter(**base, **extra_filter)
            .annotate(hour=TruncHour("usage_start"))
            .values("hour")
            .annotate(qty=Sum("usage_quantity"))
            .order_by("hour")
        )

    # Real CUR data per billing category
    ri_cur_qs = hourly_qty({"line_item_type": "DiscountedUsage"})
    sp_qs     = hourly_qty({"line_item_type": "SavingsPlanCoveredUsage"})
    od_cur_qs = hourly_qty({"line_item_type": "Usage", "pricing_term": "OnDemand"})
    spot_qs   = hourly_qty({"line_item_type": "Usage", "pricing_term": ""})

    hours: dict = {}
    for label, qs in [("ri_cur", ri_cur_qs), ("sp", sp_qs),
                       ("od_cur", od_cur_qs), ("spot", spot_qs)]:
        for row in qs:
            h = row["hour"].strftime("%Y-%m-%dT%H:%M:%S")
            hours.setdefault(h, {"ri_cur": 0.0, "sp": 0.0, "od_cur": 0.0, "spot": 0.0})
            hours[h][label] += float(row["qty"] or 0)

    if not hours:
        return {
            "data": [],
            "layout": {"title": f"No usage data for {instance_type} / {region} in last {n_days} days"},
        }

    # Current RI capacity (instance_count — same unit as usage_quantity)
    ri_cap_qs = ReservedInstance.objects.filter(
        state="active", instance_type=instance_type, region=region
    )
    if account_id:
        ri_cap_qs = ri_cap_qs.filter(account__account_id=account_id)
    ri_capacity = sum(
        r["instance_count"] for r in ri_cap_qs.values("instance_count")
    )

    # Re-split RI + OD using current RI capacity instead of historical CUR split
    sorted_hours = sorted(hours.keys())
    ri_y   = []
    sp_y   = []
    od_y   = []
    spot_y = []
    for h in sorted_hours:
        d = hours[h]
        sp_y.append(round(d["sp"], 3))
        spot_y.append(round(d["spot"], 3))
        # Base usage = everything that was either RI-covered or OD in the CUR
        base_usage = d["ri_cur"] + d["od_cur"]
        ri_y.append(round(min(base_usage, ri_capacity), 3))
        od_y.append(round(max(base_usage - ri_capacity, 0), 3))

    traces = [
        {
            "type": "scatter",
            "mode": "lines",
            "name": "Reserved (RI)",
            "x": sorted_hours,
            "y": ri_y,
            "stackgroup": "usage",
            "fillcolor": "rgba(25,135,84,0.6)",
            "line": {"color": "rgba(25,135,84,0.8)", "width": 0.5},
            "hovertemplate": "RI covered: %{y:.2f}<extra></extra>",
        },
        {
            "type": "scatter",
            "mode": "lines",
            "name": "Savings Plan",
            "x": sorted_hours,
            "y": sp_y,
            "stackgroup": "usage",
            "fillcolor": "rgba(111,66,193,0.55)",
            "line": {"color": "rgba(111,66,193,0.8)", "width": 0.5},
            "hovertemplate": "SP covered: %{y:.2f}<extra></extra>",
        },
        {
            "type": "scatter",
            "mode": "lines",
            "name": "On-Demand",
            "x": sorted_hours,
            "y": od_y,
            "stackgroup": "usage",
            "fillcolor": "rgba(220,53,69,0.55)",
            "line": {"color": "rgba(220,53,69,0.8)", "width": 0.5},
            "hovertemplate": "OD: %{y:.2f}<extra></extra>",
        },
        {
            "type": "scatter",
            "mode": "lines",
            "name": "Spot",
            "x": sorted_hours,
            "y": spot_y,
            "stackgroup": "usage",
            "fillcolor": "rgba(255,193,7,0.55)",
            "line": {"color": "rgba(255,193,7,0.8)", "width": 0.5},
            "hovertemplate": "Spot: %{y:.2f}<extra></extra>",
        },
    ]

    if ri_capacity > 0:
        traces.append({
            "type": "scatter",
            "mode": "lines",
            "name": f"RI Capacity ({ri_capacity})",
            "x": [sorted_hours[0], sorted_hours[-1]],
            "y": [ri_capacity, ri_capacity],
            "line": {"color": "#0d6efd", "width": 2, "dash": "dot"},
            "hovertemplate": f"RI capacity: {ri_capacity}<extra></extra>",
        })

    layout = {
        "xaxis": {"title": "", "type": "date"},
        "yaxis": {"title": "Instance-Hours"},
        "legend": {"orientation": "h", "y": -0.25},
        "margin": {"t": 20, "b": 80, "l": 60, "r": 20},
        "hovermode": "x unified",
    }

    return {"data": traces, "layout": layout}
