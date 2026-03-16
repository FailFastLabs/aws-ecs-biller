# PART 8 — Cost Splitting

## Objective
Implement tag-based cost splitting for shared services (e.g. k8s cluster).
The invariant — `SUM(allocated_cost) per (hour, region, usage_type) == original_cost` exactly —
must be enforced using Decimal arithmetic.

---

## App: `apps/splitting/`

### `models.py`

```python
class SplittingRule(models.Model):
    STRATEGIES = [('equal','equal'),
                  ('proportional_usage','proportional_usage'),
                  ('custom_weight','custom_weight')]
    name              = models.CharField(max_length=128)
    service           = models.CharField(max_length=128)
    region            = models.CharField(max_length=64)
    split_by_tag_key  = models.CharField(max_length=128)
    # e.g. 'user:team' — this tag key determines who gets allocated cost
    weight_strategy   = models.CharField(choices=STRATEGIES)
    custom_weights    = models.JSONField(default=dict)
    # {'backend': 0.40, 'frontend': 0.35, 'data': 0.25}
    active            = models.BooleanField(default=True)
    created_at        = models.DateTimeField(auto_now_add=True)

class SplitResult(models.Model):
    """
    One row per (hour, region, usage_type, tenant).
    INVARIANT: SUM(allocated_cost) grouped by (hour, region, usage_type) == original_cost
    """
    splitting_rule    = models.ForeignKey(SplittingRule, on_delete=models.CASCADE)
    billing_period    = models.CharField(max_length=20, db_index=True)
    hour              = models.DateTimeField(db_index=True)
    region            = models.CharField(max_length=64, db_index=True)
    usage_type        = models.CharField(max_length=256, db_index=True)
    tenant_tag_value  = models.CharField(max_length=256, db_index=True)
    original_cost     = models.DecimalField(max_digits=20, decimal_places=10)
    allocated_cost    = models.DecimalField(max_digits=20, decimal_places=10)
    allocation_weight = models.DecimalField(max_digits=10, decimal_places=8)

    class Meta:
        unique_together = [('splitting_rule','hour','region','usage_type','tenant_tag_value')]
```

---

## `services/splitter.py`

```python
from decimal import Decimal, ROUND_HALF_UP

def run_split(rule: SplittingRule, billing_period: str) -> int:
    """
    Execute cost splitting for a billing period.
    Returns count of SplitResult rows created.
    """
    start, end = _billing_period_to_range(billing_period)

    # Step 1: Aggregate original costs at (hour, region, usage_type)
    rows = (
        HourlyCostAggregate.objects
        .filter(service=rule.service, region=rule.region, hour__range=(start, end))
        .values('hour', 'region', 'usage_type')
        .annotate(total_cost=Sum('unblended_cost'))
    )

    results = []
    for row in rows:
        total_cost = Decimal(str(row['total_cost']))
        hour, region, usage_type = row['hour'], row['region'], row['usage_type']

        # Step 2: Compute weights
        weights = _compute_weights(rule, hour, region, usage_type)
        if not weights:
            continue

        # Step 3: Distribute using largest-remainder method
        allocated = _distribute_decimal(total_cost, weights)

        # Step 4: Build SplitResult objects
        for tenant, alloc_cost in allocated.items():
            weight = (alloc_cost / total_cost).quantize(Decimal('0.00000001'))
            results.append(SplitResult(
                splitting_rule=rule,
                billing_period=billing_period,
                hour=hour, region=region, usage_type=usage_type,
                tenant_tag_value=tenant,
                original_cost=total_cost,
                allocated_cost=alloc_cost,
                allocation_weight=weight,
            ))

    SplitResult.objects.bulk_create(results, batch_size=5000, ignore_conflicts=True)

    # Step 5: Verify invariant
    verify_split_invariant(rule, billing_period)

    return len(results)


def _compute_weights(rule, hour, region, usage_type) -> dict[str, Decimal]:
    if rule.weight_strategy == 'equal':
        tenants = _get_active_tenants(rule, hour)
        n = len(tenants)
        return {t: Decimal('1') / Decimal(str(n)) for t in tenants} if n else {}

    elif rule.weight_strategy == 'proportional_usage':
        usage = _get_tag_usage(rule.split_by_tag_key, hour, region, usage_type)
        total = sum(usage.values()) or Decimal('1')
        return {t: v / total for t, v in usage.items()}

    elif rule.weight_strategy == 'custom_weight':
        raw = rule.custom_weights
        total_w = sum(Decimal(str(v)) for v in raw.values())
        return {k: Decimal(str(v)) / total_w for k, v in raw.items()} if total_w else {}

    return {}


def _distribute_decimal(total: Decimal, weights: dict[str, Decimal]) -> dict[str, Decimal]:
    """
    Largest-remainder method for exact Decimal distribution.
    The last tenant absorbs rounding remainder to guarantee SUM == total.
    """
    PRECISION = Decimal('0.0000000001')
    tenants = sorted(weights.keys())
    allocated = {}
    running = Decimal('0')

    for tenant in tenants[:-1]:
        share = (weights[tenant] * total).quantize(PRECISION, rounding=ROUND_HALF_UP)
        allocated[tenant] = share
        running += share

    # Last tenant gets exact remainder
    allocated[tenants[-1]] = total - running
    return allocated


def _get_active_tenants(rule, hour) -> list[str]:
    """Get distinct tag values for rule.split_by_tag_key that had usage at this hour."""
    from apps.costs.models import LineItem
    tags_with_value = (
        LineItem.objects
        .filter(service=rule.service, region=rule.region,
                usage_start__lte=hour, usage_end__gte=hour,
                tags__has_key=rule.split_by_tag_key)
        .values_list('tags', flat=True)
    )
    return list({t.get(rule.split_by_tag_key) for t in tags_with_value if t})


def _get_tag_usage(tag_key: str, hour, region: str, usage_type: str) -> dict[str, Decimal]:
    """Proportional usage: sum of usage_quantity per tag value."""
    from apps.costs.models import LineItem
    rows = (
        LineItem.objects
        .filter(region=region, usage_type=usage_type,
                usage_start__lte=hour, usage_end__gte=hour,
                tags__has_key=tag_key)
        .values('tags')
        .annotate(qty=Sum('usage_quantity'))
    )
    result = {}
    for r in rows:
        val = r['tags'].get(tag_key)
        if val:
            result[val] = result.get(val, Decimal('0')) + Decimal(str(r['qty']))
    return result
```

---

## `services/verifier.py`

```python
class SplitInvariantViolationError(Exception):
    pass

def verify_split_invariant(rule: SplittingRule, billing_period: str,
                             tolerance: Decimal = Decimal('1e-8')) -> None:
    """
    SQL-level check: for every (hour, region, usage_type),
    SUM(allocated_cost) must equal original_cost within tolerance.
    Raises SplitInvariantViolationError if any group violates.
    """
    start, end = _billing_period_to_range(billing_period)
    groups = (
        SplitResult.objects
        .filter(splitting_rule=rule, hour__range=(start, end))
        .values('hour', 'region', 'usage_type', 'original_cost')
        .annotate(sum_allocated=Sum('allocated_cost'))
    )
    violations = []
    for g in groups:
        diff = abs(Decimal(str(g['sum_allocated'])) - Decimal(str(g['original_cost'])))
        if diff > tolerance:
            violations.append(
                f"hour={g['hour']}, region={g['region']}, "
                f"usage_type={g['usage_type']}: "
                f"sum={g['sum_allocated']}, original={g['original_cost']}, diff={diff}"
            )
    if violations:
        raise SplitInvariantViolationError(
            f"Invariant violated in {len(violations)} groups:\n" + "\n".join(violations[:5])
        )
```

---

## Management Command

```python
# scripts/management/commands/verify_splits.py
class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('billing_period', type=str)  # e.g. '2025-01'

    def handle(self, *args, **options):
        for rule in SplittingRule.objects.filter(active=True):
            try:
                verify_split_invariant(rule, options['billing_period'])
                self.stdout.write(self.style.SUCCESS(f'Rule {rule.name}: PASS'))
            except SplitInvariantViolationError as e:
                self.stdout.write(self.style.ERROR(f'Rule {rule.name}: FAIL\n{e}'))
```

---

## Seed Fixture Split Rule

```python
# In load_fixture_cur.py or a separate seed command:
SplittingRule.objects.get_or_create(
    name='EKS Cluster Cost Split',
    defaults={
        'service': 'AmazonEKS',
        'region': 'us-east-1',
        'split_by_tag_key': 'user:team',
        'weight_strategy': 'custom_weight',
        'custom_weights': {'backend': 0.40, 'frontend': 0.35, 'data': 0.25},
        'active': True,
    }
)
```

---

## API Endpoints

```
GET  /api/v1/splitting/rules/
POST /api/v1/splitting/rules/
PUT  /api/v1/splitting/rules/{id}/
POST /api/v1/splitting/rules/{id}/run/       body: {billing_period: '2025-01'}
GET  /api/v1/splitting/results/              ?rule_id=&billing_period=
GET  /api/v1/splitting/results/verify/       verify invariant for a period
```

---

## Verification

```bash
python manage.py shell -c "
from apps.splitting.models import SplittingRule
from apps.splitting.services.splitter import run_split
from apps.splitting.services.verifier import verify_split_invariant

rule = SplittingRule.objects.get(name='EKS Cluster Cost Split')
n = run_split(rule, '2025-01')
print(f'Created {n} split results')
verify_split_invariant(rule, '2025-01')
print('Invariant: PASS')
"

python manage.py verify_splits 2025-01
# Expected: Rule EKS Cluster Cost Split: PASS
```

---

## NEXT

After completing Part 8, run:
**`/Users/mfeldman/.claude/plans/PART_9_tests.md`**
