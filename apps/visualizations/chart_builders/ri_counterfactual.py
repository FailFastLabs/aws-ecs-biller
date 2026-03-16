from datetime import date, timedelta
import numpy as np
from django.db.models import Sum
from django.db.models.functions import TruncHour


def build_ri_counterfactual(
    account_id: str,
    instance_type: str,
    region: str,
    reserved_count: float = 0,
    days: int = 7,
) -> dict:
    """
    U-hoop counterfactual: avg daily cost vs reserved capacity level.

    Shape of the U:
      - Too few reserved  → lots of on-demand overage, cost rises left of minimum
      - Too many reserved → paying for idle RI capacity, cost rises right of minimum
      - Bottom of U       → optimal reservation level

    Cost model per hour h:
        cost(h, R) = R * ri_rate + max(usage_h - R, 0) * od_rate
    where R is normalized units reserved (continuous).
    Daily cost = sum over 24 hours of cost(h, R).
    Avg daily cost = mean over all days.
    """
    from apps.costs.models import LineItem, InstancePricing
    from apps.reservations.models import ReservedInstance

    if not instance_type or not region:
        return {"data": [], "layout": {"title": "Select an instance type and region"}}

    end_date = date.today()
    start_date = end_date - timedelta(days=days)

    scope = dict(
        instance_type=instance_type,
        region=region,
        service="AmazonEC2",
    )
    if account_id:
        scope["linked_account_id"] = account_id

    # If no data in the requested window, snap to the most recent available data
    if not LineItem.objects.filter(**scope, usage_start__date__gte=start_date,
                                   usage_start__date__lt=end_date).exists():
        from django.db.models import Max
        latest = LineItem.objects.filter(**scope).aggregate(mx=Max("usage_start__date"))["mx"]
        if latest:
            end_date = latest + timedelta(days=1)
            start_date = latest - timedelta(days=days - 1)

    base = dict(
        **scope,
        usage_start__date__gte=start_date,
        usage_start__date__lt=end_date,
    )

    # Collect hourly usage (RI-covered + OD + spot all count as demand)
    def hourly_qs(extra):
        return (
            LineItem.objects.filter(**base, **extra)
            .annotate(hour=TruncHour("usage_start"))
            .values("hour")
            .annotate(qty=Sum("usage_quantity"), cost=Sum("unblended_cost"))
        )

    ri_hourly  = hourly_qs({"line_item_type": "DiscountedUsage"})
    od_hourly  = hourly_qs({"line_item_type": "Usage", "pricing_term": "OnDemand"})
    sp_hourly  = hourly_qs({"line_item_type": "SavingsPlanCoveredUsage"})

    hourly: dict = {}
    for row in ri_hourly:
        h = str(row["hour"])
        hourly.setdefault(h, {"qty": 0.0, "ri_cost": 0.0, "od_cost": 0.0})
        hourly[h]["qty"]     += float(row["qty"]  or 0)
        hourly[h]["ri_cost"] += float(row["cost"] or 0)
    for row in od_hourly:
        h = str(row["hour"])
        hourly.setdefault(h, {"qty": 0.0, "ri_cost": 0.0, "od_cost": 0.0})
        hourly[h]["qty"]     += float(row["qty"]  or 0)
        hourly[h]["od_cost"] += float(row["cost"] or 0)
    for row in sp_hourly:
        h = str(row["hour"])
        hourly.setdefault(h, {"qty": 0.0, "ri_cost": 0.0, "od_cost": 0.0})
        hourly[h]["qty"] += float(row["qty"] or 0)

    if not hourly:
        return {
            "data": [],
            "layout": {"title": f"No usage data for {instance_type} / {region} in last {days}d"},
        }

    usage_series = np.array([v["qty"] for v in hourly.values()])

    # ── Rates ──────────────────────────────────────────────────────────
    try:
        pricing = (
            InstancePricing.objects.filter(instance_type=instance_type, region=region)
            .order_by("-effective_date")
            .first()
        )
        od_rate = float(pricing.od_hourly) if pricing else 0.0
        ri_rate = float(
            (pricing.convertible_1yr_hourly or pricing.standard_1yr_hourly) or 0
        ) if pricing else 0.0
    except Exception:
        od_rate = ri_rate = 0.0

    # Derive OD rate from actual spend if not in pricing table
    if od_rate == 0:
        total_od_cost = sum(float(v["od_cost"]) for v in hourly.values())
        total_od_qty  = sum(float(v["qty"]) for v in hourly.values())
        od_rate = total_od_cost / total_od_qty if total_od_qty > 0 else 0.10

    if ri_rate == 0:
        ri_rate = od_rate * 0.40  # ~60% RI discount is typical

    # ── Current reservation level (must be resolved before computing range) ──
    ri_qs = ReservedInstance.objects.filter(
        state="active", instance_type=instance_type, region=region
    )
    if account_id:
        ri_qs = ri_qs.filter(account__account_id=account_id)
    current_R = sum(float(r["normalized_units"]) for r in ri_qs.values("normalized_units"))
    if reserved_count > 0:
        current_R = reserved_count

    # ── U-hoop curve ───────────────────────────────────────────────────
    # First pass over a wide range to locate the optimal point
    peak = float(usage_series.max()) if len(usage_series) else 1.0
    hours_per_day = len(usage_series) / max(days, 1)
    wide_r = np.linspace(0, peak * 2, 200)
    wide_costs = []
    for R in wide_r:
        hc = R * ri_rate + np.maximum(usage_series - R, 0) * od_rate
        wide_costs.append(float(np.mean(hc)) * max(hours_per_day, 1))

    opt_idx_wide = int(np.argmin(wide_costs))
    opt_R_wide   = float(wide_r[opt_idx_wide])

    # Display range: 0 → max(current_R, opt_R) * 1.1  (floor at half of peak)
    display_max = max(current_R, opt_R_wide) * 1.1
    display_max = max(display_max, peak * 0.5)
    r_values = np.linspace(0, display_max, 120)

    avg_costs = []
    for R in r_values:
        hourly_costs = R * ri_rate + np.maximum(usage_series - R, 0) * od_rate
        avg_daily = float(np.mean(hourly_costs)) * max(hours_per_day, 1)
        avg_costs.append(round(avg_daily, 4))

    opt_idx  = int(np.argmin(avg_costs))
    opt_R    = float(r_values[opt_idx])
    opt_cost = avg_costs[opt_idx]

    # Cost at current_R
    cur_hourly_costs = current_R * ri_rate + np.maximum(usage_series - current_R, 0) * od_rate
    cur_avg_daily = float(np.mean(cur_hourly_costs)) * max(hours_per_day, 1)

    # Actual observed avg daily cost
    actual_daily = sum(v["ri_cost"] + v["od_cost"] for v in hourly.values())
    actual_avg   = actual_daily / max(days, 1)

    # ── Annotations ───────────────────────────────────────────────────
    traces = [
        {
            "type": "scatter",
            "mode": "lines",
            "name": "Avg Daily Cost",
            "x": r_values.tolist(),
            "y": avg_costs,
            "line": {"color": "#0d6efd", "width": 2.5},
            "fill": "tozeroy",
            "fillcolor": "rgba(13,110,253,0.07)",
            "hovertemplate": "Reserved: %{x:.1f} units<br>Avg cost/day: $%{y:.2f}<extra></extra>",
        },
        {
            "type": "scatter",
            "mode": "markers+text",
            "name": f"Optimal ({opt_R:.1f} units) → ${opt_cost:.2f}/day",
            "x": [opt_R],
            "y": [opt_cost],
            "marker": {"color": "#198754", "size": 14, "symbol": "star"},
            "text": ["Optimal"],
            "textposition": "top center",
            "hovertemplate": "Optimal: %{x:.1f} units<br>$%{y:.2f}/day<extra></extra>",
        },
        {
            "type": "scatter",
            "mode": "markers+text",
            "name": f"Current ({current_R:.1f} units) → ${cur_avg_daily:.2f}/day",
            "x": [current_R],
            "y": [round(cur_avg_daily, 4)],
            "marker": {"color": "#fd7e14", "size": 12, "symbol": "circle"},
            "text": ["Current"],
            "textposition": "top center",
            "hovertemplate": "Current: %{x:.1f} units<br>$%{y:.2f}/day<extra></extra>",
        },
    ]

    # Shade "too few" and "too many" regions
    too_few_mask  = r_values <= opt_R
    too_many_mask = r_values >= opt_R

    traces.insert(1, {
        "type": "scatter",
        "mode": "lines",
        "name": "Too few (↑ OD cost)",
        "x": r_values[too_few_mask].tolist(),
        "y": [avg_costs[i] for i, v in enumerate(too_few_mask) if v],
        "fill": "tozeroy",
        "fillcolor": "rgba(220,53,69,0.10)",
        "line": {"color": "rgba(0,0,0,0)", "width": 0},
        "showlegend": True,
        "hoverinfo": "skip",
    })
    traces.insert(2, {
        "type": "scatter",
        "mode": "lines",
        "name": "Too many (↑ idle RI cost)",
        "x": r_values[too_many_mask].tolist(),
        "y": [avg_costs[i] for i, v in enumerate(too_many_mask) if v],
        "fill": "tozeroy",
        "fillcolor": "rgba(255,193,7,0.12)",
        "line": {"color": "rgba(0,0,0,0)", "width": 0},
        "showlegend": True,
        "hoverinfo": "skip",
    })

    layout = {
        "xaxis": {"title": f"Reserved Normalized Units ({instance_type} / {region})"},
        "yaxis": {"title": "Avg Daily Cost ($)"},
        "margin": {"t": 20, "b": 60, "l": 70, "r": 20},
        "legend": {"orientation": "h", "y": -0.3},
        "hovermode": "x",
    }

    return {
        "data": traces,
        "layout": layout,
        "avg_actual": round(actual_avg, 2),
        "avg_counterfactual": round(cur_avg_daily, 2),
        "optimal_R": round(opt_R, 2),
        "optimal_cost": round(opt_cost, 2),
        "current_R": round(current_R, 2),
        "days": days,
        "instance_type": instance_type,
        "region": region,
    }
