"""Embeddable Dash page contract; the host owns the root Dash application."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from runbook.sdk.extensions.dash.ids import DashIds, validate_namespace


@dataclass(frozen=True)
class DashPage:
    """An immutable page layout plus separately registered callbacks."""

    layout_factory: Callable[[], Any]
    callback_registrar: Callable[[Any], None]
    namespace: str

    def __post_init__(self) -> None:
        validate_namespace(self.namespace)

    @property
    def ids(self) -> DashIds:
        return DashIds(self.namespace)

    def layout(self) -> Any:
        """Build this page's embeddable layout tree."""
        return self.layout_factory()

    def register_callbacks(self, app: Any) -> None:
        """Register this page's callbacks onto a host-owned Dash app."""
        self.callback_registrar(app)


__all__ = ["DashPage"]
