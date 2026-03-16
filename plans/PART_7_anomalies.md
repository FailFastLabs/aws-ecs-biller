# PART 7 — Anomaly Detection

## Objective
Detect cost anomalies using two signals: Chronos forecast residuals (primary) and
rolling Z-score (secondary). Persist only when both agree AND delta > $5.

---

## App: `apps/anomalies/`

### `models.py`

```python
class AnomalyDetectionRun(models.Model):
    account      = models.ForeignKey('accounts.AwsAccount', on_delete=models.CASCADE)
    grain        = models.CharField(max_length=16)   # hourly | daily
    method       = models.CharField(max_length=32)   # ensemble | zscore | chronos_residual
    window_hours = models.IntegerField()              # lookback window for Z-score baseline
    sigma_threshold = models.FloatField(default=3.5) # for hourly; 3.0 for daily
    min_cost_delta  = models.DecimalField(max_digits=10, decimal_places=2, default=5.00)
    created_at   = models.DateTimeField(auto_now_add=True)

class CostAnomaly(models.Model):
    DIRECTION = [('spike','spike'), ('drop','drop')]
    detection_run  = models.ForeignKey(AnomalyDetectionRun, on_delete=models.CASCADE)
    service        = models.CharField(max_length=128, db_index=True)
    region         = models.CharField(max_length=64)
    usage_type     = models.CharField(max_length=256)
    linked_account_id = models.CharField(max_length=12)
    period_start   = models.DateTimeField()
    period_end     = models.DateTimeField()
    direction      = models.CharField(choices=DIRECTION)
    baseline_cost  = models.DecimalField(max_digits=20, decimal_places=6)
    observed_cost  = models.DecimalField(max_digits=20, decimal_places=6)
    pct_change     = models.FloatField()
    z_score        = models.FloatField(null=True)
    chronos_sigma  = models.FloatField(null=True)   # |residual| / predicted_std
    detected_by    = models.CharField(max_length=32, default='ensemble')
    acknowledged   = models.BooleanField(default=False)
    acknowledged_by = models.ForeignKey('auth.User', null=True, on_delete=models.SET_NULL)
    notes          = models.TextField(blank=True)
```

---

## Services

### `services/zscore_detector.py`

```python
def detect_zscore_anomalies(series: pd.Series, timestamps: pd.DatetimeIndex,
                              window: int, threshold: float,
                              min_cost_delta: float) -> pd.DataFrame:
    """
    Rolling Z-score anomaly detection.

    Args:
        series:    hourly or daily unblended_cost values
        window:    rolling window size (168 for hourly/7d, 30 for daily/30d)
        threshold: sigma threshold (3.5 hourly, 3.0 daily)
        min_cost_delta: minimum |observed - baseline| to trigger

    Returns DataFrame with columns:
        [timestamp, observed, baseline_mean, baseline_std, z_score, is_anomaly, direction]
    """
    s = pd.Series(series.values, index=timestamps)
    rolling_mean = s.rolling(window=window, min_periods=max(24, window // 4)).mean()
    rolling_std  = s.rolling(window=window, min_periods=max(24, window // 4)).std()

    z = (s - rolling_mean) / rolling_std.replace(0, np.nan)

    is_anomaly = (z.abs() > threshold) & ((s - rolling_mean).abs() > min_cost_delta)
    direction  = pd.Series(np.where(z > 0, 'spike', 'drop'), index=timestamps)

    return pd.DataFrame({
        'timestamp':     timestamps,
        'observed':      s.values,
        'baseline_mean': rolling_mean.values,
        'baseline_std':  rolling_std.values,
        'z_score':       z.values,
        'is_anomaly':    is_anomaly.values,
        'direction':     direction.values,
    })
```

### `services/chronos_residual_detector.py`

```python
def detect_chronos_residuals(forecast_run_id: int,
                               sigma_threshold: float = 3.0,
                               min_cost_delta: float = 5.0) -> pd.DataFrame:
    """
    Compares actual_cost to predicted_cost from a ForecastRun.
    Uses predicted CI width as a proxy for predicted_std.

    chronos_sigma = |actual - predicted| / ((upper_bound - lower_bound) / 3.92)
    (3.92 = 2 * 1.96 for 95% CI)

    Returns DataFrame: [timestamp, observed, predicted, chronos_sigma, is_anomaly, direction]
    """
    points = ForecastPoint.objects.filter(
        forecast_run_id=forecast_run_id,
        actual_cost__isnull=False
    ).values('timestamp', 'predicted_cost', 'actual_cost', 'lower_bound', 'upper_bound')

    if not points:
        return pd.DataFrame()

    df = pd.DataFrame(points).astype({
        'predicted_cost': float, 'actual_cost': float,
        'lower_bound': float, 'upper_bound': float
    })

    ci_width = df['upper_bound'] - df['lower_bound']
    predicted_std = ci_width / 3.92  # convert 95% CI to sigma

    df['residual']      = df['actual_cost'] - df['predicted_cost']
    df['chronos_sigma'] = df['residual'].abs() / predicted_std.replace(0, np.nan)
    df['is_anomaly']    = (
        (df['chronos_sigma'] > sigma_threshold) &
        (df['residual'].abs() > min_cost_delta)
    )
    df['direction'] = np.where(df['residual'] > 0, 'spike', 'drop')

    return df[['timestamp','actual_cost','predicted_cost','chronos_sigma','is_anomaly','direction']]
```

### `services/ensemble.py`

```python
def run_ensemble_detection(account_id: str, service: str, region: str,
                             grain: str, window_hours: int = 168,
                             sigma_threshold: float = 3.5,
                             min_cost_delta: float = 5.0) -> list[CostAnomaly]:
    """
    An anomaly is persisted only when BOTH signals agree:
    - Z-score: is_anomaly = True
    - Chronos residual: is_anomaly = True (from most recent ForecastRun for this series)

    Falls back to Z-score only if no Chronos ForecastRun exists for this series.
    """
    # 1. Pull hourly or daily series
    if grain == 'hourly':
        qs = HourlyCostAggregate.objects.filter(
            linked_account_id=account_id, service=service, region=region
        ).order_by('hour').values('hour', 'unblended_cost')
        df = pd.DataFrame(qs)
        df['ts'] = pd.to_datetime(df['hour'], utc=True)
        series = df['unblended_cost'].astype(float)
        timestamps = df['ts']
    else:
        qs = DailyCostAggregate.objects.filter(
            linked_account_id=account_id, service=service, region=region
        ).order_by('date').values('date', 'unblended_cost')
        df = pd.DataFrame(qs)
        df['ts'] = pd.to_datetime(df['date'], utc=True)
        series = df['unblended_cost'].astype(float)
        timestamps = df['ts']

    # 2. Z-score detection
    zscore_df = detect_zscore_anomalies(series, timestamps, window=window_hours,
                                         threshold=sigma_threshold,
                                         min_cost_delta=min_cost_delta)
    zscore_flags = set(zscore_df[zscore_df['is_anomaly']]['timestamp'].tolist())

    # 3. Chronos residual detection (if run exists)
    forecast_run = ForecastRun.objects.filter(
        account__account_id=account_id, service=service, region=region, grain=grain
    ).order_by('-created_at').first()

    chronos_flags = set()
    chronos_df = pd.DataFrame()
    if forecast_run:
        chronos_df = detect_chronos_residuals(forecast_run.id, sigma_threshold, min_cost_delta)
        if not chronos_df.empty:
            chronos_flags = set(chronos_df[chronos_df['is_anomaly']]['timestamp'].tolist())

    # 4. Ensemble: both must agree (or z-score only if no Chronos run)
    if chronos_flags:
        confirmed = zscore_flags & chronos_flags
    else:
        confirmed = zscore_flags  # fallback

    # 5. Persist confirmed anomalies
    det_run = AnomalyDetectionRun.objects.create(
        account=AwsAccount.objects.get(account_id=account_id),
        grain=grain, method='ensemble' if chronos_flags else 'zscore',
        window_hours=window_hours, sigma_threshold=sigma_threshold,
        min_cost_delta=min_cost_delta
    )

    anomalies = []
    for ts in confirmed:
        z_row = zscore_df[zscore_df['timestamp'] == ts].iloc[0]
        c_row = chronos_df[chronos_df['timestamp'] == ts].iloc[0] if not chronos_df.empty else None

        anomaly = CostAnomaly.objects.create(
            detection_run=det_run,
            service=service, region=region,
            usage_type='',  # aggregate level
            linked_account_id=account_id,
            period_start=ts,
            period_end=ts + pd.Timedelta(hours=1 if grain == 'hourly' else 24),
            direction=z_row['direction'],
            baseline_cost=z_row['baseline_mean'],
            observed_cost=z_row['observed'],
            pct_change=((z_row['observed'] - z_row['baseline_mean']) /
                         max(z_row['baseline_mean'], 0.01)) * 100,
            z_score=float(z_row['z_score']),
            chronos_sigma=float(c_row['chronos_sigma']) if c_row is not None else None,
            detected_by=det_run.method,
        )
        anomalies.append(anomaly)

    return anomalies
```

---

## Celery Task

```python
@shared_task
def run_anomaly_detection_task():
    """Daily beat: run ensemble detector for all active account/service/region combos."""
    combos = (HourlyCostAggregate.objects
              .values('linked_account_id', 'service', 'region')
              .distinct())
    for combo in combos:
        run_ensemble_detection(
            account_id=combo['linked_account_id'],
            service=combo['service'],
            region=combo['region'],
            grain='hourly',
        )
```

---

## API Endpoints

```
POST /api/v1/anomalies/runs/                  trigger detection for a series
GET  /api/v1/anomalies/                       list CostAnomaly, filterable
     ?service=AmazonEC2&direction=spike&acknowledged=false
GET  /api/v1/anomalies/summary/               {spike_count, drop_count, top_services}
PATCH /api/v1/anomalies/{id}/acknowledge/     body: {notes: "..."}
```

---

## Verification

The fake data from Part 0 contains an anomaly week (Jan 13–17, EC2 us-east-1 at 3× normal).
After loading that data and running a forecast (Part 6):

```bash
python manage.py shell -c "
from apps.anomalies.services.ensemble import run_ensemble_detection
anomalies = run_ensemble_detection(
    account_id='123456789012',
    service='AmazonEC2',
    region='us-east-1',
    grain='daily',
    sigma_threshold=2.5,  # lower threshold for daily data over short window
    min_cost_delta=5.0,
)
print(f'Detected {len(anomalies)} anomalies')
for a in anomalies:
    print(f'  {a.period_start.date()} {a.direction} z={a.z_score:.2f} pct={a.pct_change:.1f}%')
# Expected: spikes on dates in Jan 13-17 window
"
```

---

## NEXT

After completing Part 7, run:
**`/Users/mfeldman/.claude/plans/PART_8_splitting.md`**
