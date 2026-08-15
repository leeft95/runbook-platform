from __future__ import annotations

from typing import Any

from ._config import register_config_page


def register(dash_app: Any, sessions: Any) -> None:
    """Register the Profiles page."""
    register_config_page(
        dash_app,
        sessions,
        module=__name__,
        kind="profile",
        path="/profiles",
        name="Profiles",
        order=1,
    )
