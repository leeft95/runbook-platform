"""Generate a self-contained seasonal leap-year regression preview."""
from pathlib import Path

import numpy as np
import pandas as pd
from runbook.core.plotting.seasonal import plot_seasonal


def main() -> None:
    dates = pd.date_range("2019-01-01", "2027-12-31", freq="D")
    monthly_values = np.array([0.853765, -0.65, -0.55, 0.37, -0.43, 0.16, 0.11, -0.38, 0.25, 0.26, -0.19, -0.20])
    data = pd.DataFrame({"Balance": monthly_values[dates.month - 1]}, index=dates)
    parts = []
    for year in (2026, 2024):
        fig = plot_seasonal(
            data.loc[:f"{year + 1}-12-31"],
            current_year=year,
            start=f"{year - 5}-01-01",
            dash_from=pd.Timestamp(year, 10, 1),
            ytd_cum_sum=True,
            title=f"Identical monthly balances · comparison year {year}" + (" (leap year)" if year == 2024 else ""),
            y_axis_title="Bcf/day",
            width=1050,
            height=650,
        )
        for trace in fig.data:
            if " vs " in trace.name:
                values = np.asarray(trace.y, dtype=float)
                assert np.isfinite(values).any()
                np.testing.assert_array_equal(values[np.isfinite(values)], 0)
            index = pd.DatetimeIndex(trace.x)
            assert not ((index.month == 2) & (index.day == 29)).any()
        parts.append(fig.to_html(full_html=False, include_plotlyjs=True if not parts else False,
                                 config={"responsive": True, "displaylogo": False}))
    output = Path(__file__).resolve().parents[1] / "preview" / "seasonal-leap-year.html"
    output.write_text(
        '<!doctype html><html><head><meta charset="utf-8"><title>Seasonal leap-year regression</title>'
        '<style>body{font:16px system-ui;background:#f5f4f1;color:#203047;margin:32px auto;max-width:1100px}'
        '.plotly-graph-div{margin:24px 0}p{line-height:1.5}</style></head><body>'
        '<h1>Seasonal leap-year regression preview</h1>'
        '<p>Synthetic data: each calendar month has the same value every year. '
        'Both daily and cumulative comparisons should remain at zero, including after February. '
        'February 29 is omitted from every panel. Dashed lines show forecasts from October onward.</p>'
        '<p><strong>PASS:</strong> All four comparison lines in both cases are exactly zero after roundoff cleanup. '
        'Chart dates use the current display year; legend labels identify the source years.</p>'
        + ''.join(parts) + '</body></html>', encoding="utf-8"
    )
    print(output)


if __name__ == "__main__":
    main()
