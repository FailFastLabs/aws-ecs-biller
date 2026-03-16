import pandas as pd
from .zscore_detector import detect_zscore_anomalies
from .chronos_residual_detector import detect_chronos_residuals


def run_ensemble_detection(account_id: str, service: str, region: str,
                             grain: str, window_hours: int = 168,
                             sigma_threshold: float = 3.5,
                             min_cost_delta: float = 5.0) -> list:
    from apps.costs.models import HourlyCostAggregate, DailyCostAggregate
    from apps.forecasting.models import ForecastRun
    from apps.accounts.models import AwsAccount
    from apps.anomalies.models import AnomalyDetectionRun, CostAnomaly

    if grain == "hourly":
        qs = HourlyCostAggregate.objects.filter(
            linked_account_id=account_id, service=service, region=region,
        ).order_by("hour").values("hour", "unblended_cost")
        df = pd.DataFrame(list(qs))
        if df.empty:
            return []
        df["ts"] = pd.to_datetime(df["hour"], utc=True)
        series = df["unblended_cost"].astype(float)
        timestamps = pd.DatetimeIndex(df["ts"])
    else:
        qs = DailyCostAggregate.objects.filter(
            linked_account_id=account_id, service=service, region=region,
        ).order_by("date").values("date", "unblended_cost")
        df = pd.DataFrame(list(qs))
        if df.empty:
            return []
        df["ts"] = pd.to_datetime(df["date"], utc=True)
        series = df["unblended_cost"].astype(float)
        timestamps = pd.DatetimeIndex(df["ts"])

    zscore_df = detect_zscore_anomalies(series, timestamps, window=window_hours,
                                         threshold=sigma_threshold, min_cost_delta=min_cost_delta)
    zscore_flags = set(zscore_df[zscore_df["is_anomaly"]]["timestamp"].tolist())

    forecast_run = ForecastRun.objects.filter(
        account__account_id=account_id, service=service, region=region, grain=grain,
    ).order_by("-created_at").first()

    chronos_flags = set()
    chronos_df = pd.DataFrame()
    if forecast_run:
        chronos_df = detect_chronos_residuals(forecast_run.id, sigma_threshold, min_cost_delta)
        if not chronos_df.empty:
            chronos_flags = set(chronos_df[chronos_df["is_anomaly"]]["timestamp"].tolist())

    confirmed = zscore_flags & chronos_flags if chronos_flags else zscore_flags

    try:
        account = AwsAccount.objects.get(account_id=account_id)
    except AwsAccount.DoesNotExist:
        return []

    det_run = AnomalyDetectionRun.objects.create(
        account=account, grain=grain,
        method="ensemble" if chronos_flags else "zscore",
        window_hours=window_hours,
        sigma_threshold=sigma_threshold,
        min_cost_delta=min_cost_delta,
    )

    anomalies = []
    for ts in confirmed:
        z_rows = zscore_df[zscore_df["timestamp"] == ts]
        if z_rows.empty:
            continue
        z_row = z_rows.iloc[0]
        c_row = None
        if not chronos_df.empty:
            c_rows = chronos_df[chronos_df["timestamp"] == ts]
            if not c_rows.empty:
                c_row = c_rows.iloc[0]

        baseline = float(z_row["baseline_mean"]) if not pd.isna(z_row["baseline_mean"]) else 0.0
        observed = float(z_row["observed"])
        pct = ((observed - baseline) / max(baseline, 0.01)) * 100

        anomaly = CostAnomaly.objects.create(
            detection_run=det_run,
            service=service, region=region, usage_type="",
            linked_account_id=account_id,
            period_start=ts,
            period_end=ts + pd.Timedelta(hours=1 if grain == "hourly" else 24),
            direction=str(z_row["direction"]),
            baseline_cost=baseline,
            observed_cost=observed,
            pct_change=pct,
            z_score=float(z_row["z_score"]) if not pd.isna(z_row["z_score"]) else None,
            chronos_sigma=float(c_row["chronos_sigma"]) if c_row is not None and not pd.isna(c_row["chronos_sigma"]) else None,
            detected_by=det_run.method,
        )
        anomalies.append(anomaly)

    return anomalies
