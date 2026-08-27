"""Generic public golden example for composable report layouts."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from runbook.sdk import report, required_aliases
from runbook.sdk.layout import Report

ALIASES = required_aliases(market="market")
INSTRUMENTS = tuple(f"Market_{index:03d}" for index in range(52))
REGIONS = ("North", "South", "West")


@report.calc("market")
def market(ctx) -> pd.DataFrame:
    """Load the synthetic market dataset selected by the profile."""
    return ctx.dataset(ALIASES.market)


def _table(frame: pd.DataFrame, index: int) -> object:
    """Build one small display table from the shared synthetic frame."""
    return frame.head(max(1, min(len(frame), 10))).copy()


def _chart(title: str) -> go.Figure:
    """Build one minimal synthetic Plotly figure."""
    figure = go.Figure()
    figure.update_layout(title=title)
    return figure


@report.page
def page(ctx):
    """Build a generic loop-heavy market dashboard without coordinates."""
    frame = ctx.calc("market")
    layout = Report("Market Dashboard")
    with layout.section("Executive Summary") as summary:
        with summary.grid(columns=2) as cards:
            cards.text(f"Rows in snapshot: {len(frame)}")
            cards.text(f"Instrument cards: {len(INSTRUMENTS)}")

    with layout.section("Price Markets") as prices:
        with prices.grid(columns=2) as cards:
            for instrument in INSTRUMENTS:
                cards.table(
                    ctx.artifact.table(_table(frame, len(instrument)), name=f"{instrument.lower()}-table"),
                    title=f"{instrument} prices",
                )
                cards.plot(
                    ctx.artifact.plot(_chart(f"{instrument} price"), name=f"{instrument.lower()}-plot"),
                    title=f"{instrument} history",
                )

    with layout.section("Regional Flows") as flows:
        with flows.grid(columns=3) as plots:
            for region in REGIONS:
                plots.plot(
                    ctx.artifact.plot(_chart(f"{region} flows"), name=f"{region.lower()}-flow"),
                    title=region,
                )
        flows.heading("Regional Detail")
        with flows.grid(columns=2) as tables:
            for region in REGIONS:
                tables.table(
                    ctx.artifact.table(_table(frame, len(region)), name=f"{region.lower()}-detail"),
                    title=region,
                )
    return layout
