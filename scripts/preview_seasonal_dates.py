"""Preview original-date seasonal hovers and caller overrides with synthetic data."""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from runbook.core.plotting.seasonal import plot_seasonal
from preview_gallery import write_gallery


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("/tmp/runbook-seasonal-dates"))
    args = parser.parse_args()
    dates = pd.date_range("2023-01-01", "2025-12-31")
    data = pd.DataFrame(
        {"Value": 50 + 10 * np.sin(dates.dayofyear * 2 * np.pi / 365) + (dates.year - 2023) * 7}, index=dates
    )
    cases = [
        (
            "calendar",
            "Calendar seasons and forecast",
            "Hover the 2025 line on April 29: the date is 2025-04-29 even on the shared seasonal axis. "
            "From May 1 the same year's points are labelled 2025_Forecast. "
            "Comparison and cumulative hovers use a seasonal month/day without an invented year. "
            "All panels use month-only tick labels; February 29 is omitted.",
            dict(current_year=2025, dash_from=pd.Timestamp("2025-05-01"), ytd_cum_sum=True),
        ),
        (
            "cross-year",
            "October–September seasons",
            "The 2024 season starts in October 2024 and continues into 2025. "
            "Hover either side of January: dates retain the correct calendar year. "
            "The forecast begins January 1, 2025, while its trace name remains 2024_Forecast.",
            dict(
                start_month=10,
                end_month=9,
                over_year=True,
                current_year=2024,
                dash_from=pd.Timestamp("2025-01-01"),
                vs_average=False,
            ),
        ),
        (
            "overrides",
            "Explicit caller overrides",
            "Caller-provided day/month ticks and a custom two-decimal hover take precedence. "
            "Source dates remain available through customdata.",
            dict(
                current_year=2025,
                dash_from=pd.Timestamp("2025-05-01"),
                vs_average=False,
                tickformat="%d/%m",
                hovertemplate="Date: %{customdata}<br>Value: %{y:.2f}<extra>%{fullData.name}</extra>",
            ),
        ),
    ]
    charts = []
    for key, title, description, options in cases:
        figure = plot_seasonal(data, title=title, width=1050, height=650, **options)
        charts.append(
            dict(
                key=key,
                title=title,
                description=description,
                figure=figure,
                template="runbook.core.plotting.plot_seasonal",
                code=f"plot_seasonal(data, **{options!r})",
            )
        )
    write_gallery(args.output_dir, [], charts, serve=False)


if __name__ == "__main__":
    main()
