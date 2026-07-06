"""Configuration loading and validation.

Combines the static ``config.yaml`` with dynamic infrastructure details read from
``terraform output -json`` so the application and infrastructure stay in sync.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = REPO_ROOT / "config.yaml"


@dataclass(frozen=True)
class SourceConfig:
    name: str
    url: str
    params: dict[str, Any]


@dataclass(frozen=True)
class ObservabilityConfig:
    freshness_sla_minutes: int
    rolling_window: int
    zscore_threshold: float
    min_history_for_anomaly: int


@dataclass(frozen=True)
class LakeInfo:
    """Resolved infrastructure details (from Terraform outputs)."""

    raw_bucket: str
    processed_bucket: str
    s3_endpoint: str | None
    region: str
    use_localstack: bool


@dataclass(frozen=True)
class Config:
    source: SourceConfig
    observability: ObservabilityConfig
    raw_prefix: str
    processed_prefix: str
    terraform_dir: Path
    duckdb_path: Path
    local_raw_dir: Path
    local_processed_dir: Path
    latest_run_path: Path
    repo_root: Path = field(default=REPO_ROOT)

    def lake_info(self) -> LakeInfo:
        """Read Terraform outputs to resolve bucket names + endpoint."""
        return load_terraform_outputs(self.terraform_dir)


def _abs(repo_root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else repo_root / path


def load_config(path: str | Path = DEFAULT_CONFIG_PATH) -> Config:
    """Load and validate ``config.yaml`` into a typed :class:`Config`."""
    path = Path(path)
    repo_root = path.resolve().parent
    raw = yaml.safe_load(path.read_text())

    source = raw["source"]
    obs = raw["observability"]
    lake = raw["lake"]
    storage = raw["storage"]
    reports = raw["reports"]

    return Config(
        source=SourceConfig(name=source["name"], url=source["url"], params=source["params"]),
        observability=ObservabilityConfig(
            freshness_sla_minutes=int(obs["freshness_sla_minutes"]),
            rolling_window=int(obs["rolling_window"]),
            zscore_threshold=float(obs["zscore_threshold"]),
            min_history_for_anomaly=int(obs["min_history_for_anomaly"]),
        ),
        raw_prefix=lake["raw_prefix"],
        processed_prefix=lake["processed_prefix"],
        terraform_dir=_abs(repo_root, lake["terraform_dir"]),
        duckdb_path=_abs(repo_root, storage["duckdb_path"]),
        local_raw_dir=_abs(repo_root, storage["local_raw_dir"]),
        local_processed_dir=_abs(repo_root, storage["local_processed_dir"]),
        latest_run_path=_abs(repo_root, reports["latest_run_path"]),
        repo_root=repo_root,
    )


def load_terraform_outputs(terraform_dir: Path) -> LakeInfo:
    """Run ``terraform output -json`` and map it into :class:`LakeInfo`.

    Falls back to sensible LocalStack defaults if Terraform has not been applied
    yet (e.g. during unit tests), so the pipeline degrades gracefully.
    """
    defaults = LakeInfo(
        raw_bucket="datapulse-raw",
        processed_bucket="datapulse-processed",
        s3_endpoint="http://localhost:4566",
        region="us-east-1",
        use_localstack=True,
    )
    try:
        result = subprocess.run(
            ["terraform", f"-chdir={terraform_dir}", "output", "-json"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return defaults

    try:
        outputs = json.loads(result.stdout)
    except json.JSONDecodeError:
        return defaults

    if not outputs:
        return defaults

    def _val(key: str, fallback: Any) -> Any:
        return outputs.get(key, {}).get("value", fallback)

    endpoint = _val("s3_endpoint", defaults.s3_endpoint)
    return LakeInfo(
        raw_bucket=_val("raw_bucket", defaults.raw_bucket),
        processed_bucket=_val("processed_bucket", defaults.processed_bucket),
        s3_endpoint=endpoint or None,
        region=_val("aws_region", defaults.region),
        use_localstack=bool(_val("use_localstack", defaults.use_localstack)),
    )
