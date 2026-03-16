from decimal import Decimal
import pytest
from apps.splitting.services.splitter import _distribute_decimal


@pytest.mark.parametrize("total_cost,weights", [
    (
        Decimal("100.00"),
        {"a": Decimal("1") / 3, "b": Decimal("1") / 3, "c": Decimal("1") / 3},
    ),
    (
        Decimal("0.01"),
        {str(i): Decimal("1") / 7 for i in range(7)},
    ),
    (
        Decimal("333.333333333"),
        {"x": Decimal("1") / 3, "y": Decimal("2") / 3},
    ),
    (
        Decimal("500.00"),
        {"only": Decimal("1")},
    ),
    (
        Decimal("1000.00"),
        {"a": Decimal("0.40"), "b": Decimal("0.35"), "c": Decimal("0.25")},
    ),
])
def test_distribute_decimal_invariant(total_cost, weights):
    result = _distribute_decimal(total_cost, weights)
    assert sum(result.values()) == total_cost, (
        f"SUM={sum(result.values())} != total={total_cost}"
    )


def test_distribute_decimal_all_nonnegative():
    weights = {"a": Decimal("0.6"), "b": Decimal("0.4")}
    result = _distribute_decimal(Decimal("50.00"), weights)
    assert all(v >= 0 for v in result.values())


def test_distribute_single_tenant_gets_all():
    result = _distribute_decimal(Decimal("99.99"), {"only": Decimal("1")})
    assert result["only"] == Decimal("99.99")


def test_distribute_repeating_decimal_sums_correctly():
    # 1/3 + 1/3 + 1/3 — classic floating point trap
    weights = {"a": Decimal("1") / 3, "b": Decimal("1") / 3, "c": Decimal("1") / 3}
    total = Decimal("1.00")
    result = _distribute_decimal(total, weights)
    assert sum(result.values()) == total
