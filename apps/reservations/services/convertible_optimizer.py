import pulp
import pandas as pd
from decimal import Decimal


NORM_FACTORS = {
    "m5.large": 4.0, "m5.xlarge": 8.0, "m5.2xlarge": 16.0,
    "c5.xlarge": 8.0, "c5.2xlarge": 16.0,
    "r5.large": 4.0, "r5.2xlarge": 16.0,
    "t3.medium": 2.0,
}


def optimize_convertible_ris(account_id: str, billing_period: str,
                               max_commitment_increase_pct: float = 0.01) -> list:
    from apps.reservations.models import ReservedInstance
    from apps.costs.models import InstancePricing, LineItem

    ris = list(ReservedInstance.objects.filter(
        account__account_id=account_id,
        offering_class="convertible",
        state="active",
    ))
    if not ris:
        return []

    # Build demand: average hourly normalized unit demand per instance type/family
    demand_qs = list(
        LineItem.objects.filter(
            billing_period=billing_period,
            linked_account_id=account_id,
            service="AmazonEC2",
            line_item_type="Usage",
        )
        .values("instance_type", "instance_family", "region")
        .annotate(total_qty=__import__("django.db.models", fromlist=["Sum"]).Sum("usage_quantity"))
    )
    demand_by_type = {
        (d["instance_type"], d["region"]): float(d["total_qty"] or 0)
        for d in demand_qs
    }

    # Get pricing
    pricing_qs = list(InstancePricing.objects.all().values(
        "region", "instance_type", "od_hourly", "convertible_1yr_hourly"
    ))
    pricing = {(p["region"], p["instance_type"]): p for p in pricing_qs}

    prob = pulp.LpProblem("convertible_ri_swap", pulp.LpMinimize)

    # Decision variables: x[ri_arn][instance_type] = normalized units allocated
    x = {}
    for ri in ris:
        x[ri.reservation_arn] = {}
        # Eligible targets: same family, same region
        family = ri.instance_family
        region = ri.region
        eligible = [itype for itype in NORM_FACTORS if itype.startswith(family) and
                    (region, itype) in pricing]
        if not eligible:
            eligible = [ri.instance_type]
        for itype in eligible:
            var = pulp.LpVariable(f"x_{ri.reservation_id}_{itype.replace('.','_')}",
                                   lowBound=0)
            x[ri.reservation_arn][itype] = var

    # Objective: minimize total RI hourly cost
    obj_terms = []
    for ri in ris:
        for itype, var in x[ri.reservation_arn].items():
            p = pricing.get((ri.region, itype), {})
            rate = float(p.get("convertible_1yr_hourly") or ri.recurring_hourly_cost / ri.normalized_units)
            obj_terms.append(rate * var)
    prob += pulp.lpSum(obj_terms)

    # Constraint (a): each RI keeps its total normalized units
    for ri in ris:
        prob += pulp.lpSum(x[ri.reservation_arn].values()) == ri.normalized_units

    # Constraint (b): total cost <= current * (1 + max_pct)
    current_total = float(sum(ri.recurring_hourly_cost for ri in ris))
    prob += pulp.lpSum(obj_terms) <= current_total * (1 + max_commitment_increase_pct)

    status = prob.solve(pulp.PULP_CBC_CMD(msg=0))
    if pulp.LpStatus[status] != "Optimal":
        return []

    # Extract recommendations
    recommendations = []
    for ri in ris:
        best_type = ri.instance_type
        best_units = 0.0
        for itype, var in x[ri.reservation_arn].items():
            val = var.value() or 0
            if val > best_units:
                best_units = val
                best_type = itype

        if best_type != ri.instance_type:
            current_monthly = float(ri.recurring_hourly_cost) * 720
            p = pricing.get((ri.region, best_type), {})
            new_rate = float(p.get("convertible_1yr_hourly") or 0) * ri.normalized_units
            optimal_monthly = new_rate * 720
            recommendations.append({
                "ri_arn": ri.reservation_arn,
                "current_type": ri.instance_type,
                "recommended_type": best_type,
                "current_monthly_cost": round(current_monthly, 2),
                "optimal_monthly_cost": round(optimal_monthly, 2),
                "monthly_savings": round(current_monthly - optimal_monthly, 2),
            })
    return recommendations
