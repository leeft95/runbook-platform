from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OperationsBrand:
    name: str = "Runbook"
    logo_src: str | None = None
    favicon_src: str | None = None
    primary: str | None = None
    primary_hover: str | None = None
    primary_soft: str | None = None
