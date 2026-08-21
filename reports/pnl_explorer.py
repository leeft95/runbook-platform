from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from runbook.sdk import column, currency, manifest, percent, plot, report, required_aliases, table, text
from runbook.sdk.extensions.dash import dashboard, dataset_values, date_range, interaction, multi_select, select
from runbook.sdk.ui import grid

ALIASES = required_aliases(pnl="pnl")


@report.calc("pnl")
def pnl(ctx) -> pd.DataFrame:
    frame = ctx.dataset(ALIASES.pnl).copy()
    frame["date"] = pd.to_datetime(frame["date"], utc=True)
    return frame.sort_values("date", kind="mergesort").reset_index(drop=True)


def build_summary(frame: pd.DataFrame) -> str:
    total = float(frame["pnl"].sum()) if not frame.empty else 0.0
    by_book = frame.groupby("book", sort=True)["pnl"].sum() if not frame.empty else pd.Series(dtype=float)
    best = str(by_book.idxmax()) if not by_book.empty else "n/a"
    worst = str(by_book.idxmin()) if not by_book.empty else "n/a"
    return f"Total PnL: £{total:,.0f} · Best contributor: {best} · Worst contributor: {worst}"


def build_chart(frame: pd.DataFrame) -> go.Figure:
    figure = go.Figure()
    if not frame.empty:
        series = frame.groupby("date", sort=True)["pnl"].sum().cumsum()
        figure.add_trace(go.Scatter(x=series.index, y=series.values, mode="lines+markers", name="PnL"))
    figure.update_layout(title="PnL through time", template="plotly_white")
    return figure


def _filter(frame: pd.DataFrame, state: dict[str, object]) -> pd.DataFrame:
    result = frame
    books = state.get("book")
    if isinstance(books, list) and books:
        result = result[result["book"].isin(books)]
    strategy = state.get("strategy")
    if isinstance(strategy, str) and strategy:
        result = result[result["strategy"] == strategy]
    date_state = state.get("date")
    start = date_state.get("start_date") if isinstance(date_state, dict) else None
    end = date_state.get("end_date") if isinstance(date_state, dict) else None
    if start:
        result = result[result["date"] >= pd.Timestamp(str(start), tz="UTC")]
    if end:
        result = result[result["date"] <= pd.Timestamp(str(end), tz="UTC")]
    return result


@report.interaction("filter_dashboard")
def filter_dashboard(ctx, state: dict[str, object]) -> dict[str, object]:
    frame = _filter(ctx.calc("pnl"), state)
    return {
        "summary": build_summary(frame),
        "pnl_chart": build_chart(frame),
        "positions": frame,
    }


@report.page
def page(ctx):
    frame = ctx.calc("pnl")
    table_frame = frame.assign(date=frame["date"].dt.strftime("%Y-%m-%d"))
    table_ref = ctx.artifact.table(table_frame, name="positions")
    chart_ref = ctx.artifact.plot(build_chart(frame), name="pnl_chart")
    return manifest(
        ctx,
        title="PnL Explorer",
        page=grid(
            rows=3,
            columns=12,
            blocks=[
                text(name="summary", text=build_summary(frame), row=1, col=1, col_span=12),
                plot(name="pnl_chart", ref=chart_ref, row=2, col=1, col_span=12),
                table(
                    name="positions",
                    ref=table_ref,
                    row=3,
                    col=1,
                    col_span=12,
                    columns=[
                        column("date", role="time"),
                        column("book", role="dimension"),
                        column("strategy", role="dimension"),
                        column("instrument", role="identifier"),
                        column("pnl", role="measure", aggregation="sum", format=currency("GBP", decimals=0)),
                        column("exposure", role="measure", aggregation="sum", format=currency("GBP", decimals=0)),
                        column("return", role="measure", aggregation="avg", format=percent(decimals=2)),
                    ],
                ),
            ],
        ),
        extensions={
            "dash": dashboard(
                controls=[
                    multi_select("book", label="Book", options=dataset_values(alias="pnl", column="book")),
                    select("strategy", label="Strategy", options=dataset_values(alias="pnl", column="strategy")),
                    date_range("date", label="Date"),
                ],
                interactions=[
                    interaction(
                        handler="filter_dashboard",
                        inputs=["book", "strategy", "date"],
                        outputs=["summary", "pnl_chart", "positions"],
                    )
                ],
            )
        },
    )
