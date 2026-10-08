"""Named report table presets built from the shared table models and builders.

Every function returns ``{header: {"data": frame, "style": plan, "plots": plots}}``.
Keyword options override preset defaults and are validated by the underlying
builder. Inputs belong to the caller and are never modified.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Hashable

import pandas as pd

from ...timeseries.cot import cot_position_changes, cot_position_divergence, cot_summary
from ..builder import resolve_table_style
from ..models import TableStylePlan
from .cot import cot_table
from .table_with_link import general_table_with_link
from .table_with_link_monthly import table_with_linked_plots_monthly


def cot_observations_table(
    observations: Mapping[str, pd.DataFrame],
    header: str = "COT",
    *,
    summary_options: Mapping[str, Any] | None = None,
    asset_options: Mapping[str, Mapping[str, Any]] | None = None,
    **style_options: Any,
) -> dict[str, dict[str, Any]]:
    """Calculate and style named Long/Short/OI/price observations.

    ``summary_options`` forwards shared options to ``cot_summary``;
    ``asset_options`` overrides them per asset, for example a MiFID
    ``change_window=208`` or a different contract value.
    Remaining options are passed to ``cot_table``.
    """
    if not observations:
        raise ValueError("observations must contain at least one named asset")
    if unknown := set(asset_options or {}) - set(observations):
        raise ValueError(f"Unknown assets in asset_options: {sorted(unknown)}")
    summary = pd.concat(
        [
            cot_summary(frame, name, **{**(summary_options or {}), **(asset_options or {}).get(name, {})})
            for name, frame in observations.items()
        ],
        ignore_index=True,
    )
    return cot_table(summary, header, **style_options)


def cot_position_changes_table(
    summary: pd.DataFrame, header: str = "COT", *, threshold: float = 1.5, **options: Any
) -> dict[str, dict[str, Any]]:
    """Style the COT rows selected by weekly or four-week position scores."""
    return cot_table(cot_position_changes(summary, threshold=threshold), header, **options)


def cot_position_divergence_table(
    summary: pd.DataFrame, header: str = "COT", **options: Any
) -> dict[str, dict[str, Any]]:
    """Style COT rows whose weekly price and position changes diverge."""
    return cot_table(cot_position_divergence(summary), header, **options)


def daily_prices_table(data: pd.DataFrame, header: str = "Daily prices", **options: Any) -> dict[str, dict[str, Any]]:
    """Show five price rows, an MA summary, and linked column/aggregate plots.

    Pass ``chart_columns`` for MA overlays, comparison frames or seasonal plots;
    other options are forwarded to ``general_table_with_link``.
    """
    return general_table_with_link(
        data,
        header,
        **{"rows": 5, "title_column_width": 165, "column_plot_links": True, "all_plots_link": True, **options},
    )


def inventory_summary_table(data: pd.DataFrame, header: str = "Inventory", **options: Any) -> dict[str, dict[str, Any]]:
    """Show 20-observation stock changes, months, quarters, QTD and Y-1/5Y.

    Defaults to seasonal highlighting. ``aggregation_columns`` can select
    averages for flow series; ``exclude_years`` selects history exclusions.
    Options are forwarded to ``table_with_linked_plots_monthly``.
    """
    return table_with_linked_plots_monthly(
        data,
        header,
        **{
            "aggregation_type": "diff",
            "windows": (20,),
            "history_months": 3,
            "history_quarters": 2,
            "include_qtd": True,
            "comparison_years": 5,
            "highlighting_rules": {"seasonal": 5},
            "row_plot_links": True,
            "all_plots_link": True,
            **options,
        },
    )


def flow_quarterly_table(
    data: pd.DataFrame, header: str = "Flow averages", *, benchmark_quarter: str, **options: Any
) -> dict[str, dict[str, Any]]:
    """Compare 10/20-observation flow averages with a supplied quarter.

    Includes quarterly history, QTD, 65-observation highlights and plot links.
    Options are forwarded to ``table_with_linked_plots_monthly``.
    """
    return table_with_linked_plots_monthly(
        data,
        header,
        benchmark_quarter=benchmark_quarter,
        **{
            "aggregation_type": "mean",
            "history_quarters": 2,
            "include_qtd": True,
            "highlighting_rules": {"window": 65},
            "row_plot_links": True,
            "all_plots_link": True,
            **options,
        },
    )


def flow_monthly_table(
    data: pd.DataFrame, header: str = "Flow totals", *, benchmark_month: str | pd.Timestamp, **options: Any
) -> dict[str, dict[str, Any]]:
    """Compare 5/10-observation flow sums with a supplied month, with row links.

    Options are forwarded to ``table_with_linked_plots_monthly``.
    """
    return table_with_linked_plots_monthly(
        data,
        header,
        benchmark_month=benchmark_month,
        **{"aggregation_type": "sum", "windows": (5, 10), "row_plot_links": True, **options},
    )


def monthly_consensus_table(
    data: pd.DataFrame, header: str = "Monthly consensus", **options: Any
) -> dict[str, dict[str, Any]]:
    """Show monthly-input changes, quarters, QTD and Y-1/5Y comparisons.

    Uses unsmoothed seasonal plots. An optional ``_last_update`` input column
    remains hidden. Options are forwarded to ``table_with_linked_plots_monthly``.
    """
    return table_with_linked_plots_monthly(
        data,
        header,
        **{
            "input_frequency": "M",
            "windows": (1,),
            "aggregation_type": "diff",
            "moving_average_window": None,
            "comparison_years": 5,
            "history_months": 3,
            "history_quarters": 2,
            "include_qtd": True,
            "row_plot_links": True,
            "all_plots_link": True,
            **options,
        },
    )


def mtd_inventory_table(data: pd.DataFrame, header: str = "MTD stocks", **options: Any) -> dict[str, dict[str, Any]]:
    """Compare 5/20-observation stock averages with the prior month-end.

    Includes seasonal highlighting and row plot links. Pass ``as_of`` to pin
    the observation date; options go to ``table_with_linked_plots_monthly``.
    """
    return table_with_linked_plots_monthly(
        data,
        header,
        **{
            "aggregation_type": "diff",
            "windows": (5, 20),
            "mtd": True,
            "highlighting_rules": {"seasonal": 5},
            "row_plot_links": True,
            **options,
        },
    )


def grouped_metrics_table(
    data: pd.DataFrame,
    header: str = "Grouped metrics",
    *,
    percentage_rows: Sequence[int] = (),
    bar_columns: Sequence[Hashable] = (),
    digits: int = 2,
    percentage_digits: int = 1,
    column_width: int = 145,
    index_width: int = 100,
    bar_min: float = -1,
    bar_max: float = 1,
) -> dict[str, dict[str, Any]]:
    """Style grouped axes with numeric/percentage rows and signed data bars.

    Supply the desired pandas Index/MultiIndex on ``data``. Percentage rows
    are zero-based positions; bar columns are actual labels (including tuples
    for MultiIndex columns). Values remain numeric and columns are centered.
    """
    if not isinstance(data, pd.DataFrame):
        raise TypeError("data must be a pandas DataFrame")
    if not header.strip():
        raise ValueError("header must not be blank")
    plan = TableStylePlan.model_validate(
        {
            "format": {
                "columns": {str(col): {"kind": "number", "digits": digits} for col in data.columns},
                "rows": [
                    {
                        "row_ref": {"mode": "position", "value": row},
                        "spec": {"kind": "percent", "digits": percentage_digits},
                    }
                    for row in percentage_rows
                ],
            },
            "sizing": {
                "columns": [{"label": str(col), "width_px": column_width} for col in data.columns],
                "index_width_px": index_width,
            },
            "rules": [
                {
                    "id": "bars",
                    "target": {"scope": "columns", "labels": [str(col) for col in bar_columns]},
                    "action": {"data_bar": {"vmin": bar_min, "vmax": bar_max}},
                }
            ]
            if len(bar_columns)
            else [],
        }
    )
    resolve_table_style(data, plan)
    return {header: {"data": data.copy(), "style": plan.model_dump(mode="json"), "plots": []}}
