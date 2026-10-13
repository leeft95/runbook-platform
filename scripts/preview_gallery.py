"""Preview the new report helpers with reproducible, synthetic data only."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from html import escape
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import parse_qs

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.offline import get_plotlyjs
from runbook.core.cot import analysis, analysis_mifid
from runbook.core.plotting.bar import plot_bar
from runbook.core.plotting.line import plot_line
from runbook.core.plotting.templates import (
    plot_cot_long_short,
    plot_cot_net,
    plot_cot_positions,
    plot_forecast_bars,
    plot_four_week_price_position,
    plot_highlighted_bar,
    plot_line_with_comparison,
    plot_line_with_moving_average,
    plot_market_holdings,
    plot_market_ohlc,
    plot_regression_intercept,
    plot_regression_origin,
    plot_reversed_seasonal_forecast,
    plot_rollup_seasonal,
    plot_seasonal_comparison,
    plot_seasonal_with_history,
    plot_spread_position_changes,
    plot_weekly_price_position,
)
from runbook.core.table import TableStylePlan, render_table_html
from runbook.core.table.templates import (
    annual_table,
    annual_table_yoy,
    cot_cme_position_change_table,
    cot_cme_position_divergence_table,
    cot_cme_summary_table,
    cot_cme_timeseries_table,
    cot_ice_mifid_summary_table,
    cot_ice_mifid_timeseries_table,
    daily_prices_table,
    ea_evolution_table,
    ea_evolution_table_yoy,
    eu_power_rollup_table,
    flow_monthly_table,
    flow_quarterly_table,
    futures_price_range_table,
    grouped_metrics_table,
    inventory_summary_table,
    kpler_inventory_consensus_table,
    kpler_inventory_table,
    monthly_consensus_table,
    monthly_table,
    monthly_table_yoy,
    mtd_inventory_table,
    oil_dashboard_table,
    oil_on_water_table,
    product_inventory_consensus_table,
    product_inventory_table,
    quarterly_table,
    quarterly_table_yoy,
    rollup_table_fcst,
    rollup_table_hst,
    russia_exports_table,
    seasonal_table,
    seasonal_table_yoy,
    summer_table,
    summer_table_yoy,
    winter_table,
    winter_table_yoy,
)
from runbook.core.table.templates.table_with_link import general_table_with_link
from runbook.core.table.templates.table_with_link_monthly import table_with_linked_plots_monthly
from runbook.core.table.templates.common import color_negative_red
from runbook.core.timeseries import range_vol
from runbook.core.timeseries.cot import prepare_cot_data


def add_range_vol_examples(table: Callable[..., Any], chart: Callable[..., Any]) -> None:
    """Feed calculated synthetic Range-Vol observations into the existing renderers."""
    as_of = pd.Timestamp("2026-10-13 12:00")
    dates = pd.bdate_range(end=as_of.normalize(), periods=180)
    t = np.arange(len(dates), dtype=float)
    bars = pd.DatetimeIndex(
        [day + pd.Timedelta(hours=9, minutes=minute) for day in dates[-30:] for minute in range(0, 181, 10)]
    )
    metrics, sharpe_rows, signal_rows, detail = {}, {}, {}, {}
    for name, kind, level, scale, phase in (
        ("Brent", "FLAT", 75, 1.0, 0),
        ("WTI", "FLAT", 70, 0.8, 13),
        ("Brent M1–M2", "SPRD", 0.5, 0.08, 5),
        ("WTI M1–M2", "SPRD", 0.3, 0.07, 20),
    ):
        x = t + phase
        close = pd.Series(level + scale * (0.03 * t + 4 * np.sin(x / 5) + np.cos(x / 2)), index=dates)
        daily = pd.DataFrame(
            {
                "PX_LAST": close,
                "PX_OPEN": close.shift().fillna(close.iloc[0]),
                "PX_HIGH": close + scale * (1 + np.sin(x) ** 2),
                "PX_LOW": close - scale * (0.5 + 0.75 * np.cos(x / 2) ** 2),
                "VOLUME": 100000 + 20000 * np.sin(x / 6),
                "3MTH_IMPVOL_100.0%MNY_DF": 25.0,
            }
        )
        # Upstream weekly/monthly labels must be observations in the daily frame.
        period_frames = [
            daily.groupby(dates.to_period(period)).agg(
                {
                    "PX_LAST": "last",
                    "PX_HIGH": "max",
                    "PX_LOW": "min",
                }
            )
            for period in ("W-FRI", "M")
        ]
        for frame, period in zip(period_frames, ("W-FRI", "M"), strict=True):
            frame.index = pd.DatetimeIndex(pd.Series(dates, index=dates).groupby(dates.to_period(period)).last())
        prices = range_vol.prepare_price_data(daily, *period_frames)
        assert prices is not None
        intraday = pd.DataFrame(
            {
                "close": np.repeat(close.iloc[-30:].to_numpy(), 19) + scale * 0.1 * np.sin(np.arange(len(bars)) / 3),
                "volume": np.repeat(daily.VOLUME.iloc[-30:].to_numpy() / 19, 19),
            },
            index=bars,
        )
        intraday.loc[intraday.index.normalize() == dates[-1], "volume"] *= 1.8 if kind == "FLAT" else 0.65
        changes = range_vol.calculate_price_changes(close, kind, intraday)
        ranges = range_vol.calculate_range_metrics(prices["highp"], prices["lowp"], close, as_of=as_of)
        volume = range_vol.calculate_volume_spikes(intraday, daily, as_of=as_of)
        sharpe = range_vol.calculate_sharpe_ratios(
            changes["daily_price_chg"], changes["intraday_price_chg"], chg_type=kind
        )
        kpi = range_vol.calculate_kpi(close, prices["imp_vol"], changes["daily_price_chg"], kind)
        momentum = range_vol.calculate_moving_average_signals(close)
        fisher = range_vol.calculate_fisher_indicators(
            *(prices[key + suffix] for suffix in ("", "_w", "_m") for key in ("highp", "lowp", "closep"))
        )
        fish, fish1, fishlt, fishlt1, counter, counter1 = range_vol.determine_fisher_signals(fisher, close)
        price_range = range_vol.calculate_current_price_range(close, prices["highp"], prices["lowp"])
        trend = range_vol.calculate_trend_index(
            changes["price_change"],
            ranges["range_spike"],
            volume["volume_spike_5d"],
            range_vol.calculate_three_day_trend(close),
            sharpe["sharpe_3d"],
            sharpe["sharpe_22d"],
            price_range,
            0.0,
            ranges["avg_true_range"],
        )
        combined = range_vol.determine_combined_signals(
            trend,
            changes["price_change"],
            momentum["mom"],
            momentum["mom1"],
            momentum["hybrid"],
            momentum["hybrid1"],
            fish,
            fish1,
            fishlt,
            fishlt1,
            counter,
            counter1,
        )
        fom_flag, fom_score, _ = range_vol.calculate_fom_metrics(
            "2026-10-01", changes["daily_price_chg"], prices["highp"], prices["lowp"], close, as_of=as_of
        )
        metrics[name] = {
            "Convention": kind,
            "Latest": close.iloc[-1],
            "Range spike": ranges["range_spike"],
            "Volume 5d": volume["volume_spike_5d"],
            "Volume 20d": volume["volume_spike_20d"],
            "FOM score": fom_score,
            "FOM breakout": fom_flag or "—",
        }
        sharpe_rows[name] = {
            "Sharpe 3d live": sharpe["sharpe_3d"],
            "Sharpe 3d COB": sharpe["sharpe_3d_cob"],
            "Sharpe 22d": sharpe["sharpe_22d"],
            "KPI": kpi["kpi_on"],
            "KPI t−1": kpi["kpi_1d"],
            "KPI index": kpi["kpi_avg"],
            "Trend index": trend,
        }
        signal_rows[name] = {
            "Momentum": momentum["mom"] or momentum["mom2"] or "—",
            "Hybrid": momentum["hybrid"] or momentum["hybrid2"] or "—",
            "Fisher": fish or "—",
            "Long-term Fisher": fishlt or "—",
            "Counter": counter or "—",
            "Stochastic": range_vol.calculate_stochastic(prices["highp"], prices["lowp"], close) or "—",
            "Sharpe": range_vol.classify_sharpe_signal(sharpe["sharpe_3d_cob"], sharpe["sharpe_22d"]),
            "Signal flag": range_vol.calculate_signal_flag(combined, trend),
        }
        detail[name] = dict(close=close, momentum=momentum, fisher=fisher, ranges=ranges, volume=volume)

    divergence = pd.DataFrame.from_dict(
        {
            name: range_vol.calculate_divergence(detail[f"{name} M1–M2"]["close"], detail[name]["close"], as_of=as_of)
            for name in ("Brent", "WTI")
        },
        orient="index",
    )
    # Deliberately crossing spread inputs demonstrate sign switches, including zero.
    spreads = pd.DataFrame({"M1–M2": [0.3, -0.2], "M2–M3": [0.1, 0.1], "M3–M4": [0.2, 0.1]}, index=dates[-2:])
    risk_metrics = pd.DataFrame.from_dict(sharpe_rows, orient="index")[["KPI", "KPI index", "Trend index"]]
    weights = {"Brent": 0.6, "WTI": 0.4}
    risk = pd.DataFrame(
        {
            "Brent": risk_metrics.loc["Brent"],
            "WTI": risk_metrics.loc["WTI"],
            "Weighted energy": range_vol.calculate_weighted_risk_index(risk_metrics, weights, normalize=True),
        }
    ).T
    for key, title, description, data, code in (
        (
            "range-vol-metrics",
            "Range-Vol · range, volume and FOM",
            "Calculated from synthetic OHLC and ten-minute bars as of 13 October 2026, 12:00. Range/volume are ratios; FOM uses the 1 October event and preceding 20 returns. FLAT and SPRD retain their own change convention.",
            pd.DataFrame.from_dict(metrics, orient="index"),
            'range_vol.calculate_range_metrics(high, low, close, as_of=as_of)\nrange_vol.calculate_volume_spikes(intraday, daily, as_of=as_of)\nrange_vol.calculate_fom_metrics("2026-10-01", changes, high, low, close, as_of=as_of)',
        ),
        (
            "range-vol-sharpe",
            "Range-Vol · Sharpe, KPI and trend",
            "The same observations: live and COB three-day Sharpe, preceding 22-return Sharpe, implied-volatility-normalized KPI and trend index. Values are raw ratios/scores, not percentage price returns.",
            pd.DataFrame.from_dict(sharpe_rows, orient="index"),
            'range_vol.calculate_sharpe_ratios(daily_changes, intraday_changes, chg_type="FLAT")\nrange_vol.calculate_kpi(close, implied_vol, daily_changes, "FLAT")',
        ),
        (
            "range-vol-signals",
            "Range-Vol · momentum and Fisher signals",
            "Signals derived from the same inputs. BUY/SELL denote fresh crosses; B/S denote prior EMA alignment. A dash means no signal. The final flag uses the report's combined-signal and trend rules.",
            pd.DataFrame.from_dict(signal_rows, orient="index"),
            "range_vol.calculate_moving_average_signals(close)\nrange_vol.determine_fisher_signals(fisher, close)",
        ),
        (
            "range-vol-divergence",
            "Range-Vol · spread/flat divergence",
            "Three/eight-observation change ratios with the current daily row excluded. This calculation preview shows both pairs; the report screens negative ratios upstream of display.",
            divergence,
            "range_vol.calculate_divergence(spread, flat, as_of=as_of)",
        ),
        (
            "range-vol-flies",
            "Range-Vol · fly sign switches",
            "Two explicitly crossing synthetic adjacent-spread pairs. Includes a move to zero; rows are actual calculate_fly_switches output.",
            range_vol.calculate_fly_switches(spreads),
            "range_vol.calculate_fly_switches(spreads)",
        ),
        (
            "range-vol-risk",
            "Range-Vol · weighted energy metrics",
            "Brent and WTI values from the Sharpe/KPI example, followed by a 60%/40% weighted component. The helper aggregates already-calculated metric rows.",
            risk,
            'range_vol.calculate_weighted_risk_index(metrics, {"Brent": 0.6, "WTI": 0.4}, normalize=True)',
        ),
    ):
        data.index.name = "Instrument" if key != "range-vol-flies" else "Fly"
        payload = table(
            key,
            title,
            description,
            grouped_metrics_table,
            data,
            header=title,
            index_width=180,
            column_width=125,
            code=code,
        )
        numeric = data.select_dtypes(include="number").columns
        for column in numeric:
            if pd.api.types.is_integer_dtype(data[column].dtype):
                payload["style"]["format"]["columns"][column]["digits"] = 0
        payload["style"]["rules"].extend(
            rule.model_dump(mode="json")
            for rule in color_negative_red(list(data.columns), [(column, column) for column in numeric])
        )

    brent = detail["Brent"]
    averages = pd.DataFrame(
        {"Close": brent["close"], **{f"EMA {window}": brent["momentum"][f"emva{window}"] for window in (3, 8, 14, 30)}},
        index=dates,
    )
    chart(
        "range-vol-ema",
        "Range-Vol · ECM EMAs and ATR",
        "Exact migrated 3/8/14/30-observation EMAs, with the five-observation ATR below. Warm-up gaps are retained; both panels use the Brent table inputs.",
        plot_line,
        {
            "Price and EMAs": averages,
            "ATR (5 observations)": pd.DataFrame({"ATR 5": brent["ranges"]["avg_true_range"]}, index=dates),
        },
        rows=2,
        shared_xaxes=True,
        code='averages = {n: range_vol.calculate_exponential_moving_average(close, n) for n in (3, 8, 14, 30)}\nplot_line({"Price and EMAs": prices_and_averages, "ATR": atr_frame}, rows=2, shared_xaxes=True)',
    )
    bands = pd.DataFrame({"Close": brent["close"].tail(40)})
    for field, label in (
        ("fdh", "Daily high"),
        ("fdl", "Daily low"),
        ("fwh", "Weekly high"),
        ("fwl", "Weekly low"),
        ("fmh", "Monthly high"),
        ("fml", "Monthly low"),
    ):
        bands[label] = brent["fisher"][field]
    chart(
        "range-vol-fisher",
        "Range-Vol · latest Fisher price bands",
        "Latest daily/weekly/monthly band levels extended across recent Brent history for comparison. These are current reference levels, not historical band series.",
        plot_line,
        bands,
        code="fisher = range_vol.calculate_fisher_indicators(high, low, close, weekly_high, weekly_low, weekly_close, monthly_high, monthly_low, monthly_close)",
    )
    volumes = brent["volume"]["volume_at_minute"].to_frame("Volume at 12:00")
    volumes["Previous 5-session mean"] = volumes.iloc[:, 0].rolling(5).mean().shift()
    volumes["Previous 20-session mean"] = volumes.iloc[:, 0].rolling(20).mean().shift()
    chart(
        "range-vol-volume",
        "Range-Vol · same-time cumulative volume",
        "Each session's cumulative volume at noon, with the preceding five/twenty-session reference means. The final session is excluded from its own denominators.",
        plot_line,
        volumes,
        code='volume = range_vol.calculate_volume_spikes(intraday, daily, as_of=as_of)\nsamples = volume["volume_at_minute"]',
    )
    chart(
        "range-vol-kpi",
        "Range-Vol · current and prior KPI",
        "Current, previous and exponentially weighted KPI from the table above. Each asset uses its FLAT/SPRD normalization; bars show ratios, not price units.",
        plot_bar,
        pd.DataFrame.from_dict(sharpe_rows, orient="index")[["KPI", "KPI t−1", "KPI index"]],
        code='plot_bar(kpi_summary[["KPI", "KPI t−1", "KPI index"]])',
    )


def build_examples() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Exercise the public helpers, without duplicating their calculations."""
    rng = np.random.default_rng(42)
    dates = pd.date_range("2017-01-01", "2025-07-01")
    t = np.arange(len(dates))
    daily = pd.DataFrame(
        {
            "Crude stocks": 420 + 24 * np.sin(t / 58) + t / 650,
            "Product stocks": 210 + 15 * np.cos(t / 68) + t / 900,
            "Refinery runs": 16 + 2 * np.sin(t / 42) + rng.normal(0, 0.2, len(t)),
        },
        index=dates,
    )
    price = pd.DataFrame(
        {"Brent": 73 + 5 * np.sin(t / 26) + rng.normal(0, 0.3, len(t)), "WTI": 68 + 4 * np.sin(t / 27)}, index=dates
    )
    price["Spread"] = price.Brent - price.WTI
    weekly = pd.date_range("2017-01-03", "2025-07-01", freq="W-TUE")
    w = np.arange(len(weekly))
    positions = pd.DataFrame(
        {
            "Long": 190_000 + 26_000 * np.sin(w / 11) + rng.normal(0, 1700, len(w)),
            "Short": 95_000 + 17_000 * np.cos(w / 13),
            "OI": 700_000 + 30_000 * np.sin(w / 22),
            "PX_LAST": 72 + 7 * np.sin(w / 11) + rng.normal(0, 0.7, len(w)),
            "Internal": np.sin(w / 19),
            "NC Long": 220_000 + w * 90,
            "NC Short": 120_000 + w * 40,
        },
        index=weekly,
    )
    positions["VWAP"] = positions.PX_LAST - 0.15
    prepared = prepare_cot_data(positions)
    tables: list[dict[str, Any]] = []
    charts: list[dict[str, Any]] = []

    def table(
        key: str,
        title: str,
        description: str,
        template: Callable[..., dict[str, dict[str, Any]]],
        *args: Any,
        code: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        payload = next(iter(template(*args, **kwargs).values()))
        tables.append(
            dict(
                key=key,
                title=title,
                description=description,
                payload=payload,
                code=code,
                template=f"{template.__module__}.{template.__name__}",
            )
        )
        return payload

    def chart(
        key: str,
        title: str,
        description: str,
        template: Callable[..., go.Figure],
        *args: Any,
        code: str | None = None,
        **kwargs: Any,
    ) -> None:
        charts.append(
            dict(
                key=key,
                title=title,
                description=description,
                figure=template(*args, **kwargs),
                code=code,
                template=f"{template.__module__}.{template.__name__}",
            )
        )

    fixture = pd.read_csv(Path(__file__).resolve().parents[1] / "data/fixtures/cot/summary.csv")
    fixture["Net Position (NC)"] = [135_000, 145_000, -88_000, -92_000]
    fixture.loc[1, ["net change z score", "4w delta change z score"]] = [0.7, 1.1]
    fixture.loc[3, ["net change z score", "4w delta change z score"]] = [-0.7, -1.1]
    fixture.loc[[1, 3], "Weekly Price Change"] *= -1
    fixture.loc[[1, 3], "_price_chg"] = 1
    cot_options = dict(label_column="24-Jun to 01-Jul", position_column="Net Position (MM)", group_column="Group")
    analysis_inputs = {
        name: positions * (1 + i * 0.05)
        for i, name in enumerate(["Brent Fut", "Brent Fut+Opt", "WTI Fut", "WTI Fut+Opt"])
    }
    analysis_groups = {name: name.split()[0] for name in analysis_inputs}
    analysis_links = {name: "cot-net" for name in analysis_inputs}
    analysis_summary = analysis(analysis_inputs, summary_options={"contract_value": 1000}, asset_groups=analysis_groups)
    mifid_inputs = {
        name: positions.drop(columns=["NC Long", "NC Short"]) * (1 + i * 0.1)
        for i, name in enumerate(["TTF Fut+Opt", "EUA Fut+Opt", "LME Copper Fut+Opt", "LME Aluminium Fut+Opt"])
    }
    mifid_groups = {name: "Metals" if name.startswith("LME") else "Energy" for name in mifid_inputs}
    mifid_summary = analysis_mifid(mifid_inputs, summary_options={"contract_value": 1000}, asset_groups=mifid_groups)
    table(
        "cot",
        "COT · analysis summary (CME / ICE / macro)",
        "Four precomputed analysis rows, built in report order from the same synthetic data as the time-series example below.",
        cot_cme_summary_table,
        analysis_summary,
        plot_links=analysis_links,
        group_column="Group",
    )
    table(
        "cot-calculated",
        "COT · analysis from time series (CME / ICE / macro)",
        "The report pipeline: calculate Brent/WTI Fut and Fut+Opt rows, concatenate, then use the same summary formatter. Matches the table above.",
        cot_cme_timeseries_table,
        analysis_inputs,
        summary_options={"contract_value": 1000},
        asset_groups=analysis_groups,
        plot_links=analysis_links,
    )
    table(
        "cot-mifid-summary",
        "COT · analysis_mifid summary (ICE MiFID / EUA-TTF / LME)",
        "Four precomputed investment-fund rows from the same synthetic TTF/EUA/LME inputs as the time-series example below.",
        cot_ice_mifid_summary_table,
        mifid_summary,
        group_column="Group",
    )
    table(
        "cot-mifid-calculated",
        "COT · analysis_mifid from time series (ICE MiFID / EUA-TTF / LME)",
        "The MiFID report pipeline with 208-observation position scores. Rows, columns, values and styling match the summary above.",
        cot_ice_mifid_timeseries_table,
        mifid_inputs,
        summary_options={"contract_value": 1000},
        asset_groups=mifid_groups,
    )
    table(
        "cot-changes",
        "COT · position_change alerts (CME / macro)",
        "Already-calculated summary rows; a 2.15 score threshold selects the strongest four-week position changes.",
        cot_cme_position_change_table,
        fixture,
        threshold=2.15,
        **cot_options,
    )
    table(
        "cot-divergence",
        "COT · position_divergence alerts (CME / macro)",
        "Already-calculated summary rows whose weekly price and position changes have opposite signs.",
        cot_cme_position_divergence_table,
        fixture,
        **cot_options,
    )
    table(
        "daily",
        "Oil dashboard · daily linked prices",
        "oil/dashboard.py: ten daily prices, a 20-observation MA, change highlights and linked seasonal charts.",
        oil_dashboard_table,
        price.tail(130),
        footer="Synthetic observations · 1 July 2025",
    )
    table(
        "linked-general",
        "Core linked variant · general",
        "The general linked table defaults to column_plot_links=True and all_plots_link=True: each column and the aggregate heading open local companion-plot pages.",
        general_table_with_link,
        price.tail(130),
        header="General prices",
        chart_columns={"Brent": "line", "WTI": "seasonal"},
    )
    table(
        "linked-disabled",
        "Linked review · both link types disabled",
        "Explicit False for column_plot_links and all_plots_link leaves the table without companion links while retaining its generated plot payload.",
        general_table_with_link,
        price.tail(130),
        header="Links disabled",
        column_plot_links=False,
        all_plots_link=False,
    )
    chart(
        "daily-ma",
        "Daily line with moving average",
        "Optional daily-chart template: a 20-observation moving-average overlay on Brent.",
        plot_line_with_moving_average,
        price.Brent.tail(130),
        window=20,
    )
    chart(
        "daily-comparison",
        "Daily line with secondary comparison",
        "WTI on the primary axis and a supplied spread series on the secondary axis.",
        plot_line_with_comparison,
        price.WTI.tail(130),
        comparison=price[["Spread"]],
    )

    table(
        "inventory",
        "Kpler inventory · seasonal stock comparisons",
        "oil/kpler_inventory.py: 20-observation changes, mixed flow averages, three months, four quarters, QTD, Y−1/5Y excluding 2020.",
        kpler_inventory_table,
        daily,
        aggregation_columns={"Refinery runs": "mean"},
        exclude_years=[2020],
    )
    flows = pd.DataFrame({"Exports": 1500 + 200 * np.sin(t / 47), "Imports": 1800 + 150 * np.cos(t / 53)}, index=dates)
    table(
        "flow-quarter",
        "Russia / OPEC exports · quarter benchmark",
        "oil/russia_exports.py and opec_exports.py: 10/20-observation averages, five months and 92-observation highlights versus a supplied quarter.",
        russia_exports_table,
        flows,
        benchmark_quarter="2025Q1",
    )
    table(
        "flow-month",
        "Generic example · monthly flow totals",
        "Generic builder example: rolling sums and completed-month totals versus May. No matching source report identified.",
        flow_monthly_table,
        flows / 100,
        benchmark_month="2025-05-01",
    )
    consensus = daily[["Crude stocks", "Product stocks"]].resample("MS").mean()
    consensus["_last_update"] = "2025-07-01"
    table(
        "monthly",
        "Kpler inventory · monthly consensus",
        "oil/kpler_inventory.py: monthly balances, quarterly means, QTD and year comparisons. Use aggregation_type='diff' for the US crude variant.",
        kpler_inventory_consensus_table,
        consensus,
    )
    table(
        "linked-monthly",
        "Core linked variant · monthly",
        "The monthly linked table defaults to row_plot_links=True and all_plots_link=True: row labels and the aggregate heading open local seasonal-plot pages.",
        table_with_linked_plots_monthly,
        consensus,
        header="Monthly stocks",
        windows=(1,),
        aggregation_type="diff",
        history_months=3,
        history_quarters=2,
        include_qtd=True,
        comparison_years=5,
    )
    table(
        "linked-subset",
        "Linked review · selected row subset",
        'row_plot_links=["Crude stocks"] links only the selected row; all_plots_link=True keeps the aggregate heading linked.',
        table_with_linked_plots_monthly,
        consensus,
        header="Subset links",
        windows=(1,),
        aggregation_type="diff",
        history_months=3,
        history_quarters=2,
        include_qtd=True,
        comparison_years=5,
        row_plot_links=["Crude stocks"],
        all_plots_link=True,
    )
    table(
        "linked-monthly-preset",
        "Linked preset · monthly consensus",
        "The public monthly_consensus_table preset inherits the shared row and aggregate link contract and defaults both link types to True.",
        monthly_consensus_table,
        consensus,
    )
    table(
        "product-consensus",
        "Product inventory · monthly consensus levels",
        "oil/product_inventory.py: US product balances as monthly and quarter-end levels, with QTD and three quarters of history.",
        product_inventory_consensus_table,
        consensus[["Product stocks", "_last_update"]],
    )
    table(
        "mtd",
        "Generic example · MTD stock changes",
        "Generic builder example: changes from the prior month-end, pinned to 24 June. This differs from the oil-on-water report calculation.",
        mtd_inventory_table,
        daily[["Crude stocks", "Product stocks"]],
        as_of="2025-06-24",
    )
    table(
        "linked-daily-preset",
        "Linked preset · daily prices",
        "The public daily_prices_table preset uses the general linked variant with both link types enabled by default.",
        daily_prices_table,
        price.tail(130),
    )
    table(
        "linked-inventory-preset",
        "Linked preset · inventory summary",
        "The public inventory_summary_table preset uses monthly row links and an aggregate link by default.",
        inventory_summary_table,
        daily,
    )
    table(
        "linked-flow-preset",
        "Linked preset · quarterly flow",
        "The public flow_quarterly_table preset uses monthly row links and an aggregate link by default.",
        flow_quarterly_table,
        flows,
        benchmark_quarter="2025Q1",
    )
    table(
        "linked-product-preset",
        "Linked preset · product inventory",
        "The public product_inventory_table preset retains the shared monthly link contract for daily product balances.",
        product_inventory_table,
        daily,
    )

    water = daily[["Crude stocks", "Product stocks"]].copy()
    water["Total"] = water.sum(axis=1)
    water["Total MTD Chg"] = water.Total
    table(
        "oil-on-water",
        "Oil on water · levels and total change",
        "oil/oil_on_water.py: 20-observation averages, with a difference for the report's Total MTD Chg row; three quarters, QTD and 92-observation highlights.",
        oil_on_water_table,
        water,
    )

    price_ranges = pd.DataFrame(
        {
            "Current price vs history": ["Brent M1", "Brent M1–M2", "WTI M1", "WTI M1–M2"],
            "Current Price": [72.25, 0.55, 68.40, -0.25],
            "Percentile of 10yr Range": [0.35, 0.70, -0.25, -0.60],
            "Z-score of 10yr Range": [0.65, 1.25, -0.40, -1.10],
            "10yr Avg Price": [68.10, 0.25, 71.30, 0.10],
            "10yr Max": [105.0, 1.50, 102.0, 1.25],
            "10yr Min": [35.0, -1.00, 32.0, -1.20],
        },
    )
    table(
        "price-range",
        "Futures price range · signed percentile bars",
        "cross_cmds/futures_price_range.py: calculated price-range rows, percentage bars on −1 to +1, two-decimal prices/z-scores and instrument group separators.",
        futures_price_range_table,
        price_ranges,
        separator_rows=(1,),
    )

    chart(
        "seasonal",
        "Seasonal comparison and cumulative panels",
        "Seasonal years, deviations from Y−1 / five-year history, and cumulative comparisons.",
        plot_seasonal_comparison,
        daily[["Crude stocks"]],
        current_year=2025,
        start="2020-01-01",
        exclude_years=[2020],
    )
    chart(
        "seasonal-reversed",
        "Seasonal forecast · reversed axes",
        "The selected year changes to a dashed forecast after 1 April. Axis reversal applies to the seasonal and comparison panels.",
        plot_reversed_seasonal_forecast,
        daily[["Product stocks"]],
        current_year=2025,
        start="2021-01-01",
        dash_from=pd.Timestamp("2025-04-01"),
        y_axis_title="Stocks (reversed)",
    )
    chart(
        "seasonal-grid",
        "Seasonal columns beside ordinary history",
        "Two seasonal columns share legend controls; the history column retains actual dates on an independent axis.",
        plot_seasonal_with_history,
        {"Crude stocks": daily[["Crude stocks"]], "Product stocks": daily[["Product stocks"]]},
        history=daily[["Crude stocks", "Product stocks"]],
        current_year=2025,
        start="2021-01-01",
    )
    chart(
        "cot-full",
        "COT · net, long and short",
        "Three position columns with price overlays, OI ratios, previous-five-year bands and an Internal model estimate.",
        plot_cot_positions,
        prepared,
        start=pd.Timestamp("2020-01-01"),
    )
    chart(
        "cot-pair",
        "COT · long / short",
        "Two-column COT layout using the same model and observation dates.",
        plot_cot_long_short,
        prepared,
        start=pd.Timestamp("2020-01-01"),
    )
    chart(
        "cot-net",
        "COT · net position and OI",
        "Two stacked panels at 70/30: seasonal position/price above OI and Internal. Linked COT asset names open this example.",
        plot_cot_net,
        prepared,
        start=pd.Timestamp("2020-01-01"),
    )
    recent_price = price.Brent.tail(150)
    ohlc = pd.DataFrame(
        {
            "PX_OPEN": recent_price - 0.2,
            "PX_HIGH": recent_price + 0.8,
            "PX_LOW": recent_price - 0.7,
            "PX_LAST": recent_price,
            "VOLUME": rng.integers(80_000, 140_000, len(recent_price)),
            "FUT_AGGTE_OPEN_INT": 700_000 + np.arange(len(recent_price)) * 100,
        },
        index=recent_price.index,
    )
    chart(
        "market",
        "COT · OHLC measurement week",
        "Price above volume/OI in a 70/30 layout. The box highlights 24 June–1 July, the week measured by the latest COT observation.",
        plot_market_ohlc,
        {"Brent": ohlc, "WTI": ohlc * 0.9},
        cot_start=prepared.index[-1] - pd.Timedelta(days=7),
    )
    chart(
        "market-holdings",
        "OHLC · open interest and holdings",
        "Holdings get their own third row when open interest is also supplied.",
        plot_market_holdings,
        {"Commodity fund": ohlc.assign(HOLDINGS=1500 + np.arange(len(ohlc)) * 3)},
        cot_start=prepared.index[-1] - pd.Timedelta(days=7),
    )
    changes = pd.DataFrame(
        {"Price change (%)": prepared.PX_LAST.pct_change(fill_method=None) * 100, "Net change": prepared.Net.diff()}
    ).tail(104)
    chart(
        "regression",
        "OLS regression · through the origin",
        "Full sample, recent 8 / 3 / 1 observations, fitted line and ±2 residual-standard-deviation bands.",
        plot_regression_origin,
        changes,
    )
    chart(
        "regression-intercept",
        "OLS regression · fitted intercept",
        "The same change data with an intercept; coefficients remain available in figure metadata.",
        plot_regression_intercept,
        changes,
    )
    for template, key, title in [
        (plot_weekly_price_position, "position-weekly", "Price vs positioning · weekly"),
        (plot_four_week_price_position, "position-four-week", "Price vs positioning · four weeks"),
        (plot_spread_position_changes, "position-spread", "Price vs positioning · spread changes"),
    ]:
        chart(
            key,
            title,
            "Older observations are grouped by year, with the previous four and the latest observation highlighted separately.",
            template,
            prepared.tail(130),
        )
    forecast = pd.Series(
        [101, 102, 99, 105, 107, 110, 112, 109, 108, 111, 113, 116],
        index=pd.date_range("2025-01-01", periods=12, freq="MS"),
        name="Demand",
    )
    chart(
        "forecast",
        "Bars · history and forecast",
        "From July onward, bars use the forecast color and pattern.",
        plot_forecast_bars,
        forecast,
        forecast_from=pd.Timestamp("2025-07-01"),
    )
    chart(
        "forecast-single",
        "Bars · one selected observation",
        "Only July is highlighted; later observations retain the base style.",
        plot_highlighted_bar,
        forecast,
        selected_at=pd.Timestamp("2025-07-01"),
    )
    power = pd.DataFrame(
        {
            "Gas": 26 + 4 * np.sin(t / 58),
            "Coal": 3 + np.cos(t / 70),
            "Nuclear": 45 + 5 * np.sin(t / 88),
            "Wind": 11 + 6 * np.cos(t / 49),
            "Solar": 20 + 8 * np.sin(t / 60),
        },
        index=dates,
    )
    power["Load"] = power.sum(axis=1)
    rollup_power = power.rename(columns={"Load": "Total"})
    balances = power.copy()
    balances["Gas share"] = power.Gas / (power.Gas + power.Coal)
    balances["Net balance"] = power.Load - 108
    for key, title, level_template, yoy_template, start in [
        ("monthly", "Monthly", monthly_table, monthly_table_yoy, "2023-07-01"),
        ("quarterly", "Quarterly", quarterly_table, quarterly_table_yoy, "2023-01-01"),
        ("seasonal", "Seasonal", seasonal_table, seasonal_table_yoy, "2019-04-01"),
        ("summer", "Summer", summer_table, summer_table_yoy, "2019-04-01"),
        ("winter", "Winter", winter_table, winter_table_yoy, "2019-04-01"),
        ("annual", "Annual", annual_table, annual_table_yoy, "2019-01-01"),
    ]:
        for template, suffix in [(level_template, ""), (yoy_template, "-yoy")]:
            table(
                f"balance-{key}{suffix}",
                f"Power balance · {title}" + (" YoY" if suffix else ""),
                "Dates are selected on the input data upstream. YoY compares matching periods in the supplied data; missing comparisons are dashes. Negative values are red in every table. Summers cover April–October; winters cover November–March.",
                template,
                balances.loc[start:"2025-06-30"],
                column_formats={"Gas share": "{:.2f}"},
            )
    ea_months = pd.date_range("2024-01-01", "2027-12-01", freq="MS")
    ea_time = np.arange(len(ea_months))
    ea_balance = pd.DataFrame(
        {
            "2026-10-05": 1.8 * np.sin(ea_time / 3) + 0.04 * ea_time - 1,
            "2026-09-28": 1.7 * np.sin(ea_time / 3) + 0.035 * ea_time - 1.1,
        },
        index=ea_months,
    )
    ea_supply = pd.DataFrame(
        {
            "2026-10-05": 100 + 0.15 * ea_time + 3 * np.sin(ea_time / 3),
            "2026-09-28": 99.9 + 0.14 * ea_time + 2.9 * np.sin(ea_time / 3),
        },
        index=ea_months,
    )
    for template, key, title, frame, variable, calculation in [
        (
            ea_evolution_table,
            "ea-evolution",
            "Global Liquids Balance (mbd)",
            ea_balance,
            "ea_balance",
            "Quarter and full-year means preserve the supplied units.",
        ),
        (
            ea_evolution_table_yoy,
            "ea-evolution-yoy",
            "YoY Global Liquids Supply (mbd)",
            ea_supply,
            "ea_supply",
            "Absolute YoY changes: quarters share the newest release's prior-year baseline; annual rows use each release's own preceding year.",
        ),
    ]:
        for single in (True, False):
            selection = '[["2026-09-28"]]' if single else ""
            table(
                key + ("-single" if single else ""),
                "EA Evolution · " + title + (" · first release" if single else " · release comparison"),
                "Monthly dates in the index, one release per column. "
                + calculation
                + " Two quarters before through two after 12 October 2026, with annual rows after each year.",
                template,
                frame[["2026-09-28"]] if single else frame,
                header=title,
                as_of="2026-10-12",
                code=f'{template.__name__}({variable}{selection}, header="{title}", as_of="2026-10-12")',
            )
    table(
        "rollup-power",
        "Power · calendar roll-ups",
        "Latest and 20d MA receive z-score highlights by default. Any displayed column can be selected with use_highlighting. Each row opens full history and seasonal base/average panels.",
        eu_power_rollup_table,
        rollup_power,
        header="EU power",
    )
    table(
        "linked-custom",
        "Linked review · custom destinations",
        "Custom row_plot_links and all_plots_link URLs point to local gallery anchors; this confirms callers can replace generated destinations independently.",
        rollup_table_hst,
        rollup_power,
        params=["Latest", "5d MA", "20d MA", "3m MA"],
        header="Custom destinations",
        row_plot_links="/gallery/index.html#linked-general",
        all_plots_link="/gallery/index.html#linked-monthly",
    )
    table(
        "linked-rollup-hst",
        "Core linked variant · historical roll-up",
        "The historical roll-up defaults to row_plot_links=True and all_plots_link=True: each displayed series and the index heading open local history/seasonal plot pages.",
        rollup_table_hst,
        rollup_power,
        params=["Latest", "5d MA", "20d MA", "3m MA"],
        header="History roll-up",
    )
    table(
        "rollup-highlight-hst",
        "Roll-up review · selected historical highlights",
        "The default roll-up card highlights Latest and 20d MA. This comparison selects 5d MA and 3m MA instead; the exact use_highlighting argument is shown below.",
        rollup_table_hst,
        rollup_power,
        params=["Latest", "5d MA", "20d MA", "3m MA"],
        header="Selected history highlights",
        use_highlighting=["5d MA", "3m MA"],
        code='rollup_table_hst(rollup_power, params=["Latest", "5d MA", "20d MA", "3m MA"],\n    header="Selected history highlights", use_highlighting=["5d MA", "3m MA"])',
    )
    table(
        "rollup-highlight-hst-none",
        "Roll-up review · historical highlights disabled",
        "use_highlighting=[] disables colored highlight bands for every historical roll-up column; red negative-value formatting remains active.",
        rollup_table_hst,
        rollup_power,
        params=["Latest", "5d MA", "20d MA", "3m MA"],
        header="No history highlights",
        use_highlighting=[],
        code='rollup_table_hst(rollup_power, params=["Latest", "5d MA", "20d MA", "3m MA"],\n    header="No history highlights", use_highlighting=[])',
    )
    table(
        "rollup-10d-hst",
        "Roll-up review · 10d historical MA",
        "10d MA is a valid calendar-window label: this card highlights Latest and 10d MA alongside 20d MA. The exact spaced label is shown in the call below.",
        rollup_table_hst,
        rollup_power,
        params=["Latest", "10d MA", "20d MA"],
        header="10d history",
        use_highlighting=["Latest", "10d MA"],
        code='rollup_table_hst(rollup_power, params=["Latest", "10d MA", "20d MA"],\n    header="10d history", use_highlighting=["Latest", "10d MA"])',
    )
    table(
        "rollup-10d-hst-none",
        "Roll-up review · 10d historical MA without highlights",
        "The same 10d MA inputs with use_highlighting=[] provide the direct no-color comparison; red negative-value formatting remains active.",
        rollup_table_hst,
        rollup_power,
        params=["Latest", "10d MA", "20d MA"],
        header="10d history no highlights",
        use_highlighting=[],
        code='rollup_table_hst(rollup_power, params=["Latest", "10d MA", "20d MA"],\n    header="10d history no highlights", use_highlighting=[])',
    )
    table(
        "rollup-share",
        "Power shares · calendar roll-ups",
        "The same numeric z-score rules apply to shares, displayed as percentages. Latest and 20d MA are highlighted by default; other columns can be selected.",
        eu_power_rollup_table,
        rollup_power.div(rollup_power.Total, axis=0),
        header="EU power share",
        format_spec="{:.1%}",
    )
    table(
        "rollup-forecast",
        "Power forecast · current month and calendar roll-ups",
        "Current Month averages all June forecasts. Latest and the MAs reference the final historical row, 18 June; linked charts retain the full series. Latest and 20d MA receive z-score highlights using configurable ±1/±2 SD limits. Other columns, including Current Month, are opt-in.",
        rollup_table_fcst,
        rollup_power,
        params=["Current Month", "Latest", "5d MA", "20d MA", "3m MA", "Y-1 20d MA", "5Y 20d MA"],
        df_hst=rollup_power.loc[:"2025-06-18"],
        today="2025-06-20",
        header="EU power forecast",
        std_limits=(1.0, 2.0),
    )
    table(
        "rollup-highlight-fcst",
        "Roll-up review · selected forecast highlights",
        "The default forecast card highlights Latest and 20d MA. This comparison selects Current Month and 5d MA instead; the exact use_highlighting argument is shown below.",
        rollup_table_fcst,
        rollup_power,
        params=["Current Month", "Latest", "5d MA", "20d MA", "3m MA", "Y-1 20d MA", "5Y 20d MA"],
        df_hst=rollup_power.loc[:"2025-06-18"],
        today="2025-06-20",
        header="Selected forecast highlights",
        std_limits=(1.0, 2.0),
        use_highlighting=["Current Month", "5d MA"],
        code='rollup_table_fcst(rollup_power, df_hst=rollup_power.loc[:"2025-06-18"],\n    params=["Current Month", "Latest", "5d MA", "20d MA", "3m MA", "Y-1 20d MA", "5Y 20d MA"],\n    today="2025-06-20", header="Selected forecast highlights",\n    std_limits=(1.0, 2.0), use_highlighting=["Current Month", "5d MA"])',
    )
    table(
        "rollup-highlight-fcst-none",
        "Roll-up review · forecast highlights disabled",
        "use_highlighting=[] disables colored highlight bands for every forecast roll-up column; red negative-value formatting remains active.",
        rollup_table_fcst,
        rollup_power,
        params=["Current Month", "Latest", "5d MA", "20d MA", "3m MA", "Y-1 20d MA", "5Y 20d MA"],
        df_hst=rollup_power.loc[:"2025-06-18"],
        today="2025-06-20",
        header="No forecast highlights",
        std_limits=(1.0, 2.0),
        use_highlighting=[],
        code='rollup_table_fcst(rollup_power, df_hst=rollup_power.loc[:"2025-06-18"],\n    params=["Current Month", "Latest", "5d MA", "20d MA", "3m MA", "Y-1 20d MA", "5Y 20d MA"],\n    today="2025-06-20", header="No forecast highlights",\n    std_limits=(1.0, 2.0), use_highlighting=[])',
    )
    table(
        "rollup-10d-fcst",
        "Roll-up review · 10d forecast MA",
        "10d MA is a valid calendar-window label: this forecast card highlights Latest and 10d MA alongside Current Month and 20d MA. The exact spaced label is shown in the call below.",
        rollup_table_fcst,
        rollup_power,
        params=["Current Month", "Latest", "10d MA", "20d MA"],
        df_hst=rollup_power.loc[:"2025-06-18"],
        today="2025-06-20",
        header="10d forecast",
        std_limits=(1.0, 2.0),
        use_highlighting=["Latest", "10d MA"],
        code='rollup_table_fcst(rollup_power, df_hst=rollup_power.loc[:"2025-06-18"],\n    params=["Current Month", "Latest", "10d MA", "20d MA"],\n    today="2025-06-20", header="10d forecast",\n    std_limits=(1.0, 2.0), use_highlighting=["Latest", "10d MA"])',
    )
    table(
        "rollup-10d-fcst-none",
        "Roll-up review · 10d forecast MA without highlights",
        "The same 10d MA forecast inputs with use_highlighting=[] provide the direct no-color comparison; red negative-value formatting remains active.",
        rollup_table_fcst,
        rollup_power,
        params=["Current Month", "Latest", "10d MA", "20d MA"],
        df_hst=rollup_power.loc[:"2025-06-18"],
        today="2025-06-20",
        header="10d forecast no highlights",
        std_limits=(1.0, 2.0),
        use_highlighting=[],
        code='rollup_table_fcst(rollup_power, df_hst=rollup_power.loc[:"2025-06-18"],\n    params=["Current Month", "Latest", "10d MA", "20d MA"],\n    today="2025-06-20", header="10d forecast no highlights",\n    std_limits=(1.0, 2.0), use_highlighting=[])',
    )
    chart(
        "rollup-seasonal",
        "Roll-up · history, base and rolling seasonal charts",
        "Full gas-generation history beside seasonal base, 5-day, 20-day and 3-month averages. All windows use calendar time.",
        plot_rollup_seasonal,
        power.Gas,
    )
    add_range_vol_examples(table, chart)
    return tables, charts


CSS = """
*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:90px}
body{margin:0;background:#f4f6f8;color:#182b3a;font:15px/1.5 system-ui,sans-serif}
header,main{max-width:1420px;margin:auto;padding:30px}h1{font-size:38px;margin:8px 0}h2{margin:0;font-size:23px}
p{color:#5a6b79;margin:8px 0 20px}.eyebrow{font-weight:650;color:#176b62;font-size:12px;letter-spacing:.12em}
nav{position:sticky;top:0;z-index:10;background:#fff;border-block:1px solid #dce3e8;padding:12px 30px;display:flex;gap:12px;align-items:center;flex-wrap:wrap}
a{color:#166d83}button,select,.button{font:inherit;border:1px solid #c9d7df;border-radius:6px;background:#fff;color:#234455;padding:7px 12px;text-decoration:none;cursor:pointer}
button[aria-pressed=true]{background:#183d48;color:#fff;border-color:#183d48}select{max-width:340px}
.section-label{display:flex;gap:12px;align-items:center;margin:26px 0 14px}.count{padding:2px 10px;background:#e0ede9;border-radius:20px;font-size:13px}
article{background:#fff;border:1px solid #dce3e8;border-radius:10px;padding:24px;margin-bottom:24px;scroll-margin-top:90px;min-width:0}
.table-scroll{overflow:auto;max-width:100%;padding:6px 0 12px}.table-scroll th,.table-scroll td{padding:4px 7px}
.meta{display:flex;gap:14px;font-size:13px;margin-top:12px}.plot{min-height:430px}.badge{font-size:12px;color:#596b78}
.style-plan{margin-top:12px}.style-plan summary{cursor:pointer;color:#166d83;font-weight:600}
.style-plan pre{max-height:420px;overflow:auto;padding:16px;background:#f4f6f8;border:1px solid #dce3e8;border-radius:6px;font:13px/1.5 monospace}
@media(max-width:750px){header,main{padding:16px}h1{font-size:30px}article{padding:12px}nav{padding:10px}}
"""


def plot_html(figure: go.Figure, key: str) -> str:
    """Fit actual helper output to the gallery width without changing its traces."""
    figure = go.Figure(figure)
    figure.update_layout(width=None, autosize=True, height=max(460, figure.layout.height or 500))
    return figure.to_html(
        full_html=False, include_plotlyjs=False, div_id=f"plot-{key}", config={"responsive": True, "displaylogo": False}
    )


def write_gallery(
    output: Path,
    tables: list[dict[str, Any]],
    charts: list[dict[str, Any]],
    *,
    serve: bool,
) -> None:
    """Export the gallery, style plans and working companion-plot links."""
    output.mkdir(parents=True, exist_ok=True)
    (output / "plots").mkdir(exist_ok=True)
    (output / "styles").mkdir(exist_ok=True)
    (output / "plotly.min.js").write_text(get_plotlyjs(), encoding="utf-8")
    page_start = '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
    head = (
        page_start
        + "<title>Runbook · chart and table gallery</title><style>"
        + CSS
        + '</style><script src="plotly.min.js"></script><body>'
    )
    sections = []
    linked: dict[str, list[go.Figure]] = {item["key"]: [item["figure"]] for item in charts}
    for kind, examples in (("tables", tables), ("charts", charts)):
        cards = []
        for item in examples:
            key = item["key"]
            if kind == "tables":
                payload = item["payload"]
                plan = TableStylePlan.model_validate(payload["style"])
                plan_json = plan.model_dump_json(indent=2, exclude_none=True)
                (output / "styles" / f"{key}.json").write_text(plan_json)
                content = '<div class="table-scroll">' + render_table_html(payload["data"], plan) + "</div>"
                content += (
                    '<details class="style-plan"><summary>View style plan</summary>'
                    f"<pre><code>{escape(plan_json)}</code></pre></details>"
                    f'<div class="meta"><a href="styles/{key}.json" download="{key}.json">Download style plan JSON</a></div>'
                )
                if serve:
                    content += f'<p><a href="/renderers/?table={key}">Compare HTML / native Dash</a></p>'
                for name, figure in zip(
                    payload.get("plot_names", []), payload.get("plots", []), strict=bool(payload.get("plot_names"))
                ):
                    linked[name] = [figure]
                if payload.get("all_plots_name"):
                    linked[payload["all_plots_name"]] = payload["plots"]
            else:
                content = '<div class="plot">' + plot_html(item["figure"], key) + "</div>"
            if item.get("code"):
                content = f'<pre style="overflow:auto">{escape(item["code"])}</pre>' + content
            cards.append(
                f'<article id="{key}"><h2>{escape(item["title"])}</h2><p>{escape(item["description"])}</p>'
                f'<p class="badge">Template: <code>{escape(item["template"])}</code></p>{content}</article>'
            )
        sections.append(
            f'<section data-kind="{kind}"><div class="section-label"><h2>{kind.title()}</h2><span class="count">{len(examples)} examples</span></div>'
            + "".join(cards)
            + "</section>"
        )
    select = (
        '<select aria-label="Jump to an example" onchange="filterGallery(\'all\');location.hash=this.value"><option value="">Jump to an example…</option>'
        + "".join(f'<option value="{item["key"]}">{escape(item["title"])}</option>' for item in [*tables, *charts])
        + "</select>"
    )
    renderer_link = '<a class="button" href="/renderers/">Compare table renderers ↗</a>' if serve else ""
    navigation = (
        "<nav>"
        + "".join(
            f'<button onclick="filterGallery(\'{kind}\')" data-filter="{kind}" aria-pressed="{str(kind == "all").lower()}">{label}</button>'
            for kind, label in (("all", "All examples"), ("tables", "Tables"), ("charts", "Charts"))
        )
        + select
        + renderer_link
        + "</nav>"
    )
    script = """<script>
function filterGallery(kind){
 document.querySelectorAll('[data-kind]').forEach(s=>s.hidden=kind!=='all'&&s.dataset.kind!==kind);
 document.querySelectorAll('[data-filter]').forEach(b=>b.setAttribute('aria-pressed',b.dataset.filter===kind));
 requestAnimationFrame(()=>document.querySelectorAll('.js-plotly-plot').forEach(p=>{if(p.offsetParent)Plotly.Plots.resize(p)}));
}
</script>"""
    (output / "index.html").write_text(
        head
        + f'<header><div class="eyebrow">RUNBOOK CORE · PREVIEW GALLERY</div><h1>Charts & table templates</h1><p>{len(tables)} table examples · {len(charts)} chart examples · Synthetic data<br>All columns are centered by default. Click table links, hover charts, zoom and toggle legend entries.</p></header>'
        + navigation
        + "<main>"
        + "".join(sections)
        + "</main>"
        + script
        + "</body></html>",
        encoding="utf-8",
    )
    for name, figures in linked.items():
        if len(figures) == 1:
            figures[0].write_json(output / "plots" / f"{name}.json")
        body = "".join(plot_html(fig, f"{name}-{i}") for i, fig in enumerate(figures))
        (output / "plots" / f"{name}.html").write_text(
            page_start
            + '<title>Runbook · linked plots</title><script src="../plotly.min.js"></script><body style="font-family:system-ui;margin:24px"><a href="../index.html">← Back to gallery</a>'
            + body
            + "</body></html>"
        )
    print(f"Gallery: {output / 'index.html'} ({len(tables)} tables, {len(charts)} charts)", flush=True)


def serve_gallery(output: Path, tables: list[dict[str, Any]], port: int) -> None:
    """Serve the bundle and a live comparison using the production renderers."""
    import dash_ag_grid as dag
    from dash import Dash, Input, Output, dcc, html
    from flask import Flask, redirect
    from runbook.core.pdl.models import PDLTableBlock
    from runbook.core.storage import BlobStore
    from runbook.sdk.extensions.dash.renderer import _build_ag_grid, _build_native_table
    from runbook.sdk.extensions.dash.tables import ag_grid_default_col_def, register_ag_grid_components
    from werkzeug.serving import make_server

    server = Flask(__name__, static_folder=str(output), static_url_path="/gallery")
    server.add_url_rule("/", "gallery", lambda: redirect("/gallery/index.html"))
    app = Dash(__name__, server=server, url_base_pathname="/renderers/")  # type: ignore[arg-type]
    register_ag_grid_components(app)
    ctx = SimpleNamespace(_artifact_store=BlobStore(f"file:{output}"), _artifact_prefix="")
    plot_refs = {path.stem: f"plots/{path.name}" for path in (output / "plots").glob("*.json")}
    examples = {item["key"]: item for item in tables}
    app.layout = html.Main(
        [
            html.A("← Back to the complete gallery", href="/gallery/index.html"),
            html.H1("Compare table renderers"),
            html.P(
                "The same data and style plan in static HTML, native Dash, and AG Grid. All observations are synthetic."
            ),
            dcc.Location(id="preview-location", refresh=False),
            dcc.Dropdown(
                id="table-choice",
                options=[{"label": x["title"], "value": x["key"]} for x in tables],
                value="price-range" if "price-range" in examples else tables[0]["key"],
                clearable=False,
            ),
            html.Div(id="table-comparison"),
        ],
        style={"fontFamily": "system-ui", "padding": "24px", "maxWidth": "1450px", "margin": "auto"},
    )

    @app.callback(Output("table-choice", "value"), Input("preview-location", "search"))
    def select_example(search: str | None) -> str:
        key = parse_qs((search or "").lstrip("?")).get("table", [None])[0]
        if isinstance(key, str) and key in examples:
            return key
        return "price-range" if "price-range" in examples else tables[0]["key"]

    @app.callback(Output("table-comparison", "children"), Input("table-choice", "value"))
    def comparison(key: str) -> list[Any]:
        item = examples[key]
        payload = item["payload"]
        frame = payload["data"]
        block = PDLTableBlock(name=key, data_ref=f"{key}.parquet", style_ref=f"styles/{key}.json", row=1, col=1)

        def route(kind: str, value: str) -> str | None:
            return f"/gallery/plots/{value}.html" if kind == "plot" else None

        native = _build_native_table(frame, block, "native-table", ctx, route, plot_refs)
        grid = _build_ag_grid(frame, block, ctx, route, plot_refs)
        return [
            html.P(item["description"]),
            html.Pre(item["code"], style={"overflow": "auto"}) if item.get("code") else None,
            html.Details(
                [
                    html.Summary("View style plan", style={"cursor": "pointer", "color": "#166d83"}),
                    html.Pre(
                        TableStylePlan.model_validate(payload["style"]).model_dump_json(indent=2, exclude_none=True),
                        style={
                            "maxHeight": "420px",
                            "overflow": "auto",
                            "padding": "16px",
                            "background": "#f4f6f8",
                            "border": "1px solid #dce3e8",
                            "borderRadius": "6px",
                            "font": "13px/1.5 monospace",
                        },
                    ),
                ],
                style={"marginBottom": "12px"},
            ),
            html.A("Download style plan JSON", href=f"/gallery/styles/{key}.json", download=f"{key}.json"),
            html.H2("Static HTML"),
            html.Iframe(
                srcDoc='<base href="/gallery/">' + render_table_html(frame, payload["style"]),
                style={"width": "100%", "height": "300px", "border": "0"},
            ),
            html.H2("Native Dash"),
            html.Div(native, style={"overflowX": "auto"}),
            html.H2("AG Grid"),
            dag.AgGrid(
                rowData=grid.row_data,
                columnDefs=grid.column_defs,
                defaultColDef=ag_grid_default_col_def(),
                dashGridOptions={"suppressFieldDotNotation": True},
                style={"height": "380px", "width": "100%"},
            ),
            html.Div(grid.footer) if grid.footer is not None else None,
        ]

    httpd = make_server("127.0.0.1", port, server, threaded=True)
    print(f"PREVIEW_URL=http://127.0.0.1:{httpd.server_port}/", flush=True)
    httpd.serve_forever()


def main() -> None:
    """Generate an offline gallery, optionally serving live renderer comparisons."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("/tmp/runbook-gallery"))
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    tables, charts = build_examples()
    write_gallery(output, tables, charts, serve=args.serve)
    if args.serve:
        serve_gallery(output, tables, args.port)


if __name__ == "__main__":
    main()
