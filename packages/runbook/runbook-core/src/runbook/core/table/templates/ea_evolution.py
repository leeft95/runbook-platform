"""EA monthly release snapshots, aggregated into quarter and annual rows."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from typing import Any

import pandas as pd

from ..builder import _default_numeric_formats
from ..models import (
    TableAction,
    TableColumnSizing,
    TableFormatSpec,
    TableRule,
    TableSizing,
    TableStyleFormat,
    TableStyleOptions,
    TableStylePlan,
    TableTarget,
    TargetScope,
    parse_python_format_string,
)
from .common import color_negative_red
from .table_with_link_monthly import _normalize_input_frame


def ea_evolution_table(
    df: pd.DataFrame,
    header: str = "EA Evolution",
    *,
    yoy: bool = False,
    as_of: str | pd.Timestamp | None = None,
    quarter_window: tuple[int, int] | None = (-2, 2),
    format_spec: TableFormatSpec | str | None = None,
    column_width: int = 85,
    index_width: int = 85,
    rules: Sequence[TableRule] = (),
) -> dict[str, dict[str, Any]]:
    """Compare EA releases, with one monthly series per release-date column.

    ``df`` has one dated row per month and one numeric column per release.
    A single release is sufficient. All supplied release columns are retained,
    ordered newest first and displayed as Oct-05; years are included when
    needed to distinguish releases. Units are preserved without conversion.

    Quarters and years are arithmetic means of available monthly observations.
    Rows are labelled 2026Q2, 2026Q3, etc., with 2026Y after that year's
    displayed quarters. Annual means use the full supplied year, including
    months outside the displayed quarter window. Missing values are not filled.
    Rows with no values in any release are omitted.

    ``yoy=True`` follows the EA report: quarters subtract the same quarter one
    year earlier from the newest release, shared across all release columns.
    Annual rows subtract the preceding year's mean within each release column;
    2027Y compares that column's 2027 and 2026 means. These are absolute
    differences in the input units, not percentages. A single release supports
    YoY when it contains the corresponding prior-year observations; missing
    baselines produce missing differences. ``ea_evolution_table_yoy`` is the
    named preset.

    ``quarter_window`` gives inclusive offsets from the ``as_of`` quarter;
    (-2, 2) shows two preceding quarters, the current quarter and two following
    quarters. None shows all supplied quarters. ``as_of=None`` uses today.
    Formatting, widths and rules work like the other period tables. Means
    default to two decimals; all columns are centered, rows alternate colours
    and negative values are red. A vertical border separates Date from the
    releases; a horizontal border precedes the final two displayed rows when
    there are more than two rows. Inputs are copied; no releases are fetched,
    stored or synthesized. Returns the named data/style/plots payload.
    """
    if not isinstance(df, pd.DataFrame):
        raise TypeError("df must be a pandas DataFrame")
    if not header.strip():
        raise ValueError("header must not be blank")
    if df.empty:
        raise ValueError("df must contain at least one month and release")
    if not all(isinstance(column, (str, date)) for column in df.columns):
        raise ValueError("release columns must be dates")
    releases = pd.DatetimeIndex([pd.Timestamp(column).tz_localize(None) for column in df.columns]).normalize()
    if releases.hasnans or not releases.is_unique:
        raise ValueError("release columns must contain unique, non-missing dates")
    frame = df.copy()
    frame.columns = releases.strftime("%Y-%m-%d")
    frame.index = pd.to_datetime(frame.index, errors="raise").tz_localize(None)
    frame = _normalize_input_frame(frame, columns_filter=None, fill_na=None).apply(pd.to_numeric, errors="raise")
    if not frame.index.to_period("M").is_unique:
        raise ValueError("df must contain at most one observation per calendar month")
    frame = frame.loc[:, sorted(frame.columns, reverse=True)]
    quarters = frame.groupby(frame.index.to_period("Q")).mean()
    annual = frame.groupby(frame.index.year).mean()
    if yoy:
        quarters = quarters.sub(quarters.iloc[:, 0].reindex(quarters.index - 4).set_axis(quarters.index), axis=0)
        annual = annual - annual.reindex(annual.index - 1).set_axis(annual.index)
    if quarter_window is not None:
        if (
            len(quarter_window) != 2
            or any(isinstance(value, bool) or not isinstance(value, int) for value in quarter_window)
            or quarter_window[0] > quarter_window[1]
        ):
            raise ValueError("quarter_window must be ordered integer offsets or None")
        current_date = pd.Timestamp(datetime.today() if as_of is None else as_of)
        if pd.isna(current_date):
            raise ValueError("as_of must be a valid date")
        current = current_date.tz_localize(None).to_period("Q")
        quarters = quarters.loc[
            (quarters.index >= current + quarter_window[0]) & (quarters.index <= current + quarter_window[1])
        ]
    rows = []
    for year in quarters.index.year.unique():
        year_quarters = quarters.loc[quarters.index.year == year].copy()
        year_quarters.index = year_quarters.index.astype(str)
        year_mean = annual.loc[[year]].rename(index={year: f"{year}Y"})
        rows.extend([year_quarters, year_mean])
    result = pd.concat(rows) if rows else quarters.iloc[:0].copy()
    result = result.dropna(how="all")
    result.index = pd.Index(result.index, dtype="object", name="Date")
    release_dates = pd.to_datetime(result.columns)
    labels = release_dates.strftime("%b-%d")
    result.columns = labels if labels.is_unique else release_dates.strftime("%b-%d-%Y")
    spec = parse_python_format_string(format_spec) if isinstance(format_spec, str) else format_spec
    style_rules = [
        TableRule(
            id="ea_date_divider",
            target=TableTarget(scope=TargetScope.columns, positions=[0]),
            action=TableAction(border_left="1px solid black"),
        )
    ]
    if len(result) > 2:
        style_rules.append(
            TableRule(
                id="ea_final_rows",
                target=TableTarget(scope=TargetScope.rows, positions=[len(result) - 2]),
                action=TableAction(border_top="1px solid black"),
            )
        )
    plan = TableStylePlan(
        format=TableStyleFormat(
            na_rep="-",
            columns={column: spec for column in result}
            if spec is not None
            else _default_numeric_formats(result, thousands=True),
        ),
        sizing=TableSizing(
            index_width_px=index_width,
            columns=[TableColumnSizing(label=column, width_px=column_width) for column in result],
        ),
        rules=[*style_rules, *color_negative_red(list(result), [(column, column) for column in result]), *rules],
        options=TableStyleOptions(max_rows=max(1, len(result))),
    )
    return {header: {"data": result, "style": plan.model_dump(mode="python", exclude_none=True), "plots": []}}


def ea_evolution_table_yoy(
    df: pd.DataFrame, header: str = "EA Evolution YoY", **options: Any
) -> dict[str, dict[str, Any]]:
    """Compare release YoY changes with EA's quarterly and annual baselines.

    Options and output match ``ea_evolution_table``. Use this for the EA report's
    supply/demand tables; use the level template for liquids/crude balances.
    Quarters share the newest release's prior-year baseline; years compare
    against the preceding year within each release column.
    """
    return ea_evolution_table(df, header, yoy=True, **options)
