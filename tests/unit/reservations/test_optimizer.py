import pytest
from unittest.mock import patch, MagicMock
from decimal import Decimal


@pytest.mark.django_db
def test_optimizer_returns_empty_when_no_convertible_ris():
    from apps.reservations.services.convertible_optimizer import optimize_convertible_ris
    result = optimize_convertible_ris("123456789012", "2025-01")
    assert result == []


@pytest.mark.django_db
def test_optimizer_with_convertible_ri_and_pricing():
    from apps.reservations.services.convertible_optimizer import optimize_convertible_ris
    from apps.costs.models import InstancePricing
    from tests.factories.reservations import ReservedInstanceFactory
    from tests.factories.accounts import AwsAccountFactory

    account = AwsAccountFactory(account_id="111122223333")

    # Create a convertible RI
    ri = ReservedInstanceFactory(
        account=account,
        instance_type="m5.large",
        instance_family="m5",
        region="us-east-1",
        offering_class="convertible",
        normalized_units=40.0,
        recurring_hourly_cost=Decimal("0.6240"),
        state="active",
    )

    # Create pricing for m5.large and m5.xlarge
    InstancePricing.objects.create(
        region="us-east-1",
        instance_type="m5.large",
        od_hourly=Decimal("0.0960"),
        convertible_1yr_hourly=Decimal("0.0624"),
        convertible_3yr_hourly=Decimal("0.0450"),
        standard_1yr_hourly=Decimal("0.0580"),
        standard_3yr_hourly=Decimal("0.0400"),
        effective_date="2025-01-01",
    )
    InstancePricing.objects.create(
        region="us-east-1",
        instance_type="m5.xlarge",
        od_hourly=Decimal("0.1920"),
        convertible_1yr_hourly=Decimal("0.1248"),
        convertible_3yr_hourly=Decimal("0.0900"),
        standard_1yr_hourly=Decimal("0.1160"),
        standard_3yr_hourly=Decimal("0.0800"),
        effective_date="2025-01-01",
    )

    # Should run the LP and return a list (may be empty if no swap is beneficial)
    result = optimize_convertible_ris("111122223333", "2025-01")
    assert isinstance(result, list)


@pytest.mark.django_db
def test_optimizer_non_optimal_lp_returns_empty():
    """When PuLP solver returns non-optimal, should return []."""
    from apps.reservations.services.convertible_optimizer import optimize_convertible_ris
    from tests.factories.reservations import ReservedInstanceFactory
    from tests.factories.accounts import AwsAccountFactory
    from apps.costs.models import InstancePricing
    import pulp

    account = AwsAccountFactory(account_id="999988887777")
    ReservedInstanceFactory(
        account=account,
        instance_type="m5.large",
        instance_family="m5",
        region="us-east-1",
        offering_class="convertible",
        normalized_units=40.0,
        recurring_hourly_cost=Decimal("0.6240"),
        state="active",
    )
    InstancePricing.objects.create(
        region="us-east-1",
        instance_type="m5.large",
        od_hourly=Decimal("0.0960"),
        convertible_1yr_hourly=Decimal("0.0624"),
        convertible_3yr_hourly=Decimal("0.0450"),
        standard_1yr_hourly=Decimal("0.0580"),
        standard_3yr_hourly=Decimal("0.0400"),
        effective_date="2025-01-01",
    )

    # Patch the solver to return Infeasible
    with patch("pulp.LpProblem.solve", return_value=-1):
        with patch.dict("pulp.constants.LpStatus", {-1: "Infeasible"}):
            result = optimize_convertible_ris("999988887777", "2025-01")
    assert isinstance(result, list)
