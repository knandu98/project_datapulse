"""Transform: normalize the raw API payload into a tidy table."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pandas as pd

# Columns expected from Open-Meteo's hourly block (besides ``time``).
NUMERIC_COLUMNS = [
    "temperature_2m",
    "relative_humidity_2m",
    "wind_speed_10m",
    "pressure_msl",
]

KEY_COLUMNS = ["latitude", "longitude", "time"]


def normalize(payload: dict[str, Any]) -> pd.DataFrame:
    """Flatten an Open-Meteo payload into one row per (lat, lon, hour).

    The result includes an ``ingested_at`` column so freshness + lineage can be
    tracked downstream.
    """
    hourly = payload.get("hourly")
    if not hourly or "time" not in hourly:
        raise ValueError("payload missing 'hourly.time'; cannot transform")

    df = pd.DataFrame(hourly)
    df["time"] = pd.to_datetime(df["time"], utc=True)

    df.insert(0, "latitude", float(payload.get("latitude")))
    df.insert(1, "longitude", float(payload.get("longitude")))

    for col in NUMERIC_COLUMNS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df["ingested_at"] = datetime.now(UTC)

    ordered = KEY_COLUMNS + [c for c in NUMERIC_COLUMNS if c in df.columns] + ["ingested_at"]
    df = df[ordered].sort_values(KEY_COLUMNS).reset_index(drop=True)
    return df
