"""Named report table presets built from the shared table models and builders.

Every function returns ``{header: {"data": frame, "style": plan, "plots": plots}}``.
Keyword options override preset defaults and are validated by the underlying
builder. Inputs belong to the caller and are never modified.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Hashable

import pandas as pd

from ...cot import analysis, analysis_mifid, position_change, position_divergence, summary_from_timeseries
from ..builder import resolve_table_style
from ..models import TableStylePlan
from .cot import cot_summary_table
from .rollup import rollup_table_hst
from .table_with_link import general_table_with_link
from .table_with_link_monthly import table_with_linked_plots_monthly


def cot_timeseries_table(
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
    Remaining options are passed to ``cot_summary_table``. Prefer the named
    ``cot_cme_timeseries_table`` or ``cot_ice_mifid_timeseries_table``
    presets when migrating ECM calculation paths.
    """
    summary = summary_from_timeseries(observations, summary_options=summary_options, asset_options=asset_options)
    return cot_summary_table(summary, header, **style_options)


def cot_cme_summary_table(
    summary: pd.DataFrame, header: str = "Speculators Net Position (Managed money)", **options: Any
) -> dict[str, dict[str, Any]]:
    """Style existing ``ecm.cmds.quant.cot.analysis`` output without recalculating.

    Used by cot_cme.py, cot_ice.py and cot_macro.py, including their dealer
    variants. Expects the instrument label in the first column and
    ``Net Position (MM)``, with optional ``Net Position (NC)``. Override
    ``header`` for dealers/macro, and column options for normalized summaries.
    """
    return cot_summary_table(
        summary,
        header,
        **{"label_column": next(iter(summary.columns), "Asset"), "position_column": "Net Position (MM)", **options},
    )


def cot_ice_mifid_summary_table(
    summary: pd.DataFrame, header: str = "Speculators Net Position (Investment Funds)", **options: Any
) -> dict[str, dict[str, Any]]:
    """Style existing ``ecm.cmds.quant.cot.analysis_mifid`` output.

    Used by cot_ice_mifid.py, cot_euattf.py and cot_lme.py. Expects the
    instrument label in the first column and ``Net Position``. Calculation
    windows and supplied scores are preserved; no observations are required.
    """
    return cot_summary_table(
        summary,
        header,
        **{"label_column": next(iter(summary.columns), "Asset"), "position_column": "Net Position", **options},
    )


def cot_cme_timeseries_table(
    observations: Mapping[str, pd.DataFrame],
    header: str = "Speculators Net Position (Managed money)",
    *,
    summary_options: Mapping[str, Any] | None = None,
    asset_options: Mapping[str, Mapping[str, Any]] | None = None,
    asset_groups: Mapping[str, str] | None = None,
    **options: Any,
) -> dict[str, dict[str, Any]]:
    """Calculate the ``cot.analysis`` report preset from named time series.

    For CME, ICE and macro reports: each DatetimeIndex frame needs Long/Short,
    with optional OI/PX_LAST/VWAP/Internal and NC Long/NC Short. Position-score
    windows default to 52 observations. Contract conversion is caller-owned
    (e.g. ``position_scale=0.25``); the optional NC pair stays separate.
    Output goes through ``cot_cme_summary_table`` with the same column
    names/order, including the date-range heading and dollar-million changes.
    Each asset is one row in mapping order; ``asset_groups`` adds row separators.
    Uses Runbook's documented return/four-week corrections, not a legacy clone.
    """
    if asset_groups is not None:
        options.setdefault("group_column", "Group")
    summary = analysis(
        observations,
        summary_options=summary_options,
        asset_options=asset_options,
        asset_groups=asset_groups,
        label_column=options.get("label_column"),
        position_column=options.get("position_column", "Net Position (MM)"),
        group_column=options.get("group_column", "Group"),
    )
    return cot_cme_summary_table(summary, header, **options)


def cot_ice_mifid_timeseries_table(
    observations: Mapping[str, pd.DataFrame],
    header: str = "Speculators Net Position (Investment Funds)",
    *,
    summary_options: Mapping[str, Any] | None = None,
    asset_options: Mapping[str, Mapping[str, Any]] | None = None,
    asset_groups: Mapping[str, str] | None = None,
    **options: Any,
) -> dict[str, dict[str, Any]]:
    """Calculate the ``cot.analysis_mifid`` preset from named time series.

    For ICE MiFID, EUA/TTF and LME reports: supply normalized Long/Short and
    optional OI/PX_LAST/VWAP/Internal. Combine additional venues' positions
    into Long/Short before calling. Position-score windows default to 208;
    price-score/rank windows remain 52 and percentile history remains 260.
    ``summary_options`` and per-asset ``asset_options`` override defaults.
    Output goes through ``cot_ice_mifid_summary_table`` with the same
    column names/order, date-range heading and dollar/euro-million changes.
    Each asset is one row in mapping order; ``asset_groups`` adds row separators.
    """
    if asset_groups is not None:
        options.setdefault("group_column", "Group")
    summary = analysis_mifid(
        observations,
        summary_options=summary_options,
        asset_options=asset_options,
        asset_groups=asset_groups,
        label_column=options.get("label_column"),
        position_column=options.get("position_column", "Net Position"),
        group_column=options.get("group_column", "Group"),
    )
    return cot_ice_mifid_summary_table(summary, header, **options)


def cot_position_change_table(
    summary: pd.DataFrame, header: str = "COT", *, threshold: float = 1.5, **options: Any
) -> dict[str, dict[str, Any]]:
    """Apply ECM ``position_change`` screening to already-calculated summaries.

    Used by cot_cme.update_cme and cot_macro.update_macro. Requires
    ``net change z score`` and ``4w delta change z score``; the supplied
    calculation windows are preserved. Column options go to cot_summary_table.
    """
    return cot_summary_table(position_change(summary, threshold=threshold), header, **options)


def cot_position_divergence_table(
    summary: pd.DataFrame, header: str = "COT", **options: Any
) -> dict[str, dict[str, Any]]:
    """Apply ECM ``position_divergence`` screening to calculated summaries.

    Used by cot_cme.update_cme and cot_macro.update_macro. Requires
    ``Weekly Delta Change`` and ``Weekly Price Change`` with opposite signs.
    Column options go to cot_summary_table.
    """
    return cot_summary_table(position_divergence(summary), header, **options)


# Report families sharing the same ECM calculation and column conventions.
cot_ice_summary_table = cot_cme_summary_table
cot_ice_timeseries_table = cot_cme_timeseries_table
cot_euattf_summary_table = cot_lme_summary_table = cot_ice_mifid_summary_table
cot_euattf_timeseries_table = cot_lme_timeseries_table = cot_ice_mifid_timeseries_table

# Calculation-family spellings and the v0.3.2.2 generic names remain available.
cot_analysis_summary_table = cot_cme_summary_table
cot_analysis_timeseries_table = cot_cme_timeseries_table
cot_analysis_mifid_summary_table = cot_ice_mifid_summary_table
cot_analysis_mifid_timeseries_table = cot_ice_mifid_timeseries_table
cot_observations_table = cot_timeseries_table
cot_position_changes_table = cot_position_change_table


def cot_macro_summary_table(
    summary: pd.DataFrame, header: str = "Speculators Net Position", **options: Any
) -> dict[str, dict[str, Any]]:
    """cot_macro.py: standard analysis rows with the macro report heading."""
    return cot_cme_summary_table(summary, header, **options)


def cot_macro_timeseries_table(
    observations: Mapping[str, pd.DataFrame], header: str = "Speculators Net Position", **options: Any
) -> dict[str, dict[str, Any]]:
    """cot_macro.py: a dictionary of Long/Short frames, using cot.analysis."""
    return cot_cme_timeseries_table(observations, header, **options)


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


def futures_price_range_table(
    summary: pd.DataFrame,
    header: str = "Futures price range",
    *,
    history_years: int = 10,
    separator_rows: Sequence[int] = (),
) -> dict[str, dict[str, Any]]:
    """Style calculated rows from cross_cmds/futures_price_range.py.

    Expects Current price vs history, Current Price, Percentile of {N}yr Range,
    Z-score of {N}yr Range, {N}yr Avg Price, {N}yr Max and {N}yr Min. Percentiles
    use one decimal percent and signed bars on [-1, 1]; prices/scores use two
    decimals. The first label column becomes the row index; no numeric index
    is added. All columns are centered. Inputs retain their row/column order.
    Contract history selection and range calculations belong to the caller.
    ``separator_rows`` supplies zero-based group boundaries instead of the
    source report's fixed row numbers. Reuses the grouped-format style builder.
    """
    if not isinstance(history_years, int) or isinstance(history_years, bool) or history_years < 1:
        raise ValueError("history_years must be a positive integer")
    label = "Current price vs history"
    percentile = f"Percentile of {history_years}yr Range"
    required = {
        label,
        "Current Price",
        percentile,
        f"Z-score of {history_years}yr Range",
        f"{history_years}yr Avg Price",
        f"{history_years}yr Max",
        f"{history_years}yr Min",
    }
    if missing := required - set(summary.columns):
        raise ValueError(f"Missing price-range summary columns: {sorted(missing)}")
    frame = summary.set_index(label)
    payload = grouped_metrics_table(frame, header, bar_columns=[percentile], column_width=100, index_width=120)[header]
    plan = payload["style"]
    plan["format"]["columns"][percentile] = {"kind": "percent", "digits": 1}
    for column in plan["sizing"]["columns"]:
        if column["label"] == percentile:
            column["width_px"] = 120
    if len(separator_rows):
        plan["rules"].append(
            {
                "id": "price_range_groups",
                "target": {"scope": "rows", "positions": list(separator_rows)},
                "action": {"border_bottom": "1px solid #000000"},
            }
        )
    resolve_table_style(frame, plan)
    return {header: payload}


def cot_cme_position_change_table(
    summary: pd.DataFrame, header: str = "COT position changes", *, threshold: float = 1.5, **options: Any
) -> dict[str, dict[str, Any]]:
    """Screen and style cot_cme.py/cot_macro.py analysis rows, retaining their schema."""
    return cot_cme_summary_table(position_change(summary, threshold), header, **options)


def cot_cme_position_divergence_table(
    summary: pd.DataFrame, header: str = "COT price/position divergence", **options: Any
) -> dict[str, dict[str, Any]]:
    """Screen cot_cme.py/cot_macro.py analysis rows for opposite weekly moves."""
    return cot_cme_summary_table(position_divergence(summary), header, **options)


cot_macro_position_change_table = cot_cme_position_change_table
cot_macro_position_divergence_table = cot_cme_position_divergence_table


def oil_dashboard_table(data: pd.DataFrame, header: str = "Liquids Price", **options: Any) -> dict[str, dict[str, Any]]:
    """oil/dashboard.py: ten daily price rows, 20-observation MA and seasonal links.

    Supply the report's selected, dated price series. Also used for crude,
    freight, gasoil and gasoline panels. Aggregation and unit conversion of
    source instruments belong to the caller.
    """
    return daily_prices_table(
        data,
        header,
        **{
            "rows": 10,
            "title_column_width": 100,
            "data_column_width": 80,
            "chart_columns": {tuple(data.columns): "seasonal"},
            "exclude_years": [2020, 2022],
            **options,
        },
    )


def kpler_inventory_table(
    data: pd.DataFrame, header: str = "Crude Stocks", **options: Any
) -> dict[str, dict[str, Any]]:
    """oil/kpler_inventory.py and product_inventory.py: stock changes and history.

    Takes prepared daily stock levels (including any report-side five-day
    smoothing). Uses 20-observation changes, three months, four quarters, QTD,
    Y-1/5Y and seasonal highlights excluding 2020. Pass aggregation_columns
    for derived flow rows, e.g. {"Total (kbd)": "mean"}; no smoothing or unit
    conversion is inferred from column names.
    """
    return inventory_summary_table(data, header, **{"history_quarters": 4, "exclude_years": [2020], **options})


def product_inventory_table(
    data: pd.DataFrame, header: str = "Product Stocks", **options: Any
) -> dict[str, dict[str, Any]]:
    """oil/product_inventory.py: prepared daily product stocks, using table_format1."""
    return kpler_inventory_table(data, header, **options)


def kpler_inventory_consensus_table(
    data: pd.DataFrame, header: str = "Crude Stocks", **options: Any
) -> dict[str, dict[str, Any]]:
    """Monthly consensus rows in oil/kpler_inventory.py and product_inventory.py.

    Input is monthly balances in the report's units, with optional _last_update.
    The global crude consensus uses means and three quarters. For US crude use
    aggregation_type="diff"; for US products use aggregation_type=None (levels).
    """
    return monthly_consensus_table(data, header, **{"aggregation_type": "mean", "history_quarters": 3, **options})


def product_inventory_consensus_table(
    data: pd.DataFrame, header: str = "Product Stocks", **options: Any
) -> dict[str, dict[str, Any]]:
    """oil/product_inventory.py: monthly US product consensus levels."""
    return kpler_inventory_consensus_table(data, header, **{"aggregation_type": None, **options})


def russia_exports_table(
    data: pd.DataFrame, header: str = "Total export (kbd)", *, benchmark_quarter: str, **options: Any
) -> dict[str, dict[str, Any]]:
    """oil/russia_exports.py: 10/20-observation averages versus a supplied quarter.

    Includes five completed months and 92-observation highlighting. The report
    passes prior-year Q4 explicitly; templates do not consult today's date.
    Supply prepared daily flows by destination/product, already in kbd.
    """
    return flow_quarterly_table(
        data,
        header,
        benchmark_quarter=benchmark_quarter,
        **{
            "windows": (10, 20),
            "history_months": 5,
            "history_quarters": 0,
            "include_qtd": False,
            "highlighting_rules": {"window": 92},
            **options,
        },
    )


# These reports call the same table_format2_vs_month calculation with these defaults.
opec_exports_table = clean_exports_table = oil_demand_centres_table = russia_exports_table


def oil_on_water_table(
    data: pd.DataFrame, header: str = "Oil on Water (mb)", **options: Any
) -> dict[str, dict[str, Any]]:
    """oil/oil_on_water.py: regional levels plus the report's Total MTD Chg row.

    Supply daily regional stocks, Total and (optionally) Total MTD Chg. As in
    the report, that last series is a copy of Total and receives 20-observation
    differences; despite its name the source report does not enable mtd=True.
    Other rows use means. Includes three quarters/QTD, excluding 2020 history.
    """
    return inventory_summary_table(
        data,
        header,
        **{
            "aggregation_type": "mean",
            "aggregation_columns": {"Total MTD Chg": "diff"} if "Total MTD Chg" in data else None,
            "history_quarters": 3,
            "highlighting_rules": {"window": 92},
            "exclude_years": [2020],
            **options,
        },
    )


def eu_power_rollup_table(
    data: pd.DataFrame, params: Sequence[str] | None = None, header: str = "EU power", **options: Any
) -> dict[str, dict[str, Any]]:
    """User-supplied EU power-stack report: calendar roll-ups and linked seasons.

    This reference is not a recovered new_reports file. Supply one time-series
    frame of generation/load levels; for power or thermal shares supply ratios
    and format_spec="{:.1%}". Latest is the exact last input row.
    The final series supplies the total, labeled "Total" by default; override
    total_label or set it to None for inputs without a total series.
    """
    return rollup_table_hst(data, params, header, **options)
