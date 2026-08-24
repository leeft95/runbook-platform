"""Reusable HTTP readiness and acquisition capability."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping
from urllib.parse import urlsplit, urlunsplit

from loguru import logger
from runbook.data.config import SourceConfig
from runbook.data.ingest.adapters.base.templates import (
    filename_from_locator,
    render_template,
)
from runbook.data.ingest.models import (
    AcquisitionResult,
    PreviousAcquisitionState,
    RawArtifactRecord,
    ReadinessResult,
    ReadinessStatus,
)

requests: Any = None
try:
    import requests as _requests
except ImportError:  # pragma: no cover
    pass
else:
    requests = _requests

_READINESS_KEYS = (
    "readiness_url_template",
    "readiness_url",
    "download_url_template",
    "download_url",
    "url",
)
_DOWNLOAD_KEYS = (
    "download_url_template",
    "download_url",
    "url",
    "readiness_url_template",
    "readiness_url",
)


def _safe_locator(locator: str) -> str:
    """Remove query strings and fragments before a locator is written to logs."""
    parsed = urlsplit(locator)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def _locator(config: SourceConfig, run: str, observed_at, keys: tuple[str, ...]) -> str | None:
    """Resolve the first configured readiness or download URL template."""
    for key in keys:
        value = config.params.get(key)
        rendered = render_template(value, acquisition_run=run, observed_at=observed_at)
        if rendered:
            return rendered
        if isinstance(value, str) and value:
            return value
    return None


def _filename(config: SourceConfig, run: str, observed_at, locator: str, response: Any) -> str:
    """Choose a configured, header-derived, or URL-derived source filename."""
    value = render_template(
        config.params.get("filename_template"),
        acquisition_run=run,
        observed_at=observed_at,
    )
    if value:
        return value
    headers = getattr(response, "headers", {})
    disposition = headers.get("content-disposition", "") if isinstance(headers, Mapping) else ""
    return disposition.partition("filename=")[2].strip("\"' ") or filename_from_locator(locator)


@dataclass
class HttpAdapter:
    session: Any | None = None

    def validate(self, source_config: SourceConfig) -> None:
        """Require at least one usable HTTP locator."""
        if not any(source_config.params.get(key) for key in {*_READINESS_KEYS, *_DOWNLOAD_KEYS}):
            raise ValueError("http adapter requires a URL or URL template")

    def check(self, *, source_config: SourceConfig, acquisition_run: str, observed_at) -> ReadinessResult:
        """Stream a readiness GET and classify HTTP status without downloading the body."""
        self.validate(source_config)
        if requests is None and self.session is None:
            raise ImportError("requests is required for http readiness checks")
        locator = _locator(source_config, acquisition_run, observed_at, _READINESS_KEYS)
        assert locator is not None
        logger.info(
            "query start source={} operation=http-readiness locator={}",
            source_config.source_id,
            _safe_locator(locator),
        )
        session = self.session or requests.Session()
        response = session.get(locator, timeout=30, stream=True)
        try:
            code = int(response.status_code)
            status = (
                ReadinessStatus.ready
                if code < 400
                else ReadinessStatus.not_ready
                if code == 404 or (400 <= code < 500 and code not in {401, 403})
                else ReadinessStatus.failed
            )
            logger.info(
                "query complete source={} operation=http-readiness status={} outcome={}",
                source_config.source_id,
                code,
                status.value,
            )
            return ReadinessResult(
                source_id=source_config.source_id,
                acquisition_run=acquisition_run,
                status=status,
                observed_at=observed_at,
                remote_filename=_filename(source_config, acquisition_run, observed_at, locator, response),
                remote_locator=locator,
                message=None if status is ReadinessStatus.ready else f"HTTP readiness status {code}",
            )
        finally:
            close = getattr(response, "close", None)
            if callable(close):
                close()

    def acquire(
        self,
        *,
        source_config: SourceConfig,
        readiness: ReadinessResult,
        fetched_at,
        previous_watermarks: Mapping[str, datetime] | None = None,
        previous_state: PreviousAcquisitionState | None = None,
    ) -> AcquisitionResult:
        """Download the configured locator and return its raw bytes and metadata."""
        self.validate(source_config)
        if requests is None and self.session is None:
            raise ImportError("requests is required for http acquisition")
        locator = (
            _locator(source_config, readiness.acquisition_run, fetched_at, _DOWNLOAD_KEYS) or readiness.remote_locator
        )
        if not locator:
            raise ValueError("http acquisition requires a URL")
        logger.info(
            "query start source={} operation=http-download locator={}",
            source_config.source_id,
            _safe_locator(locator),
        )
        response = (self.session or requests.Session()).get(locator, timeout=60, stream=True)
        try:
            status = int(response.status_code)
            try:
                response.raise_for_status()
            except Exception as exc:
                logger.error(
                    "query failed source={} operation=http-download status={} reason={}",
                    source_config.source_id,
                    status,
                    exc,
                )
                raise
            headers = getattr(response, "headers", {})
            payload = response.content
            logger.info(
                "query complete source={} operation=http-download status={} bytes={}",
                source_config.source_id,
                status,
                len(payload),
            )
            return AcquisitionResult(
                record=RawArtifactRecord(
                    source_id=source_config.source_id,
                    acquisition_run=readiness.acquisition_run,
                    source_filename=readiness.remote_filename
                    or _filename(
                        source_config,
                        readiness.acquisition_run,
                        fetched_at,
                        locator,
                        response,
                    ),
                    source_locator=locator,
                    fetched_at=fetched_at,
                    content_type=headers.get("content-type"),
                ),
                payload=payload,
            )
        finally:
            close = getattr(response, "close", None)
            if callable(close):
                close()


__all__ = ["HttpAdapter"]
