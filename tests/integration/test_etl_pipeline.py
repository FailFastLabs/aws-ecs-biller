import pytest


@pytest.mark.django_db
def test_full_pipeline_loads_fixture(loaded_line_items):
    from apps.costs.models import LineItem
    assert LineItem.objects.count() > 1000


@pytest.mark.django_db
def test_aggregates_created(loaded_line_items):
    from apps.costs.models import DailyCostAggregate, HourlyCostAggregate
    assert DailyCostAggregate.objects.filter(date__year=2025, date__month=1).count() > 0
    assert HourlyCostAggregate.objects.filter(hour__year=2025, hour__month=1).count() > 0


@pytest.mark.django_db
def test_aggregate_sum_matches_line_items(loaded_line_items):
    from django.db.models import Sum
    from apps.costs.models import LineItem, DailyCostAggregate
    li_sum = float(
        LineItem.objects.filter(billing_period="2025-01")
        .aggregate(Sum("unblended_cost"))["unblended_cost__sum"] or 0
    )
    da_sum = float(
        DailyCostAggregate.objects.filter(date__year=2025, date__month=1)
        .aggregate(Sum("unblended_cost"))["unblended_cost__sum"] or 0
    )
    assert li_sum > 0
    assert abs(li_sum - da_sum) < 0.01


@pytest.mark.django_db
def test_line_items_have_tags(loaded_line_items):
    from apps.costs.models import LineItem
    with_tags = LineItem.objects.exclude(tags={}).count()
    assert with_tags > 0


@pytest.mark.django_db
def test_ec2_line_items_present(loaded_line_items):
    from apps.costs.models import LineItem
    ec2_count = LineItem.objects.filter(service="AmazonEC2").count()
    assert ec2_count > 100
