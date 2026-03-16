import pytest
from decimal import Decimal


@pytest.mark.django_db
def test_split_rule_creation(api_client, db):
    resp = api_client.post("/api/v1/splitting/rules/", data={
        "name": "Test EKS Split",
        "service": "AmazonEKS",
        "region": "us-east-1",
        "split_by_tag_key": "user:team",
        "weight_strategy": "custom_weight",
        "custom_weights": {"backend": 0.5, "frontend": 0.5},
        "active": True,
    }, format="json")
    assert resp.status_code == 201


@pytest.mark.django_db
def test_distribute_always_sums_to_total():
    from apps.splitting.services.splitter import _distribute_decimal
    for total_cents in [1, 100, 333, 1000000]:
        total = Decimal(str(total_cents)) / 100
        weights = {"a": Decimal("0.4"), "b": Decimal("0.35"), "c": Decimal("0.25")}
        result = _distribute_decimal(total, weights)
        assert sum(result.values()) == total
