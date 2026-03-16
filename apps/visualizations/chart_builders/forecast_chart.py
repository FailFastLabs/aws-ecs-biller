def build_forecast_chart(forecast_run_id: int) -> dict:
    from apps.forecasting.models import ForecastPoint
    points = list(ForecastPoint.objects.filter(
        forecast_run_id=forecast_run_id
    ).order_by("timestamp").values("timestamp", "predicted_cost", "lower_bound", "upper_bound", "actual_cost"))

    if not points:
        return {"data": [], "layout": {"title": "Forecast"}}

    x = [str(p["timestamp"]) for p in points]
    predicted = [float(p["predicted_cost"]) for p in points]
    lower = [float(p["lower_bound"]) for p in points]
    upper = [float(p["upper_bound"]) for p in points]
    actual = [float(p["actual_cost"]) if p["actual_cost"] is not None else None for p in points]

    traces = [
        {"type": "scatter", "mode": "lines", "name": "Predicted", "x": x, "y": predicted},
        {"type": "scatter", "mode": "lines", "name": "Upper 95%", "x": x, "y": upper,
         "line": {"dash": "dot"}, "fill": None},
        {"type": "scatter", "mode": "lines", "name": "Lower 95%", "x": x, "y": lower,
         "line": {"dash": "dot"}, "fill": "tonexty", "fillcolor": "rgba(0,100,255,0.1)"},
        {"type": "scatter", "mode": "markers", "name": "Actual", "x": x, "y": actual,
         "marker": {"color": "green"}},
    ]
    return {
        "data": traces,
        "layout": {"title": f"Forecast Run #{forecast_run_id}", "xaxis": {"title": "Time"}, "yaxis": {"title": "USD"}},
    }
