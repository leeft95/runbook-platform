"""Pydantic models for deterministic table-style schemas."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)
from typing_extensions import Annotated

TABLE_STYLE_SCHEMA_VERSION: Literal["table-style/0.2"] = "table-style/0.2"
TableStyleSchemaVersion = Literal["table-style/0.1", "table-style/0.2"]
NonEmptyRef = Annotated[str, StringConstraints(min_length=1)]


def validate_link_url(value: str) -> str:
    """Validate a link URL accepted by table and standalone link renderers."""
    if any(char.isspace() or ord(char) < 0x20 or ord(char) == 0x7F for char in value):
        raise ValueError(f"table URL contains whitespace or control characters: {value!r}")
    parsed = urlsplit(value)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"table URL must use an http or https scheme: {value!r}")
    return value


class TableLinkKind(str, Enum):
    report = "report"
    plot = "plot"
    url = "url"


class TableLinkDestination(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: TableLinkKind
    value: NonEmptyRef | None = Field(default=None, exclude_if=lambda value: value is None)
    value_field: NonEmptyRef | None = Field(default=None, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def validate_value(self) -> "TableLinkDestination":
        if (self.value is None) == (self.value_field is None):
            raise ValueError("link destination must set exactly one of 'value' or 'value_field'")
        return self


class TableLink(BaseModel):
    model_config = ConfigDict(extra="forbid")

    area: Literal["cells", "header", "index_header"]
    field: NonEmptyRef | None = Field(default=None, exclude_if=lambda value: value is None)
    destination: TableLinkDestination

    @model_validator(mode="after")
    def validate_area(self) -> "TableLink":
        if self.area in {"cells", "header"} and self.field is None:
            raise ValueError(f"link field is required for area='{self.area}'")
        if self.area == "index_header" and self.field is not None:
            raise ValueError("link field must be omitted for area='index_header'")
        if self.destination.value_field is not None and self.area != "cells":
            raise ValueError("dynamic link destinations are only valid for area='cells'")
        if self.area == "cells" and self.destination.kind == TableLinkKind.plot:
            raise ValueError("plot link destinations are not valid for area='cells'")
        return self


class TableArtifactRef(BaseModel):
    """Runtime-facing table artifact references used by PDL table blocks."""

    model_config = ConfigDict(extra="forbid")

    data_ref: NonEmptyRef
    style_ref: NonEmptyRef | None = None
    html_ref: NonEmptyRef | None = None
    style_key: NonEmptyRef | None = None
    links: list[TableLink] | None = Field(default=None, exclude_if=lambda value: not value)


class TargetScope(str, Enum):
    all = "all"
    columns = "columns"
    rows = "rows"


class ConditionOp(str, Enum):
    always = "always"
    eq = "eq"
    ne = "ne"
    gt = "gt"
    gte = "gte"
    lt = "lt"
    lte = "lte"
    between = "between"
    in_ = "in"
    isna = "isna"
    notna = "notna"
    z_gt = "z_gt"
    z_lt = "z_lt"


class RHSKind(str, Enum):
    literal = "literal"
    column = "column"
    row = "row"
    zscore = "zscore"


class RowRefMode(str, Enum):
    label = "label"
    position = "position"


class FormatKind(str, Enum):
    number = "number"
    percent = "percent"
    date = "date"
    string = "string"


class TableRowRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: RowRefMode
    value: Any

    @model_validator(mode="after")
    def validate_position(self) -> "TableRowRef":
        if self.mode == RowRefMode.position and not isinstance(self.value, int):
            raise ValueError("row_ref.value must be an integer when row_ref.mode='position'")
        return self


class TableLiteralRHS(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["literal"] = "literal"
    value: Any


class TableColumnRHS(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["column"] = "column"
    label: str


class TableRowRHS(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["row"] = "row"
    row_ref: TableRowRef


class TableZScoreRHS(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["zscore"] = "zscore"
    mean_column: str
    std_column: str
    num_std: float = Field(default=1.0, ge=0)


TableConditionRHS = TableLiteralRHS | TableColumnRHS | TableRowRHS | TableZScoreRHS


class TableTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: TargetScope = TargetScope.all
    labels: list[str] | None = None
    positions: list[int] | None = None

    @field_validator("positions")
    @classmethod
    def validate_positions_non_negative(cls, value: list[int] | None) -> list[int] | None:
        if value is None:
            return value
        if any(position < 0 for position in value):
            raise ValueError("target.positions must contain non-negative integers")
        return value

    @model_validator(mode="after")
    def validate_scope_references(self) -> "TableTarget":
        if self.scope == TargetScope.columns:
            has_labels = bool(self.labels)
            has_positions = bool(self.positions)
            if not (has_labels or has_positions):
                raise ValueError("target.labels or target.positions is required when target.scope is 'columns'")
            return self

        if self.scope == TargetScope.rows:
            has_labels = bool(self.labels)
            has_positions = bool(self.positions)
            if not (has_labels or has_positions):
                raise ValueError("target.labels or target.positions is required when target.scope is 'rows'")
            return self

        if self.positions:
            raise ValueError("target.positions is only supported when target.scope is 'columns' or 'rows'")
        return self


class TableCondition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: ConditionOp = ConditionOp.always
    rhs: TableConditionRHS | None = None
    lhs_column: str | None = None
    all_of: list["TableCondition"] | None = None
    any_of: list["TableCondition"] | None = None

    @model_validator(mode="after")
    def validate_rhs(self) -> "TableCondition":
        has_all_of = bool(self.all_of)
        has_any_of = bool(self.any_of)
        if has_all_of and has_any_of:
            raise ValueError("condition.all_of and condition.any_of are mutually exclusive")

        if has_all_of or has_any_of:
            if self.op != ConditionOp.always:
                raise ValueError("condition.op must be 'always' when using condition.all_of or condition.any_of")
            if self.rhs is not None:
                raise ValueError("condition.rhs must be omitted when using condition.all_of or condition.any_of")
            return self

        rhs_optional_ops = {ConditionOp.always, ConditionOp.isna, ConditionOp.notna}
        rhs_literal_only_ops = {ConditionOp.between, ConditionOp.in_}
        rhs_zscore_only_ops = {ConditionOp.z_gt, ConditionOp.z_lt}

        if self.op in rhs_optional_ops:
            if self.rhs is not None:
                raise ValueError(f"condition.rhs must be omitted when condition.op='{self.op.value}'")
            return self

        if self.rhs is None:
            raise ValueError(f"condition.rhs is required when condition.op='{self.op.value}'")

        if self.op in rhs_zscore_only_ops:
            if not isinstance(self.rhs, TableZScoreRHS):
                raise ValueError(f"condition.rhs.kind='zscore' is required when condition.op='{self.op.value}'")
            return self

        if self.op in rhs_literal_only_ops and not isinstance(self.rhs, TableLiteralRHS):
            raise ValueError(f"condition.rhs.kind='literal' is required when condition.op='{self.op.value}'")

        if isinstance(self.rhs, TableZScoreRHS):
            raise ValueError(f"condition.op='{self.op.value}' does not support condition.rhs.kind='zscore'")

        return self


class TableAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    background_color: str | None = None
    text_color: str | None = None
    font_weight: str | None = None
    font_style: str | None = None
    text_align: str | None = None
    bottom_border: bool | None = None
    border_top: str | None = None
    border_right: str | None = None
    border_bottom: str | None = None
    border_left: str | None = None

    @model_validator(mode="after")
    def validate_non_empty(self) -> "TableAction":
        if not any(
            [
                self.background_color is not None,
                self.text_color is not None,
                self.font_weight is not None,
                self.font_style is not None,
                self.text_align is not None,
                self.bottom_border is not None,
                self.border_top is not None,
                self.border_right is not None,
                self.border_bottom is not None,
                self.border_left is not None,
            ]
        ):
            raise ValueError("action must set at least one style property")
        return self

    def css_properties(self) -> dict[str, str]:
        """Handle css properties."""
        css: dict[str, str] = {}
        if self.background_color is not None:
            css["background-color"] = self.background_color
        if self.text_color is not None:
            css["color"] = self.text_color
        if self.font_weight is not None:
            css["font-weight"] = self.font_weight
        if self.font_style is not None:
            css["font-style"] = self.font_style
        if self.text_align is not None:
            css["text-align"] = self.text_align
        if self.border_top is not None:
            css["border-top"] = self.border_top
        if self.border_right is not None:
            css["border-right"] = self.border_right
        if self.border_bottom is not None:
            css["border-bottom"] = self.border_bottom
        elif self.bottom_border:
            css["border-bottom"] = "1px solid #000000"
        if self.border_left is not None:
            css["border-left"] = self.border_left
        return css


class TableRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    target: TableTarget
    condition: TableCondition = Field(default_factory=TableCondition)
    action: TableAction


class TableFormatNumber(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["number"] = "number"
    digits: int = Field(default=2, ge=0)
    thousands: bool = False


class TableFormatPercent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["percent"] = "percent"
    digits: int = Field(default=2, ge=0)


class TableFormatDate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["date"] = "date"
    pattern: str


class TableFormatString(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["string"] = "string"


TableFormatSpec = TableFormatNumber | TableFormatPercent | TableFormatDate | TableFormatString


_PERCENT_FMT_RE = re.compile(r"^(?P<thousands>,)?(?:\.(?P<digits>\d+))?%$")
_NUMBER_FMT_RE = re.compile(r"^(?P<thousands>,)?(?:\.(?P<digits>\d+))?(?P<kind>[fFgGd])?$")


def parse_python_format_string(format_spec: str) -> TableFormatSpec:
    """Parse a supported python format string into canonical format spec."""
    if format_spec == "{}":
        return TableFormatString()

    if not (format_spec.startswith("{:") and format_spec.endswith("}")):
        raise ValueError(f"Unsupported python format string: {format_spec!r}")

    inner = format_spec[2:-1]

    percent_match = _PERCENT_FMT_RE.fullmatch(inner)
    if percent_match is not None:
        digits = int(percent_match.group("digits") or 2)
        return TableFormatPercent(digits=digits)

    number_match = _NUMBER_FMT_RE.fullmatch(inner)
    if number_match is not None:
        fmt_kind = number_match.group("kind")
        digits_raw = number_match.group("digits")
        thousands = number_match.group("thousands") == ","
        if digits_raw is not None:
            digits = int(digits_raw)
        elif fmt_kind == "d":
            digits = 0
        else:
            digits = 2
        return TableFormatNumber(digits=digits, thousands=thousands)

    raise ValueError(f"Unsupported python format string: {format_spec!r}")


class TableStyleFormat(BaseModel):
    model_config = ConfigDict(extra="forbid")

    na_rep: str | None = None
    precision: int | None = Field(default=None, ge=0)
    thousands: str | None = None
    columns: dict[str, TableFormatSpec] = Field(default_factory=dict)

    @field_validator("columns", mode="before")
    @classmethod
    def normalize_columns(cls, value: Any) -> Any:
        if value is None:
            return {}
        if not isinstance(value, Mapping):
            raise TypeError("format.columns must be a mapping")

        out: dict[str, Any] = {}
        for col_name, raw_spec in value.items():
            if not isinstance(col_name, str) or not col_name:
                raise ValueError("format.columns keys must be non-empty strings")
            if isinstance(raw_spec, str):
                out[col_name] = parse_python_format_string(raw_spec)
            else:
                out[col_name] = raw_spec
        return out


class TableColumnSizing(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    width_px: int = Field(gt=0)


class TableRowSizing(BaseModel):
    model_config = ConfigDict(extra="forbid")

    row_ref: TableRowRef
    width_px: int = Field(gt=0)


class TableSizing(BaseModel):
    model_config = ConfigDict(extra="forbid")

    columns: list[TableColumnSizing] = Field(default_factory=list)
    rows: list[TableRowSizing] = Field(default_factory=list)


class TableGlobalStyle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    background_color: str = "lightblue"
    one_bg_color: bool = False
    header_border_bottom: str = "1px solid black"
    table_border: str = "2px solid black"
    font_size: str = "11pt"
    font_family: str = "Calibri"
    header_text_align: str = "center"


class TableStyleOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_rows: int = Field(default=100, ge=1)
    global_style: TableGlobalStyle = Field(default_factory=TableGlobalStyle)
    show_index: bool = True
    hidden_columns: list[str] = Field(default_factory=list)
    hidden_rows: list[TableRowRef] = Field(default_factory=list)


class TableStylePlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: TableStyleSchemaVersion = TABLE_STYLE_SCHEMA_VERSION
    style_key: str | None = None
    format: TableStyleFormat = Field(default_factory=TableStyleFormat)
    sizing: TableSizing = Field(default_factory=TableSizing)
    rules: list[TableRule] = Field(default_factory=list)
    options: TableStyleOptions = Field(default_factory=TableStyleOptions)
    links: list[TableLink] | None = Field(default=None, exclude_if=lambda value: not value)

    @model_validator(mode="after")
    def validate_links_version(self) -> "TableStylePlan":
        if self.schema_version == "table-style/0.1" and self.links:
            raise ValueError("table-style/0.1 does not support table links")
        return self


TableCondition.model_rebuild()


@dataclass(frozen=True)
class ResolvedTableStyle:
    """Renderer-neutral table semantics resolved against a concrete dataframe."""

    schema_version: TableStyleSchemaVersion
    style_key: str | None
    visible_columns: tuple[str, ...]
    hidden_columns: frozenset[str]
    hidden_rows: frozenset[int]
    column_width_px: dict[str, int]
    row_width_px: dict[int, int]
    cell_css: dict[tuple[int, str], dict[str, str]]
    formats: dict[str, TableFormatSpec]
    na_rep: str | None
    precision: int | None
    thousands: str | None
    global_style: TableGlobalStyle
    show_index: bool
    max_rows: int
    links: tuple[TableLink, ...]
    cell_links: dict[tuple[int, str], TableLinkDestination]
    header_links: dict[str, TableLinkDestination]
    index_header_link: TableLinkDestination | None

    @property
    def format(self) -> TableStyleFormat:
        """Return the resolved format definition as a table-style model."""
        return TableStyleFormat(
            na_rep=self.na_rep,
            precision=self.precision,
            thousands=self.thousands,
            columns=dict(self.formats),
        )


StyleInput = TableStylePlan | Mapping[str, Any]


__all__ = [
    "TABLE_STYLE_SCHEMA_VERSION",
    "TableStyleSchemaVersion",
    "ConditionOp",
    "FormatKind",
    "RHSKind",
    "RowRefMode",
    "StyleInput",
    "TableArtifactRef",
    "TableLink",
    "TableLinkDestination",
    "TableLinkKind",
    "TableAction",
    "TableColumnRHS",
    "TableColumnSizing",
    "TableCondition",
    "TableConditionRHS",
    "TableFormatDate",
    "TableFormatNumber",
    "TableFormatPercent",
    "TableFormatSpec",
    "TableFormatString",
    "TableGlobalStyle",
    "TableLiteralRHS",
    "TableRowRef",
    "TableRowRHS",
    "TableRowSizing",
    "TableRule",
    "TableSizing",
    "TableStyleFormat",
    "TableStyleOptions",
    "TableStylePlan",
    "ResolvedTableStyle",
    "TableTarget",
    "TableZScoreRHS",
    "TargetScope",
    "parse_python_format_string",
]
