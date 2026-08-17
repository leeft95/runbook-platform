"""Source acquisition, adapters, parsers, and curation entry points."""

from runbook.data.ingest.models import (
    AcquisitionResult,
    AcquisitionStageResult,
    CuratedFrame,
    CurationResult,
    IngestRequest,
    IngestResult,
    RawArtifactRecord,
    ReadinessResult,
    ReadinessStatus,
    SourceConfig,
)
from runbook.data.ingest.runner import run_ingest, run_stage1_acquire

__all__ = [
    "AcquisitionResult",
    "AcquisitionStageResult",
    "CurationResult",
    "CuratedFrame",
    "IngestRequest",
    "IngestResult",
    "RawArtifactRecord",
    "ReadinessResult",
    "ReadinessStatus",
    "SourceConfig",
    "run_ingest",
    "run_stage1_acquire",
]
