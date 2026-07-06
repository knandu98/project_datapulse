"""Tests for the transform step."""

from __future__ import annotations

import pandas as pd
import pytest

from datapulse.transform import KEY_COLUMNS, NUMERIC_COLUMNS, normalize


def test_normalize_produces_tidy_rows(sample_payload):
    df = normalize(sample_payload)
    assert len(df) == 3
    for col in KEY_COLUMNS:
        assert col in df.columns
    for col in NUMERIC_COLUMNS:
        assert col in df.columns
    assert "ingested_at" in df.columns


def test_normalize_sets_lat_lon_from_payload(sample_payload):
    df = normalize(sample_payload)
    assert (df["latitude"] == 52.52).all()
    assert (df["longitude"] == 13.41).all()


def test_normalize_parses_time_as_utc(sample_payload):
    df = normalize(sample_payload)
    assert str(df["time"].dt.tz) == "UTC"


def test_normalize_missing_hourly_raises():
    with pytest.raises(ValueError):
        normalize({"latitude": 1.0, "longitude": 2.0})


def test_normalize_coerces_non_numeric_to_nan(sample_payload):
    sample_payload["hourly"]["temperature_2m"] = ["x", 2.0, 3.0]
    df = normalize(sample_payload)
    assert pd.isna(df.loc[0, "temperature_2m"])
