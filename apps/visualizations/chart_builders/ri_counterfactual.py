from datetime import date, timedelta
import numpy as np
from django.db.models import Sum
from django.db.models.functions import TruncDate


def build_ri_counterfactual(
    account_id: str,
    instance_type: str,
    region: str,
    reserved_count: float,
    days: int = 7,
) -> dict:
    from apps.costs.models import LineItem, InstancePricing

    if not instance_type or not region:
        return {"data": [], "layout": {"title": "Select an instance type and region"}}

    end_date = date.today()
    start_date = end_date - timedelta(days=days)

    base_filter = dict(
        instance_type=instance_type,
        region=region,
        service="AmazonEC2",
        usage_start__date__gte=start_date,
        usage_start__date__lt=end_date,
    )
    if account_id:
        base_filter["linked_account_id"] = account_id

    # Daily usage: combine OD + RI-covered
    od_daily = (
        LineItem.objects.filter(**base_filter, line_item_type="Usage", pricing_term="OnDemand")
        .annotate(day=TruncDate("usage_start"))
        .values("day")
        .annotate(qty=Sum("usage_quantity"), cost=Sum("unblended_cost"))
    )
    ri_daily = (
        LineItem.objects.filter(**base_filter, line_item_type="DiscountedUsage")
        .annotate(day=TruncDate("usage_start"))
        .values("day")
        .annotate(qty=Sum("usage_quantity"), ri_cost=Sum("reservation_effective_cost"))
    )

    # Build daily totals dict
    daily: dict = {}
    for row in od_daily:
        d = str(row["day"])
        daily.setdefault(d, {"od_qty": 0, "od_cost": 0, "ri_qty": 0, "ri_cost": 0})
        daily[d]["od_qty"] += float(row["qty"] or 0)
        daily[d]["od_cost"] += float(row["cost"] or 0)
    for row in ri_daily:
        d = str(row["day"])
        daily.setdefault(d, {"od_qty": 0, "od_cost": 0, "ri_qty": 0, "ri_cost": 0})
        daily[d]["ri_qty"] += float(row["qty"] or 0)
        daily[d]["ri_cost"] += float(row["ri_cost"] or 0)

    if not daily:
        return {"data": [], "layout": {"title": f"No usage data for {instance_type} in {region}"}}

    # Get pricing
    try:
        pricing = InstancePricing.objects.filter(
            instance_type=instance_type, region=region
        ).order_by("-effective_date").first()
        od_rate = float(pricing.od_hourly) if pricing else 0
        ri_rate = float(pricing.convertible_1yr_hourly or pricing.standard_1yr_hourly or 0) if pricing else 0
    except Exception:
        od_rate = 0
        ri_rate = 0

    # Fall back: derive od_rate from actual data
    if od_rate == 0:
        total_od_qty = sum(v["od_qty"] for v in daily.values())
        total_od_cost = sum(v["od_cost"] for v in daily.values())
        od_rate = total_od_cost / total_od_qty if total_od_qty > 0 else 0.1

    if ri_rate == 0:
        ri_rate = od_rate * 0.4  # typical ~60% discount

    days_list = sorted(daily.keys())
    actual_costs = []
    actual_labels = []

    for d in days_list:
        v = daily[d]
        # Actual cost: RI-covered at ri_cost + OD at od_cost
        actual_costs.append(v["ri_cost"] + v["od_cost"])
        actual_labels.append(d)

    avg_actual = np.mean(actual_costs) if actual_costs else 0

    # Counterfactual curve: cost at different reserved_count values
    max_qty = max((v["od_qty"] + v["ri_qty"]) for v in daily.values())
    curve_counts = np.linspace(0, max_qty * 1.3, 60)
    curve_costs = []
    for rc in curve_counts:
        daily_cf_costs = []
        for v in daily.values():
            total_qty = v["od_qty"] + v["ri_qty"]
            below = min(total_qty, rc)
            above = max(total_qty - rc, 0)
            # Committed RI cost is fixed regardless of usage (if unused, still pay)
            ri_committed_cost = rc * ri_rate * 24  # 24 hrs/day
            od_cost = above * od_rate
            # Total cost per day = RI commitment + OD overage
            daily_cf_costs.append(ri_committed_cost + od_cost)
        curve_costs.append(np.mean(daily_cf_costs))

    # Mark the current actual reserved_count (approximated from RI qty)
    avg_ri_qty = np.mean([v["ri_qty"] for v in daily.values()])
    current_rc = reserved_count if reserved_count > 0 else avg_ri_qty

    # Cost at requested reserved_count
    cf_at_rc = []
    for v in daily.values():
        total_qty = v["od_qty"] + v["ri_qty"]
        above = max(total_qty - current_rc, 0)
        cf_at_rc.append(current_rc * ri_rate * 24 + above * od_rate)
    avg_cf = np.mean(cf_at_rc) if cf_at_rc else 0

    traces = [
        {
            "type": "scatter",
            "mode": "lines",
            "name": "Avg Daily Cost (counterfactual)",
            "x": curve_counts.tolist(),
            "y": [round(c, 4) for c in curve_costs],
            "line": {"color": "#0d6efd", "width": 2},
            "hovertemplate": "Reserved: %{x:.0f} hrs/day<br>Avg cost: $%{y:.2f}<extra></extra>",
        },
        {
            "type": "scatter",
            "mode": "markers",
            "name": f"Current (≈{current_rc:.0f} hrs/day reserved)",
            "x": [current_rc],
            "y": [round(avg_cf, 4)],
            "marker": {"color": "#198754", "size": 12, "symbol": "circle"},
            "hovertemplate": "Reserved: %{x:.0f}<br>Avg cost: $%{y:.2f}<extra></extra>",
        },
        {
            "type": "scatter",
            "mode": "markers",
            "name": f"Actual avg daily cost: ${avg_actual:.2f}",
            "x": [avg_ri_qty],
            "y": [round(avg_actual, 4)],
            "marker": {"color": "#dc3545", "size": 10, "symbol": "x"},
            "hovertemplate": "Actual avg: $%{y:.2f}<extra></extra>",
        },
    ]

    layout = {
        "xaxis": {"title": "Reserved Instance-Hours / Day"},
        "yaxis": {"title": "Avg Daily Cost ($)"},
        "margin": {"t": 20, "b": 50, "l": 70, "r": 20},
        "legend": {"orientation": "h", "y": -0.3},
    }

    return {
        "data": traces,
        "layout": layout,
        "avg_actual": round(avg_actual, 2),
        "avg_counterfactual": round(avg_cf, 2),
        "days": days,
        "instance_type": instance_type,
        "region": region,
    }
