import numpy as np
from django.db.models import Sum


def compute_sp_counterfactual(account_id: str, billing_period: str) -> dict:
    from apps.costs.models import LineItem

    sp_rows = (
        LineItem.objects.filter(
            billing_period=billing_period,
            linked_account_id=account_id,
            line_item_type="SavingsPlanCoveredUsage",
        )
        .values("savings_plan_arn")
        .annotate(
            actual_cost=Sum("sp_effective_cost"),
            od_equivalent=Sum("public_on_demand_cost"),
            used_commitment=Sum("sp_used_commitment"),
        )
    )

    results = {}
    for row in sp_rows:
        arn = row["savings_plan_arn"]
        actual = float(row["actual_cost"] or 0)
        od = float(row["od_equivalent"] or 0)
        savings = od - actual
        savings_rate = savings / od if od else 0

        # Marginal analysis: would +10% commitment save more than it costs?
        # hours_in_period = 744 (Jan 2025)
        hours = 744
        used = float(row["used_commitment"] or 0)
        # p80 of hourly uncovered spend: approximate as 0 since we don't have full data
        additional_fee = used / hours * 0.10 * hours
        marginal_savings = used / hours * 0.10 * savings_rate * hours
        recommend_increase = marginal_savings > additional_fee

        results[arn] = {
            "actual_cost": actual,
            "od_equivalent": od,
            "savings": savings,
            "savings_rate": round(savings_rate, 4),
            "recommend_increase": recommend_increase,
            "recommended_commitment_delta": round(used / hours * 0.10, 4) if recommend_increase else 0,
        }
    return results
