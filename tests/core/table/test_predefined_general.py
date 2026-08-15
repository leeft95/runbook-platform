from __future__ import annotations

import re

import numpy as np
import pandas as pd
from runbook.core.table import general_table_with_link, render_table_html


def _extract_css_blocks(html: str) -> list[tuple[list[str], dict[str, str]]]:
    match = re.search(r"<style[^>]*>(.*?)</style>", html, flags=re.S)
    if match is None:
        return []

    css = match.group(1)
    blocks: list[tuple[list[str], dict[str, str]]] = []
    for selector_group, body in re.findall(r"([^{}]+)\{([^{}]+)\}", css):
        selectors = [selector.strip() for selector in selector_group.split(",") if selector.strip()]
        props: dict[str, str] = {}
        for item in body.split(";"):
            item = item.strip()
            if not item or ":" not in item:
                continue
            key, value = item.split(":", 1)
            props[key.strip()] = value.strip()
        blocks.append((selectors, props))
    return blocks


def _style_for_label(html: str, df: pd.DataFrame, row: int, col_label: str) -> dict[str, str]:
    col_pos = int(df.columns.get_loc(col_label))
    style: dict[str, str] = {}
    cell_selector_re = re.compile(rf"_row{row}_col{col_pos}$")
    for selectors, props in _extract_css_blocks(html):
        if any(cell_selector_re.search(selector) for selector in selectors):
            style.update(props)
    return style


def test_general_table_with_link_mixed_semantics_and_hidden_helpers() -> None:
    idx = pd.date_range("2024-01-01", periods=80, freq="D")
    base = np.linspace(100.0, 104.0, num=len(idx))
    raw_df = pd.DataFrame(
        {
            "A": base,
            "B": np.full(len(idx), 50.0),
        },
        index=idx,
    )
    raw_df.loc[idx[-1], "A"] = 120.0
    raw_df.loc[idx[-2], "A"] = 104.1

    out = general_table_with_link(raw_df=raw_df, header="Liquids Price", rows=5)
    table_df = out["Liquids Price"]["data"]
    style = out["Liquids Price"]["style"]

    assert "A_chg" in table_df.columns
    assert "A_chg_mean" in table_df.columns
    assert "A_chg_std" in table_df.columns

    html = render_table_html(table_df, style)

    assert "A_chg" not in html
    assert "A_chg_mean" not in html
    assert "A_chg_std" not in html

    rendered_df = table_df.loc[:, ["Liquids Price", "A", "B"]]
    assert rendered_df.iloc[-1, 0] == "20d mv (simple)"
    assert np.isclose(
        float(rendered_df.iloc[-1]["A"]),
        float(raw_df["A"].rolling(20).mean().iloc[-1]),
        equal_nan=False,
    )
    assert np.isclose(float(rendered_df.iloc[-2]["A"]), float(raw_df["A"].iloc[-1]), equal_nan=False)

    dated_row_style = _style_for_label(html, rendered_df, len(rendered_df.index) - 2, "A")
    summary_row_style = _style_for_label(html, rendered_df, len(rendered_df.index) - 1, "A")
    assert dated_row_style.get("background-color") == "green"
    assert summary_row_style.get("background-color") == "green"


def test_general_table_with_link_chart_tuple_overrides_and_plot_count() -> None:
    idx = pd.date_range("2020-01-01", periods=900, freq="D")
    raw_df = pd.DataFrame(
        {
            "A": np.linspace(1.0, 900.0, num=len(idx)),
            "B": np.linspace(2.0, 901.0, num=len(idx)),
        },
        index=idx,
    )

    out = general_table_with_link(
        raw_df=raw_df,
        header="Asset",
        chart_columns={("A", "B"): "line"},
    )

    assert len(out["Asset"]["plots"]) == 2
