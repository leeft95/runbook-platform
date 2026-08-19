from __future__ import annotations

from typing import Any

from ._config import register_config_page


def register(dash_app: Any, sessions: Any) -> None:
    """Register the Sources page."""
    register_config_page(
        dash_app,
        sessions,
        module=__name__,
        kind="source",
        path="/sources",
        name="Sources",
        order=0,
    )
