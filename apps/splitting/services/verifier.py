from decimal import Decimal
from django.db.models import Sum


class SplitInvariantViolationError(Exception):
    pass


def _billing_period_to_range(billing_period: str):
    from datetime import date
    year, month = map(int, billing_period.split("-"))
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month + 1, 1)
    return start, end


def verify_split_invariant(rule, billing_period: str,
                             tolerance: Decimal = Decimal("1e-8")) -> None:
    from apps.splitting.models import SplitResult

    start, end = _billing_period_to_range(billing_period)
    groups = (
        SplitResult.objects.filter(splitting_rule=rule, hour__date__range=(start, end))
        .values("hour", "region", "usage_type", "original_cost")
        .annotate(sum_allocated=Sum("allocated_cost"))
    )
    violations = []
    for g in groups:
        diff = abs(Decimal(str(g["sum_allocated"])) - Decimal(str(g["original_cost"])))
        if diff > tolerance:
            violations.append(
                f"hour={g['hour']}, region={g['region']}, usage_type={g['usage_type']}: "
                f"sum={g['sum_allocated']}, original={g['original_cost']}, diff={diff}"
            )
    if violations:
        raise SplitInvariantViolationError(
            f"Invariant violated in {len(violations)} groups:\n" + "\n".join(violations[:5])
        )
