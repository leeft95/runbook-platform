from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from runbook.core.plotting.templates import comparison_chart


def test_comparison_panels_use_first_column_and_seasonal_cumulative_logic() -> None:
    dates = pd.date_range("2024-01-01", periods=4, freq="MS")
    frame = pd.DataFrame({"Reference": [10.0, 20.0, np.nan, 40.0], "EA": [12.0, np.nan, 33.0, 44.0]}, index=dates)
    original = frame.copy()
    figure = comparison_chart(frame, title="Exports", units="mcm/d", show_difference=True)
    traces = {(trace.name, trace.yaxis): trace for trace in figure.data}
    assert traces.keys() == {("Reference", "y"), ("EA", "y"), ("EA", "y2"), ("EA", "y3")}
    assert traces[("Reference", "y")].line.color == "black"
    np.testing.assert_allclose(traces[("EA", "y3")].y, [2, np.nan, np.nan, 4], equal_nan=True)
    # Accumulate each series first, exactly as seasonal charts do; no month-length weighting.
    np.testing.assert_allclose(traces[("EA", "y2")].y, [2, np.nan, np.nan, 19], equal_nan=True)
    assert len({trace.line.color for trace in figure.data if trace.name == "EA"}) == 1
    assert sum(trace.showlegend for trace in figure.data if trace.name == "EA") == 1
    assert all(trace.legendgroup == trace.name and not trace.connectgaps for trace in figure.data)
    assert figure.layout.xaxis.matches == figure.layout.xaxis2.matches == "x3"
    assert figure.layout.yaxis.title.text == "mcm/d"
    assert figure.layout.yaxis2.title.text == "Cum. delta to Reference<br>(mcm/d)"
    assert figure.layout.yaxis3.title.text == "Delta to Reference<br>(mcm/d)"
    heights = [
        figure.get_subplot(row, 1).yaxis.domain[1] - figure.get_subplot(row, 1).yaxis.domain[0] for row in (1, 2, 3)
    ]
    np.testing.assert_allclose(np.array(heights) / sum(heights), [0.5, 0.3, 0.2])
    assert len(figure.layout.shapes) == 3
    assert figure.layout.height == 600
    assert figure.layout.yaxis.domain[0] - figure.layout.yaxis2.domain[1] == pytest.approx(0.02)
    assert not figure.layout.annotations
    assert figure.layout.title.text == "Exports"
    assert figure.layout.xaxis.title.text is None
    assert figure.layout.xaxis2.title.text is None
    assert figure.layout.xaxis3.title.text == "Date"
    assert all(shape.x0 == shape.x1 == dates[0] and shape.line.dash == "dash" for shape in figure.layout.shapes)
    assert figure.to_json()
    pd.testing.assert_frame_equal(frame, original)


@pytest.mark.parametrize("order", [[2, 1, 0], [1, 2, 0]], ids=["descending", "shuffled"])
@pytest.mark.parametrize("timezone", [None, "Europe/London"])
@pytest.mark.parametrize("show_difference", [False, True])
def test_comparison_sorts_both_inputs_and_marks_earliest_comparison_date(order, timezone, show_difference) -> None:
    dates = pd.date_range("2025-01-01", periods=3, tz=timezone)
    frame = pd.DataFrame({"Base": [100.0, 200.0, 300.0], "EA": [110.0, 190.0, 330.0]}, index=dates).iloc[order]
    history = pd.DataFrame({"Base": [1.0, 2.0, 3.0]}, index=dates - pd.DateOffset(years=1)).iloc[order]
    original_frame, original_history = frame.copy(), history.copy()
    figure = comparison_chart(
        frame,
        history,
        show_difference=show_difference,
        series_styles={"EA": {"line": {"color": "red"}}},
        height=650,
    )
    plain = comparison_chart(frame, show_difference=show_difference)
    assert figure.layout.height == 650
    assert figure.data[0].name == "History: Base" and figure.data[0].line.color == "grey"
    assert figure.data[0].yaxis == "y"
    assert min(figure.data[0].x) == history.index.min()
    np.testing.assert_allclose(pd.Series(figure.data[0].y).dropna(), [1, 2, 3])
    assert all(trace.line.color == "red" for trace in figure.data if trace.name == "EA")
    for plotted in (figure, plain):
        assert all(shape.x0 == shape.x1 == dates[0] for shape in plotted.layout.shapes)
        assert all(list(trace.x) == sorted(trace.x) for trace in plotted.data)
        traces = {(trace.name, trace.yaxis): trace for trace in plotted.data}
        np.testing.assert_allclose(pd.Series(traces[("Base", "y")].y).dropna(), [100, 200, 300])
        np.testing.assert_allclose(pd.Series(traces[("EA", "y")].y).dropna(), [110, 190, 330])
        np.testing.assert_allclose(traces[("EA", "y2")].y, [10, 0, 30])
        assert list(traces[("EA", "y2")].x) == list(dates)
        if show_difference:
            np.testing.assert_allclose(traces[("EA", "y3")].y, [10, -10, 30])
            assert list(traces[("EA", "y3")].x) == list(dates)
    pd.testing.assert_frame_equal(frame, original_frame)
    pd.testing.assert_frame_equal(history, original_history)


def test_comparison_roundoff_is_zero_at_the_operand_scale() -> None:
    frame = pd.DataFrame(
        {"Base": [0.3, 0.3], "Other": [0.1 + 0.2, 0.1 + 0.2]}, index=pd.date_range("2025-01-01", periods=2)
    )
    figure = comparison_chart(frame, show_difference=True)
    for trace in figure.data[2:]:
        np.testing.assert_array_equal(trace.y, [0, 0])


@pytest.mark.parametrize(
    "frame, error",
    [
        (pd.DataFrame({"Base": [1], "Other": [2]}), TypeError),
        (pd.DataFrame({"Base": [1]}, index=pd.to_datetime(["2025-01-01"])), ValueError),
        (pd.DataFrame({"Base": [1, 2], "Other": [2, 3]}, index=pd.to_datetime(["2025-01-01"] * 2)), ValueError),
        (pd.DataFrame([[1, 2]], columns=["Base", "Base"], index=pd.to_datetime(["2025-01-01"])), ValueError),
        (pd.DataFrame({"Base": [1], "Other": [2]}, index=pd.DatetimeIndex([pd.NaT])), ValueError),
    ],
)
def test_comparison_validates_input_dates_and_columns(frame, error) -> None:
    with pytest.raises(error):
        comparison_chart(frame)


def test_comparison_gallery_examples_use_public_template_with_and_without_history() -> None:
    import runpy
    from pathlib import Path

    gallery = runpy.run_path(str(Path(__file__).resolve().parents[3] / "scripts/preview_gallery.py"))
    figures = []

    def chart(key, title, description, template, *args, code, **kwargs):
        assert template is comparison_chart and "comparison_chart(" in code
        figures.append((key, template(*args, **kwargs)))

    gallery["add_comparison_examples"](chart)
    assert [key for key, _ in figures] == ["comparison-history", "comparison-no-history", "comparison-differences"]
    for key, figure in figures:
        assert ("Kpler actuals" in {trace.name for trace in figure.data}) == (key != "comparison-no-history")
        assert figure.layout.yaxis.title.text == "mcm/d"
        assert figure.layout.title.text == "Global LNG exports"
        assert not figure.layout.annotations
        rows = 3 if key == "comparison-differences" else 2
        assert figure.get_subplot(rows, 1).xaxis.title.text == "Month"
        assert all(figure.get_subplot(row, 1).xaxis.title.text is None for row in range(1, rows))
        assert len(figure.layout.shapes) == (3 if key == "comparison-differences" else 2)
        assert figure.to_json()


def test_comparison_defaults_to_levels_and_cumulative_panels() -> None:
    frame = pd.DataFrame(
        {"Base": [10.0, 20.0, 30.0], "Other": [12.0, 19.0, 34.0]}, index=pd.date_range("2025-01-01", periods=3)
    )
    figure = comparison_chart(frame)
    assert [(trace.name, trace.yaxis) for trace in figure.data] == [("Base", "y"), ("Other", "y"), ("Other", "y2")]
    np.testing.assert_allclose(figure.data[-1].y, [2, 1, 5])
    assert len(figure.layout.shapes) == 2
    assert figure.layout.height == 600
    assert figure.layout.yaxis.domain[0] - figure.layout.yaxis2.domain[1] == pytest.approx(0.02)
    assert figure.layout.yaxis2.title.text == "Cum. delta to Base"
    heights = [
        figure.get_subplot(row, 1).yaxis.domain[1] - figure.get_subplot(row, 1).yaxis.domain[0] for row in (1, 2)
    ]
    np.testing.assert_allclose(np.array(heights) / sum(heights), [0.7, 0.3])


@pytest.mark.parametrize("show_difference, weights", [(False, [4, 1]), (True, [0.6, 0.25, 0.15])])
def test_comparison_custom_row_heights_preserve_spacing_and_shared_axes(show_difference, weights) -> None:
    frame = pd.DataFrame({"Base": [10.0, 20.0], "Other": [12.0, 19.0]}, index=pd.date_range("2025-01-01", periods=2))
    original_weights = weights.copy()
    figure = comparison_chart(
        frame, show_difference=show_difference, row_heights=weights, height=800, vertical_spacing=0.04
    )
    domains = [figure.get_subplot(row, 1).yaxis.domain for row in range(1, len(weights) + 1)]
    heights = np.array([upper - lower for lower, upper in domains])
    np.testing.assert_allclose(heights / heights.sum(), np.array(weights) / sum(weights))
    for top, bottom in zip(domains, domains[1:]):
        assert top[0] - bottom[1] == pytest.approx(0.04)
    assert figure.layout.height == 800
    assert not figure.layout.annotations
    assert figure.layout.xaxis.matches == f"x{len(weights)}"
    assert figure.get_subplot(len(weights), 1).xaxis.title.text == "Date"
    assert weights == original_weights


@pytest.mark.parametrize("weights", [[], [1], [1, 1, 1], [0, 1], [-1, 2], [np.nan, 1], [np.inf, 1]])
def test_comparison_rejects_invalid_row_heights(weights) -> None:
    frame = pd.DataFrame({"Base": [10.0, 20.0], "Other": [12.0, 19.0]}, index=pd.date_range("2025-01-01", periods=2))
    with pytest.raises(ValueError, match="row_heights.*positive, finite weight"):
        comparison_chart(frame, row_heights=weights)
