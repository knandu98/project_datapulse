"""Observability: freshness, volume, schema drift, distribution drift, anomalies.

All anomaly math is plain statistics (rolling mean/std + z-score) so it is fully
deterministic and unit-testable. No ML.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from .config import ObservabilityConfig
from .contract import ContractResult
from .transform import NUMERIC_COLUMNS


@dataclass
class MetricRow:
    metric: str
    column_name: str
    value: float
    baseline: float | None = None
    zscore: float | None = None
    is_anomaly: bool = False


@dataclass
class ObservationResult:
    metrics: list[MetricRow] = field(default_factory=list)
    anomalies_found: int = 0

    def add(self, row: MetricRow) -> None:
        self.metrics.append(row)
        if row.is_anomaly:
            self.anomalies_found += 1


def zscore(value: float, history: pd.Series) -> tuple[float | None, float | None]:
    """Return ``(baseline_mean, zscore)`` of ``value`` against ``history``.

    Returns ``(None, None)`` when there is too little history or zero variance.
    """
    clean = pd.to_numeric(history, errors="coerce").dropna()
    if len(clean) < 2:
        return None, None
    mean = float(clean.mean())
    std = float(clean.std(ddof=0))
    if std == 0:
        return mean, 0.0
    return mean, float((value - mean) / std)


def freshness_minutes(df: pd.DataFrame, now: datetime | None = None) -> float:
    """Age (in minutes) of the newest ``time`` record versus ``now``."""
    now = now or datetime.now(UTC)
    newest = pd.to_datetime(df["time"], utc=True).max()
    return float((now - newest.to_pydatetime()).total_seconds() / 60.0)


def detect_volume_anomaly(
    current_rows: int,
    history: pd.Series,
    threshold: float,
    min_history: int,
) -> MetricRow:
    """Flag the row count for this run against the rolling baseline."""
    baseline, z = (None, None)
    is_anomaly = False
    if len(history.dropna()) >= min_history:
        baseline, z = zscore(float(current_rows), history)
        is_anomaly = z is not None and abs(z) >= threshold
    return MetricRow(
        metric="volume",
        column_name="row_count",
        value=float(current_rows),
        baseline=baseline,
        zscore=z,
        is_anomaly=is_anomaly,
    )


def detect_distribution_drift(
    df: pd.DataFrame,
    history: pd.DataFrame,
    threshold: float,
    min_history: int,
) -> list[MetricRow]:
    """Per numeric column, compare the current mean to the rolling baseline.

    ``history`` is a frame of prior per-run column means (one row per past run,
    one column per numeric field).
    """
    rows: list[MetricRow] = []
    for col in NUMERIC_COLUMNS:
        if col not in df.columns:
            continue
        current_mean = float(pd.to_numeric(df[col], errors="coerce").mean())
        baseline, z = (None, None)
        is_anomaly = False
        if col in history.columns and len(history[col].dropna()) >= min_history:
            baseline, z = zscore(current_mean, history[col])
            is_anomaly = z is not None and abs(z) >= threshold
        rows.append(
            MetricRow(
                metric="distribution_drift",
                column_name=col,
                value=current_mean,
                baseline=baseline,
                zscore=z,
                is_anomaly=is_anomaly,
            )
        )
    return rows


def detect_schema_drift(df: pd.DataFrame, expected_columns: list[str]) -> MetricRow:
    """Flag missing/extra columns relative to the contract's expected set."""
    actual = set(df.columns)
    expected = set(expected_columns)
    missing = expected - actual
    extra = actual - expected
    drift_count = len(missing) + len(extra)
    return MetricRow(
        metric="schema_drift",
        column_name="columns",
        value=float(drift_count),
        baseline=0.0,
        zscore=None,
        is_anomaly=drift_count > 0,
    )


def observe(
    df: pd.DataFrame,
    contract: ContractResult,
    run_history: pd.DataFrame,
    metrics_history: pd.DataFrame,
    config: ObservabilityConfig,
    expected_columns: list[str],
    now: datetime | None = None,
) -> ObservationResult:
    """Compute all health metrics for the current run.

    ``run_history`` is the prior ``run_history`` table (for volume baselines);
    ``metrics_history`` is the prior ``metrics`` table (for distribution baselines).
    """
    result = ObservationResult()

    # Freshness ---------------------------------------------------------------
    age = freshness_minutes(df, now=now)
    result.add(
        MetricRow(
            metric="freshness",
            column_name="minutes",
            value=age,
            baseline=float(config.freshness_sla_minutes),
            is_anomaly=age > config.freshness_sla_minutes,
        )
    )

    # Volume ------------------------------------------------------------------
    vol_history = (
        run_history["rows_ingested"]
        if "rows_ingested" in run_history.columns
        else pd.Series([], dtype=float)
    )
    result.add(
        detect_volume_anomaly(
            current_rows=len(df),
            history=vol_history.tail(config.rolling_window),
            threshold=config.zscore_threshold,
            min_history=config.min_history_for_anomaly,
        )
    )

    # Schema drift ------------------------------------------------------------
    result.add(detect_schema_drift(df, expected_columns))

    # Distribution drift ------------------------------------------------------
    dist_history = _distribution_history(metrics_history, config.rolling_window)
    for row in detect_distribution_drift(
        df, dist_history, config.zscore_threshold, config.min_history_for_anomaly
    ):
        result.add(row)

    # Contract violations -----------------------------------------------------
    result.add(
        MetricRow(
            metric="contract_violations",
            column_name="checks_failed",
            value=float(contract.checks_failed),
            baseline=0.0,
            is_anomaly=contract.checks_failed > 0,
        )
    )

    return result


def _distribution_history(metrics_history: pd.DataFrame, window: int) -> pd.DataFrame:
    """Reshape the metrics table into one row per run of per-column means."""
    if metrics_history.empty or "metric" not in metrics_history.columns:
        return pd.DataFrame()
    dist = metrics_history[metrics_history["metric"] == "distribution_drift"]
    if dist.empty:
        return pd.DataFrame()
    pivot = dist.pivot_table(
        index="run_ts", columns="column_name", values="value", aggfunc="last"
    ).sort_index()
    return pivot.tail(window)


def metrics_to_frame(result: ObservationResult, run_id: str, run_ts: datetime) -> pd.DataFrame:
    """Convert the observation result into a frame matching the ``metrics`` table."""
    records = [
        {
            "run_id": run_id,
            "run_ts": run_ts,
            "metric": row.metric,
            "column_name": row.column_name,
            "value": float(row.value),
            "baseline": np.nan if row.baseline is None else float(row.baseline),
            "zscore": np.nan if row.zscore is None else float(row.zscore),
            "is_anomaly": bool(row.is_anomaly),
        }
        for row in result.metrics
    ]
    return pd.DataFrame.from_records(
        records,
        columns=[
            "run_id",
            "run_ts",
            "metric",
            "column_name",
            "value",
            "baseline",
            "zscore",
            "is_anomaly",
        ],
    )
