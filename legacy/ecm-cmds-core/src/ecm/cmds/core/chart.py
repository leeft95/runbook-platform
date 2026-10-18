import datetime as dt
import typing as tp

import ecm.cmds.core.time_series as ts
import holidays
import numpy as np
import pandas as pd
import plotly as py
import plotly.graph_objects as go
import statsmodels.api as sm
from ecm.cmds.core.plotting_lib import PlottingLib
from ecm.cmds.core.utils import convert_path_to_linux
from plotly.subplots import make_subplots
from pyg_base import dt as pygdt


def _generate_holiday_dates(start_year, end_year):
    common_dates = []
    for year in range(start_year, end_year + 1):
        common_dates.append(f"{year}-12-25")  # Christmas
        common_dates.append(f"{year}-12-26")  # Boxing Day
        common_dates.append(f"{year}-01-01")  # New Year's Day

    us_holidays = holidays.UnitedStates(years=range(start_year, end_year + 1))
    uk_holidays = holidays.UnitedKingdom(years=range(start_year, end_year + 1))
    holiday_dates_us = [d.strftime("%Y-%m-%d") for d in us_holidays.keys()]
    holiday_dates_uk = [d.strftime("%Y-%m-%d") for d in uk_holidays.keys()]

    dates = list(set(common_dates + holiday_dates_us + holiday_dates_uk))
    return dates


def _add_charts(
    data,
    fig,
    mode,
    highlight_dict,
    showlegend,
    title,
    hovertemplate,
    column_titles,
    row,
    col,
    secondary_y,
):
    for i in data.columns:
        if column_titles is None:
            column_titles = [title]
        if highlight_dict is not None:
            high_dict = highlight_dict.copy()
            if i in highlight_dict.keys():
                line_mode = high_dict[i].pop("mode", "lines")
                fill = high_dict[i].pop("fill", None)
                fillcolor = high_dict[i].pop("fillcolor", None)
                hovertemplate = high_dict[i].pop("hovertemplate", "%{x|%b/%d} %{y}")
                if line_mode != "bars":
                    trace = go.Scatter(
                        x=data.index,
                        y=data[i],
                        showlegend=showlegend,
                        name=i,
                        mode=line_mode,
                        line=high_dict[i],
                        hovertemplate=hovertemplate,
                        fillcolor=fillcolor,
                        fill=fill,
                        legendgroup=i,
                        connectgaps=True,
                    )

                else:
                    if "color" in high_dict[i].keys():
                        marker_color = high_dict[i].pop("color")
                    else:
                        marker_color = None
                    if "marker" in high_dict[i].keys():
                        marker = high_dict[i].pop("marker")
                    else:
                        marker = None
                    if "showlegend" in high_dict[i].keys():
                        showlegend_bar = high_dict[i].pop("showlegend")
                    else:
                        showlegend_bar = showlegend
                    if "legendonly" in high_dict[i].keys():
                        visible = "legendonly" if high_dict[i].pop("legendonly") else True
                    else:
                        visible = True
                    if "blabel" in high_dict[i].keys():
                        if not isinstance(high_dict[i]["blabel"], dict):
                            high_dict[i]["blabel"] = {}
                        textposition = high_dict[i].get("blabel", {}).pop("textposition", "outside")
                        textformat = high_dict[i].get("blabel", {}).pop("textformat", "%{text:.2s}")
                        high_dict[i].pop("blabel")
                        text = data[i]
                    else:
                        text = None
                        textposition = None
                        textformat = None
                    trace = go.Bar(
                        x=data.index if visible != "legendonly" else [None],
                        y=data[i] if visible != "legendonly" else [None],
                        showlegend=showlegend_bar,
                        name=i,
                        legendgroup=i,
                        marker_color=marker_color,
                        marker=marker,
                        hovertemplate=hovertemplate,
                        visible=True,
                        textposition=textposition,
                        texttemplate=textformat,
                        text=text,
                    )
                fig.add_trace(trace=trace, secondary_y=secondary_y, row=row, col=col)
            else:
                fig.add_trace(
                    go.Scatter(
                        x=data.index,
                        y=data[i],
                        showlegend=showlegend,
                        name=i,
                        mode=mode,
                        line=dict(width=1),
                        hovertemplate=hovertemplate,
                        legendgroup=i,
                        connectgaps=True,
                    ),
                    secondary_y=secondary_y,
                    row=row,
                    col=col,
                )
        else:
            fig.add_trace(
                go.Scatter(
                    x=data.index,
                    y=data[i],
                    showlegend=showlegend,
                    name=i,
                    line=dict(width=1),
                    mode=mode,
                    legendgroup=i,
                    hovertemplate=hovertemplate,
                    connectgaps=True,
                ),
                secondary_y=secondary_y,
                row=row,
                col=col,
            )
        if not data.empty and len(data.index) >= 3:
            try:
                inferred_freq = pd.infer_freq(data.index)
                if inferred_freq is None or any(inferred_freq.endswith(x) for x in ["D", "B"]):
                    try:
                        data.index = pd.to_datetime(data.index)
                        dates = _generate_holiday_dates(min(data.index.year), max(data.index.year))
                        fig.update_xaxes(
                            rangebreaks=[
                                dict(bounds=["sat", "sun" if line_mode == "bars" else "mon"]),
                                dict(values=dates),
                            ],
                            row=row,
                            col=col,
                        )
                    except Exception:
                        pass
            except Exception:
                pass
    return fig, column_titles


def _line_chart(data, title=None, **kwargs):
    """
    Plotly line chart
    """
    x_axis_title = kwargs.get("x_axis_title", None)
    y_axis_title = kwargs.get("y_axis_title", None)
    p1y2_axis_title = kwargs.get("p1y2_axis_title", None)
    p2y1_axis_title = kwargs.get("p2y1_axis_title", None)
    p2y2_axis_title = kwargs.get("p2y2_axis_title", None)
    p3y1_axis_title = kwargs.get("p3y1_axis_title", None)
    p3y2_axis_title = kwargs.get("p3y2_axis_title", None)
    y_axis_reversed = kwargs.get("y_axis_reversed", False)
    p1y2_axis_reversed = kwargs.get("p1y2_axis_reversed", False)
    p2y1_axis_reversed = kwargs.get("p2y1_axis_reversed", False)
    p2y2_axis_reversed = kwargs.get("p2y2_axis_reversed", False)
    p3y1_axis_reversed = kwargs.get("p3y1_axis_reversed", False)
    p3y2_axis_reversed = kwargs.get("p3y2_axis_reversed", False)
    file_path = kwargs.get("file_path", None)
    hovertemplate = kwargs.get("hovertemplate", "%{x|%b/%d} %{y}")
    highlight_dict = kwargs.get("highlight_dict", None)
    highlight_dict_c2 = kwargs.get("highlight_dict_c2", None)
    data_p1y2 = kwargs.get("data_p1y2", None)
    data_p2y1 = kwargs.get("data_p2y1", None)
    data_p2y2 = kwargs.get("data_p2y2", None)
    data_p3y1 = kwargs.get("data_p3y1", None)
    data_p3y2 = kwargs.get("data_p3y2", None)
    data_p1y1c2 = kwargs.get("data_p1y1c2", None)
    data_p1y2c2 = kwargs.get("data_p1y2c2", None)
    data_p2y1c2 = kwargs.get("data_p2y1c2", None)
    data_p2y2c2 = kwargs.get("data_p2y2c2", None)
    data_p3y1c2 = kwargs.get("data_p3y1c2", None)
    data_p3y2c2 = kwargs.get("data_p3y2c2", None)
    data_c2 = kwargs.get("data_c2", None)
    subplots = kwargs.get("subplots", 1)
    secondary_y = kwargs.get("secondary_y", False)
    col = kwargs.get("col", 1)
    column_titles = kwargs.get("column_titles", None)
    showlegend = kwargs.get("showlegend", True)
    showlegend_c2 = kwargs.get("showlegend_c2", False)
    width = kwargs.get("width", 900)
    height = kwargs.get("height", 600)
    tickformat = kwargs.get("tickformat", "%b")
    show_grid_c2 = kwargs.get("show_grid_c2", False)
    show_grid_c1 = kwargs.get("show_grid_c1", False)
    y_range = kwargs.get("y_range", None)
    mode = kwargs.get("mode", None)
    bar_mode = kwargs.get("bar_mode", None)

    if isinstance(subplots, int):
        if subplots == 1:
            subplots = [1]
        if subplots == 2:
            subplots = [0.7, 0.3]
        elif subplots == 3:
            subplots = [0.6, 0.2, 0.2]

    if isinstance(secondary_y, list):
        if len(secondary_y) == 1:
            secondary_y = [[{"secondary_y": secondary_y[0]}]] * len(subplots)
        else:
            secondary_y = [[{"secondary_y": secondary_y[i]}] for i in secondary_y]
    else:
        secondary_y = [[{"secondary_y": secondary_y}]] * len(subplots)

    if col == 2:
        raise NotImplementedError("Unrecoverable chart.py:237 two-column setup statement")
        if data_c2 is None:
            second_col = secondary_y
        else:
            second_col = [{"rowspan": len(subplots)}] + [None] * (len(subplots) - 1)
        if data_p2y1c2 is not None and data_p2y1 is None:
            second_col = [{"rowspan": len(subplots)}] + [None] * (len(subplots) - 1)
            secondary_y = [list(a) for a in zip(second_col, secondary_y)]
        else:
            secondary_y = [list(a) for a in zip(secondary_y, second_col)]

    if len(subplots) == 1 and col == 1:
        fig = make_subplots(specs=secondary_y)
    else:
        fig = make_subplots(
            rows=len(subplots),
            cols=col,
            row_heights=subplots,
            shared_xaxes=True,
            vertical_spacing=0.02,
            specs=secondary_y,
            column_titles=column_titles,
            horizontal_spacing=0.08,
        )
    fig, column_titles = _add_charts(
        data,
        fig,
        mode,
        highlight_dict,
        showlegend,
        title,
        hovertemplate,
        column_titles,
        row=1,
        col=1,
        secondary_y=False,
    )
    if data_p1y2 is not None:
        fig, column_titles = _add_charts(
            data_p1y2,
            fig,
            mode,
            highlight_dict,
            showlegend,
            title,
            hovertemplate,
            column_titles,
            row=1,
            col=1,
            secondary_y=True,
        )
    if data_p2y1 is not None:
        fig, column_titles = _add_charts(
            data_p2y1,
            fig,
            mode,
            highlight_dict,
            showlegend,
            title,
            hovertemplate,
            column_titles,
            row=2,
            col=1,
            secondary_y=False,
        )
    if data_p2y2 is not None:
        fig, column_titles = _add_charts(
            data_p2y2,
            fig,
            mode,
            highlight_dict,
            showlegend,
            title,
            hovertemplate,
            column_titles,
            row=2,
            col=1,
            secondary_y=True,
        )
    if data_p3y1 is not None:
        fig, column_titles = _add_charts(
            data_p3y1,
            fig,
            mode,
            highlight_dict,
            showlegend,
            title,
            hovertemplate,
            column_titles,
            row=3,
            col=1,
            secondary_y=False,
        )
    if data_p3y2 is not None:
        fig, column_titles = _add_charts(
            data_p3y2,
            fig,
            mode,
            highlight_dict,
            showlegend,
            title,
            hovertemplate,
            column_titles,
            row=3,
            col=1,
            secondary_y=True,
        )
    if data_p1y1c2 is not None:
        fig, column_titles = _add_charts(
            data_p1y1c2,
            fig,
            mode,
            highlight_dict_c2,
            showlegend_c2,
            title,
            hovertemplate,
            column_titles,
            row=1,
            col=2,
            secondary_y=False,
        )
    if data_p1y2c2 is not None:
        fig, column_titles = _add_charts(
            data_p1y2c2,
            fig,
            mode,
            highlight_dict_c2,
            showlegend_c2,
            title,
            hovertemplate,
            column_titles,
            row=1,
            col=2,
            secondary_y=True,
        )
    if data_p2y1c2 is not None:
        fig, column_titles = _add_charts(
            data_p2y1c2,
            fig,
            mode,
            highlight_dict_c2,
            showlegend_c2,
            title,
            hovertemplate,
            column_titles,
            row=2,
            col=2,
            secondary_y=False,
        )
    if data_p2y2c2 is not None:
        fig, column_titles = _add_charts(
            data_p2y2c2,
            fig,
            mode,
            highlight_dict_c2,
            showlegend_c2,
            title,
            hovertemplate,
            column_titles,
            row=2,
            col=2,
            secondary_y=True,
        )
    if data_p3y1c2 is not None:
        fig, column_titles = _add_charts(
            data_p3y1c2,
            fig,
            mode,
            highlight_dict_c2,
            showlegend_c2,
            title,
            hovertemplate,
            column_titles,
            row=3,
            col=2,
            secondary_y=False,
        )
    if data_p3y2c2 is not None:
        fig, column_titles = _add_charts(
            data_p3y2c2,
            fig,
            mode,
            highlight_dict_c2,
            showlegend_c2,
            title,
            hovertemplate,
            column_titles,
            row=3,
            col=2,
            secondary_y=True,
        )
    if data_c2 is not None:
        fig, column_titles = _add_charts(
            data_c2,
            fig,
            mode,
            highlight_dict_c2,
            showlegend_c2,
            title,
            hovertemplate,
            column_titles,
            row=1,
            col=2,
            secondary_y=False,
        )

    if y_axis_title is not None:
        fig.update_yaxes(title_text=y_axis_title, row=1, col=1, secondary_y=False)
    if p1y2_axis_title is not None:
        fig.update_yaxes(title_text=p1y2_axis_title, row=1, col=1, secondary_y=True, showgrid=False)
    if p2y1_axis_title is not None:
        fig.update_yaxes(title_text=p2y1_axis_title, row=2, col=1, secondary_y=False)
    if p2y2_axis_title is not None:
        fig.update_yaxes(title_text=p2y2_axis_title, row=2, col=1, secondary_y=True, showgrid=False)
    if p3y1_axis_title is not None:
        fig.update_yaxes(title_text=p3y1_axis_title, row=3, col=1, secondary_y=False)
    if p3y2_axis_title is not None:
        fig.update_yaxes(title_text=p3y2_axis_title, row=3, col=1, secondary_y=True, showgrid=False)

    if y_axis_reversed:
        fig.update_yaxes(autorange="reversed", row=1, col=1, secondary_y=False)
    if p1y2_axis_reversed:
        fig.update_yaxes(autorange="reversed", row=1, col=1, secondary_y=True, showgrid=False)
    if p2y1_axis_reversed:
        fig.update_yaxes(autorange="reversed", row=2, col=1, secondary_y=False)
    if p2y2_axis_reversed:
        fig.update_yaxes(autorange="reversed", row=2, col=1, secondary_y=True, showgrid=False)
    if p3y1_axis_reversed:
        fig.update_yaxes(autorange="reversed", row=3, col=1, secondary_y=False)
    if p3y2_axis_reversed:
        fig.update_yaxes(autorange="reversed", row=3, col=1, secondary_y=True, showgrid=False)

    if show_grid_c1 is False:
        fig.update_xaxes(showgrid=False, row=1, col=1)
    if show_grid_c2 is False:
        fig.update_xaxes(showgrid=False, row=1, col=2)

    if len(subplots) == 1:
        fig["layout"]["xaxis"]["title"] = x_axis_title
    elif len(subplots) == 2:
        fig["layout"]["xaxis2"]["title"] = x_axis_title
    elif len(subplots) == 3:
        fig["layout"]["xaxis3"]["title"] = x_axis_title
    if tickformat == "%b":
        fig.update_xaxes(dtick="M1", tickformat="%b")
    if y_range is not None:
        if y_range[0] is None:
            fig.update_yaxes(range=[data.min().min(), y_range[1]])
        elif y_range[1] is None:
            fig.update_yaxes(range=[y_range[0], data.max().max()])
        else:
            fig.update_yaxes(range=y_range)
    raise NotImplementedError("Unrecoverable chart.py:490 conditional figure-title tail")
    fig.update_layout(
        title=...,
        width=width,
        height=height,
        legend_groupclick="toggleitem",
        legend_tracegroupgap=3,
    )
    if bar_mode is not None:
        fig.update_layout(barmode=bar_mode)

    if file_path is not None:
        file_path = convert_path_to_linux(file_path)
        py.offline.plot(fig, auto_open=False, filename=file_path)
    return fig


def line_chart(
    df,
    title=None,
    data_p1y2=None,
    data_p2y1=None,
    data_p2y2=None,
    data_p3y1=None,
    data_p3y2=None,
    data_p1y1c2=None,
    data_p1y2c2=None,
    data_p2y1c2=None,
    data_p2y2c2=None,
    data_p3y1c2=None,
    data_p3y2c2=None,
    data_c2=None,
    subplots=1,
    col=1,
    showlegend=True,
    showlegend_c2=False,
    secondary_y=False,
    hovertemplate=None,
    highlight_dict=None,
    highlight_dict_c2=None,
    x_axis_title=None,
    y_axis_title=None,
    p1y2_axis_title=None,
    p2y1_axis_title=None,
    p2y2_axis_title=None,
    p3y1_axis_title=None,
    p3y2_axis_title=None,
    y_axis_reversed=False,
    p1y2_axis_reversed=False,
    p2y1_axis_reversed=False,
    p2y2_axis_reversed=False,
    p3y1_axis_reversed=False,
    p3y2_axis_reversed=False,
    width=900,
    height=600,
    tickformat="%b",
    column_titles=None,
    show_grid_c2=True,
    show_grid_c1=True,
    y_range=None,
    file_path=None,
    mode="lines",
):
    """
    Plotly line chart
    """
    return _line_chart(
        data=df,
        title=title,
        data_p1y2=data_p1y2,
        data_p2y1=data_p2y1,
        data_p2y2=data_p2y2,
        data_p3y1=data_p3y1,
        data_p3y2=data_p3y2,
        data_p1y1c2=data_p1y1c2,
        data_p1y2c2=data_p1y2c2,
        data_p2y1c2=data_p2y1c2,
        data_p2y2c2=data_p2y2c2,
        data_p3y1c2=data_p3y1c2,
        data_p3y2c2=data_p3y2c2,
        data_c2=data_c2,
        subplots=subplots,
        col=col,
        showlegend=showlegend,
        showlegend_c2=showlegend_c2,
        secondary_y=secondary_y,
        hovertemplate=hovertemplate,
        highlight_dict=highlight_dict,
        highlight_dict_c2=highlight_dict_c2,
        x_axis_title=x_axis_title,
        y_axis_title=y_axis_title,
        p1y2_axis_title=p1y2_axis_title,
        p2y1_axis_title=p2y1_axis_title,
        p2y2_axis_title=p2y2_axis_title,
        p3y1_axis_title=p3y1_axis_title,
        p3y2_axis_title=p3y2_axis_title,
        y_axis_reversed=y_axis_reversed,
        p1y2_axis_reversed=p1y2_axis_reversed,
        p2y1_axis_reversed=p2y1_axis_reversed,
        p2y2_axis_reversed=p2y2_axis_reversed,
        p3y1_axis_reversed=p3y1_axis_reversed,
        p3y2_axis_reversed=p3y2_axis_reversed,
        width=width,
        height=height,
        tickformat=tickformat,
        column_titles=column_titles,
        show_grid_c2=show_grid_c2,
        show_grid_c1=show_grid_c1,
        y_range=y_range,
        file_path=file_path,
        mode=mode,
    )


def seasonal_chart(
    df,
    start=None,
    column=None,
    title=None,
    vs_avg=True,
    ytd=False,
    df_ytd=False,
    freq="D",
    ex2020=True,
    x_axis_title=None,
    y_axis_title=None,
    y1_axis_title=None,
    y2_axis_title=None,
    y_axis_reversed=False,
    y1_axis_reversed=False,
    y2_axis_reversed=False,
    width=900,
    height=600,
    file_path=None,
    dash_from=None,
    dash_name="Forecast",
    start_day=1,
    start_month=1,
    end_day=31,
    end_month=12,
    over_year=False,
    ytd_diff=False,
    ytd_cum_sum=False,
    exclude_years=None,
    dropna_all=False,
    **kwargs,
):
    """
    Convert data to seasonal time series, then chart data by year
    The first panel is data by year
    The second panel is this year vs last yr and 5yr average
    The third panel is YTD change
    Example:
        import ecm.cmds.core.core.pyg as pyg
        c = pyg.get_data(pyg.reports_db().data, name="kpler_implied_demand_exporter_roll")
        seasonal_chart(df=c.iloc[:, 0], vs_avg=True, ytd=True, title='Kpler export',
                       freq='D',
                       ex2020=True,
                       x_axis_title='Date',
                       y_axis_title='kb',
                       y1_axis_title='kb',
                       y2_axis_title='kb',
                       y_axis_reversed=True,
                       y1_axis_reversed=True,
                       y2_axis_reversed=True,
                       file_path="H:\\temp\\test_chart.html")
    """
    convert_to_dby = kwargs.get("convert_to_dby", True)
    if isinstance(df, pd.DataFrame):
        if column is None:
            data_ = df.iloc[:, 0]
        else:
            data_ = df[column]
    else:
        data_ = df.copy()
    if dash_from is not None:
        if isinstance(dash_from, str):
            dash_from_ = pd.to_datetime(dash_from)
        else:
            dash_from_ = dash_from
        dash_data_ = data_.loc[dash_from_:]
        dash_sdate_loc = np.where(data_.index >= dt.datetime(dash_from_.year, start_month, start_day))[0][0]
        dash_dts = data_.index[dash_sdate_loc:]
        if not over_year:
            end_bound = dt.datetime(dash_from_.year, end_month, end_day)
        else:
            end_bound = dt.datetime(dash_from_.year + 1, end_month, end_day)
        dash_dts = dash_dts[dash_dts <= end_bound]
        data_ = data_.loc[:dash_from_]
        dash_data_ = dash_data_.reindex(dash_dts)
        dash_data_by_yr = ts.data_by_year(dash_data_, freq=freq, start_day=start_day, start_month=start_month, end_day=end_day, end_month=end_month)
        if dash_name is not None:
            dash_data_by_yr.columns = [f"{x}_{dash_name}" for x in dash_data_by_yr.columns]
        dash_data_by_yr = dash_data_by_yr.dropna(how="all", axis=1)
    if start is not None:
        if isinstance(start, str):
            start = pygdt(start)
        if isinstance(data_, pd.DataFrame):
            data_ = data_.loc[data_.index >= start, :]
        elif isinstance(data_, pd.Series):
            data_ = data_.loc[data_.index >= start]
    subplot_count = 1
    if vs_avg:
        subplot_count += 1
    if ytd or ytd_cum_sum:
        subplot_count += 1
    if subplot_count == 2:
        subplots = [0.7, 0.3]
    elif subplot_count == 3:
        subplots = [0.5, 0.25, 0.25]
    else:
        subplots = 1
    if convert_to_dby:
        data_by_yr = ts.data_by_year(
            data_,
            freq=freq,
            start_day=start_day,
            start_month=start_month,
            end_day=end_day,
            end_month=end_month,
        )
        cur_yr = kwargs.get("cur_yr", data_by_yr.columns[-1])
        dts = pd.date_range(
            dt.datetime(cur_yr, start_month, start_day),
            dt.datetime(cur_yr, end_month, end_day),
            freq=freq,
        )
    else:
        data_by_yr = df.copy()
        cur_yr = kwargs.get("cur_yr", data_by_yr.columns[-1])
        dts = data_by_yr.index
    if dropna_all:
        data_by_yr = data_by_yr.dropna(how="all", axis=1)
    if df_ytd:
        data_by_yr = data_by_yr.cumsum(axis=0)
    if exclude_years is not None and isinstance(exclude_years, list):
        for yr in exclude_years:
            if yr in data_by_yr.columns:
                data_by_yr.drop([yr], axis=1, inplace=True)
            if str(yr) in data_by_yr.columns:
                data_by_yr.drop([str(yr)], axis=1, inplace=True)
    if ex2020 and 2020 in data_by_yr.columns:
        data_by_yr.drop([2020], axis=1, inplace=True)

    data_by_yr_raw = data_by_yr.copy()
    if dash_from is not None:
        data_by_yr = pd.concat([data_by_yr, dash_data_by_yr], axis=1)
        color_list = ["black", "red", "blue", "green", "orange"]
        raise NotImplementedError("Unrecoverable chart.py:750 forecast-highlight conditional tail")
        highlight_dash = {
            x: ...
            for idx, x in enumerate(dash_data_by_yr.columns)
        }
    if len(dts) < data_by_yr.shape[0]:
        data_by_yr = data_by_yr.iloc[: len(dts), :]
    if len(dts) < data_by_yr_raw.shape[0]:
        data_by_yr_raw = data_by_yr_raw.iloc[: len(dts), :]
    data_by_yr["Date"] = dts
    data_by_yr = data_by_yr.set_index("Date")
    data_by_yr_raw["Date"] = dts
    data_by_yr_raw = data_by_yr_raw.set_index("Date")
    if vs_avg:
        data1 = data_by_yr_raw[cur_yr] - data_by_yr_raw.iloc[:, -6:-1].mean(axis=1)
        data1 = data1.to_frame("Cur Yr vs 5y Avg")
        data1["Cur Yr vs Y-1"] = data_by_yr_raw[cur_yr] - data_by_yr_raw.iloc[:, -2]
    else:
        data1 = None
    if ytd:
        if not ytd_diff:
            data2 = (data_by_yr[cur_yr].cumsum()).to_frame("YTD cum chg")
        else:
            data2 = (data_by_yr[cur_yr].diff().cumsum()).to_frame("YTD cum chg")
    else:
        data2 = None
    if ytd_cum_sum:
        if not ytd_diff:
            if data2 is not None and data2.empty is False:
                data2["Cum Cur Yr vs 5y Avg"] = data_by_yr[cur_yr].cumsum() - data_by_yr_raw.iloc[:, -6:-1].cumsum().mean(axis=1)
            else:
                data2 = (data_by_yr[cur_yr].cumsum() - data_by_yr_raw.iloc[:, -6:-1].cumsum().mean(axis=1)).to_frame("Cum Cur Yr vs 5y Avg")
            data2["Cum Cur Yr vs Y-1"] = data_by_yr[cur_yr].cumsum() - data_by_yr_raw.iloc[:, -2].cumsum()
        else:
            if data2 is not None and data2.empty is False:
                data2["Cum Cur Yr vs 5y Avg"] = data_by_yr[cur_yr].diff().cumsum() - data_by_yr_raw.iloc[:, -6:-1].diff().cumsum().mean(axis=1)
            else:
                data2 = (data_by_yr[cur_yr].diff().cumsum() - data_by_yr_raw.iloc[:, -6:-1].diff().cumsum().mean(axis=1)).to_frame("Cum Cur Yr vs 5y Avg")
            data2["Cum Cur Yr vs Y-1"] = data_by_yr[cur_yr].diff().cumsum() - data_by_yr_raw.iloc[:, -2].diff().cumsum()

    if data2 is not None and "Cum Cur Yr vs Y-1" in data2.columns:
        default_highlight = {
            cur_yr: {"width": 2, "color": "black"},
            cur_yr - 1: {"width": 1, "color": "blue"},
            "Cur Yr vs 5y Avg": {"color": "black", "width": 1},
            "Cur Yr vs Y-1": {"color": "black", "dash": "dash", "width": 1},
            "YTD cum chg": {"color": "black", "width": 1},
            "Cum Cur Yr vs 5y Avg": {"color": "grey", "width": 1},
            "Cum Cur Yr vs Y-1": {"color": "grey", "dash": "dash", "width": 1, "fill": "tozeroy"},
        }
    elif data2 is not None and "YTD cum chg" in data2.columns:
        default_highlight = {
            cur_yr: {"width": 2, "color": "black"},
            cur_yr - 1: {"width": 1, "color": "blue"},
            "Cur Yr vs 5y Avg": {"color": "black", "width": 1},
            "Cur Yr vs Y-1": {"color": "black", "dash": "dash", "width": 1},
            "YTD cum chg": {"color": "black", "width": 1},
        }
    else:
        default_highlight = {
            cur_yr: {"width": 2, "color": "black"},
            cur_yr - 1: {"width": 1, "color": "blue"},
            "Cur Yr vs 5y Avg": {"color": "black", "width": 1},
            "Cur Yr vs Y-1": {"color": "black", "dash": "dash", "width": 1},
        }
    highlight = kwargs.get("highlight", default_highlight)
    tickformat = kwargs.get("tickformat", "%b")
    if dash_from is not None and highlight == default_highlight:
        highlight = highlight | highlight_dash

    if (ytd or ytd_cum_sum) and not vs_avg:
        data1 = data2
        data2 = None

    return line_chart(
        df=data_by_yr,
        title=title,
        data_p1y2=None,
        data_p2y1=data1,
        data_p2y2=None,
        data_p3y1=data2,
        data_p3y2=None,
        subplots=subplots,
        secondary_y=False,
        highlight_dict=highlight,
        x_axis_title=x_axis_title,
        y_axis_title=y_axis_title,
        p1y2_axis_title=None,
        p2y1_axis_title=y1_axis_title,
        p2y2_axis_title=None,
        p3y1_axis_title=y2_axis_title,
        p3y2_axis_title=None,
        y_axis_reversed=y_axis_reversed,
        p1y2_axis_reversed=False,
        p2y1_axis_reversed=y1_axis_reversed,
        p2y2_axis_reversed=False,
        p3y1_axis_reversed=y2_axis_reversed,
        p3y2_axis_reversed=False,
        width=width,
        height=height,
        file_path=file_path,
        tickformat=tickformat,
    )


def _build_seasonal_panels(
    data_series: pd.Series,
    *,
    vs_avg: bool = True,
    ytd: bool = False,
    df_ytd: bool = False,
    freq: str = "D",
    ex2020: bool = True,
    dash_from=None,
    dash_name: str = "Forecast",
    start_day: int = 1,
    start_month: int = 1,
    end_day: int = 31,
    end_month: int = 12,
    over_year: bool = False,
    ytd_diff: bool = False,
    ytd_cum_sum: bool = False,
    exclude_years=None,
    dropna_all: bool = False,
    start=None,
    highlight: dict | None = None,
) -> dict:
    """Internal: build seasonal transformed dataframe and optional panels.

    Returns dict with keys: data, panel_vs, panel_ytd, highlight, rows.
    Mirrors seasonal_chart logic but without plotting side-effects.
    """
    s = data_series.copy()
    if start is not None:
        start_dt = pygdt(start) if isinstance(start, str) else start
        s = s.loc[s.index >= start_dt]
    dash_data_by_yr = None
    if dash_from is not None:
        dash_from_ = pd.to_datetime(dash_from) if isinstance(dash_from, str) else dash_from
        dash_future = s.loc[dash_from_:]
        dash_sdate_loc = np.where(s.index >= dt.datetime(dash_from_.year, start_month, start_day))[0][0]
        dash_dts = s.index[dash_sdate_loc:]
        end_bound = dt.datetime(dash_from_.year + (1 if over_year else 0), end_month, end_day)
        dash_dts = dash_dts[dash_dts <= end_bound]
        s = s.loc[:dash_from_]
        dash_future = dash_future.reindex(dash_dts)
        dash_data_by_yr = ts.data_by_year(
            dash_future,
            freq=freq,
            start_day=start_day,
            start_month=start_month,
            end_day=end_day,
            end_month=end_month,
            over_year=over_year,
        )
        if dash_name is not None:
            dash_data_by_yr.columns = [f"{x}_{dash_name}" for x in dash_data_by_yr.columns]
        dash_data_by_yr = dash_data_by_yr.dropna(how="all", axis=1)
    data_by_yr = ts.data_by_year(
        s,
        freq=freq,
        start_day=start_day,
        start_month=start_month,
        end_day=end_day,
        end_month=end_month,
        over_year=over_year,
    )
    data_by_yr_raw = data_by_yr.copy()

    if df_ytd:
        data_by_yr = data_by_yr.cumsum(axis=0)
    if exclude_years is not None and isinstance(exclude_years, list):
        for yr in exclude_years:
            for label in (yr, str(yr)):
                if label in data_by_yr.columns:
                    data_by_yr.drop([label], axis=1, inplace=True)
    if ex2020 and 2020 in data_by_yr.columns:
        data_by_yr.drop([2020], axis=1, inplace=True)
    if dropna_all:
        data_by_yr = data_by_yr.dropna(how="all", axis=1)
    cur_yr = data_by_yr.columns[-1]
    dts = pd.date_range(
        dt.datetime(cur_yr, start_month, start_day),
        dt.datetime(cur_yr + (1 if over_year else 0), end_month, end_day),
        freq=freq,
    )
    if dash_data_by_yr is not None:
        data_by_yr = pd.concat([data_by_yr, dash_data_by_yr], axis=1)
        color_list = ["black", "red", "blue", "green", "orange"]
        raise NotImplementedError("Unrecoverable chart.py:939 forecast-highlight conditional tail")
        highlight_dash = {
            c: ...
            for i, c in enumerate(dash_data_by_yr.columns)
        }
    else:
        highlight_dash = {}
    rows = data_by_yr.shape[0]
    if len(dts) < rows:
        data_by_yr = data_by_yr.iloc[: len(dts), :]
        data_by_yr_raw = data_by_yr_raw.iloc[: len(dts), :]
        rows = data_by_yr.shape[0]
    elif len(dts) > rows:
        dts = dts[:rows]
    data_by_yr["Date"] = dts
    data_by_yr.set_index("Date", inplace=True)
    data_by_yr_raw["Date"] = dts
    data_by_yr_raw = data_by_yr_raw.set_index("Date")
    panel_vs = None
    panel_ytd = None

    if vs_avg:
        panel_vs = data_by_yr_raw[cur_yr] - data_by_yr_raw.iloc[:, -6:-1].mean(axis=1)
        panel_vs = panel_vs.to_frame("Cur Yr vs 5y Avg")
        panel_vs["Cur Yr vs Y-1"] = data_by_yr_raw[cur_yr] - data_by_yr_raw.iloc[:, -2]
    if ytd:
        if not ytd_diff:
            panel_ytd = (data_by_yr[cur_yr].cumsum()).to_frame("YTD cum chg")
        else:
            panel_ytd = (data_by_yr[cur_yr].diff().cumsum()).to_frame("YTD cum chg")
    else:
        panel_ytd = None
    if ytd_cum_sum:
        if not ytd_diff:
            if panel_ytd is not None and panel_ytd.empty is False:
                panel_ytd["Cum Cur Yr vs 5y Avg"] = data_by_yr[cur_yr].cumsum() - data_by_yr_raw.iloc[:, -6:-1].cumsum().mean(axis=1)
            else:
                panel_ytd = (data_by_yr[cur_yr].cumsum() - data_by_yr_raw.iloc[:, -6:-1].cumsum().mean(axis=1)).to_frame("Cum Cur Yr vs 5y Avg")
            panel_ytd["Cum Cur Yr vs Y-1"] = data_by_yr[cur_yr].cumsum() - data_by_yr_raw.iloc[:, -2].cumsum()
        else:
            if panel_ytd is not None and panel_ytd.empty is False:
                panel_ytd["Cum Cur Yr vs 5y Avg"] = panel_ytd[cur_yr].diff().cumsum() - data_by_yr_raw.iloc[:, -6:-1].diff().cumsum().mean(axis=1)
            else:
                panel_ytd = (data_by_yr[cur_yr].diff().cumsum() - data_by_yr_raw.iloc[:, -6:-1].diff().cumsum().mean(axis=1)).to_frame("Cum Cur Yr vs 5y Avg")
            panel_ytd["Cum Cur Yr vs Y-1"] = data_by_yr[cur_yr].diff().cumsum() - data_by_yr_raw.iloc[:, -2].diff().cumsum()

    if panel_ytd is not None and "Cum Cur Yr vs Y-1" in panel_ytd.columns:
        default_highlight = {
            cur_yr: {"width": 2, "color": "black"},
            cur_yr - 1: {"width": 1, "color": "blue"},
            "Cur Yr vs 5y Avg": {"color": "black", "width": 1},
            "Cur Yr vs Y-1": {"color": "black", "dash": "dash", "width": 1},
            "YTD cum chg": {"color": "black", "width": 1},
            "Cum Cur Yr vs 5y Avg": {"color": "grey", "width": 1},
            "Cum Cur Yr vs Y-1": {"color": "grey", "dash": "dash", "width": 1, "fill": "tozeroy"},
        }
    elif panel_ytd is not None and "YTD cum chg" in panel_ytd.columns:
        default_highlight = {
            cur_yr: {"width": 2, "color": "black"},
            cur_yr - 1: {"width": 1, "color": "blue"},
            "Cur Yr vs 5y Avg": {"color": "black", "width": 1},
            "Cur Yr vs Y-1": {"color": "black", "dash": "dash", "width": 1},
            "YTD cum chg": {"color": "black", "width": 1},
        }
    else:
        default_highlight = {
            cur_yr: {"width": 2, "color": "black"},
            cur_yr - 1: {"width": 1, "color": "blue"},
            "Cur Yr vs 5y Avg": {"color": "black", "width": 1},
            "Cur Yr vs Y-1": {"color": "black", "dash": "dash", "width": 1},
        }

    if (ytd or ytd_cum_sum) and not vs_avg and panel_ytd is not None:
        panel_vs = panel_ytd
        panel_ytd = None

    if highlight is None:
        hdict = default_highlight | highlight_dash
    else:
        missing = {k: v for k, v in default_highlight.items() if k not in highlight}
        hdict = highlight | missing
        if not any(k in highlight for k in highlight_dash.keys()):
            hdict |= highlight_dash

    subplot_count = 1 + (1 if panel_vs is not None else 0) + (1 if panel_ytd is not None else 0)
    return dict(data=data_by_yr, panel_vs=panel_vs, panel_ytd=panel_ytd, highlight=hdict, rows=subplot_count)


def seasonal_chart_2col(
    df,
    df1,
    start=None,
    column=None,
    column1=None,
    title=None,
    vs_avg=True,
    ytd=False,
    freq="D",
    ex2020=True,
    x_axis_title=None,
    y_axis_title=None,
    y1_axis_title=None,
    y2_axis_title=None,
    highlight_dict=None,
    highlight_dict_c2=None,
    showlegend_c2=True,
    width=1600,
    height=600,
    column_titles=None,
    switch=False,
    show_grid_c1=True,
    show_grid_c2=True,
    file_path=None,
):
    """
    Convert data to seasonal time series, then chart data by year
    The first panel is data by year
    The second panel is this year vs last yr and 5yr average
    The third panel is YTD change
    switch: switch seasonal chart to the second chart
    Example:
        import ecm.cmds.core.core.pyg as pyg
        c = pyg.get_data(pyg.reports_db().data, name="kpler_implied_demand_exporter")
        c1 = (c.sum(axis=1).to_frame("Total")).rolling(20).sum()
        c1 = c1.loc[c1.index >= dt.datetime(2017, 1, 1)]
        seasonal_chart_2col(
            df=c1,
            df1=c1.iloc[-250:, :],
            column=None,
            title="Total export (kb)",
            vs_avg=True,
            ytd=False,
            freq="D",
            x_axis_title="Date",
            y_axis_title="kb",
            y1_axis_title="kb",
            y2_axis_title=None,
            highlight_dict={"Total": {"color": "black", "width": 1}},
            file_path="H:\\temp\\test_chart.html",
        )

    Example:
        import ecm.cmds.core.core.pyg as pyg
        c1 = pyg.get_data(pyg.reports_db().data, name="China_disty_export_actual_vs_allocation")
        c2 = pyg.get_data(pyg.reports_db().data, name="China_disty_export_smooth")
        seasonal_chart_2col(
            df=c2,
            df1=c1,
            column=None,
            title="China Gasoil Export (kbd)",
            vs_avg=True,
            ytd=False,
            freq="D",
            # x_axis_title="Date",
            y_axis_title="kb",
            y1_axis_title="kb",
            y2_axis_title=None,
            highlight_dict_c2={
                0: {"color": "blue", "width": 2},
                1: {"color": "red", "width": 2},
                2: {"color": "blue", "dash": "dash", "width": 2},
                3: {"color": "red", "dash": "dash", "width": 2},
            },
            # column_titles=["Actual vs Allocation", "Seasonal Export"],
            column_titles=None,
            switch=True,
            show_grid_c1=False,
            show_grid_c2=True,
            file_path="H:\\temp\\test_chart.html",
        )
    """
    if isinstance(df, pd.DataFrame):
        if column is None:
            data_ = df.iloc[:, 0]
        else:
            data_ = df[column]
    else:
        data_ = df.copy()
    if start is not None:
        if isinstance(start, str):
            start = pygdt(start)
        if isinstance(data_, pd.DataFrame):
            data_ = data_.loc[data_.index >= start, :]
        elif isinstance(data_, pd.Series):
            data_ = data_.loc[data_.index >= start]
    if vs_avg and not ytd:
        subplots = [0.7, 0.3]
    elif vs_avg and ytd:
        subplots = [0.5, 0.25, 0.25]
    else:
        subplots = 1
    data_by_yr = ts.data_by_year(data_, freq=freq)
    if ex2020 and 2020 in data_by_yr.columns:
        data_by_yr.drop([2020], axis=1, inplace=True)
    cur_yr = data_by_yr.columns[-1]
    dts = pd.date_range(dt.datetime(cur_yr, 1, 1), dt.datetime(cur_yr, 12, 31), freq=freq)
    if len(dts) < data_by_yr.shape[0]:
        data_by_yr = data_by_yr.iloc[: len(dts), :]
    data_by_yr["Date"] = dts
    data_by_yr = data_by_yr.set_index("Date")
    if vs_avg:
        data1 = data_by_yr[cur_yr] - data_by_yr.iloc[:, -6:-1].mean(axis=1)
        data1 = data1.to_frame("Cur Yr vs 5y Avg")
        data1["Cur Yr vs Y-1"] = data_by_yr[cur_yr] - data_by_yr.iloc[:, -2]
    else:
        data1 = None
    if ytd:
        data2 = (data_by_yr[cur_yr].cumsum()).to_frame("YTD cum chg")
    else:
        data2 = None

    highlight_dict_ = {
        cur_yr: {"width": 2, "color": "black"},
        cur_yr - 1: {"width": 1, "color": "blue"},
        "Cur Yr vs 5y Avg": {"color": "black", "width": 1},
        "Cur Yr vs Y-1": {"color": "black", "dash": "dash", "width": 1},
        "YTD cum chg": {"color": "black", "width": 1},
    }

    if highlight_dict is not None:
        highlight_dict_ = {**highlight_dict_, **highlight_dict}

    highlight_dict_c2_ = None
    if switch:
        if highlight_dict_c2 is not None:
            highlight_dict_c2_ = {}
            for k, v in highlight_dict_c2.items():
                if isinstance(k, str) and k.isdigit() and int(k) < len(df1.columns):
                    highlight_dict_c2_[df1.columns[int(k)]] = v
                else:
                    highlight_dict_c2_[k] = v
        else:
            highlight_dict_c2_ = {**highlight_dict_}

    if column1 is None:
        column1 = df1.columns

    if switch:
        return line_chart(
            df=df1[column1],
            title=title,
            data_p1y1c2=data_by_yr,
            data_p1y2c2=None,
            data_p2y1c2=data1,
            data_p2y2c2=None,
            data_p3y1c2=data2,
            data_p3y2c2=None,
            subplots=subplots,
            col=2,
            showlegend_c2=showlegend_c2,
            secondary_y=False,
            highlight_dict=highlight_dict_c2_ if highlight_dict_c2_ is not None else highlight_dict_,
            highlight_dict_c2=highlight_dict_,
            x_axis_title=x_axis_title,
            y_axis_title=y_axis_title,
            p1y2_axis_title=None,
            p2y1_axis_title=y1_axis_title,
            p2y2_axis_title=None,
            p3y1_axis_title=y2_axis_title,
            p3y2_axis_title=None,
            width=width,
            height=height,
            column_titles=column_titles,
            show_grid_c1=show_grid_c1,
            show_grid_c2=show_grid_c2,
            file_path=file_path,
        )
    else:
        return line_chart(
            df=data_by_yr,
            title=title,
            data_p1y2=None,
            data_p2y1=data1,
            data_p2y2=None,
            data_p3y1=data2,
            data_p3y2=None,
            data_c2=df1[column1],
            subplots=subplots,
            col=2,
            showlegend_c2=showlegend_c2,
            secondary_y=False,
            highlight_dict=highlight_dict_,
            highlight_dict_c2=highlight_dict_c2,
            x_axis_title=x_axis_title,
            y_axis_title=y_axis_title,
            p1y2_axis_title=None,
            p2y1_axis_title=y1_axis_title,
            p2y2_axis_title=None,
            p3y1_axis_title=y2_axis_title,
            p3y2_axis_title=None,
            width=width,
            height=height,
            column_titles=column_titles,
            file_path=file_path,
        )


def seasonal_chart_2col_new(
    df,
    df1,
    start=None,
    column=None,
    column1=None,
    title=None,
    vs_avg=True,
    ytd=False,
    freq="D",
    ex2020=True,
    x_axis_title=None,
    y_axis_title=None,
    y1_axis_title=None,
    y2_axis_title=None,
    highlight_dict=None,
    highlight_dict_c2=None,
    showlegend_c2=True,
    width=1600,
    height=600,
    column_titles=None,
    switch=False,
    show_grid_c1=True,
    show_grid_c2=True,
    file_path=None,
):
    """
    Convert data to seasonal time series, then chart data by year
    The first panel is data by year
    The second panel is this year vs last yr and 5yr average
    The third panel is YTD change
    switch: switch seasonal chart to the second chart
    Example:
        import ecm.cmds.core.core.pyg as pyg
        c = pyg.get_data(pyg.reports_db().data, name="kpler_implied_demand_exporter")
        c1 = (c.sum(axis=1).to_frame("Total")).rolling(20).sum()
        c1 = c1.loc[c1.index >= dt.datetime(2017, 1, 1)]
        seasonal_chart_2col(
            df=c1,
            df1=c1.iloc[-250:, :],
            column=None,
            title="Total export (kb)",
            vs_avg=True,
            ytd=False,
            freq="D",
            x_axis_title="Date",
            y_axis_title="kb",
            y1_axis_title="kb",
            y2_axis_title=None,
            highlight_dict={"Total": {"color": "black", "width": 1}},
            file_path="H:\\temp\\test_chart.html",
        )

    Example:
        import ecm.cmds.core.core.pyg as pyg
        c1 = pyg.get_data(pyg.reports_db().data, name="China_disty_export_actual_vs_allocation")
        c2 = pyg.get_data(pyg.reports_db().data, name="China_disty_export_smooth")
        seasonal_chart_2col(
            df=c2,
            df1=c1,
            column=None,
            title="China Gasoil Export (kbd)",
            vs_avg=True,
            ytd=False,
            freq="D",
            # x_axis_title="Date",
            y_axis_title="kb",
            y1_axis_title="kb",
            y2_axis_title=None,
            highlight_dict_c2={
                0: {"color": "blue", "width": 2},
                1: {"color": "red", "width": 2},
                2: {"color": "blue", "dash": "dash", "width": 2},
                3: {"color": "red", "dash": "dash", "width": 2},
            },
            # column_titles=["Actual vs Allocation", "Seasonal Export"],
            column_titles=None,
            switch=True,
            show_grid_c1=False,
            show_grid_c2=True,
            file_path="H:\\temp\\test_chart.html",
        )
    """
    if isinstance(df, pd.DataFrame):
        if column is None:
            data_ = df.iloc[:, 0]
        else:
            data_ = df[column]
    else:
        data_ = df.copy()
    if start is not None:
        if isinstance(start, str):
            start = pygdt(start)
        if isinstance(data_, pd.DataFrame):
            data_ = data_.loc[data_.index >= start, :]
        elif isinstance(data_, pd.Series):
            data_ = data_.loc[data_.index >= start]
    if vs_avg and not ytd:
        subplots = [0.7, 0.3]
    elif vs_avg and ytd:
        subplots = [0.5, 0.25, 0.25]
    else:
        subplots = 1
    data_by_yr = ts.data_by_year(data_, freq=freq)
    if ex2020 and 2020 in data_by_yr.columns:
        data_by_yr.drop([2020], axis=1, inplace=True)
    cur_yr = data_by_yr.columns[-1]
    dts = pd.date_range(dt.datetime(cur_yr, 1, 1), dt.datetime(cur_yr, 12, 31), freq=freq)
    if len(dts) < data_by_yr.shape[0]:
        data_by_yr = data_by_yr.iloc[: len(dts), :]
    data_by_yr["Date"] = dts
    data_by_yr = data_by_yr.set_index("Date")
    if vs_avg:
        data1 = data_by_yr[cur_yr] - data_by_yr.iloc[:, -6:-1].mean(axis=1)
        data1 = data1.to_frame("Cur Yr vs 5y Avg")
        data1["Cur Yr vs Y-1"] = data_by_yr[cur_yr] - data_by_yr.iloc[:, -2]
    else:
        data1 = None
    if ytd:
        data2 = (data_by_yr[cur_yr].cumsum()).to_frame("YTD cum chg")
    else:
        data2 = None

    highlight_dict_ = {
        cur_yr: {"width": 2, "color": "black"},
        cur_yr - 1: {"width": 1, "color": "blue"},
        "Cur Yr vs 5y Avg": {"color": "black", "width": 1},
        "Cur Yr vs Y-1": {"color": "black", "dash": "dash", "width": 1},
        "YTD cum chg": {"color": "black", "width": 1},
    }

    if highlight_dict is not None:
        highlight_dict_ = {**highlight_dict_, **highlight_dict}

    if highlight_dict_c2 is not None and switch:
        highlight_dict_c2_ = {}
        for k, _v in highlight_dict_c2.items():
            if k.isdigit() and int(k) < 100:
                highlight_dict_c2_[df1.columns[int(k)]] = highlight_dict_c2[k]

    if column1 is None:
        column1 = df1.columns
    pl_lib = {}
    if data1 is not None:
        if switch:
            pl_lib["data_p2y1c2"] = data1
        else:
            pl_lib["data_p2y1c1"] = data1
        pl_lib["y_axis_title_p2y1c1"] = y1_axis_title
        pl_lib["highlight_dict_p2y1c1"] = highlight_dict_
    if data2 is not None:
        if switch:
            pl_lib["data_p3y1c2"] = data1
        else:
            pl_lib["data_p3y1c1"] = data1
        pl_lib["y_axis_title_p3y1c2"] = y2_axis_title
        pl_lib["highlight_dict_p3y1c2"] = highlight_dict_c2 if not switch else highlight_dict_c2_
    pl_lib["highlight_dict_c2"] = highlight_dict_c2 if not switch else highlight_dict_c2_
    pl_lib["highlight_dict"] = highlight_dict_
    if column_titles is not None:
        pl_lib["column_titles"] = column_titles
    if switch:
        chart = PlottingLib(
            rows=len(subplots),
            cols=2,
            data_c1=df1[column1],
            title=title,
            width=width,
            height=height,
            data_c2=data_by_yr,
            col=2,
            showlegend_c2=showlegend_c2,
            x_axis_title=x_axis_title,
            y_axis_title=y_axis_title,
            p2y1_axis_title=y1_axis_title,
            show_grid_c1=show_grid_c1,
            show_grid_c2=show_grid_c2,
            file_path=file_path,
            **pl_lib,
        )
        return chart.fig
    else:
        chart = PlottingLib(
            rows=len(subplots),
            cols=2,
            data_c1=data_by_yr,
            data_c2=df1[column1],
            title=title,
            width=width,
            height=height,
            col=2,
            showlegend_c2=showlegend_c2,
            x_axis_title=x_axis_title,
            y_axis_title=y_axis_title,
            p2y1_axis_title=y1_axis_title,
            show_grid_c1=show_grid_c1,
            show_grid_c2=show_grid_c2,
            file_path=file_path,
            **pl_lib,
        )
        return chart.fig


def seasonal(df, title=None, freq="D", **kwargs):
    """
    Convert data to seasonal time series, then chart data by year
    """
    ex2020 = kwargs.get("ex2020", False)
    drop_years = kwargs.get("drop_years", None)
    column = kwargs.get("column", None)
    start = kwargs.get("start", None)
    x_axis_title = kwargs.get("x_axis_title", None)
    y_axis_title = kwargs.get("y_axis_title", None)
    p1y2_axis_title = kwargs.get("p1y2_axis_title", None)
    p2y1_axis_title = kwargs.get("p2y1_axis_title", None)
    p2y2_axis_title = kwargs.get("p2y2_axis_title", None)
    p3y1_axis_title = kwargs.get("p3y1_axis_title", None)
    p3y2_axis_title = kwargs.get("p3y2_axis_title", None)
    y_axis_reversed = kwargs.get("y_axis_reversed", False)
    p1y2_axis_reversed = kwargs.get("p1y2_axis_reversed", False)
    p2y1_axis_reversed = kwargs.get("p2y1_axis_reversed", False)
    p2y2_axis_reversed = kwargs.get("p2y2_axis_reversed", False)
    p3y1_axis_reversed = kwargs.get("p3y1_axis_reversed", False)
    p3y2_axis_reversed = kwargs.get("p3y2_axis_reversed", False)
    file_path = kwargs.get("file_path", None)
    highlight_dict = kwargs.get("highlight_dict", None)
    data_p1y2 = kwargs.get("data_p1y2", None)
    data_p2y1 = kwargs.get("data_p2y1", None)
    data_p2y2 = kwargs.get("data_p2y2", None)
    data_p3y1 = kwargs.get("data_p3y1", None)
    data_p3y2 = kwargs.get("data_p3y2", None)
    secondary_y = kwargs.get("secondary_y", False)
    dropna_all = kwargs.get("dropna_all", False)
    start_day = kwargs.get("start_day", 1)
    start_month = kwargs.get("start_month", 1)
    end_day = kwargs.get("end_day", 31)
    end_month = kwargs.get("end_month", 12)
    ytd = kwargs.get("ytd", False)
    width = kwargs.get("width", None)
    height = kwargs.get("height", None)
    dash_from = kwargs.get("dash_from", None)
    dash_name = kwargs.get("dash_name", "Forecast")

    if isinstance(df, pd.DataFrame):
        if column is None:
            data_ = df.iloc[:, 0]
        else:
            data_ = df[column]
    else:
        data_ = df.copy()
    if dash_from is not None:
        if isinstance(dash_from, str):
            dash_from_ = pd.to_datetime(dash_from)
        else:
            dash_from_ = dash_from
        dash_data_ = data_.loc[dash_from_:]
        dash_sdate_loc = np.where(data_.index >= dt.datetime(dash_from_.year, 1, 1))[0][0]
        dash_dts = data_.index[dash_sdate_loc:]
        data_ = data_.loc[:dash_from_]
        dash_data_ = dash_data_.reindex(dash_dts)
        dash_data_by_yr = ts.data_by_year(dash_data_, freq="W" if freq.lower().startswith("w") else freq)
        if dash_name is not None:
            dash_data_by_yr.columns = [f"{x}_{dash_name}" for x in dash_data_by_yr.columns]
        dash_data_by_yr = dash_data_by_yr.dropna(how="all", axis=1)
    if start is not None:
        if isinstance(start, str):
            start = pygdt(start)
        if isinstance(data_, pd.DataFrame):
            data_ = data_.loc[data_.index >= start, :]
        elif isinstance(data_, pd.Series):
            data_ = data_.loc[data_.index >= start]
    if data_p2y1 is not None and data_p3y1 is None:
        subplots = [0.7, 0.3]
    elif data_p2y1 is not None and data_p3y1 is not None:
        subplots = [0.5, 0.25, 0.25]
    else:
        subplots = 1
    data_by_yr = ts.data_by_year(
        data_,
        freq="W" if freq.lower().startswith("w") else freq,
        start=start,
        start_day=start_day,
        start_month=start_month,
        end_day=end_day,
        end_month=end_month,
    )
    if dropna_all:
        data_by_yr = data_by_yr.dropna(how="all", axis=1)
    if ytd:
        data_by_yr = data_by_yr.cumsum(axis=0)
    if ex2020 and 2020 in data_by_yr.columns:
        data_by_yr.drop([2020], axis=1, inplace=True)
        if 2022 in data_by_yr.columns:
            data_by_yr.drop([2022], axis=1, inplace=True)
    if drop_years is not None:
        try:
            data_by_yr.drop(drop_years, axis=1, inplace=True)
        except Exception:
            pass
    cur_yr = data_by_yr.columns[-1]
    dts = pd.date_range(dt.datetime(cur_yr, 1, 1), dt.datetime(cur_yr, 12, 31), freq=freq)
    if dash_from is not None:
        data_by_yr = pd.concat([data_by_yr, dash_data_by_yr], axis=1)
        color_list = ["black", "red", "blue", "green", "orange"]
        raise NotImplementedError("Unrecoverable chart.py:1602 forecast-highlight conditional tail")
        highlight_dash = {
            x: ...
            for idx, x in enumerate(dash_data_by_yr.columns)
        }

    def adjust_length(dts, data_by_yr):
        if len(dts) < data_by_yr.shape[0]:
            if not isinstance(data_by_yr.index, pd.DatetimeIndex):
                data_by_yr = data_by_yr.iloc[: len(dts), :].copy()
            else:
                data_by_yr = data_by_yr.reindex(dts)
        data_by_yr["Date"] = dts
        data_by_yr = data_by_yr.set_index("Date")
        return data_by_yr

    data_by_yr = adjust_length(dts, data_by_yr)
    if data_p1y2 is not None:
        data_p1y2 = adjust_length(dts, data_p1y2)
    if data_p2y1 is not None:
        data_p2y1 = adjust_length(dts, data_p2y1)
    if data_p2y2 is not None:
        data_p2y2 = adjust_length(dts, data_p2y2)
    if data_p3y1 is not None:
        data_p3y1 = adjust_length(dts, data_p3y1)
    if data_p3y2 is not None:
        data_p3y2 = adjust_length(dts, data_p3y2)
    default_highlight = {
        cur_yr: {"width": 2, "color": "black"},
        cur_yr - 1: {"width": 1, "color": "blue"},
    }
    if data_p2y1 is not None:  # vs average panel
        if "Cur Yr vs 5y Avg" in data_p2y1.columns:
            default_highlight["Cur Yr vs 5y Avg"] = {"color": "black", "width": 1}
        if "Cur Yr vs Y-1" in data_p2y1.columns:
            default_highlight["Cur Yr vs Y-1"] = {"color": "black", "dash": "dash", "width": 1}
    if data_p3y1 is not None:  # YTD panel
        if "YTD cum chg" in data_p3y1.columns:
            default_highlight["YTD cum chg"] = {"color": "black", "width": 1}

    if highlight_dict is not None:
        highlight_dict_ = {**default_highlight, **highlight_dict}
        user_supplied = True
    else:
        highlight_dict_ = default_highlight
        user_supplied = False

    if dash_from is not None and not user_supplied:
        highlight_dict_ = highlight_dict_ | highlight_dash
    return line_chart(
        df=data_by_yr,
        title=title,
        data_p1y2=data_p1y2,
        data_p2y1=data_p2y1,
        data_p2y2=data_p2y2,
        data_p3y1=data_p3y1,
        data_p3y2=data_p3y2,
        subplots=subplots,
        secondary_y=secondary_y,
        highlight_dict=highlight_dict_,
        x_axis_title=x_axis_title,
        y_axis_title=y_axis_title,
        p1y2_axis_title=p1y2_axis_title,
        p2y1_axis_title=p2y1_axis_title,
        p2y2_axis_title=p2y2_axis_title,
        p3y1_axis_title=p3y1_axis_title,
        p3y2_axis_title=p3y2_axis_title,
        y_axis_reversed=y_axis_reversed,
        p1y2_axis_reversed=p1y2_axis_reversed,
        p2y1_axis_reversed=p2y1_axis_reversed,
        p2y2_axis_reversed=p2y2_axis_reversed,
        p3y1_axis_reversed=p3y1_axis_reversed,
        p3y2_axis_reversed=p3y2_axis_reversed,
        file_path=file_path,
        width=width,
        height=height,
    )


def seasonal_new(data, title=None, freq="D", **kwargs):
    """n x m seasonal chart builder using PlottingLib (shared legend).

    data may be a single Series/DataFrame or list thereof. Each dataset becomes a column.
    """
    if not isinstance(data, list):
        data = [data]
    highlight_arg = kwargs.get("highlight")
    rangebreak_holidays = kwargs.get("rangebreak_holidays", "all")
    if isinstance(highlight_arg, list):
        highlight_list = highlight_arg
    else:
        highlight_list = [highlight_arg] * len(data)
    pl_args = {}
    max_rows = 1
    for idx, d in enumerate(data, start=1):
        if isinstance(d, pd.DataFrame):
            series = d.iloc[:, 0] if kwargs.get("column") is None else d[kwargs.get("column")]
        else:
            series = d.copy()
        panels = _build_seasonal_panels(
            series,
            vs_avg=kwargs.get("vs_avg", True),
            ytd=kwargs.get("ytd", False),
            df_ytd=kwargs.get("df_ytd", False),
            freq=freq,
            ex2020=kwargs.get("ex2020", True),
            dash_from=kwargs.get("dash_from"),
            dash_name=kwargs.get("dash_name", "Forecast"),
            start_day=kwargs.get("start_day", 1),
            start_month=kwargs.get("start_month", 1),
            end_day=kwargs.get("end_day", 31),
            end_month=kwargs.get("end_month", 12),
            over_year=kwargs.get("over_year", False),
            ytd_diff=kwargs.get("ytd_diff", False),
            ytd_cum_sum=kwargs.get("ytd_cum_sum", False),
            exclude_years=kwargs.get("exclude_years"),
            dropna_all=kwargs.get("dropna_all", False),
            start=kwargs.get("start"),
            highlight=highlight_list[idx - 1],
        )
        max_rows = max(max_rows, panels["rows"])
        pl_args[f"data_c{idx}"] = panels["data"]
        pl_args[f"highlight_dict_c{idx}"] = panels["highlight"]
        if panels["panel_vs"] is not None:
            pl_args[f"data_p2y1c{idx}"] = panels["panel_vs"]
            if kwargs.get("y1_axis_title"):
                pl_args[f"y_axis_title_p2y1c{idx}"] = kwargs.get("y1_axis_title")
            pl_args[f"highlight_dict_p2c{idx}"] = panels["highlight"]
            if kwargs.get("y1_axis_reversed"):
                pl_args[f"axis_reversed_p2y1c{idx}"] = True
        if panels["panel_ytd"] is not None:
            pl_args[f"data_p3y1c{idx}"] = panels["panel_ytd"]
            if kwargs.get("y2_axis_title"):
                pl_args[f"y_axis_title_p3y2c{idx}"] = kwargs.get("y2_axis_title")
            pl_args[f"highlight_dict_p3c{idx}"] = panels["highlight"]
            if kwargs.get("y2_axis_reversed"):
                pl_args[f"axis_reversed_p3y2c{idx}"] = True
        if kwargs.get("y_axis_reversed"):
            pl_args[f"axis_reversed_p1y1c{idx}"] = True
    pl_args["y_axis_title"] = kwargs.get("y_axis_title")
    fig = PlottingLib(
        title=title if isinstance(title, str) else None,
        column_titles=title if isinstance(title, list) else None,
        rows=max_rows,
        col=len(data),
        width=kwargs.get("width", 900),
        height=kwargs.get("height", 600),
        x_axis_title=kwargs.get("x_axis_title"),
        file_path=kwargs.get("file_path"),
        rangebreak_holidays=rangebreak_holidays,
        **pl_args,
    ).fig
    return fig


def seasonal_chart_new(df, title=None, freq="D", **kwargs):
    return seasonal_new(df if isinstance(df, list) else [df], title=title, freq=freq, **kwargs)


def cot_chart(df, start=None, title=None, columns=None, ex2020=False, freq="W-TUE", file_path=None):
    """
    COT chart
    Example:
        import ecm.cmds.core.core.pyg as pyg
        c = pyg.get_data(pyg.reports_db().data, name="COA Comdty_cot_net_chart")
        cot_chart(df=c, title='COA Net position vs Price',
                  start=dt.datetime(2018,1,1),
                  columns=["Net", "PX_LAST", "Net OI"],
                  ex2020=False,
                  file_path="H:\\temp\\test_chart.html")
    """
    if columns is not None:
        data_ = df[columns]
    else:
        data_ = df.copy()
    if start is not None:
        data_ = data_.loc[data_.index >= start, :]
    if data_.iloc[:, 0].last_valid_index().year < data_.index[-1].year:
        data_.drop(data_.index[data_.index > data_.iloc[:, 0].last_valid_index()], axis=0, inplace=True)
    data0 = data_.iloc[:, 0]
    data1 = data_.iloc[:, -1]
    price = data_.iloc[:, 1]
    data_by_yr0 = ts.data_by_year(data0, start_day=1, start_month=1, freq="W")
    data_by_yr1 = ts.data_by_year(data1, start_day=1, start_month=1, freq="W")
    if ex2020 and 2020 in data_by_yr0.columns:
        data_by_yr0.drop([2020], axis=1, inplace=True)
        data_by_yr1.drop([2020], axis=1, inplace=True)
    cur_yr = data_by_yr0.columns[-1]
    dts = pd.date_range(dt.datetime(cur_yr, 1, 1), dt.datetime(cur_yr, 12, 31), freq=freq)
    actual_dts = data_[data_.index >= dt.datetime(cur_yr, 1, 1)].index
    if len(actual_dts) > 0:
        loc_ = len(actual_dts)
        dts = actual_dts.union(dts[loc_:])
    if len(dts) < data_by_yr0.shape[0]:
        data_by_yr0 = data_by_yr0.iloc[: len(dts), :]
        data_by_yr1 = data_by_yr1.iloc[: len(dts), :]
    data_by_yr0["Date"] = dts
    data_by_yr0 = data_by_yr0.set_index("Date")
    data_by_yr1["Date"] = dts
    data_by_yr1 = data_by_yr1.set_index("Date")
    price = price.loc[price.index >= dt.datetime(cur_yr, 1, 1)]
    price = price.reindex(dts)
    price = price.to_frame("price")

    max = data_by_yr1.iloc[:, -6:-1].max(axis=1)
    min = data_by_yr1.iloc[:, -6:-1].min(axis=1)
    new_data = pd.concat([data_by_yr1.iloc[:, -1], max, min], axis=1)
    new_data.columns = ["Net/OI", "Max", "Min"]
    return _line_chart(
        data=data_by_yr0,
        title=title,
        data_p1y2=price,
        data_p2y1=new_data,
        y_axis_title="Contracts",
        p1y2_axis_title="Price",
        p2y1_axis_title="Net/OI",
        secondary_y=True,
        subplots=2,
        col=1,
        highlight_dict={
            "price": {"mode": "lines+markers", "color": "black", "width": 2, "dash": "dash"},
            data_by_yr0.columns[-1]: {"mode": "lines+markers", "color": "red", "width": 2},
            new_data.columns[0]: {"mode": "lines+markers", "color": "red", "width": 2},
            "Max": {"color": "lightgrey", "width": 0},
            "Min": {"color": "lightgrey", "width": 0, "fill": "tonexty", "fillcolor": None},
        },
        file_path=file_path,
        height=500,
        width=750,
    )


def cot_chart_new(
    df,
    title=None,
    start=None,
    titles=None,
    columns=None,
    ex2020=False,
    freq="W-TUE",
    file_path=None,
    rows=2,
    price_override_name=None,
):
    """
    COT chart
    Example:
        import ecm.cmds.core.core.pyg as pyg
        c = pyg.get_data(pyg.reports_db().data, name="COA Comdty_cot_net_chart")
        cot_chart(df=c, title='COA Net position vs Price',
                  start=dt.datetime(2018,1,1),
                  columns=["Net", "PX_LAST", "Net OI"],
                  ex2020=False,
                  file_path="H:\\temp\\test_chart.html")
    """
    if isinstance(titles, str):
        titles = [titles]
    if columns is not None:
        data = []
        if isinstance(columns, list) and isinstance(columns[0], list):
            for clmns in columns:
                data.append(df[clmns])
        else:
            data.append(df[columns])
    else:
        data.append(df.copy())
    plot_cols = dict()
    for i, data_ in enumerate(data):
        if start is not None:
            data_ = data_.loc[data_.index >= start, :]
        if data_.iloc[:, 0].last_valid_index().year < data_.index[-1].year:
            data_.drop(data_.index[data_.index > data_.iloc[:, 0].last_valid_index()], axis=0, inplace=True)
        if "CTA LN4" in data_.columns:
            data0 = data_.iloc[:, 0]
            data1 = data_.iloc[:, -2]
            price = data_.iloc[:, 1]
            cta_ln4 = data_.iloc[:, -1]
        else:
            data0 = data_.iloc[:, 0]
            data1 = data_.iloc[:, -1]
            price = data_.iloc[:, 1]
            cta_ln4 = pd.DataFrame()

        data_by_yr0 = ts.data_by_year(data0, start_day=1, start_month=1, freq="W")
        data_by_yr1 = ts.data_by_year(data1, start_day=1, start_month=1, freq="W")
        if ex2020 and 2020 in data_by_yr0.columns:
            data_by_yr0.drop([2020], axis=1, inplace=True)
            data_by_yr1.drop([2020], axis=1, inplace=True)
        cur_yr = data_by_yr0.columns[-1]
        dts = pd.date_range(dt.datetime(cur_yr, 1, 1), dt.datetime(cur_yr, 12, 31), freq=freq)
        actual_dts = data_[data_.index >= dt.datetime(cur_yr, 1, 1)].index
        if len(actual_dts) > 0:
            loc_ = len(actual_dts)
            dts = actual_dts.union(dts[loc_:])
        if len(dts) < data_by_yr0.shape[0]:
            data_by_yr0 = data_by_yr0.iloc[: len(dts), :]
            data_by_yr1 = data_by_yr1.iloc[: len(dts), :]
        data_by_yr0["Date"] = dts
        data_by_yr0 = data_by_yr0.set_index("Date")
        data_by_yr1["Date"] = dts
        data_by_yr1 = data_by_yr1.set_index("Date")
        price = price.loc[price.index >= dt.datetime(cur_yr, 1, 1)]
        price = price.reindex(dts)
        price = price.to_frame("price") if not price_override_name else price.to_frame(price_override_name)
        if not cta_ln4.empty:
            cta_ln4 = cta_ln4.loc[cta_ln4.index >= dt.datetime(cur_yr, 1, 1)]
            cta_ln4 = cta_ln4.reindex(dts)
            cta_ln4 = cta_ln4.to_frame("CTA LN4")
            plot_cols[f"data_p2y2c{i+1}"] = cta_ln4
            plot_cols[f"y_axis_title_p2y2c{i+1}"] = "CTA LN4"
            plot_cols[f"dtick_p2y2c{i+1}"] = 0.2
            plot_cols[f"dtick_p2y1c{i+1}"] = 0.2
            if "Short" in data_.columns:
                plot_cols[f"axis_reversed_p2y2c{i+1}"] = True
                plot_cols[f"axis_reversed_p2y2c{i+1}"] = True

        max = data_by_yr1.iloc[:, -6:-1].max(axis=1)
        min = data_by_yr1.iloc[:, -6:-1].min(axis=1)
        new_data = pd.concat([data_by_yr1.iloc[:, -1], max, min], axis=1)
        new_data.columns = ["Net/OI", "Max", "Min"]

        plot_cols[f"data_p1y1c{i+1}"] = data_by_yr0
        plot_cols[f"y_axis_title_p1y1c{i+1}"] = "Contracts"
        plot_cols[f"data_p1y2c{i+1}"] = price
        plot_cols[f"y_axis_title_p1y2c{i+1}"] = "Price"
        plot_cols[f"data_p2y1c{i+1}"] = new_data
        plot_cols[f"y_axis_title_p2y1c{i+1}"] = "Net/OI"
    height = 500
    if len(data) > 1:
        width = 750 * len(data)
    else:
        width = 750
    ret_fig = PlottingLib(
        title=title,
        column_titles=titles,
        showlegend=True,
        secondary_y=True,
        rows=rows,
        col=len(data),
        highlight_dict={
            "price" if not price_override_name else price_override_name: {"mode": "lines+markers", "color": "black", "width": 2, "dash": "dash"},
            data_by_yr0.columns[-1]: {"mode": "lines+markers", "color": "red", "width": 2},
            "Net/OI": {"mode": "lines+markers", "color": "red", "width": 2},
            "Max": {"color": "lightgrey", "width": 0},
            "Min": {"color": "lightgrey", "width": 0, "fill": "tonexty", "fillcolor": None},
            "CTA LN4": {"color": "blue", "mode": "lines+markers"},
        },
        file_path=file_path,
        height=height,
        width=width,
        **plot_cols,
    ).fig
    ret_fig.update_xaxes(dtick="M1", tickformat="%b")
    return ret_fig


def has_subplot(fig, row, col) -> bool:
    return any(fig.select_yaxes(row=row, col=col))


def cot_px_ohlc_chart(
    data: tp.List[pd.DataFrame] = None,
    title=None,
    column_titles=None,
    cot_start=None,
    **kwargs,
):
    plot_args = dict()
    num_plots = 0
    rows = 1
    if data is None:
        raise ValueError("Data must be provided as a list of DataFrames")
    required = ["PX_OPEN", "PX_HIGH", "PX_LOW", "PX_LAST"]
    if isinstance(cot_start, str):
        cot_start = pd.to_datetime(cot_start)
    if isinstance(cot_start, dt.datetime):
        center = cot_start
        pad = dt.timedelta(days=90 - 14)
        min_date = center - pad
    else:
        min_date = None
    for i, df in enumerate(data, start=1):
        if isinstance(df, pd.DataFrame):
            if min_date is not None:
                df = df.loc[df.index >= min_date, :]
            if not all(col in df.columns for col in required):
                raise ValueError(f"DataFrame must contain {', '.join(required)}")
            else:
                data_ohlc = df[["PX_OPEN", "PX_HIGH", "PX_LOW", "PX_LAST"]]
                if i != 1:
                    plot_args[f"data_c{i}"] = data_ohlc
                    plot_args[f"ohlc_p1c{i}"] = True
                else:
                    plot_args["data"] = data_ohlc
                    plot_args["ohlc_p1"] = True
            if "VOLUME" in df.columns and not df["VOLUME"].replace(0.0, np.nan).isna().all():
                data_vol = df[["VOLUME"]]
                plot_args[f"data_c{i}p2y1"] = data_vol
                plot_args[f"y_axis_title_c{i}p2y1"] = "Volume"
                rows = 2
            if "FUT_AGGTE_OPEN_INT" in df.columns and not df["FUT_AGGTE_OPEN_INT"].replace(0.0, np.nan).isna().all():
                data_fut_oi = df[["FUT_AGGTE_OPEN_INT"]].rename(columns={"FUT_AGGTE_OPEN_INT": "OI"})
                plot_args[f"data_c{i}p2y2"] = data_fut_oi
                plot_args[f"y_axis_title_c{i}p2y2"] = "OI"
                rows = 2
            if "HOLDINGS" in df.columns and not df["HOLDINGS"].replace(0.0, np.nan).isna().all():
                data_holdings = df[["HOLDINGS"]]
                plot_args[f"data_c{i}p2y2"] = data_holdings
                plot_args[f"y_axis_title_c{i}p2y2"] = "Holdings ($M)"
                rows = 2
            num_plots += 1
    highlight_dict = {
        "OI": {"color": "blue"},
        "VOLUME": {"mode": "bars", "bar_color": "lightblue", "width": 1},
        "HOLDINGS": {"color": "blue"},
    }
    plot_args["highlight_dict"] = highlight_dict
    plot_args["x_axis_title"] = "Date"
    plot_args["y_axis_title"] = "Price"
    width = 750 * num_plots
    height = 500
    fig = PlottingLib(
        title=title,
        column_titles=column_titles,
        tickformat_p1="%b %d",
        dtick="M1",
        rows=rows,
        col=num_plots,
        width=width,
        height=height,
        **plot_args,
    )._fig
    no_highlight = kwargs.get("no_highlight", False)
    if isinstance(cot_start, dt.datetime) and not no_highlight:
        center = cot_start
        pad = dt.timedelta(days=90 - 14)
        fig.add_vrect(
            x0=cot_start,
            x1=cot_start + dt.timedelta(7),
            annotation_text=center.strftime("%Y-%m-%d"),
            annotation_position="top left",
            annotation_font_size=10,
            fillcolor="pink",
            opacity=0.25,
            line_width=0,
        )
        fig.update_xaxes(
            autorange=False,
            range=[center - pad, max([d.x[-1] for d in fig.data])],
            dtick="M1",
            tickformat="%b %d",
        )
    return fig


def cot_chart_2col(
    df,
    df1=None,
    start=None,
    titles=None,
    columns=None,
    columns1=None,
    ex2020=False,
    freq="W-TUE",
    file_path=None,
):
    """
    COT chart
    Example:
        import ecm.cmds.core.core.pyg as pyg
        c = pyg.get_data(pyg.reports_db().data, name="COA Comdty_cot_net_chart")
        cot_chart_2col(df=c, titles=['COA Long position vs Price', 'COA Short position vs Price'],
                      start=dt.datetime(2018,1,1),
                      columns=["Long", "PX_LAST", "Long OI"],
                      columns1=["Short", "PX_LAST", "Short OI"],
                      ex2020=False,
                      file_path="H:\\temp\\test_chart.html")
    """
    if df1 is None:
        data_ = df[columns]
        data1_ = df[columns1]
    else:
        if columns is not None:
            data_ = df[columns]
        else:
            data_ = df.copy()
        if columns1 is not None:
            data1_ = df1[columns1]
        else:
            data1_ = df1.copy()
    if start is not None:
        data_ = data_.loc[data_.index >= start, :]
        data1_ = data1_.loc[data1_.index >= start, :]

    data0 = data_.iloc[:, 0]
    data1 = data_.iloc[:, -1]
    price = data_.iloc[:, 1]
    data_by_yr0 = ts.data_by_year(data0, start_day=1, start_month=1, freq="W")
    data_by_yr1 = ts.data_by_year(data1, start_day=1, start_month=1, freq="W")
    if ex2020 and 2020 in data_by_yr0.columns:
        data_by_yr0.drop([2020], axis=1, inplace=True)
        data_by_yr1.drop([2020], axis=1, inplace=True)
    cur_yr = data_by_yr0.columns[-1]
    dts = pd.date_range(dt.datetime(cur_yr, 1, 1), dt.datetime(cur_yr, 12, 31), freq=freq)
    actual_dts = data_[data_.index >= dt.datetime(cur_yr, 1, 1)].index
    if len(actual_dts) > 0:
        loc_ = len(actual_dts)
        dts = actual_dts.union(dts[loc_:])
    if len(dts) < data_by_yr0.shape[0]:
        data_by_yr0 = data_by_yr0.iloc[: len(dts), :]
        data_by_yr1 = data_by_yr1.iloc[: len(dts), :]
    data_by_yr0["Date"] = dts
    data_by_yr0 = data_by_yr0.set_index("Date")
    data_by_yr1["Date"] = dts
    data_by_yr1 = data_by_yr1.set_index("Date")
    price = price.loc[price.index >= dt.datetime(cur_yr, 1, 1)]
    price = price.reindex(dts)
    price = price.to_frame("price")

    max = data_by_yr1.iloc[:, -6:-1].max(axis=1)
    min = data_by_yr1.iloc[:, -6:-1].min(axis=1)
    new_data = pd.concat([data_by_yr1.iloc[:, -1], max, min], axis=1)
    new_data.columns = ["Net/OI", "Max", "Min"]

    data01 = data1_.iloc[:, 0]
    data11 = data1_.iloc[:, -1]
    price1 = data1_.iloc[:, 1]
    data_by_yr01 = ts.data_by_year(data01, start_day=1, start_month=1, freq="W")
    data_by_yr11 = ts.data_by_year(data11, start_day=1, start_month=1, freq="W")
    if ex2020 and 2020 in data_by_yr01.columns:
        data_by_yr01.drop([2020], axis=1, inplace=True)
        data_by_yr11.drop([2020], axis=1, inplace=True)
    cur_yr = data_by_yr01.columns[-1]
    dts = pd.date_range(dt.datetime(cur_yr, 1, 1), dt.datetime(cur_yr, 12, 31), freq=freq)
    actual_dts = data_[data_.index >= dt.datetime(cur_yr, 1, 1)].index
    if len(actual_dts) > 0:
        loc_ = len(actual_dts)
        dts = actual_dts.union(dts[loc_:])
    if len(dts) < data_by_yr01.shape[0]:
        data_by_yr01 = data_by_yr01.iloc[: len(dts), :]
        data_by_yr11 = data_by_yr11.iloc[: len(dts), :]
    data_by_yr01["Date"] = dts
    data_by_yr01 = data_by_yr01.set_index("Date")
    data_by_yr11["Date"] = dts
    data_by_yr11 = data_by_yr11.set_index("Date")
    price1 = price1.loc[price1.index >= dt.datetime(cur_yr, 1, 1)]
    price1 = price1.reindex(dts)
    price1 = price1.to_frame("price")

    max1 = data_by_yr11.iloc[:, -6:-1].max(axis=1)
    min1 = data_by_yr11.iloc[:, -6:-1].min(axis=1)
    new_data1 = pd.concat([data_by_yr11.iloc[:, -1], max1, min1], axis=1)
    new_data1.columns = ["Net/OI", "Max", "Min"]
    return _line_chart(
        data=data_by_yr0,
        column_titles=titles,
        data_p1y2=price,
        data_p2y1=new_data,
        data_p1y1c2=data_by_yr01,
        data_p1y2c2=price1,
        data_p2y1c2=new_data1,
        y_axis_title="Contracts",
        p1y2_axis_title="Price",
        p2y2_axis_title="Price",
        p2y1_axis_title="Contracts/OI",
        secondary_y=True,
        subplots=2,
        col=2,
        height=500,
        width=1400,
        showlegend_c2=True,
        highlight_dict={
            "price": {"mode": "lines+markers", "color": "black", "width": 2, "dash": "dash"},
            data_by_yr0.columns[-1]: {"mode": "lines+markers", "color": "red", "width": 2},
            new_data.columns[0]: {"mode": "lines+markers", "color": "red", "width": 2},
            "Max": {"color": "lightgrey", "width": 0},
            "Min": {"color": "lightgrey", "width": 0, "fill": "tonexty", "fillcolor": None},
        },
        highlight_dict_c2={
            "price": {"mode": "lines+markers", "color": "black", "width": 2, "dash": "dash"},
            data_by_yr0.columns[-1]: {"mode": "lines+markers", "color": "red", "width": 2},
            new_data.columns[0]: {"mode": "lines+markers", "color": "red", "width": 2},
            "Max": {"color": "lightgrey", "width": 0},
            "Min": {"color": "lightgrey", "width": 0, "fill": "tonexty", "fillcolor": None},
        },
        file_path=file_path,
    )


def regression_chart(data, title, highlight_length=8, xaxis_title=None, yaxis_title=None):
    """
    Draw scatter points chart with regression line and +/- 2 std
    first column in data is y, 2nd is x
    """
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=data.iloc[:, 1],
            y=data.iloc[:, 0],
            text=data.index.strftime("%d/%b/%Y"),
            opacity=0.8,
            showlegend=True,
            mode="markers",
            name="Full sample",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=data.iloc[-highlight_length:, 1],
            y=data.iloc[-highlight_length:, 0],
            text=data.index.strftime("%d/%b/%Y"),
            opacity=0.8,
            showlegend=True,
            mode="markers",
            name=f"last {highlight_length} changes",
            marker=dict(color="black", size=12),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=data.iloc[-4:, 1],
            y=data.iloc[-4:, 0],
            text=data.index.strftime("%d/%b/%Y"),
            opacity=0.8,
            showlegend=True,
            mode="markers",
            name="last 3 changes",
            marker=dict(color="green", size=12),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=data.iloc[-1:, 1],
            y=data.iloc[-1:, 0],
            text=data.index.strftime("%d/%b/%Y"),
            opacity=0.8,
            showlegend=True,
            mode="markers",
            name="latest change",
            marker=dict(color="red", size=12),
        )
    )

    lm = sm.OLS(data.iloc[:, 0], data.iloc[:, 1]).fit()
    y_fit = data.iloc[:, 1] * lm.params.values
    fig.add_trace(
        go.Scatter(
            x=data.iloc[:, 1],
            y=y_fit,
            opacity=0.8,
            showlegend=True,
            mode="lines",
            name="fit",
            marker=dict(color="grey", size=2),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=data.iloc[:, 1],
            y=y_fit + 2 * lm.scale**0.5,
            mode="lines",
            name="+2sd",
            line=dict(color="grey", width=2, dash="dash"),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=data.iloc[:, 1],
            y=y_fit - 2 * lm.scale**0.5,
            mode="lines",
            name="-2sd",
            line=dict(color="grey", width=2, dash="dash"),
        )
    )
    fig.update_traces(hovertemplate="date: %{text} <br>x: %{x} <br>y: %{y}")
    fig.update_layout(
        title={
            "text": title,
            "x": 0.5,
            "xanchor": "center",
        },
        xaxis_title=xaxis_title,
        yaxis_title=yaxis_title,
        yaxis_tickformat=".1%",
        width=900,
        height=600,
    )
    return fig, lm



_change_type_map = {"W": "weeks", "D": "days", "M": "months"}


def price_vs_pos_chart(cot_data, highlight_length=4, title=None, n_weeks=1, **kwargs):
    cols = kwargs.get("columns", ["Net", "PX_LAST"])
    if len(cols) != 2:
        raise ValueError("Need exactly 2 columns")
    x_axis_title = kwargs.get("x_axis_title", "WoW Net Pos Change")
    y_axis_title = kwargs.get("y_axis_title", "WoW Price Change")
    change_type = kwargs.get("change_type", "W")
    if change_type not in ["W", "D", "M"]:
        change_label = "weeks"
    else:
        change_label = _change_type_map[change_type]

    is_spread = kwargs.get("is_spread", False)
    x_col = cols[0]
    y_col = cols[1]
    plot_data = cot_data[cols].copy()
    plot_data["Year"] = plot_data.index.year
    palette = ["green", "orange", "blue"]  # px.colors.qualitative.Safe # or any palette list
    years = sorted(plot_data["Year"].unique())
    color_map = {y: palette[i % len(palette)] for i, y in enumerate(years)}
    plot_data = plot_data.dropna()
    if is_spread:
        plot_data[y_col] = plot_data[y_col].diff(n_weeks)
    else:
        plot_data[y_col] = plot_data[y_col].pct_change(n_weeks) * 100
    plot_data[x_col] = plot_data[x_col].diff(n_weeks)
    plot_data[y_col] = plot_data[y_col]
    plot_data = plot_data.dropna()
    fig = go.Figure()

    highlight_data = plot_data.iloc[-(highlight_length + 1) : -1]  # noqa: E203
    if not highlight_length < len(plot_data):
        raise NotImplementedError("Unrecoverable chart.py:2370 rest_data fallback")
    rest_data = rest_data = plot_data.iloc[: -(highlight_length + 1)] if highlight_length < len(plot_data) else ...
    last_data = plot_data.iloc[-1:]
    lm = sm.OLS(plot_data.iloc[:, 1], plot_data.iloc[:, 0]).fit()
    y_fit = plot_data.iloc[:, 0] * lm.params.values
    fig.add_trace(go.Scatter(x=plot_data.iloc[:, 0], y=y_fit, opacity=0.8, showlegend=True, mode="lines", name="fit", marker=dict(color="grey", size=2)))
    fig.add_trace(
        go.Scatter(
            x=plot_data.iloc[:, 0],
            y=y_fit + 2 * lm.scale**0.5,
            mode="lines",
            name="+2sd",
            line=dict(color="grey", width=2, dash="dash"),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=plot_data.iloc[:, 0],
            y=y_fit - 2 * lm.scale**0.5,
            mode="lines",
            name="-2sd",
            line=dict(color="grey", width=2, dash="dash"),
        )
    )
    for y in reversed(years):
        sub = rest_data[rest_data["Year"] == y]
        fig.add_trace(
            go.Scatter(
                x=sub[x_col],
                y=sub[y_col],
                mode="markers",
                name=str(y),
                legendgroup=str(y),
                marker=dict(color=color_map[y], size=5),
            )
        )
    fig.add_trace(
        go.Scatter(
            x=highligh_data[x_col],
            y=highligh_data[y_col],
            mode="markers",
            name=f"last {highlight_length} {change_label}",
            legendgroup=f"last {highlight_length} changes",
            marker=dict(size=8, color="red", opacity=1, symbol="x"),
            text=[d.strftime("%Y-%m-%d") for d in highligh_data.index],
            hovertemplate="date: %{text}<br>x: %{x}<br>y: %{y}",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=last_data[x_col],
            y=last_data[y_col],
            mode="markers",
            name=f"{last_data.index[-1].strftime('%Y-%m-%d')}",
            legendgroup="latest",
            marker=dict(color="blue", size=10, line=dict(color="red", width=1)),
            text=[d.strftime("%Y-%m-%d") for d in last_data.index],
            hovertemplate="date: %{text}<br>x: %{x}<br>y: %{y}",
        )
    )
    fig.update_layout(
        width=750,
        height=500,
        legend_title_text="Year",
        title={
            "text": title,
            "x": 0.5,
            "xanchor": "center",
        },
        xaxis_title=x_axis_title,
        yaxis_title=y_axis_title,
    )
    return fig


def bar_fcast_chart(
    df: pd.Series | pd.DataFrame,
    split_index: int,
    fcst_legend: str = None,
    hist_legend: str = None,
    pattern_shape: str = None,
    fcst_color: str = "blue",
    hist_color: str = "green",
    single_column: bool = False,
    title: str = None,
    x_axis_title: str = None,
    y_axis_title: str = None,
    column_width: float = 0.5,
    **kwargs,
):
    if isinstance(df, pd.Series):
        df = df.to_frame()
    try:
        pd.infer_freq(df.index)
        hovertemplate = "%{x|%b/%d} %{y}"
        ONE_DAY = 24 * 60 * 60 * 1000
        column_width = (column_width * 40) * ONE_DAY
        not_datetime = False
    except Exception:
        hovertemplate = "%{x}|%{y}"
        df.index = df.index.astype(str)
        not_datetime = True
    if single_column and not fcst_legend:
        fcst_legend = hist_legend or df.columns[0]
    _df = df.copy().reset_index()
    split_location = _df.iloc[split_index].name
    if single_column:
        color_assignments = [hist_color if x != split_location else fcst_color for x in _df.index]
        if pattern_shape:
            pattern_assignments = [pattern_shape if x == split_location else "" for x in _df.index]
        else:
            pattern_assignments = [""] * len(df.index)
        dummy_data = pd.DataFrame(dict(fcst_legend=[0] * len(df.index)), index=df.index)
        if split_index == 0:
            dummy_data_2 = pd.DataFrame(dict(foo=[0] * (len(df.index))), index=df.index)
        else:
            dummy_data_2 = pd.DataFrame()
    else:
        color_assignments = [hist_color if x < split_location else fcst_color for x in _df.index]
        if pattern_shape:
            pattern_assignments = ["" if x < split_location else pattern_shape for x in _df.index]
        else:
            pattern_assignments = [""] * len(df.index)
        dummy_data = pd.DataFrame(dict(fcst_legend=[0] * len(df.index)), index=df.index)
        if split_index == 0:
            dummy_data_2 = pd.DataFrame(dict(foo=[0] * (len(df.index))), index=df.index)
        else:
            dummy_data_2 = pd.DataFrame()
    plot_data = pd.concat([df, dummy_data, dummy_data_2], axis=1)
    if not dummy_data_2.empty:
        columns = [
            f"{hist_legend or df.columns[0]}_plot",
            f"{fcst_legend or df.columns[0]}_dummy",
            hist_legend or df.columns[0],
        ]
    else:
        columns = [hist_legend or df.columns[0], f"{fcst_legend or df.columns[0]}_dummy"]
    plot_data.columns = columns
    plot_column = plot_data.columns[0]
    dummy_data_column = plot_data.columns[1]
    highlight_dict = {
        plot_column: {
            "mode": "bars",
            "color": color_assignments,
            "marker": dict(pattern=dict(shape=pattern_assignments)),
            "hovertemplate": hovertemplate,
        },
        dummy_data_column: {
            "mode": "bars",
            "color": fcst_color,
            "legendonly": True,
            "marker": dict(pattern=dict(shape=pattern_assignments)),
        },
    }
    if not dummy_data_2.empty:
        dumm_data_col = plot_data.columns[-1]
        highlight_dict[dumm_data_col] = {
            "mode": "bars",
            "color": hist_color,
            "legendonly": True,
        }
        plot_config = highlight_dict[plot_column]
        plot_config["showlegend"] = False  # type: ignore[index]
        highlight_dict[plot_column] = plot_config

    chart = _line_chart(
        data=plot_data,
        col=1,
        highlight_dict=highlight_dict,
        title=title,
        tickformat=None,
        x_axis_title=x_axis_title,
        y_axis_title=y_axis_title,
        **kwargs,
    )
    chart.data[0].name = df.columns[0]
    chart.data[1].name = fcst_legend or df.columns[0]
    if column_width:
        chart.update_traces(width=column_width, selector=dict(type="bar"))

    legend_traces = [trace for trace in chart.data if trace.showlegend]
    if len(legend_traces) == 3:
        shown_indices = [i for i, trace in enumerate(chart.data) if trace.showlegend]
        chart.data[shown_indices[1]].showlegend = False
    if not_datetime:
        chart.update_layout(xaxis_type="category")

    return chart


if __name__ == "__main__":


    def _make_sine(start_year=2020, end_year=2025, freq="D", amp=10, noise=1.5, seed=42):
        rng = np.random.default_rng(seed)
        idx = pd.date_range(f"{start_year}-01-01", f"{end_year}-12-31", freq=freq)
        day_of_year = idx.dayofyear.values
        vals = amp * np.sin(2 * np.pi * day_of_year / 365.25) + 0.05 * (idx.year - start_year)
        vals += rng.normal(0, noise, size=len(idx))
        return pd.Series(vals, index=idx, name="sine")

    base = _make_sine()
    test_series = base.copy()

    def test_seasonal_chart():
        fig = seasonal_chart(
            df=test_series,
            vs_avg=True,
            dash_from=test_series.index[-100],
            start_day=10,
            start_month=3,
            end_day=15,
            end_month=11,
            over_year=False,
            title="seasonal_chart",
            ytd_cum_sum=True,
        )
        dash_cols = [c for c in fig.data if "Forecast" in getattr(c, "name", "")]
        print("seasonal_chart dash traces:", len(dash_cols))
        return fig

    def test_seasonal_chart_new_multi():
        fig = seasonal_new(
            data=[test_series, test_series * 1.1],
            title=["A", "B"],
            vs_avg=True,
            dash_from=test_series.index[-100],
            start_day=10,
            start_month=3,
            end_day=15,
            end_month=11,
            over_year=False,
            width=1200,
            ytd_cum_sum=True,
        )
        print("seasonal_new columns:", len({tr.xaxis for tr in fig.data}))
        return fig

    def test_seasonal_chart_2col():
        df_side = test_series.to_frame("SideData").rolling(7).mean()
        fig = seasonal_chart_2col(
            df=test_series,
            df1=df_side,
            vs_avg=True,
            ytd=True,
            title="seasonal_chart_2col",
        )
        print("seasonal_chart_2col traces:", len(fig.data))
        return fig

    def test_seasonal_chart_2col_switch():
        df_side = test_series.to_frame("SideData").rolling(14).mean()
        fig = seasonal_chart_2col(
            df=test_series,
            df1=df_side,
            vs_avg=True,
            ytd=False,
            title="seasonal_chart_2col_switch",
            switch=True,
        )
        print("seasonal_chart_2col switch traces:", len(fig.data))
        return fig

    def test_alias_chart_new():
        fig = seasonal_chart_new(
            df=test_series,
            vs_avg=True,
            ytd=True,
            dash_from=test_series.index[-35],
            start_day=20,
            start_month=6,
            end_day=28,
            end_month=12,
            over_year=True,
            title="seasonal_chart_new alias",
        )
        print("seasonal_chart_new traces:", len(fig.data))
        return fig

    _figs = [
        test_seasonal_chart(),
        test_seasonal_chart_new_multi(),
        test_seasonal_chart_2col(),
        test_seasonal_chart_2col_switch(),
        test_alias_chart_new(),
    ]
    for f in _figs:
        f.show()
    print("Seasonal regression smoke tests complete")


    print("Testing seasonal_chart with dummy data...")

    date_range = pd.date_range(start="2018-01-01", end="2026-12-31", freq="W-MON")

    np.random.seed(42)
    base_value = 400000
    seasonal_pattern = 50000 * np.sin(np.arange(len(date_range)) * 2 * np.pi / 52)
    trend = np.linspace(0, 30000, len(date_range))
    noise = np.random.normal(0, 10000, len(date_range))
    stocks_values = base_value + seasonal_pattern + trend + noise

    data = pd.DataFrame({"Commercial stocks": stocks_values}, index=date_range)

    doe_date_range = pd.date_range(start="2024-01-01", end="2025-11-10", freq="W-MON")
    data_extra = {"doe": pd.DataFrame({"value": np.random.normal(400000, 20000, len(doe_date_range))}, index=doe_date_range)}

    dash_from_date = data_extra["doe"].dropna().index[-1]  # Should be around Nov 2025

    print(f"Data shape: {data.shape}")
    print(f"Data range: {data.index[0]} to {data.index[-1]}")
    print(f"Dash from date: {dash_from_date}")
    print("\nData sample:")
    print(data.head())



