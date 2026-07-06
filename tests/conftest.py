"""Shared pytest fixtures and helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest


@pytest.fixture
def sample_payload() -> dict:
    """A minimal, valid Open-Meteo-style payload with 3 hourly records."""
    base = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    times = [(base + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M") for i in range(3)]
    return {
        "latitude": 52.52,
        "longitude": 13.41,
        "hourly": {
            "time": times,
            "temperature_2m": [1.0, 2.0, 3.0],
            "relative_humidity_2m": [80.0, 81.0, 79.0],
            "wind_speed_10m": [5.0, 6.0, 4.5],
            "pressure_msl": [1010.0, 1011.0, 1009.0],
        },
    }


@pytest.fixture
def empty_history() -> tuple[pd.DataFrame, pd.DataFrame]:
    return pd.DataFrame(), pd.DataFrame()
