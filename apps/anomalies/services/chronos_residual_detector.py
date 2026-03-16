import numpy as np
import pandas as pd


def detect_chronos_residuals(forecast_run_id: int,
                               sigma_threshold: float = 3.0,
                               min_cost_delta: float = 5.0) -> pd.DataFrame:
    from apps.forecasting.models import ForecastPoint

    points = list(ForecastPoint.objects.filter(
        forecast_run_id=forecast_run_id,
        actual_cost__isnull=False,
    ).values("timestamp", "predicted_cost", "actual_cost", "lower_bound", "upper_bound"))

    if not points:
        return pd.DataFrame()

    df = pd.DataFrame(points)
    for col in ("predicted_cost", "actual_cost", "lower_bound", "upper_bound"):
        df[col] = df[col].astype(float)

    ci_width = df["upper_bound"] - df["lower_bound"]
    predicted_std = ci_width / 3.92

    df["residual"] = df["actual_cost"] - df["predicted_cost"]
    df["chronos_sigma"] = df["residual"].abs() / predicted_std.replace(0, np.nan)
    df["is_anomaly"] = (
        (df["chronos_sigma"] > sigma_threshold) &
        (df["residual"].abs() > min_cost_delta)
    )
    df["direction"] = np.where(df["residual"] > 0, "spike", "drop")

    return df[["timestamp", "actual_cost", "predicted_cost", "chronos_sigma", "is_anomaly", "direction"]]
