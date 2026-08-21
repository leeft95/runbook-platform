from __future__ import annotations

from collections.abc import Sequence
from typing import TypeGuard

from runbook.sdk.extensions.dash.models import (
    DashControl,
    DashDateRange,
    DashExtension,
    DashInteraction,
    DashMultiSelect,
    DashSelect,
    DashToggle,
    DatasetValues,
    JSONScalar,
)


def dataset_values(*, alias: str, column: str) -> DatasetValues:
    """Reference distinct values from one pinned snapshot dataset."""
    return DatasetValues(alias=alias, column=column)


def select(
    name: str,
    *,
    label: str | None = None,
    options: Sequence[JSONScalar] | DatasetValues | None = None,
    value: JSONScalar = None,
) -> DashSelect:
    """Build a single-value control."""
    return DashSelect(name=name, label=label, options=list(options) if _is_sequence(options) else options, value=value)


def multi_select(
    name: str,
    *,
    label: str | None = None,
    options: Sequence[JSONScalar] | DatasetValues | None = None,
    value: Sequence[JSONScalar] = (),
) -> DashMultiSelect:
    """Build a multi-value control."""
    return DashMultiSelect(
        name=name,
        label=label,
        options=list(options) if _is_sequence(options) else options,
        value=list(value),
    )


def date_range(
    name: str,
    *,
    label: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> DashDateRange:
    """Build a date-range control."""
    return DashDateRange(name=name, label=label, start_date=start_date, end_date=end_date)


def toggle(name: str, *, label: str | None = None, value: bool = False) -> DashToggle:
    """Build a boolean control."""
    return DashToggle(name=name, label=label, value=value)


def interaction(*, handler: str, inputs: Sequence[str] = (), outputs: Sequence[str] = ()) -> DashInteraction:
    """Declare a plain-Python report interaction and its graph edges."""
    return DashInteraction(handler=handler, inputs=list(inputs), outputs=list(outputs))


def dashboard(
    *,
    controls: Sequence[DashControl] = (),
    interactions: Sequence[DashInteraction] = (),
    tables: dict[str, dict[str, object]] | None = None,
) -> DashExtension:
    """Build a pdl-dash/0.1 extension object."""
    return DashExtension(controls=list(controls), interactions=list(interactions), tables=tables or {})


def _is_sequence(value: object) -> TypeGuard[Sequence[JSONScalar]]:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, DatasetValues))
