import numpy as np
import pandas as pd


def detect_zscore_anomalies(series: pd.Series, timestamps: pd.DatetimeIndex,
                              window: int, threshold: float,
                              min_cost_delta: float) -> pd.DataFrame:
    s = pd.Series(series.values, index=timestamps)
    min_periods = max(24, window // 4)
    rolling_mean = s.rolling(window=window, min_periods=min_periods).mean()
    rolling_std = s.rolling(window=window, min_periods=min_periods).std()

    z = (s - rolling_mean) / rolling_std.replace(0, np.nan)
    is_anomaly = (z.abs() > threshold) & ((s - rolling_mean).abs() > min_cost_delta)
    direction = pd.Series(np.where(z > 0, "spike", "drop"), index=timestamps)

    return pd.DataFrame({
        "timestamp": timestamps,
        "observed": s.values,
        "baseline_mean": rolling_mean.values,
        "baseline_std": rolling_std.values,
        "z_score": z.values,
        "is_anomaly": is_anomaly.values,
        "direction": direction.values,
    })
