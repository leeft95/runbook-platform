"""Reusable local-file readiness and acquisition capability."""

from __future__ import annotations

import mimetypes
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from loguru import logger
from runbook.data.config import SourceConfig
from runbook.data.ingest.models import (
    AcquisitionResult,
    PreviousAcquisitionState,
    RawArtifactRecord,
    ReadinessResult,
    ReadinessStatus,
)


@dataclass
class LocalFileAdapter:
    def validate(self, source_config: SourceConfig) -> None:
        """Require a configured local file path."""
        path = source_config.params.get("local_path")
        if not isinstance(path, str) or not path:
            raise ValueError("local_file adapter requires params.local_path")

    def check(self, *, source_config: SourceConfig, acquisition_run: str, observed_at) -> ReadinessResult:
        """Check local file availability without reading its contents."""
        self.validate(source_config)
        path = Path(source_config.params["local_path"])
        return ReadinessResult(
            source_id=source_config.source_id,
            acquisition_run=acquisition_run,
            status=ReadinessStatus.ready if path.exists() else ReadinessStatus.not_ready,
            observed_at=observed_at,
            remote_filename=str(source_config.params.get("filename") or path.name),
            remote_locator=str(path),
            metadata={"local_path": str(path)},
        )

    def acquire(
        self,
        *,
        source_config: SourceConfig,
        readiness: ReadinessResult,
        fetched_at,
        previous_watermarks: Mapping[str, datetime] | None = None,
        previous_state: PreviousAcquisitionState | None = None,
    ) -> AcquisitionResult:
        """Read the validated local file into an acquisition result."""
        self.validate(source_config)
        path = Path(
            readiness.metadata.get("local_path") or readiness.remote_locator or source_config.params["local_path"]
        )
        filename = readiness.remote_filename or path.name
        logger.info(
            "query start source={} operation=local-read path={}",
            source_config.source_id,
            path,
        )
        payload = path.read_bytes()
        logger.info(
            "query complete source={} operation=local-read bytes={}",
            source_config.source_id,
            len(payload),
        )
        return AcquisitionResult(
            record=RawArtifactRecord(
                source_id=source_config.source_id,
                acquisition_run=readiness.acquisition_run,
                source_filename=filename,
                source_locator=str(path),
                fetched_at=fetched_at,
                content_type=mimetypes.guess_type(filename)[0] or "application/octet-stream",
            ),
            payload=payload,
        )


__all__ = ["LocalFileAdapter"]
