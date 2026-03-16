import factory
from apps.reservations.models import ReservedInstance, SavingsPlan
from tests.factories.accounts import AwsAccountFactory


class ReservedInstanceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ReservedInstance
        django_get_or_create = ("reservation_id",)

    account = factory.SubFactory(AwsAccountFactory)
    reservation_id = factory.Sequence(lambda n: f"ri-test-{n:012x}")
    reservation_arn = factory.LazyAttribute(lambda o: f"arn:aws:ec2:us-east-1:123456789012:reserved-instances/{o.reservation_id}")
    instance_type = "m5.large"
    instance_family = "m5"
    normalized_units = 40.0
    region = "us-east-1"
    tenancy = "default"
    platform = "Linux/UNIX"
    offering_class = "convertible"
    offering_type = "No Upfront"
    instance_count = 10
    start_date = "2024-01-01"
    end_date = "2027-01-01"
    fixed_price = 0.0
    recurring_hourly_cost = 0.6240
    scope = "Region"
    state = "active"
