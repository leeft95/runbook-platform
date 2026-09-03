# General purpose plotting library

import math
import typing as tp
from collections.abc import Mapping
from enum import Enum

import pandas as pd
import plotly
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from pydantic import BaseModel, ConfigDict, model_validator


class PlotType(str, Enum):
    line = "line"
    bar = "bar"
    scatter = "scatter"
    line_scatter = "line+scatter"
    pie = "pie"
    histogram = "histogram"
    OHLC = "OHLC"


class GraphlyTraceSpec(BaseModel):
    plot_type: PlotType | str
    row: int = 1
    col: int = 1
    data: pd.DataFrame | None = None
    columns: list[str] | None = None
    title: str | None = None
    x_axis_title: str | None = None
    y_axis_title: str | None = None
    reversed_y: bool = False
    trace_style: dict[str, tp.Any] | None = None
    series_styles: dict[str, dict[str, tp.Any]] | None = None
    name_map: dict[str, str] | None = None
    secondary_y: bool = False
    hovertemplate: str | None = None
    show_legend: bool = True
    show_grid: bool = True
    show_rangeslider: bool | None = None
    use_rangebreaks: bool | None = None
    holiday_countries: list[str] | None = None

    model_config = ConfigDict(arbitrary_types_allowed=True)


class GraphlyFigureSpec(BaseModel):
    traces: list[GraphlyTraceSpec]
    data: pd.DataFrame | None = None
    title: str | None = None
    n_rows: int = 1
    n_cols: int = 1
    width: int | None = None
    height: int | None = None
    row_heights: list[float] | None = None
    column_widths: list[float] | None = None
    shared_xaxes: bool = False
    shared_yaxes: bool = False
    horizontal_spacing: float | None = None
    vertical_spacing: float | None = None
    show_rangeslider: bool = False
    tickformat: str | None = "%b"
    dtick: str | int | float | None = "M1"
    use_rangebreaks: bool = True
    holiday_countries: list[str] | None = None
    legend_groups: bool = False

    model_config = ConfigDict(arbitrary_types_allowed=True)


class PlotlyPlotDef(BaseModel):
    """Definition for a single subplot payload.

    Style fields:
    - ``trace_style`` applies to every trace generated from ``data``.
    - ``series_styles`` applies per column name and overrides ``trace_style``.
      Nested style dicts are deep-merged so partial overrides are supported.
    """

    data: pd.DataFrame
    title: str | None = None
    row: int | None = None
    col: int | None = None
    x_axis_title: str | None = None
    y_axis_title: str | None = None
    reversed_y: bool = False
    plot_type: PlotType = PlotType.line
    tickformat: str | None = None
    dtick: str | int | float | None = None
    hovertemplate: str | None = "%{x|%b/%d} %{y}"
    secondary_y: bool = False
    show_legend: bool = True
    show_grid: bool = True
    show_rangeslider: bool | None = None
    use_rangebreaks: bool | None = None
    holiday_countries: list[str] | None = None
    # kwargs passed into each trace constructor for this subplot.
    trace_style: dict[str, tp.Any] | None = None
    # Per-column kwargs keyed by dataframe column name.
    series_styles: dict[str, dict[str, tp.Any]] | None = None

    model_config = ConfigDict(arbitrary_types_allowed=True)


class PlotlyFigureDef(BaseModel):
    plots: list[PlotlyPlotDef]
    title: str | None = None
    n_rows: int = 1
    n_cols: int = 1
    width: int | None = None  # dynamic width based on number of columns
    height: int | None = None  # dynamic height based on number of rows

    @staticmethod
    def width_for_cols(n_cols: int) -> int:
        """Handle width for cols."""
        return max(1, n_cols) * 700

    @staticmethod
    def height_for_rows(n_rows: int) -> int:
        """Handle height for rows."""
        return max(1, n_rows) * 450

    @model_validator(mode="before")
    @classmethod
    def _set_default_dimensions(cls, values):
        if not isinstance(values, dict):
            return values
        n_cols = values.get("n_cols", 1) or 1
        n_rows = values.get("n_rows", 1) or 1
        if values.get("width") is None:
            values["width"] = cls.width_for_cols(n_cols)
        if values.get("height") is None:
            values["height"] = cls.height_for_rows(n_rows)
        return values

    def get_width(self, n_cols: int) -> int:
        """Return width."""
        base_width = 600
        return base_width * n_cols

    def get_height(self, n_rows: int) -> int:
        """Return height."""
        base_height = 400
        return base_height * n_rows


class GraphlyPlotter:
    _DEFAULT_DATETIME_HOVERTEMPLATE = "%{x|%b/%d} %{y}"

    def __init__(
        self,
        title: str | None = None,
        n_rows: int = 1,
        n_cols: int = 1,
        width: int | None = None,
        height: int | None = None,
        auto_layout: bool = True,
        row_heights: list[float] | None = None,
        column_widths: list[float] | None = None,
        shared_xaxes: bool = False,
        shared_yaxes: bool = False,
        horizontal_spacing: float | None = 0.08,
        vertical_spacing: float | None = 0.02,
        dtick: str | int | float | None = "M1",
        tickformat: str | None = "%b",
        show_rangeslider: bool = False,
        use_rangebreaks: bool = True,
        holiday_countries: list[str] | None = None,
        legend_groups: bool = False,
    ):
        self.title = title
        self.n_rows = n_rows
        self.n_cols = n_cols
        self.width = width
        self.height = height
        self.auto_layout = auto_layout
        self.row_heights = row_heights
        self.column_widths = column_widths
        self.shared_xaxes = shared_xaxes
        self.shared_yaxes = shared_yaxes
        self.horizontal_spacing = horizontal_spacing
        self.vertical_spacing = vertical_spacing
        self.dtick = dtick
        self.tickformat = tickformat
        self.show_rangeslider = show_rangeslider
        self.use_rangebreaks = use_rangebreaks
        self.holiday_countries = holiday_countries if holiday_countries is not None else ["US"]
        self.legend_groups = legend_groups

    def plot_spec(self, fig_spec: GraphlyFigureSpec) -> go.Figure:
        """Handle plot spec."""
        self._validate_trace_specs(fig_spec)
        plot_defs = [self._trace_spec_to_plot_def(trace_spec, fig_spec.data) for trace_spec in fig_spec.traces]
        return GraphlyPlotter(
            title=fig_spec.title if fig_spec.title is not None else self.title,
            n_rows=fig_spec.n_rows,
            n_cols=fig_spec.n_cols,
            width=fig_spec.width,
            height=fig_spec.height,
            auto_layout=False,
            row_heights=fig_spec.row_heights,
            column_widths=fig_spec.column_widths,
            shared_xaxes=fig_spec.shared_xaxes,
            shared_yaxes=fig_spec.shared_yaxes,
            horizontal_spacing=fig_spec.horizontal_spacing,
            vertical_spacing=fig_spec.vertical_spacing,
            dtick=fig_spec.dtick,
            tickformat=fig_spec.tickformat,
            show_rangeslider=fig_spec.show_rangeslider,
            use_rangebreaks=fig_spec.use_rangebreaks,
            holiday_countries=fig_spec.holiday_countries,
            legend_groups=fig_spec.legend_groups,
        ).plot(plot_defs, title=fig_spec.title)

    def build_definition(self, plots: list[PlotlyPlotDef], title: str | None = None) -> PlotlyFigureDef:
        """Build definition."""
        n_rows = self.n_rows
        n_cols = self.n_cols
        if self.auto_layout and (n_rows == 1 and n_cols == 1 and len(plots) > 1):
            n_cols = max(1, int(math.ceil(math.sqrt(len(plots)))))
            n_rows = max(1, int(math.ceil(len(plots) / n_cols)))

        return PlotlyFigureDef(
            plots=plots,
            title=title if title is not None else self.title,
            n_rows=n_rows,
            n_cols=n_cols,
            width=self.width,
            height=self.height,
        )

    def plot(self, plots: list[PlotlyPlotDef], title: str | None = None) -> go.Figure:
        """Handle plot."""
        if not plots:
            raise ValueError("plots is required.")
        fig_def = self.build_definition(plots, title=title)
        explicit_positions = self._uses_explicit_positions(fig_def.plots)
        if explicit_positions:
            self._validate_plot_positions(fig_def.plots, fig_def.n_rows, fig_def.n_cols)
            plots_by_cell = self._group_defs_by_cell(fig_def.plots)
            subplot_titles = self._explicit_subplot_titles(plots_by_cell, fig_def.n_rows, fig_def.n_cols)
            subplot_specs = self._explicit_subplot_specs(plots_by_cell, fig_def.n_rows, fig_def.n_cols)
        else:
            subplot_titles = [p.title or "" for p in fig_def.plots] if len(fig_def.plots) > 1 else None
            subplot_specs = []
            for r in range(fig_def.n_rows):
                row_specs: list[dict[str, tp.Any]] = []
                for c in range(fig_def.n_cols):
                    i = r * fig_def.n_cols + c
                    if i < len(fig_def.plots):
                        row_specs.append(self._subplot_spec_for_cell([fig_def.plots[i]]))
                    else:
                        row_specs.append({"secondary_y": False})
                subplot_specs.append(row_specs)
        fig = make_subplots(
            rows=fig_def.n_rows,
            cols=fig_def.n_cols,
            subplot_titles=subplot_titles,
            specs=subplot_specs,
            row_heights=self.row_heights,
            column_widths=self.column_widths,
            shared_xaxes=self.shared_xaxes,
            shared_yaxes=self.shared_yaxes,
            horizontal_spacing=self.horizontal_spacing,
            vertical_spacing=self.vertical_spacing,
        )
        should_group_legend = self.legend_groups and len(fig_def.plots) > 1
        legend_seen_names: set[str] = set()
        legend_group_colors: dict[str, str] = {}
        color_index_state = [0]

        for i, plot_def in enumerate(fig_def.plots):
            if explicit_positions:
                row = tp.cast(int, plot_def.row)
                col = tp.cast(int, plot_def.col)
            else:
                row = (i // fig_def.n_cols) + 1
                col = (i % fig_def.n_cols) + 1
            self._add_plot(
                fig,
                plot_def,
                row=row,
                col=col,
                group_legend=should_group_legend,
                legend_seen_names=legend_seen_names,
                legend_group_colors=legend_group_colors,
                color_index_state=color_index_state,
            )
            x_rangebreaks = self._resolved_rangebreaks(plot_def)
            x_tickformat, x_dtick = self._resolved_x_tick_settings(plot_def)

            fig.update_xaxes(
                title_text=plot_def.x_axis_title,
                tickformat=x_tickformat,
                dtick=x_dtick,
                rangebreaks=x_rangebreaks,
                rangeslider_visible=self.show_rangeslider
                if plot_def.show_rangeslider is None
                else plot_def.show_rangeslider,
                showgrid=plot_def.show_grid,
                row=row,
                col=col,
            )
            fig.update_yaxes(
                title_text=plot_def.y_axis_title,
                showgrid=plot_def.show_grid,
                autorange="reversed" if plot_def.reversed_y else True,
                row=row,
                col=col,
                secondary_y=plot_def.secondary_y
            )

        showlegend = any(p.show_legend for p in fig_def.plots)
        fig.update_layout(
            title=fig_def.title,
            width=fig_def.width,
            height=fig_def.height,
            showlegend=showlegend,
            legend_tracegroupgap=3,
        )
        return fig

    def _validate_trace_specs(self, fig_spec: GraphlyFigureSpec) -> None:
        """Validate trace specs."""
        if fig_spec.n_rows < 1 or fig_spec.n_cols < 1:
            raise ValueError("n_rows and n_cols must be positive integers.")
        if not fig_spec.traces:
            raise ValueError("traces is required.")
        for trace_spec in fig_spec.traces:
            if trace_spec.row < 1 or trace_spec.col < 1:
                raise ValueError("GraphlyTraceSpec row and col must be positive integers.")
            if trace_spec.row > fig_spec.n_rows or trace_spec.col > fig_spec.n_cols:
                raise ValueError(
                    f"GraphlyTraceSpec position ({trace_spec.row}, {trace_spec.col}) exceeds subplot grid {fig_spec.n_rows}x{fig_spec.n_cols}."
                )
            self._resolve_trace_plot_type(trace_spec)
            self._resolve_trace_dataframe(trace_spec, fig_spec.data)

    def _resolve_trace_plot_type(self, trace_spec: GraphlyTraceSpec) -> PlotType:
        """Resolve trace plot type."""
        try:
            return PlotType(trace_spec.plot_type)
        except ValueError as exc:
            raise ValueError(f"Unsupported plot type {trace_spec.plot_type!r}.") from exc

    def _resolve_trace_dataframe(self, trace_spec: GraphlyTraceSpec, shared_data: pd.DataFrame | None) -> pd.DataFrame:
        """Resolve trace dataframe."""
        df = trace_spec.data if trace_spec.data is not None else shared_data
        if df is None:
            raise ValueError("Each trace must provide data directly or rely on a shared figure-level dataframe.")
        if not isinstance(df, pd.DataFrame):
            raise TypeError("Trace data must be a pandas DataFrame.")
        return df

    def _resolve_trace_columns(
        self, trace_spec: GraphlyTraceSpec, df: pd.DataFrame, plot_type: PlotType
    ) -> pd.DataFrame:
        """Resolve trace columns."""
        if plot_type == PlotType.OHLC:
            if trace_spec.columns is None:
                cols = {str(c).lower(): c for c in df.columns}
                required = ["open", "high", "low", "close"]
                if not all(name in cols for name in required):
                    raise ValueError(
                        "OHLC traces require columns [open, high, low, close] or explicit column selection."
                    )
                selected = [cols[name] for name in required]
            else:
                if len(trace_spec.columns) != 4:
                    raise ValueError("OHLC traces require exactly four columns: [open, high, low, close].")
                missing = [name for name in trace_spec.columns if name not in df.columns]
                if missing:
                    raise ValueError(f"Trace columns not found in dataframe: {missing}.")
                selected = list(trace_spec.columns)
            out = df.loc[:, selected].copy()
            out.columns = ["open", "high", "low", "close"]
            return out

        if trace_spec.columns is None:
            return df.copy()

        missing = [name for name in trace_spec.columns if name not in df.columns]
        if missing:
            raise ValueError(f"Trace columns not found in dataframe: {missing}.")
        return df.loc[:, list(trace_spec.columns)].copy()

    def _apply_name_map(
        self,
        df: pd.DataFrame,
        name_map: dict[str, str] | None,
        series_styles: dict[str, dict[str, tp.Any]] | None,
    ) -> tuple[pd.DataFrame, dict[str, dict[str, tp.Any]] | None]:
        """Handle apply name map."""
        if not name_map:
            return df, series_styles

        missing = [name for name in name_map if name not in map(str, df.columns)]
        if missing:
            raise ValueError(f"name_map contains unknown columns: {missing}.")

        rename_map = {column: name_map.get(str(column), str(column)) for column in df.columns}
        renamed = df.rename(columns=rename_map)
        if not series_styles:
            return renamed, None

        normalized_styles: dict[str, dict[str, tp.Any]] = {}
        for source_name, final_name in rename_map.items():
            style = series_styles.get(final_name)
            if style is None:
                style = series_styles.get(str(source_name))
            if style is not None:
                normalized_styles[str(final_name)] = style
        for key, style in series_styles.items():
            if key in normalized_styles:
                continue
            if key in map(str, renamed.columns):
                normalized_styles[key] = style
        return renamed, normalized_styles or None

    def _trace_spec_to_plot_def(self, trace_spec: GraphlyTraceSpec, shared_data: pd.DataFrame | None) -> PlotlyPlotDef:
        """Handle trace spec to plot def."""
        plot_type = self._resolve_trace_plot_type(trace_spec)
        df = self._resolve_trace_dataframe(trace_spec, shared_data)
        resolved_df = self._resolve_trace_columns(trace_spec, df, plot_type)
        resolved_df, resolved_series_styles = self._apply_name_map(
            resolved_df, trace_spec.name_map, trace_spec.series_styles
        )
        return PlotlyPlotDef(
            data=resolved_df,
            title=trace_spec.title,
            row=trace_spec.row,
            col=trace_spec.col,
            x_axis_title=trace_spec.x_axis_title,
            y_axis_title=trace_spec.y_axis_title,
            reversed_y=trace_spec.reversed_y,
            plot_type=plot_type,
            tickformat=None,
            dtick=None,
            hovertemplate=trace_spec.hovertemplate,
            secondary_y=trace_spec.secondary_y,
            show_legend=trace_spec.show_legend,
            show_grid=trace_spec.show_grid,
            show_rangeslider=trace_spec.show_rangeslider,
            use_rangebreaks=trace_spec.use_rangebreaks,
            holiday_countries=trace_spec.holiday_countries,
            trace_style=trace_spec.trace_style,
            series_styles=resolved_series_styles,
        )

    def _uses_explicit_positions(self, plot_defs: list[PlotlyPlotDef]) -> bool:
        """Handle uses explicit positions."""
        return any(plot_def.row is not None or plot_def.col is not None for plot_def in plot_defs)

    def _validate_plot_positions(self, plot_defs: list[PlotlyPlotDef], n_rows: int, n_cols: int) -> None:
        """Validate plot positions."""
        for plot_def in plot_defs:
            row = plot_def.row
            col = plot_def.col
            if (row is None) != (col is None):
                raise ValueError("PlotlyPlotDef row and col must both be set or both be None.")
            if row is None and col is None:
                raise ValueError("All PlotlyPlotDef instances must set row and col when using explicit placement.")
            if not isinstance(row, int) or not isinstance(col, int):
                raise ValueError("PlotlyPlotDef row and col must be integers.")
            if row < 1 or col < 1:
                raise ValueError("PlotlyPlotDef row and col must be positive integers.")
            if row > n_rows or col > n_cols:
                raise ValueError(f"PlotlyPlotDef position ({row}, {col}) exceeds subplot grid {n_rows}x{n_cols}.")

    def _group_defs_by_cell(self, plot_defs: list[PlotlyPlotDef]) -> dict[tuple[int, int], list[PlotlyPlotDef]]:
        """Handle group defs by cell."""
        grouped: dict[tuple[int, int], list[PlotlyPlotDef]] = {}
        for plot_def in plot_defs:
            key = (tp.cast(int, plot_def.row), tp.cast(int, plot_def.col))
            grouped.setdefault(key, []).append(plot_def)
        return grouped

    def _cell_uses_secondary(self, plot_defs: list[PlotlyPlotDef]) -> bool:
        """Handle cell uses secondary."""
        return any(self._plot_def_uses_secondary(plot_def) for plot_def in plot_defs)

    def _explicit_subplot_titles(
        self,
        plots_by_cell: dict[tuple[int, int], list[PlotlyPlotDef]],
        n_rows: int,
        n_cols: int,
    ) -> list[str] | None:
        """Handle explicit subplot titles."""
        titles: list[str] = []
        has_non_empty_title = False
        for row in range(1, n_rows + 1):
            for col in range(1, n_cols + 1):
                cell_plots = plots_by_cell.get((row, col), [])
                title = ""
                for plot_def in cell_plots:
                    if plot_def.title:
                        title = plot_def.title
                        has_non_empty_title = True
                        break
                titles.append(title)
        return titles if has_non_empty_title else None

    def _explicit_subplot_specs(
        self,
        plots_by_cell: dict[tuple[int, int], list[PlotlyPlotDef]],
        n_rows: int,
        n_cols: int,
    ) -> list[list[dict[str, tp.Any]]]:
        """Handle explicit subplot specs."""
        subplot_specs: list[list[dict[str, tp.Any]]] = []
        for row in range(1, n_rows + 1):
            row_specs: list[dict[str, tp.Any]] = []
            for col in range(1, n_cols + 1):
                cell_plots = plots_by_cell.get((row, col), [])
                row_specs.append(self._subplot_spec_for_cell(cell_plots))
            subplot_specs.append(row_specs)
        return subplot_specs

    def _subplot_spec_for_cell(self, plot_defs: list[PlotlyPlotDef]) -> dict[str, tp.Any]:
        """Handle subplot spec for cell."""
        if not plot_defs:
            return {"secondary_y": False}

        plot_types = {plot_def.plot_type for plot_def in plot_defs}
        if PlotType.pie in plot_types:
            if len(plot_types) > 1 or len(plot_defs) > 1:
                raise ValueError("Pie traces must occupy their own subplot cell.")
            return {"type": "domain"}

        return {"secondary_y": self._cell_uses_secondary(plot_defs)}

    def _plot_def_uses_secondary(self, plot_def: PlotlyPlotDef) -> bool:
        """Handle plot def uses secondary."""
        if plot_def.secondary_y:
            return True
        if not plot_def.series_styles:
            return False
        for col_name in plot_def.data.columns:
            style = plot_def.series_styles.get(str(col_name), {})
            if bool(style.get("secondary_y", False)):
                return True
        return False

    def _resolved_x_tick_settings(self, plot_def: PlotlyPlotDef) -> tuple[str | None, str | int | float | None]:
        """Handle resolved x tick settings."""
        tickformat = plot_def.tickformat if plot_def.tickformat is not None else self.tickformat
        dtick = plot_def.dtick if plot_def.dtick is not None else self.dtick

        # For OHLC, choose sensible x-axis defaults by index frequency when not explicitly set.
        if plot_def.plot_type != PlotType.OHLC:
            return tickformat, dtick
        if plot_def.tickformat is not None and plot_def.dtick is not None:
            return tickformat, dtick
        if not isinstance(plot_def.data.index, pd.DatetimeIndex):
            return tickformat, dtick

        freq_name = self._infer_freq_name(plot_def.data.index)
        if freq_name is None:
            median_seconds = self._infer_median_step_seconds(plot_def.data.index)
            if median_seconds is None:
                return tickformat, dtick
            if plot_def.tickformat is None:
                tickformat = "%b %d\n%H:%M"
            if plot_def.dtick is None:
                if median_seconds <= 5 * 60:
                    dtick = 12 * 60 * 60 * 1000
                elif median_seconds <= 60 * 60:
                    dtick = 24 * 60 * 60 * 1000
                else:
                    dtick = "M1"
            return tickformat, dtick

        if plot_def.tickformat is None:
            if freq_name in {"T", "min", "5min", "15min", "30min", "H"}:
                tickformat = "%b %d\n%H:%M"
            elif freq_name in {"B", "D"}:
                tickformat = "%b %d"
            elif freq_name.startswith("W"):
                tickformat = "%b %d\n%Y"
            elif freq_name.startswith("M"):
                tickformat = "%b\n%Y"
            else:
                tickformat = "%b %d\n%Y"

        if plot_def.dtick is None:
            if freq_name in {"T", "min"}:
                dtick = 6 * 60 * 60 * 1000
            elif freq_name == "5min":
                dtick = 12 * 60 * 60 * 1000
            elif freq_name in {"15min", "30min"}:
                dtick = 24 * 60 * 60 * 1000
            elif freq_name == "H":
                dtick = 24 * 60 * 60 * 1000
            elif freq_name in {"B", "D"}:
                dtick = "M1"
            elif freq_name.startswith("W"):
                dtick = "M1"
            elif freq_name.startswith("M"):
                dtick = "M3"
            else:
                dtick = "M1"

        return tickformat, dtick

    def _infer_freq_name(self, index: pd.DatetimeIndex) -> str | None:
        """Handle infer freq name."""
        freq = tp.cast(str | None, index.freqstr)
        if freq is None:
            try:
                freq = pd.infer_freq(index)
            except ValueError:
                freq = None
        if freq is None:
            return None

        try:
            return str(pd.tseries.frequencies.to_offset(freq).name)
        except (TypeError, ValueError):
            return None

    def _infer_median_step_seconds(self, index: pd.DatetimeIndex) -> float | None:
        """Handle infer median step seconds."""
        if len(index) < 2:
            return None
        idx = index
        if idx.tz is not None:
            idx = idx.tz_localize(None)
        diffs = idx.to_series().diff().dropna()
        if diffs.empty:
            return None
        seconds = diffs.dt.total_seconds()
        if seconds.empty:
            return None
        return float(seconds.median())

    def _resolved_rangebreaks(self, plot_def: PlotlyPlotDef) -> list[dict[str, tp.Any]] | None:
        """Handle resolved rangebreaks."""
        df = plot_def.data
        if df.empty or not isinstance(df.index, pd.DatetimeIndex):
            return None

        use_rangebreaks = self.use_rangebreaks if plot_def.use_rangebreaks is None else plot_def.use_rangebreaks
        if not use_rangebreaks:
            return None

        freq_name = self._infer_freq_name(df.index)
        if freq_name is None:
            return None
        if freq_name not in {"D", "B"}:
            return None

        holiday_countries = self.holiday_countries if plot_def.holiday_countries is None else plot_def.holiday_countries
        holiday_values = self._holiday_values(df.index, countries=holiday_countries)
        rangebreaks: list[dict[str, tp.Any]] = [{"bounds": ["sat", "mon"]}]
        if holiday_values:
            rangebreaks.append({"values": holiday_values})
        return rangebreaks

    def _holiday_values(self, index: pd.DatetimeIndex, countries: list[str]) -> list[str]:
        """Handle holiday values."""
        try:
            import holidays
        except ImportError as exc:
            raise ImportError("holidays package is required for holiday rangebreaks.") from exc

        start_year = int(index.min().year)
        end_year = int(index.max().year)
        holiday_dates: set = set()
        for country in countries:
            holiday_map = holidays.country_holidays(country, years=range(start_year, end_year + 1))
            holiday_dates.update(holiday_map.keys())
        return [d.isoformat() for d in sorted(holiday_dates)]

    def _resolved_hovertemplate(self, plot_def: PlotlyPlotDef) -> str | None:
        """Handle resolved hovertemplate."""
        hovertemplate = plot_def.hovertemplate
        # Candlestick/OHLC default hover is better (Open/High/Low/Close labels).
        if plot_def.plot_type == PlotType.OHLC and hovertemplate == self._DEFAULT_DATETIME_HOVERTEMPLATE:
            return None
        # Histograms use numeric x bins; date formatting renders "NaN" in hover.
        if plot_def.plot_type == PlotType.histogram and hovertemplate == self._DEFAULT_DATETIME_HOVERTEMPLATE:
            return "%{x:.3f}<br>count=%{y}"
        return hovertemplate

    def _apply_legend_grouping(self, trace: tp.Any, group_legend: bool, legend_seen_names: set[str]):
        """Handle apply legend grouping."""
        if not group_legend:
            return

        name = trace.name
        if not isinstance(name, str) or name == "":
            return

        trace.legendgroup = name
        if name in legend_seen_names:
            trace.showlegend = False
            return

        legend_seen_names.add(name)
        if trace.showlegend is None:
            trace.showlegend = True

    def _extract_trace_color(self, trace: tp.Any) -> str | None:
        """Extract trace color."""
        line = getattr(trace, "line", None)
        if line is not None:
            color = getattr(line, "color", None)
            if isinstance(color, str) and color:
                return color
        marker = getattr(trace, "marker", None)
        if marker is not None:
            color = getattr(marker, "color", None)
            if isinstance(color, str) and color:
                return color
        return None

    def _apply_trace_color(self, trace: tp.Any, color: str):
        """Handle apply trace color."""
        line = getattr(trace, "line", None)
        if line is not None:
            try:
                line.color = color
            except (TypeError, ValueError):
                pass
        marker = getattr(trace, "marker", None)
        if marker is not None:
            try:
                marker.color = color
            except (TypeError, ValueError):
                pass

    def _apply_group_color(
        self,
        trace: tp.Any,
        group_legend: bool,
        legend_group_colors: dict[str, str],
        color_index_state: list[int],
    ):
        """Handle apply group color."""
        if not group_legend:
            return
        name = trace.name
        if not isinstance(name, str) or name == "":
            return

        color = legend_group_colors.get(name)
        if color is None:
            color = self._extract_trace_color(trace)
            if color is None:
                palette = plotly.colors.DEFAULT_PLOTLY_COLORS
                color = palette[color_index_state[0] % len(palette)]
                color_index_state[0] += 1
            legend_group_colors[name] = color
        self._apply_trace_color(trace, color)

    def _add_plot(
        self,
        fig: go.Figure,
        plot_def: PlotlyPlotDef,
        row: int,
        col: int,
        group_legend: bool = False,
        legend_seen_names: set[str] | None = None,
        legend_group_colors: dict[str, str] | None = None,
        color_index_state: list[int] | None = None,
    ):
        """Handle add plot."""
        df = plot_def.data
        if df.empty:
            return
        if legend_seen_names is None:
            legend_seen_names = set()
        if legend_group_colors is None:
            legend_group_colors = {}
        if color_index_state is None:
            color_index_state = [0]
        hovertemplate = self._resolved_hovertemplate(plot_def)

        def _build_trace_with_connectgaps(trace_cls: tp.Any, kwargs: dict[str, tp.Any]) -> tp.Any:
            """Build trace with connectgaps."""
            if "connectgaps" not in kwargs:
                kwargs_with_connect = dict(kwargs)
                kwargs_with_connect["connectgaps"] = True
                try:
                    return trace_cls(**kwargs_with_connect)
                except (TypeError, ValueError):
                    pass
            return trace_cls(**kwargs)

        def _merge_style(base: dict[str, tp.Any], overlay: dict[str, tp.Any]) -> dict[str, tp.Any]:
            """Handle merge style."""
            out = dict(base)
            for key, value in overlay.items():
                base_value = out.get(key)
                if isinstance(base_value, Mapping) and isinstance(value, Mapping):
                    out[key] = _merge_style(dict(base_value), dict(value))
                else:
                    out[key] = value
            return out

        def _resolved_style(series_name: str | None = None) -> dict[str, tp.Any]:
            """Handle resolved style."""
            style: dict[str, tp.Any] = dict(plot_def.trace_style or {})
            if series_name is not None and plot_def.series_styles:
                style = _merge_style(style, plot_def.series_styles.get(series_name, {}))
            return style

        if plot_def.plot_type == PlotType.pie:
            if df.shape[1] >= 2:
                labels = df.iloc[:, 0]
                values = df.iloc[:, 1]
            else:
                labels = df.index
                values = df.iloc[:, 0]
            pie_kwargs: dict[str, tp.Any] = {"labels": labels, "values": values, "name": plot_def.title}
            pie_style = _resolved_style()
            pie_style.pop("secondary_y", None)
            pie_kwargs.update(pie_style)
            pie_trace = _build_trace_with_connectgaps(go.Pie, pie_kwargs)
            self._apply_group_color(pie_trace, group_legend, legend_group_colors, color_index_state)
            self._apply_legend_grouping(pie_trace, group_legend, legend_seen_names)
            fig.add_trace(
                pie_trace,
                row=row,
                col=col,
            )
            return

        if plot_def.plot_type == PlotType.OHLC:
            cols = {c.lower(): c for c in df.columns}
            required = ["open", "high", "low", "close"]
            if not all(k in cols for k in required):
                raise ValueError("OHLC plot requires columns: open, high, low, close")
            ohlc_kwargs: dict[str, tp.Any] = {
                "x": df.index,
                "open": df[cols["open"]],
                "high": df[cols["high"]],
                "low": df[cols["low"]],
                "close": df[cols["close"]],
                "name": plot_def.title,
                "hovertemplate": hovertemplate,
                "increasing": dict(line=dict(color="green"), fillcolor="green"),
                "decreasing": dict(line=dict(color="red"), fillcolor="red"),
            }
            ohlc_style = _resolved_style()
            use_secondary = bool(ohlc_style.pop("secondary_y", plot_def.secondary_y))
            ohlc_kwargs.update(ohlc_style)
            ohlc_trace = _build_trace_with_connectgaps(go.Candlestick, ohlc_kwargs)
            self._apply_group_color(ohlc_trace, group_legend, legend_group_colors, color_index_state)
            self._apply_legend_grouping(ohlc_trace, group_legend, legend_seen_names)
            fig.add_trace(
                ohlc_trace,
                row=row,
                col=col,
                secondary_y=use_secondary,
            )
            return

        mode = None
        if plot_def.plot_type == PlotType.line:
            mode = "lines"
        elif plot_def.plot_type == PlotType.scatter:
            mode = "markers"
        elif plot_def.plot_type == PlotType.line_scatter:
            mode = "lines+markers"

        for col_name in df.columns:
            series = df[col_name]
            col_style = _resolved_style(str(col_name))
            use_secondary = bool(col_style.pop("secondary_y", plot_def.secondary_y))
            if plot_def.plot_type == PlotType.bar:
                bar_kwargs: dict[str, tp.Any] = {"name": str(col_name), "hovertemplate": hovertemplate}
                bar_kwargs.update(col_style)
                bar_kwargs["x"] = df.index
                bar_kwargs["y"] = series
                trace = _build_trace_with_connectgaps(go.Bar, bar_kwargs)
            elif plot_def.plot_type == PlotType.histogram:
                hist_kwargs: dict[str, tp.Any] = {"name": str(col_name), "hovertemplate": hovertemplate}
                hist_kwargs.update(col_style)
                hist_kwargs["x"] = series
                trace = _build_trace_with_connectgaps(go.Histogram, hist_kwargs)
            else:
                scatter_kwargs: dict[str, tp.Any] = {"name": str(col_name), "hovertemplate": hovertemplate}
                scatter_kwargs.update(col_style)
                if mode is not None:
                    scatter_kwargs.setdefault("mode", mode)
                line_cfg = scatter_kwargs.get("line")
                if line_cfg is None:
                    scatter_kwargs["line"] = {"width": 1}
                elif isinstance(line_cfg, Mapping):
                    line_cfg = dict(line_cfg)
                    line_cfg.setdefault("width", 1)
                    scatter_kwargs["line"] = line_cfg
                scatter_kwargs["x"] = df.index
                scatter_kwargs["y"] = series
                trace = _build_trace_with_connectgaps(go.Scatter, scatter_kwargs)
            self._apply_group_color(trace, group_legend, legend_group_colors, color_index_state)
            self._apply_legend_grouping(trace, group_legend, legend_seen_names)
            fig.add_trace(trace, row=row, col=col, secondary_y=use_secondary)
