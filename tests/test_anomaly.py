"""Tests for the anomaly-detection math (the core observability logic)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd

from datapulse.config import ObservabilityConfig
from datapulse.observability import (
    detect_distribution_drift,
    detect_schema_drift,
    detect_volume_anomaly,
    freshness_minutes,
    zscore,
)

CONFIG = ObservabilityConfig(
    freshness_sla_minutes=180,
    rolling_window=20,
    zscore_threshold=3.0,
    min_history_for_anomaly=5,
)


def test_zscore_flags_known_spike():
    history = pd.Series([10.0] * 10)
    _, z = zscore(100.0, history)
    # zero variance -> std 0 -> z defined as 0; use a varied history instead
    history = pd.Series([10, 11, 9, 10, 12, 8, 10, 11, 9, 10], dtype=float)
    mean, z = zscore(100.0, history)
    assert mean is not None
    assert abs(z) > 3.0


def test_zscore_normal_value_not_extreme():
    history = pd.Series([10, 11, 9, 10, 12, 8, 10, 11, 9, 10], dtype=float)
    _, z = zscore(10.5, history)
    assert abs(z) < 3.0


def test_zscore_insufficient_history_returns_none():
    assert zscore(5.0, pd.Series([1.0])) == (None, None)


def test_volume_spike_is_flagged():
    history = pd.Series([100, 101, 99, 100, 102, 98, 100], dtype=float)
    row = detect_volume_anomaly(500, history, threshold=3.0, min_history=5)
    assert row.is_anomaly
    assert row.zscore is not None and abs(row.zscore) >= 3.0


def test_volume_normal_not_flagged():
    history = pd.Series([100, 101, 99, 100, 102, 98, 100], dtype=float)
    row = detect_volume_anomaly(100, history, threshold=3.0, min_history=5)
    assert not row.is_anomaly


def test_volume_insufficient_history_not_flagged():
    history = pd.Series([100, 101], dtype=float)
    row = detect_volume_anomaly(9999, history, threshold=3.0, min_history=5)
    assert not row.is_anomaly  # not enough history to trust the flag


def test_distribution_drift_flags_shift():
    df = pd.DataFrame({"temperature_2m": [50.0, 51.0, 49.0]})  # mean ~50
    history = pd.DataFrame({"temperature_2m": [10, 11, 9, 10, 12, 8, 10]})
    rows = detect_distribution_drift(df, history, threshold=3.0, min_history=5)
    temp = next(r for r in rows if r.column_name == "temperature_2m")
    assert temp.is_anomaly


def test_distribution_drift_stable_not_flagged():
    df = pd.DataFrame({"temperature_2m": [10.0, 11.0, 9.0]})  # mean ~10
    history = pd.DataFrame({"temperature_2m": [10, 11, 9, 10, 12, 8, 10]})
    rows = detect_distribution_drift(df, history, threshold=3.0, min_history=5)
    temp = next(r for r in rows if r.column_name == "temperature_2m")
    assert not temp.is_anomaly


def test_schema_drift_detects_missing_and_extra():
    df = pd.DataFrame({"latitude": [1.0], "surprise_col": [2.0]})
    row = detect_schema_drift(df, expected_columns=["latitude", "longitude"])
    assert row.is_anomaly
    assert row.value == 2.0  # 1 missing (longitude) + 1 extra (surprise_col)


def test_schema_drift_clean_when_matching():
    df = pd.DataFrame({"latitude": [1.0], "longitude": [2.0]})
    row = detect_schema_drift(df, expected_columns=["latitude", "longitude"])
    assert not row.is_anomaly


def test_freshness_minutes_recent():
    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    df = pd.DataFrame({"time": pd.to_datetime([now - timedelta(minutes=30)], utc=True)})
    assert freshness_minutes(df, now=now) == 30.0


def test_freshness_minutes_stale():
    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    df = pd.DataFrame({"time": pd.to_datetime([now - timedelta(hours=10)], utc=True)})
    assert freshness_minutes(df, now=now) == 600.0
    assert np.isclose(freshness_minutes(df, now=now), 600.0)
