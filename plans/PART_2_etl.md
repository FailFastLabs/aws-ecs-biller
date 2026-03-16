# PART 2 — Accounts, Ingestion, ETL, Costs Apps

## Objective
Build the data pipeline: AWS account config → S3 download → Pandas ETL → PostgreSQL.
Load the fake CUR data from Part 0. Provide core LineItem + aggregate models.

---

## App: `apps/accounts/`

### `models.py`
```python
class AwsAccount(models.Model):
    account_id   = models.CharField(max_length=12, unique=True)
    account_name = models.CharField(max_length=128)
    iam_role_arn = models.CharField(max_length=256, blank=True)
    is_payer     = models.BooleanField(default=False)
    created_at   = models.DateTimeField(auto_now_add=True)

class CurManifest(models.Model):
    account      = models.ForeignKey(AwsAccount, on_delete=models.CASCADE)
    s3_bucket    = models.CharField(max_length=256)
    s3_prefix    = models.CharField(max_length=512)
    report_name  = models.CharField(max_length=256)
    time_unit    = models.CharField(choices=[('HOURLY','HOURLY'),('DAILY','DAILY')])
    compression  = models.CharField(choices=[('GZIP','GZIP'),('Parquet','Parquet')])
    aws_region   = models.CharField(max_length=32)
    last_synced_at = models.DateTimeField(null=True)
```

### `serializers.py` + `views.py` + `urls.py`
Standard DRF ModelViewSet for AwsAccount and CurManifest.
Extra action: `POST /accounts/{id}/test-credentials/` — calls `boto3.client('sts').get_caller_identity()`.

---

## App: `apps/ingestion/`

### `models.py`
```python
class CurDownloadJob(models.Model):
    STATUS = [('pending','pending'),('running','running'),('success','success'),('failed','failed')]
    manifest       = models.ForeignKey('accounts.CurManifest', on_delete=models.CASCADE)
    billing_period = models.CharField(max_length=20)
    s3_keys        = models.JSONField(default=list)
    status         = models.CharField(choices=STATUS, default='pending')
    celery_task_id = models.CharField(max_length=64, blank=True)
    started_at     = models.DateTimeField(null=True)
    completed_at   = models.DateTimeField(null=True)
    error_message  = models.TextField(blank=True)
    rows_downloaded = models.BigIntegerField(default=0)

class CurFile(models.Model):
    ETL_STATUS = [('pending','pending'),('processed','processed'),('error','error')]
    job           = models.ForeignKey(CurDownloadJob, on_delete=models.CASCADE)
    s3_key        = models.CharField(max_length=1024)
    local_path    = models.CharField(max_length=1024)
    file_hash_sha256 = models.CharField(max_length=64)
    size_bytes    = models.BigIntegerField()
    downloaded_at = models.DateTimeField(auto_now_add=True)
    etl_status    = models.CharField(choices=ETL_STATUS, default='pending')
```

### `services/s3_downloader.py`
```python
def download_cur_file(manifest: CurManifest, s3_key: str, local_path: Path) -> str:
    """Download a CUR file from S3. Returns SHA-256 of downloaded file."""
    session = assume_role_session(manifest.account.iam_role_arn)
    s3 = session.client('s3', region_name=manifest.aws_region)
    s3.download_file(manifest.s3_bucket, s3_key, str(local_path))
    return sha256_of_file(local_path)
```

### `services/manifest_parser.py`
```python
def parse_manifest(manifest_json: dict) -> list[str]:
    """Return list of S3 report keys from a CUR manifest JSON."""
    return manifest_json.get('reportKeys', [])
```

### `tasks.py`
```python
@shared_task(bind=True, max_retries=3)
def download_cur_task(self, job_id: int) -> int:
    """Download all files for a CurDownloadJob. Returns job_id for chaining."""

@shared_task(bind=True, max_retries=2)
def run_etl_task(self, job_id: int) -> str:
    """Run ETL for all CurFiles in a job. Returns billing_period."""

# These chain: download_cur_task.s(job_id) | run_etl_task.s() | refresh_aggregates_task.s()
```

---

## App: `apps/etl/`

### Pipeline stages (each a pure function, no side effects):

**`pipeline/reader.py`**
```python
def read_cur_file(path: Path, chunk_size: int = 500_000) -> Iterator[pd.DataFrame]:
    """Yield DataFrames from CSV or Parquet. Auto-detects format from extension."""
    if path.suffix in ('.gz', '.csv'):
        for chunk in pd.read_csv(path, chunksize=chunk_size, dtype=str,
                                  compression='gzip' if path.suffix == '.gz' else None):
            yield chunk
    elif path.suffix == '.parquet':
        yield pd.read_parquet(path, engine='pyarrow')
```

**`pipeline/normalizer.py`**
```python
from apps.etl.column_mappings.cur_columns import CUR_TO_INTERNAL

def normalize_schema(df: pd.DataFrame) -> pd.DataFrame:
    """Rename CUR columns to internal names, cast types, derive billing_period."""
    # 1. Rename known columns; keep unknown as-is for debugging
    df = df.rename(columns={k: v for k, v in CUR_TO_INTERNAL.items() if k in df.columns})
    # 2. Parse timestamps as UTC
    for col in ('usage_start', 'usage_end', 'billing_period_start', 'billing_period_end'):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], utc=True, errors='coerce')
    # 3. Derive billing_period from billing_period_start
    df['billing_period'] = df['billing_period_start'].dt.strftime('%Y-%m')
    # 4. Cast cost columns to float64 (Decimal loaded at DB insert time)
    COST_COLS = ['unblended_cost','blended_cost','net_unblended_cost',
                 'public_on_demand_cost','reservation_effective_cost',
                 'reservation_amortized_upfront_cost','reservation_recurring_fee',
                 'sp_effective_cost','sp_net_effective_cost','split_cost']
    for col in COST_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
    # 5. Parse tags JSON
    if 'tags' in df.columns:
        df['tags'] = df['tags'].apply(_parse_tags_json)
    return df

def _parse_tags_json(raw: str) -> dict:
    """Parse CUR resource_tags string into dict. Returns {} on failure."""
    if pd.isna(raw) or not raw:
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
```

**`pipeline/deduplicator.py`**
```python
def deduplicate(df: pd.DataFrame, existing_ids: set[str]) -> pd.DataFrame:
    """
    Remove rows already in DB or duplicated within this file.
    existing_ids: set of line_item_id values for this billing_period already in DB.
    """
    df = df.drop_duplicates(subset=['line_item_id', 'billing_period'])
    mask = df['line_item_id'].isin(existing_ids)
    return df[~mask]
```

**`pipeline/validator.py`**
```python
REQUIRED_FIELDS = ['line_item_id', 'billing_period', 'usage_start',
                   'service', 'linked_account_id', 'unblended_cost']
CREDIT_TYPES = {'Credit', 'Refund', 'EdpDiscount', 'BundledDiscount'}

def validate(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (valid_df, rejected_df). Log rejection reasons."""
    mask_null = df[REQUIRED_FIELDS].isnull().any(axis=1)
    mask_neg  = (df['unblended_cost'] < 0) & (~df['line_item_type'].isin(CREDIT_TYPES))
    rejected  = df[mask_null | mask_neg].copy()
    valid     = df[~(mask_null | mask_neg)].copy()
    return valid, rejected
```

**`pipeline/loader.py`**
```python
def bulk_load(df: pd.DataFrame, batch_size: int = 10_000) -> int:
    """Bulk insert DataFrame rows into LineItem. Returns count inserted."""
    from apps.costs.models import LineItem
    objs = [LineItem(**_row_to_model_kwargs(row)) for _, row in df.iterrows()]
    created = LineItem.objects.bulk_create(objs, batch_size=batch_size,
                                            ignore_conflicts=True)
    return len(created)
```

**`pipeline/aggregator.py`**
```python
def refresh_daily_aggregates(billing_period: str) -> None:
    """Upsert DailyCostAggregate for a billing period."""
    from apps.costs.models import LineItem, DailyCostAggregate
    qs = (LineItem.objects
          .filter(billing_period=billing_period)
          .annotate(date=TruncDate('usage_start'))
          .values('date','linked_account_id','service','region','usage_type','line_item_type')
          .annotate(unblended_cost=Sum('unblended_cost'),
                    usage_quantity=Sum('usage_quantity')))
    for row in qs:
        DailyCostAggregate.objects.update_or_create(
            date=row['date'], linked_account_id=row['linked_account_id'],
            service=row['service'], region=row['region'],
            usage_type=row['usage_type'], line_item_type=row['line_item_type'],
            defaults={'unblended_cost': row['unblended_cost'],
                      'usage_quantity': row['usage_quantity']}
        )
    # Same pattern for HourlyCostAggregate using TruncHour
```

### Column mapping `apps/etl/column_mappings/cur_columns.py`
Use the full `CUR_TO_INTERNAL` dict from the master plan.

### `models.py`
```python
class EtlRun(models.Model):
    cur_file         = models.ForeignKey('ingestion.CurFile', on_delete=models.CASCADE)
    rows_read        = models.BigIntegerField(default=0)
    rows_after_dedup = models.BigIntegerField(default=0)
    rows_loaded      = models.BigIntegerField(default=0)
    duration_seconds = models.FloatField(null=True)
    started_at       = models.DateTimeField(auto_now_add=True)
    completed_at     = models.DateTimeField(null=True)
    error_detail     = models.TextField(blank=True)
    status           = models.CharField(max_length=16, default='pending')
```

---

## App: `apps/costs/`

### `models.py`

**`LineItem`** — see master plan for full field list.

Key additions:
- `UniqueConstraint(fields=['line_item_id','billing_period'], name='uq_li_bp')`
- PostgreSQL GIN index on `tags` via migration `RunSQL`:
  ```sql
  CREATE INDEX costs_lineitem_tags_gin ON costs_lineitem USING GIN (tags jsonb_path_ops);
  ```

**`DailyCostAggregate`**:
```python
class DailyCostAggregate(models.Model):
    date              = models.DateField(db_index=True)
    linked_account_id = models.CharField(max_length=12, db_index=True)
    service           = models.CharField(max_length=128, db_index=True)
    region            = models.CharField(max_length=64, db_index=True)
    usage_type        = models.CharField(max_length=256)
    line_item_type    = models.CharField(max_length=64)
    unblended_cost    = models.DecimalField(max_digits=20, decimal_places=6)
    usage_quantity    = models.DecimalField(max_digits=24, decimal_places=6)
    class Meta:
        unique_together = [('date','linked_account_id','service','region','usage_type','line_item_type')]
```

**`HourlyCostAggregate`**: same but `hour = DateTimeField`.

### `filters.py`
```python
class LineItemFilter(filters.FilterSet):
    usage_start_after  = filters.DateTimeFilter(field_name='usage_start', lookup_expr='gte')
    usage_start_before = filters.DateTimeFilter(field_name='usage_start', lookup_expr='lte')
    tag_key   = filters.CharFilter(method='filter_tag_key')
    tag_value = filters.CharFilter(method='filter_tag_value')

    def filter_tag_key(self, qs, name, value):
        return qs.filter(tags__has_key=value)

    def filter_tag_value(self, qs, name, value):
        # used together with tag_key
        return qs.filter(tags__contains={self.data.get('tag_key', ''): value})

    class Meta:
        model  = LineItem
        fields = ['service','region','linked_account_id','line_item_type',
                  'instance_type','billing_period']
```

### API endpoints (`urls.py`)
```
GET /api/v1/costs/line-items/       filterable + paginated
GET /api/v1/costs/daily/
GET /api/v1/costs/hourly/
GET /api/v1/costs/by-service/       aggregate totals by service
GET /api/v1/costs/by-region/
GET /api/v1/costs/by-account/
GET /api/v1/costs/by-tag/           ?tag_key=user:team
GET /api/v1/costs/top-n/            ?n=10&group_by=usage_type
```

---

## Load Fake Data

After migrations, load the fixture from Part 0 via management command:

### `scripts/management/commands/load_fixture_cur.py`
```python
class Command(BaseCommand):
    help = 'Load CUR fixture CSV directly into LineItem (bypasses S3 download)'

    def handle(self, *args, **options):
        from apps.etl.pipeline.reader import read_cur_file
        from apps.etl.pipeline.normalizer import normalize_schema
        from apps.etl.pipeline.deduplicator import deduplicate
        from apps.etl.pipeline.validator import validate
        from apps.etl.pipeline.loader import bulk_load
        from apps.etl.pipeline.aggregator import refresh_daily_aggregates, refresh_hourly_aggregates

        path = Path(settings.BASE_DIR) / 'tests/fixtures/cur_sample_2025_01.csv'
        total = 0
        for chunk in read_cur_file(path):
            df = normalize_schema(chunk)
            df = deduplicate(df, existing_ids=set())
            valid, rejected = validate(df)
            n = bulk_load(valid)
            total += n
            self.stdout.write(f'Loaded {n} rows (rejected {len(rejected)})')

        refresh_daily_aggregates('2025-01')
        refresh_hourly_aggregates('2025-01')
        self.stdout.write(self.style.SUCCESS(f'Done. Total rows: {total}'))
```

Run: `python manage.py load_fixture_cur`

---

## Verification
```bash
python manage.py migrate
python manage.py load_fixture_cur
# Expect: LineItem.objects.count() > 5000
# Expect: DailyCostAggregate.objects.count() == 31 * (distinct service/region/account combos)
# Manual check: sum of daily aggregates for 2025-01 == sum of LineItem.unblended_cost for 2025-01
python manage.py shell -c "
from apps.costs.models import LineItem, DailyCostAggregate
from django.db.models import Sum
li_sum = LineItem.objects.filter(billing_period='2025-01').aggregate(Sum('unblended_cost'))
da_sum = DailyCostAggregate.objects.filter(date__startswith='2025-01').aggregate(Sum('unblended_cost'))
print('LineItem sum:', li_sum)
print('Daily agg sum:', da_sum)
assert abs(float(li_sum['unblended_cost__sum']) - float(da_sum['unblended_cost__sum'])) < 0.01
print('PASS: sums match')
"
```

---

## NEXT

After completing Part 2, run:
**`/Users/mfeldman/.claude/plans/PART_3_viz.md`**
