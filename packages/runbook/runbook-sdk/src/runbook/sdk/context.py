from __future__ import annotations

import copy
import io
import json
import re
from dataclasses import is_dataclass
from typing import Any, Callable, Mapping, TypeVar

import pandas as pd
from loguru import logger
from runbook.core.report_artifacts import ArtifactRegistry, validate_artifact_name
from runbook.core.snapshots import Snapshot
from runbook.data import BlobStore, load_snapshot_dataset
from runbook.sdk.live import UNAVAILABLE_LIVE_RESOLVER, LiveDataResolver

TParams = TypeVar("TParams")
_CACHE_MISS = object()
_SEGMENT_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


class Ctx:
    """The single read-only report context used by preview and production."""

    def __init__(
        self,
        *,
        snapshot: Snapshot,
        store: BlobStore,
        report_id: str,
        config: Mapping[str, Any],
        code_version: str,
        context_hash: str,
        artifact_prefix: str,
        artifact_store: BlobStore | None = None,
        use_cache: bool = True,
        live: LiveDataResolver | None = None,
    ):
        self.snapshot = snapshot
        self._store = store
        self._artifact_store = artifact_store or store
        self.report_id = report_id
        self.config = copy.deepcopy(dict(config))
        self.code_version = code_version
        self.context_hash = context_hash
        self._artifact_prefix = artifact_prefix.rstrip("/")
        self.use_cache = use_cache
        self.live = live or UNAVAILABLE_LIVE_RESOLVER
        self._calc_fns: dict[str, Callable[[Ctx], Any]] = {}
        self._memo: dict[str, Any] = {}
        self.cache_hits: dict[str, bool] = {}
        self._active_calcs: set[str] = set()
        self.artifact = ArtifactRegistry(
            table_ref_resolver=lambda name: f"tables/{name}.parquet",
            table_writer=self._write_table,
        )

    def register_calc(self, name: str, fn: Callable[["Ctx"], Any]) -> None:
        """Register one named calculation for deterministic lazy execution."""
        validate_artifact_name(name)
        self._calc_fns[name] = fn

    def dataset(self, alias: str, *, filters: Mapping[str, object] | None = None) -> pd.DataFrame:
        """Load one immutable snapshot dataset by report alias."""
        return load_snapshot_dataset(
            self._store,
            self.snapshot,
            alias,
            filters=filters or None,
        )

    def get_params(self, model: type[TParams]) -> TParams:
        """Validate the JSON report parameters with a Pydantic or dataclass model."""
        raw = self.config.get("params", {})
        if not isinstance(raw, Mapping):
            raise TypeError("ctx.config['params'] must be a mapping")
        payload = dict(raw)
        validate = getattr(model, "model_validate", None)
        if callable(validate):
            return validate(payload)
        if is_dataclass(model):
            return model(**payload)  # type: ignore[misc]
        return model(**payload)  # type: ignore[misc]

    def _cache_prefix(self, name: str) -> str:
        """Handle cache prefix."""
        safe = validate_artifact_name(name)
        for label, value in (
            ("report_id", self.report_id),
            ("snapshot_id", self.snapshot.snapshot_id),
            ("code_version", self.code_version),
            ("context_hash", self.context_hash),
        ):
            if not _SEGMENT_RE.fullmatch(str(value)):
                raise ValueError(f"invalid {label} path segment: {value!r}")
        return f"cache/{self.report_id}/{self.snapshot.snapshot_id}/{self.code_version}/{self.context_hash}/calc={safe}"

    def _write_table(self, name: str, frame: pd.DataFrame) -> None:
        """Persist one immutable parquet table artifact under the report prefix."""
        self._artifact_store.put_immutable(
            f"{self._artifact_prefix}/tables/{name}.parquet",
            frame.to_parquet(index=True),
        )

    def _read_cached(self, name: str) -> Any:
        """Read a typed calculation cache entry or return the miss sentinel."""
        prefix = self._cache_prefix(name)
        meta_key = f"{prefix}.meta.json"
        if not self.use_cache or not self._artifact_store.exists(meta_key):
            return _CACHE_MISS
        meta = self._artifact_store.get_json(meta_key)
        if not isinstance(meta, dict) or meta.get("kind") not in {
            "json",
            "none",
            "series",
            "dataframe",
        }:
            raise ValueError(f"unknown cache metadata for {name!r}")
        if meta.get("kind") == "none":
            return None
        if meta.get("kind") == "json":
            return self._artifact_store.get_json(f"{prefix}.json")
        frame = pd.read_parquet(io.BytesIO(self._artifact_store.get(f"{prefix}.parquet")))
        if meta.get("kind") == "series":
            series = frame.iloc[:, 0]
            series.name = meta.get("name")
            return series
        return frame

    def _write_cached(self, name: str, value: Any) -> Any:
        """Persist a calculation with metadata that preserves None and JSON types."""
        prefix = self._cache_prefix(name)
        if isinstance(value, pd.Series):
            self._artifact_store.put_immutable(
                f"{prefix}.parquet",
                value.to_frame(name=value.name or "value").to_parquet(index=True),
            )
            self._artifact_store.put_immutable(
                f"{prefix}.meta.json",
                json.dumps(
                    {"kind": "series", "name": value.name},
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode(),
            )
            return value
        if isinstance(value, pd.DataFrame):
            self._artifact_store.put_immutable(f"{prefix}.parquet", value.to_parquet(index=True))
            self._artifact_store.put_immutable(f"{prefix}.meta.json", b'{"kind":"dataframe"}')
            return value
        normalized = json.loads(
            json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
        )
        if normalized is None:
            self._artifact_store.put_immutable(f"{prefix}.meta.json", b'{"kind":"none"}')
        else:
            self._artifact_store.put_immutable(
                f"{prefix}.json",
                json.dumps(
                    normalized,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                ).encode(),
            )
            self._artifact_store.put_immutable(f"{prefix}.meta.json", b'{"kind":"json"}')
        return normalized

    def calc(self, name: str) -> Any:
        """Evaluate a named calculation once, using immutable cache entries."""
        if name in self._memo:
            logger.debug("stage=3 calculation memoized report={} calc={}", self.report_id, name)
            return self._memo[name]
        cached = self._read_cached(name)
        if cached is not _CACHE_MISS:
            self.cache_hits[name] = True
            self._memo[name] = cached
            logger.info("stage=3 calculation cache-hit report={} calc={}", self.report_id, name)
            return cached
        try:
            fn = self._calc_fns[name]
        except KeyError as exc:
            raise KeyError(f"unknown report calculation: {name!r}") from exc
        if name in self._active_calcs:
            raise ValueError(f"calculation cycle detected at {name!r}")
        self.cache_hits[name] = False
        self._active_calcs.add(name)
        logger.info("stage=3 calculation start report={} calc={}", self.report_id, name)
        try:
            value = fn(self)
            value = self._write_cached(name, value)
            self._memo[name] = value
            logger.info(
                "stage=3 calculation complete report={} calc={} cache_hit=false",
                self.report_id,
                name,
            )
            return value
        finally:
            self._active_calcs.remove(name)
