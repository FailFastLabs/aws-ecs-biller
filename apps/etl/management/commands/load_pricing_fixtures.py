from pathlib import Path
import pandas as pd
from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Load EDP discounts, spot prices, instance pricing from fixture CSVs"

    def handle(self, *args, **options):
        from apps.costs.models import EdpDiscount, SpotPriceHistory, InstancePricing

        base = Path(settings.BASE_DIR) / "tests/fixtures"

        # EDP Discounts
        edp_df = pd.read_csv(base / "edp_discounts.csv")
        for _, row in edp_df.iterrows():
            EdpDiscount.objects.update_or_create(
                service=row["service"],
                region=row["region"],
                effective_date="2025-01-01",
                defaults={"discount_pct": row["discount_pct"]},
            )
        self.stdout.write(f"Loaded {len(edp_df)} EDP discounts")

        # Spot prices
        spot_df = pd.read_csv(base / "spot_price_history.csv")
        spot_df["timestamp"] = pd.to_datetime(spot_df["timestamp"], utc=True)
        objs = [
            SpotPriceHistory(
                region=r["region"],
                instance_type=r["instance_type"],
                availability_zone=r["availability_zone"],
                timestamp=r["timestamp"],
                spot_price=r["spot_price_usd"],
            )
            for _, r in spot_df.iterrows()
        ]
        SpotPriceHistory.objects.bulk_create(objs, ignore_conflicts=True, batch_size=5000)
        self.stdout.write(f"Loaded {len(objs)} spot price records")

        # Instance pricing
        price_df = pd.read_csv(base / "instance_pricing.csv")
        for _, row in price_df.iterrows():
            InstancePricing.objects.update_or_create(
                region=row["region"],
                instance_type=row["instance_type"],
                effective_date="2025-01-01",
                defaults={
                    "od_hourly": row["od_hourly"],
                    "convertible_1yr_hourly": row["convertible_1yr_hourly"],
                    "convertible_3yr_hourly": row["convertible_3yr_hourly"],
                    "standard_1yr_hourly": row["standard_1yr_hourly"],
                    "standard_3yr_hourly": row["standard_3yr_hourly"],
                },
            )
        self.stdout.write(f"Loaded {len(price_df)} instance pricing rows")
