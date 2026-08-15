from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(payload: Any) -> str:
    """Return strict, deterministic JSON for identities and cache keys.

    Callers must pass JSON values.  Silently stringifying arbitrary Python
    objects makes identities depend on repr/locale/implementation details.
    """
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def sha256_hexdigest(payload: str) -> str:
    """Handle sha256 hexdigest."""
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def sha256_json(payload: Any) -> str:
    """Hash a JSON-compatible value after canonical serialization."""
    return sha256_hexdigest(canonical_json(payload))


def sha256_bytes(payload: bytes) -> str:
    """Handle sha256 bytes."""
    return hashlib.sha256(payload).hexdigest()


def snapshot_id_from_inputs(snapshot_inputs: Any) -> str:
    """Handle snapshot id from inputs."""
    return sha256_json(snapshot_inputs)
