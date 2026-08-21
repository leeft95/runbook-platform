"""Central namespaced component ID generation for PDL Dash pages."""

from __future__ import annotations

import re
from dataclasses import dataclass

_SAFE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$")


def validate_namespace(namespace: str) -> str:
    """Validate the host-provided page namespace."""
    if not isinstance(namespace, str) or not _SAFE.fullmatch(namespace):
        raise ValueError(f"invalid Dash page namespace: {namespace!r}")
    return namespace


@dataclass(frozen=True)
class DashIds:
    """Generate globally unique IDs from one host/page namespace."""

    namespace: str

    def __post_init__(self) -> None:
        validate_namespace(self.namespace)

    def _component(self, kind: str, local_name: str) -> str:
        if not _SAFE.fullmatch(local_name):
            raise ValueError(f"invalid PDL {kind} name: {local_name!r}")
        return f"pdl-{self.namespace}-{kind}-{local_name}"

    def block(self, local_name: str) -> str:
        return self._component("block", local_name)

    def control(self, local_name: str) -> str:
        return self._component("control", local_name)


__all__ = ["DashIds", "validate_namespace"]
