# PART 9 — Full Test Coverage Pass

## Objective
Write unit and integration tests to reach ≥ 80% coverage across all apps.
All tests use the fake CUR fixture from Part 0.

---

## Test Structure

```
tests/
├── conftest.py
├── factories/
│   ├── accounts.py
│   ├── costs.py
│   ├── reservations.py
│   └── splitting.py
├── unit/
│   ├── etl/
│   │   ├── test_reader.py
│   │   ├── test_normalizer.py
│   │   ├── test_deduplicator.py
│   │   └── test_validator.py
│   ├── reservations/
│   │   ├── test_coverage.py
│   │   ├── test_utilization.py
│   │   ├── test_sp_counterfactual.py
│   │   └── test_convertible_optimizer.py
│   ├── forecasting/
│   │   └── test_chronos_forecaster.py
│   ├── anomalies/
│   │   ├── test_zscore_detector.py
│   │   ├── test_chronos_residual_detector.py
│   │   └── test_ensemble.py
│   └── splitting/
│       ├── test_splitter.py
│       └── test_invariant.py
├── integration/
│   ├── test_etl_pipeline.py
│   ├── test_ingestion_tasks.py
│   ├── test_api_costs.py
│   ├── test_api_reservations.py
│   ├── test_api_forecasting.py
│   └── test_api_anomalies.py
└── fixtures/
    ├── cur_sample_2025_01.csv      (from Part 0)
    ├── edp_discounts.csv           (from Part 0)
    ├── spot_price_history.csv      (from Part 0)
    ├── instance_pricing.csv        (from Part 0)
    └── cur_manifest_2025_01.json   (from Part 0)
```

---

## `tests/conftest.py`

```python
import pytest
from django.test import Client
from rest_framework.test import APIClient

@pytest.fixture
def api_client():
    return APIClient()

@pytest.fixture
def aws_account(db):
    from tests.factories.accounts import AwsAccountFactory
    return AwsAccountFactory(account_id='123456789012', account_name='acme-prod', is_payer=True)

@pytest.fixture
def mock_s3(aws_credentials):
    """moto S3 mock with sample CUR file uploaded."""
    import boto3
    from moto import mock_aws
    with mock_aws():
        s3 = boto3.client('s3', region_name='us-east-1')
        s3.create_bucket(Bucket='test-cur-bucket')
        s3.upload_file(
            'tests/fixtures/cur_sample_2025_01.csv',
            'test-cur-bucket',
            'acme-cur/20250101-20250201/acme-cur-1.csv'
        )
        yield s3

@pytest.fixture
def loaded_line_items(db, aws_account):
    """Load fixture CSV into LineItem table. Reused across integration tests."""
    from pathlib import Path
    from apps.etl.pipeline.reader import read_cur_file
    from apps.etl.pipeline.normalizer import normalize_schema
    from apps.etl.pipeline.deduplicator import deduplicate
    from apps.etl.pipeline.validator import validate
    from apps.etl.pipeline.loader import bulk_load
    from apps.etl.pipeline.aggregator import refresh_daily_aggregates, refresh_hourly_aggregates

    path = Path('tests/fixtures/cur_sample_2025_01.csv')
    for chunk in read_cur_file(path):
        df = normalize_schema(chunk)
        df = deduplicate(df, set())
        valid, _ = validate(df)
        bulk_load(valid)
    refresh_daily_aggregates('2025-01')
    refresh_hourly_aggregates('2025-01')
```

---

## Unit Tests: ETL

### `tests/unit/etl/test_normalizer.py`

```python
def test_normalize_renames_columns():
    raw = pd.DataFrame({
        'identity_line_item_id':      ['li-001'],
        'line_item_unblended_cost':   ['1.234567890'],
        'line_item_usage_start_date': ['2025-01-01T00:00:00Z'],
        'bill_billing_period_start_date': ['2025-01-01T00:00:00Z'],
        'line_item_usage_account_id': ['123456789012'],
        'line_item_product_code':     ['AmazonEC2'],
        'line_item_usage_amount':     ['1.0'],
        'line_item_blended_cost':     ['1.234567890'],
    })
    result = normalize_schema(raw)
    assert 'line_item_id' in result.columns
    assert 'unblended_cost' in result.columns
    assert 'usage_start' in result.columns
    assert pd.api.types.is_datetime64_any_dtype(result['usage_start'])
    assert result['billing_period'].iloc[0] == '2025-01'

def test_normalize_fills_zero_for_missing_cost():
    raw = pd.DataFrame({
        'identity_line_item_id': ['li-002'],
        'line_item_unblended_cost': [None],
        # ... other required cols
    })
    result = normalize_schema(raw)
    assert result['unblended_cost'].iloc[0] == 0.0

def test_normalize_parses_tags_json():
    raw = pd.DataFrame({'resource_tags': ['{"user:team":"backend","user:env":"prod"}']})
    result = normalize_schema(raw)
    assert result['tags'].iloc[0] == {'user:team': 'backend', 'user:env': 'prod'}

def test_normalize_handles_malformed_tags():
    raw = pd.DataFrame({'resource_tags': ['not-valid-json']})
    result = normalize_schema(raw)
    assert result['tags'].iloc[0] == {}
```

### `tests/unit/etl/test_deduplicator.py`

```python
def test_dedup_removes_existing_ids():
    df = pd.DataFrame({'line_item_id': ['a', 'b', 'c'], 'billing_period': ['2025-01'] * 3})
    result = deduplicate(df, existing_ids={'b'})
    assert set(result['line_item_id']) == {'a', 'c'}

def test_dedup_removes_within_file_duplicates():
    df = pd.DataFrame({'line_item_id': ['a', 'a', 'b'], 'billing_period': ['2025-01'] * 3})
    result = deduplicate(df, existing_ids=set())
    assert len(result) == 2
```

### `tests/unit/etl/test_validator.py`

```python
def test_validate_rejects_null_required_field():
    df = pd.DataFrame({
        'line_item_id': [None], 'billing_period': ['2025-01'],
        'usage_start': ['2025-01-01'], 'service': ['AmazonEC2'],
        'linked_account_id': ['123456789012'], 'unblended_cost': [1.0],
        'line_item_type': ['Usage'],
    })
    valid, rejected = validate(df)
    assert len(valid) == 0
    assert len(rejected) == 1

def test_validate_rejects_negative_non_credit():
    df = pd.DataFrame({
        'line_item_id': ['li-001'], 'billing_period': ['2025-01'],
        'usage_start': ['2025-01-01'], 'service': ['AmazonEC2'],
        'linked_account_id': ['123456789012'], 'unblended_cost': [-5.0],
        'line_item_type': ['Usage'],
    })
    valid, rejected = validate(df)
    assert len(valid) == 0

def test_validate_allows_negative_credit():
    df = pd.DataFrame({
        'line_item_id': ['li-002'], 'billing_period': ['2025-01'],
        'usage_start': ['2025-01-01'], 'service': ['AmazonEC2'],
        'linked_account_id': ['123456789012'], 'unblended_cost': [-100.0],
        'line_item_type': ['Credit'],
    })
    valid, rejected = validate(df)
    assert len(valid) == 1
```

---

## Unit Tests: Splitting (most critical — mathematical correctness)

### `tests/unit/splitting/test_invariant.py`

```python
from decimal import Decimal
import pytest
from apps.splitting.services.splitter import _distribute_decimal

@pytest.mark.parametrize("n_tenants,total_cost,weights", [
    # Equal split, round number
    (3, Decimal('100.00'), {'a': Decimal('1')/3, 'b': Decimal('1')/3, 'c': Decimal('1')/3}),
    # Very small total, many tenants
    (7, Decimal('0.01'), {str(i): Decimal('1')/7 for i in range(7)}),
    # Repeating decimal
    (2, Decimal('333.333333333'), {'x': Decimal('1')/3, 'y': Decimal('2')/3}),
    # Single tenant: must get everything
    (1, Decimal('500.00'), {'only': Decimal('1')}),
    # Custom weights summing to 1
    (3, Decimal('1000.00'), {'a': Decimal('0.40'), 'b': Decimal('0.35'), 'c': Decimal('0.25')}),
])
def test_distribute_decimal_invariant(n_tenants, total_cost, weights):
    result = _distribute_decimal(total_cost, weights)
    assert sum(result.values()) == total_cost, (
        f"SUM={sum(result.values())} != total={total_cost}"
    )

def test_distribute_decimal_all_nonnegative():
    weights = {'a': Decimal('0.6'), 'b': Decimal('0.4')}
    result = _distribute_decimal(Decimal('50.00'), weights)
    assert all(v >= 0 for v in result.values())
```

---

## Unit Tests: Anomaly Detection

### `tests/unit/anomalies/test_zscore_detector.py`

```python
def test_zscore_detects_spike():
    values = [10.0] * 200
    values[180] = 100.0  # clear spike
    series = pd.Series(values)
    timestamps = pd.date_range('2025-01-01', periods=200, freq='h', tz='UTC')
    result = detect_zscore_anomalies(series, timestamps, window=168, threshold=3.0, min_cost_delta=5.0)
    assert result.iloc[180]['is_anomaly'] == True
    assert result.iloc[180]['direction'] == 'spike'
    # No false positives in stable region
    assert result.iloc[:168]['is_anomaly'].sum() == 0

def test_zscore_detects_drop():
    values = [100.0] * 200
    values[190] = 5.0  # clear drop
    series = pd.Series(values)
    timestamps = pd.date_range('2025-01-01', periods=200, freq='h', tz='UTC')
    result = detect_zscore_anomalies(series, timestamps, window=168, threshold=3.0, min_cost_delta=5.0)
    assert result.iloc[190]['is_anomaly'] == True
    assert result.iloc[190]['direction'] == 'drop'

def test_zscore_no_anomaly_below_min_delta():
    values = [10.0] * 200
    values[180] = 13.0  # small spike, below $5 delta
    series = pd.Series(values)
    timestamps = pd.date_range('2025-01-01', periods=200, freq='h', tz='UTC')
    result = detect_zscore_anomalies(series, timestamps, window=168, threshold=3.0, min_cost_delta=5.0)
    assert result['is_anomaly'].sum() == 0
```

---

## Unit Tests: RI Coverage

### `tests/unit/reservations/test_coverage.py`

```python
@pytest.mark.django_db
def test_coverage_pct_fully_utilized(loaded_line_items):
    from apps.reservations.services.coverage import compute_ri_coverage
    df = compute_ri_coverage('123456789012', '2025-01')
    m5_large = df[(df['instance_type'] == 'm5.large') & (df['region'] == 'us-east-1')]
    # Standard RI at 100% capacity — coverage should be near 100%
    assert m5_large['coverage_pct'].mean() > 0.90

def test_coverage_pct_partially_utilized(loaded_line_items):
    from apps.reservations.services.coverage import compute_ri_coverage
    df = compute_ri_coverage('123456789012', '2025-01')
    c5_xlarge = df[(df['instance_type'] == 'c5.xlarge') & (df['region'] == 'us-east-1')]
    # Convertible RI: unused on weekends, so avg utilization < 85%
    assert c5_xlarge['utilization_pct'].mean() < 0.85
```

---

## Integration Tests

### `tests/integration/test_etl_pipeline.py`

```python
@pytest.mark.django_db
def test_full_pipeline_loads_fixture(db):
    from apps.costs.models import LineItem, DailyCostAggregate
    # Use loaded_line_items fixture
    assert LineItem.objects.count() > 1000
    assert DailyCostAggregate.objects.filter(date__year=2025, date__month=1).count() > 0

@pytest.mark.django_db
def test_aggregate_sum_matches_line_items(loaded_line_items):
    from django.db.models import Sum
    from apps.costs.models import LineItem, DailyCostAggregate
    li_sum = float(LineItem.objects.filter(billing_period='2025-01')
                   .aggregate(Sum('unblended_cost'))['unblended_cost__sum'])
    da_sum = float(DailyCostAggregate.objects.filter(date__year=2025, date__month=1)
                   .aggregate(Sum('unblended_cost'))['unblended_cost__sum'])
    assert abs(li_sum - da_sum) < 0.01
```

### `tests/integration/test_api_costs.py`

```python
@pytest.mark.django_db
def test_cost_by_service_returns_200(api_client, loaded_line_items):
    resp = api_client.get('/api/v1/costs/by-service/?billing_period=2025-01')
    assert resp.status_code == 200
    data = resp.json()
    services = [r['service'] for r in data['results']]
    assert 'AmazonEC2' in services

@pytest.mark.django_db
def test_daily_trend_chart_has_correct_structure(api_client, loaded_line_items):
    resp = api_client.get('/api/v1/viz/daily-trend/?start_date=2025-01-01&end_date=2025-01-31')
    assert resp.status_code == 200
    body = resp.json()
    assert 'data' in body
    assert 'layout' in body
    assert len(body['data']) > 0
    trace = body['data'][0]
    assert trace['type'] == 'scatter'
    assert len(trace['x']) == 31   # 31 days in January

@pytest.mark.django_db
def test_top_n_returns_correct_count(api_client, loaded_line_items):
    resp = api_client.get('/api/v1/costs/top-n/?n=3&group_by=service&billing_period=2025-01')
    assert resp.status_code == 200
    assert len(resp.json()['results']) == 3
```

### `tests/integration/test_ingestion_tasks.py`

```python
@pytest.mark.django_db
def test_download_cur_task_with_moto(mock_s3, aws_account):
    from apps.accounts.models import CurManifest
    from apps.ingestion.models import CurDownloadJob
    from apps.ingestion.tasks import download_cur_task

    manifest = CurManifest.objects.create(
        account=aws_account, s3_bucket='test-cur-bucket',
        s3_prefix='acme-cur', report_name='acme-cur',
        time_unit='HOURLY', compression='GZIP', aws_region='us-east-1'
    )
    job = CurDownloadJob.objects.create(
        manifest=manifest, billing_period='2025-01',
        s3_keys=['acme-cur/20250101-20250201/acme-cur-1.csv']
    )
    download_cur_task(job.id)
    job.refresh_from_db()
    assert job.status == 'success'
    assert job.rows_downloaded > 0
```

---

## Running Tests

```bash
# All tests with coverage
pytest --cov=apps --cov-report=term-missing --cov-report=html --cov-fail-under=80

# Unit tests only (fast, no DB)
pytest tests/unit/ -v

# Integration tests only
pytest tests/integration/ -v --reuse-db

# Specific app
pytest tests/unit/splitting/ -v

# Coverage report
open htmlcov/index.html
```

---

## Verification

```bash
pytest --cov=apps --cov-fail-under=80
# Expected output:
# PASSED tests/unit/etl/test_normalizer.py::test_normalize_renames_columns
# PASSED tests/unit/splitting/test_invariant.py::test_distribute_decimal_invariant[...]
# PASSED tests/unit/anomalies/test_zscore_detector.py::test_zscore_detects_spike
# ...
# Coverage: 83%  (target: ≥ 80%)
# ===== N passed, 0 failed =====

ruff check .
# No issues.

mypy apps/
# Success: no issues found in N source files
```

---

## PROJECT COMPLETE

All 10 parts have been implemented. Final checklist:

- [ ] 1 MB handwritten CUR CSV fixture with realistic patterns (Part 0)
- [ ] Django project scaffold + docker-compose + GitHub CI (Part 1)
- [ ] ETL pipeline loading fixture into LineItem + aggregates (Part 2)
- [ ] Cost API + Plotly visualization endpoints (Part 3)
- [ ] EDP + spot price + instance pricing datasets (Part 4)
- [ ] RI/SP coverage, utilization, PuLP convertible swap optimizer (Part 5)
- [ ] Chronos zero-shot forecasting (24h + 7d) (Part 6)
- [ ] Ensemble anomaly detection (Chronos residual + Z-score) (Part 7)
- [ ] Tag-based cost splitting with verified invariant (Part 8)
- [ ] ≥ 80% test coverage, ruff + mypy clean (Part 9)
