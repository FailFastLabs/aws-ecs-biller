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
    Stacked area chart of hourly EC2 usage for a specific instance_type+region:
      - RI Covered           (green,  bottom)
      - Savings Plan Covered (purple, above RI — only SP rows for this instance type)
      - On-Demand            (red,    above SP)
      - Spot                 (yellow, top)
    Plus a horizontal dashed line for currently purchased RI capacity.
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

    ri_qs   = hourly_qty({"line_item_type": "DiscountedUsage"})
    sp_qs   = hourly_qty({"line_item_type": "SavingsPlanCoveredUsage"})
    od_qs   = hourly_qty({"line_item_type": "Usage", "pricing_term": "OnDemand"})
    spot_qs = hourly_qty({"line_item_type": "Usage", "pricing_term": ""})

    # Merge into a dict keyed by hour string
    hours: dict = {}
    for label, qs in [("ri", ri_qs), ("sp", sp_qs), ("od", od_qs), ("spot", spot_qs)]:
        for row in qs:
            h = row["hour"].strftime("%Y-%m-%dT%H:%M:%S")
            hours.setdefault(h, {"ri": 0.0, "sp": 0.0, "od": 0.0, "spot": 0.0})
            hours[h][label] += float(row["qty"] or 0)

    if not hours:
        return {
            "data": [],
            "layout": {"title": f"No usage data for {instance_type} / {region} in last {n_days} days"},
        }

    sorted_hours = sorted(hours.keys())
    ri_y   = [round(hours[h]["ri"],   3) for h in sorted_hours]
    sp_y   = [round(hours[h]["sp"],   3) for h in sorted_hours]
    od_y   = [round(hours[h]["od"],   3) for h in sorted_hours]
    spot_y = [round(hours[h]["spot"], 3) for h in sorted_hours]

    # Current purchased RI capacity (normalized units / hr) for this type+region
    ri_cap_qs = ReservedInstance.objects.filter(
        state="active", instance_type=instance_type, region=region
    )
    if account_id:
        ri_cap_qs = ri_cap_qs.filter(account__account_id=account_id)
    ri_capacity = sum(
        float(r["normalized_units"]) for r in ri_cap_qs.values("normalized_units")
    )

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
            "hovertemplate": "RI: %{y:.2f} units<extra></extra>",
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
            "hovertemplate": "SP: %{y:.2f} units<extra></extra>",
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
            "hovertemplate": "OD: %{y:.2f} units<extra></extra>",
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
            "hovertemplate": "Spot: %{y:.2f} units<extra></extra>",
        },
    ]

    if ri_capacity > 0:
        traces.append({
            "type": "scatter",
            "mode": "lines",
            "name": f"Reserved Capacity ({ri_capacity:.1f} units)",
            "x": [sorted_hours[0], sorted_hours[-1]],
            "y": [ri_capacity, ri_capacity],
            "line": {"color": "#0d6efd", "width": 2, "dash": "dash"},
            "hovertemplate": f"Reserved: {ri_capacity:.1f} units<extra></extra>",
        })

    layout = {
        "xaxis": {"title": "", "type": "date"},
        "yaxis": {"title": "Normalized Instance-Units"},
        "legend": {"orientation": "h", "y": -0.25},
        "margin": {"t": 20, "b": 80, "l": 60, "r": 20},
        "hovermode": "x unified",
    }

    return {"data": traces, "layout": layout}
