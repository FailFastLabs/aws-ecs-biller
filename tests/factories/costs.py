import factory
from django.utils import timezone
from apps.costs.models import LineItem, DailyCostAggregate, HourlyCostAggregate


class LineItemFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = LineItem

    line_item_id = factory.Sequence(lambda n: f"li-test-{n:06d}")
    billing_period = "2025-01"
    usage_start = factory.LazyFunction(lambda: timezone.now())
    service = "AmazonEC2"
    linked_account_id = "123456789012"
    region = "us-east-1"
    usage_type = "USE1-BoxUsage:m5.large"
    line_item_type = "Usage"
    unblended_cost = factory.LazyAttribute(lambda o: 0.096)
    usage_quantity = 1.0
    tags = factory.LazyFunction(dict)


class DailyAggFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = DailyCostAggregate
        django_get_or_create = ("date", "linked_account_id", "service", "region", "usage_type", "line_item_type")

    date = factory.LazyFunction(lambda: __import__("datetime").date(2025, 1, 1))
    linked_account_id = "123456789012"
    service = "AmazonEC2"
    region = "us-east-1"
    usage_type = "USE1-BoxUsage:m5.large"
    line_item_type = "Usage"
    unblended_cost = 100.0
    usage_quantity = 24.0


class HourlyAggFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = HourlyCostAggregate
        django_get_or_create = ("hour", "linked_account_id", "service", "region", "usage_type", "line_item_type")

    hour = factory.LazyFunction(lambda: __import__("django.utils.timezone", fromlist=["now"]).now().replace(minute=0, second=0, microsecond=0))
    linked_account_id = "123456789012"
    service = "AmazonEC2"
    region = "us-east-1"
    usage_type = "USE1-BoxUsage:m5.large"
    line_item_type = "Usage"
    unblended_cost = 4.0
    usage_quantity = 1.0
