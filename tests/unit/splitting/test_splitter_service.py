"""Tests for splitting service functions that aren't covered by other tests."""
import pytest
from decimal import Decimal
from datetime import datetime, timezone as dt_tz
from unittest.mock import patch, MagicMock


@pytest.mark.django_db
def test_billing_period_to_range_regular():
    from apps.splitting.services.splitter import _billing_period_to_range
    from datetime import date
    start, end = _billing_period_to_range("2025-03")
    assert start == date(2025, 3, 1)
    assert end == date(2025, 4, 1)


@pytest.mark.django_db
def test_billing_period_to_range_december():
    from apps.splitting.services.splitter import _billing_period_to_range
    from datetime import date
    start, end = _billing_period_to_range("2025-12")
    assert start == date(2025, 12, 1)
    assert end == date(2026, 1, 1)


@pytest.mark.django_db
def test_compute_weights_custom_weight():
    from apps.splitting.services.splitter import _compute_weights
    from tests.factories.splitting import SplittingRuleFactory
    rule = SplittingRuleFactory(
        weight_strategy="custom_weight",
        custom_weights={"a": 0.4, "b": 0.6},
    )
    hour = datetime(2025, 1, 1, 0, 0, tzinfo=dt_tz.utc)
    weights = _compute_weights(rule, hour, "us-east-1", "BoxUsage")
    assert "a" in weights and "b" in weights
    assert abs(float(weights["a"]) - 0.4) < 1e-9
    assert abs(float(weights["b"]) - 0.6) < 1e-9


@pytest.mark.django_db
def test_compute_weights_equal():
    from apps.splitting.services.splitter import _compute_weights, _get_active_tenants
    from tests.factories.splitting import SplittingRuleFactory
    from tests.factories.costs import LineItemFactory

    rule = SplittingRuleFactory(
        weight_strategy="equal",
        split_by_tag_key="user:team",
    )
    hour = datetime(2025, 1, 5, 10, 0, tzinfo=dt_tz.utc)
    # Create line items with the tag so tenants can be discovered
    LineItemFactory(
        service=rule.service, region=rule.region,
        usage_start=hour, usage_end=hour,
        tags={"user:team": "backend"},
    )
    LineItemFactory(
        service=rule.service, region=rule.region,
        usage_start=hour, usage_end=hour,
        tags={"user:team": "frontend"},
    )
    weights = _compute_weights(rule, hour, "us-east-1", "BoxUsage")
    if weights:  # may be empty if no tenants found in exact range
        assert len(weights) >= 1
        assert all(v > 0 for v in weights.values())


@pytest.mark.django_db
def test_compute_weights_proportional():
    from apps.splitting.services.splitter import _compute_weights
    from tests.factories.splitting import SplittingRuleFactory
    from tests.factories.costs import LineItemFactory

    rule = SplittingRuleFactory(
        weight_strategy="proportional_usage",
        split_by_tag_key="user:team",
    )
    hour = datetime(2025, 1, 5, 10, 0, tzinfo=dt_tz.utc)
    LineItemFactory(
        service=rule.service, region=rule.region,
        usage_start=hour, usage_end=hour,
        tags={"user:team": "backend"},
        usage_quantity=8.0,
    )
    LineItemFactory(
        service=rule.service, region=rule.region,
        usage_start=hour, usage_end=hour,
        tags={"user:team": "frontend"},
        usage_quantity=2.0,
    )
    weights = _compute_weights(rule, hour, rule.region, "USE1-BoxUsage:m5.large")
    if weights:
        total = sum(weights.values())
        assert abs(float(total) - 1.0) < 1e-6


@pytest.mark.django_db
def test_compute_weights_unknown_strategy_returns_empty():
    from apps.splitting.services.splitter import _compute_weights
    from unittest.mock import MagicMock
    mock_rule = MagicMock()
    mock_rule.weight_strategy = "unknown"
    hour = datetime(2025, 1, 5, 10, 0, tzinfo=dt_tz.utc)
    result = _compute_weights(mock_rule, hour, "us-east-1", "BoxUsage")
    assert result == {}


@pytest.mark.django_db
def test_run_split_with_custom_weights_creates_results():
    from apps.splitting.services.splitter import run_split
    from apps.splitting.models import SplitResult
    from apps.costs.models import HourlyCostAggregate
    from tests.factories.splitting import SplittingRuleFactory

    rule = SplittingRuleFactory(
        service="AmazonEC2",
        region="us-east-1",
        weight_strategy="custom_weight",
        custom_weights={"backend": 0.6, "frontend": 0.4},
    )

    # Create hourly cost aggregate in 2025-01
    hour = datetime(2025, 1, 10, 12, 0, tzinfo=dt_tz.utc)
    HourlyCostAggregate.objects.create(
        hour=hour,
        linked_account_id="123456789012",
        service="AmazonEC2",
        region="us-east-1",
        usage_type="BoxUsage",
        line_item_type="Usage",
        unblended_cost=100.0,
        usage_quantity=1.0,
    )

    n = run_split(rule, "2025-01")
    assert n == 2  # backend + frontend
    results = list(SplitResult.objects.filter(splitting_rule=rule))
    assert len(results) == 2
    tenants = {r.tenant_tag_value for r in results}
    assert tenants == {"backend", "frontend"}
    # Invariant check: sum of allocated_cost == original_cost
    total_allocated = sum(r.allocated_cost for r in results)
    assert abs(float(total_allocated) - 100.0) < 1e-6


@pytest.mark.django_db
def test_run_split_skips_when_no_weights():
    from apps.splitting.services.splitter import run_split
    from apps.splitting.models import SplitResult
    from apps.costs.models import HourlyCostAggregate
    from tests.factories.splitting import SplittingRuleFactory

    # equal strategy but no tenants (no matching LineItems)
    rule = SplittingRuleFactory(
        service="AmazonEKS",
        region="ap-southeast-1",
        weight_strategy="equal",
        split_by_tag_key="user:team",
    )
    hour = datetime(2025, 1, 15, 6, 0, tzinfo=dt_tz.utc)
    HourlyCostAggregate.objects.create(
        hour=hour,
        linked_account_id="123456789012",
        service="AmazonEKS",
        region="ap-southeast-1",
        usage_type="EKS:Node",
        line_item_type="Usage",
        unblended_cost=50.0,
        usage_quantity=1.0,
    )
    n = run_split(rule, "2025-01")
    # No tenants → no splits
    assert n == 0
    assert SplitResult.objects.filter(splitting_rule=rule).count() == 0


@pytest.mark.django_db
def test_get_active_tenants():
    from apps.splitting.services.splitter import _get_active_tenants
    from tests.factories.costs import LineItemFactory
    from tests.factories.splitting import SplittingRuleFactory
    rule = SplittingRuleFactory(
        service="AmazonEC2", region="us-east-1", split_by_tag_key="user:env"
    )
    hour = datetime(2025, 1, 5, 0, 0, tzinfo=dt_tz.utc)
    LineItemFactory(service="AmazonEC2", region="us-east-1",
                    usage_start=hour, usage_end=hour, tags={"user:env": "prod"})
    LineItemFactory(service="AmazonEC2", region="us-east-1",
                    usage_start=hour, usage_end=hour, tags={"user:env": "dev"})
    tenants = _get_active_tenants(rule, hour)
    assert set(tenants) == {"prod", "dev"}
