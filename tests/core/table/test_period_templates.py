import numpy as np
import pandas as pd
import pytest

from runbook.core import table


@pytest.mark.parametrize("yoy", [False, True])
@pytest.mark.parametrize("period", ["monthly", "quarterly", "seasonal", "summer", "winter", "annual"])
def test_period_templates_use_all_supplied_observations_for_calendar_means_and_yoy(period, yoy) -> None:
    values = np.array([4, 10, 30, 40, 50, 70, 90, 14, 34, 44, 65, 85, 105], dtype=float)
    frame = pd.DataFrame(
        {"Level": values, "Negative": -values, "Ratio": values / 100, "Notes": "ignore"},
        index=[
            "2019-03-31",
            "2019-04-01",
            "2019-04-20",
            "2019-10-31",
            "2019-11-01",
            "2020-01-15",
            "2020-03-31",
            "2020-04-01",
            "2020-04-20",
            "2020-10-31",
            "2020-11-01",
            "2021-01-15",
            "2021-03-31",
        ],
    ).iloc[::-1]
    original = frame.copy()
    expected_levels = {
        "monthly": {
            "Mar19": 4,
            "Apr19": 20,
            "Oct19": 40,
            "Nov19": 50,
            "Jan20": 70,
            "Mar20": 90,
            "Apr20": 24,
            "Oct20": 44,
            "Nov20": 65,
            "Jan21": 85,
            "Mar21": 105,
        },
        "quarterly": {
            "Q1 2019": 4,
            "Q2 2019": 20,
            "Q4 2019": 45,
            "Q1 2020": 80,
            "Q2 2020": 24,
            "Q4 2020": 54.5,
            "Q1 2021": 95,
        },
        "seasonal": {"Win18": 4, "Sum19": 80 / 3, "Win19": 70, "Sum20": 92 / 3, "Win20": 85},
        "summer": {"Sum19": 80 / 3, "Sum20": 92 / 3},
        "winter": {"Win18": 4, "Win19": 70, "Win20": 85},
        "annual": {2019: 134 / 5, 2020: 317 / 6, 2021: 95},
    }
    expected_yoy = {
        "monthly": {
            "Mar19": np.nan,
            "Apr19": np.nan,
            "Oct19": np.nan,
            "Nov19": np.nan,
            "Jan20": np.nan,
            "Mar20": 86,
            "Apr20": 4,
            "Oct20": 4,
            "Nov20": 15,
            "Jan21": 15,
            "Mar21": 15,
        },
        "quarterly": {
            "Q1 2019": np.nan,
            "Q2 2019": np.nan,
            "Q4 2019": np.nan,
            "Q1 2020": 76,
            "Q2 2020": 4,
            "Q4 2020": 9.5,
            "Q1 2021": 15,
        },
        "seasonal": {"Win18": np.nan, "Sum19": np.nan, "Win19": 66, "Sum20": 4, "Win20": 15},
        "summer": {"Sum19": np.nan, "Sum20": 4},
        "winter": {"Win18": np.nan, "Win19": 66, "Win20": 15},
        "annual": {2019: np.nan, 2020: 317 / 6 - 134 / 5, 2021: 95 - 317 / 6},
    }
    options = dict(column_formats={"Ratio": "{:.2f}"})
    template = getattr(table, period + "_table" + ("_yoy" if yoy else ""))
    header = period.capitalize() + (" YoY" if yoy else "")
    payload = template(frame, **options)[header]
    base = table.period_table(frame, period, yoy=yoy, **options)[header]
    result = payload["data"]
    expected = (expected_yoy if yoy else expected_levels)[period]
    assert list(result.index) == list(expected)
    assert list(result) == ["Level", "Negative", "Ratio"]
    np.testing.assert_allclose(result.Level, list(expected.values()), equal_nan=True)
    np.testing.assert_allclose(result.Negative, -result.Level, equal_nan=True)
    np.testing.assert_allclose(result.Ratio, result.Level / 100, equal_nan=True)
    pd.testing.assert_frame_equal(result, base["data"])
    assert payload["style"] == base["style"]
    assert payload["plots"] == []
    resolved = table.resolve_table_style(result, payload["style"])
    assert resolved.formats["Ratio"].digits == 2
    assert resolved.formats["Level"].digits == 2
    assert resolved.global_style.one_bg_color == (period == "annual")
    for row in range(len(result)):
        if pd.notna(result.Negative.iloc[row]):
            assert resolved.cell_css[(row, "Negative")]["color"] == "red"
        assert "color" not in resolved.cell_css.get((row, "Level"), {})
    html = table.render_table_html(result, payload["style"])
    assert "text-align: center" in html and "color: red" in html
    pd.testing.assert_frame_equal(frame, original)


@pytest.mark.parametrize("period", ["monthly", "quarterly", "seasonal", "summer", "winter", "annual"])
def test_yoy_does_not_substitute_previous_available_period_when_a_year_is_missing(period) -> None:
    frame = pd.DataFrame(
        {"Value": [1.0, 2.0, 3.0, 4.0]},
        index=pd.to_datetime(["2019-04-01", "2019-11-01", "2021-04-01", "2021-11-01"]),
    )
    payload = next(iter(table.period_table(frame, period, yoy=True).values()))
    assert payload["data"].Value.isna().all()


def test_periods_keep_local_dates_skip_missing_values_and_preserve_partial_periods() -> None:
    frame = pd.DataFrame(
        {"Value": [1.0, np.nan, 3.0, 5.0]},
        index=pd.to_datetime(
            ["2019-10-31 23:30", "2019-11-01 00:30", "2020-03-31 23:30", "2020-04-01 00:30"]
        ).tz_localize("America/New_York"),
    )
    seasons = table.seasonal_table(frame)["Seasonal"]["data"]
    assert seasons.Value.to_dict() == {"Sum19": 1, "Win19": 3, "Sum20": 5}
    assert seasons.index.name == "Season"
    monthly = table.monthly_table(frame)["Monthly"]["data"]
    assert list(monthly.index) == ["Oct19", "Nov19", "Mar20", "Apr20"]
    np.testing.assert_allclose(monthly.Value, [1, np.nan, 3, 5], equal_nan=True)
    assert monthly.index.name == "Month"
    annual = table.annual_table(frame)["Annual"]["data"]
    assert annual.Value.to_dict() == {2019: 1, 2020: 4}
    empty = table.winter_table(frame.loc[frame.index.month == 4])["Winter"]
    assert empty["data"].empty
    assert "<table" in table.render_table_html(empty["data"], empty["style"])


@pytest.mark.parametrize("index", [["2025-01-01", "2025-01-01"], ["2025-01-01", None], ["invalid", "2025-01-01"]])
def test_periods_reject_duplicate_missing_or_invalid_dates(index) -> None:
    with pytest.raises(ValueError):
        table.monthly_table(pd.DataFrame({"Value": [1, 2]}, index=index))


@pytest.mark.parametrize(
    "options",
    [
        {"period": "weekly"},
        {"column_formats": {"Unknown": "{:.2f}"}},
        {"header": " "},
    ],
)
def test_periods_reject_invalid_options(options) -> None:
    frame = pd.DataFrame({"Value": [1]}, index=["2025-01-01"])
    with pytest.raises(ValueError):
        table.period_table(frame, **options)


def test_periods_reject_inputs_without_numeric_columns() -> None:
    with pytest.raises(ValueError, match="numeric columns"):
        table.monthly_table(pd.DataFrame({"Notes": ["text"]}, index=["2025-01-01"]))
