from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from runbook.sdk import column, currency, date, percent, report, required_aliases
from runbook.sdk.extensions.dash import dashboard, dataset_values, date_range, interaction, multi_select, select
from runbook.sdk.layout import Report
from runbook.sdk.live import LiveCapabilityUnavailableError

ALIASES = required_aliases(pnl="pnl")


@report.calc("pnl")
def pnl(ctx) -> pd.DataFrame:
    """Load and normalize the deterministic PnL dataset."""
    frame = ctx.dataset(ALIASES.pnl).copy()
    frame["date"] = pd.to_datetime(frame["date"], utc=True)
    return frame.sort_values("date", kind="mergesort").reset_index(drop=True)


def build_summary(frame: pd.DataFrame) -> str:
    """Build the static and interactive summary line."""
    total = float(frame["pnl"].sum()) if not frame.empty else 0.0
    by_book = frame.groupby("book", sort=True)["pnl"].sum() if not frame.empty else pd.Series(dtype=float)
    best = str(by_book.idxmax()) if not by_book.empty else "n/a"
    worst = str(by_book.idxmin()) if not by_book.empty else "n/a"
    return f"Total PnL: £{total:,.0f} · Best contributor: {best} · Worst contributor: {worst}"


def build_chart(frame: pd.DataFrame) -> go.Figure:
    """Build the cumulative PnL Plotly figure."""
    figure = go.Figure()
    if not frame.empty:
        series = frame.groupby("date", sort=True)["pnl"].sum().cumsum()
        figure.add_trace(go.Scatter(x=series.index, y=series.values, mode="lines+markers", name="PnL"))
    figure.update_layout(title="PnL through time", template="plotly_white")
    return figure


def _utc_day(value: object) -> pd.Timestamp:
    """Normalize a date-control value to the start of its UTC day."""
    timestamp = pd.Timestamp(str(value))
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    else:
        timestamp = timestamp.tz_convert("UTC")
    return timestamp.normalize()


def _filter(frame: pd.DataFrame, state: dict[str, object]) -> pd.DataFrame:
    """Apply control state to the PnL frame."""
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
    dates = pd.to_datetime(result["date"], utc=True)
    if start:
        result = result[dates >= _utc_day(start)]
    if end:
        result = result[dates < _utc_day(end) + pd.Timedelta(days=1)]
    return result


def _live_frame(ctx, state: dict[str, object]) -> pd.DataFrame:
    """Query optional live rows with named parameters and normalize their schema."""
    date_state = state.get("date")
    start = date_state.get("start_date") if isinstance(date_state, dict) else None
    end = date_state.get("end_date") if isinstance(date_state, dict) else None
    books = state.get("book")
    books = books if isinstance(books, list) else []
    strategy = state.get("strategy") if isinstance(state.get("strategy"), str) else None
    try:
        source = ctx.live.sql("demo_pnl")
    except LiveCapabilityUnavailableError:
        return pd.DataFrame(columns=["date", "book", "strategy", "instrument", "pnl", "exposure", "return"])

    predicates = ["(:strategy IS NULL OR strategy = :strategy)"]
    params: dict[str, object] = {"strategy": strategy}
    if start:
        predicates.append("business_date >= :start")
        params["start"] = _utc_day(start).strftime("%Y-%m-%d")
    if end:
        predicates.append("business_date < :end")
        params["end"] = (_utc_day(end) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    if books:
        names = [f":book_{index}" for index in range(len(books))]
        predicates.append(f"book IN ({', '.join(names)})")
        params.update({name[1:]: value for name, value in zip(names, books, strict=True)})
    frame = source.query(
        "SELECT business_date AS date, book, strategy, instrument, pnl, exposure FROM demo_live_pnl WHERE "
        + " AND ".join(predicates),
        params,
    )
    frame["date"] = pd.to_datetime(frame["date"], utc=True)
    frame["return"] = 0.0
    return frame


@report.interaction("filter_dashboard")
def filter_dashboard(ctx, state: dict[str, object]) -> dict[str, object]:
    """Update summary, chart, and table from ordinary JSON interaction state."""
    managed = _filter(ctx.calc("pnl"), state)
    live = _live_frame(ctx, state)
    frame = pd.concat([managed, live], ignore_index=True)
    return {
        "summary": build_summary(frame),
        "pnl_chart": build_chart(frame),
        "positions": frame,
    }


@report.page
def page(ctx):
    """Build the canonical static-first PnL Explorer PDL manifest."""
    frame = ctx.calc("pnl")
    table_frame = frame.assign(date=frame["date"].dt.date)
    table_ref = ctx.artifact.table(table_frame, name="positions")
    chart_ref = ctx.artifact.plot(build_chart(frame), name="pnl_chart")
    layout = Report(
        "PnL Explorer",
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
    with layout.grid(columns=12) as report_grid:
        report_grid.text(build_summary(frame), name="summary", col_span=12)
        report_grid.plot(chart_ref, name="pnl_chart", col_span=12)
        report_grid.table(
            table_ref,
            name="positions",
            col_span=12,
            columns=[
                column("date", role="time", format=date()),
                column("book", role="dimension"),
                column("strategy", role="dimension"),
                column("instrument", role="identifier"),
                column("pnl", role="measure", aggregation="sum", format=currency("GBP", decimals=0)),
                column("exposure", role="measure", aggregation="sum", format=currency("GBP", decimals=0)),
                column("return", role="measure", aggregation="avg", format=percent(decimals=2)),
            ],
        )
    return layout
