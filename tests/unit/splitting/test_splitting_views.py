"""Tests for splitting API views."""
import pytest
from datetime import datetime, timezone as dt_tz
from decimal import Decimal
from unittest.mock import patch
from tests.factories.splitting import SplittingRuleFactory
from apps.splitting.models import SplitResult


@pytest.mark.django_db
def test_splitting_rule_list(api_client):
    SplittingRuleFactory.create_batch(3)
    resp = api_client.get("/api/v1/splitting/rules/")
    assert resp.status_code == 200
    assert resp.json()["count"] >= 3


@pytest.mark.django_db
def test_splitting_rule_create(api_client):
    resp = api_client.post("/api/v1/splitting/rules/", data={
        "name": "EKS Split",
        "service": "AmazonEKS",
        "region": "us-east-1",
        "split_by_tag_key": "user:team",
        "weight_strategy": "custom_weight",
        "custom_weights": {"a": 0.5, "b": 0.5},
        "active": True,
    }, format="json")
    assert resp.status_code == 201


@pytest.mark.django_db
def test_splitting_rule_detail(api_client):
    rule = SplittingRuleFactory()
    resp = api_client.get(f"/api/v1/splitting/rules/{rule.pk}/")
    assert resp.status_code == 200
    assert resp.json()["id"] == rule.pk


@pytest.mark.django_db
def test_run_split_view_success(api_client):
    from apps.costs.models import HourlyCostAggregate
    rule = SplittingRuleFactory(
        service="AmazonEC2",
        region="us-east-1",
        weight_strategy="custom_weight",
        custom_weights={"a": 0.5, "b": 0.5},
    )
    hour = datetime(2025, 1, 10, 12, 0, tzinfo=dt_tz.utc)
    HourlyCostAggregate.objects.create(
        hour=hour, linked_account_id="123456789012",
        service="AmazonEC2", region="us-east-1",
        usage_type="BoxUsage", line_item_type="Usage",
        unblended_cost=100.0, usage_quantity=1.0,
    )
    resp = api_client.post(
        f"/api/v1/splitting/rules/{rule.pk}/run/",
        data={"billing_period": "2025-01"},
        format="json",
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["created"] == 2
    assert data["status"] == "ok"


@pytest.mark.django_db
def test_run_split_view_invariant_violation(api_client):
    from unittest.mock import patch
    rule = SplittingRuleFactory()
    from apps.splitting.services.verifier import SplitInvariantViolationError
    with patch("apps.splitting.services.splitter.run_split",
               side_effect=SplitInvariantViolationError("violation!")):
        resp = api_client.post(
            f"/api/v1/splitting/rules/{rule.pk}/run/",
            data={"billing_period": "2025-01"},
            format="json",
        )
    assert resp.status_code == 500


@pytest.mark.django_db
def test_split_result_list_view(api_client):
    rule = SplittingRuleFactory()
    hour = datetime(2025, 1, 5, 0, 0, tzinfo=dt_tz.utc)
    SplitResult.objects.create(
        splitting_rule=rule, billing_period="2025-01",
        hour=hour, region="us-east-1", usage_type="BoxUsage",
        tenant_tag_value="a", original_cost="100", allocated_cost="50",
        allocation_weight="0.50000000",
    )
    resp = api_client.get(f"/api/v1/splitting/results/?rule_id={rule.pk}&billing_period=2025-01")
    assert resp.status_code == 200
    assert resp.json()["count"] >= 1


@pytest.mark.django_db
def test_verify_split_view_ok(api_client):
    rule = SplittingRuleFactory()
    resp = api_client.get(f"/api/v1/splitting/results/verify/?rule_id={rule.pk}&billing_period=2025-01")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.django_db
def test_verify_split_view_violation(api_client):
    rule = SplittingRuleFactory()
    from apps.splitting.services.verifier import SplitInvariantViolationError
    with patch("apps.splitting.services.verifier.verify_split_invariant",
               side_effect=SplitInvariantViolationError("bad!")):
        resp = api_client.get(
            f"/api/v1/splitting/results/verify/?rule_id={rule.pk}&billing_period=2025-01"
        )
    assert resp.status_code == 400
