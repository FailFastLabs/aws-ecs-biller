# PART 4 — Additional Pricing Datasets

## Objective
Load and expose three supplementary pricing datasets:
1. **EDP Discounts** — enterprise discount % per service/region
2. **Spot Price History** — hourly spot prices per instance type/AZ
3. **Instance Pricing Catalog** — OD + RI rates per instance type/region

These are needed by the RI recommender (Part 5) and visualizations.

---

## Models (`apps/costs/models.py` — add to existing file)

```python
class EdpDiscount(models.Model):
    """Enterprise Discount Program rate per service/region."""
    service      = models.CharField(max_length=128, db_index=True)
    region       = models.CharField(max_length=64, db_index=True)
    discount_pct = models.DecimalField(max_digits=6, decimal_places=3)
    effective_date = models.DateField()
    source       = models.CharField(max_length=32, default='manual')  # 'manual' or 'aws_api'

    class Meta:
        unique_together = [('service', 'region', 'effective_date')]


class SpotPriceHistory(models.Model):
    """Historical EC2 spot prices."""
    region        = models.CharField(max_length=64, db_index=True)
    instance_type = models.CharField(max_length=64, db_index=True)
    availability_zone = models.CharField(max_length=32)
    timestamp     = models.DateTimeField(db_index=True)
    spot_price    = models.DecimalField(max_digits=10, decimal_places=6)

    class Meta:
        unique_together = [('region', 'instance_type', 'availability_zone', 'timestamp')]
        indexes = [models.Index(fields=['region', 'instance_type', 'timestamp'])]


class InstancePricing(models.Model):
    """On-demand and RI pricing per instance type/region."""
    region               = models.CharField(max_length=64, db_index=True)
    instance_type        = models.CharField(max_length=64, db_index=True)
    od_hourly            = models.DecimalField(max_digits=10, decimal_places=6)
    convertible_1yr_hourly  = models.DecimalField(max_digits=10, decimal_places=6, null=True)
    convertible_3yr_hourly  = models.DecimalField(max_digits=10, decimal_places=6, null=True)
    standard_1yr_hourly  = models.DecimalField(max_digits=10, decimal_places=6, null=True)
    standard_3yr_hourly  = models.DecimalField(max_digits=10, decimal_places=6, null=True)
    effective_date       = models.DateField()
    source               = models.CharField(max_length=32, default='manual')

    class Meta:
        unique_together = [('region', 'instance_type', 'effective_date')]
```

---

## Management Command: `load_pricing_fixtures`

```python
# scripts/management/commands/load_pricing_fixtures.py
class Command(BaseCommand):
    help = 'Load EDP discounts, spot prices, instance pricing from fixture CSVs'

    def handle(self, *args, **options):
        base = Path(settings.BASE_DIR) / 'tests/fixtures'

        # EDP Discounts
        edp_df = pd.read_csv(base / 'edp_discounts.csv')
        for _, row in edp_df.iterrows():
            EdpDiscount.objects.update_or_create(
                service=row['service'], region=row['region'],
                effective_date='2025-01-01',
                defaults={'discount_pct': row['discount_pct']}
            )
        self.stdout.write(f'Loaded {len(edp_df)} EDP discounts')

        # Spot prices
        spot_df = pd.read_csv(base / 'spot_price_history.csv')
        spot_df['timestamp'] = pd.to_datetime(spot_df['timestamp'], utc=True)
        objs = [SpotPriceHistory(**r) for r in spot_df.to_dict('records')]
        SpotPriceHistory.objects.bulk_create(objs, ignore_conflicts=True)
        self.stdout.write(f'Loaded {len(objs)} spot price records')

        # Instance pricing
        price_df = pd.read_csv(base / 'instance_pricing.csv')
        for _, row in price_df.iterrows():
            InstancePricing.objects.update_or_create(
                region=row['region'], instance_type=row['instance_type'],
                effective_date='2025-01-01',
                defaults={k: row[k] for k in
                          ['od_hourly','convertible_1yr_hourly','convertible_3yr_hourly',
                           'standard_1yr_hourly','standard_3yr_hourly']}
            )
        self.stdout.write(f'Loaded {len(price_df)} instance pricing rows')
```

---

## API Endpoints (add to `apps/costs/urls.py`)

```
GET /api/v1/costs/instance-pricing/
    ?region=us-east-1&instance_type=m5.large
    → OD and RI rates, effective discount vs OD

GET /api/v1/costs/spot-prices/
    ?region=us-east-1&instance_type=m5.large&start=2025-01-01&end=2025-01-31
    → time series of spot prices

GET /api/v1/costs/spot-vs-od/
    ?region=us-east-1&instance_type=m5.large
    → {od_hourly: 0.096, avg_spot: 0.031, max_spot: 0.072, pct_savings: 67.7}

GET /api/v1/costs/edp-discounts/
    → list of EDP rates by service/region
```

---

## Spot Price Visualization

Add to `apps/visualizations/chart_builders/spot_prices.py`:
```python
def build_spot_vs_od_chart(region: str, instance_type: str) -> dict:
    """
    Line chart: spot price over time vs flat OD rate.
    Highlights periods where spot > 70% of OD (risky for spot bids).
    """
    od_rate = InstancePricing.objects.filter(
        region=region, instance_type=instance_type
    ).latest('effective_date').od_hourly

    spots = SpotPriceHistory.objects.filter(
        region=region, instance_type=instance_type
    ).order_by('timestamp').values('timestamp', 'spot_price', 'availability_zone')

    df = pd.DataFrame(spots)
    # One trace per AZ + flat OD reference line
```

---

## Verification
```bash
python manage.py load_pricing_fixtures
python manage.py shell -c "
from apps.costs.models import EdpDiscount, InstancePricing, SpotPriceHistory
print('EDP:', EdpDiscount.objects.count())
print('Pricing:', InstancePricing.objects.count())
print('Spot:', SpotPriceHistory.objects.count())
p = InstancePricing.objects.get(region='us-east-1', instance_type='m5.large', effective_date='2025-01-01')
print(f'm5.large OD={p.od_hourly}, 3yr-std={p.standard_3yr_hourly}')
"

curl "http://localhost:8000/api/v1/costs/spot-vs-od/?region=us-east-1&instance_type=m5.large"
```

---

## NEXT

After completing Part 4, run:
**`/Users/mfeldman/.claude/plans/PART_5_reservations.md`**
