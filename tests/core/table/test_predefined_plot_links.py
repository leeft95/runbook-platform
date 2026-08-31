from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from runbook.core.table import general_table_with_link, render_table_html, table_with_linked_plots_monthly
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


def test_monthly_plot_names_follow_raw_plot_order_and_filtered_headers_are_not_linked() -> None:
    output = table_with_linked_plots_monthly(
        _frame("A", "B"),
        header="Monthly / Asset",
        columns_filter=["A"],
        all_plots_link=True,
        column_plot_links=True,
    )["Monthly / Asset"]

    assert output["plot_names"] == [
        "monthly-asset-a-seasonal-mva",
        "monthly-asset-b-seasonal-mva",
    ]
    assert output["all_plots_name"] == "monthly-asset-plots"
    assert output["data"].index.name == "Monthly / Asset"
    assert not isinstance(output["data"].index, pd.RangeIndex)
    assert len(output["style"]["links"]) == 1
    assert output["style"]["links"][0]["area"] == "index_header"
    assert "field" not in output["style"]["links"][0]
    assert output["style"]["links"][0]["destination"]["kind"].value == "plot"
    assert output["style"]["links"][0]["destination"]["value"] == "monthly-asset-plots"
    assert (
        '<a href="plots/monthly-asset-plots.html" data-runbook-link-kind="plot" '
        'data-runbook-plot-name="monthly-asset-plots">Monthly / Asset</a>'
        in render_table_html(output["data"], output["style"])
    )

    with pytest.raises(ValueError):
        table_with_linked_plots_monthly(_frame("A"), header="Monthly", column_plot_links=["A"])


def test_monthly_without_moving_average_uses_seasonal_plot_type() -> None:
    output = table_with_linked_plots_monthly(
        _frame("A"), header="Monthly", moving_averge_window=None, all_plots_link=True
    )["Monthly"]
    assert output["plot_names"] == ["monthly-a-seasonal"]
