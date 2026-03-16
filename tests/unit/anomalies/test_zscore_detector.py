import numpy as np
import pandas as pd
import pytest
from apps.anomalies.services.zscore_detector import detect_zscore_anomalies


def make_series(n=200, spike_idx=None, spike_val=None, base=10.0):
    values = [base] * n
    if spike_idx is not None:
        values[spike_idx] = spike_val
    series = pd.Series(values)
    timestamps = pd.date_range("2025-01-01", periods=n, freq="h", tz="UTC")
    return series, timestamps


def test_zscore_detects_spike():
    series, timestamps = make_series(spike_idx=180, spike_val=100.0)
    result = detect_zscore_anomalies(series, timestamps, window=168, threshold=3.0, min_cost_delta=5.0)
    assert result.iloc[180]["is_anomaly"] is True or result.iloc[180]["is_anomaly"] == True
    assert result.iloc[180]["direction"] == "spike"


def test_zscore_detects_drop():
    series, timestamps = make_series(n=200, base=100.0, spike_idx=190, spike_val=5.0)
    result = detect_zscore_anomalies(series, timestamps, window=168, threshold=3.0, min_cost_delta=5.0)
    assert result.iloc[190]["is_anomaly"] == True
    assert result.iloc[190]["direction"] == "drop"


def test_zscore_no_anomaly_below_min_delta():
    # Small spike: 10 -> 13 (delta=3, below min_cost_delta=5)
    series, timestamps = make_series(spike_idx=180, spike_val=13.0)
    result = detect_zscore_anomalies(series, timestamps, window=168, threshold=3.0, min_cost_delta=5.0)
    assert result["is_anomaly"].sum() == 0


def test_zscore_stable_series_no_anomalies():
    series, timestamps = make_series(n=200, base=50.0)
    result = detect_zscore_anomalies(series, timestamps, window=168, threshold=3.0, min_cost_delta=5.0)
    assert result["is_anomaly"].sum() == 0


def test_zscore_returns_correct_columns():
    series, timestamps = make_series()
    result = detect_zscore_anomalies(series, timestamps, window=168, threshold=3.0, min_cost_delta=5.0)
    for col in ("timestamp", "observed", "baseline_mean", "baseline_std", "z_score", "is_anomaly", "direction"):
        assert col in result.columns
