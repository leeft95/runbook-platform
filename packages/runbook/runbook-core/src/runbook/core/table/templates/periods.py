"""Calendar balance tables and same-period, previous-year differences.

Each template takes dated observations, averages numeric columns directly and
returns the ordinary named data/style/plots payload. No totals, missing periods
or companion plots are added. See ``monthly_table`` for shared options.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal

import pandas as pd

from ..models import (
    TableColumnSizing,
    TableFormatSpec,
    TableGlobalStyle,
    TableRule,
    TableSizing,
    TableStyleFormat,
    TableStyleOptions,
    TableStylePlan,
    parse_python_format_string,
)
from .common import color_negative_red
from .table_with_link_monthly import _normalize_input_frame


def monthly_table(df: pd.DataFrame, header: str = "Monthly", **options: Any) -> dict[str, dict[str, Any]]:
    """Average observations by calendar month, displaying labels such as Apr26.

    Shared options: ``format_spec`` defaults to
    ``'{:,.0f}'``; ``column_formats`` overrides individual series, e.g.
    ``{'NATL_GS': '{:.2f}'}``. ``column_width``/``index_width`` default to
    85/85 pixels, and ``rules`` appends shared style overrides.

    Dates are parsed, stripped of timezone while preserving local clock time,
    validated as unique/non-missing, and sorted on a copy. Only numeric columns
    are used; their order and names are retained. Means skip missing values
    and include partial periods. There is no filling or equal-month weighting.
    Date selection belongs to the caller; all supplied observations are used.
    YoY variants subtract the matching period one calendar year earlier.
    Missing comparisons stay missing, displayed as
    a dash. Values remain numeric, all columns are centered and negatives red.
    Annual tables use a solid blue background; other tables alternate rows.
    """
    return period_table(df, "monthly", header, **options)


def monthly_table_yoy(df: pd.DataFrame, header: str = "Monthly YoY", **options: Any) -> dict[str, dict[str, Any]]:
    """Subtract the same month's mean one year earlier; options match monthly_table."""
    return period_table(df, "monthly", header, yoy=True, **options)


def quarterly_table(df: pd.DataFrame, header: str = "Quarterly", **options: Any) -> dict[str, dict[str, Any]]:
    """Average observations by calendar quarter, labelled Q1 2026, Q2 2026, etc.

    Quarters run Jan–Mar, Apr–Jun, Jul–Sep and Oct–Dec. Shared options and
    missing-data behavior match ``monthly_table``.
    """
    return period_table(df, "quarterly", header, **options)


def quarterly_table_yoy(df: pd.DataFrame, header: str = "Quarterly YoY", **options: Any) -> dict[str, dict[str, Any]]:
    """Subtract the same quarter's mean one year earlier; options match monthly_table."""
    return period_table(df, "quarterly", header, yoy=True, **options)


def seasonal_table(df: pd.DataFrame, header: str = "Seasonal", **options: Any) -> dict[str, dict[str, Any]]:
    """Average Apr–Oct summers and Nov–Mar winters, labelled by their start year.

    Sum19 covers April–October 2019; Win19 covers November 2019–March 2020.
    Shared options and missing-data behavior match ``monthly_table``.
    """
    return period_table(df, "seasonal", header, **options)


def seasonal_table_yoy(df: pd.DataFrame, header: str = "Seasonal YoY", **options: Any) -> dict[str, dict[str, Any]]:
    """Subtract the matching summer/winter one year earlier; options match monthly_table."""
    return period_table(df, "seasonal", header, yoy=True, **options)


def summer_table(df: pd.DataFrame, header: str = "Summer", **options: Any) -> dict[str, dict[str, Any]]:
    """Show only Apr–Oct means from seasonal_table, with the same shared options."""
    return period_table(df, "summer", header, **options)


def summer_table_yoy(df: pd.DataFrame, header: str = "Summer YoY", **options: Any) -> dict[str, dict[str, Any]]:
    """Subtract the previous summer's mean; options match monthly_table."""
    return period_table(df, "summer", header, yoy=True, **options)


def winter_table(df: pd.DataFrame, header: str = "Winter", **options: Any) -> dict[str, dict[str, Any]]:
    """Show only Nov–Mar means from seasonal_table, named for the November year."""
    return period_table(df, "winter", header, **options)


def winter_table_yoy(df: pd.DataFrame, header: str = "Winter YoY", **options: Any) -> dict[str, dict[str, Any]]:
    """Subtract the previous winter's mean; options match monthly_table."""
    return period_table(df, "winter", header, yoy=True, **options)


def annual_table(df: pd.DataFrame, header: str = "Annual", **options: Any) -> dict[str, dict[str, Any]]:
    """Average supplied observations by calendar year.

    Shared options and missing-data behavior match ``monthly_table``.
    """
    return period_table(df, "annual", header, **options)


def annual_table_yoy(df: pd.DataFrame, header: str = "Annual YoY", **options: Any) -> dict[str, dict[str, Any]]:
    """Subtract the previous calendar year's mean; options match monthly_table."""
    return period_table(df, "annual", header, yoy=True, **options)


def period_table(
    df: pd.DataFrame,
    period: Literal["monthly", "quarterly", "seasonal", "summer", "winter", "annual"] = "monthly",
    header: str | None = None,
    *,
    yoy: bool = False,
    format_spec: TableFormatSpec | str = "{:,.0f}",
    column_formats: Mapping[str, TableFormatSpec | str] | None = None,
    column_width: int = 85,
    index_width: int = 85,
    rules: Sequence[TableRule] = (),
) -> dict[str, dict[str, Any]]:
    """Build any calendar balance table, optionally as absolute YoY differences.

    ``period`` selects monthly, quarterly, seasonal, summer, winter or annual.
    ``yoy=True`` compares the same period one year earlier, not the previous
    available row. Date selection belongs to the caller; this builder uses
    all supplied observations.
    The twelve named templates are presets of this builder. Shared options,
    input normalization and styling are documented in ``monthly_table``.
    """
    if period not in {"monthly", "quarterly", "seasonal", "summer", "winter", "annual"}:
        raise ValueError(f"Unsupported period: {period!r}")
    if header is None:
        header = period.capitalize() + (" YoY" if yoy else "")
    if not isinstance(df, pd.DataFrame):
        raise TypeError("df must be a pandas DataFrame")
    if not header.strip():
        raise ValueError("header must not be blank")
    frame = df.copy()
    frame.index = pd.to_datetime(frame.index, errors="raise").tz_localize(None)
    frame = _normalize_input_frame(frame, columns_filter=None, fill_na=None).select_dtypes(include="number")
    if not len(frame.columns):
        raise ValueError("df must contain numeric columns")
    if period in {"seasonal", "summer", "winter"}:
        dates = frame.index
        starts = pd.DatetimeIndex(
            pd.to_datetime(
                {
                    "year": dates.year - (dates.month <= 3).astype(int),
                    "month": [4 if 4 <= month <= 10 else 11 for month in dates.month],
                    "day": 1,
                }
            )
        )
        means = frame.groupby(starts).mean()
        previous = means.index - pd.DateOffset(years=1)
        period_dates = means.index
    else:
        frequency, lag = {"monthly": ("M", 12), "quarterly": ("Q", 4), "annual": ("Y", 1)}[period]
        means = frame.groupby(frame.index.to_period(frequency)).mean()
        previous = means.index - lag
        period_dates = means.index.to_timestamp()
    result = means - means.reindex(previous).set_axis(means.index) if yoy else means
    if period in {"summer", "winter"}:
        keep = period_dates.month == (4 if period == "summer" else 11)
        result = result.loc[keep].copy()
        period_dates = period_dates[keep]
    if period == "monthly":
        result.index = pd.Index(period_dates.strftime("%b%y"), name="Month")
    elif period == "quarterly":
        result.index = pd.Index([f"Q{date.quarter} {date.year}" for date in period_dates], name="Quarter")
    elif period == "annual":
        result.index = pd.Index(period_dates.year, name="Year")
    else:
        result.index = pd.Index(
            [f"{'Sum' if date.month == 4 else 'Win'}{date:%y}" for date in period_dates], name="Season"
        )

    if unknown := set(column_formats or {}) - set(result.columns):
        raise ValueError(f"Unknown column_formats columns: {sorted(unknown)}")
    formats = {column: format_spec for column in result}
    formats.update(column_formats or {})
    plan = TableStylePlan(
        format=TableStyleFormat(
            na_rep="-",
            columns={
                col: parse_python_format_string(spec) if isinstance(spec, str) else spec
                for col, spec in formats.items()
            },
        ),
        sizing=TableSizing(
            index_width_px=index_width,
            columns=[TableColumnSizing(label=column, width_px=column_width) for column in result],
        ),
        rules=[*color_negative_red(list(result), [(column, column) for column in result]), *rules],
        options=TableStyleOptions(
            max_rows=max(1, len(result)), global_style=TableGlobalStyle(one_bg_color=period == "annual")
        ),
    )
    return {header: {"data": result, "style": plan.model_dump(mode="python", exclude_none=True), "plots": []}}
