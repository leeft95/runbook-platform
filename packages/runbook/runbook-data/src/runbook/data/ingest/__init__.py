"""Source acquisition, adapters, parsers, and curation entry points."""

from runbook.data.ingest.adapters import HistoricalSourceAdapter, SourceAdapter
from runbook.data.ingest.models import (
    AcquisitionResult,
    AcquisitionStageResult,
    CuratedFrame,
    CurationResult,
    HistoricalExecutionContext,
    IngestRequest,
    IngestResult,
    PreviousAcquisitionState,
    RawArtifactRecord,
    ReadinessResult,
    ReadinessStatus,
    SourceConfig,
)
from runbook.data.ingest.parsers import Stage2Parser
from runbook.data.ingest.runner import (
    load_previous_acquisition_state,
    run_ingest,
    run_stage1_acquire,
)

__all__ = [
    "AcquisitionResult",
    "AcquisitionStageResult",
    "CurationResult",
    "CuratedFrame",
    "IngestRequest",
    "IngestResult",
    "HistoricalExecutionContext",
    "HistoricalSourceAdapter",
    "PreviousAcquisitionState",
    "RawArtifactRecord",
    "ReadinessResult",
    "ReadinessStatus",
    "SourceConfig",
    "load_previous_acquisition_state",
    "run_ingest",
    "run_stage1_acquire",
    "SourceAdapter",
    "Stage2Parser",
]
