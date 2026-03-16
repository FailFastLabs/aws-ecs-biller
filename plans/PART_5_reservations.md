# PART 5 — RI/SP Analysis + PuLP Optimizer

## Objective
Build the reservations app: coverage/utilization views, SP counterfactual analysis,
and a PuLP linear program to recommend convertible RI swaps.

---

## App: `apps/reservations/`

### `models.py`

```python
class ReservedInstance(models.Model):
    account          = models.ForeignKey('accounts.AwsAccount', on_delete=models.CASCADE)
    reservation_id   = models.CharField(max_length=64, unique=True)
    reservation_arn  = models.CharField(max_length=512, unique=True)
    instance_type    = models.CharField(max_length=64, db_index=True)
    instance_family  = models.CharField(max_length=64)
    normalized_units = models.FloatField()  # count × normalization_factor
    region           = models.CharField(max_length=64)
    tenancy          = models.CharField(max_length=32)
    platform         = models.CharField(max_length=64)
    offering_class   = models.CharField(max_length=32)   # standard | convertible
    offering_type    = models.CharField(max_length=64)   # No Upfront | Partial | Full
    instance_count   = models.IntegerField()
    start_date       = models.DateField()
    end_date         = models.DateField()
    fixed_price      = models.DecimalField(max_digits=20, decimal_places=6)
    recurring_hourly_cost = models.DecimalField(max_digits=20, decimal_places=6)
    scope            = models.CharField(max_length=32)   # Region | AZ
    state            = models.CharField(max_length=32)   # active | retired

class RiRecommendation(models.Model):
    account          = models.ForeignKey('accounts.AwsAccount', on_delete=models.CASCADE)
    generated_at     = models.DateTimeField(auto_now_add=True)
    recommendation_type = models.CharField(max_length=32)
    # buy_ri | buy_sp | convert_ri | reduce_ri | reduce_sp
    instance_type    = models.CharField(max_length=64)
    region           = models.CharField(max_length=64)
    platform         = models.CharField(max_length=64, blank=True)
    quantity         = models.IntegerField()
    estimated_monthly_savings = models.DecimalField(max_digits=20, decimal_places=2)
    break_even_months = models.FloatField(null=True)
    analysis_window_days = models.IntegerField(default=30)
    confidence_score = models.FloatField()
    detail_json      = models.JSONField(default=dict)

class SavingsPlan(models.Model):
    account          = models.ForeignKey('accounts.AwsAccount', on_delete=models.CASCADE)
    savings_plan_id  = models.CharField(max_length=64, unique=True)
    savings_plan_arn = models.CharField(max_length=512)
    plan_type        = models.CharField(max_length=32)   # Compute | EC2Instance
    commitment_hourly = models.DecimalField(max_digits=20, decimal_places=6)
    start_date       = models.DateField()
    end_date         = models.DateField()
    state            = models.CharField(max_length=32)
```

---

## Services

### `services/coverage.py`

**AWS application order**: non-convertible RIs → convertible RIs → Savings Plans → on-demand.
This must be reflected in coverage attribution:

```python
def compute_ri_coverage(account_id: str, billing_period: str) -> pd.DataFrame:
    """
    Returns DataFrame with columns:
    [instance_type, region, platform, hour, on_demand_hours, ri_covered_hours,
     coverage_pct, utilization_pct, unused_ri_hours]

    Queries LineItem for:
    - line_item_type='DiscountedUsage' → ri_covered_hours (ordered: standard first, then convertible)
    - line_item_type='RIFee'           → total purchased capacity (unused_ri_hours derived from here)
    - line_item_type='Usage', pricing_term='OnDemand' → on_demand_hours
    """
```

### `services/utilization.py`

```python
def compute_ri_utilization(account_id: str, billing_period: str) -> pd.DataFrame:
    """
    utilization_pct = SUM(DiscountedUsage.usage_quantity) /
                      SUM(RIFee.reservation_norm_units * reservation_count)
    per (reservation_arn, billing_period).

    Returns DataFrame: [reservation_arn, instance_type, region, offering_class,
                        purchased_units, used_units, utilization_pct,
                        unused_hours, unused_cost]
    """
```

### `services/sp_counterfactual.py`

```python
def compute_sp_counterfactual(account_id: str, billing_period: str) -> dict:
    """
    For each Savings Plan:
    1. Compute actual SP-covered cost: SUM(sp_effective_cost WHERE SavingsPlanCoveredUsage)
    2. Compute counterfactual on-demand cost: SUM(public_on_demand_cost WHERE SavingsPlanCoveredUsage)
    3. Savings = counterfactual - actual
    4. Marginal analysis: if commitment were +10%, would additional coverage savings
       exceed the additional base fee?
       additional_fee = commitment * 0.10 * hours_in_period
       marginal_savings = p80(hourly_uncovered_eligible_spend) * 0.10 * savings_rate
       recommend_increase = marginal_savings > additional_fee
    Returns: {sp_arn: {actual_cost, od_equivalent, savings, savings_rate,
                        recommend_increase, recommended_commitment_delta}}
    """
```

---

## PuLP Convertible RI Optimizer

### `services/convertible_optimizer.py`

The optimization problem: given convertible RIs that can be exchanged for other instance types
in the same family, find the allocation that minimizes total hourly cost while keeping
total reserved commitment within [current, current × 1.01].

```python
import pulp

def optimize_convertible_ris(account_id: str, billing_period: str,
                              max_commitment_increase_pct: float = 0.01) -> list[dict]:
    """
    Step 1: Identify all active convertible RIs for this account.

    Step 2: Build demand curves.
    For each instance family (e.g. 'm5'), in each region:
    - Compute hourly on-demand normalized unit demand from LineItem
    - Compute per-instance-type OD rates from InstancePricing

    Step 3: Define decision variables.
    x[arn][instance_type] = number of normalized units to assign to this instance type
    (convertible exchange: can change instance type within family freely)

    Step 4: LP formulation.
    Minimize:   SUM over (arn, instance_type) of:
                    x[arn][instance_type] * ri_hourly_rate[instance_type]
                + SUM over (instance_type, hour) of:
                    max(0, demand[instance_type][hour] - covered[instance_type]) * od_rate[instance_type]

    Subject to:
    (a) SUM(x[arn][*]) == original_normalized_units[arn]  ∀ arn
        (exchange preserves total normalized unit count per RI)
    (b) SUM over all RI allocations of ri_hourly_cost ≤ current_total_ri_cost * (1 + max_pct)
    (c) x[arn][instance_type] >= 0  ∀ arn, instance_type
    (d) instance_type must be in same family as original RI

    Step 5: Solve with PuLP (CBC solver).

    Step 6: Compare solution to current allocation.
    For each RI where optimal instance_type != current instance_type:
        emit swap recommendation with estimated monthly savings.

    Returns: list of {ri_arn, current_type, recommended_type,
                       current_monthly_cost, optimal_monthly_cost, monthly_savings}
    """
    prob = pulp.LpProblem("convertible_ri_swap", pulp.LpMinimize)

    # Build decision variables: x[ri_arn][instance_type] = normalized units
    ris = ReservedInstance.objects.filter(
        account__account_id=account_id,
        offering_class='convertible',
        state='active'
    )

    # For each RI, get eligible swap targets (same family, same region)
    # from InstancePricing

    # Objective: minimize RI cost + residual on-demand cost
    # Constraints: (a) unit conservation, (b) budget cap

    status = prob.solve(pulp.PULP_CBC_CMD(msg=0))
    if pulp.LpStatus[status] != 'Optimal':
        raise ValueError(f"LP solver did not find optimal solution: {pulp.LpStatus[status]}")

    # Extract recommendations from solution
    recommendations = []
    for ri in ris:
        for itype, var in x[ri.reservation_arn].items():
            if var.value() > 0.01 and itype != ri.instance_type:
                recommendations.append({...})
    return recommendations
```

---

## API Endpoints (`urls.py`)

```
GET  /api/v1/reservations/ris/                 list ReservedInstances
POST /api/v1/reservations/sync/                boto3 sync from AWS EC2 API
GET  /api/v1/reservations/savings-plans/
POST /api/v1/reservations/savings-plans/sync/
GET  /api/v1/reservations/coverage/            ?account_id=&billing_period=
GET  /api/v1/reservations/utilization/         ?account_id=&billing_period=
GET  /api/v1/reservations/sp-counterfactual/   ?account_id=&billing_period=
GET  /api/v1/reservations/recommendations/     list RiRecommendation records
POST /api/v1/reservations/recommendations/run/ trigger analysis + PuLP optimization
GET  /api/v1/reservations/convertible-swaps/   ?account_id=&billing_period=
```

---

## Seed Reservations from Fake Data

Since we have no real AWS API, seed `ReservedInstance` records from the RI ARNs
baked into the fake CUR fixture (see Part 0 RI ARNs):

```python
# scripts/management/commands/seed_reservations.py
RI_FIXTURES = [
    {'reservation_id': 'ri-0a1b2c3d4e5f6789a', 'instance_type': 'm5.large',
     'instance_family': 'm5', 'normalized_units': 40.0,  # 10 * 4.0
     'region': 'us-east-1', 'offering_class': 'standard', 'instance_count': 10,
     'start_date': '2024-01-01', 'end_date': '2027-01-01',
     'recurring_hourly_cost': 0.6240, 'fixed_price': 0.0, 'state': 'active'},
    {'reservation_id': 'ri-0b2c3d4e5f6789ab', 'instance_type': 'c5.xlarge',
     'instance_family': 'c5', 'normalized_units': 40.0,  # 5 * 8.0
     'region': 'us-east-1', 'offering_class': 'convertible', 'instance_count': 5,
     'start_date': '2024-06-01', 'end_date': '2027-06-01',
     'recurring_hourly_cost': 0.4675, 'fixed_price': 0.0, 'state': 'active'},
    # ... remaining RIs from Part 0 universe
]
```

---

## Verification

```bash
python manage.py seed_reservations

python manage.py shell -c "
from apps.reservations.services.coverage import compute_ri_coverage
df = compute_ri_coverage('123456789012', '2025-01')
print(df[['instance_type','region','coverage_pct','utilization_pct']].describe())
# m5.large in us-east-1 should show ~100% coverage
# c5.xlarge convertible should show <80% utilization (unused on weekends)
"

# Trigger PuLP optimization
curl -X POST http://localhost:8000/api/v1/reservations/recommendations/run/ \
  -H 'Content-Type: application/json' \
  -d '{"account_id": "123456789012", "billing_period": "2025-01"}'
# Should return at least 1 convertible swap recommendation for c5.xlarge
```

---

## NEXT

After completing Part 5, run:
**`/Users/mfeldman/.claude/plans/PART_6_forecasting.md`**
