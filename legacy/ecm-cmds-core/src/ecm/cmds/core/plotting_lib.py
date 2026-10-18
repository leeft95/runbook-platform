import re
import typing as tp
from pathlib import Path

import holidays
import numpy as np
import pandas as pd
import plotly as py
import plotly.graph_objects as go
from ecm.cmds.core.utils import convert_path_to_linux
from loguru import logger as log
from plotly.subplots import make_subplots
from pydantic import BaseModel


class PlotData(BaseModel):
    y: int
    p: int
    c: int
    data: tp.Optional[pd.DataFrame] = None
    highlight_dict: tp.Optional[tp.Dict[tp.Any, tp.Any]] = None
    y_axis_title: tp.Optional[str] = None
    x_axis_title: tp.Optional[str] = None
    y_reversed: bool = False
    mode: str = "lines"
    tickformat: str | None = "%b"
    dtick: str | float | None = "M1"
    hovertemplate: str = "%{x|%b/%d} %{y}"
    secondary_y: bool = False
    show_grid: bool = False
    title: tp.Optional[str] = None
    legend_group: str | None = None
    ohlc: bool = False
    ohlc_name: str = "OHLC"

    class Config:
        arbitrary_types_allowed = True


class PlotConfig(BaseModel):
    plots: tp.Dict[str, PlotData]
    highlight_dict: tp.Optional[tp.Dict[tp.Any, tp.Any]] = None
    column_titles: tp.Optional[tp.List[str]] = None
    width: int | None = 900  # Allow None for responsive mode
    height: int = 600
    row_heights: tp.Optional[tp.List[float]] = [1.0]
    specs: tp.Union[bool, tp.List[tp.List[tp.Union[dict, None]]]] = False
    subplots: int = 1
    showlegend: bool = True
    x_axis_title: str | None = None
    y_axis_title: str | None = None
    y_range: tp.List[tp.Any] | None = None
    tickformat: str = "%b"
    file_path: tp.Optional[tp.Union[str, Path]] = None
    secondary_y: bool = False
    vertical_spacing: float = 0.02
    dynamic_date_rangebreak: bool = False
    rangebreak_holidays: str | bool = "us"  # "us", "all", or False to disable rangebreaks
    _ohlc: bool = False

    class Config:
        extra = "allow"


class PlottingLib:
    """
    General purpose plotting class to generate plotly figures of n rows by n columns
    """
    _plot_regex = None
    _key_regex = r"(?P<c>{c})_(?P<p>{p})_(?P<y>{y})"

    def __init__(self, title: str = None, rows: int = 1, col: int = 1, debug=False, **kwargs):
        if self._plot_regex is None:
            raise NotImplementedError("Photographed plotting_lib.py line 74 regex suffix is clipped")
        self.title = title
        self.rows = rows
        self.cols = col
        self.debug = debug
        plot_columns_data: tp.Dict[str, tp.Any] = {}
        max_rows = 0
        max_columns = 0
        has_ohlc = False
        for k, v in kwargs.items():
            m_data = self._plot_regex.match(k)
            if m_data and any(m_data.groups()):
                g_dict = m_data.groupdict()
                plot_num = g_dict.get("p", 1)
                plot_num = 1 if not plot_num else int(plot_num[-1])
                y_num = g_dict.get("y", 1)
                y_num = 1 if not y_num else int(y_num[-1])
                column_num = g_dict.get("c", 1)
                column_num = 1 if not column_num else int(column_num[-1])
                key = self._gen_plot_key(plot_num, column_num, y_num)
            else:
                column_num = 1
                y_num = 1
                plot_num = 1
                key = self._gen_plot_key(plot_num, column_num, y_num)
            plot_args = plot_columns_data.get(key, dict(p=plot_num, y=y_num, c=column_num))
            max_rows = max(max_rows, plot_num)
            max_columns = max(max_columns, column_num)
            if k.startswith("data"):
                if isinstance(v, pd.Series):
                    v = v.to_frame()
                if isinstance(v, list):
                    raise ValueError(f"Data for c{column_num} p{plot_num} y{y_num}" " must be provided as an [photographed message clipped]")
                plot_args["data"] = v
            if k.startswith("axis_reversed_"):
                plot_args["y_reversed"] = v
            if k.startswith("y_axis_title_"):
                plot_args["y_axis_title"] = v
            if k.startswith("x_axis_title_"):
                plot_args["x_axis_title"] = v
            if k.startswith("hovertemplate"):
                plot_args["hovertemplate"] = v
            if k.startswith("mode_"):
                plot_args["mode"] = v
            if k.startswith("show_grid_"):
                plot_args["show_grid"] = v
            if k.startswith("show_grid_"):
                plot_args["show_grid"] = v
            if k.startswith("tickformat_"):
                plot_args["tickformat"] = v
            if k.startswith("showlegend_"):
                plot_args["showlegend"] = v
            if k.startswith("highlight_dict_"):
                plot_args["highlight_dict"] = v
            if k.startswith("legend_group_"):
                plot_args["legend_group"] = v
            if k.startswith("dtick_"):
                plot_args["dtick"] = v
            if k.startswith("name_ohlc_"):
                plot_args["ohlc_name"] = v
            if k.startswith("ohlc_"):
                plot_args["ohlc"] = v
                has_ohlc = True
            if k.startswith("title_"):
                if not (self.rows == 1 and self.cols == 1 and self.title):
                    plot_args["title"] = v
            if y_num == 2:
                plot_args["secondary_y"] = True
            if "column_titles" in kwargs.keys() and column_num >= 1:
                pass
            plot_columns_data[key] = plot_args
        plots = {k: PlotData(**v) for k, v in plot_columns_data.items()}
        self.plt_config = PlotConfig(plots=plots, _ohlc=has_ohlc, **kwargs)

        if max_columns != self.cols:
            raise ValueError(f"Generated plot data for {max_columns}" f" figure columns expecting {self.cols}")
        if max_rows != self.rows:
            raise ValueError(f"Generated plot data for {max_rows} figure rows expecting {rows}")
        self.plt_config.subplots = self.rows
        match self.rows:
            case 1:
                self.plt_config.row_heights = [1]
            case 2:
                self.plt_config.row_heights = [0.7, 0.3]
            case 3:
                self.plt_config.row_heights = [0.5, 0.25, 0.25]
            case _:
                max_height = self.plt_config.height
                first_plot = 1 - (0.6 * max_height) / 1000
                rest_plots = 1 - (0.2 * max_height) / 1000
                self.plt_config.row_heights = [first_plot] + [rest_plots] * (self.rows - 1)

        specs = []
        for col in range(1, self.cols + 1):
            spec_row = np.empty(self.rows, np.dtype(object))
            plts = self._get_plot(c=col)
            if plts is not None:
                if len(plts) == 1:
                    if plts[0].secondary_y:
                        spec_row[0] = dict(secondary_y=True, rowspan=self.rows)
                    else:
                        spec_row[0] = dict(secondary_y=False, rowspan=self.rows)
                else:
                    for plt in sorted(plts, key=lambda x: x.p):
                        if plt.secondary_y:
                            sy = dict(secondary_y=True, rowspan=1)
                            spec_row[plt.p - 1] = sy
                        else:
                            sy = dict(secondary_y=False, rowspan=1)
                            if not isinstance(spec_row[plt.p - 1], dict):
                                spec_row[plt.p - 1] = sy
                    if (len(np.where(spec_row == None)[0])) > 0:  # noqa: E711
                        plt_positions = np.array([x.p for x in plts])
                        diff = plt_positions[1:] - plt_positions[:-1]
                        index_where_multi_span = np.where(diff != 1)[0]
                        for i in index_where_multi_span:
                            row_def = spec_row[i]
                            if row_def is not None:
                                row_def["rowspan"] = 2
                                spec_row[i] = row_def
                specs.append(list(spec_row))
        specs = list(map(list, zip(*specs)))
        self.plt_config.specs = specs
        self._gen_fig()
        self._fig = self._add_data_to_figure()
        if self.plt_config.file_path:
            self.save_fig(self._fig, self.plt_config.file_path)

    def _get_all_plot_keys(self, c: int | None = None, y: int | None = None, p: int | None = None):
        keys = self.plt_config.plots.keys()
        ret_keys = []
        key_regex = self._key_regex.format(p=p or "[0-9]", y=y or "[0-9]", c=c or "[0-9]")
        regex = re.compile(key_regex)
        for key in keys:
            m_dict = regex.match(key)
            if m_dict:
                ret_keys.append(key)
        return ret_keys

    def _gen_plot_key(self, p, c, y):
        return f"{c}_{p}_{y}"

    def _generate_holiday_dates(self, start_year, end_year, holiday_set: str | bool = "us"):
        """Generate holiday dates for rangebreaks.

        Args:
            [TRANSCRIPTION GAP: lines237–238 absent between photos.]
            holiday_set: "us" for US holidays only, "all" for US + China holidays, True defaults to "us"
        """
        if holiday_set is True:
            holiday_set = "us"
        common_dates = []
        for year in range(start_year, end_year + 1):
            common_dates.append(f"{year}-12-25")  # Christmas
            common_dates.append(f"{year}-12-26")  # Boxing Day
            common_dates.append(f"{year}-01-01")  # New Year's Day

        us_holidays = holidays.UnitedStates(years=range(start_year, end_year + 1))
        holiday_dates = [d.strftime("%Y-%m-%d") for d in us_holidays.keys()]
        if holiday_set == "all":
            china_holidays = holidays.China(years=range(start_year, end_year + 1))
            holiday_dates += [d.strftime("%Y-%m-%d") for d in china_holidays.keys()]
        dates = pd.to_datetime(list(set(common_dates + holiday_dates)))
        return dates

    def _gen_plot(self, plt: PlotData, fig: go.Figure, data: pd.DataFrame, data_ohlc: pd.DataFrame):
        master_highlight = self.plt_config.highlight_dict
        plt_mode = plt.mode
        sec_y = plt.secondary_y
        p = plt.p
        c = plt.c
        if not data_ohlc.empty:
            trace = go.Candlestick(
                x=data_ohlc.index,
                open=data_ohlc["PX_OPEN"], high=data_ohlc["PX_HIGH"], low=data_ohlc["PX_LOW"], close=data_ohlc["PX_LAST"],
                name=plt.ohlc_name, legendgroup=plt.ohlc_name, showlegend=True,
                increasing=dict(line=dict(color="green"), fillcolor="green"),
                decreasing=dict(line=dict(color="red"), fillcolor="red"),
            )
            fig.add_trace(trace, secondary_y=sec_y, row=p, col=c)
            fig.update_xaxes(rangeslider_visible=False, row=p, col=c)
            if self.plt_config.rangebreak_holidays:
                data_ohlc.index = pd.to_datetime(data_ohlc.index)
                dates = self._generate_holiday_dates(min(data_ohlc.index.year), max(data_ohlc.index.year), self.plt_config.rangebreak_holidays)
                fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"]), dict(values=dates)], row=p, col=c)
        if data is not None and not data.empty:
            for i in data.columns:
                h_dict = plt.highlight_dict or master_highlight
                if h_dict is not None and i in h_dict.keys():
                    mod_dict = {}
                    hi_dict = {}
                    mod_keys = ["fill", "fillcolor", "mode", "bar_color", "marker", "showlegend", "legendonly", "blabel"]
                    for k, v in h_dict[i].items():
                        if k in mod_keys:
                            mod_dict[k] = v
                        else:
                            hi_dict[k] = v
                    mode = mod_dict.get("mode", plt_mode).lower()
                    legend_group = data[i].name
                    showlegend = True
                    match mode:
                        case "lines" | "lines+markers":
                            trace = go.Scatter(
                                x=data.index, y=data[i], showlegend=showlegend, name=i, mode=mode, line=hi_dict,
                                fillcolor=mod_dict.get("fillcolor", None), fill=mod_dict.get("fill", None),
                                legendgroup=legend_group, connectgaps=True
                            )
                        case "bars":
                            if "bar_color" in mod_dict.keys():
                                marker_color = mod_dict.get("bar_color")
                            else:
                                marker_color = None
                            if "marker" in mod_dict.keys():
                                marker = mod_dict.get("marker")
                            else:
                                marker = None
                            if "showlegend" in mod_dict.keys():
                                showlegend_bar = mod_dict.get("showlegend")
                            else:
                                showlegend_bar = showlegend
                            if "legendonly" in mod_dict.keys():
                                visible = "legendonly" if mod_dict.get("legendonly") else True
                            else:
                                visible = True
                            if "blabel" in mod_dict.keys():
                                if not isinstance(mod_dict["blabel"], dict):
                                    mod_dict["blabel"] = {}
                                textposition = mod_dict.get("blabel", {}).pop("textposition", "outside")
                                textformat = mod_dict.get("blabel", {}).pop("textformat", "%{text:.2s}")
                                mod_dict.get("blabel")
                                text = data[i]
                            else:
                                text = None
                                textposition = None
                                textformat = None
                            trace = go.Bar(
                                x=data.index if visible != "legendonly" else [None],
                                y=data[i] if visible != "legendonly" else [None],
                                showlegend=showlegend_bar, legendgroup=legend_group,
                                marker=marker, marker_color=marker_color, visible=True,
                                textposition=textposition, texttemplate=textformat, text=text
                            )
                        case _:
                            trace = None
                            log.error(f"{mode} is not configured skipping p{p}_c{c}")
                else:
                    mode = plt_mode
                    legend_group = data[i].name
                    showlegend = True
                    match mode:
                        case "lines" | "lines+markers":
                            trace = go.Scatter(
                                x=data.index, y=data[i], showlegend=showlegend, name=i,
                                mode=mode, line=dict(width=1), legendgroup=legend_group, connectgaps=True
                            )
                        case "bars":
                            trace = go.Bar(
                                x=data.index, y=data[i], showlegend=showlegend, name=i, legendgroup=legend_group,
                            )
                        case _:
                            trace = None
                            log.error(f"{mode} is not configured skipping p{p}_c{c}")
                if trace:
                    if self.debug:
                        log.info(f"Adding row:{p}|col:{c}")
                    fig.add_trace(trace, secondary_y=sec_y, row=p, col=c)
                    fig.update_yaxes(
                        title_text=plt.y_axis_title or self.plt_config.y_axis_title,
                        secondary_y=sec_y, autorange="reversed" if plt.y_reversed else True,
                        showgrid=False if sec_y else True, row=p, col=c,
                    )
                    if plt.show_grid:
                        fig.update_xaxes(showgrid=True)
                    if plt.tickformat != "%b":
                        fig.update_xaxes(tickformat=plt.tickformat, row=p, col=c)
                    else:
                        fig.update_xaxes(tickformat="%b", row=p, col=c)
                    if plt.dtick != "M1":
                        fig.update_xaxes(dtick=plt.dtick, row=p, col=c)
                    else:
                        fig.update_xaxes(dtick="M1", row=p, col=c)
            if self.plt_config.rangebreak_holidays:
                try:
                    data.index = pd.to_datetime(data.index)
                    dates = self._generate_holiday_dates(min(data.index.year), max(data.index.year), self.plt_config.rangebreak_holidays)
                    fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"]), dict(values=dates)], row=p, col=c)
                except Exception:
                    log.warning(f"Could not add rangebreaks to data in row:{p},col{c}" " as index is not an [photographed message clipped]")
        return fig

    def _get_plot(self, p: int | None = None, y: int | None = None, c: int = None) -> tp.List[PlotData] | None:
        all_keys = self._get_all_plot_keys(p=p, c=c, y=y)
        plts = [self.plt_config.plots[key] for key in all_keys]
        return plts if any(plts) else None

    _processed_legend_groups: tp.List[str] = []
    _ohlc_columns = ["PX_OPEN", "PX_HIGH", "PX_LOW", "PX_LAST"]

    def _plot(self, plt: PlotData, fig: go.Figure):
        ohlc = plt.ohlc
        data: pd.DataFrame = plt.data
        data_ohlc: pd.DataFrame = pd.DataFrame()
        if ohlc:
            try:
                data_ohlc = data[self._ohlc_columns]
                data = data.drop(columns=self._ohlc_columns)
            except KeyError as e:
                log.error(f"OHLC set to True for {plt.c}|{plt.p} but" f" {self._ohlc_columns} not in dataframe")
                raise e
        fig = self._gen_plot(plt=plt, fig=fig, data=data, data_ohlc=data_ohlc)
        return fig

    def _update_layouts(self):
        fig = self._fig
        title = self.title
        if self.plt_config._ohlc:
            extra_args = dict(xaxis_rangeslider_visible=False)
        else:
            extra_args = {}
        layout_args = {
            "title": {"text": title, "x": 0.5, "xanchor": "center"},
            "height": self.plt_config.height,
            "legend_tracegroupgap": 3,
            **extra_args,
        }
        if self.plt_config.width is not None:
            layout_args["width"] = self.plt_config.width
        fig.update_layout(**layout_args)
        if self.plt_config.dynamic_date_rangebreak:
            fig.update_xaxes(
                tickformatstops=[
                    dict(dtickrange=[None, 2628000000], value="%d %b %Y"),
                    dict(dtickrange=[2628000000, 31536000000], value="%b %Y"),
                    dict(dtickrange=[31536000000, None], value="%Y"),
                ]
            )
            fig.update_xaxes(tickformat=None, dtick=None)
        names = set()
        fig.for_each_trace(lambda trace: trace.update(showlegend=False) if (trace.name in names) else names.add(trace.name))
        self._add_subplot_titles()

    def _add_subplot_titles(self):
        """Add title annotations for subplots that have titles defined."""
        if self.rows == 1 and self.cols == 1 and self.title:
            return
        if self.plt_config.column_titles is not None:
            return
        fig = self._fig
        plts = self._get_plot()
        for plt in plts:
            if plt.title:
                subplot_index = (plt.p - 1) * self.cols + plt.c
                x_ref = f"x{subplot_index}" if subplot_index > 1 else "x"
                y_ref = f"y{subplot_index}" if subplot_index > 1 else "y"
                raise NotImplementedError("Photographed plotting_lib.py annotation coordinates537–539 unavailable")
                fig.add_annotation(
                    text=plt.title, xref=f"{x_ref} domain",
                    showarrow=False, xanchor="center", yanchor="bottom", yshift=10,
                    font=dict(size=11, color="black"),
                )

    def save_fig(self, fig, path: tp.Union[str, Path]):
        path = convert_path_to_linux(path)
        py.offline.plot(fig, auto_open=False, filename=path)

    def _add_data_to_figure(self):
        fig = self._fig
        plts = self._get_plot()
        for plt in sorted(plts, key=lambda x: x.c):
            fig = self._plot(plt, fig)
        self._update_layouts()
        return fig

    def _gen_fig(self):
        specs = self.plt_config.specs
        if self.cols == 1 and self.rows == 1:
            self._fig = make_subplots(specs=specs, x_title=self.plt_config.x_axis_title)
        else:
            self._fig = make_subplots(
                rows=self.rows, cols=self.cols,
                x_title=self.plt_config.x_axis_title or list(self.plt_config.plots.values())[0].data.index.name,
                row_heights=self.plt_config.row_heights, shared_xaxes=True,
                vertical_spacing=self.plt_config.vertical_spacing, specs=specs,
                column_titles=self.plt_config.column_titles,
                horizontal_spacing=self.plt_config.horizontal_spacing,
                print_grid=True if self.debug else False,
            )

    def show(self):
        self._fig.show()

    @property
    def fig(self):
        return self._fig


if __name__ == "__main__":

    import datetime as dt

    dts = pd.date_range("2024-01-01", "2024-01-15")
    y = list(map(lambda x: x * 2 if dts[x] >= dt.datetime(2024, 1, 9) else x, range(0, len(dts))))
    y2 = list(map(lambda x: x * 0, range(0, len(dts))))
    color_assignments = list(map(lambda x: "green" if dts[x] > dt.datetime(2024, 1, 9) else "blue", range(0, len(dts))))
    pattern_shape = list(map(lambda x: "\\" if dts[x] > dt.datetime(2024, 1, 9) else "", range(0, len(dts))))
    data = pd.DataFrame(dict(x=dts, y=y, y2=y2)).set_index("x")
    pl = PlottingLib(
        title="TEST BARS", rows=1, cols=1, data=data,
        tickformat_p1=None,
        highlight_dict={
            "y": {
                "mode": "bars", "bar_color": color_assignments,
                "marker": dict(pattern=dict(shape=pattern_shape)),
                "blabel": {"textposition": "outside", "textformat": "%{text}"},
            },
            "y2": {
                "mode": "bars", "bar_color": "green", "legendonly": True,
                "marker": dict(pattern=dict(shape="\\")),
            },
        },
    )  # Closing delimiter inferred; the final photograph ends at line671.
