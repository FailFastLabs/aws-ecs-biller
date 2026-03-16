import os
import pytest
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.test")

from rest_framework.test import APIClient


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def aws_account(db):
    from apps.accounts.models import AwsAccount
    account, _ = AwsAccount.objects.get_or_create(
        account_id="123456789012",
        defaults={"account_name": "acme-prod", "is_payer": True},
    )
    return account


@pytest.fixture
def mock_aws_credentials(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")


@pytest.fixture
def loaded_line_items(db, aws_account):
    from pathlib import Path
    from apps.etl.pipeline.reader import read_cur_file
    from apps.etl.pipeline.normalizer import normalize_schema
    from apps.etl.pipeline.deduplicator import deduplicate
    from apps.etl.pipeline.validator import validate
    from apps.etl.pipeline.loader import bulk_load
    from apps.etl.pipeline.aggregator import refresh_daily_aggregates, refresh_hourly_aggregates

    path = Path("tests/fixtures/cur_sample_2025_01.csv")
    if not path.exists():
        return
    for chunk in read_cur_file(path):
        df = normalize_schema(chunk)
        df = deduplicate(df, set())
        valid, _ = validate(df)
        bulk_load(valid)
    refresh_daily_aggregates("2025-01")
    refresh_hourly_aggregates("2025-01")
