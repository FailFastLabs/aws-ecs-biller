from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Load CUR fixture CSV directly into LineItem (bypasses S3 download)"

    def handle(self, *args, **options):
        from apps.etl.pipeline.reader import read_cur_file
        from apps.etl.pipeline.normalizer import normalize_schema
        from apps.etl.pipeline.deduplicator import deduplicate
        from apps.etl.pipeline.validator import validate
        from apps.etl.pipeline.loader import bulk_load
        from apps.etl.pipeline.aggregator import refresh_daily_aggregates, refresh_hourly_aggregates
        from apps.splitting.models import SplittingRule

        path = Path(settings.BASE_DIR) / "tests/fixtures/cur_sample_2025_01.csv"
        total = 0
        for chunk in read_cur_file(path):
            df = normalize_schema(chunk)
            df = deduplicate(df, existing_ids=set())
            valid, rejected = validate(df)
            n = bulk_load(valid)
            total += n
            self.stdout.write(f"Loaded {n} rows (rejected {len(rejected)})")

        refresh_daily_aggregates("2025-01")
        refresh_hourly_aggregates("2025-01")

        # Seed EKS split rule
        SplittingRule.objects.get_or_create(
            name="EKS Cluster Cost Split",
            defaults={
                "service": "AmazonEKS",
                "region": "us-east-1",
                "split_by_tag_key": "user:team",
                "weight_strategy": "custom_weight",
                "custom_weights": {"backend": 0.40, "frontend": 0.35, "data": 0.25},
                "active": True,
            },
        )

        self.stdout.write(self.style.SUCCESS(f"Done. Total rows: {total}"))
