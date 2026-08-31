"""Deterministic semantic-link and generated-plot golden report."""

from __future__ import annotations

import pandas as pd
from runbook.core.table import general_table_with_link
from runbook.sdk import plot_line, report, required_aliases
from runbook.sdk.layout import Report
from runbook.sdk.table_style import link_column

ALIASES = required_aliases(prices="prices")


@report.calc("prices")
def prices(ctx) -> pd.DataFrame:
    """Load a stable dated price series for the linked-table example."""
    frame = ctx.dataset(ALIASES.prices).copy()
    timestamp = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    return frame.assign(timestamp=timestamp).sort_values("timestamp", kind="mergesort").set_index("timestamp")


@report.page
def page(ctx):
    """Build one table with semantic body and generated plot links."""
    source = prices(ctx)[["close"]].rename(columns={"close": "price"})
    # Keep the input small while retaining enough points for the deterministic
    # moving-average and z-score helpers used by the public table template.
    source["volume"] = [100.0 + 5.0 * index for index in range(len(source))]
    table_payload = general_table_with_link(
        source,
        header="Asset",
        rows=min(5, len(source)),
        moving_average_window=3,
        change_zscore_window=3,
        chart_columns={"price": "line", "volume": "line"},
        column_plot_links=True,
        all_plots_link=True,
    )["Asset"]

    table_data = table_payload["data"].copy()
    # Cross-report targets intentionally remain unresolved in single-report preview.
    table_data["report_ref"] = [f"price-detail/{index:02d}" for index in range(len(table_data))]
    table_data["source_url"] = [f"https://example.com/prices/{index:02d}" for index in range(len(table_data))]
    style = dict(table_payload["style"])
    options = dict(style.get("options", {}))
    options["hidden_columns"] = [
        *options.get("hidden_columns", []),
        "report_ref",
        "source_url",
    ]
    style["options"] = options
    style["links"] = [
        *style.get("links", []),
        link_column("price", report_id_from="report_ref"),
        link_column("volume", url_from="source_url"),
    ]

    for name, figure in zip(table_payload["plot_names"], table_payload["plots"], strict=True):
        ctx.artifact.plot(figure, name=name)
    table_ref = ctx.artifact.table(table_data, name="linked_prices", style=style)
    overview_ref = ctx.artifact.plot(plot_line(source[["price"]], title="Price overview"), name="price-overview")

    layout = Report(ctx.config.get("title", "Linked Table Golden"))
    with layout.grid(columns=1) as report_grid:
        report_grid.table(table_ref, name="linked_prices", title="Linked prices", width="40vw")
        report_grid.plot(overview_ref, name="price_overview", title="Price overview")
    return layout


__all__ = ["ALIASES", "page", "prices"]
