from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime

from loguru import logger
from runbook.data import (
    DatabasePointerRegistry,
    open_pointer_registry,
    resolve_snapshot,
)
from runbook.data.pipeline import slot_key
from runbook.sdk import ReportProfile, execute_report, resolve_code_version


@dataclass(frozen=True)
class ReportOutcome:
    profile_id: str
    slot: str
    status: str
    artifact_id: str | None = None
    snapshot_id: str | None = None
    context_hash: str | None = None
    code_version: str | None = None
    prefix: str | None = None
    html_ref: str | None = None
    stage3_ref: str | None = None
    stage4_ref: str | None = None
    cache_hits: dict[str, bool] | None = None
    reason: str | None = None

    def as_dict(self) -> dict:
        """Return the database-persistable report outcome."""
        return asdict(self)


def run_report(
    *,
    store,
    profile: ReportProfile,
    slot: datetime,
    code_version: str | None = None,
    reports_root: str = "reports",
    snapshot=None,
    pointer_registry: DatabasePointerRegistry | None = None,
) -> ReportOutcome:
    """Publish one immutable report artifact set; run state is service-owned."""
    slot_id = slot_key(slot)
    logger.info("report task start report={} slot={}", profile.profile_id, slot_id)
    try:
        resolved_code = resolve_code_version(code_version)
        pinned_snapshot = snapshot is not None
        if pinned_snapshot:
            resolved_snapshot = snapshot
        else:
            registry = pointer_registry or open_pointer_registry()
            resolved_snapshot = resolve_snapshot(
                store,
                profile.datasets,
                pointer_registry=registry,
            )
        if not pinned_snapshot and resolved_snapshot.watermark < slot:
            logger.info(
                "report task waiting report={} slot={} reason=watermark",
                profile.profile_id,
                slot_id,
            )
            return ReportOutcome(
                profile.profile_id,
                slot_id,
                "waiting",
                reason="dataset watermark is behind report slot",
            )
        logger.info(
            "stage=3 compute report={} slot={} snapshot={}",
            profile.profile_id,
            slot_id,
            resolved_snapshot.snapshot_id,
        )
        result = execute_report(
            store=store,
            profile=profile,
            snapshot=resolved_snapshot,
            code_version=resolved_code,
            reports_root=reports_root,
        )
        outcome = ReportOutcome(
            profile.profile_id,
            slot_id,
            "success",
            artifact_id=result.artifact_id,
            snapshot_id=result.snapshot_id,
            context_hash=result.context_hash,
            code_version=result.code_version,
            prefix=result.prefix,
            html_ref=result.html_ref,
            stage3_ref=result.stage3_ref,
            stage4_ref=result.stage4_ref,
            cache_hits=result.cache_hits,
        )
        logger.info(
            "report task complete report={} slot={} status=success artifact={}",
            profile.profile_id,
            slot_id,
            result.artifact_id,
        )
        return outcome
    except ValueError as exc:
        if str(exc).startswith("no pointer exists for dataset"):
            logger.info(
                "report task waiting report={} slot={} reason={}",
                profile.profile_id,
                slot_id,
                exc,
            )
            return ReportOutcome(profile.profile_id, slot_id, "waiting", reason=str(exc))
        logger.exception(
            "report task failed report={} slot={} reason={}",
            profile.profile_id,
            slot_id,
            exc,
        )
        return ReportOutcome(profile.profile_id, slot_id, "failed", reason=str(exc))
    except Exception as exc:
        logger.exception(
            "report task failed report={} slot={} reason={}",
            profile.profile_id,
            slot_id,
            exc,
        )
        return ReportOutcome(profile.profile_id, slot_id, "failed", reason=str(exc))
