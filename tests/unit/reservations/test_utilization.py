import pytest
from django.utils import timezone
from tests.factories.costs import LineItemFactory


@pytest.mark.django_db
def test_utilization_empty_when_no_rifee():
    from apps.reservations.services.utilization import compute_ri_utilization
    df = compute_ri_utilization("123456789012", "2025-01")
    assert df.empty


@pytest.mark.django_db
def test_utilization_basic():
    from apps.reservations.services.utilization import compute_ri_utilization
    arn = "arn:aws:ec2:us-east-1:123456789012:reserved-instances/ri-abc"
    # RIFee row
    LineItemFactory(
        billing_period="2025-01",
        linked_account_id="123456789012",
        line_item_type="RIFee",
        reservation_arn=arn,
        instance_type="m5.large",
        region="us-east-1",
        offering_class="standard",
        normalized_usage_amount=744.0,
        unblended_cost=100.0,
        reservation_unused_quantity=24.0,
        reservation_unused_recurring_fee=5.0,
    )
    # DiscountedUsage row
    LineItemFactory(
        billing_period="2025-01",
        linked_account_id="123456789012",
        line_item_type="DiscountedUsage",
        reservation_arn=arn,
        normalized_usage_amount=720.0,
    )
    df = compute_ri_utilization("123456789012", "2025-01")
    assert not df.empty
    assert "utilization_pct" in df.columns
    row = df.iloc[0]
    assert float(row["purchased_units"]) == pytest.approx(744.0)
    assert float(row["utilization_pct"]) == pytest.approx(720.0 / 744.0, rel=1e-3)


@pytest.mark.django_db
def test_utilization_no_discounted_usage():
    from apps.reservations.services.utilization import compute_ri_utilization
    arn = "arn:aws:ec2:us-east-1:123456789012:reserved-instances/ri-xyz"
    LineItemFactory(
        billing_period="2025-01",
        linked_account_id="123456789012",
        line_item_type="RIFee",
        reservation_arn=arn,
        instance_type="c5.xlarge",
        region="us-east-1",
        offering_class="convertible",
        normalized_usage_amount=744.0,
        unblended_cost=80.0,
        reservation_unused_quantity=744.0,
        reservation_unused_recurring_fee=80.0,
    )
    df = compute_ri_utilization("123456789012", "2025-01")
    assert not df.empty
    assert float(df.iloc[0]["utilization_pct"]) == pytest.approx(0.0)
