"""Small immutable worker-log storage helpers."""

from __future__ import annotations

import hashlib
import os
import traceback
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from multiprocessing import current_process
from threading import Event, Lock, Thread, current_thread
from typing import Any, Iterator
from urllib.parse import quote

from loguru import logger
from runbook.data import BlobStore, open_blob_store
from runbook.data.pipeline import slot_key

_ORDINARY_BYTES = 96 * 1024
_EXCEPTION_BYTES = 32 * 1024
_PART_BYTES = 16 * 1024
_STORE_WRITE_LOCK = Lock()


@dataclass(frozen=True)
class RunLogIdentity:
    """Stable identity used to address one run's diagnostic log."""

    run_id: str
    kind: str
    target_id: str
    slot: datetime
    report_id: str | None = None


def run_log_prefix(identity: RunLogIdentity) -> str:
    """Return the immutable logical prefix for a run log."""
    slot = slot_key(identity.slot)
    if identity.kind in {"profile", "report"} or identity.report_id is not None:
        report_id = _safe_segment(identity.report_id or identity.target_id)
        profile_id = _safe_segment(identity.target_id)
        run_id = _safe_segment(identity.run_id)
        return f"operations/logs/reports/{report_id}/profile={profile_id}/slot={slot}/run={run_id}/"
    source_id = _safe_segment(identity.target_id)
    run_id = _safe_segment(identity.run_id)
    return f"operations/logs/sources/{source_id}/slot={slot}/run={run_id}/"


def _safe_segment(value: str) -> str:
    """Encode an identity as one blob-key segment, including dot segments."""
    encoded = quote(str(value), safe="-_.")
    return f"_{encoded}" if encoded in {".", ".."} else encoded


def _utc_now() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


def _format_record(message: Any) -> tuple[bytes, bool]:
    """Format one Loguru record and identify exception records."""
    record = message.record
    stamp = record["time"].astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    prefix = f"{stamp} level={record['level'].name} pid={record['process'].id} process={record['process'].name} "
    body = str(record["message"])
    exception = record.get("exception")
    if exception is not None:
        body += "\n" + "".join(traceback.format_exception(exception.type, exception.value, exception.traceback)).rstrip(
            "\n"
        )
    return (prefix + body + "\n").encode("utf-8", errors="replace"), exception is not None


@dataclass
class _Capture:
    store: BlobStore
    identity: RunLogIdentity
    parts: list[dict[str, Any]] = field(default_factory=list)
    ordinary_used: int = 0
    exception_used: int = 0
    ordinary_truncated: bool = False
    exception_truncated: bool = False
    _buffer: bytearray = field(default_factory=bytearray)
    _lines: int = 0
    _part_number: int = 0
    _lock: Lock = field(default_factory=Lock)
    _stop: Event = field(default_factory=Event, repr=False)
    _flusher: Thread | None = field(default=None, repr=False)
    _finished: bool = False

    @property
    def prefix(self) -> str:
        """Return this capture's blob prefix."""
        return run_log_prefix(self.identity)

    @property
    def log_ref(self) -> str:
        """Return this capture's terminal manifest reference."""
        return f"{self.prefix}manifest.json"

    def add(self, payload: bytes, *, exception: bool) -> None:
        """Buffer bytes within the ordinary or exception allowance."""
        with self._lock:
            limit = _EXCEPTION_BYTES if exception else _ORDINARY_BYTES
            used = self.exception_used if exception else self.ordinary_used
            remaining = max(0, limit - used)
            if not remaining:
                if exception:
                    self.exception_truncated = True
                else:
                    self.ordinary_truncated = True
                return
            if len(payload) > remaining:
                marker = b"[runbook log truncated]\n"
                payload = payload[: max(0, remaining - len(marker))] + marker[:remaining]
                if exception:
                    self.exception_truncated = True
                else:
                    self.ordinary_truncated = True
            if exception:
                self.exception_used += len(payload)
            else:
                self.ordinary_used += len(payload)
            self._buffer.extend(payload)
            self._lines += payload.count(b"\n")
            while len(self._buffer) >= _PART_BYTES:
                before = len(self._buffer)
                self._flush(_PART_BYTES)
                if len(self._buffer) == before:
                    break

    def _flush(self, size: int) -> None:
        """Persist up to ``size`` buffered bytes as the next immutable part."""
        if not size:
            return
        payload = bytes(self._buffer[:size])
        line_count = payload.count(b"\n")
        part_number = self._part_number + 1
        ref = f"{self.prefix}part={part_number:06d}.log"
        try:
            self._put(ref, payload)
        except Exception:
            # Capture must never change the run outcome.
            return
        del self._buffer[:size]
        self._part_number = part_number
        self.parts.append(
            {
                "part": part_number,
                "ref": ref,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "bytes": len(payload),
                "lines": line_count,
            }
        )
        self._lines -= line_count

    def start(self) -> None:
        """Flush residual output in the background while the worker runs."""
        self._flusher = Thread(target=self._flush_loop, name="runbook-log-flusher", daemon=True)
        self._flusher.start()

    def _flush_loop(self) -> None:
        """Flush pending output every two seconds until capture stops."""
        while not self._stop.wait(2.0):
            with self._lock:
                if self._buffer:
                    self._flush(min(len(self._buffer), _PART_BYTES))

    def _stop_flusher(self) -> None:
        """Stop and join the periodic flush thread."""
        self._stop.set()
        if self._flusher is not None and self._flusher is not current_thread():
            self._flusher.join(timeout=2.5)
        self._flusher = None

    def _put(self, ref: str, payload: bytes) -> None:
        """Write without recursively routing BlobStore's progress log here."""
        with _STORE_WRITE_LOCK:
            with logger.contextualize(run_log_internal=True):
                self.store.put_immutable(ref, payload)

    def sink(self, message: Any) -> None:
        """Accept an INFO-or-higher Loguru record without propagating errors."""
        if message.record.get("extra", {}).get("run_log_internal"):
            return
        try:
            payload, exception = _format_record(message)
            self.add(payload, exception=exception)
        except Exception:
            return

    def write_exception(self, exc: BaseException) -> None:
        """Append a full standard traceback using reserved exception capacity."""
        payload = (
            f"{_utc_now().isoformat(timespec='milliseconds').replace('+00:00', 'Z')} level=ERROR "
            f"pid={os.getpid()} process={current_process().name} worker failure: {exc}\n"
            + "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        ).encode("utf-8", errors="replace")
        self.add(payload, exception=True)

    def resume(self) -> None:
        """Resume a crash log so a parent fallback follows existing chunks."""
        with self._lock:
            part_number = 1
            total = 0
            while part_number <= 8192:
                ref = f"{self.prefix}part={part_number:06d}.log"
                if not self.store.exists(ref):
                    break
                payload = self.store.get(ref)
                self.parts.append(
                    {
                        "part": part_number,
                        "ref": ref,
                        "sha256": hashlib.sha256(payload).hexdigest(),
                        "bytes": len(payload),
                        "lines": payload.count(b"\n"),
                    }
                )
                total += len(payload)
                part_number += 1
            self._part_number = part_number - 1
            self.ordinary_used = min(total, _ORDINARY_BYTES)
            self.exception_used = min(max(0, total - _ORDINARY_BYTES), _EXCEPTION_BYTES)

    def finish(self, *, incomplete: bool = False) -> str:
        """Flush remaining bytes and write the immutable terminal manifest."""
        if self._finished:
            return self.log_ref
        self._stop_flusher()
        with self._lock:
            while self._buffer:
                before = len(self._buffer)
                self._flush(min(before, _PART_BYTES))
                if len(self._buffer) == before:
                    break
            payload = {
                "schema_version": "run-log/1",
                "identity": asdict(self.identity),
                "parts": self.parts,
                "bytes": sum(item["bytes"] for item in self.parts),
                "lines": sum(item["lines"] for item in self.parts),
                "truncated": self.ordinary_truncated or self.exception_truncated,
                "ordinary_truncated": self.ordinary_truncated,
                "exception_truncated": self.exception_truncated,
                "incomplete": incomplete,
                "completed_at": _utc_now().isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            }
            try:
                self._put(self.log_ref, _json_bytes(payload))
            except Exception:
                pass
            self._finished = True
            return self.log_ref


def _json_bytes(value: Any) -> bytes:
    """Serialize a compact deterministic JSON payload."""
    import json

    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


@contextmanager
def capture_worker_logs(store_uri: str, identity: RunLogIdentity) -> Iterator[_Capture]:
    """Capture INFO+ Loguru records into immutable chunks and a manifest."""
    capture = _Capture(open_blob_store(store_uri), identity)
    token = logger.add(
        capture.sink,
        level="INFO",
        diagnose=False,
        filter=lambda record: not record["extra"].get("run_log_internal", False),
    )
    capture.start()
    try:
        yield capture
    finally:
        logger.remove(token)
        capture.finish()


def write_failure_log(
    store_uri: str,
    identity: RunLogIdentity,
    exception: BaseException,
    *,
    incomplete: bool = False,
) -> str:
    """Persist a compact failure traceback without raising capture errors."""
    try:
        capture = _Capture(open_blob_store(store_uri), identity)
        capture.resume()
        capture.write_exception(exception)
        return capture.finish(incomplete=incomplete)
    except Exception:
        return f"{run_log_prefix(identity)}manifest.json"


def read_log_tail(store: BlobStore, identity: RunLogIdentity, after_part: int = 0) -> dict[str, Any]:
    """Read available numbered chunks after ``after_part`` and any manifest."""
    prefix = run_log_prefix(identity)
    parts: list[dict[str, Any]] = []
    text_parts: list[str] = []
    part = max(0, int(after_part)) + 1
    while part <= 8192:
        ref = f"{prefix}part={part:06d}.log"
        if not store.exists(ref):
            break
        payload = store.get(ref)
        parts.append({"part": part, "ref": ref, "bytes": len(payload)})
        text_parts.append(payload.decode("utf-8", errors="replace"))
        part += 1
    manifest = store.get_json(f"{prefix}manifest.json") if store.exists(f"{prefix}manifest.json") else None
    incomplete = bool(manifest and manifest.get("incomplete"))
    return {
        "text": "".join(text_parts),
        "parts": parts,
        "next_part": part - 1,
        "manifest": manifest,
        "complete": manifest is not None and not incomplete,
        "incomplete": incomplete,
        "terminal": manifest is not None,
        "truncated": bool(manifest and manifest.get("truncated")),
    }


__all__ = [
    "RunLogIdentity",
    "capture_worker_logs",
    "read_log_tail",
    "run_log_prefix",
    "write_failure_log",
]
