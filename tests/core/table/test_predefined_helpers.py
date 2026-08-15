from __future__ import annotations

import re

import pandas as pd
from runbook.core.table import (
    band_compare_rules,
    color_negative_red,
    column_compare_rules,
    highlight,
    highlight_on_key,
    highlight_on_range,
    highlight_zscore,
    membership_rules,
    range_rules,
    render_table_html,
    sign_rules,
)
from runbook.core.table.models import TableStylePlan


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


def test_membership_rules() -> None:
    df = pd.DataFrame({"key": ["A", "B", "C"], "value": [1, 2, 3]})
    rules = membership_rules(
        list(df.columns),
        [(1, 0, ["A"], ["B"])],
    )
    html = render_table_html(df, TableStylePlan(rules=rules))

    row0 = _style_for_label(html, df, 0, "value")
    row1 = _style_for_label(html, df, 1, "value")
    row2 = _style_for_label(html, df, 2, "value")
    assert row0.get("background-color") == "#C6EFCE"
    assert row1.get("background-color") == "#FFC7CE"
    assert row2.get("background-color") == "lightblue"


def test_membership_rules_accept_labels() -> None:
    df = pd.DataFrame({"key": ["A", "B", "C"], "value": [1, 2, 3]})
    rules = membership_rules(
        list(df.columns),
        [("value", "key", ["A"], ["B"])],
    )
    html = render_table_html(df, TableStylePlan(rules=rules))

    row0 = _style_for_label(html, df, 0, "value")
    row1 = _style_for_label(html, df, 1, "value")
    row2 = _style_for_label(html, df, 2, "value")
    assert row0.get("background-color") == "#C6EFCE"
    assert row1.get("background-color") == "#FFC7CE"
    assert row2.get("background-color") == "lightblue"


def test_sign_rules() -> None:
    df = pd.DataFrame({"x": [2.0, -1.0, 0.0]})
    rules = sign_rules(list(df.columns), [(0, 0)])
    html = render_table_html(df, TableStylePlan(rules=rules))

    row0 = _style_for_label(html, df, 0, "x")
    row1 = _style_for_label(html, df, 1, "x")
    row2 = _style_for_label(html, df, 2, "x")
    assert row0.get("background-color") == "#C6EFCE"
    assert row1.get("background-color") == "#FFC7CE"
    assert row2.get("background-color") == "lightblue"


def test_sign_rules_accept_labels() -> None:
    df = pd.DataFrame({"x": [2.0, -1.0, 0.0]})
    rules = sign_rules(list(df.columns), [("x", "x")])
    html = render_table_html(df, TableStylePlan(rules=rules))

    row0 = _style_for_label(html, df, 0, "x")
    row1 = _style_for_label(html, df, 1, "x")
    row2 = _style_for_label(html, df, 2, "x")
    assert row0.get("background-color") == "#C6EFCE"
    assert row1.get("background-color") == "#FFC7CE"
    assert row2.get("background-color") == "lightblue"


def test_range_rules() -> None:
    df = pd.DataFrame({"x": [2.0, -2.0, 0.0]})
    rules = range_rules(list(df.columns), [(0, 0, -1.0, 1.0)])
    html = render_table_html(df, TableStylePlan(rules=rules))

    row0 = _style_for_label(html, df, 0, "x")
    row1 = _style_for_label(html, df, 1, "x")
    row2 = _style_for_label(html, df, 2, "x")
    assert row0.get("background-color") == "#C6EFCE"
    assert row1.get("background-color") == "#FFC7CE"
    assert row2.get("background-color") == "lightblue"


def test_range_rules_accept_labels() -> None:
    df = pd.DataFrame({"x": [2.0, -2.0, 0.0]})
    rules = range_rules(list(df.columns), [("x", "x", -1.0, 1.0)])
    html = render_table_html(df, TableStylePlan(rules=rules))

    row0 = _style_for_label(html, df, 0, "x")
    row1 = _style_for_label(html, df, 1, "x")
    row2 = _style_for_label(html, df, 2, "x")
    assert row0.get("background-color") == "#C6EFCE"
    assert row1.get("background-color") == "#FFC7CE"
    assert row2.get("background-color") == "lightblue"


def test_column_compare_rules() -> None:
    df = pd.DataFrame({"lhs": [3.0, 1.0, 2.0], "rhs": [2.0, 2.0, 2.0]})
    rules = column_compare_rules(list(df.columns), [(0, 0, 1)])
    html = render_table_html(df, TableStylePlan(rules=rules))

    row0 = _style_for_label(html, df, 0, "lhs")
    row1 = _style_for_label(html, df, 1, "lhs")
    row2 = _style_for_label(html, df, 2, "lhs")
    assert row0.get("background-color") == "#C6EFCE"
    assert row1.get("background-color") == "#FFC7CE"
    assert row2.get("background-color") == "lightblue"


def test_column_compare_rules_accept_labels() -> None:
    df = pd.DataFrame({"lhs": [3.0, 1.0, 2.0], "rhs": [2.0, 2.0, 2.0]})
    rules = column_compare_rules(list(df.columns), [("lhs", "lhs", "rhs")])
    html = render_table_html(df, TableStylePlan(rules=rules))

    row0 = _style_for_label(html, df, 0, "lhs")
    row1 = _style_for_label(html, df, 1, "lhs")
    row2 = _style_for_label(html, df, 2, "lhs")
    assert row0.get("background-color") == "#C6EFCE"
    assert row1.get("background-color") == "#FFC7CE"
    assert row2.get("background-color") == "lightblue"


def test_band_compare_rules() -> None:
    df = pd.DataFrame(
        {
            "signal": [1.5, 2.5, -1.5, -2.5],
            "weak_ref": [1.0, 1.0, -1.0, -1.0],
            "strong_ref": [2.0, 2.0, -2.0, -2.0],
        }
    )
    rules = band_compare_rules(list(df.columns), [(0, 0, 1, 2)])
    html = render_table_html(df, TableStylePlan(rules=rules))

    row0 = _style_for_label(html, df, 0, "signal")
    row1 = _style_for_label(html, df, 1, "signal")
    row2 = _style_for_label(html, df, 2, "signal")
    row3 = _style_for_label(html, df, 3, "signal")
    assert row0.get("background-color") == "#C6EFCE"
    assert row1.get("background-color") == "green"
    assert row2.get("background-color") == "#FFC7CE"
    assert row3.get("background-color") == "#FFA94D"


def test_band_compare_rules_accept_labels() -> None:
    df = pd.DataFrame(
        {
            "signal": [1.5, 2.5, -1.5, -2.5],
            "weak_ref": [1.0, 1.0, -1.0, -1.0],
            "strong_ref": [2.0, 2.0, -2.0, -2.0],
        }
    )
    rules = band_compare_rules(list(df.columns), [("signal", "signal", "weak_ref", "strong_ref")])
    html = render_table_html(df, TableStylePlan(rules=rules))

    row0 = _style_for_label(html, df, 0, "signal")
    row1 = _style_for_label(html, df, 1, "signal")
    row2 = _style_for_label(html, df, 2, "signal")
    row3 = _style_for_label(html, df, 3, "signal")
    assert row0.get("background-color") == "#C6EFCE"
    assert row1.get("background-color") == "green"
    assert row2.get("background-color") == "#FFC7CE"
    assert row3.get("background-color") == "#FFA94D"


def test_highlight() -> None:
    df = pd.DataFrame(
        {
            "self_target": [2.0, -2.0, 0.0, 0.0, 0.0],
            "sign_source": [3.0, -3.0, 0.0, 0.0, 0.0],
            "sign_target": [0.0, 0.0, 0.0, 0.0, 0.0],
            "triple_target": [3.0, 0.0, 2.0, 2.0, 2.0],
            "triple_gt_ref": [2.0, 2.0, 2.0, 2.0, 2.0],
            "triple_lt_ref": [1.0, 1.0, 1.0, 1.0, 1.0],
            "quad_target": [0.0, 0.0, 0.0, 0.0, 0.0],
            "quad_signal": [4.0, 0.0, 2.0, 2.0, 2.0],
            "quad_upper": [3.0, 3.0, 3.0, 3.0, 3.0],
            "quad_lower": [1.0, 1.0, 1.0, 1.0, 1.0],
            "band5_signal": [5.0, 3.0, 2.0, 1.5, 0.0],
            "band5_strong_ref": [4.0, 4.0, 4.0, 4.0, 4.0],
            "band5_weak_ref": [2.0, 2.0, 2.0, 2.0, 2.0],
            "band5_weak_down_ref": [2.0, 2.0, 2.0, 2.0, 2.0],
            "band5_strong_down_ref": [1.0, 1.0, 1.0, 1.0, 1.0],
            "band6_target": [0.0, 0.0, 0.0, 0.0, 0.0],
            "band6_signal": [5.0, 3.0, 1.5, 0.0, 2.0],
            "band6_strong_ref": [4.0, 4.0, 4.0, 4.0, 4.0],
            "band6_weak_ref": [2.0, 2.0, 2.0, 2.0, 2.0],
            "band6_weak_down_ref": [2.0, 2.0, 2.0, 2.0, 2.0],
            "band6_strong_down_ref": [1.0, 1.0, 1.0, 1.0, 1.0],
        }
    )
    rules = highlight(
        list(df.columns),
        [
            (0,),
            (2, 1),
            (3, 4, 5),
            (6, 7, 8, 9),
            (10, 11, 12, 13, 14),
            (15, 16, 17, 18, 19, 20),
        ],
    )
    html = render_table_html(df, TableStylePlan(rules=rules))

    assert _style_for_label(html, df, 0, "self_target").get("background-color") == "#C6EFCE"
    assert _style_for_label(html, df, 1, "self_target").get("background-color") == "#FFC7CE"
    assert _style_for_label(html, df, 2, "self_target").get("background-color") == "lightblue"

    assert _style_for_label(html, df, 0, "sign_target").get("background-color") == "#C6EFCE"
    assert _style_for_label(html, df, 1, "sign_target").get("background-color") == "#FFC7CE"

    assert _style_for_label(html, df, 0, "triple_target").get("background-color") == "#C6EFCE"
    assert _style_for_label(html, df, 1, "triple_target").get("background-color") == "#FFC7CE"
    assert _style_for_label(html, df, 2, "triple_target").get("background-color") == "lightblue"

    assert _style_for_label(html, df, 0, "quad_target").get("background-color") == "#C6EFCE"
    assert _style_for_label(html, df, 1, "quad_target").get("background-color") == "#FFC7CE"
    assert _style_for_label(html, df, 2, "quad_target").get("background-color") == "lightblue"

    assert _style_for_label(html, df, 0, "band5_signal").get("background-color") == "green"
    assert _style_for_label(html, df, 1, "band5_signal").get("background-color") == "#C6EFCE"
    assert _style_for_label(html, df, 2, "band5_signal").get("background-color") == "lightblue"
    assert _style_for_label(html, df, 3, "band5_signal").get("background-color") == "#FFC7CE"
    assert _style_for_label(html, df, 4, "band5_signal").get("background-color") == "#FFA94D"

    assert _style_for_label(html, df, 0, "band6_target").get("background-color") == "green"
    assert _style_for_label(html, df, 1, "band6_target").get("background-color") == "#C6EFCE"
    assert _style_for_label(html, df, 2, "band6_target").get("background-color") == "#FFC7CE"
    assert _style_for_label(html, df, 3, "band6_target").get("background-color") == "#FFA94D"
    assert _style_for_label(html, df, 4, "band6_target").get("background-color") == "lightblue"


def test_highlight_accepts_labels() -> None:
    df = pd.DataFrame(
        {
            "self_target": [2.0, -2.0, 0.0],
            "sign_source": [3.0, -3.0, 0.0],
            "sign_target": [0.0, 0.0, 0.0],
            "triple_target": [3.0, 0.0, 2.0],
            "triple_gt_ref": [2.0, 2.0, 2.0],
            "triple_lt_ref": [1.0, 1.0, 1.0],
        }
    )
    rules = highlight(
        list(df.columns),
        [
            ("self_target",),
            ("sign_target", "sign_source"),
            ("triple_target", "triple_gt_ref", "triple_lt_ref"),
        ],
    )
    html = render_table_html(df, TableStylePlan(rules=rules))

    assert _style_for_label(html, df, 0, "self_target").get("background-color") == "#C6EFCE"
    assert _style_for_label(html, df, 1, "self_target").get("background-color") == "#FFC7CE"
    assert _style_for_label(html, df, 0, "sign_target").get("background-color") == "#C6EFCE"
    assert _style_for_label(html, df, 1, "sign_target").get("background-color") == "#FFC7CE"
    assert _style_for_label(html, df, 0, "triple_target").get("background-color") == "#C6EFCE"
    assert _style_for_label(html, df, 1, "triple_target").get("background-color") == "#FFC7CE"


def test_highlight_on_key() -> None:
    df = pd.DataFrame({"key": ["A", "B"], "value": [1, 2]})
    rules = highlight_on_key(list(df.columns), [(1, 0, ["A"], ["B"])])
    html = render_table_html(df, TableStylePlan(rules=rules))
    assert "background-color: #C6EFCE" in html
    assert "background-color: #FFC7CE" in html


def test_highlight_on_key_accepts_labels() -> None:
    df = pd.DataFrame({"key": ["A", "B"], "value": [1, 2]})
    rules = highlight_on_key(list(df.columns), [("value", "key", ["A"], ["B"])])
    html = render_table_html(df, TableStylePlan(rules=rules))
    assert "background-color: #C6EFCE" in html
    assert "background-color: #FFC7CE" in html


def test_highlight_on_range() -> None:
    df = pd.DataFrame({"value": [2.0, -2.0]})
    rules = highlight_on_range(list(df.columns), [(0, 0, -1.0, 1.0)])
    html = render_table_html(df, TableStylePlan(rules=rules))
    assert "background-color: #C6EFCE" in html
    assert "background-color: #FFC7CE" in html


def test_highlight_on_range_accepts_labels() -> None:
    df = pd.DataFrame({"value": [2.0, -2.0]})
    rules = highlight_on_range(list(df.columns), [("value", "value", -1.0, 1.0)])
    html = render_table_html(df, TableStylePlan(rules=rules))
    assert "background-color: #C6EFCE" in html
    assert "background-color: #FFC7CE" in html


def test_color_negative_red() -> None:
    df = pd.DataFrame({"value": [2.0, -2.0, 0.0]})
    rules = color_negative_red(list(df.columns), [(0, 0)])
    html = render_table_html(df, TableStylePlan(rules=rules))
    row0 = _style_for_label(html, df, 0, "value")
    row1 = _style_for_label(html, df, 1, "value")
    row2 = _style_for_label(html, df, 2, "value")
    assert row0.get("color") is None
    assert row1.get("color") == "red"
    assert row2.get("color") is None


def test_color_negative_red_accepts_labels() -> None:
    df = pd.DataFrame({"value": [2.0, -2.0, 0.0]})
    rules = color_negative_red(list(df.columns), [("value", "value")])
    html = render_table_html(df, TableStylePlan(rules=rules))
    row0 = _style_for_label(html, df, 0, "value")
    row1 = _style_for_label(html, df, 1, "value")
    row2 = _style_for_label(html, df, 2, "value")
    assert row0.get("color") is None
    assert row1.get("color") == "red"
    assert row2.get("color") is None


def test_highlight_zscore() -> None:
    df = pd.DataFrame(
        {
            "signal": [4.0, 2.1, -1.0, -3.0, 0.0],
            "_mean": [1.0, 1.0, 1.0, 1.0, 1.0],
            "_std": [1.0, 1.0, 1.0, 1.0, 1.0],
        }
    )
    rules = highlight_zscore(list(df.columns), [(0, "_mean", "_std")])
    html = render_table_html(df, TableStylePlan(rules=rules))
    row0 = _style_for_label(html, df, 0, "signal")
    row1 = _style_for_label(html, df, 1, "signal")
    row2 = _style_for_label(html, df, 2, "signal")
    row3 = _style_for_label(html, df, 3, "signal")
    row4 = _style_for_label(html, df, 4, "signal")
    assert row0.get("background-color") == "green"
    assert row1.get("background-color") == "lightgreen"
    assert row2.get("background-color") == "#FFA94D"
    assert row3.get("background-color") == "#FF8787"
    assert row4.get("background-color") == "lightblue"


def test_highlight_zscore_accepts_labels() -> None:
    df = pd.DataFrame(
        {
            "signal": [4.0, 2.1, -1.0, -3.0, 0.0],
            "_mean": [1.0, 1.0, 1.0, 1.0, 1.0],
            "_std": [1.0, 1.0, 1.0, 1.0, 1.0],
        }
    )
    rules = highlight_zscore(list(df.columns), [("signal", "_mean", "_std")])
    html = render_table_html(df, TableStylePlan(rules=rules))
    row0 = _style_for_label(html, df, 0, "signal")
    row1 = _style_for_label(html, df, 1, "signal")
    row2 = _style_for_label(html, df, 2, "signal")
    row3 = _style_for_label(html, df, 3, "signal")
    row4 = _style_for_label(html, df, 4, "signal")
    assert row0.get("background-color") == "green"
    assert row1.get("background-color") == "lightgreen"
    assert row2.get("background-color") == "#FFA94D"
    assert row3.get("background-color") == "#FF8787"
    assert row4.get("background-color") == "lightblue"


def test_highlight_zscore_with_separate_signal_column() -> None:
    df = pd.DataFrame(
        {
            "target": [0.0, 0.0, 0.0, 0.0, 0.0],
            "signal": [4.0, 2.1, -1.0, -3.0, 0.0],
            "_mean": [1.0, 1.0, 1.0, 1.0, 1.0],
            "_std": [1.0, 1.0, 1.0, 1.0, 1.0],
        }
    )
    rules = highlight_zscore(list(df.columns), [(0, 1, "_mean", "_std")])
    html = render_table_html(df, TableStylePlan(rules=rules))
    row0 = _style_for_label(html, df, 0, "target")
    row1 = _style_for_label(html, df, 1, "target")
    row2 = _style_for_label(html, df, 2, "target")
    row3 = _style_for_label(html, df, 3, "target")
    row4 = _style_for_label(html, df, 4, "target")
    assert row0.get("background-color") == "green"
    assert row1.get("background-color") == "lightgreen"
    assert row2.get("background-color") == "#FFA94D"
    assert row3.get("background-color") == "#FF8787"
    assert row4.get("background-color") == "lightblue"


def test_highlight_zscore_with_separate_signal_column_accepts_labels() -> None:
    df = pd.DataFrame(
        {
            "target": [0.0, 0.0, 0.0, 0.0, 0.0],
            "signal": [4.0, 2.1, -1.0, -3.0, 0.0],
            "_mean": [1.0, 1.0, 1.0, 1.0, 1.0],
            "_std": [1.0, 1.0, 1.0, 1.0, 1.0],
        }
    )
    rules = highlight_zscore(list(df.columns), [("target", "signal", "_mean", "_std")])
    html = render_table_html(df, TableStylePlan(rules=rules))
    row0 = _style_for_label(html, df, 0, "target")
    row1 = _style_for_label(html, df, 1, "target")
    row2 = _style_for_label(html, df, 2, "target")
    row3 = _style_for_label(html, df, 3, "target")
    row4 = _style_for_label(html, df, 4, "target")
    assert row0.get("background-color") == "green"
    assert row1.get("background-color") == "lightgreen"
    assert row2.get("background-color") == "#FFA94D"
    assert row3.get("background-color") == "#FF8787"
    assert row4.get("background-color") == "lightblue"
