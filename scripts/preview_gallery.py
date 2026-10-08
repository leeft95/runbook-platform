"""Preview the new report helpers with reproducible, synthetic data only."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from html import escape
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.offline import get_plotlyjs

from runbook.core.plotting.templates import (
    plot_line_with_moving_average,
    plot_line_with_comparison,
    plot_seasonal_comparison,
    plot_reversed_seasonal_forecast,
    plot_seasonal_with_history,
    plot_cot_positions,
    plot_cot_long_short,
    plot_cot_net,
    plot_market_ohlc,
    plot_market_holdings,
    plot_regression_origin,
    plot_regression_intercept,
    plot_weekly_price_position,
    plot_four_week_price_position,
    plot_spread_position_changes,
    plot_forecast_bars,
    plot_highlighted_bar,
    plot_rollup_seasonal,
)
from runbook.core.table import TableStylePlan, render_table_html
from runbook.core.table.templates import (
    cot_table,
    cot_observations_table,
    cot_position_changes_table,
    cot_position_divergence_table,
    daily_prices_table,
    inventory_summary_table,
    flow_quarterly_table,
    flow_monthly_table,
    monthly_consensus_table,
    mtd_inventory_table,
    grouped_metrics_table,
    rollup_table_hst,
)
from runbook.core.timeseries.cot import prepare_cot_data


def build_examples() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Exercise the public helpers, without duplicating their calculations."""
    rng = np.random.default_rng(42)
    dates = pd.date_range("2017-01-01", "2025-07-01")
    t = np.arange(len(dates))
    daily = pd.DataFrame(
        {
            "Crude stocks": 420 + 24 * np.sin(t / 58) + t / 650,
            "Product stocks": 210 + 15 * np.cos(t / 68) + t / 900,
            "Refinery runs": 16 + 2 * np.sin(t / 42) + rng.normal(0, 0.2, len(t)),
        },
        index=dates,
    )
    price = pd.DataFrame(
        {"Brent": 73 + 5 * np.sin(t / 26) + rng.normal(0, 0.3, len(t)), "WTI": 68 + 4 * np.sin(t / 27)}, index=dates
    )
    price["Spread"] = price.Brent - price.WTI
    weekly = pd.date_range("2017-01-03", "2025-07-01", freq="W-TUE")
    w = np.arange(len(weekly))
    positions = pd.DataFrame(
        {
            "Long": 190_000 + 26_000 * np.sin(w / 11) + rng.normal(0, 1700, len(w)),
            "Short": 95_000 + 17_000 * np.cos(w / 13),
            "OI": 700_000 + 30_000 * np.sin(w / 22),
            "PX_LAST": 72 + 7 * np.sin(w / 11) + rng.normal(0, 0.7, len(w)),
            "Internal": np.sin(w / 19),
            "NC Long": 220_000 + w * 90,
            "NC Short": 120_000 + w * 40,
        },
        index=weekly,
    )
    positions["VWAP"] = positions.PX_LAST - 0.15
    prepared = prepare_cot_data(positions)
    tables: list[dict[str, Any]] = []
    charts: list[dict[str, Any]] = []

    def table(
        key: str,
        title: str,
        description: str,
        template: Callable[..., dict[str, dict[str, Any]]],
        *args: Any,
        **kwargs: Any,
    ) -> None:
        payload = next(iter(template(*args, **kwargs).values()))
        tables.append(
            dict(
                key=key,
                title=title,
                description=description,
                payload=payload,
                template=f"runbook.core.table.templates.{template.__name__}",
            )
        )

    def chart(
        key: str,
        title: str,
        description: str,
        template: Callable[..., go.Figure],
        *args: Any,
        **kwargs: Any,
    ) -> None:
        charts.append(
            dict(
                key=key,
                title=title,
                description=description,
                figure=template(*args, **kwargs),
                template=f"runbook.core.plotting.templates.{template.__name__}",
            )
        )

    fixture = pd.read_csv(Path(__file__).resolve().parents[1] / "data/fixtures/cot/summary.csv")
    fixture["Net Position (NC)"] = [135_000, 145_000, -88_000, -92_000]
    fixture.loc[1, ["net change z score", "4w delta change z score"]] = [0.7, 1.1]
    fixture.loc[3, ["net change z score", "4w delta change z score"]] = [-0.7, -1.1]
    fixture.loc[[1, 3], "Weekly Price Change"] *= -1
    fixture.loc[[1, 3], "_price_chg"] = 1
    cot_options = dict(label_column="24-Jun to 01-Jul", position_column="Net Position (MM)", group_column="Group")
    table(
        "cot",
        "COT · managed money",
        "Complete summary, noncommercial positions, hidden signals, group borders and linked asset names. Scroll sideways to see every measure.",
        cot_table,
        fixture,
        plot_links={label: "cot-net" for label in fixture.iloc[:, 0]},
        **cot_options,
    )
    table(
        "cot-calculated",
        "COT · calculated from observations",
        "The same synthetic Long/Short/OI/price inputs, with standard and MiFID dispersion windows.",
        cot_observations_table,
        {"Standard · 52 observations": positions, "MiFID · 208 observations": positions},
        summary_options={"contract_value": 1000},
        asset_options={"MiFID · 208 observations": {"change_window": 208}},
    )
    table(
        "cot-changes",
        "COT · large position moves",
        "A score threshold of 2.15 selects the strongest four-week changes from the fixture.",
        cot_position_changes_table,
        fixture,
        threshold=2.15,
        **cot_options,
    )
    table(
        "cot-divergence",
        "COT · price / position divergence",
        "Only instruments whose weekly price and position changes have opposite signs.",
        cot_position_divergence_table,
        fixture,
        **cot_options,
    )
    table(
        "daily",
        "Daily prices · linked table",
        "Dated prices, a moving-average summary, change highlights, footer and clickable chart headings.",
        daily_prices_table,
        price.tail(130),
        chart_columns={"Brent": 20, "WTI": price[["Spread"]], "Spread": "line"},
        footer="Synthetic observations · 1 July 2025",
    )
    chart(
        "daily-ma",
        "Daily line with moving average",
        "The daily table's Brent chart uses a 20-observation moving-average overlay.",
        plot_line_with_moving_average,
        price.Brent.tail(130),
        window=20,
    )
    chart(
        "daily-comparison",
        "Daily line with secondary comparison",
        "WTI on the primary axis and a supplied spread series on the secondary axis.",
        plot_line_with_comparison,
        price.WTI.tail(130),
        comparison=price[["Spread"]],
    )

    table(
        "inventory",
        "Inventory · seasonal comparisons",
        "20-observation changes, mixed flow averages, completed months and quarters, QTD, Y−1 and five-year comparisons excluding 2020.",
        inventory_summary_table,
        daily,
        aggregation_columns={"Refinery runs": "mean"},
        exclude_years=[2020],
    )
    flows = pd.DataFrame({"Exports": 1500 + 200 * np.sin(t / 47), "Imports": 1800 + 150 * np.cos(t / 53)}, index=dates)
    table(
        "flow-quarter",
        "Flows · quarter benchmark",
        "10- and 20-observation averages with a Q1 benchmark and rolling-history highlights.",
        flow_quarterly_table,
        flows,
        benchmark_quarter="2025Q1",
    )
    table(
        "flow-month",
        "Flows · month benchmark",
        "Rolling sums and completed-month totals, with an explicit May benchmark.",
        flow_monthly_table,
        flows / 100,
        benchmark_month="2025-05-01",
    )
    consensus = daily[["Crude stocks", "Product stocks"]].resample("MS").mean()
    consensus["_last_update"] = "2025-07-01"
    table(
        "monthly",
        "Monthly consensus",
        "One-month changes with quarterly history, QTD and same-month year comparisons. Update metadata stays hidden.",
        monthly_consensus_table,
        consensus,
    )
    table(
        "mtd",
        "Stocks · MTD basis",
        "Each rolling average is measured from the previous calendar month-end. This example is pinned to 24 June.",
        mtd_inventory_table,
        daily[["Crude stocks", "Product stocks"]],
        as_of="2025-06-24",
    )

    columns = pd.MultiIndex.from_product([["January", "February"], ["Latest", "Change"]], names=["Month", "Metric"])
    index = pd.MultiIndex.from_product([["Europe", "US"], ["Returns", "Spread"]], names=["Region", "Measure"])
    grouped = pd.DataFrame(
        [[0.125, -0.2, 0.2, 0.35], [10.25, -0.5, 11.5, 0.1], [0.05, 0.7, 0.08, -0.25], [15.5, 0.8, 17.25, -0.8]],
        index=index,
        columns=columns,
    )
    table(
        "grouped",
        "Grouped table · mixed formats and data bars",
        "MultiIndex rows and columns, percentage versus numeric row formats, signed bars and centered alignment. Compare all three renderers below.",
        grouped_metrics_table,
        grouped,
        percentage_rows=(0, 2),
        bar_columns=(columns[1], columns[3]),
    )

    chart(
        "seasonal",
        "Seasonal comparison and cumulative panels",
        "Seasonal years, deviations from Y−1 / five-year history, and cumulative comparisons.",
        plot_seasonal_comparison,
        daily[["Crude stocks"]],
        current_year=2025,
        start="2020-01-01",
        exclude_years=[2020],
    )
    chart(
        "seasonal-reversed",
        "Seasonal forecast · reversed axes",
        "The selected year changes to a dashed forecast after 1 April. Axis reversal applies to the seasonal and comparison panels.",
        plot_reversed_seasonal_forecast,
        daily[["Product stocks"]],
        current_year=2025,
        start="2021-01-01",
        dash_from=pd.Timestamp("2025-04-01"),
        y_axis_title="Stocks (reversed)",
    )
    chart(
        "seasonal-grid",
        "Seasonal columns beside ordinary history",
        "Two seasonal columns share legend controls; the history column retains actual dates on an independent axis.",
        plot_seasonal_with_history,
        {"Crude stocks": daily[["Crude stocks"]], "Product stocks": daily[["Product stocks"]]},
        history=daily[["Crude stocks", "Product stocks"]],
        current_year=2025,
        start="2021-01-01",
    )
    chart(
        "cot-full",
        "COT · net, long and short",
        "Three position columns with price overlays, OI ratios, previous-five-year bands and an internal/CTA series.",
        plot_cot_positions,
        prepared,
        start=pd.Timestamp("2020-01-01"),
    )
    chart(
        "cot-pair",
        "COT · long / short",
        "Two-column COT layout using the same model and observation dates.",
        plot_cot_long_short,
        prepared,
        start=pd.Timestamp("2020-01-01"),
    )
    chart(
        "cot-net",
        "COT · single position / price panel",
        "A one-row COT variant without the OI panel. Linked COT asset names open this example.",
        plot_cot_net,
        prepared,
        start=pd.Timestamp("2020-01-01"),
    )
    recent_price = price.Brent.tail(150)
    ohlc = pd.DataFrame(
        {
            "PX_OPEN": recent_price - 0.2,
            "PX_HIGH": recent_price + 0.8,
            "PX_LOW": recent_price - 0.7,
            "PX_LAST": recent_price,
            "VOLUME": rng.integers(80_000, 140_000, len(recent_price)),
            "FUT_AGGTE_OPEN_INT": 700_000 + np.arange(len(recent_price)) * 100,
        },
        index=recent_price.index,
    )
    chart(
        "market",
        "OHLC · volume and open interest",
        "Two markets, independent price and OI scales, volume bars and a shaded COT reference week.",
        plot_market_ohlc,
        {"Brent": ohlc, "WTI": ohlc * 0.9},
        cot_start="2025-06-10",
    )
    chart(
        "market-holdings",
        "OHLC · open interest and holdings",
        "Holdings get their own third row when open interest is also supplied.",
        plot_market_holdings,
        {"Commodity fund": ohlc.assign(HOLDINGS=1500 + np.arange(len(ohlc)) * 3)},
        cot_start="2025-06-10",
    )
    changes = pd.DataFrame(
        {"Price change (%)": prepared.PX_LAST.pct_change(fill_method=None) * 100, "Net change": prepared.Net.diff()}
    ).tail(104)
    chart(
        "regression",
        "OLS regression · through the origin",
        "Full sample, recent 8 / 3 / 1 observations, fitted line and ±2 residual-standard-deviation bands.",
        plot_regression_origin,
        changes,
    )
    chart(
        "regression-intercept",
        "OLS regression · fitted intercept",
        "The same change data with an intercept; coefficients remain available in figure metadata.",
        plot_regression_intercept,
        changes,
    )
    for template, key, title in [
        (plot_weekly_price_position, "position-weekly", "Price vs positioning · weekly"),
        (plot_four_week_price_position, "position-four-week", "Price vs positioning · four weeks"),
        (plot_spread_position_changes, "position-spread", "Price vs positioning · spread changes"),
    ]:
        chart(
            key,
            title,
            "Older observations are grouped by year, with the previous four and the latest observation highlighted separately.",
            template,
            prepared.tail(130),
        )
    forecast = pd.Series(
        [101, 102, 99, 105, 107, 110, 112, 109, 108, 111, 113, 116],
        index=pd.date_range("2025-01-01", periods=12, freq="MS"),
        name="Demand",
    )
    chart(
        "forecast",
        "Bars · history and forecast",
        "From July onward, bars use the forecast color and pattern.",
        plot_forecast_bars,
        forecast,
        forecast_from=pd.Timestamp("2025-07-01"),
    )
    chart(
        "forecast-single",
        "Bars · one selected observation",
        "Only July is highlighted; later observations retain the base style.",
        plot_highlighted_bar,
        forecast,
        selected_at=pd.Timestamp("2025-07-01"),
    )
    power = pd.DataFrame(
        {
            "Gas": 26 + 4 * np.sin(t / 58),
            "Coal": 3 + np.cos(t / 70),
            "Nuclear": 45 + 5 * np.sin(t / 88),
            "Wind": 11 + 6 * np.cos(t / 49),
            "Solar": 20 + 8 * np.sin(t / 60),
        },
        index=dates,
    )
    power["Load"] = power.sum(axis=1)
    table(
        "rollup-power",
        "Power · calendar roll-ups",
        "Latest, 5-day / 20-day / 3-month averages, and matching prior-year windows. Each row opens full history and seasonal base/average panels.",
        rollup_table_hst,
        power,
        header="EU power",
    )
    table(
        "rollup-share",
        "Power shares · calendar roll-ups",
        "The same template accepts a time-series DataFrame of shares and formats the roll-ups as percentages.",
        rollup_table_hst,
        power.drop(columns="Load").div(power.Load, axis=0),
        header="EU power share",
        format_spec="{:.1%}",
    )
    chart(
        "rollup-seasonal",
        "Roll-up · history, base and rolling seasonal charts",
        "Full gas-generation history beside seasonal base, 5-day, 20-day and 3-month averages. All windows use calendar time.",
        plot_rollup_seasonal,
        power.Gas,
    )
    return tables, charts


CSS = """
*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:90px}
body{margin:0;background:#f4f6f8;color:#182b3a;font:15px/1.5 system-ui,sans-serif}
header,main{max-width:1420px;margin:auto;padding:30px}h1{font-size:38px;margin:8px 0}h2{margin:0;font-size:23px}
p{color:#5a6b79;margin:8px 0 20px}.eyebrow{font-weight:650;color:#176b62;font-size:12px;letter-spacing:.12em}
nav{position:sticky;top:0;z-index:10;background:#fff;border-block:1px solid #dce3e8;padding:12px 30px;display:flex;gap:12px;align-items:center;flex-wrap:wrap}
a{color:#166d83}button,select,.button{font:inherit;border:1px solid #c9d7df;border-radius:6px;background:#fff;color:#234455;padding:7px 12px;text-decoration:none;cursor:pointer}
button[aria-pressed=true]{background:#183d48;color:#fff;border-color:#183d48}select{max-width:340px}
.section-label{display:flex;gap:12px;align-items:center;margin:26px 0 14px}.count{padding:2px 10px;background:#e0ede9;border-radius:20px;font-size:13px}
article{background:#fff;border:1px solid #dce3e8;border-radius:10px;padding:24px;margin-bottom:24px;scroll-margin-top:90px;min-width:0}
.table-scroll{overflow:auto;max-width:100%;padding:6px 0 12px}.table-scroll th,.table-scroll td{padding:4px 7px}
.meta{display:flex;gap:14px;font-size:13px;margin-top:12px}.plot{min-height:430px}.badge{font-size:12px;color:#596b78}
.style-plan{margin-top:12px}.style-plan summary{cursor:pointer;color:#166d83;font-weight:600}
.style-plan pre{max-height:420px;overflow:auto;padding:16px;background:#f4f6f8;border:1px solid #dce3e8;border-radius:6px;font:13px/1.5 monospace}
@media(max-width:750px){header,main{padding:16px}h1{font-size:30px}article{padding:12px}nav{padding:10px}}
"""


def plot_html(figure: go.Figure, key: str) -> str:
    """Fit actual helper output to the gallery width without changing its traces."""
    figure = go.Figure(figure)
    figure.update_layout(width=None, autosize=True, height=max(460, figure.layout.height or 500))
    return figure.to_html(
        full_html=False, include_plotlyjs=False, div_id=f"plot-{key}", config={"responsive": True, "displaylogo": False}
    )


def write_gallery(output: Path, tables: list[dict[str, Any]], charts: list[dict[str, Any]], *, serve: bool) -> None:
    """Export the gallery, style plans and working companion-plot links."""
    output.mkdir(parents=True, exist_ok=True)
    (output / "plots").mkdir(exist_ok=True)
    (output / "styles").mkdir(exist_ok=True)
    (output / "plotly.min.js").write_text(get_plotlyjs(), encoding="utf-8")
    page_start = '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
    head = (
        page_start
        + "<title>Runbook · chart and table gallery</title><style>"
        + CSS
        + '</style><script src="plotly.min.js"></script><body>'
    )
    sections = []
    linked: dict[str, list[go.Figure]] = {item["key"]: [item["figure"]] for item in charts}
    for kind, examples in (("tables", tables), ("charts", charts)):
        cards = []
        for item in examples:
            key = item["key"]
            if kind == "tables":
                payload = item["payload"]
                plan = TableStylePlan.model_validate(payload["style"])
                plan_json = plan.model_dump_json(indent=2, exclude_none=True)
                (output / "styles" / f"{key}.json").write_text(plan_json)
                content = '<div class="table-scroll">' + render_table_html(payload["data"], plan) + "</div>"
                content += (
                    '<details class="style-plan"><summary>View style plan</summary>'
                    f"<pre><code>{escape(plan_json)}</code></pre></details>"
                    f'<div class="meta"><a href="styles/{key}.json" download="{key}.json">Download style plan JSON</a></div>'
                )
                for name, figure in zip(
                    payload.get("plot_names", []), payload.get("plots", []), strict=bool(payload.get("plot_names"))
                ):
                    linked[name] = [figure]
                if payload.get("all_plots_name"):
                    linked[payload["all_plots_name"]] = payload["plots"]
            else:
                content = '<div class="plot">' + plot_html(item["figure"], key) + "</div>"
            cards.append(
                f'<article id="{key}"><h2>{escape(item["title"])}</h2><p>{escape(item["description"])}</p>'
                f'<p class="badge">Template: <code>{escape(item["template"])}</code></p>{content}</article>'
            )
        sections.append(
            f'<section data-kind="{kind}"><div class="section-label"><h2>{kind.title()}</h2><span class="count">{len(examples)} examples</span></div>'
            + "".join(cards)
            + "</section>"
        )
    select = (
        '<select aria-label="Jump to an example" onchange="filterGallery(\'all\');location.hash=this.value"><option value="">Jump to an example…</option>'
        + "".join(f'<option value="{item["key"]}">{escape(item["title"])}</option>' for item in [*tables, *charts])
        + "</select>"
    )
    renderer_link = '<a class="button" href="/renderers/">Compare table renderers ↗</a>' if serve else ""
    navigation = (
        "<nav>"
        + "".join(
            f'<button onclick="filterGallery(\'{kind}\')" data-filter="{kind}" aria-pressed="{str(kind == "all").lower()}">{label}</button>'
            for kind, label in (("all", "All examples"), ("tables", "Tables"), ("charts", "Charts"))
        )
        + select
        + renderer_link
        + "</nav>"
    )
    script = """<script>
function filterGallery(kind){
 document.querySelectorAll('[data-kind]').forEach(s=>s.hidden=kind!=='all'&&s.dataset.kind!==kind);
 document.querySelectorAll('[data-filter]').forEach(b=>b.setAttribute('aria-pressed',b.dataset.filter===kind));
 requestAnimationFrame(()=>document.querySelectorAll('.js-plotly-plot').forEach(p=>{if(p.offsetParent)Plotly.Plots.resize(p)}));
}
</script>"""
    (output / "index.html").write_text(
        head
        + f'<header><div class="eyebrow">RUNBOOK CORE · PREVIEW GALLERY</div><h1>Charts & table templates</h1><p>{len(tables)} table examples · {len(charts)} chart examples · Synthetic data through 1 July 2025<br>All columns are centered by default. Click table links, hover charts, zoom and toggle legend entries.</p></header>'
        + navigation
        + "<main>"
        + "".join(sections)
        + "</main>"
        + script
        + "</body></html>",
        encoding="utf-8",
    )
    for name, figures in linked.items():
        if len(figures) == 1:
            figures[0].write_json(output / "plots" / f"{name}.json")
        body = "".join(plot_html(fig, f"{name}-{i}") for i, fig in enumerate(figures))
        (output / "plots" / f"{name}.html").write_text(
            page_start
            + '<title>Runbook · linked plots</title><script src="../plotly.min.js"></script><body style="font-family:system-ui;margin:24px"><a href="../index.html">← Back to gallery</a>'
            + body
            + "</body></html>"
        )
    print(f"Gallery: {output / 'index.html'} ({len(tables)} tables, {len(charts)} charts)", flush=True)


def serve_gallery(output: Path, tables: list[dict[str, Any]], port: int) -> None:
    """Serve the bundle and a live comparison using the production renderers."""
    from dash import Dash, Input, Output, dcc, html
    import dash_ag_grid as dag
    from flask import Flask, redirect
    from werkzeug.serving import make_server
    from runbook.core.pdl.models import PDLTableBlock
    from runbook.core.storage import BlobStore
    from runbook.sdk.extensions.dash.renderer import _build_ag_grid, _build_native_table
    from runbook.sdk.extensions.dash.tables import ag_grid_default_col_def, register_ag_grid_components

    server = Flask(__name__, static_folder=str(output), static_url_path="/gallery")
    server.add_url_rule("/", "gallery", lambda: redirect("/gallery/index.html"))
    app = Dash(__name__, server=server, url_base_pathname="/renderers/")
    register_ag_grid_components(app)
    ctx = SimpleNamespace(_artifact_store=BlobStore(f"file:{output}"), _artifact_prefix="")
    plot_refs = {path.stem: f"plots/{path.name}" for path in (output / "plots").glob("*.json")}
    examples = {item["key"]: item for item in tables}
    app.layout = html.Main(
        [
            html.A("← Back to the complete gallery", href="/gallery/index.html"),
            html.H1("Compare table renderers"),
            html.P(
                "The same data and style plan in static HTML, native Dash, and AG Grid. All observations are synthetic."
            ),
            dcc.Dropdown(
                id="table-choice",
                options=[{"label": x["title"], "value": x["key"]} for x in tables],
                value="grouped",
                clearable=False,
            ),
            html.Div(id="table-comparison"),
        ],
        style={"fontFamily": "system-ui", "padding": "24px", "maxWidth": "1450px", "margin": "auto"},
    )

    @app.callback(Output("table-comparison", "children"), Input("table-choice", "value"))
    def comparison(key: str) -> list[Any]:
        item = examples[key]
        payload = item["payload"]
        frame = payload["data"]
        block = PDLTableBlock(name=key, data_ref=f"{key}.parquet", style_ref=f"styles/{key}.json", row=1, col=1)

        def route(kind: str, value: str) -> str | None:
            return f"/gallery/plots/{value}.html" if kind == "plot" else None

        native = _build_native_table(frame, block, "native-table", ctx, route, plot_refs)
        grid = _build_ag_grid(frame, block, ctx, route, plot_refs)
        return [
            html.P(item["description"]),
            html.Details(
                [
                    html.Summary("View style plan", style={"cursor": "pointer", "color": "#166d83"}),
                    html.Pre(
                        TableStylePlan.model_validate(payload["style"]).model_dump_json(indent=2, exclude_none=True),
                        style={
                            "maxHeight": "420px",
                            "overflow": "auto",
                            "padding": "16px",
                            "background": "#f4f6f8",
                            "border": "1px solid #dce3e8",
                            "borderRadius": "6px",
                            "font": "13px/1.5 monospace",
                        },
                    ),
                ],
                style={"marginBottom": "12px"},
            ),
            html.A("Download style plan JSON", href=f"/gallery/styles/{key}.json", download=f"{key}.json"),
            html.H2("Static HTML"),
            html.Iframe(
                srcDoc='<base href="/gallery/">' + render_table_html(frame, payload["style"]),
                style={"width": "100%", "height": "300px", "border": "0"},
            ),
            html.H2("Native Dash"),
            html.Div(native, style={"overflowX": "auto"}),
            html.H2("AG Grid"),
            dag.AgGrid(
                rowData=grid.row_data,
                columnDefs=grid.column_defs,
                defaultColDef=ag_grid_default_col_def(),
                dashGridOptions={"suppressFieldDotNotation": True},
                style={"height": "380px", "width": "100%"},
            ),
            html.Div(grid.footer) if grid.footer is not None else None,
        ]

    httpd = make_server("127.0.0.1", port, server, threaded=True)
    print(f"PREVIEW_URL=http://127.0.0.1:{httpd.server_port}/", flush=True)
    httpd.serve_forever()


def main() -> None:
    """Generate an offline gallery, optionally serving live renderer comparisons."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("/tmp/runbook-gallery"))
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    tables, charts = build_examples()
    write_gallery(output, tables, charts, serve=args.serve)
    if args.serve:
        serve_gallery(output, tables, args.port)


if __name__ == "__main__":
    main()
