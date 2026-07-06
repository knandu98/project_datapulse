"""Tests for the storage layer (DuckDB tables + idempotent Parquet upsert).

S3 is exercised via a fake client so these tests need no LocalStack/network.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import pytest

from datapulse.config import (
    Config,
    LakeInfo,
    ObservabilityConfig,
    SourceConfig,
)
from datapulse.storage import Storage


class _FakeS3:
    """Minimal in-memory stand-in for a boto3 S3 client."""

    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.buckets: set[str] = set()

    def head_bucket(self, Bucket):  # noqa: N803 (boto3 casing)
        from botocore.exceptions import ClientError

        if Bucket not in self.buckets:
            raise ClientError({"Error": {"Code": "404"}}, "HeadBucket")

    def create_bucket(self, Bucket, **kwargs):  # noqa: N803
        self.buckets.add(Bucket)

    def put_object(self, Bucket, Key, Body):  # noqa: N803
        self.objects[(Bucket, Key)] = Body


@pytest.fixture
def storage(tmp_path, monkeypatch) -> Storage:
    lake = LakeInfo(
        raw_bucket="raw",
        processed_bucket="processed",
        s3_endpoint="http://localhost:4566",
        region="us-east-1",
        use_localstack=True,
    )
    config = Config(
        source=SourceConfig(name="t", url="http://x", params={}),
        observability=ObservabilityConfig(180, 20, 3.0, 5),
        raw_prefix="raw/",
        processed_prefix="processed/",
        terraform_dir=tmp_path / "infra",
        duckdb_path=tmp_path / "db.duckdb",
        local_raw_dir=tmp_path / "raw",
        local_processed_dir=tmp_path / "processed",
        latest_run_path=tmp_path / "reports" / "latest.json",
        repo_root=tmp_path,
    )
    monkeypatch.setattr("datapulse.storage.s3_client", lambda _lake: _FakeS3())
    return Storage(config, lake=lake)


def _frame(times, temps) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "latitude": [52.52] * len(times),
            "longitude": [13.41] * len(times),
            "time": pd.to_datetime(times, utc=True),
            "temperature_2m": temps,
            "ingested_at": [datetime.now(UTC)] * len(times),
        }
    )


def test_tables_created(storage):
    assert storage.read_run_history().empty
    assert storage.read_metrics().empty


def test_run_history_roundtrip(storage):
    row = {
        "run_id": "abc",
        "run_ts": datetime.now(UTC),
        "status": "success",
        "rows_ingested": 3,
        "checks_passed": 10,
        "checks_failed": 0,
        "anomalies_found": 0,
        "error": None,
    }
    storage.append_run_history(row)
    df = storage.read_run_history()
    assert len(df) == 1
    assert df.iloc[0]["run_id"] == "abc"


def test_upsert_is_idempotent(storage):
    df = _frame(["2026-01-01T00:00", "2026-01-01T01:00"], [1.0, 2.0])
    merged1 = storage.upsert_processed(df, key_columns=["latitude", "longitude", "time"])
    merged2 = storage.upsert_processed(df, key_columns=["latitude", "longitude", "time"])
    assert len(merged1) == 2
    assert len(merged2) == 2  # re-running must not duplicate rows


def test_upsert_latest_wins_on_conflict(storage):
    df1 = _frame(["2026-01-01T00:00"], [1.0])
    df2 = _frame(["2026-01-01T00:00"], [9.0])  # same key, new value
    storage.upsert_processed(df1, key_columns=["latitude", "longitude", "time"])
    merged = storage.upsert_processed(df2, key_columns=["latitude", "longitude", "time"])
    assert len(merged) == 1
    assert merged.iloc[0]["temperature_2m"] == 9.0


def test_upsert_appends_new_keys(storage):
    df1 = _frame(["2026-01-01T00:00"], [1.0])
    df2 = _frame(["2026-01-01T01:00"], [2.0])
    storage.upsert_processed(df1, key_columns=["latitude", "longitude", "time"])
    merged = storage.upsert_processed(df2, key_columns=["latitude", "longitude", "time"])
    assert len(merged) == 2
