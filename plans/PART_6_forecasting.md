# PART 6 — Forecasting with Chronos

## Objective
Integrate Amazon Chronos (zero-shot time series foundation model) for 24h and 7-day
cost forecasts at hourly and daily granularity.

## Dependency
```
pip install chronos-forecasting torch
```
Chronos runs on CPU for inference (no GPU required for small context windows).
Use `chronos-t5-small` model for speed; `chronos-t5-large` for accuracy in prod.

---

## App: `apps/forecasting/`

### `models.py`
```python
class ForecastRun(models.Model):
    account          = models.ForeignKey('accounts.AwsAccount', on_delete=models.CASCADE)
    grain            = models.CharField(max_length=16)   # hourly | daily
    service          = models.CharField(max_length=128, blank=True)
    region           = models.CharField(max_length=64, blank=True)
    usage_type       = models.CharField(max_length=256, blank=True)
    training_start   = models.DateField()
    training_end     = models.DateField()
    forecast_horizon = models.IntegerField()   # hours or days depending on grain
    model_name       = models.CharField(max_length=64, default='chronos-t5-small')
    mae              = models.FloatField(null=True)
    mape             = models.FloatField(null=True)
    created_at       = models.DateTimeField(auto_now_add=True)

class ForecastPoint(models.Model):
    forecast_run    = models.ForeignKey(ForecastRun, on_delete=models.CASCADE,
                                        related_name='points')
    timestamp       = models.DateTimeField(db_index=True)
    predicted_cost  = models.DecimalField(max_digits=20, decimal_places=6)
    lower_bound     = models.DecimalField(max_digits=20, decimal_places=6)
    upper_bound     = models.DecimalField(max_digits=20, decimal_places=6)
    actual_cost     = models.DecimalField(max_digits=20, decimal_places=6, null=True)
    # actual_cost backfilled when data arrives; used for accuracy tracking + anomaly detection

    class Meta:
        unique_together = [('forecast_run', 'timestamp')]
```

---

## `services/chronos_forecaster.py`

```python
import torch
import numpy as np
import pandas as pd
from chronos import ChronosPipeline


def build_context_series(account_id: str, service: str, region: str,
                          grain: str, training_start, training_end) -> torch.Tensor:
    """
    Pull historical aggregates, fill gaps, return as torch.Tensor (float32).
    Chronos expects shape [1, context_length].
    """
    if grain == 'hourly':
        qs = HourlyCostAggregate.objects.filter(
            linked_account_id=account_id, service=service, region=region,
            hour__range=(training_start, training_end)
        ).order_by('hour').values('hour', 'unblended_cost')
        freq = 'h'
        col = 'hour'
    else:
        qs = DailyCostAggregate.objects.filter(
            linked_account_id=account_id, service=service, region=region,
            date__range=(training_start, training_end)
        ).order_by('date').values('date', 'unblended_cost')
        freq = 'D'
        col = 'date'

    df = pd.DataFrame(qs).rename(columns={col: 'ts', 'unblended_cost': 'y'})
    df['ts'] = pd.to_datetime(df['ts'], utc=True)
    df = df.set_index('ts').reindex(
        pd.date_range(training_start, training_end, freq=freq, tz='UTC'),
        fill_value=0.0
    )
    values = df['y'].astype(float).values
    return torch.tensor(values, dtype=torch.float32).unsqueeze(0)  # [1, T]


def run_chronos_forecast(account_id: str, service: str, region: str,
                          grain: str, training_start, training_end,
                          horizon: int, model_name: str = 'chronos-t5-small') -> ForecastRun:
    """
    Run Chronos zero-shot forecast. Returns persisted ForecastRun.

    horizon: number of steps ahead (hours if grain='hourly', days if grain='daily')
    """
    pipeline = ChronosPipeline.from_pretrained(
        f"amazon/{model_name}",
        device_map="cpu",
        torch_dtype=torch.bfloat16,
    )

    context = build_context_series(account_id, service, region, grain,
                                    training_start, training_end)

    # Chronos returns samples: shape [num_samples, prediction_length]
    forecast_samples, quantiles = pipeline.predict(
        context=context,
        prediction_length=horizon,
        num_samples=20,
        temperature=1.0,
        top_k=50,
        top_p=1.0,
    )
    # forecast_samples: [20, horizon]
    median = np.median(forecast_samples.numpy(), axis=0)
    lower  = np.quantile(forecast_samples.numpy(), 0.025, axis=0)
    upper  = np.quantile(forecast_samples.numpy(), 0.975, axis=0)

    # Persist
    account = AwsAccount.objects.get(account_id=account_id)
    run = ForecastRun.objects.create(
        account=account, grain=grain, service=service, region=region,
        training_start=training_start, training_end=training_end,
        forecast_horizon=horizon, model_name=model_name
    )

    freq = 'h' if grain == 'hourly' else 'D'
    timestamps = pd.date_range(
        start=pd.Timestamp(training_end) + pd.tseries.frequencies.to_offset(freq),
        periods=horizon, freq=freq, tz='UTC'
    )

    points = [
        ForecastPoint(
            forecast_run=run,
            timestamp=ts,
            predicted_cost=max(0.0, float(median[i])),
            lower_bound=max(0.0, float(lower[i])),
            upper_bound=max(0.0, float(upper[i])),
        )
        for i, ts in enumerate(timestamps)
    ]
    ForecastPoint.objects.bulk_create(points)

    return run


def backfill_actuals(run: ForecastRun) -> None:
    """
    Fill in ForecastPoint.actual_cost from the aggregate tables after data arrives.
    Called by daily Celery beat task.
    """
    for point in run.points.filter(actual_cost__isnull=True):
        if run.grain == 'hourly':
            agg = HourlyCostAggregate.objects.filter(
                linked_account_id=run.account.account_id,
                service=run.service, region=run.region,
                hour=point.timestamp
            ).aggregate(total=Sum('unblended_cost'))
            actual = agg['total']
        else:
            agg = DailyCostAggregate.objects.filter(
                linked_account_id=run.account.account_id,
                service=run.service, region=run.region,
                date=point.timestamp.date()
            ).aggregate(total=Sum('unblended_cost'))
            actual = agg['total']

        if actual is not None:
            point.actual_cost = actual
            point.save(update_fields=['actual_cost'])


def compute_accuracy(run: ForecastRun) -> dict:
    """Compute MAE and MAPE for a run once actuals are backfilled."""
    points = run.points.filter(actual_cost__isnull=False)
    if not points.exists():
        return {'mae': None, 'mape': None}
    df = pd.DataFrame(points.values('predicted_cost', 'actual_cost'))
    df = df.astype(float)
    mae  = (df['actual_cost'] - df['predicted_cost']).abs().mean()
    mape = ((df['actual_cost'] - df['predicted_cost']).abs() /
             df['actual_cost'].replace(0, np.nan)).mean() * 100
    run.mae  = float(mae)
    run.mape = float(mape)
    run.save(update_fields=['mae', 'mape'])
    return {'mae': run.mae, 'mape': run.mape}
```

---

## Celery Task

```python
# tasks.py
@shared_task
def run_forecast_task(account_id, service, region, grain='hourly',
                       horizon=24, model_name='chronos-t5-small'):
    from .services.chronos_forecaster import run_chronos_forecast
    from datetime import date, timedelta
    training_end   = date.today() - timedelta(days=1)
    training_start = training_end - timedelta(days=60)
    run = run_chronos_forecast(account_id, service, region, grain,
                                training_start, training_end, horizon, model_name)
    return run.id

@shared_task
def backfill_actuals_task():
    """Daily beat task: backfill actuals for all open forecast runs."""
    from .services.chronos_forecaster import backfill_actuals, compute_accuracy
    cutoff = timezone.now() - timedelta(days=30)
    for run in ForecastRun.objects.filter(created_at__gte=cutoff):
        backfill_actuals(run)
        compute_accuracy(run)
```

---

## API Endpoints

```
POST /api/v1/forecasting/runs/
     body: {account_id, service, region, grain, horizon, model_name}
     → triggers Celery task, returns {run_id, status}

GET  /api/v1/forecasting/runs/
GET  /api/v1/forecasting/runs/{id}/
GET  /api/v1/forecasting/runs/{id}/points/     paginated ForecastPoint data
GET  /api/v1/forecasting/runs/{id}/accuracy/   {mae, mape}
```

---

## Verification

```bash
# With fake data loaded:
python manage.py shell -c "
from apps.forecasting.services.chronos_forecaster import run_chronos_forecast
from datetime import date
run = run_chronos_forecast(
    account_id='123456789012',
    service='AmazonEC2',
    region='us-east-1',
    grain='daily',
    training_start=date(2025, 1, 1),
    training_end=date(2025, 1, 24),
    horizon=7,
    model_name='chronos-t5-small'
)
print(f'ForecastRun {run.id}: {run.points.count()} points')
pts = run.points.order_by('timestamp').values('timestamp','predicted_cost','lower_bound','upper_bound')
for p in pts: print(p)
"
```

---

## NEXT

After completing Part 6, run:
**`/Users/mfeldman/.claude/plans/PART_7_anomalies.md`**
