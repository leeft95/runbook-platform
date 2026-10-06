"""COT report price, volume, and open-interest panels."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from .graphly import GraphlyTraceSpec, PlotType
from .mixed import plot_mixed


def plot_cot_market(
    data: dict[str, pd.DataFrame],
    title: str | None = None,
    *,
    cot_start: str | pd.Timestamp | None = None,
    highlight: bool = True,
    lookback_days: int = 76,
    ohlc_columns: tuple[str, str, str, str] = ("PX_OPEN", "PX_HIGH", "PX_LOW", "PX_LAST"),
    volume_column: str | None = "VOLUME",
    open_interest_column: str | None = "FUT_AGGTE_OPEN_INT",
    holdings_column: str | None = "HOLDINGS",
    width: int | None = None,
    height: int = 600,
) -> go.Figure:
    """Plot named markets with OHLC and optional volume/OI/holdings panels.

    Inputs are already-acquired frames. ``cot_start`` filters to a lookback
    window and optionally shades the following seven days. All inputs are
    sorted without filling missing observations or altering the caller's data.
    Optional series with only missing values or zeros are omitted.
    """
    if not data:
        raise ValueError("data must contain at least one named market")
    if not isinstance(lookback_days, int) or isinstance(lookback_days, bool) or lookback_days < 0:
        raise ValueError("lookback_days must be a non-negative integer")
    if len(ohlc_columns) != 4 or len(set(ohlc_columns)) != 4:
        raise ValueError("ohlc_columns must contain distinct open, high, low and close columns")
    traces = []
    highlights = []
    rows = 1
    for col, (name, raw) in enumerate(data.items(), start=1):
        if not isinstance(raw, pd.DataFrame) or not isinstance(raw.index, pd.DatetimeIndex):
            raise TypeError("Each market requires a DataFrame with a DatetimeIndex")
        if not raw.index.is_unique or raw.index.hasnans or not raw.columns.is_unique:
            raise ValueError("Market observations and columns must be unique and dates cannot be NaT")
        frame = raw.sort_index()
        if cot_start is not None:
            start = pd.Timestamp(cot_start)
            if frame.index.tz is not None and start.tzinfo is None:
                start = start.tz_localize(frame.index.tz)
            frame = frame.loc[frame.index >= start - pd.Timedelta(days=lookback_days)]
            highlights.append((col, start))
        if frame.empty:
            raise ValueError(f"No observations remain for market {name!r}")
        prices = frame.loc[:, list(ohlc_columns)].copy()
        prices.columns = ["open", "high", "low", "close"]
        traces.append(
            GraphlyTraceSpec(
                plot_type=PlotType.OHLC,
                data=prices,
                col=col,
                title=name,
                y_axis_title="Price",
            )
        )
        has_oi = (
            open_interest_column is not None
            and open_interest_column in frame
            and frame[open_interest_column].fillna(0).ne(0).any()
        )
        for field, label, kind, secondary in (
            (volume_column, "Volume", PlotType.bar, False),
            (open_interest_column, "OI", PlotType.line, True),
            (holdings_column, "Holdings", PlotType.line, True),
        ):
            if field is None or field not in frame or not frame[field].fillna(0).ne(0).any():
                continue
            panel_row = 3 if label == "Holdings" and has_oi else 2
            rows = max(rows, panel_row)
            traces.append(
                GraphlyTraceSpec(
                    plot_type=kind,
                    data=frame[[field]],
                    name_map={field: label},
                    row=panel_row,
                    col=col,
                    y_axis_title=label,
                    secondary_y=secondary and panel_row == 2,
                    trace_style={"marker": {"color": "lightblue"}} if kind == PlotType.bar else None,
                )
            )
    fig = plot_mixed(
        traces,
        title=title,
        width=width or 750 * len(data),
        height=height,
        n_rows=rows,
        n_cols=len(data),
        row_heights={2: [0.7, 0.3], 3: [0.5, 0.3, 0.2]}.get(rows),
        shared_xaxes=True,
        use_rangebreaks=False,
        legend_groups=True,
    )
    if highlight:
        for col, start in highlights:
            fig.add_vrect(
                x0=start,
                x1=start + pd.Timedelta(days=7),
                fillcolor="pink",
                opacity=0.25,
                line_width=0,
                row="all",
                col=col,
                exclude_empty_subplots=False,
            )
            fig.add_annotation(
                x=start, y=1, yref="y domain", text=start.strftime("%Y-%m-%d"), showarrow=False, row=1, col=col
            )
    return fig
