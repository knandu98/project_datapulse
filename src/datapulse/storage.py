"""Storage layer: DuckDB tables, local Parquet mirror, and S3 (boto3) access.

The S3 endpoint + bucket names come from Terraform outputs (:class:`LakeInfo`)
so the same code path works against LocalStack and real AWS.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import boto3
import duckdb
import pandas as pd
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

from .config import Config, LakeInfo

METRICS_TABLE = "metrics"
RUN_HISTORY_TABLE = "run_history"


def s3_client(lake: LakeInfo):
    """Build a boto3 S3 client pointed at LocalStack or real AWS."""
    kwargs: dict[str, Any] = {"region_name": lake.region}
    if lake.use_localstack:
        kwargs.update(
            endpoint_url=lake.s3_endpoint,
            aws_access_key_id="test",
            aws_secret_access_key="test",
            config=BotoConfig(s3={"addressing_style": "path"}),
        )
    elif lake.s3_endpoint:
        kwargs["endpoint_url"] = lake.s3_endpoint
    return boto3.client("s3", **kwargs)


def ensure_bucket(client, bucket: str) -> None:
    """Create the bucket if it does not already exist (idempotent)."""
    try:
        client.head_bucket(Bucket=bucket)
    except ClientError:
        client.create_bucket(Bucket=bucket)


def put_object(client, bucket: str, key: str, body: bytes | str) -> None:
    if isinstance(body, str):
        body = body.encode("utf-8")
    ensure_bucket(client, bucket)
    client.put_object(Bucket=bucket, Key=key, Body=body)


class Storage:
    """Facade over DuckDB + local Parquet + S3."""

    def __init__(self, config: Config, lake: LakeInfo | None = None) -> None:
        self.config = config
        self.lake = lake or config.lake_info()
        self.config.duckdb_path.parent.mkdir(parents=True, exist_ok=True)
        self.config.local_raw_dir.mkdir(parents=True, exist_ok=True)
        self.config.local_processed_dir.mkdir(parents=True, exist_ok=True)
        self._init_duckdb()

    # --- DuckDB ----------------------------------------------------------------
    def connect(self) -> duckdb.DuckDBPyConnection:
        return duckdb.connect(str(self.config.duckdb_path))

    def _init_duckdb(self) -> None:
        with self.connect() as con:
            con.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {METRICS_TABLE} (
                    run_id      VARCHAR,
                    run_ts      TIMESTAMP,
                    metric      VARCHAR,
                    column_name VARCHAR,
                    value       DOUBLE,
                    baseline    DOUBLE,
                    zscore      DOUBLE,
                    is_anomaly  BOOLEAN
                )
                """
            )
            con.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {RUN_HISTORY_TABLE} (
                    run_id          VARCHAR,
                    run_ts          TIMESTAMP,
                    status          VARCHAR,
                    rows_ingested   BIGINT,
                    checks_passed   BIGINT,
                    checks_failed   BIGINT,
                    anomalies_found BIGINT,
                    error           VARCHAR
                )
                """
            )

    def append_metrics(self, df: pd.DataFrame) -> None:
        if df.empty:
            return
        with self.connect() as con:
            con.register("metrics_df", df)
            con.execute(f"INSERT INTO {METRICS_TABLE} SELECT * FROM metrics_df")
            con.unregister("metrics_df")

    def append_run_history(self, row: dict[str, Any]) -> None:
        df = pd.DataFrame([row])
        with self.connect() as con:
            con.register("run_df", df)
            con.execute(
                f"""
                INSERT INTO {RUN_HISTORY_TABLE}
                SELECT run_id, run_ts, status, rows_ingested, checks_passed,
                       checks_failed, anomalies_found, error
                FROM run_df
                """
            )
            con.unregister("run_df")

    def read_run_history(self) -> pd.DataFrame:
        with self.connect() as con:
            return con.execute(f"SELECT * FROM {RUN_HISTORY_TABLE} ORDER BY run_ts").fetch_df()

    def read_metrics(self) -> pd.DataFrame:
        with self.connect() as con:
            return con.execute(f"SELECT * FROM {METRICS_TABLE} ORDER BY run_ts").fetch_df()

    # --- Raw snapshots ---------------------------------------------------------
    def write_raw(self, payload: dict[str, Any], timestamp: str) -> tuple[Path, str]:
        """Persist a raw JSON snapshot locally and to the raw S3 bucket."""
        body = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        local_path = self.config.local_raw_dir / f"{timestamp}.json"
        local_path.write_text(body)

        key = f"{self.config.raw_prefix}{timestamp}.json"
        client = s3_client(self.lake)
        put_object(client, self.lake.raw_bucket, key, body)
        return local_path, key

    # --- Processed Parquet -----------------------------------------------------
    def processed_path(self) -> Path:
        return self.config.local_processed_dir / "weather.parquet"

    def read_processed(self) -> pd.DataFrame:
        path = self.processed_path()
        if not path.exists():
            return pd.DataFrame()
        return pd.read_parquet(path)

    def upsert_processed(self, df: pd.DataFrame, key_columns: list[str]) -> pd.DataFrame:
        """Merge new rows into the processed dataset, deduping on the natural key.

        Idempotent: re-running with overlapping data keeps a single row per key
        (latest wins). Writes the result locally and mirrors it to S3.
        """
        existing = self.read_processed()
        combined = pd.concat([existing, df], ignore_index=True) if not existing.empty else df
        combined = combined.drop_duplicates(subset=key_columns, keep="last").reset_index(drop=True)
        combined = combined.sort_values(key_columns).reset_index(drop=True)

        path = self.processed_path()
        combined.to_parquet(path, index=False)

        # Mirror to the processed bucket (single consolidated object).
        client = s3_client(self.lake)
        key = f"{self.config.processed_prefix}weather.parquet"
        ensure_bucket(client, self.lake.processed_bucket)
        client.put_object(Bucket=self.lake.processed_bucket, Key=key, Body=path.read_bytes())
        return combined
