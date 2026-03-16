import numpy as np
import pandas as pd


def _to_aware(d):
    """Convert a date or naive datetime to a UTC-aware datetime."""
    from datetime import date, datetime, timezone as dt_tz
    if isinstance(d, datetime):
        return d if d.tzinfo else d.replace(tzinfo=dt_tz.utc)
    return datetime(d.year, d.month, d.day, tzinfo=dt_tz.utc)


def _fetch_daily_series(account_id, region, training_start, training_end,
                         service="", instance_type=""):
    """Return a DataFrame with columns [ts, y] aggregated by calendar day.

    Routing:
      - level 1 (region only):               DailyCostAggregate, all services
      - level 2 (region + service):           DailyCostAggregate, filtered by service
      - level 3 (region + service + itype):   LineItem, TruncDate
    """
    from django.db.models import Sum
    from django.db.models.functions import TruncDate
    from apps.costs.models import DailyCostAggregate, LineItem

    t_start = _to_aware(training_start)
    t_end   = _to_aware(training_end)

    if instance_type:
        qs = (
            LineItem.objects
            .filter(
                linked_account_id=account_id,
                service=service, region=region, instance_type=instance_type,
                usage_start__range=(t_start, t_end),
            )
            .annotate(ts=TruncDate("usage_start"))
            .values("ts")
            .annotate(y=Sum("unblended_cost"))
            .order_by("ts")
        )
    elif service:
        qs = (
            DailyCostAggregate.objects
            .filter(
                linked_account_id=account_id,
                service=service, region=region,
                date__range=(t_start.date(), t_end.date()),
            )
            .values("date")
            .annotate(y=Sum("unblended_cost"))
            .order_by("date")
        )
    else:
        qs = (
            DailyCostAggregate.objects
            .filter(
                linked_account_id=account_id,
                region=region,
                date__range=(t_start.date(), t_end.date()),
            )
            .values("date")
            .annotate(y=Sum("unblended_cost"))
            .order_by("date")
        )

    rows = list(qs)
    if not rows:
        return pd.DataFrame(columns=["ts", "y"])
    df = pd.DataFrame(rows)
    # Normalise the date column name
    if "date" in df.columns:
        df = df.rename(columns={"date": "ts"})
    return df[["ts", "y"]]


def _fetch_hourly_series(account_id, region, training_start, training_end,
                          service="", instance_type=""):
    """Return a DataFrame with columns [ts, y] aggregated by hour."""
    from django.db.models import Sum
    from django.db.models.functions import TruncHour
    from apps.costs.models import HourlyCostAggregate, LineItem

    t_start = _to_aware(training_start)
    t_end   = _to_aware(training_end)

    if instance_type:
        qs = (
            LineItem.objects
            .filter(
                linked_account_id=account_id,
                service=service, region=region, instance_type=instance_type,
                usage_start__range=(t_start, t_end),
            )
            .annotate(ts=TruncHour("usage_start"))
            .values("ts")
            .annotate(y=Sum("unblended_cost"))
            .order_by("ts")
        )
    elif service:
        qs = (
            HourlyCostAggregate.objects
            .filter(
                linked_account_id=account_id,
                service=service, region=region,
                hour__range=(t_start, t_end),
            )
            .values("hour")
            .annotate(y=Sum("unblended_cost"))
            .order_by("hour")
        )
    else:
        qs = (
            HourlyCostAggregate.objects
            .filter(
                linked_account_id=account_id,
                region=region,
                hour__range=(t_start, t_end),
            )
            .values("hour")
            .annotate(y=Sum("unblended_cost"))
            .order_by("hour")
        )

    rows = list(qs)
    if not rows:
        return pd.DataFrame(columns=["ts", "y"])
    df = pd.DataFrame(rows)
    if "hour" in df.columns:
        df = df.rename(columns={"hour": "ts"})
    return df[["ts", "y"]]


def build_context_array(account_id: str, region: str, grain: str,
                         training_start, training_end,
                         service: str = "", instance_type: str = "") -> np.ndarray:
    """Return a 1-D numpy float32 array of historical costs (no torch dependency)."""
    if grain == "hourly":
        df = _fetch_hourly_series(account_id, region, training_start, training_end,
                                   service=service, instance_type=instance_type)
        freq = "h"
    else:
        df = _fetch_daily_series(account_id, region, training_start, training_end,
                                  service=service, instance_type=instance_type)
        freq = "D"

    if df.empty:
        df = pd.DataFrame({
            "ts": pd.date_range(training_start, training_end, freq=freq, tz="UTC"),
            "y": 0.0,
        })

    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = df.set_index("ts").reindex(
        pd.date_range(training_start, training_end, freq=freq, tz="UTC"), fill_value=0.0
    )
    return df["y"].astype(np.float32).values


def build_context_series(account_id: str, region: str, grain: str,
                          training_start, training_end,
                          service: str = "", instance_type: str = ""):
    """Build a PyTorch tensor of shape (1, T) for Chronos input."""
    import torch
    values = build_context_array(account_id, region, grain, training_start, training_end,
                                  service=service, instance_type=instance_type)
    return torch.tensor(values, dtype=torch.float32).unsqueeze(0)


def run_chronos_forecast(account_id: str, region: str,
                          grain: str, training_start, training_end,
                          horizon: int, model_name: str = "chronos-t5-small",
                          service: str = "", instance_type: str = ""):
    """Run a Chronos forecast (with linear fallback) for one grouping combination.

    Grouping levels:
      service=""  + instance_type=""  → level 1 (region)
      service!="" + instance_type=""  → level 2 (region + service)
      service!="" + instance_type!="" → level 3 (region + service + instance_type)
    """
    from apps.accounts.models import AwsAccount
    from apps.forecasting.models import (
        ForecastRun, ForecastPoint,
        GROUPING_REGION, GROUPING_REGION_SERVICE, GROUPING_REGION_SERVICE_INSTANCE,
    )

    if instance_type:
        grouping_level = GROUPING_REGION_SERVICE_INSTANCE
    elif service:
        grouping_level = GROUPING_REGION_SERVICE
    else:
        grouping_level = GROUPING_REGION

    vals = build_context_array(account_id, region, grain, training_start, training_end,
                                service=service, instance_type=instance_type)

    try:
        import torch
        from chronos import ChronosPipeline
        context = torch.tensor(vals, dtype=torch.float32).unsqueeze(0)
        pipeline = ChronosPipeline.from_pretrained(
            f"amazon/{model_name}", device_map="cpu", torch_dtype=torch.bfloat16,
        )
        forecast_samples, _ = pipeline.predict(
            context=context, prediction_length=horizon, num_samples=20,
        )
        samples_np = forecast_samples.numpy()
        median = np.median(samples_np, axis=0)
        lower = np.quantile(samples_np, 0.025, axis=0)
        upper = np.quantile(samples_np, 0.975, axis=0)
    except ImportError:
        # torch or chronos not installed — linear extrapolation fallback
        window = min(7, len(vals))
        baseline = float(np.mean(vals[-window:])) if window > 0 else 1.0
        median = np.array([baseline] * horizon)
        lower = median * 0.8
        upper = median * 1.2

    account = AwsAccount.objects.get(account_id=account_id)
    run = ForecastRun.objects.create(
        account=account,
        grain=grain,
        grouping_level=grouping_level,
        service=service,
        region=region,
        instance_type=instance_type,
        training_start=training_start,
        training_end=training_end,
        forecast_horizon=horizon,
        model_name=model_name,
    )

    freq = "h" if grain == "hourly" else "D"
    timestamps = pd.date_range(
        start=pd.Timestamp(str(training_end)) + pd.tseries.frequencies.to_offset(freq),
        periods=horizon, freq=freq, tz="UTC",
    )
    ForecastPoint.objects.bulk_create([
        ForecastPoint(
            forecast_run=run,
            timestamp=ts,
            predicted_cost=max(0.0, float(median[i])),
            lower_bound=max(0.0, float(lower[i])),
            upper_bound=max(0.0, float(upper[i])),
        )
        for i, ts in enumerate(timestamps)
    ])
    return run


def backfill_actuals(run) -> None:
    from django.db.models import Sum
    from apps.costs.models import HourlyCostAggregate, DailyCostAggregate, LineItem

    for point in run.points.filter(actual_cost__isnull=True):
        if run.instance_type:
            # Level 3: LineItem
            if run.grain == "hourly":
                agg = LineItem.objects.filter(
                    linked_account_id=run.account.account_id,
                    service=run.service, region=run.region, instance_type=run.instance_type,
                    usage_start__gte=point.timestamp,
                    usage_start__lt=point.timestamp + pd.Timedelta(hours=1),
                ).aggregate(total=Sum("unblended_cost"))
            else:
                agg = LineItem.objects.filter(
                    linked_account_id=run.account.account_id,
                    service=run.service, region=run.region, instance_type=run.instance_type,
                    usage_start__date=point.timestamp.date(),
                ).aggregate(total=Sum("unblended_cost"))
        elif run.service:
            # Level 2: aggregates filtered by service
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
        else:
            # Level 1: all services in region
            if run.grain == "hourly":
                agg = HourlyCostAggregate.objects.filter(
                    linked_account_id=run.account.account_id,
                    region=run.region, hour=point.timestamp,
                ).aggregate(total=Sum("unblended_cost"))
            else:
                agg = DailyCostAggregate.objects.filter(
                    linked_account_id=run.account.account_id,
                    region=run.region, date=point.timestamp.date(),
                ).aggregate(total=Sum("unblended_cost"))

        if agg["total"] is not None:
            point.actual_cost = agg["total"]
            point.save(update_fields=["actual_cost"])


def compute_accuracy(run) -> dict:
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
