"""
Portfolio-level RI/SP sizing recommendation.

Answers two questions:
  1. Are we over- or under-reserved overall?
  2. What should we do about it?

Over-reserved  → can't cancel early; show when natural expiries bring us to optimal.
Under-reserved → recommend which instance types to buy more of and by how much.
"""
from collections import defaultdict
from datetime import date, timedelta


def compute_portfolio_recommendation(account_id: str, billing_period: str, n_days: int = 30) -> dict:
    from django.db.models import Sum
    from django.db.models.functions import TruncHour
    from apps.costs.models import LineItem, InstancePricing
    from apps.reservations.models import ReservedInstance, SavingsPlan

    # ── 1. Current RI/SP portfolio ─────────────────────────────────────
    ri_qs = ReservedInstance.objects.filter(state="active")
    sp_qs = SavingsPlan.objects.filter(state="active")
    if account_id:
        ri_qs = ri_qs.filter(account__account_id=account_id)
        sp_qs = sp_qs.filter(account__account_id=account_id)

    ri_rows = list(ri_qs.values(
        "end_date", "instance_type", "instance_family", "region",
        "normalized_units", "recurring_hourly_cost", "instance_count",
        "offering_class",
    ))
    sp_rows = list(sp_qs.values("end_date", "plan_type", "commitment_hourly"))

    current_ri_hourly = sum(
        float(r["recurring_hourly_cost"] or 0) * (r["instance_count"] or 1)
        for r in ri_rows
    )
    current_sp_hourly = sum(float(r["commitment_hourly"] or 0) for r in sp_rows)

    # ── 2. Actual demand from LineItems (last n_days) ──────────────────
    end_date   = date.today()
    start_date = end_date - timedelta(days=n_days)

    scope = dict(service="AmazonEC2")
    if account_id:
        scope["linked_account_id"] = account_id

    # Snap to latest data if requested window has none
    if not LineItem.objects.filter(**scope, usage_start__date__gte=start_date,
                                   usage_start__date__lt=end_date).exists():
        from django.db.models import Max
        latest = LineItem.objects.filter(**scope).aggregate(mx=Max("usage_start__date"))["mx"]
        if latest:
            end_date = latest + timedelta(days=1)
            start_date = latest - timedelta(days=n_days - 1)

    base = dict(
        **scope,
        usage_start__date__gte=start_date,
        usage_start__date__lt=end_date,
    )

    # Hourly RI-covered usage
    ri_demand = (
        LineItem.objects.filter(**base, line_item_type="DiscountedUsage")
        .values("instance_type", "region")
        .annotate(total_qty=Sum("usage_quantity"), total_cost=Sum("reservation_effective_cost"))
    )
    # Hourly OD usage
    od_demand = (
        LineItem.objects.filter(**base, line_item_type="Usage", pricing_term="OnDemand")
        .values("instance_type", "region")
        .annotate(total_qty=Sum("usage_quantity"), total_cost=Sum("unblended_cost"))
    )

    # Aggregate per type/region
    demand_map: dict = defaultdict(lambda: {"ri_qty": 0.0, "od_qty": 0.0,
                                             "ri_cost": 0.0, "od_cost": 0.0})
    for row in ri_demand:
        k = (row["instance_type"], row["region"])
        demand_map[k]["ri_qty"]  += float(row["total_qty"]  or 0)
        demand_map[k]["ri_cost"] += float(row["total_cost"] or 0)
    for row in od_demand:
        k = (row["instance_type"], row["region"])
        demand_map[k]["od_qty"]  += float(row["total_qty"]  or 0)
        demand_map[k]["od_cost"] += float(row["total_cost"] or 0)

    # Total actual demand cost: RI effective cost + OD cost  (per period, not per hour)
    total_ri_demand_cost = sum(v["ri_cost"] for v in demand_map.values())
    total_od_demand_cost = sum(v["od_cost"] for v in demand_map.values())
    total_demand_cost    = total_ri_demand_cost + total_od_demand_cost

    # Per-hour rates (averaged over the window)
    hours_in_window = n_days * 24
    avg_ri_demand_hourly = total_ri_demand_cost / hours_in_window
    avg_od_demand_hourly = total_od_demand_cost / hours_in_window

    # ── 3. Over / under determination ─────────────────────────────────
    # "Ideal" committed RI spend = what we're currently paying for RI-covered usage
    # OD overage = spend we're paying OD rates that could be covered by RIs
    # Unused RI = RI committed but not used (wasted)
    unused_ri_hourly = max(current_ri_hourly - avg_ri_demand_hourly, 0)
    od_overage_hourly = avg_od_demand_hourly

    # Net position: positive = over-reserved (waste), negative = under-reserved (OD spillover)
    net_delta_hourly = unused_ri_hourly - od_overage_hourly

    if net_delta_hourly > 0.001:
        status = "over"
    elif od_overage_hourly > 0.001:
        status = "under"
    else:
        status = "optimal"

    # ── 4. Under-reserved: purchase recommendations ────────────────────
    increase_recs = []
    if status == "under":
        # Get pricing for OD types so we can estimate savings
        pricing_qs = {
            (p["region"], p["instance_type"]): p
            for p in InstancePricing.objects.values(
                "region", "instance_type", "od_hourly",
                "convertible_1yr_hourly", "standard_1yr_hourly",
            )
        }
        # Sort OD-heavy types by OD cost descending
        od_types = sorted(
            [
                (k, v) for k, v in demand_map.items()
                if v["od_cost"] > 0
            ],
            key=lambda x: x[1]["od_cost"],
            reverse=True,
        )
        for (itype, region), v in od_types[:10]:
            od_cost_total = v["od_cost"]
            od_qty_total  = v["od_qty"]
            if od_qty_total == 0:
                continue
            od_rate = od_cost_total / od_qty_total

            p = pricing_qs.get((region, itype), {})
            ri_rate = float(
                p.get("convertible_1yr_hourly") or p.get("standard_1yr_hourly") or 0
            )
            if ri_rate == 0:
                ri_rate = od_rate * 0.40

            # Avg hourly OD qty for this type
            avg_hourly_od_qty = od_qty_total / hours_in_window
            # Monthly savings if fully covered by RI
            monthly_od_cost = od_cost_total / n_days * 30
            monthly_ri_cost = avg_hourly_od_qty * ri_rate * 24 * 30
            monthly_savings = monthly_od_cost - monthly_ri_cost
            # How many instances to buy (normalized units → instances via avg unit size)
            units_needed = avg_hourly_od_qty
            # Approximate RI count: round up to nearest whole instance
            # Use normalized_units from the RI table for that type if available
            norm_per_instance = next(
                (float(r["normalized_units"]) / max(r["instance_count"], 1)
                 for r in ri_rows if r["instance_type"] == itype),
                od_qty_total / hours_in_window or 1.0,
            )
            count_needed = max(1, round(units_needed / norm_per_instance))

            increase_recs.append({
                "instance_type": itype,
                "region": region,
                "units_needed": round(units_needed, 2),
                "count_needed": count_needed,
                "avg_hourly_od_cost": round(od_cost_total / hours_in_window, 4),
                "monthly_od_cost": round(monthly_od_cost, 2),
                "monthly_ri_cost": round(monthly_ri_cost, 2),
                "monthly_savings": round(monthly_savings, 2),
            })

    # ── 5. Over-reserved: natural decrease timeline ────────────────────
    decrease_timeline = None
    if status == "over":
        target_hourly = current_ri_hourly - net_delta_hourly  # what we should be paying

        today = date.today()
        last_end = max((r["end_date"] for r in ri_rows), default=today)
        d = today
        natural_date = None
        months_until = None

        while d <= last_end:
            committed = sum(
                float(r["recurring_hourly_cost"] or 0) * (r["instance_count"] or 1)
                for r in ri_rows
                if r["end_date"] >= d
            )
            if committed <= target_hourly + 0.0001:
                natural_date = str(d)
                months_until = round((d - today).days / 30.44, 1)
                break
            d += timedelta(days=7)  # check weekly

        # Which RIs are the "excess" ones (expiring latest, most expensive)
        excess_hourly = net_delta_hourly
        excess_ris = []
        for r in sorted(ri_rows, key=lambda x: x["end_date"], reverse=True):
            hr = float(r["recurring_hourly_cost"] or 0) * (r["instance_count"] or 1)
            excess_ris.append({
                "instance_type": r["instance_type"],
                "region": r["region"],
                "instance_count": r["instance_count"],
                "hourly_cost": round(hr, 4),
                "end_date": str(r["end_date"]),
            })
            excess_hourly -= hr
            if excess_hourly <= 0:
                break

        decrease_timeline = {
            "target_hourly": round(target_hourly, 4),
            "excess_hourly": round(net_delta_hourly, 4),
            "natural_date": natural_date,
            "months_until_optimal": months_until,
            "excess_ris": excess_ris,
        }

    return {
        "current_ri_hourly": round(current_ri_hourly, 4),
        "current_sp_hourly": round(current_sp_hourly, 4),
        "current_total_hourly": round(current_ri_hourly + current_sp_hourly, 4),
        "avg_ri_demand_hourly": round(avg_ri_demand_hourly, 4),
        "avg_od_demand_hourly": round(avg_od_demand_hourly, 4),
        "unused_ri_hourly": round(unused_ri_hourly, 4),
        "od_overage_hourly": round(od_overage_hourly, 4),
        "net_delta_hourly": round(net_delta_hourly, 4),
        "status": status,
        "n_days": n_days,
        "increase_recs": increase_recs,
        "decrease_timeline": decrease_timeline,
    }
