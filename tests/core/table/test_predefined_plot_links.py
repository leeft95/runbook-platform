from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from runbook.core.table import (
    general_table_with_link,
    render_table_html,
    resolve_table_style,
    rollup_table_hst,
    rollup_table_fcst,
    table_with_linked_plots_monthly,
)
from runbook.core.table.builder import link_anchor
from runbook.core.table.models import TableLinkDestination, TableLinkKind


def _frame(*columns: str, periods: int = 900) -> pd.DataFrame:
    index = pd.date_range("2020-01-01", periods=periods, freq="D")
    return pd.DataFrame({column: np.arange(periods, dtype=float) for column in columns}, index=index)


def test_plot_link_options_false_preserve_payload_shape() -> None:
    output = general_table_with_link(_frame("A"), header="Asset")
    assert set(output["Asset"]) == {"data", "style", "plots"}
    assert "links" not in output["Asset"]["style"]


def test_non_prefixed_json_plot_name_keeps_legacy_href() -> None:
    anchor = link_anchor("Foo", TableLinkDestination(kind=TableLinkKind.plot, value="foo.json"))
    assert 'href="plots/foo.json.html"' in anchor
    assert 'data-runbook-plot-name="foo.json"' in anchor


def test_general_plot_links_are_named_in_figure_order_and_include_modes() -> None:
    output = general_table_with_link(
        _frame("A", "B", "C"),
        header="Inventory / Prices",
        chart_columns={"A": "line", "B": "seasonal", "C": "seasonal_mva"},
        column_plot_links=True,
        all_plots_link=True,
    )["Inventory / Prices"]

    assert output["plot_names"] == [
        "inventory-prices-a-line",
        "inventory-prices-b-seasonal",
        "inventory-prices-c-seasonal-mva",
    ]
    assert output["all_plots_name"] == "inventory-prices-plots"
    assert output["data"].index.name == "Inventory / Prices"
    assert not isinstance(output["data"].index, pd.RangeIndex)
    assert [link["area"] for link in output["style"]["links"]] == [
        "header",
        "header",
        "header",
        "index_header",
    ]
    assert all(link["destination"]["kind"].value == "plot" for link in output["style"]["links"])


def test_general_plot_links_can_select_a_subset() -> None:
    output = general_table_with_link(_frame("A", "B"), header="Asset", column_plot_links=["B"])["Asset"]

    assert [link["field"] for link in output["style"]["links"]] == ["B"]
    assert output["plot_names"] == ["asset-a-seasonal", "asset-b-seasonal"]


@pytest.mark.parametrize("header", ["", "   ", "///"])
def test_general_plot_links_reject_blank_or_slug_empty_header(header: str) -> None:
    with pytest.raises(ValueError):
        general_table_with_link(_frame("A"), header=header, all_plots_link=True)


def test_plot_links_reject_unknown_and_duplicate_normalized_columns() -> None:
    with pytest.raises(ValueError, match="unknown"):
        general_table_with_link(_frame("A"), header="Asset", column_plot_links=["Missing"])

    with pytest.raises(ValueError, match="Duplicate generated plot name"):
        general_table_with_link(_frame("A!", "A?"), header="Asset", column_plot_links=True)


def test_monthly_plot_names_follow_raw_plot_order_and_filtered_rows_are_not_linked() -> None:
    output = table_with_linked_plots_monthly(
        _frame("A", "B"),
        header="Monthly / Asset",
        columns_filter=["A"],
        all_plots_link=True,
        row_plot_links=True,
    )["Monthly / Asset"]

    assert output["plot_names"] == [
        "monthly-asset-a-seasonal-mva",
        "monthly-asset-b-seasonal-mva",
    ]
    assert output["all_plots_name"] == "monthly-asset-plots"
    assert isinstance(output["data"].index, pd.RangeIndex)
    assert [link["area"] for link in output["style"]["links"]] == ["cells", "header"]
    assert output["style"]["links"][0]["field"] == "Monthly / Asset"
    assert output["style"]["links"][0]["destination"]["value_field"] == "_plot_link"
    assert output["style"]["links"][1]["field"] == "Monthly / Asset"
    assert output["style"]["links"][1]["destination"]["kind"].value == "plot"
    assert output["style"]["links"][1]["destination"]["value"] == "monthly-asset-plots"
    assert output["style"]["options"]["show_index"] is False
    assert output["style"]["options"]["hidden_columns"] == ["_plot_link"]
    html = render_table_html(output["data"], output["style"])
    assert html.count("<thead>") == 1
    assert "index_name" not in html
    assert (
        '<a href="plots/monthly-asset-plots.html" data-runbook-link-kind="plot" '
        'data-runbook-plot-name="monthly-asset-plots">Monthly / Asset</a>' in html
    )
    assert (
        '<a href="plots/monthly-asset-a-seasonal-mva.html" data-runbook-link-kind="plot" '
        'data-runbook-plot-name="monthly-asset-a-seasonal-mva">A</a>' in html
    )
    assert "monthly-asset-b-seasonal-mva" not in html

    with pytest.raises(ValueError):
        table_with_linked_plots_monthly(_frame("A"), header="Monthly", row_plot_links=["Missing"])


def test_monthly_plot_subset_links_aggregation_label() -> None:
    output = table_with_linked_plots_monthly(
        _frame("A", "B"),
        header="Monthly",
        aggregation_columns={"A": "MovingAverage"},
        row_plot_links=["A"],
    )["Monthly"]

    assert [link["field"] for link in output["style"]["links"]] == ["Monthly"]
    assert output["style"]["links"][0]["destination"]["value_field"] == "_plot_link"
    html = render_table_html(output["data"], output["style"])
    assert (
        '<a href="plots/monthly-a-seasonal-mva.html" data-runbook-link-kind="plot" '
        'data-runbook-plot-name="monthly-a-seasonal-mva">A [MA]</a>' in html
    )


def test_monthly_label_column_name_avoids_period_column_collision() -> None:
    output = table_with_linked_plots_monthly(
        _frame("A"),
        header="10d Level",
        row_plot_links=True,
    )["10d Level"]

    assert output["data"].columns[0] == "10d Level_2"
    assert output["style"]["links"][0]["field"] == "10d Level_2"
    assert "10d Level_2" not in output["style"]["options"]["hidden_columns"]
    assert "_plot_link" in output["style"]["options"]["hidden_columns"]

    underscore = table_with_linked_plots_monthly(_frame("A"), header="_Asset", row_plot_links=True)["_Asset"]
    assert underscore["data"].columns[0] == "_Asset"
    assert "_Asset" not in underscore["style"]["options"]["hidden_columns"]

    helper_collision = table_with_linked_plots_monthly(_frame("A"), header="_plot_link", row_plot_links=True)[
        "_plot_link"
    ]
    assert helper_collision["data"].columns[0] == "_plot_link"
    assert helper_collision["style"]["links"][0]["destination"]["value_field"] == "_plot_link_2"
    assert helper_collision["style"]["options"]["hidden_columns"] == ["_plot_link_2"]


def test_monthly_without_moving_average_uses_seasonal_plot_type() -> None:
    output = table_with_linked_plots_monthly(
        _frame("A"), header="Monthly", moving_average_window=None, all_plots_link=True
    )["Monthly"]
    assert output["plot_names"] == ["monthly-a-seasonal"]


def test_monthly_row_plot_links_are_disabled_by_default() -> None:
    output = table_with_linked_plots_monthly(_frame("A"), header="Monthly")["Monthly"]
    assert "links" not in output["style"]


@pytest.mark.parametrize("page", ["https://example.test/power?view=all#gas", "../power/details.html", "/reports/power"])
@pytest.mark.parametrize(
    "template, option",
    [
        (general_table_with_link, "column_plot_links"),
        (table_with_linked_plots_monthly, "row_plot_links"),
        (rollup_table_hst, "row_plot_links"),
        (rollup_table_fcst, "row_plot_links"),
    ],
)
def test_template_string_links_target_pages_without_generated_plot_routing(template, option, page) -> None:
    payload = template(_frame("A", "B", periods=80), header="Power", **{option: page, "all_plots_link": page})["Power"]
    resolved = resolve_table_style(payload["data"], payload["style"])
    destinations = [*resolved.header_links.values(), *resolved.cell_links.values(), *resolved.index_links.values()]
    if resolved.index_header_link is not None:
        destinations.append(resolved.index_header_link)
    assert len(destinations) >= 3
    assert all(link.kind == TableLinkKind.url and link.value == page for link in destinations)
    assert "all_plots_name" not in payload
    assert len(payload["plot_names"]) == len(payload["plots"])
    html = render_table_html(payload["data"], payload["style"])
    assert f'href="{page}"' in html
    assert "data-runbook-plot-name=" not in html


@pytest.mark.parametrize(
    "page", ["", "javascript:alert(1)", "data:text/html,x", "//example.test", "\\\\example.test", " page.html"]
)
def test_custom_page_links_reject_unsafe_or_empty_urls(page) -> None:
    with pytest.raises(ValueError):
        general_table_with_link(_frame("A", periods=30), header="Power", all_plots_link=page)


@pytest.mark.parametrize(
    "template, options, selected",
    [
        (general_table_with_link, {}, "A"),
        (
            table_with_linked_plots_monthly,
            {"aggregation_type": "MovingAverage", "highlighting_rules": {"window": 30}},
            "10d MA",
        ),
        (rollup_table_fcst, {"params": ["Latest", "5d MA", "20d MA"]}, "5d MA"),
    ],
)
def test_highlight_selection_preserves_negative_text_and_numeric_columns(template, options, selected) -> None:
    frame = -_frame("A", "B", periods=90) - 100
    frame.iloc[-1] = -1000
    if template is rollup_table_fcst:
        options = {**options, "today": frame.index[-1]}
    default = template(frame, header="Power", **options)["Power"]
    chosen = template(frame, header="Power", highlight_columns=[selected], **options)["Power"]
    disabled = template(frame, header="Power", highlight_columns=[], **options)["Power"]
    default_style = resolve_table_style(default["data"], default["style"])
    chosen_style = resolve_table_style(chosen["data"], chosen["style"])
    disabled_style = resolve_table_style(disabled["data"], disabled["style"])
    assert any("background-color" in css for css in default_style.cell_css.values())
    assert {column for (_, column), css in chosen_style.cell_css.items() if "background-color" in css} == {selected}
    assert not any("background-color" in css for css in disabled_style.cell_css.values())
    for payload, resolved in [(chosen, chosen_style), (disabled, disabled_style)]:
        pd.testing.assert_frame_equal(
            payload["data"][list(resolved.visible_columns)], default["data"][list(resolved.visible_columns)]
        )
        assert any(css.get("color") == "red" for css in resolved.cell_css.values())
    with pytest.raises(ValueError, match="highlight_columns"):
        template(frame, header="Power", highlight_columns=["Missing"], **options)
