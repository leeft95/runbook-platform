"""Small generic local/S3 blob store primitive."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlparse

from loguru import logger

from .utils.hashing import canonical_json

DEFAULT_STORE_URI = "file:.runbook"


class BlobStore:
    """Byte store with atomic local writes and immutable object support."""

    def __init__(self, uri: str):
        parsed = urlparse(uri)
        self.scheme = parsed.scheme or "file"
        if self.scheme == "file":
            self.root: Path | None = Path(parsed.path or parsed.netloc or uri).expanduser().resolve()
            self.bucket = None
            self.prefix = ""
        elif self.scheme == "s3":
            if not parsed.netloc:
                raise ValueError(f"S3 URI requires a bucket: {uri!r}")
            self.root = None
            self.bucket = parsed.netloc
            self.prefix = parsed.path.strip("/")
        else:
            raise ValueError(f"unsupported store URI scheme: {self.scheme!r}")

    def _key(self, key: str) -> str:
        """Validate a relative object key and apply the configured prefix."""
        normalized = str(PurePosixPath(key))
        if normalized.startswith("/") or normalized.startswith("../") or normalized == ".." or "/../" in normalized:
            raise ValueError(f"invalid blob key: {key!r}")
        return "/".join(part for part in (self.prefix, normalized) if part)

    def _write(self, key: str, payload: bytes, *, mode: str) -> str:
        """Write one blob atomically and emit a backend diagnostic."""
        normalized = str(PurePosixPath(key))
        self._key(normalized)
        if self.scheme == "file":
            assert self.root is not None
            target = self.root / normalized
            target.parent.mkdir(parents=True, exist_ok=True)
            fd, temp_name = tempfile.mkstemp(prefix=".runbook-", dir=target.parent)
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp_name, target)
            finally:
                if os.path.exists(temp_name):
                    os.unlink(temp_name)
        else:
            import boto3

            boto3.client(
                "s3",
                endpoint_url=os.getenv("S3_ENDPOINT_URL"),
                region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
            ).put_object(Bucket=self.bucket, Key=self._key(normalized), Body=payload)
        logger.info("write backend={} mode={} key={} bytes={}", self.scheme, mode, normalized, len(payload))
        return normalized

    def put(self, key: str, payload: bytes) -> str:
        """Write one mutable blob."""
        return self._write(key, payload, mode="mutable")

    def put_immutable(self, key: str, payload: bytes) -> str:
        """Create a blob once, accepting identical retries."""
        normalized = str(PurePosixPath(key))
        self._key(normalized)
        if self.exists(normalized):
            if self.get(normalized) != payload:
                raise IOError(f"immutable blob conflict: {normalized}")
            logger.debug("write skipped backend={} mode=immutable key={} reason=identical", self.scheme, normalized)
            return normalized
        return self._write(normalized, payload, mode="immutable")

    def get(self, key: str) -> bytes:
        """Read one complete blob."""
        normalized = str(PurePosixPath(key))
        self._key(normalized)
        if self.scheme == "file":
            assert self.root is not None
            return (self.root / normalized).read_bytes()
        import boto3

        return (
            boto3.client(
                "s3",
                endpoint_url=os.getenv("S3_ENDPOINT_URL"),
                region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
            )
            .get_object(Bucket=self.bucket, Key=self._key(normalized))["Body"]
            .read()
        )

    def exists(self, key: str) -> bool:
        """Return whether a blob exists."""
        normalized = str(PurePosixPath(key))
        self._key(normalized)
        if self.scheme == "file":
            assert self.root is not None
            return (self.root / normalized).is_file()
        import boto3

        try:
            boto3.client(
                "s3",
                endpoint_url=os.getenv("S3_ENDPOINT_URL"),
                region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
            ).head_object(Bucket=self.bucket, Key=self._key(normalized))
        except Exception as exc:
            code = getattr(exc, "response", {}).get("Error", {}).get("Code")
            if code in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise
        return True

    def put_json(self, key: str, payload: Any) -> str:
        """Write a canonical JSON document."""
        return self.put(key, canonical_json(payload).encode())

    def get_json(self, key: str) -> Any:
        """Read a JSON document."""
        return json.loads(self.get(key).decode())


def open_blob_store(uri: str | None = None) -> BlobStore:
    """Open the configured local or S3 store."""
    return BlobStore(uri or os.environ.get("RUNBOOK_DATA_STORE_URI") or DEFAULT_STORE_URI)


__all__ = ["BlobStore", "DEFAULT_STORE_URI", "open_blob_store"]
