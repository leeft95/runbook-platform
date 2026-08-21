from __future__ import annotations

from typing import Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from typing_extensions import Annotated

JSONScalar = str | int | float | bool | None
ControlName = Annotated[str, StringConstraints(pattern=r"^[a-zA-Z0-9_.-]+$", min_length=1)]


class DatasetValues(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["dataset_values"] = "dataset_values"
    alias: Annotated[str, StringConstraints(min_length=1)]
    column: Annotated[str, StringConstraints(min_length=1)]


ControlOptions = list[JSONScalar] | DatasetValues


class _ControlBase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: ControlName
    label: str | None = None


class DashSelect(_ControlBase):
    type: Literal["select"] = "select"
    options: ControlOptions | None = None
    value: JSONScalar = None


class DashMultiSelect(_ControlBase):
    type: Literal["multi_select"] = "multi_select"
    options: ControlOptions | None = None
    value: list[JSONScalar] = Field(default_factory=list)


class DashDateRange(_ControlBase):
    type: Literal["date_range"] = "date_range"
    start_date: str | None = None
    end_date: str | None = None


class DashToggle(_ControlBase):
    type: Literal["toggle"] = "toggle"
    value: bool = False


DashControl = Union[DashSelect, DashMultiSelect, DashDateRange, DashToggle]


class DashInteraction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    handler: Annotated[str, StringConstraints(pattern=r"^[a-zA-Z0-9_.-]+$", min_length=1)]
    inputs: list[ControlName] = Field(default_factory=list)
    outputs: list[Annotated[str, StringConstraints(pattern=r"^[a-zA-Z0-9_.-]+$", min_length=1)]] = Field(
        default_factory=list
    )


class DashExtension(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["pdl-dash/0.1"] = "pdl-dash/0.1"
    controls: list[DashControl] = Field(default_factory=list)
    interactions: list[DashInteraction] = Field(default_factory=list)
    tables: dict[str, dict[str, Any]] = Field(default_factory=dict)

    @classmethod
    def from_manifest(cls, raw: dict[str, Any]) -> "DashExtension":
        """Parse the generic manifest extension with discriminated controls."""
        controls = raw.get("controls", [])
        normalized: list[dict[str, Any]] = []
        for control in controls:
            if isinstance(control, BaseModel):
                normalized.append(control.model_dump(mode="json"))
            elif isinstance(control, dict):
                normalized.append(control)
            else:
                raise TypeError("dash controls must be objects")
        payload = dict(raw)
        payload["controls"] = normalized
        return cls.model_validate(payload)
