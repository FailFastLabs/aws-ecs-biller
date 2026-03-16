from decimal import Decimal
from datetime import datetime, timezone as dt_tz
import pytest
from apps.splitting.models import SplittingRule, SplitResult
from apps.splitting.services.verifier import verify_split_invariant, SplitInvariantViolationError
from tests.factories.splitting import SplittingRuleFactory


@pytest.mark.django_db
def test_verify_passes_when_splits_sum_correctly():
    rule = SplittingRuleFactory(weight_strategy="custom_weight")
    hour = datetime(2025, 1, 5, 10, 0, tzinfo=dt_tz.utc)
    original = Decimal("100.0000000000")
    for tenant, amt in [("backend", "40.0000000000"), ("frontend", "35.0000000000"), ("data", "25.0000000000")]:
        SplitResult.objects.create(
            splitting_rule=rule, billing_period="2025-01",
            hour=hour, region="us-east-1", usage_type="BoxUsage",
            tenant_tag_value=tenant, original_cost=original,
            allocated_cost=Decimal(amt), allocation_weight=Decimal("0.33000000"),
        )
    verify_split_invariant(rule, "2025-01")


@pytest.mark.django_db
def test_verify_raises_when_splits_do_not_sum():
    rule = SplittingRuleFactory(weight_strategy="custom_weight")
    hour = datetime(2025, 1, 5, 11, 0, tzinfo=dt_tz.utc)
    original = Decimal("100.0000000000")
    # Allocate only 60 instead of 100 — diff = 40 > tolerance
    SplitResult.objects.create(
        splitting_rule=rule, billing_period="2025-01",
        hour=hour, region="us-east-1", usage_type="BoxUsage",
        tenant_tag_value="backend", original_cost=original,
        allocated_cost=Decimal("60.0000000000"), allocation_weight=Decimal("0.60000000"),
    )
    with pytest.raises(SplitInvariantViolationError):
        verify_split_invariant(rule, "2025-01")


@pytest.mark.django_db
def test_verify_empty_results_passes():
    rule = SplittingRuleFactory(weight_strategy="custom_weight")
    # No SplitResult rows — groups is empty, should not raise
    verify_split_invariant(rule, "2025-02")


@pytest.mark.django_db
def test_verify_december_billing_period():
    """December edge case: next month is January of next year."""
    rule = SplittingRuleFactory(weight_strategy="custom_weight")
    hour = datetime(2025, 12, 15, 10, 0, tzinfo=dt_tz.utc)
    original = Decimal("50.0000000000")
    SplitResult.objects.create(
        splitting_rule=rule, billing_period="2025-12",
        hour=hour, region="us-east-1", usage_type="BoxUsage",
        tenant_tag_value="only", original_cost=original,
        allocated_cost=original, allocation_weight=Decimal("1.00000000"),
    )
    verify_split_invariant(rule, "2025-12")


@pytest.mark.django_db
def test_verify_tolerance_boundary():
    """Difference exactly at tolerance (1e-8) should pass."""
    rule = SplittingRuleFactory(weight_strategy="custom_weight")
    hour = datetime(2025, 1, 10, 8, 0, tzinfo=dt_tz.utc)
    original = Decimal("100.0000000000")
    # Allocate 99.9999999900 → diff = 1e-8, at boundary → passes
    SplitResult.objects.create(
        splitting_rule=rule, billing_period="2025-01",
        hour=hour, region="us-east-1", usage_type="BoxUsage",
        tenant_tag_value="only", original_cost=original,
        allocated_cost=Decimal("99.9999999900"), allocation_weight=Decimal("1.00000000"),
    )
    verify_split_invariant(rule, "2025-01")
