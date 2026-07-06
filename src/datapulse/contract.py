"""Data contract: a pandera schema + a validation runner that records results."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd
import pandera.pandas as pa
from pandera.pandas import Check, Column, DataFrameSchema

from .transform import KEY_COLUMNS

# Explicit column types, plausible value ranges, nullability, and a unique key.
SCHEMA = DataFrameSchema(
    {
        "latitude": Column(float, nullable=False),
        "longitude": Column(float, nullable=False),
        "time": Column("datetime64[ns, UTC]", nullable=False),
        "temperature_2m": Column(float, Check.in_range(-90.0, 60.0), nullable=True, required=False),
        "relative_humidity_2m": Column(
            float, Check.in_range(0.0, 100.0), nullable=True, required=False
        ),
        "wind_speed_10m": Column(float, Check.in_range(0.0, 150.0), nullable=True, required=False),
        "pressure_msl": Column(float, Check.in_range(850.0, 1100.0), nullable=True, required=False),
        "ingested_at": Column("datetime64[ns, UTC]", nullable=False),
    },
    unique=KEY_COLUMNS,
    strict=False,
    coerce=True,
)


@dataclass
class ContractResult:
    passed: bool
    checks_passed: int
    checks_failed: int
    failure_cases: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "checks_passed": self.checks_passed,
            "checks_failed": self.checks_failed,
            "failure_cases": self.failure_cases,
        }


def _count_checks() -> int:
    """Total number of column-level checks declared in the schema."""
    total = 0
    for column in SCHEMA.columns.values():
        total += 1  # type/nullability check
        total += len(column.checks)
    total += 1  # uniqueness on the key
    return total


def validate(df: pd.DataFrame) -> ContractResult:
    """Validate ``df`` against :data:`SCHEMA`, recording pass/fail counts."""
    total_checks = _count_checks()
    try:
        SCHEMA.validate(df, lazy=True)
    except pa.errors.SchemaErrors as exc:
        failure_df = exc.failure_cases
        failed = int(failure_df["check"].nunique()) if not failure_df.empty else 1
        cases = [
            f"{row.get('column')}: {row.get('check')} (failure={row.get('failure_case')})"
            for row in failure_df.head(20).to_dict("records")
        ]
        return ContractResult(
            passed=False,
            checks_passed=max(total_checks - failed, 0),
            checks_failed=failed,
            failure_cases=cases,
        )
    return ContractResult(passed=True, checks_passed=total_checks, checks_failed=0)
