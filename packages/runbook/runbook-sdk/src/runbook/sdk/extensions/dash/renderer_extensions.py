"""Presentation hooks for the public Dash renderer."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from runbook.core.pdl.models import PDLManifest
from runbook.sdk.extensions.dash.models import DashControl


@dataclass(frozen=True)
class DashRenderedControl:
    """A custom Dash control and its native-to-logical input binding."""

    component: Any
    input_properties: tuple[str, ...]
    decode: Callable[[tuple[Any, ...]], Any] | None = None


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
    ) -> DashRenderedControl | Any | None:
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


__all__ = ["DashRenderedControl", "DashRendererExtension"]
