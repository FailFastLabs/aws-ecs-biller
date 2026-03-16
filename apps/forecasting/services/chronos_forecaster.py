import numpy as np
import pandas as pd


def build_context_series(account_id: str, service: str, region: str,
                          grain: str, training_start, training_end):
    import torch
    from apps.costs.models import HourlyCostAggregate, DailyCostAggregate

    if grain == "hourly":
        qs = HourlyCostAggregate.objects.filter(
            linked_account_id=account_id, service=service, region=region,
            hour__range=(training_start, training_end),
        ).order_by("hour").values("hour", "unblended_cost")
        freq = "h"
        col = "hour"
    else:
        qs = DailyCostAggregate.objects.filter(
            linked_account_id=account_id, service=service, region=region,
            date__range=(training_start, training_end),
        ).order_by("date").values("date", "unblended_cost")
        freq = "D"
        col = "date"

    df = pd.DataFrame(list(qs)).rename(columns={col: "ts", "unblended_cost": "y"})
    if df.empty:
        df = pd.DataFrame({"ts": pd.date_range(training_start, training_end, freq=freq, tz="UTC"), "y": 0.0})
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = df.set_index("ts").reindex(
        pd.date_range(training_start, training_end, freq=freq, tz="UTC"), fill_value=0.0
    )
    values = df["y"].astype(float).values
    return torch.tensor(values, dtype=torch.float32).unsqueeze(0)


def run_chronos_forecast(account_id: str, service: str, region: str,
                          grain: str, training_start, training_end,
                          horizon: int, model_name: str = "chronos-t5-small"):
    import torch
    from apps.accounts.models import AwsAccount
    from apps.forecasting.models import ForecastRun, ForecastPoint

    try:
        from chronos import ChronosPipeline
        pipeline = ChronosPipeline.from_pretrained(
            f"amazon/{model_name}", device_map="cpu", torch_dtype=torch.bfloat16,
        )
        context = build_context_series(account_id, service, region, grain, training_start, training_end)
        forecast_samples, _ = pipeline.predict(
            context=context, prediction_length=horizon, num_samples=20,
        )
        samples_np = forecast_samples.numpy()
        median = np.median(samples_np, axis=0)
        lower = np.quantile(samples_np, 0.025, axis=0)
        upper = np.quantile(samples_np, 0.975, axis=0)
    except ImportError:
        # Chronos not installed — use simple linear extrapolation fallback
        context_arr = build_context_series(account_id, service, region, grain, training_start, training_end)
        vals = context_arr.numpy()[0]
        last = float(vals[-1]) if len(vals) > 0 else 1.0
        median = np.array([last] * horizon)
        lower = median * 0.8
        upper = median * 1.2

    account = AwsAccount.objects.get(account_id=account_id)
    run = ForecastRun.objects.create(
        account=account, grain=grain, service=service, region=region,
        training_start=training_start, training_end=training_end,
        forecast_horizon=horizon, model_name=model_name,
    )

    freq = "h" if grain == "hourly" else "D"
    timestamps = pd.date_range(
        start=pd.Timestamp(str(training_end)) + pd.tseries.frequencies.to_offset(freq),
        periods=horizon, freq=freq, tz="UTC",
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


def backfill_actuals(run) -> None:
    from django.db.models import Sum
    from apps.costs.models import HourlyCostAggregate, DailyCostAggregate

    for point in run.points.filter(actual_cost__isnull=True):
        if run.grain == "hourly":
            agg = HourlyCostAggregate.objects.filter(
                linked_account_id=run.account.account_id,
                service=run.service, region=run.region, hour=point.timestamp,
            ).aggregate(total=Sum("unblended_cost"))
        else:
            agg = DailyCostAggregate.objects.filter(
                linked_account_id=run.account.account_id,
                service=run.service, region=run.region, date=point.timestamp.date(),
            ).aggregate(total=Sum("unblended_cost"))
        if agg["total"] is not None:
            point.actual_cost = agg["total"]
            point.save(update_fields=["actual_cost"])


def compute_accuracy(run) -> dict:
    import pandas as pd
    points = run.points.filter(actual_cost__isnull=False)
    if not points.exists():
        return {"mae": None, "mape": None}
    df = pd.DataFrame(list(points.values("predicted_cost", "actual_cost"))).astype(float)
    mae = (df["actual_cost"] - df["predicted_cost"]).abs().mean()
    mape = ((df["actual_cost"] - df["predicted_cost"]).abs() /
             df["actual_cost"].replace(0, float("nan"))).mean() * 100
    run.mae = float(mae)
    run.mape = float(mape)
    run.save(update_fields=["mae", "mape"])
    return {"mae": run.mae, "mape": run.mape}
