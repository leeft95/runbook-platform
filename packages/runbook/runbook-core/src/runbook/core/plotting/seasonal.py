from __future__ import annotations

import datetime as dt
import typing as tp

import pandas as pd
import plotly
from runbook.core.plotting.graphly import GraphlyPlotter, PlotlyPlotDef, PlotType
from runbook.core.timeseries.transforms import ts_by_year


def _as_dummy_cutoff(dts: pd.DatetimeIndex, dash_from: dt.datetime) -> pd.Timestamp:
    """Map a real date to the dummy plotting year used by ts_by_year."""
    return pd.Timestamp(year=int(dts[0].year), month=dash_from.month, day=dash_from.day)


def _row_heights_for_rows(rows: int) -> list[float] | None:
    """Handle row heights for rows."""
    match rows:
        case 1:
            return [1.0]
        case 2:
            return [0.7, 0.3]
        case 3:
            return [0.5, 0.3, 0.2]
        case _:
            return None


def plot_seasonal(
    df: pd.DataFrame,
    frequency: str = "D",
    start_day: int | None = 1,
    start_month: int | None = 1,
    end_day: int | None = 31,
    end_month: int | None = 12,
    column: tp.Hashable | None = None,
    over_year: bool = False,
    title: str | None = None,
    width: int = 900,
    height: int = 600,
    show_legend: bool = False,
    hovertemplate: str | None = None,
    dash_from: dt.datetime | None = None,
    dash_name: str = "Forecast",
    df_ytd: bool = False,
    ytd: bool = False,
    vs_average: bool = True,
    ytd_diff: bool = False,
    ytd_cum_sum: bool = False,
    shared_xaxes: bool = True,
    tickformat: str | None = "%b",
    dtick: str | int | float | None = "M1",
    use_rangebreaks: bool = True,
    holiday_countries: list[str] | None = None,
    exclude_years: tp.List[int] | None = None,
    **kwargs: tp.Any,
) -> plotly.graph_objs._figure.Figure:
    """Plot a seasonal chart with optional comparison and cumulative subplots."""
    if not isinstance(df, pd.DataFrame):
        raise TypeError("df must be a pandas DataFrame.")
    if not isinstance(df.index, pd.DatetimeIndex):
        raise TypeError("df index must be a pandas DatetimeIndex.")

    df_by_year = ts_by_year(
        df,
        frequency=frequency,
        start_day=start_day,
        start_month=start_month,
        end_day=end_day,
        end_month=end_month,
        column=column,
        over_year=over_year,
        dummy_date_index=True,
    )
    if df_by_year.empty:
        raise ValueError("No seasonal data available after ts_by_year transformation.")

    if exclude_years:
        df_by_year = df_by_year.drop(columns=exclude_years, errors="ignore")

    current_year = kwargs.get("current_year", int(df_by_year.columns[-1]))
    if current_year not in df_by_year.columns:
        raise KeyError(f"current_year {current_year!r} not found in seasonal data.")

    if df_ytd:
        df_by_year = df_by_year.cumsum(axis=0)

    dts = df_by_year.index
    if not isinstance(dts, pd.DatetimeIndex):
        raise TypeError("Expected ts_by_year(dummy_date_index=True) to return a DatetimeIndex.")
    history = df_by_year.drop(columns=[current_year], errors="ignore")
    avg_5y = history.iloc[:, -5:].mean(axis=1) if not history.empty else None
    prev_year = int(history.columns[-1]) if not history.empty else None

    dash_cutoff = _as_dummy_cutoff(dts, dash_from) if dash_from is not None else None
    dash_year = dash_from.year if dash_from is not None else None
    forecast_year_colors = ["black", "red", "blue", "green", "orange"]
    forecast_color_by_year: dict[int, str] = {}
    if dash_year is not None:
        forecast_years = sorted(int(y) for y in df_by_year.columns if int(y) >= dash_year)
        for i, forecast_year in enumerate(forecast_years):
            forecast_color_by_year[forecast_year] = forecast_year_colors[i % len(forecast_year_colors)]

    seasonal_data = pd.DataFrame(index=dts)
    series_styles: dict[str, dict[str, tp.Any]] = {}

    for year_raw in df_by_year.columns:
        year = int(year_raw)

        base_name = str(year)
        base_style: dict[str, tp.Any] = {}
        if year == current_year:
            base_style = {"line": {"color": "black", "width": 2}}
        elif prev_year is not None and year == prev_year:
            base_style = {"line": {"color": "blue", "width": 1}}
        series = df_by_year[year]

        if dash_cutoff is None or dash_year is None or year < dash_year:
            seasonal_data[base_name] = series
            if base_style:
                series_styles[base_name] = base_style
            continue

        if year > dash_year:
            fcst_name = f"{year}_{dash_name}"
            seasonal_data[fcst_name] = series
            series_styles[fcst_name] = {
                "line": {
                    "color": forecast_color_by_year.get(year, forecast_year_colors[0]),
                    "width": 2,
                    "dash": "dash",
                }
            }
            continue

        hist_series = series.where(dts < dash_cutoff)
        fcst_series = series.where(dts >= dash_cutoff)

        if hist_series.notna().any():
            seasonal_data[base_name] = hist_series
            if base_style:
                series_styles[base_name] = base_style

        if fcst_series.notna().any():
            fcst_name = f"{year}_{dash_name}"
            seasonal_data[fcst_name] = fcst_series
            series_styles[fcst_name] = {
                "line": {
                    "color": forecast_color_by_year.get(year, forecast_year_colors[0]),
                    "width": 2,
                    "dash": "dash",
                }
            }

    subplot_frames: list[pd.DataFrame] = [seasonal_data]

    if vs_average:
        data_vs_avg = pd.DataFrame(index=dts)
        if avg_5y is not None and not avg_5y.empty:
            fivey_name = "Cur Yr vs 5y Avg"
            data_vs_avg[fivey_name] = df_by_year[current_year] - avg_5y
            series_styles[fivey_name] = {"line": {"color": "black", "width": 1}}
        if prev_year is not None:
            y1_name = "Cur Yr vs Y-1"
            data_vs_avg[y1_name] = df_by_year[current_year] - df_by_year[prev_year]
            series_styles[y1_name] = {"line": {"color": "black", "width": 1, "dash": "dash"}}
        if not data_vs_avg.empty:
            subplot_frames.append(data_vs_avg)

    if ytd or ytd_cum_sum:
        data_ytd = pd.DataFrame(index=dts)

        if ytd:
            ytd_name = "YTD cumulative change"
            if ytd_diff:
                data_ytd[ytd_name] = df_by_year[current_year].diff().cumsum()
            else:
                data_ytd[ytd_name] = df_by_year[current_year].cumsum()
            series_styles[ytd_name] = {"line": {"color": "black", "width": 1}}

        if ytd_cum_sum:
            if prev_year is not None:
                cum_name = "Cum Cur Yr vs Y-1"
                cum_vs = (df_by_year[current_year] - df_by_year[prev_year]).cumsum()
            elif avg_5y is not None and not avg_5y.empty:
                cum_name = "Cum Cur Yr vs 5y Avg"
                cum_vs = (df_by_year[current_year] - avg_5y).cumsum()
            else:
                cum_name = "YTD cumulative change"
                cum_vs = df_by_year[current_year].cumsum()

            data_ytd[cum_name] = cum_vs
            if cum_name == "Cum Cur Yr vs Y-1":
                series_styles[cum_name] = {
                    "line": {"color": "grey", "width": 1, "dash": "dash"},
                    "fill": "tozeroy",
                }
            else:
                series_styles[cum_name] = {"line": {"color": "grey", "width": 1}}

        if not data_ytd.empty:
            subplot_frames.append(data_ytd)

    rows = len(subplot_frames)
    if rows > 1:
        vertical_spacing = 0.02
    else:
        vertical_spacing = None
    plot_defs = [
        PlotlyPlotDef(
            data=panel_df,
            row=row,
            col=1,
            plot_type=PlotType.line,
            hovertemplate=hovertemplate,
            tickformat=tickformat,
            dtick=dtick,
            use_rangebreaks=use_rangebreaks,
            holiday_countries=holiday_countries,
            show_legend=show_legend,
            series_styles=series_styles,
        )
        for row, panel_df in enumerate(subplot_frames, start=1)
    ]
    fig = GraphlyPlotter(
        width=width,
        height=height,
        n_rows=rows,
        n_cols=1,
        auto_layout=False,
        row_heights=_row_heights_for_rows(rows),
        shared_xaxes=shared_xaxes,
        vertical_spacing=vertical_spacing,
        tickformat=tickformat,
        dtick=dtick,
        use_rangebreaks=use_rangebreaks,
        holiday_countries=holiday_countries,
    ).plot(plot_defs, title=title)

    fig.update_layout(margin={"l": 50, "r": 20, "t": 60, "b": 50})
    fig.update_yaxes(title_text=kwargs.get("y_axis_title", ""), row=1, col=1)
    fig.update_xaxes(title_text="Date", row=rows, col=1)
    return fig


def plot_cot(
    data: pd.DataFrame,
    columns: list[list[str]] | None,
    title: str,
    plot_titles: list[str],
    freq: str = "W",
    start: dt.datetime | None = None,
    exclude_years: tp.List[int] | None = None,
) -> plotly.graph_objs._figure.Figure:
    """Build a 2x3 COT figure:
    - Top row: seasonal position overlays + current-year price (secondary y)
    - Bottom row: current-year position/oi + historical oi min/max band + CTA LN4 (secondary y)
    """
    if not isinstance(data, pd.DataFrame):
        raise TypeError("data must be a pandas DataFrame.")
    if not isinstance(data.index, pd.DatetimeIndex):
        raise TypeError("data index must be a pandas DatetimeIndex.")
    if len(plot_titles) != 3:
        raise ValueError("plot_titles must contain exactly 3 titles.")

    def _normalize_panel_specs(specs: list[list[str]] | None) -> list[dict[str, str | None]]:
        # Three permutations: Net / Long / Short. Internal is optional.
        """Normalize panel specs."""
        defaults = [
            ["Net", "PX_LAST", "Net OI", "Internal"],
            ["Long", "PX_LAST", "Long OI", "Internal"],
            ["Short", "PX_LAST", "Short OI", "Internal"],
        ]
        raw = defaults if specs is None else specs
        if len(raw) != 3:
            raise ValueError("columns must contain exactly three panel permutations.")

        out: list[dict[str, str | None]] = []
        for panel_i, panel in enumerate(raw):
            if not isinstance(panel, list):
                raise TypeError(f"columns[{panel_i}] must be a list.")
            if len(panel) not in {3, 4}:
                raise ValueError(f"columns[{panel_i}] must be [main, PX_LAST, oi] or [main, PX_LAST, oi, Internal].")

            main_col, price_col, oi_col = panel[0], panel[1], panel[2]
            internal_col = panel[3] if len(panel) == 4 else None
            for required in (main_col, price_col, oi_col):
                if required not in data.columns:
                    raise KeyError(f"Required column {required!r} in panel {panel_i} not found in data.")
            if internal_col is not None and internal_col not in data.columns:
                internal_col = None
            out.append({"main": main_col, "price": price_col, "oi": oi_col, "internal": internal_col})
        return out

    panel_specs = _normalize_panel_specs(columns)
    n_cols = len(panel_specs)
    n_rows = 2
    working = data.sort_index()
    if start is not None:
        working = working.loc[working.index >= start]
    if working.empty:
        raise ValueError("No rows left after applying start filter.")

    series_styles: dict[str, dict[str, tp.Any]] = {
        "price": {
            "line": {"color": "black", "width": 1.5, "dash": "dash"},
            "secondary_y": True,
        },
        "CTA LN4": {
            "line": {"color": "blue", "width": 1.6},
            "mode": "lines+markers",
            "secondary_y": True,
        },
        "Net/OI": {"line": {"color": "red", "width": 1.6}, "mode": "lines+markers"},
        "Max": {"line": {"color": "lightgrey", "width": 1}},
        "Min": {
            "line": {"color": "lightgrey", "width": 1},
            "fill": "tonexty",
            "fillcolor": "rgba(180, 180, 180, 0.35)",
        },
    }
    plot_defs: list[PlotlyPlotDef] = []

    for panel_i, spec in enumerate(panel_specs):
        main_col = tp.cast(str, spec["main"])
        price_col = tp.cast(str, spec["price"])
        oi_col = tp.cast(str, spec["oi"])
        internal_col = tp.cast(str | None, spec["internal"])

        main_by_year = ts_by_year(working[main_col], frequency=freq, dummy_date_index=True)
        if main_by_year.empty:
            raise ValueError(f"No seasonal data for panel {panel_i + 1} ({main_col}).")
        price_by_year = ts_by_year(working[price_col], frequency=freq, dummy_date_index=True)
        oi_by_year = ts_by_year(working[oi_col], frequency=freq, dummy_date_index=True)
        if exclude_years:
            main_by_year = main_by_year.drop(columns=exclude_years, errors="ignore")
            price_by_year = price_by_year.drop(columns=exclude_years, errors="ignore")
            oi_by_year = oi_by_year.drop(columns=exclude_years, errors="ignore")

        current_year = int(main_by_year.columns[-1])

        # Top row dataframe: year lines + current-year price.
        top_df = pd.DataFrame(index=main_by_year.index)
        for year_raw in main_by_year.columns:
            year = int(year_raw)
            top_df[str(year)] = main_by_year[year]
            if year == current_year:
                series_styles[str(year)] = {"line": {"color": "red", "width": 2}, "mode": "lines+markers"}
        if current_year in price_by_year.columns:
            top_df["price"] = price_by_year[current_year].reindex(top_df.index)

        # Bottom row dataframe: historical OI band + current-year OI + optional internal.
        bottom_df = pd.DataFrame(index=oi_by_year.index)
        oi_hist = oi_by_year.drop(columns=[current_year], errors="ignore")
        bottom_df["Max"] = oi_hist.max(axis=1) if not oi_hist.empty else oi_by_year[current_year]
        bottom_df["Min"] = oi_hist.min(axis=1) if not oi_hist.empty else oi_by_year[current_year]
        if current_year in oi_by_year.columns:
            net_oi_current = oi_by_year[current_year].reindex(bottom_df.index)
            if "Short" in main_col:
                net_oi_current = net_oi_current.iloc[::-1].reset_index(drop=True)
                net_oi_current.index = bottom_df.index
            bottom_df["Net/OI"] = net_oi_current

        if internal_col is not None:
            internal_by_year = ts_by_year(working[internal_col], frequency=freq, dummy_date_index=True)
            if current_year in internal_by_year.columns:
                internal_current = internal_by_year[current_year].reindex(bottom_df.index)
                bottom_df["CTA LN4"] = internal_current

        plot_defs.append(
            PlotlyPlotDef(
                data=top_df,
                title=plot_titles[panel_i],
                row=1,
                col=panel_i + 1,
                plot_type=PlotType.line,
                show_legend=True,
                tickformat="%b",
                dtick="M1",
                use_rangebreaks=False,
                series_styles=series_styles,
            )
        )
        plot_defs.append(
            PlotlyPlotDef(
                data=bottom_df,
                row=2,
                col=panel_i + 1,
                plot_type=PlotType.line,
                show_legend=True,
                tickformat="%b",
                dtick="M1",
                use_rangebreaks=False,
                series_styles=series_styles,
            )
        )

    fig = GraphlyPlotter(
        width=750 * n_cols,
        height=280 * n_rows,
        n_rows=n_rows,
        n_cols=n_cols,
        auto_layout=False,
        shared_xaxes=True,
        vertical_spacing=0.02,
        horizontal_spacing=0.08,
        tickformat="%b",
        dtick="M1",
        use_rangebreaks=False,
        legend_groups=True,
    ).plot(plot_defs, title=title)
    # Bottom center x-axis title only.
    fig.update_xaxes(title_text="Date", row=n_rows, col=(n_cols + 1) // 2)
    for col in range(1, n_cols + 1):
        fig.update_yaxes(title_text="Contracts", row=1, col=col, secondary_y=False)
        fig.update_yaxes(title_text="Price", row=1, col=col, secondary_y=True)
        fig.update_yaxes(title_text="Net/OI", row=n_rows, col=col, secondary_y=False)
        fig.update_yaxes(title_text="CTA LN4", row=n_rows, col=col, secondary_y=True)
    return fig
