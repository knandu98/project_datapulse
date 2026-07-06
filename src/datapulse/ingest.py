"""Ingest: fetch the latest payload from the configured public API."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import requests

from .config import SourceConfig


class IngestError(RuntimeError):
    """Raised when the upstream API cannot be fetched."""


def utc_timestamp() -> str:
    """A filesystem-safe UTC timestamp used to name raw snapshots."""
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def fetch(source: SourceConfig, timeout: int = 30) -> dict[str, Any]:
    """Fetch the latest payload. Raises :class:`IngestError` on any failure."""
    try:
        response = requests.get(source.url, params=source.params, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError) as exc:  # ValueError = bad JSON
        raise IngestError(f"Failed to fetch {source.name} from {source.url}: {exc}") from exc
