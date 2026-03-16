from django.core.management.base import BaseCommand


RI_FIXTURES = [
    {
        "reservation_id": "ri-0a1b2c3d4e5f6789a",
        "reservation_arn": "arn:aws:ec2:us-east-1:123456789012:reserved-instances/ri-0a1b2c3d4e5f6789a",
        "instance_type": "m5.large", "instance_family": "m5",
        "normalized_units": 40.0, "region": "us-east-1",
        "tenancy": "default", "platform": "Linux/UNIX",
        "offering_class": "standard", "offering_type": "No Upfront",
        "instance_count": 10, "start_date": "2024-01-01", "end_date": "2027-01-01",
        "fixed_price": 0.0, "recurring_hourly_cost": 0.6240,
        "scope": "Region", "state": "active",
    },
    {
        "reservation_id": "ri-0b2c3d4e5f6789ab",
        "reservation_arn": "arn:aws:ec2:us-east-1:123456789012:reserved-instances/ri-0b2c3d4e5f6789ab",
        "instance_type": "c5.xlarge", "instance_family": "c5",
        "normalized_units": 40.0, "region": "us-east-1",
        "tenancy": "default", "platform": "Linux/UNIX",
        "offering_class": "convertible", "offering_type": "No Upfront",
        "instance_count": 5, "start_date": "2024-06-01", "end_date": "2027-06-01",
        "fixed_price": 0.0, "recurring_hourly_cost": 0.4675,
        "scope": "Region", "state": "active",
    },
    {
        "reservation_id": "ri-0c3d4e5f6789abc",
        "reservation_arn": "arn:aws:ec2:us-west-2:123456789012:reserved-instances/ri-0c3d4e5f6789abc",
        "instance_type": "m5.2xlarge", "instance_family": "m5",
        "normalized_units": 48.0, "region": "us-west-2",
        "tenancy": "default", "platform": "Linux/UNIX",
        "offering_class": "convertible", "offering_type": "No Upfront",
        "instance_count": 3, "start_date": "2023-12-01", "end_date": "2026-12-01",
        "fixed_price": 0.0, "recurring_hourly_cost": 0.7488,
        "scope": "Region", "state": "active",
    },
    {
        "reservation_id": "ri-0d4e5f6789abcd",
        "reservation_arn": "arn:aws:ec2:eu-west-1:123456789012:reserved-instances/ri-0d4e5f6789abcd",
        "instance_type": "r5.large", "instance_family": "r5",
        "normalized_units": 16.0, "region": "eu-west-1",
        "tenancy": "default", "platform": "Linux/UNIX",
        "offering_class": "standard", "offering_type": "No Upfront",
        "instance_count": 4, "start_date": "2024-03-01", "end_date": "2027-03-01",
        "fixed_price": 0.0, "recurring_hourly_cost": 0.3276,
        "scope": "Region", "state": "active",
    },
]

SP_FIXTURES = [
    {
        "savings_plan_id": "sp-abc123def456",
        "savings_plan_arn": "arn:aws:savingsplans::123456789012:savingsplan/sp-abc123def456",
        "plan_type": "ComputeSavingsPlan",
        "commitment_hourly": 2.50,
        "start_date": "2024-07-01", "end_date": "2025-07-01",
        "state": "active",
    },
]


class Command(BaseCommand):
    help = "Seed ReservedInstance and SavingsPlan records from fixture data"

    def handle(self, *args, **options):
        from apps.accounts.models import AwsAccount
        from apps.reservations.models import ReservedInstance, SavingsPlan

        try:
            account = AwsAccount.objects.get(account_id="123456789012")
        except AwsAccount.DoesNotExist:
            account = AwsAccount.objects.create(
                account_id="123456789012",
                account_name="acme-prod",
                is_payer=True,
            )

        for ri in RI_FIXTURES:
            ReservedInstance.objects.update_or_create(
                reservation_id=ri["reservation_id"],
                defaults={"account": account, **{k: v for k, v in ri.items() if k != "reservation_id"}},
            )
        self.stdout.write(f"Seeded {len(RI_FIXTURES)} reserved instances")

        for sp in SP_FIXTURES:
            SavingsPlan.objects.update_or_create(
                savings_plan_id=sp["savings_plan_id"],
                defaults={"account": account, **{k: v for k, v in sp.items() if k != "savings_plan_id"}},
            )
        self.stdout.write(f"Seeded {len(SP_FIXTURES)} savings plans")
        self.stdout.write(self.style.SUCCESS("Done"))
