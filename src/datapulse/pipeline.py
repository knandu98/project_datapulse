"""Pipeline orchestrator: runs steps 1-6 idempotently and is the CLI entrypoint.

python -m datapulse.pipeline run
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

from . import contract as contract_mod
from . import ingest as ingest_mod
from . import observability as obs_mod
from . import transform as transform_mod
from .config import Config, load_config
from .storage import Storage


def _expected_columns() -> list[str]:
    return list(contract_mod.SCHEMA.columns.keys())


def _write_latest_run(config: Config, report: dict) -> None:
    path = config.latest_run_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, default=str))


def run(config_path: str | Path | None = None) -> int:
    """Execute the full pipeline once. Returns a process exit code."""
    config = load_config(config_path) if config_path else load_config()
    storage = Storage(config)

    run_id = uuid.uuid4().hex[:12]
    run_ts = datetime.now(UTC)

    # --- 1. INGEST -----------------------------------------------------------
    try:
        payload = ingest_mod.fetch(config.source)
    except ingest_mod.IngestError as exc:
        return _record_failure(storage, config, run_id, run_ts, str(exc))

    timestamp = ingest_mod.utc_timestamp()
    storage.write_raw(payload, timestamp)

    # --- 2. TRANSFORM --------------------------------------------------------
    try:
        tidy = transform_mod.normalize(payload)
    except ValueError as exc:
        return _record_failure(storage, config, run_id, run_ts, f"transform: {exc}")

    merged = storage.upsert_processed(tidy, key_columns=transform_mod.KEY_COLUMNS)

    # --- 3. CONTRACT ---------------------------------------------------------
    contract_result = contract_mod.validate(tidy)

    # --- 4. OBSERVE ----------------------------------------------------------
    run_history = storage.read_run_history()
    metrics_history = storage.read_metrics()
    observation = obs_mod.observe(
        df=tidy,
        contract=contract_result,
        run_history=run_history,
        metrics_history=metrics_history,
        config=config.observability,
        expected_columns=_expected_columns(),
        now=run_ts,
    )
    metrics_frame = obs_mod.metrics_to_frame(observation, run_id, run_ts)
    storage.append_metrics(metrics_frame)

    # --- 5. REPORT -----------------------------------------------------------
    status = "success" if contract_result.passed and observation.anomalies_found == 0 else "warning"
    history_row = {
        "run_id": run_id,
        "run_ts": run_ts,
        "status": status,
        "rows_ingested": len(tidy),
        "checks_passed": contract_result.checks_passed,
        "checks_failed": contract_result.checks_failed,
        "anomalies_found": observation.anomalies_found,
        "error": None,
    }
    storage.append_run_history(history_row)

    report = {
        **history_row,
        "total_rows_in_lake": len(merged),
        "contract": contract_result.as_dict(),
        "metrics": metrics_frame.to_dict("records"),
    }
    _write_latest_run(config, report)

    _print_summary(report)
    return 0


def _record_failure(
    storage: Storage, config: Config, run_id: str, run_ts: datetime, error: str
) -> int:
    """Record a failed run, write the report, and signal a non-zero exit."""
    history_row = {
        "run_id": run_id,
        "run_ts": run_ts,
        "status": "failed",
        "rows_ingested": 0,
        "checks_passed": 0,
        "checks_failed": 0,
        "anomalies_found": 0,
        "error": error,
    }
    storage.append_run_history(history_row)
    _write_latest_run(config, {**history_row, "contract": None, "metrics": []})
    print(f"[datapulse] RUN FAILED: {error}", file=sys.stderr)
    return 1


def _print_summary(report: dict) -> None:
    print(
        f"[datapulse] run {report['run_id']} status={report['status']} "
        f"rows={report['rows_ingested']} "
        f"checks_passed={report['checks_passed']} checks_failed={report['checks_failed']} "
        f"anomalies={report['anomalies_found']}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="datapulse", description="DataPulse pipeline CLI.")
    sub = parser.add_subparsers(dest="command", required=True)
    run_parser = sub.add_parser("run", help="Run the full pipeline once.")
    run_parser.add_argument("--config", default=None, help="Path to config.yaml.")
    args = parser.parse_args(argv)

    if args.command == "run":
        return run(args.config)
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
