from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from runbook.core.plotting.graphly import GraphlyPlotter, PlotlyPlotDef, PlotType


def test_graphly_stress_ohlc_output_contract() -> None:
    csv_path = Path("data/fixtures/intraday_bars.csv")
    intraday = pd.read_csv(csv_path, parse_dates=["timestamp"], nrows=3000)
    ohlc_df = intraday.set_index("timestamp")[["open", "high", "low", "close"]]
    lower = ohlc_df.quantile(0.01)
    upper = ohlc_df.quantile(0.99)
    inlier_mask = ohlc_df.ge(lower).all(axis=1) & ohlc_df.le(upper).all(axis=1)
    ohlc_df = ohlc_df.loc[inlier_mask]

    fig = GraphlyPlotter(width=1200, height=600).plot(
        [PlotlyPlotDef(data=ohlc_df, title="Synthetic Intraday OHLC", plot_type=PlotType.OHLC, x_axis_title="Time")],
        title="Graphly OHLC Demo",
    )

    assert len(fig.data) == 1
    assert fig.data[0].type in {"ohlc", "candlestick"}
    assert fig.layout.xaxis.title.text == "Time"
    assert fig.layout.xaxis.tickformat in {"%b %d\n%H:%M", "%b %d"}


def test_graphly_stress_grouped_legend_output_contract() -> None:
    rng = np.random.default_rng(seed=42)
    idx = pd.date_range("2025-01-01", periods=120, freq="D")
    base = np.cumsum(rng.normal(0.0, 1.0, size=len(idx)))
    left = pd.DataFrame({"2024": base, "2025": base + 2.0}, index=idx)
    mid = pd.DataFrame({"2024": base * 0.7 + 1.5, "2025": base * 0.9 + 2.5}, index=idx)
    right = pd.DataFrame({"2024": base * 1.2 - 1.0, "2025": base * 1.1 + 1.0}, index=idx)

    fig = GraphlyPlotter(width=1500, height=450, n_rows=1, n_cols=3, legend_groups=True, shared_xaxes=True).plot(
        [
            PlotlyPlotDef(data=left, title="Panel A", plot_type=PlotType.line),
            PlotlyPlotDef(data=mid, title="Panel B", plot_type=PlotType.line),
            PlotlyPlotDef(data=right, title="Panel C", plot_type=PlotType.line),
        ],
        title="Graphly Legend Grouping (Single Row, Multi Column)",
    )

    assert len(fig.data) == 6
    traces_2024 = [t for t in fig.data if t.name == "2024"]
    traces_2025 = [t for t in fig.data if t.name == "2025"]
    assert len(traces_2024) == 3
    assert len(traces_2025) == 3
    assert traces_2024[0].showlegend is True
    assert traces_2024[1].showlegend is False
    assert traces_2024[2].showlegend is False
    assert traces_2025[0].showlegend is True
    assert traces_2025[1].showlegend is False
    assert traces_2025[2].showlegend is False
    assert all(t.legendgroup == "2024" for t in traces_2024)
    assert all(t.legendgroup == "2025" for t in traces_2025)
    assert all(t.line.color == traces_2024[0].line.color for t in traces_2024)
    assert all(t.line.color == traces_2025[0].line.color for t in traces_2025)


def test_graphly_stress_mixed_output_contract() -> None:
    rng = np.random.default_rng(seed=42)
    d_idx = pd.date_range("2025-03-01", periods=100, freq="B")
    prices = pd.DataFrame({"px": 100 + np.cumsum(rng.normal(0.0, 0.8, size=len(d_idx)))}, index=d_idx)
    spread = pd.DataFrame({"sprd": rng.normal(0.0, 1.0, size=len(d_idx))}, index=d_idx)
    volume = pd.DataFrame({"vol": rng.integers(200, 1800, size=len(d_idx))}, index=d_idx)
    buckets = pd.DataFrame({"ret": rng.normal(0.0, 1.0, size=1200)})

    fig = GraphlyPlotter(
        width=1400,
        height=900,
        n_rows=2,
        n_cols=2,
        shared_xaxes=False,
        use_rangebreaks=True,
        holiday_countries=["US", "GB"],
    ).plot(
        [
            PlotlyPlotDef(data=prices, title="Line (Bday + Holidays)", plot_type=PlotType.line),
            PlotlyPlotDef(data=volume, title="Bar (Mon Weekend Break)", plot_type=PlotType.bar),
            PlotlyPlotDef(data=spread, title="Scatter", plot_type=PlotType.scatter),
            PlotlyPlotDef(data=buckets, title="Histogram", plot_type=PlotType.histogram),
        ],
        title="Graphly Mixed Plot Stress Demo",
    )

    assert len(fig.data) == 4
    assert fig.data[0].type == "scatter"
    assert fig.data[1].type == "bar"
    assert fig.data[2].type == "scatter"
    assert fig.data[3].type == "histogram"
    assert fig.data[3].hovertemplate == "%{x:.3f}<br>count=%{y}"
    assert fig.layout.xaxis.rangebreaks[0].bounds == ("sat", "mon")
    assert fig.layout.xaxis2.rangebreaks[0].bounds == ("sat", "mon")
    assert fig.layout.xaxis3.rangebreaks[0].bounds == ("sat", "mon")
    assert tuple(fig.layout.xaxis4.rangebreaks) == ()
