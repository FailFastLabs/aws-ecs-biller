def build_forecast_chart(forecast_run_id: int, history_days: int = 30) -> dict:
    """Build a Plotly chart showing historical data flowing into the forecast window.

    Traces:
      1. History  — actual past costs up to training_end
      2. Predicted — forecast median
      3. CI band   — upper/lower 95% bounds (filled)
      4. Actual    — actuals that have been backfilled into forecast points
    """
    import pandas as pd
    from django.db.models import Sum
    from apps.forecasting.models import ForecastRun, ForecastPoint

    try:
        run = ForecastRun.objects.get(pk=forecast_run_id)
    except ForecastRun.DoesNotExist:
        return {"data": [], "layout": {"title": "Forecast"}}

    points = list(
        ForecastPoint.objects
        .filter(forecast_run_id=forecast_run_id)
        .order_by("timestamp")
        .values("timestamp", "predicted_cost", "lower_bound", "upper_bound", "actual_cost")
    )
    if not points:
        return {"data": [], "layout": {"title": "Forecast"}}

    # ── Historical context ─────────────────────────────────────────────────
    from datetime import timedelta
    hist_start = run.training_end - timedelta(days=history_days)

    if run.grain == "hourly":
        from apps.costs.models import HourlyCostAggregate
        hist_qs = (
            HourlyCostAggregate.objects
            .filter(
                linked_account_id=run.account.account_id,
                hour__date__range=(hist_start, run.training_end),
                **({"service": run.service} if run.service else {}),
                **({"region":  run.region}  if run.region  else {}),
            )
            .values("hour")
            .annotate(cost=Sum("unblended_cost"))
            .order_by("hour")
        )
        hist_rows = [(str(r["hour"]), float(r["cost"])) for r in hist_qs]
    else:
        from apps.costs.models import DailyCostAggregate
        filters = dict(date__range=(hist_start, run.training_end))
        if run.service:
            filters["service"] = run.service
        if run.region:
            filters["region"] = run.region
        if run.account_id:
            filters["linked_account_id"] = run.account.account_id
        hist_qs = (
            DailyCostAggregate.objects
            .filter(**filters)
            .values("date")
            .annotate(cost=Sum("unblended_cost"))
            .order_by("date")
        )
        hist_rows = [(str(r["date"]), float(r["cost"])) for r in hist_qs]

    # Also handle L3 (instance_type): fall back to LineItem
    if run.instance_type and not hist_rows:
        from django.db.models.functions import TruncDate, TruncHour
        from apps.costs.models import LineItem
        trunc_fn = TruncHour if run.grain == "hourly" else TruncDate
        trunc_col = "hour_ts" if run.grain == "hourly" else "day_ts"
        hist_qs = (
            LineItem.objects
            .filter(
                linked_account_id=run.account.account_id,
                service=run.service, region=run.region,
                instance_type=run.instance_type,
                usage_start__date__range=(hist_start, run.training_end),
            )
            .annotate(**{trunc_col: trunc_fn("usage_start")})
            .values(trunc_col)
            .annotate(cost=Sum("unblended_cost"))
            .order_by(trunc_col)
        )
        hist_rows = [(str(r[trunc_col]), float(r["cost"])) for r in hist_qs]

    # ── Forecast series ────────────────────────────────────────────────────
    fx = [str(p["timestamp"]) for p in points]
    predicted = [float(p["predicted_cost"]) for p in points]
    lower     = [float(p["lower_bound"])    for p in points]
    upper     = [float(p["upper_bound"])    for p in points]
    actual    = [float(p["actual_cost"]) if p["actual_cost"] is not None else None for p in points]

    # Build label for chart title
    parts = []
    if run.region:
        parts.append(run.region)
    if run.service:
        parts.append(run.service)
    if run.instance_type:
        parts.append(run.instance_type)
    label = " / ".join(parts) if parts else f"Run #{forecast_run_id}"

    traces = []

    # History trace
    if hist_rows:
        hx = [r[0] for r in hist_rows]
        hy = [r[1] for r in hist_rows]
        traces.append({
            "type": "scatter", "mode": "lines", "name": "History",
            "x": hx, "y": hy,
            "line": {"color": "#6c757d", "width": 1.5},
        })

    # CI band (upper → lower filled)
    traces.append({
        "type": "scatter", "mode": "lines", "name": "Upper 95%",
        "x": fx, "y": upper,
        "line": {"dash": "dot", "color": "rgba(13,110,253,0.4)", "width": 1},
        "showlegend": False,
    })
    traces.append({
        "type": "scatter", "mode": "lines", "name": "Lower 95%",
        "x": fx, "y": lower,
        "line": {"dash": "dot", "color": "rgba(13,110,253,0.4)", "width": 1},
        "fill": "tonexty", "fillcolor": "rgba(13,110,253,0.10)",
        "showlegend": False,
    })

    # Predicted trace
    traces.append({
        "type": "scatter", "mode": "lines+markers", "name": "Forecast",
        "x": fx, "y": predicted,
        "line": {"color": "#0d6efd", "width": 2.5},
        "marker": {"size": 5},
    })

    # Actual (backfilled)
    if any(v is not None for v in actual):
        traces.append({
            "type": "scatter", "mode": "markers", "name": "Actual",
            "x": fx, "y": actual,
            "marker": {"color": "#198754", "size": 7, "symbol": "circle-open"},
        })

    # Vertical line at forecast start (as a shape)
    forecast_start = fx[0] if fx else None
    shapes = []
    if forecast_start:
        shapes.append({
            "type": "line", "x0": forecast_start, "x1": forecast_start,
            "y0": 0, "y1": 1, "yref": "paper",
            "line": {"color": "#dc3545", "width": 1.5, "dash": "dashdot"},
        })

    return {
        "data": traces,
        "layout": {
            "title": f"{label} ({run.grain})",
            "xaxis": {"title": "Date", "showgrid": True, "gridcolor": "#f0f0f0"},
            "yaxis": {"title": "USD", "showgrid": True, "gridcolor": "#f0f0f0"},
            "shapes": shapes,
            "legend": {"orientation": "h", "y": -0.15},
            "plot_bgcolor": "white",
            "paper_bgcolor": "white",
            "hovermode": "x unified",
        },
    }
