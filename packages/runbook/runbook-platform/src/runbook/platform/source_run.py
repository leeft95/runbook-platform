from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime

from loguru import logger
from runbook.data import DatabasePointerRegistry, SourceConfig, open_pointer_registry
from runbook.data.ingest import IngestRequest, run_ingest
from runbook.data.pipeline import slot_key


@dataclass(frozen=True)
class SourceOutcome:
    source_id: str
    slot: str
    status: str
    datasets: dict[str, str] | None = None
    reason: str | None = None

    def as_dict(self) -> dict:
        """Return the database-persistable source outcome."""
        return asdict(self)


def run_source(
    *,
    store,
    config: SourceConfig,
    slot: datetime,
    pointer_registry: DatabasePointerRegistry | None = None,
) -> SourceOutcome:
    """Run one source slot; run state is persisted by the service plane."""
    slot_id = slot_key(slot)
    logger.info("source task start source={} slot={}", config.source_id, slot_id)
    try:
        registry = pointer_registry or open_pointer_registry()
        result = run_ingest(
            IngestRequest(source_config=config, run_time=slot),
            store=store,
            pointer_registry=registry,
        )
        if result.status.value != "ready":
            outcome = SourceOutcome(
                config.source_id,
                slot_id,
                result.status.value,
                reason=result.message,
            )
        else:
            outcome = SourceOutcome(config.source_id, slot_id, "success", datasets=result.datasets)
        logger.info(
            "source task complete source={} slot={} status={}",
            config.source_id,
            slot_id,
            outcome.status,
        )
        return outcome
    except Exception as exc:
        outcome = SourceOutcome(config.source_id, slot_id, "failed", reason=str(exc))
        logger.error(
            "source task failed source={} slot={} reason={}",
            config.source_id,
            slot_id,
            exc,
        )
        return outcome
