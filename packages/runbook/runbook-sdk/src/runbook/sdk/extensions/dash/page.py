"""Embeddable Dash page contract; the host owns the root Dash application."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from runbook.sdk.extensions.dash.ids import DashIds, validate_namespace

RouteResolver = Callable[[str, str], str | None]


@dataclass(frozen=True)
class DashPage:
    """An immutable page layout plus separately registered callbacks."""

    layout_factory: Callable[[], Any]
    callback_registrar: Callable[[Any], None]
    namespace: str
    plot_layout_factory: Callable[[str], Any] | None = None

    def __post_init__(self) -> None:
        validate_namespace(self.namespace)

    @property
    def ids(self) -> DashIds:
        """Return the central ID helper for this page namespace."""
        return DashIds(self.namespace)

    def layout(self) -> Any:
        """Build this page's embeddable layout tree."""
        return self.layout_factory()

    def register_callbacks(self, app: Any) -> None:
        """Register this page's callbacks onto a host-owned Dash app."""
        self.callback_registrar(app)

    def plot_layout(self, name: str) -> Any:
        """Build a native Dash detail layout for one logical plot name."""
        if self.plot_layout_factory is None:
            raise ValueError("this DashPage does not expose native plot pages")
        return self.plot_layout_factory(name)


__all__ = ["DashPage", "RouteResolver"]
