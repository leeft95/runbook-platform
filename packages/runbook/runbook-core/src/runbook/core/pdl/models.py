"""Pydantic models for the runbook PDL core manifest (`pdl-core/0.1`).

These models are the typed Python representation of the manifest-first JSON
contract used by Stage 3 (manifest build) and Stage 4 (render/publish). They
describe report structure and artifact references only; they do not contain any
execution, data access, or runtime orchestration logic.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator
from runbook.core.table.models import TableArtifactRef
from typing_extensions import Annotated

NonEmptyStr = Annotated[str, StringConstraints(min_length=1)]
BlockNameStr = Annotated[
    str,
    StringConstraints(pattern=r"^[a-zA-Z0-9_\-\.]+$", min_length=1),
]


class PDLSourceType(str, Enum):
    manual = "manual"
    default = "default"
    theme = "theme"


class PDLTextFormat(str, Enum):
    plain = "plain"
    markdown = "markdown"


class PDLPageType(str, Enum):
    grid = "grid"
    flex_grid = "flex_grid"
    custom = "custom"


class PDLColumnRole(str, Enum):
    """Renderer-neutral semantic role for a table column."""

    dimension = "dimension"
    measure = "measure"
    time = "time"
    identifier = "identifier"


class PDLAggregation(str, Enum):
    """Supported renderer-neutral aggregation intents."""

    sum = "sum"
    avg = "avg"
    min = "min"
    max = "max"
    count = "count"  # type: ignore[assignment]
    first = "first"
    last = "last"


class PDLNumberFormat(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["number"] = "number"
    decimals: int | None = Field(default=None, ge=0, le=12)


class PDLCurrencyFormat(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["currency"] = "currency"
    currency: NonEmptyStr
    decimals: int | None = Field(default=None, ge=0, le=12)


class PDLPercentFormat(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["percent"] = "percent"
    decimals: int | None = Field(default=None, ge=0, le=12)


class PDLDateFormat(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["date"] = "date"


class PDLDateTimeFormat(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["datetime"] = "datetime"


PDLColumnFormat = Union[
    PDLNumberFormat,
    PDLCurrencyFormat,
    PDLPercentFormat,
    PDLDateFormat,
    PDLDateTimeFormat,
]


class PDLColumn(BaseModel):
    """Optional semantic metadata for one physical table field."""

    model_config = ConfigDict(extra="forbid")

    field: NonEmptyStr
    label: NonEmptyStr | None = None
    role: PDLColumnRole | None = None
    aggregation: PDLAggregation | None = None
    format: PDLColumnFormat | None = Field(default=None, discriminator="kind")
    hidden: bool = False

    @model_validator(mode="after")
    def validate_aggregation_role(self) -> "PDLColumn":
        if self.aggregation is not None and self.role not in {None, PDLColumnRole.measure}:
            raise ValueError("aggregation is only valid for measure columns")
        return self


class PDLStyle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    css_ref: NonEmptyStr
    source_type: PDLSourceType
    source_key: NonEmptyStr


class PDLBlockBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    name: BlockNameStr
    title: str | None = None
    row: int = Field(ge=1)
    col: int = Field(ge=1)
    row_span: int = Field(default=1, ge=1)
    col_span: int = Field(default=1, ge=1)
    extensions: dict[str, dict[str, Any]] | None = None


class PDLTableBlock(PDLBlockBase, TableArtifactRef):
    type: Literal["table"] = "table"
    columns: list[PDLColumn] | None = None

    @field_validator("columns")
    @classmethod
    def validate_unique_columns(cls, value: list[PDLColumn] | None) -> list[PDLColumn] | None:
        if value is None:
            return None
        fields = [column.field for column in value]
        if len(fields) != len(set(fields)):
            raise ValueError("table columns must not contain duplicate fields")
        return value


class PDLPlotRefBlock(PDLBlockBase):
    type: Literal["plot_ref"] = "plot_ref"
    ref: NonEmptyStr


class PDLTextBlock(PDLBlockBase):
    type: Literal["text"] = "text"
    text: str
    format: PDLTextFormat | None = None


PDLBlock = Union[PDLTableBlock, PDLPlotRefBlock, PDLTextBlock]


class PDLPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_type: PDLPageType
    rows: int | None = Field(default=None, ge=1)
    columns: int | None = Field(default=None, ge=1, le=12)
    blocks: list[PDLBlock] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_blocks_fit_grid(self) -> "PDLPage":
        names = [block.name for block in self.blocks]
        if len(names) != len(set(names)):
            raise ValueError("page blocks must not contain duplicate names")
        if self.page_type in {PDLPageType.grid, PDLPageType.flex_grid}:
            if self.rows is None or self.columns is None:
                raise ValueError("rows and columns are required when page_type is 'grid' or 'flex_grid'")

            max_rows, max_cols = self.rows, self.columns

            for block in self.blocks:
                last_row = block.row + block.row_span - 1
                last_col = block.col + block.col_span - 1
                if last_row > max_rows or last_col > max_cols:
                    raise ValueError(
                        f"block '{block.name}' ({block.type}) at row={block.row}, col={block.col}, row_span={block.row_span}, col_span={block.col_span} exceeds grid bounds ({max_rows}x{max_cols})"
                    )

            return self

        if self.rows is not None or self.columns is not None:
            raise ValueError("rows and columns must be omitted when page_type is not 'grid' or 'flex_grid'")

        return self


class PDLArtifacts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plots: list[NonEmptyStr] | None = None
    tables: list[NonEmptyStr] | None = None
    files: list[NonEmptyStr] | None = None


class PDLManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["pdl-core/0.1"] = "pdl-core/0.1"
    title: NonEmptyStr
    snapshot_id: NonEmptyStr
    as_of: datetime
    style: PDLStyle | None = None
    page: PDLPage
    artifacts: PDLArtifacts | None = None
    # Immutable snapshot/runtime notices rendered outside the author grid.
    warnings: tuple[NonEmptyStr, ...] = ()
    # describes what extension this manifest can be used for,
    # e.g. plotly dash with a specific component/styling system.
    extensions: dict[str, dict[str, Any]] | None = None

    @field_validator("warnings", mode="before")
    @classmethod
    def normalize_warnings(cls, value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        return tuple(dict.fromkeys(str(item) for item in value))
