import pandas as pd
from runbook.sdk import plot_line, report, required_aliases
from runbook.sdk.layout import Link, Report
from runbook.sdk.table_style import (
    action,
    condition,
    format_percent,
    rhs_literal,
    rule,
    table_style,
    target_columns,
)

ALIASES = required_aliases(prices="prices")


@report.calc("returns")
def returns(ctx):
    """Calculate close-to-close returns for the configured price dataset."""
    df = ctx.dataset(ALIASES.prices).copy()
    params = ctx.config.get("params", {})
    price_col = str(params.get("price_col", "price"))
    if price_col not in df.columns:
        raise ValueError(f"price column is missing from dataset: {price_col!r}")
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="raise")
        df = df.sort_values("timestamp", kind="mergesort").set_index("timestamp")
    s = df[price_col].astype(float).pct_change(fill_method=None)
    return s.rename("returns").to_frame()


@report.calc("vol")
def vol(ctx):
    """Calculate rolling annualized volatility using report parameters."""
    rets = ctx.calc("returns")["returns"]
    params = ctx.config.get("params", {})
    window = int(params.get("vol_window", 20))
    v = rets.rolling(window=window).std(ddof=0).mul(pd.Series(260.0**0.5, index=rets.index))
    return v.rename("vol").to_frame()


@report.page
def page(ctx):
    """Build the range-volatility demonstration page."""
    returns = ctx.calc("returns")
    vol = ctx.calc("vol")
    layout = ctx.config.get("layout", {})
    width = int(layout.get("plot_width", 1000))
    height = int(layout.get("plot_height", 450))
    fig_returns = plot_line(
        data=returns,
        title="Returns",
        width=width,
        height=height,
        show_legend=False,
        use_rangebreaks=True,
    )
    fig_vol = plot_line(
        data=vol,
        title="Volatility",
        width=width,
        height=height,
        show_legend=False,
        use_rangebreaks=True,
        series_styles={"vol": {"line": {"color": "#2A6F9E"}}},
    )

    # Keep timestamp indexes for deterministic calculations and plots, while
    # materializing JSON-safe timestamp values for the table identity/hash.
    def table_frame(frame):
        """Return a display copy with timestamp indexes rendered as strings."""
        if not isinstance(frame.index, pd.DatetimeIndex):
            return frame
        display = frame.reset_index()
        display["timestamp"] = display["timestamp"].astype(str)
        return display

    # Example deterministic table styler artifacts (`table-style/0.1`) via SDK builders.
    returns_style = table_style(
        key="returns_style_v1",
        formats=[format_percent("returns", digits=2)],
        rules=[
            rule(
                "neg_returns_red",
                target_columns(["returns"]),
                condition("lt", rhs=rhs_literal(0)),
                action(text_color="#B00020", font_weight="600"),
            )
        ],
        max_rows=100,
        na_rep="-",
    )
    vol_style = table_style(
        key="vol_style_v1",
        formats=[format_percent("vol", digits=2)],
        rules=[
            rule(
                "high_vol_yellow",
                target_columns(["vol"]),
                condition("gt", rhs=rhs_literal(0.3)),
                action(background_color="#FFF3CD"),
            )
        ],
        max_rows=100,
        na_rep="-",
    )

    returns_ref = ctx.artifact.table(table_frame(returns), name="returns", style=returns_style)
    vol_ref = ctx.artifact.table(table_frame(vol), name="vol", style=vol_style)
    returns_plot_ref = ctx.artifact.plot(fig_returns, name="returns")
    vol_plot_ref = ctx.artifact.plot(fig_vol, name="vol")

    layout = Report(ctx.config.get("title", "Range Vol (PoC)"))
    with layout.grid(columns=2) as report_grid:
        report_grid.table(returns_ref, name="returns_table", title="Returns")
        report_grid.plot(returns_plot_ref, name="returns_plot", title="Returns Plot")
        report_grid.table(vol_ref, name="vol_table", title="Volatility")
        report_grid.plot(vol_plot_ref, name="vol_plot", title="Volatility Plot")
    layout.add(Link("Visit example.com →", url="https://example.com", name="example-link"))
    return layout
