"""DOE weekly report table templates."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
import pandas as pd

from ..builder import resolve_table_style
from ..models import TableColumnSizing, TableSizing, TableStyleFormat, TableStyleOptions, TableStylePlan

_DEFAULT_HISTORY_YEARS = (2018, 2019, 2021, 2023, 2024, 2025)


def _weekly_frame(data: pd.DataFrame, *, minimum_rows: int = 5) -> pd.DataFrame:
    if not isinstance(data, pd.DataFrame):
        raise TypeError("data must be a pandas DataFrame")
    if not isinstance(data.index, pd.DatetimeIndex):
        raise TypeError("data must have a DatetimeIndex")
    if data.index.has_duplicates:
        raise ValueError("data index must not contain duplicate dates")
    if len(data) < minimum_rows:
        raise ValueError(f"data must contain at least {minimum_rows} observations")
    frame = data.sort_index().copy()
    if frame.empty or len(frame.select_dtypes(include="number").columns) != len(frame.columns):
        raise ValueError("data must contain only numeric columns")
    return frame


def _same_week(frame: pd.DataFrame, year: int, week: int) -> pd.DataFrame:
    return frame.loc[(frame.index.year == year) & (frame.index.strftime("%W").astype(int) == week)]


def _doe_payload(
    frame: pd.DataFrame,
    header: str,
    *,
    formats: Mapping[str, str] | None = None,
    column_width: int = 120,
    index_width: int = 120,
) -> dict[str, dict[str, Any]]:
    if not isinstance(header, str) or not header.strip():
        raise ValueError("header must not be blank")
    numeric = frame.select_dtypes(include="number").columns
    column_formats = {str(column): "{:,.0f}" for column in numeric}
    column_formats.update(formats or {})
    plan = TableStylePlan(
        format=TableStyleFormat(na_rep="-", columns=column_formats),
        sizing=TableSizing(
            index_width_px=index_width,
            columns=[TableColumnSizing(label=str(column), width_px=column_width) for column in frame.columns],
        ),
        options=TableStyleOptions(max_rows=max(1, len(frame))),
    )
    resolve_table_style(frame, plan)
    return {header: {"data": frame, "style": plan.model_dump(mode="python", exclude_none=True), "plots": []}}


def doe_signal_table(
    summary: pd.DataFrame,
    header: str = "DOE inventory signals",
    *,
    label_column: str = "Stocks Change",
) -> dict[str, dict[str, Any]]:
    """Style the report's prepared Crude/PADD2-Cushing/Whisper signal rows."""
    if not isinstance(summary, pd.DataFrame):
        raise TypeError("summary must be a pandas DataFrame")
    frame = summary.copy()
    if label_column in frame.columns:
        frame = frame.set_index(label_column)
    elif isinstance(frame.index, pd.RangeIndex):
        raise ValueError(f"summary must contain {label_column!r} or use a named row index")
    return _doe_payload(
        frame,
        header,
        formats={
            "4w average change (%)": "{:.1%}",
            "4y z-score": "{:.2f}",
            "s-curve signal": "{:.2f}",
            "Position": "{:,.0f}",
            "Position chg": "{:,.0f}",
        },
        index_width=100,
    )


def doe_overview_table(
    data: pd.DataFrame,
    header: str = "Runs, Demand and Stocks (mb), average 4w level for Demand",
    *,
    demand_columns: Sequence[str] = ("Demand",),
    history_years: Sequence[int] = _DEFAULT_HISTORY_YEARS,
    history_label: str = "18-25",
    row_labels: Mapping[str, str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Build the cross-product DOE stocks, runs and demand summary."""
    frame = _weekly_frame(data)
    if unknown := set(demand_columns) - set(frame.columns):
        raise ValueError(f"Unknown demand columns: {sorted(unknown)}")
    if not history_years:
        raise ValueError("history_years must not be empty")

    latest_date = frame.index[-1]
    week = int(latest_date.strftime("%W"))
    prior = _same_week(frame, latest_date.year - 1, week)
    changes = frame.diff(4)
    history = changes.loc[changes.index.year.isin(history_years) & (changes.index.strftime("%W").astype(int) == week)]
    next_history = changes.shift(-4).loc[history.index]
    result = pd.DataFrame(
        {
            "Latest": frame.iloc[-1],
            "1 week change": frame.diff().iloc[-1],
            "4 week change": changes.iloc[-1],
            "4w chg Y-1": np.nan,
            f"4w chg {history_label}": history.mean(),
            f"Next 4w chg {history_label}": next_history.mean(),
            "YoY chg": frame.iloc[-1] - prior.iloc[-1] if len(prior) else np.nan,
        }
    )
    prior_changes = _same_week(changes, latest_date.year - 1, week)
    if len(prior_changes):
        result["4w chg Y-1"] = prior_changes.iloc[-1]

    rolling = frame.rolling(4).mean()
    for column in demand_columns:
        result.loc[column, "4 week change"] = rolling[column].iloc[-1]
        prior_level = _same_week(rolling[[column]], latest_date.year - 1, week)
        result.loc[column, "4w chg Y-1"] = prior_level[column].iloc[-1] if len(prior_level) else np.nan
        history_level = rolling.loc[
            rolling.index.year.isin(history_years) & (rolling.index.strftime("%W").astype(int) == week), column
        ]
        result.loc[column, f"4w chg {history_label}"] = history_level.mean()
        result.loc[column, f"Next 4w chg {history_label}"] = rolling[column].shift(-4).loc[history_level.index].mean()

    result["last_update"] = frame.apply(pd.Series.last_valid_index).dt.strftime("%Y-%m-%d")
    labels = dict(row_labels or {"Demand": "Demand (Outright)"})
    result.index = [labels.get(label, label) for label in result.index]
    result.index.name = "Total"
    return _doe_payload(result, header)


def doe_detail_table(
    data: pd.DataFrame,
    header: str = "DOE report detailed",
    *,
    history_years: Sequence[int] = _DEFAULT_HISTORY_YEARS,
    history_label: str = "18-25",
    consensus: Mapping[str, Any] | pd.Series | None = None,
    consensus_label: str = "Consensus Stocks chg (kbd)",
) -> dict[str, dict[str, Any]]:
    """Build the detailed DOE crude, mogas or distillate balance table.

    ``data`` contains weekly levels with a required ``Stocks`` column. A
    prepared consensus row can be appended by column name for the crude table.
    """
    frame = _weekly_frame(data)
    if "Stocks" not in frame:
        raise ValueError("data must contain a Stocks column")
    if not history_years:
        raise ValueError("history_years must not be empty")

    latest_date = frame.index[-1]
    week = int(latest_date.strftime("%W"))
    derived = frame.copy()
    derived["Change in stock (kbd)"] = frame["Stocks"].diff() / 7
    changes = derived.diff(4)
    prior_changes = _same_week(changes, latest_date.year - 1, week)
    history = changes.loc[changes.index.year.isin(history_years) & (changes.index.strftime("%W").astype(int) == week)]
    prior = _same_week(derived, latest_date.year - 1, week)
    one_week = frame.diff().iloc[-1]
    one_week["Change in stock (kbd)"] = one_week["Stocks"] / 7
    four_week = frame.diff(4).iloc[-1]
    four_week["Change in stock (kbd)"] = four_week["Stocks"] / 28
    result = pd.DataFrame(
        {
            "Latest": frame.iloc[-1],
            "4 week average": derived.rolling(4).mean().iloc[-1],
            "1 week change": one_week,
            "4 week change": four_week,
            "4w chg Y-1": prior_changes.iloc[-1] if len(prior_changes) else np.nan,
            f"4w chg {history_label}": history.mean(),
            f"Next 4w chg {history_label}": changes.shift(-4).loc[history.index].mean(),
            "YoY chg": derived.iloc[-1] - prior.iloc[-1] if len(prior) else np.nan,
        }
    )
    result = result.reindex([*frame.columns, "Change in stock (kbd)"])
    result.loc["Change in stock (kbd)", "Latest"] = np.nan
    result["last_update"] = frame.apply(pd.Series.last_valid_index).dt.strftime("%Y-%m-%d")
    result = result.rename(index={"Stocks": "Stocks (kb)"})
    if consensus is not None:
        if not consensus_label.strip():
            raise ValueError("consensus_label must not be blank")
        row = pd.Series(dict(consensus), name=consensus_label).reindex(result.columns)
        result = pd.concat([result, row.to_frame().T])
    result.index.name = header.removesuffix(" report detailed")
    return _doe_payload(result, header)


def doe_crude_table(data: pd.DataFrame, header: str = "DOE Crude report detailed", **options: Any):
    """Build the crude variant of :func:`doe_detail_table`."""
    return doe_detail_table(data, header, **options)


def doe_mogas_table(data: pd.DataFrame, header: str = "DOE Mogas report detailed", **options: Any):
    """Build the motor-gasoline variant of :func:`doe_detail_table`."""
    return doe_detail_table(data, header, **options)


def doe_distillates_table(data: pd.DataFrame, header: str = "DOE Disty report detailed", **options: Any):
    """Build the distillates variant of :func:`doe_detail_table`."""
    return doe_detail_table(data, header, **options)


__all__ = [
    "doe_crude_table",
    "doe_detail_table",
    "doe_distillates_table",
    "doe_mogas_table",
    "doe_overview_table",
    "doe_signal_table",
]
