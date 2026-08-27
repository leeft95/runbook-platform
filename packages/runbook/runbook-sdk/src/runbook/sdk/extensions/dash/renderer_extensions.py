"""Presentation hooks for the public Dash renderer."""

from __future__ import annotations

from typing import Any, Protocol

from runbook.core.pdl.models import PDLManifest
from runbook.sdk.extensions.dash.models import DashControl


class DashRendererExtension(Protocol):
    """Optional trusted-Python presentation hooks for a rendered Dash page."""

    def wrap_page(self, content: Any, *, manifest: PDLManifest, namespace: str) -> Any | None:
        """Wrap the complete page content, or return ``None`` for vanilla output."""
        ...

    def render_control(
        self,
        control: DashControl,
        *,
        component_id: str,
        options: list[Any] | None,
    ) -> Any | None:
        """Render one control, or return ``None`` for its vanilla component."""
        ...

    def wrap_block(
        self,
        body: Any,
        *,
        block: Any,
        title: Any | None,
        namespace: str,
    ) -> Any | None:
        """Wrap one public-rendered block body, or return ``None`` for vanilla output."""
        ...


__all__ = ["DashRendererExtension"]
