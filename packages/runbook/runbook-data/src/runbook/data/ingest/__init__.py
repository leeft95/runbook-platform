"""Source acquisition, adapters, parsers, and curation entry points."""

from runbook.data.ingest.models import (
    AcquisitionResult,
    CuratedFrame,
    IngestRequest,
    IngestResult,
    RawArtifactRecord,
    ReadinessResult,
    ReadinessStatus,
    SourceConfig,
)
from runbook.data.ingest.runner import run_ingest

__all__ = [
    "AcquisitionResult",
    "CuratedFrame",
    "IngestRequest",
    "IngestResult",
    "RawArtifactRecord",
    "ReadinessResult",
    "ReadinessStatus",
    "SourceConfig",
    "run_ingest",
]
