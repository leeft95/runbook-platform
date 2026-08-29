"""Deterministic table-style normalization, hashing, and HTML rendering."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from html import escape
from typing import Any, Callable, cast

import pandas as pd
from runbook.core.table.models import (
    ConditionOp,
    ResolvedTableStyle,
    RowRefMode,
    StyleInput,
    TableColumnRHS,
    TableCondition,
    TableFormatDate,
    TableFormatNumber,
    TableFormatPercent,
    TableFormatSpec,
    TableFormatString,
    TableLiteralRHS,
    TableRowRef,
    TableRowRHS,
    TableStylePlan,
    TableTarget,
    TableZScoreRHS,
    TargetScope,
)
from runbook.core.utils import canonical_json, sha256_hexdigest


def normalize_table_style(
    style: StyleInput | None,
    *,
    style_key: str | None = None,
    max_rows: int | None = None,
) -> TableStylePlan:
    """Validate and normalize style input into canonical table style model."""
    if style is None:
        plan = TableStylePlan()
    elif isinstance(style, TableStylePlan):
        plan = style
    elif isinstance(style, Mapping):
        plan = TableStylePlan.model_validate(style)
    elif hasattr(style, "model_dump"):
        model_payload = cast(Any, style).model_dump(mode="python")
        plan = TableStylePlan.model_validate(model_payload)
    else:
        raise TypeError(f"Unsupported table style input type: {type(style)!r}")

    if style_key is None and max_rows is None:
        return plan

    payload = plan.model_dump(mode="python", exclude_none=True)
    if style_key is not None:
        payload["style_key"] = style_key
    if max_rows is not None:
        payload.setdefault("options", {})
        payload["options"]["max_rows"] = max_rows
    return TableStylePlan.model_validate(payload)


def table_style_payload(
    style: StyleInput | None,
    *,
    style_key: str | None = None,
    max_rows: int | None = None,
) -> dict[str, Any]:
    """Return canonical style payload dictionary."""
    plan = normalize_table_style(style, style_key=style_key, max_rows=max_rows)
    return cast(dict[str, Any], plan.model_dump(mode="python", exclude_none=True))


def table_style_json(
    style: StyleInput | None,
    *,
    style_key: str | None = None,
    max_rows: int | None = None,
) -> str:
    """Return canonical style payload JSON string."""
    return canonical_json(table_style_payload(style, style_key=style_key, max_rows=max_rows))


def table_style_hash(
    style: StyleInput | None,
    *,
    style_key: str | None = None,
    max_rows: int | None = None,
) -> str:
    """Return deterministic style hash."""
    return sha256_hexdigest(table_style_json(style, style_key=style_key, max_rows=max_rows))


def _is_null(value: Any) -> bool:
    """Handle is null."""
    result = pd.isna(value)
    if isinstance(result, bool):
        return result
    return False


def _css_string(css: Mapping[str, str]) -> str:
    """Handle css string."""
    if not css:
        return ""
    return "; ".join(f"{key}: {value}" for key, value in sorted(css.items()))


def _ensure_supported_dataframe(df: pd.DataFrame) -> None:
    """Handle ensure supported dataframe."""
    if not isinstance(df, pd.DataFrame):
        raise TypeError(f"Expected pandas.DataFrame, got {type(df)!r}")
    if isinstance(df.index, pd.MultiIndex):
        raise ValueError("MultiIndex index is not supported for table styling in v1")
    if isinstance(df.columns, pd.MultiIndex):
        raise ValueError("MultiIndex columns are not supported for table styling in v1")


def _column_lookup(df: pd.DataFrame) -> dict[str, int]:
    """Handle column lookup."""
    lookup: dict[str, int] = {}
    for pos, col in enumerate(df.columns):
        key = str(col)
        if key in lookup:
            raise ValueError(f"Duplicate column labels after string normalization: {key!r}")
        lookup[key] = pos
    return lookup


def _resolve_row_ref_position(index: pd.Index, row_ref: TableRowRef) -> int:
    """Resolve row ref position."""
    if row_ref.mode == RowRefMode.position:
        pos = cast(int, row_ref.value)
        if pos < 0 or pos >= len(index):
            raise ValueError(f"row_ref.position out of range: {pos}")
        return pos

    matches = [i for i, idx_val in enumerate(index.tolist()) if idx_val == row_ref.value]
    if not matches and isinstance(row_ref.value, str):
        matches = [i for i, idx_val in enumerate(index.tolist()) if str(idx_val) == row_ref.value]
    if not matches:
        raise ValueError(f"row_ref label not found: {row_ref.value!r}")
    if len(matches) != 1:
        raise ValueError(f"row_ref label must resolve to exactly one row: {row_ref.value!r}")
    return matches[0]


def _resolve_target_row_positions(
    index: pd.Index,
    labels: Sequence[str] | None,
    positions: Sequence[int] | None,
) -> list[int]:
    """Resolve target row positions."""
    resolved_positions: list[int] = []
    if labels is not None:
        for label in labels:
            matches = [i for i, idx_val in enumerate(index.tolist()) if str(idx_val) == label]
            if not matches:
                raise ValueError(f"target row label not found: {label!r}")
            resolved_positions.extend(matches)

    if positions is not None:
        for position in positions:
            if position < 0 or position >= len(index):
                raise ValueError(f"target row position out of range: {position}")
            resolved_positions.append(position)

    return sorted(set(resolved_positions))


def _resolve_target(
    df: pd.DataFrame,
    target: TableTarget,
    col_lookup: Mapping[str, int],
) -> tuple[list[int], list[int]]:
    """Resolve target."""
    row_positions = list(range(len(df.index)))
    col_positions = list(range(len(df.columns)))

    if target.scope == TargetScope.all:
        return row_positions, col_positions

    if target.scope == TargetScope.columns:
        resolved_cols: list[int] = []
        if target.labels is not None:
            for label in target.labels:
                if label not in col_lookup:
                    raise ValueError(f"target column label not found: {label!r}")
                resolved_cols.append(col_lookup[label])
        if target.positions is not None:
            for position in target.positions:
                if position < 0 or position >= len(df.columns):
                    raise ValueError(f"target column position out of range: {position}")
                resolved_cols.append(position)
        return row_positions, sorted(set(resolved_cols))

    resolved_rows = _resolve_target_row_positions(df.index, target.labels, target.positions)
    return resolved_rows, col_positions


def _validate_rhs_shape(condition: TableCondition) -> None:
    """Validate rhs shape."""
    if condition.all_of is not None:
        for nested in condition.all_of:
            _validate_rhs_shape(nested)
        return

    if condition.any_of is not None:
        for nested in condition.any_of:
            _validate_rhs_shape(nested)
        return

    if condition.op == ConditionOp.between:
        assert isinstance(condition.rhs, TableLiteralRHS)
        if (
            not isinstance(condition.rhs.value, Sequence)
            or isinstance(condition.rhs.value, (str, bytes))
            or len(condition.rhs.value) != 2
        ):
            raise ValueError("condition.rhs.value must be a 2-item sequence when condition.op='between'")

    if condition.op == ConditionOp.in_:
        assert isinstance(condition.rhs, TableLiteralRHS)
        if not isinstance(condition.rhs.value, Sequence) or isinstance(condition.rhs.value, (str, bytes)):
            raise ValueError("condition.rhs.value must be a sequence when condition.op='in'")


def _evaluate_condition(
    *,
    lhs: Any,
    condition: TableCondition,
    df: pd.DataFrame,
    row_pos: int,
    col_pos: int,
    col_lookup: Mapping[str, int],
) -> bool:
    """Handle evaluate condition."""
    if condition.all_of is not None:
        return all(
            _evaluate_condition(
                lhs=lhs,
                condition=nested,
                df=df,
                row_pos=row_pos,
                col_pos=col_pos,
                col_lookup=col_lookup,
            )
            for nested in condition.all_of
        )

    if condition.any_of is not None:
        return any(
            _evaluate_condition(
                lhs=lhs,
                condition=nested,
                df=df,
                row_pos=row_pos,
                col_pos=col_pos,
                col_lookup=col_lookup,
            )
            for nested in condition.any_of
        )

    lhs_value = lhs
    if condition.lhs_column is not None:
        if condition.lhs_column not in col_lookup:
            raise ValueError(f"condition lhs column label not found: {condition.lhs_column!r}")
        lhs_value = df.iat[row_pos, col_lookup[condition.lhs_column]]

    if condition.op == ConditionOp.always:
        return True
    if condition.op == ConditionOp.isna:
        return _is_null(lhs_value)
    if condition.op == ConditionOp.notna:
        return not _is_null(lhs_value)

    assert condition.rhs is not None

    if condition.op in {ConditionOp.z_gt, ConditionOp.z_lt}:
        assert isinstance(condition.rhs, TableZScoreRHS)
        if condition.rhs.mean_column not in col_lookup:
            raise ValueError(f"rhs mean column label not found: {condition.rhs.mean_column!r}")
        if condition.rhs.std_column not in col_lookup:
            raise ValueError(f"rhs std column label not found: {condition.rhs.std_column!r}")

        mean_col_pos = col_lookup[condition.rhs.mean_column]
        std_col_pos = col_lookup[condition.rhs.std_column]
        mean_value = df.iat[row_pos, mean_col_pos]
        std_value = df.iat[row_pos, std_col_pos]

        if _is_null(lhs_value) or _is_null(mean_value) or _is_null(std_value):
            return False

        try:
            lhs_numeric = float(cast(Any, lhs_value))
            mean_numeric = float(cast(Any, mean_value))
            std_numeric = abs(float(cast(Any, std_value)))
        except Exception:
            return False

        threshold = float(condition.rhs.num_std) * std_numeric
        if condition.op == ConditionOp.z_gt:
            return bool(lhs_numeric > (mean_numeric + threshold))
        return bool(lhs_numeric < (mean_numeric - threshold))

    if isinstance(condition.rhs, TableLiteralRHS):
        rhs_value = condition.rhs.value
    elif isinstance(condition.rhs, TableColumnRHS):
        if condition.rhs.label not in col_lookup:
            raise ValueError(f"rhs column label not found: {condition.rhs.label!r}")
        rhs_col_pos = col_lookup[condition.rhs.label]
        rhs_value = df.iat[row_pos, rhs_col_pos]
    elif isinstance(condition.rhs, TableRowRHS):
        rhs_row_pos = _resolve_row_ref_position(df.index, condition.rhs.row_ref)
        rhs_value = df.iat[rhs_row_pos, col_pos]
    else:
        raise ValueError(f"Unsupported rhs kind for condition: {condition.rhs!r}")

    if _is_null(lhs_value) or _is_null(rhs_value):
        return False

    lhs_cmp = cast(Any, lhs_value)
    rhs_cmp = cast(Any, rhs_value)

    try:
        if condition.op == ConditionOp.eq:
            return bool(lhs_cmp == rhs_cmp)
        if condition.op == ConditionOp.ne:
            return bool(lhs_cmp != rhs_cmp)
        if condition.op == ConditionOp.gt:
            return bool(lhs_cmp > rhs_cmp)
        if condition.op == ConditionOp.gte:
            return bool(lhs_cmp >= rhs_cmp)
        if condition.op == ConditionOp.lt:
            return bool(lhs_cmp < rhs_cmp)
        if condition.op == ConditionOp.lte:
            return bool(lhs_cmp <= rhs_cmp)
        if condition.op == ConditionOp.between:
            assert isinstance(rhs_value, Sequence)
            lower = rhs_value[0]
            upper = rhs_value[1]
            if _is_null(lower) or _is_null(upper):
                return False
            lower_cmp = cast(Any, lower)
            upper_cmp = cast(Any, upper)
            return bool(lower_cmp <= lhs_cmp <= upper_cmp)
        if condition.op == ConditionOp.in_:
            assert isinstance(rhs_value, Sequence)
            return any((not _is_null(candidate)) and bool(lhs_value == candidate) for candidate in rhs_value)
    except Exception:
        return False

    raise ValueError(f"Unsupported condition op: {condition.op!r}")


@dataclass(frozen=True)
class _ResolvedStyleMaps:
    row_width_px: dict[int, int]
    column_width_px: dict[str, int]
    cell_css: dict[tuple[int, str], dict[str, str]]


def _resolve_style_maps_for_frames(
    visible_df: pd.DataFrame,
    style: TableStylePlan,
    *,
    style_df: pd.DataFrame,
) -> _ResolvedStyleMaps:
    """Resolve style maps for frames."""
    visible_col_lookup = _column_lookup(visible_df)
    style_col_lookup = _column_lookup(style_df)

    for fmt_col in style.format.columns:
        if fmt_col not in visible_col_lookup:
            raise ValueError(f"format column label not found: {fmt_col!r}")

    column_width_px: dict[str, int] = {}
    for item in style.sizing.columns:
        if item.label not in visible_col_lookup:
            raise ValueError(f"sizing column label not found: {item.label!r}")
        column_width_px[item.label] = item.width_px

    row_width_px: dict[int, int] = {}
    for item in style.sizing.rows:
        row_pos = _resolve_row_ref_position(visible_df.index, item.row_ref)
        row_width_px[row_pos] = item.width_px

    cell_css: dict[tuple[int, str], dict[str, str]] = {}
    for rule in style.rules:
        _validate_rhs_shape(rule.condition)
        row_positions, col_positions = _resolve_target(visible_df, rule.target, visible_col_lookup)
        css_props = rule.action.css_properties()
        for row_pos in row_positions:
            for col_pos in col_positions:
                visible_col_label = str(visible_df.columns[col_pos])
                style_col_pos = style_col_lookup.get(visible_col_label)
                if style_col_pos is None:
                    raise ValueError(f"style data column label not found: {visible_col_label!r}")
                lhs = style_df.iat[row_pos, style_col_pos]
                if _evaluate_condition(
                    lhs=lhs,
                    condition=rule.condition,
                    df=style_df,
                    row_pos=row_pos,
                    col_pos=style_col_pos,
                    col_lookup=style_col_lookup,
                ):
                    key = (row_pos, visible_col_label)
                    existing = cell_css.get(key, {})
                    merged = dict(existing)
                    merged.update(css_props)
                    cell_css[key] = merged

    return _ResolvedStyleMaps(
        row_width_px=row_width_px,
        column_width_px=column_width_px,
        cell_css=cell_css,
    )


def resolve_table_style(
    df: pd.DataFrame,
    style: StyleInput | None = None,
    *,
    style_df: pd.DataFrame | None = None,
    style_key: str | None = None,
    max_rows: int | None = None,
) -> ResolvedTableStyle:
    """Resolve table-style semantics against a dataframe for any renderer."""
    _ensure_supported_dataframe(df)
    plan = normalize_table_style(style, style_key=style_key, max_rows=max_rows)
    visible_df = df.head(plan.options.max_rows)
    visible_style_df = visible_df if style_df is None else style_df.loc[visible_df.index]

    _ensure_supported_dataframe(visible_df)
    _ensure_supported_dataframe(visible_style_df)
    if len(visible_style_df.index) != len(visible_df.index):
        raise ValueError("style_df must align to visible df rows")

    maps = _resolve_style_maps_for_frames(visible_df, plan, style_df=visible_style_df)
    visible_labels = tuple(str(col) for col in visible_df.columns)
    hidden_columns = frozenset(col for col in plan.options.hidden_columns if col in visible_df.columns)
    hidden_rows = frozenset(
        _resolve_row_ref_position(visible_df.index, row_ref) for row_ref in plan.options.hidden_rows
    )
    visible_columns = tuple(label for label in visible_labels if label not in hidden_columns)

    return ResolvedTableStyle(
        schema_version=plan.schema_version,
        style_key=plan.style_key,
        visible_columns=visible_columns,
        hidden_columns=hidden_columns,
        hidden_rows=hidden_rows,
        column_width_px=maps.column_width_px,
        row_width_px=maps.row_width_px,
        cell_css=maps.cell_css,
        formats=dict(plan.format.columns),
        na_rep=plan.format.na_rep,
        precision=plan.format.precision,
        thousands=plan.format.thousands,
        global_style=plan.options.global_style,
        show_index=plan.options.show_index,
        max_rows=plan.options.max_rows,
    )


def _format_date_value(value: Any, pattern: str) -> str:
    """Format date value."""
    if isinstance(value, (datetime, date)):
        if isinstance(value, date) and not isinstance(value, datetime):
            dt = datetime.combine(value, datetime.min.time())
        else:
            dt = cast(datetime, value)
    else:
        dt = pd.to_datetime(value, errors="coerce").to_pydatetime()
        if pd.isna(dt):
            return str(value)

    fmt = pattern
    fmt = fmt.replace("yyyy", "%Y")
    fmt = fmt.replace("MM", "%m")
    fmt = fmt.replace("dd", "%d")
    fmt = fmt.replace("HH", "%H")
    fmt = fmt.replace("mm", "%M")
    fmt = fmt.replace("ss", "%S")
    return dt.strftime(fmt)


def _formatter_from_spec(spec: TableFormatSpec) -> Callable[[Any], Any]:
    """Handle formatter from spec."""

    def _format(value: Any) -> Any:
        """Handle format."""
        if _is_null(value):
            return value

        if isinstance(spec, TableFormatNumber):
            try:
                num = float(value)
            except Exception:
                return str(value)
            if spec.thousands:
                return f"{num:,.{spec.digits}f}"
            return f"{num:.{spec.digits}f}"

        if isinstance(spec, TableFormatPercent):
            try:
                num = float(value)
            except Exception:
                return str(value)
            return f"{num * 100:.{spec.digits}f}%"

        if isinstance(spec, TableFormatDate):
            return _format_date_value(value, spec.pattern)

        if isinstance(spec, TableFormatString):
            return str(value)

        return str(value)

    return _format


def _deterministic_styler_uuid(df: pd.DataFrame, plan: TableStylePlan, table_class: str) -> str:
    """Handle deterministic styler uuid."""
    index_values = [None if _is_null(value) else value for value in df.index.tolist()]
    data_rows: list[list[Any]] = []
    for row in df.itertuples(index=False, name=None):
        data_rows.append([None if _is_null(value) else value for value in row])

    payload = {
        "schema_version": plan.schema_version,
        "style_key": plan.style_key,
        "table_class": table_class,
        "style": plan.model_dump(mode="python", exclude_none=True),
        "columns": [str(col) for col in df.columns],
        "index": index_values,
        "data": data_rows,
    }
    return sha256_hexdigest(canonical_json(payload))[:12]


def render_table_html(
    df: pd.DataFrame,
    style: StyleInput | None = None,
    *,
    style_df: pd.DataFrame | None = None,
    style_key: str | None = None,
    max_rows: int | None = None,
    table_class: str = "rb-table",
) -> str:
    """Render deterministic HTML table using the normalized style plan."""
    plan = normalize_table_style(style, style_key=style_key, max_rows=max_rows)
    resolved = resolve_table_style(
        df,
        plan,
        style_df=style_df,
    )
    visible_df = df.head(resolved.max_rows)
    visible_col_lookup = _column_lookup(visible_df)

    rows = len(visible_df.index)
    cols = len(visible_df.columns)
    global_style = resolved.global_style
    base_row_backgrounds = set(range(rows)) if global_style.one_bg_color else set(range(0, rows, 2))
    cell_css: list[list[dict[str, str]]] = [[{} for _ in range(cols)] for _ in range(rows)]

    for row_pos in base_row_backgrounds:
        for col_pos in range(cols):
            cell_css[row_pos][col_pos]["background-color"] = global_style.background_color

    for col_label, width in resolved.column_width_px.items():
        col_pos = visible_col_lookup[col_label]
        for row_pos in range(rows):
            cell_css[row_pos][col_pos]["width"] = f"{width}px"
            cell_css[row_pos][col_pos]["min-width"] = f"{width}px"

    for row_pos, width in resolved.row_width_px.items():
        for col_pos in range(cols):
            cell_css[row_pos][col_pos]["width"] = f"{width}px"
            cell_css[row_pos][col_pos]["min-width"] = f"{width}px"

    for (row_pos, col_label), resolved_css in resolved.cell_css.items():
        cell_css[row_pos][visible_col_lookup[col_label]].update(resolved_css)

    css_frame = pd.DataFrame(
        [[_css_string(cell_css[row_pos][col_pos]) for col_pos in range(cols)] for row_pos in range(rows)],
        index=visible_df.index,
        columns=visible_df.columns,
    )

    table_styles: list[dict[str, Any]] = [
        {
            "selector": "th",
            "props": [
                ("border-bottom", global_style.header_border_bottom),
                ("font-size", global_style.font_size),
                ("font-family", global_style.font_family),
                ("text-align", global_style.header_text_align),
            ],
        },
        {
            "selector": "",
            "props": [
                ("border", global_style.table_border),
                ("font-size", global_style.font_size),
                ("font-family", global_style.font_family),
                ("border-collapse", "collapse"),
            ],
        },
    ]

    for col_label, width in resolved.column_width_px.items():
        col_pos = visible_col_lookup[col_label]
        table_styles.append(
            {
                "selector": f".col{col_pos}",
                "props": [("width", f"{width}px"), ("min-width", f"{width}px")],
            }
        )

    for row_pos, width in resolved.row_width_px.items():
        table_styles.append(
            {
                "selector": f".row{row_pos}",
                "props": [("width", f"{width}px"), ("min-width", f"{width}px")],
            }
        )

    formatter_map: dict[str, Callable[[Any], Any]] = {
        col: _formatter_from_spec(spec) for col, spec in resolved.formats.items()
    }

    table_attrs = f'class="{escape(table_class)}" data-style-schema="{escape(resolved.schema_version)}"'

    styler = cast(Any, visible_df.style)
    styler = styler.set_uuid(_deterministic_styler_uuid(visible_df, plan, table_class))
    styler = styler.set_table_attributes(table_attrs)
    styler = styler.set_table_styles(cast(Any, table_styles), overwrite=False)
    styler = styler.apply(lambda _: css_frame, axis=None)
    styler = styler.format(
        formatter=cast(Any, formatter_map) if formatter_map else None,
        na_rep=resolved.na_rep,
        precision=resolved.precision,
        thousands=resolved.thousands,
    )

    if not resolved.show_index:
        styler = styler.hide(axis="index")

    hidden_columns = list(resolved.hidden_columns)
    if hidden_columns:
        styler = styler.hide(subset=hidden_columns, axis="columns")

    hidden_row_positions = list(resolved.hidden_rows)
    if hidden_row_positions:
        hidden_row_index = visible_df.index.take(hidden_row_positions)
        styler = styler.hide(subset=hidden_row_index, axis="index")

    return styler.to_html()


__all__ = [
    "normalize_table_style",
    "render_table_html",
    "resolve_table_style",
    "table_style_hash",
    "table_style_json",
    "table_style_payload",
]
