"""Tests for the pandera data contract."""

from __future__ import annotations

from datapulse.contract import validate
from datapulse.transform import normalize


def test_valid_data_passes(sample_payload):
    df = normalize(sample_payload)
    result = validate(df)
    assert result.passed
    assert result.checks_failed == 0
    assert result.checks_passed > 0


def test_out_of_range_temperature_fails(sample_payload):
    df = normalize(sample_payload)
    df.loc[0, "temperature_2m"] = 999.0  # impossible temperature
    result = validate(df)
    assert not result.passed
    assert result.checks_failed >= 1
    assert any("temperature_2m" in c for c in result.failure_cases)


def test_duplicate_key_fails(sample_payload):
    df = normalize(sample_payload)
    dup = df.iloc[[0]].copy()
    df = df._append(dup, ignore_index=True) if hasattr(df, "_append") else df
    import pandas as pd

    df = pd.concat([df, dup], ignore_index=True)
    result = validate(df)
    assert not result.passed


def test_humidity_out_of_range_fails(sample_payload):
    df = normalize(sample_payload)
    df.loc[1, "relative_humidity_2m"] = 250.0
    result = validate(df)
    assert not result.passed
