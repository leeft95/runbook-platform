"""Small deterministic SQLite live-data provider for local demos and tests."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone

import pandas as pd
from runbook.sdk.live import JSONValue, LiveCapabilityUnavailableError, LiveQuerySource


@dataclass(frozen=True)
class LiveQueryProvenance:
    """Safe metadata captured for one live query."""

    logical_provider: str
    query_time: datetime
    query_hash: str
    parameter_keys: tuple[str, ...]
    parameter_types: tuple[str, ...]
    duration_ms: float


class SQLiteLiveQuerySource:
    """A parameterized SQLite source exposed through the live query protocol."""

    def __init__(self, connection: sqlite3.Connection, *, logical_provider: str):
        self._connection = connection
        self.logical_provider = logical_provider
        self.last_provenance: LiveQueryProvenance | None = None

    def query(self, statement: str, params: Mapping[str, JSONValue] | None = None) -> pd.DataFrame:
        """Execute parameterized SQL and return rows as a dataframe."""
        if not isinstance(statement, str) or not statement.strip():
            raise ValueError("live SQL statement must be a non-empty string")
        safe_params = dict(params or {})
        parameter_keys = tuple(sorted(str(key) for key in safe_params))
        parameter_types = tuple(type(safe_params[key]).__name__ for key in sorted(safe_params))
        digest_payload = {"statement": statement, "parameter_keys": parameter_keys, "parameter_types": parameter_types}
        query_hash = hashlib.sha256(
            json.dumps(digest_payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        started = time.monotonic()
        frame = pd.read_sql_query(statement, self._connection, params=safe_params)
        duration_ms = (time.monotonic() - started) * 1000.0
        self.last_provenance = LiveQueryProvenance(
            logical_provider=self.logical_provider,
            query_time=datetime.now(timezone.utc),
            query_hash=query_hash,
            parameter_keys=parameter_keys,
            parameter_types=parameter_types,
            duration_ms=duration_ms,
        )
        return frame


class SQLiteLiveDataResolver:
    """Resolve logical names to local SQLite live query sources."""

    def __init__(self, sources: Mapping[str, SQLiteLiveQuerySource]):
        self._sources = dict(sources)

    @classmethod
    def from_connection(
        cls,
        connection: sqlite3.Connection,
        *,
        logical_provider: str = "sqlite-demo",
        name: str = "demo_pnl",
    ) -> "SQLiteLiveDataResolver":
        """Create one logical source backed by an existing SQLite connection."""
        return cls({name: SQLiteLiveQuerySource(connection, logical_provider=logical_provider)})

    def sql(self, name: str) -> LiveQuerySource:
        """Resolve one logical source without accepting URLs or credentials."""
        try:
            return self._sources[name]
        except KeyError as exc:
            raise LiveCapabilityUnavailableError(f"live SQL source is unavailable: {name!r}") from exc


def build_demo_live_provider() -> SQLiteLiveDataResolver:
    """Build deterministic in-memory live PnL data for public examples."""
    connection = sqlite3.connect(":memory:")
    frame = pd.DataFrame(
        [
            {
                "business_date": "2024-01-17",
                "book": "Alpha",
                "strategy": "Macro",
                "instrument": "GBPUSD",
                "pnl": 250.0,
                "exposure": 100000.0,
            },
            {
                "business_date": "2024-01-17",
                "book": "Beta",
                "strategy": "RV",
                "instrument": "EURGBP",
                "pnl": -80.0,
                "exposure": 75000.0,
            },
            {
                "business_date": "2024-01-18",
                "book": "Gamma",
                "strategy": "Credit",
                "instrument": "UK10Y",
                "pnl": 420.0,
                "exposure": 52000.0,
            },
        ]
    )
    frame.to_sql("demo_live_pnl", connection, index=False)
    return SQLiteLiveDataResolver.from_connection(connection)


__all__ = [
    "LiveQueryProvenance",
    "SQLiteLiveDataResolver",
    "SQLiteLiveQuerySource",
    "build_demo_live_provider",
]
