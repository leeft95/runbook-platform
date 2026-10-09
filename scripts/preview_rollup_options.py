"""Compare static HTML and native Dash rendering for the roll-up options."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from runbook.core.table.templates import rollup_table_fcst, rollup_table_hst

from preview_gallery import plot_html, serve_gallery, write_gallery


CASES = [
    (
        "default",
        "Forecast defaults",
        "Latest and its 20-day z-score reference use df_hst; averages use df. Current Month is unhighlighted; Total is calculated.",
        "rollup_table_fcst(df, **base, include_total=True, total_label=None)",
    ),
    (
        "signals",
        "Signals that agree and diverge",
        "Rising is green in both columns. Pullback has a red Latest but green MA. Falling is negative in both; Flat has no dispersion.",
        'rollup_table_fcst(signals, today="2025-02-09", params=["Latest", "20d MA"], include_total=False)',
    ),
    (
        "history",
        "Historical roll-up",
        "Historical template: final supplied row anchors all windows; no Current Month column.",
        "rollup_table_hst(df_hst)",
    ),
    (
        "no-history",
        "Forecast without df_hst",
        "Without history, today anchors Latest and every MA; future forecast rows do not set the anchor.",
        'rollup_table_fcst(df, today="2025-06-20")',
    ),
    (
        "latest",
        "Highlight Latest only",
        "Latest is scored against the trailing 20-calendar-day raw observations.",
        'rollup_table_fcst(df, **base, use_highlighting=["Latest"])',
    ),
    (
        "ma",
        "Highlight 20d MA only",
        "The displayed 20d MA is scored against the last 20 calendar days of its own rolling-average history.",
        'rollup_table_fcst(df, **base, use_highlighting=["20d MA"])',
    ),
    (
        "selected",
        "Select other average columns",
        "Each selected average is scored against its own history; unselected cells retain row banding.",
        'rollup_table_fcst(df, **base, use_highlighting=["5d MA", "3m MA", "Y-1 20d MA"])',
    ),
    (
        "all",
        "Select every column",
        "Current Month is opt-in and uses monthly-average history. All other columns use their own daily reference series.",
        'rollup_table_fcst(df, **base, use_highlighting=["Current Month", "Latest", "5d MA", "20d MA", "3m MA", "Y-1 20d MA", "5Y 20d MA"])',
    ),
    (
        "no-highlights",
        "Disable z-score highlighting",
        "Empty selection removes z-score highlights; negative values still display in red.",
        'rollup_table_fcst(signals, today="2025-02-09", params=["Latest", "20d MA"], use_highlighting=[], include_total=False)',
    ),
    (
        "sensitive",
        "More sensitive SD limits",
        "Mild and strong colours start beyond 0.5 and 1 standard deviation.",
        "rollup_table_fcst(df, **base, std_limits=(0.5, 1.0))",
    ),
    (
        "wide",
        "Wider SD limits",
        "Mild and strong colours start beyond 2 and 3 standard deviations.",
        "rollup_table_fcst(df, **base, std_limits=(2.0, 3.0))",
    ),
    (
        "omit-total",
        "Omit Total",
        "Keep all component rows and omit the calculated total and its plots.",
        "rollup_table_fcst(df, **base, include_total=False)",
    ),
    (
        "named-total",
        "Name a calculated total",
        "Demand is absent from the input, so it names the sum of every displayed column.",
        'rollup_table_fcst(df, **base, total_label="Demand")',
    ),
    (
        "precomputed",
        "Use a precomputed total",
        "Load is supplied in the middle of the input. It moves to the last row without being counted twice.",
        'rollup_table_fcst(precomputed, **base, total_label="Load")',
    ),
    (
        "omit-precomputed",
        "Omit a supplied total",
        "Only the matching Load series is removed; every component remains.",
        'rollup_table_fcst(precomputed, **base, total_label="Load", include_total=False)',
    ),
    (
        "integer",
        "Integer and float formatting",
        "Latest retains integer dtype and displays 0 dp; averages are floats and display 2 dp.",
        'rollup_table_fcst(df.round().astype(int), df_hst=df_hst.round().astype(int), today="2025-06-20")',
    ),
    (
        "percent",
        "Override the numeric format",
        "Shares use percentage formatting. Calculations and z-score limits remain numeric.",
        'rollup_table_fcst(df.div(df.sum(axis=1), axis=0), df_hst=df_hst.div(df_hst.sum(axis=1), axis=0), today="2025-06-20", format_spec="{:.1%}")',
    ),
    (
        "no-links",
        "Disable table links",
        "Row and heading links are disabled. Companion figures are still returned.",
        "rollup_table_fcst(df, **base, row_plot_links=False, all_plots_link=False)",
    ),
    (
        "link-subset",
        "Link selected rows",
        "Only Gas links to its generated figure; the heading still opens all companion plots.",
        'rollup_table_fcst(df, **base, row_plot_links=["Gas"])',
    ),
    (
        "custom-links",
        "URL and relative report-page links",
        "Rows open an external example URL; the heading opens a custom local page containing chosen plots.",
        'rollup_table_fcst(df, **base, row_plot_links="https://example.com", all_plots_link="/gallery/custom-report.html")',
    ),
    (
        "columns",
        "Custom columns and windows",
        "Select and order custom windows; any displayed column can be highlighted.",
        'rollup_table_fcst(df, **base, params=["Latest", "10d MA", "Y-2 20d MA"], use_highlighting=["10d MA"])',
    ),
]


def main() -> None:
    """Render each example's shared data and style plan as HTML and Dash."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("/tmp/runbook-rollup-options"))
    parser.add_argument("--port", type=int, default=8767)
    parser.add_argument("--serve", action="store_true")
    args = parser.parse_args()
    output = args.output_dir.resolve()
    dates = pd.date_range("2020-01-01", "2025-07-01")
    t = np.arange(len(dates))
    df = pd.DataFrame(
        {
            "Gas": 28 + 6 * np.sin(t / 35) + t / 1000,
            "Coal": 5 + 0.5 * np.cos(t / 27),
            "Wind": 14 + 5 * np.sin(t / 21) + t / 1250,
        },
        index=dates,
    )
    df_hst = df.loc[:"2025-06-18"].copy()
    df_hst["Gas"] += 2.0
    base = dict(df_hst=df_hst, today="2025-06-20")
    precomputed = pd.concat([df.Gas, df.sum(axis=1).rename("Load"), df[["Coal", "Wind"]]], axis=1)
    signals = pd.DataFrame(
        {
            "Rising": np.arange(40.0),
            "Pullback": [0.0] * 20 + [100.0] * 19 + [0.0],
            "Falling": -np.arange(40.0),
            "Flat": [100.0] * 40,
        },
        index=pd.date_range("2025-01-01", periods=40),
    )
    namespace = {
        "rollup_table_fcst": rollup_table_fcst,
        "rollup_table_hst": rollup_table_hst,
        "df": df,
        "df_hst": df_hst,
        "base": base,
        "precomputed": precomputed,
        "signals": signals,
    }
    tables = []
    for key, title, description, expression in CASES:
        # Unique headers keep each example's generated plot destinations distinct.
        expression = expression[:-1] + f", header={title!r})"
        payload = next(iter(eval(expression, namespace).values()))
        tables.append(
            dict(
                key=f"rollup-{key}",
                title=title,
                description=description,
                payload=payload,
                template="runbook.core.table.templates." + expression.split("(")[0],
                code=expression,
            )
        )
    write_gallery(output, tables, [], serve=args.serve)
    chosen_plots = tables[0]["payload"]["plots"][:1] + tables[1]["payload"]["plots"][:1]
    (output / "custom-report.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>Custom report page</title><script src="plotly.min.js"></script><h1>Custom report page</h1><p>The caller chooses which plots appear here.</p>'
        + "".join(plot_html(figure, f"custom-{i}") for i, figure in enumerate(chosen_plots)),
        encoding="utf-8",
    )
    if args.serve:
        serve_gallery(output, tables, args.port)


if __name__ == "__main__":
    main()
