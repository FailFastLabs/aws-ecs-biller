from decimal import Decimal, ROUND_HALF_UP
from datetime import date


def _billing_period_to_range(billing_period: str):
    year, month = map(int, billing_period.split("-"))
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month + 1, 1)
    return start, end


def _compute_weights(rule, hour, region, usage_type) -> dict:
    if rule.weight_strategy == "equal":
        tenants = _get_active_tenants(rule, hour)
        n = len(tenants)
        return {t: Decimal("1") / Decimal(str(n)) for t in tenants} if n else {}
    elif rule.weight_strategy == "proportional_usage":
        usage = _get_tag_usage(rule.split_by_tag_key, hour, region, usage_type)
        total = sum(usage.values()) or Decimal("1")
        return {t: v / total for t, v in usage.items()}
    elif rule.weight_strategy == "custom_weight":
        raw = rule.custom_weights
        total_w = sum(Decimal(str(v)) for v in raw.values())
        return {k: Decimal(str(v)) / total_w for k, v in raw.items()} if total_w else {}
    return {}


def _distribute_decimal(total: Decimal, weights: dict) -> dict:
    PRECISION = Decimal("0.0000000001")
    tenants = sorted(weights.keys())
    allocated = {}
    running = Decimal("0")
    for tenant in tenants[:-1]:
        share = (weights[tenant] * total).quantize(PRECISION, rounding=ROUND_HALF_UP)
        allocated[tenant] = share
        running += share
    allocated[tenants[-1]] = total - running
    return allocated


def _get_active_tenants(rule, hour) -> list:
    from apps.costs.models import LineItem
    tags_qs = LineItem.objects.filter(
        service=rule.service, region=rule.region,
        usage_start__lte=hour, usage_end__gte=hour,
        tags__has_key=rule.split_by_tag_key,
    ).values_list("tags", flat=True)
    return list({t.get(rule.split_by_tag_key) for t in tags_qs if t})


def _get_tag_usage(tag_key: str, hour, region: str, usage_type: str) -> dict:
    from django.db.models import Sum
    from apps.costs.models import LineItem
    rows = (
        LineItem.objects.filter(
            region=region, usage_type=usage_type,
            usage_start__lte=hour, usage_end__gte=hour,
            tags__has_key=tag_key,
        )
        .values("tags")
        .annotate(qty=Sum("usage_quantity"))
    )
    result = {}
    for r in rows:
        val = r["tags"].get(tag_key)
        if val:
            result[val] = result.get(val, Decimal("0")) + Decimal(str(r["qty"]))
    return result


def run_split(rule, billing_period: str) -> int:
    from django.db.models import Sum
    from apps.costs.models import HourlyCostAggregate
    from apps.splitting.models import SplitResult
    from .verifier import verify_split_invariant

    start, end = _billing_period_to_range(billing_period)
    rows = (
        HourlyCostAggregate.objects.filter(
            service=rule.service, region=rule.region, hour__date__range=(start, end),
        )
        .values("hour", "region", "usage_type")
        .annotate(total_cost=Sum("unblended_cost"))
    )

    results = []
    for row in rows:
        total_cost = Decimal(str(row["total_cost"]))
        hour, region, usage_type = row["hour"], row["region"], row["usage_type"]
        weights = _compute_weights(rule, hour, region, usage_type)
        if not weights:
            if rule.weight_strategy == "custom_weight" and rule.custom_weights:
                raw = rule.custom_weights
                total_w = sum(Decimal(str(v)) for v in raw.values())
                weights = {k: Decimal(str(v)) / total_w for k, v in raw.items()}
        if not weights:
            continue
        allocated = _distribute_decimal(total_cost, weights)
        for tenant, alloc_cost in allocated.items():
            weight = (alloc_cost / total_cost).quantize(Decimal("0.00000001")) if total_cost else Decimal("0")
            results.append(SplitResult(
                splitting_rule=rule,
                billing_period=billing_period,
                hour=hour, region=region, usage_type=usage_type,
                tenant_tag_value=tenant,
                original_cost=total_cost,
                allocated_cost=alloc_cost,
                allocation_weight=weight,
            ))

    SplitResult.objects.bulk_create(results, batch_size=5000, ignore_conflicts=True)
    verify_split_invariant(rule, billing_period)
    return len(results)
