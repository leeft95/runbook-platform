from __future__ import annotations

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field
from runbook.sdk import plot_line, report, required_aliases
from runbook.sdk.table_style import format_number, format_percent, table_style
from runbook.sdk.ui import flex_grid, manifest, plot, table, text

ALIASES = required_aliases(daily_prices="daily_prices", intraday_bars="intraday_bars")


class Params(BaseModel):
    lookback_days: int = Field(default=60, ge=1)


@report.calc("daily_returns")
def daily_returns(ctx) -> pd.DataFrame:
    """Calculate daily close-to-close returns from the daily dataset."""
    frame = ctx.dataset(ALIASES.daily_prices).copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame = frame.sort_values("timestamp", kind="mergesort").reset_index(drop=True)
    frame["daily_return"] = frame["close"].astype(float).pct_change(fill_method=None)
    return frame[["timestamp", "close", "daily_return"]]


@report.calc("intraday_daily")
def intraday_daily(ctx) -> pd.DataFrame:
    """Aggregate intraday closes into one return per UTC session date."""
    frame = ctx.dataset(ALIASES.intraday_bars).copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame = frame.sort_values("timestamp", kind="mergesort").reset_index(drop=True)
    frame["session"] = frame["timestamp"].dt.floor("D")
    frame["log_return"] = np.log(frame["close"].astype(float)).groupby(frame["session"]).diff()
    return (
        frame.groupby("session", sort=True)
        .agg(
            realized_vol=(
                "log_return",
                lambda values: float(np.sqrt(np.square(values.dropna()).sum())),
            ),
            volume=("volume", "sum"),
            intraday_close=("close", "last"),
            bar_count=("close", "size"),
        )
        .reset_index()
    )


@report.calc("comparison")
def comparison(ctx) -> pd.DataFrame:
    """Join daily and intraday return series for comparison."""
    params = ctx.get_params(Params)
    daily = ctx.calc("daily_returns").rename(columns={"timestamp": "session"})
    intraday = ctx.calc("intraday_daily")
    result = daily.merge(intraday, on="session", how="inner", sort=True)
    result["abs_daily_return"] = result["daily_return"].abs()
    return result.tail(params.lookback_days).reset_index(drop=True)


@report.page
def page(ctx):
    """Build the generic daily and intraday snapshot page."""
    params = ctx.get_params(Params)
    comparison_frame = ctx.calc("comparison")
    daily_frame = ctx.calc("daily_returns")

    table_frame = comparison_frame[["session", "close", "daily_return", "realized_vol", "volume", "bar_count"]].tail(
        params.lookback_days
    )
    table_frame = table_frame.copy()
    table_frame["session"] = table_frame["session"].dt.strftime("%Y-%m-%d")
    table_ref = ctx.artifact.table(
        table_frame,
        name="comparison",
        style=table_style(
            key="timeseries_snapshot_comparison_v1",
            show_index=False,
            formats=[
                format_number("close", digits=2),
                format_percent("daily_return", digits=2),
                format_percent("realized_vol", digits=2),
                format_number("volume", digits=0, thousands=True),
                format_number("bar_count", digits=0, thousands=True),
            ],
            max_rows=params.lookback_days,
            na_rep="-",
        ),
    )

    close_fig = plot_line(
        data=daily_frame.set_index("timestamp")[["close"]],
        title="Daily close",
        width=700,
        height=360,
        show_legend=False,
        use_rangebreaks=True,
    )
    volatility_fig = plot_line(
        data=comparison_frame.set_index("session")[["abs_daily_return", "realized_vol"]],
        title="Daily absolute return vs intraday realized volatility",
        width=700,
        height=360,
        show_legend=True,
        use_rangebreaks=True,
    )
    close_ref = ctx.artifact.plot(close_fig, name="daily_close")
    volatility_ref = ctx.artifact.plot(volatility_fig, name="volatility")

    return manifest(
        ctx,
        title=ctx.config.get("title", "Timeseries Snapshot Demo"),
        page=flex_grid(
            rows=3,
            columns=2,
            blocks=[
                text(
                    name="summary",
                    title="Run Summary",
                    text=f"Snapshot: {ctx.snapshot.snapshot_id[:12]}\nWatermark: {ctx.snapshot.watermark.isoformat()}",
                    row=1,
                    col=1,
                    col_span=2,
                ),
                table(
                    name="comparison_table",
                    title="Recent comparison",
                    ref=table_ref,
                    row=2,
                    col=1,
                    col_span=2,
                ),
                plot(
                    name="daily_close_plot",
                    title="Daily close",
                    ref=close_ref,
                    row=3,
                    col=1,
                ),
                plot(
                    name="volatility_plot",
                    title="Volatility",
                    ref=volatility_ref,
                    row=3,
                    col=2,
                ),
            ],
        ),
    )
