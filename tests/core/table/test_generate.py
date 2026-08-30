from __future__ import annotations

import re

import numpy as np
import pandas as pd
import pytest
from runbook.core.table import (
    TableFormatDate,
    TableFormatNumber,
    TableFormatPercent,
    TableFormatString,
    TableStylePlan,
    format_table_value,
    normalize_table_style,
    render_table_html,
    resolve_table_style,
    table_style_hash,
    table_style_json,
    table_style_payload,
)


def test_format_table_value_is_renderer_neutral_for_supported_specs() -> None:
    assert format_table_value(1234.5, TableFormatNumber(digits=1, thousands=True)) == "1,234.5"
    assert format_table_value(0.125, TableFormatPercent(digits=2)) == "12.50%"
    assert format_table_value("2024-01-02", TableFormatDate(pattern="yyyy/MM/dd")) == "2024/01/02"
    assert format_table_value(123, TableFormatString()) == "123"
    assert format_table_value(None, TableFormatString(), na_rep="NA") == "NA"
    assert format_table_value("", TableFormatString()) == ""


def test_table_style_versions_default_to_02_and_preserve_01() -> None:
    default_plan = TableStylePlan()
    assert default_plan.schema_version == "table-style/0.2"
    assert default_plan.model_dump(mode="python")["schema_version"] == "table-style/0.2"
    assert table_style_payload(None)["schema_version"] == "table-style/0.2"

    legacy_plan = TableStylePlan.model_validate({"schema_version": "table-style/0.1"})
    legacy_round_trip = TableStylePlan.model_validate(legacy_plan.model_dump(mode="python"))
    assert legacy_round_trip.model_dump(mode="python")["schema_version"] == "table-style/0.1"
    assert table_style_json(legacy_plan) == table_style_json(legacy_round_trip)
    assert table_style_hash(legacy_plan) == table_style_hash(legacy_round_trip)
    html = render_table_html(pd.DataFrame({"value": [1]}), legacy_plan)
    assert 'data-style-schema="table-style/0.1"' in html


def test_table_style_links_require_02_without_changing_legacy_no_link_payloads() -> None:
    legacy = TableStylePlan.model_validate({"schema_version": "table-style/0.1"})
    legacy_empty = TableStylePlan.model_validate({"schema_version": "table-style/0.1", "links": []})

    assert "links" not in table_style_payload(legacy)
    assert table_style_payload(legacy_empty) == table_style_payload(legacy)
    assert table_style_hash(legacy_empty) == table_style_hash(legacy)
    with pytest.raises(ValueError, match="table-style/0.1 does not support table links"):
        TableStylePlan.model_validate(
            {
                "schema_version": "table-style/0.1",
                "links": [
                    {
                        "area": "header",
                        "field": "month",
                        "destination": {"kind": "plot", "value": "plots/month"},
                    }
                ],
            }
        )


def test_resolve_table_style_is_deterministic_and_renderer_neutral() -> None:
    df = pd.DataFrame({"value": [1.0, -1.0], "helper": [0.0, 0.0]}, index=["keep", "hide"])
    style = {
        "schema_version": "table-style/0.2",
        "format": {"columns": {"value": "{:.1f}"}},
        "sizing": {
            "columns": [{"label": "value", "width_px": 120}],
            "rows": [{"row_ref": {"mode": "label", "value": "keep"}, "width_px": 80}],
        },
        "rules": [
            {
                "id": "negative",
                "target": {"scope": "columns", "labels": ["value"]},
                "condition": {"op": "lt", "rhs": {"kind": "literal", "value": 0}},
                "action": {"text_color": "red"},
            }
        ],
        "options": {
            "hidden_columns": ["helper"],
            "hidden_rows": [{"mode": "label", "value": "hide"}],
        },
    }

    resolved = resolve_table_style(df, style)
    assert resolved == resolve_table_style(df, style)
    assert resolved.visible_columns == ("value",)
    assert resolved.hidden_columns == frozenset({"helper"})
    assert resolved.hidden_rows == frozenset({1})
    assert resolved.column_width_px == {"value": 120}
    assert resolved.row_width_px == {0: 80}
    assert resolved.formats["value"].kind == "number"
    assert resolved.cell_css[(1, "value")]["color"] == "red"


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


def _style_for_cell(html: str, row: int, col_pos: int) -> dict[str, str]:
    style: dict[str, str] = {}
    cell_selector_re = re.compile(rf"_row{row}_col{col_pos}$")
    for selectors, props in _extract_css_blocks(html):
        if any(cell_selector_re.search(selector) for selector in selectors):
            style.update(props)
    return style


def _style_for_label(html: str, df: pd.DataFrame, row: int, col_label: str) -> dict[str, str]:
    return _style_for_cell(html, row, int(df.columns.get_loc(col_label)))


def test_normalize_table_style_parses_python_format_strings() -> None:
    style = {
        "schema_version": "table-style/0.1",
        "format": {
            "columns": {
                "ret": "{:.2%}",
                "vol": "{:,.1f}",
            }
        },
    }

    plan = normalize_table_style(style)
    ret_fmt = plan.format.columns["ret"]
    vol_fmt = plan.format.columns["vol"]
    assert ret_fmt.kind == "percent"
    assert getattr(ret_fmt, "digits", None) == 2
    assert vol_fmt.kind == "number"
    assert getattr(vol_fmt, "digits", None) == 1
    assert getattr(vol_fmt, "thousands", None) is True


def test_table_style_hash_and_json_are_deterministic() -> None:
    style_a = {
        "schema_version": "table-style/0.1",
        "style_key": "k1",
        "options": {"max_rows": 10},
        "format": {"na_rep": "-", "columns": {"x": "{:.2%}"}},
        "rules": [],
    }
    style_b = {
        "rules": [],
        "format": {"columns": {"x": "{:.2%}"}, "na_rep": "-"},
        "schema_version": "table-style/0.1",
        "options": {"max_rows": 10},
        "style_key": "k1",
    }

    assert table_style_hash(style_a) == table_style_hash(style_b)
    assert table_style_json(style_a) == table_style_json(style_b)


def test_render_table_html_applies_literal_column_and_row_comparisons() -> None:
    df = pd.DataFrame(
        {
            "a": [1.0, 3.0, -1.0],
            "b": [2.0, 1.0, 0.5],
        },
        index=["baseline", "x", "y"],
    )

    style = {
        "schema_version": "table-style/0.1",
        "format": {"na_rep": "-", "columns": {"a": "{:.2f}", "b": "{:.2f}"}},
        "sizing": {
            "columns": [{"label": "a", "width_px": 100}],
            "rows": [{"row_ref": {"mode": "label", "value": "baseline"}, "width_px": 200}],
        },
        "rules": [
            {
                "id": "a_lt_zero",
                "target": {"scope": "columns", "labels": ["a"]},
                "condition": {"op": "lt", "rhs": {"kind": "literal", "value": 0}},
                "action": {"text_color": "#B00020"},
            },
            {
                "id": "a_gt_b",
                "target": {"scope": "columns", "labels": ["a"]},
                "condition": {"op": "gt", "rhs": {"kind": "column", "label": "b"}},
                "action": {"background_color": "#E6F4EA"},
            },
            {
                "id": "a_lt_baseline_a",
                "target": {"scope": "columns", "labels": ["a"]},
                "condition": {
                    "op": "lt",
                    "rhs": {
                        "kind": "row",
                        "row_ref": {"mode": "label", "value": "baseline"},
                    },
                },
                "action": {"font_style": "italic"},
            },
        ],
        "options": {"max_rows": 100},
    }

    html = render_table_html(df, style)

    row0_col_a = _style_for_label(html, df, 0, "a")
    assert row0_col_a.get("width") == "200px"
    assert row0_col_a.get("min-width") == "200px"
    assert row0_col_a.get("background-color") == "lightblue"

    row1_col_a = _style_for_label(html, df, 1, "a")
    assert row1_col_a.get("background-color") == "#E6F4EA"
    assert row1_col_a.get("width") == "100px"

    row2_col_a = _style_for_label(html, df, 2, "a")
    assert row2_col_a.get("color") == "#B00020"
    assert row2_col_a.get("font-style") == "italic"


def test_render_table_html_null_comparison_is_no_match() -> None:
    df = pd.DataFrame({"a": [np.nan, 1.0]})
    style = {
        "schema_version": "table-style/0.1",
        "rules": [
            {
                "id": "gt_zero",
                "target": {"scope": "columns", "labels": ["a"]},
                "condition": {"op": "gt", "rhs": {"kind": "literal", "value": 0}},
                "action": {"text_color": "#111111"},
            }
        ],
    }

    html = render_table_html(df, style)
    row0_col_a = _style_for_label(html, df, 0, "a")
    row1_col_a = _style_for_label(html, df, 1, "a")
    assert row0_col_a.get("color") is None
    assert row1_col_a.get("color") == "#111111"


def test_render_table_html_fails_for_unknown_target_column() -> None:
    df = pd.DataFrame({"a": [1.0]})
    style = {
        "schema_version": "table-style/0.1",
        "rules": [
            {
                "id": "unknown",
                "target": {"scope": "columns", "labels": ["missing"]},
                "condition": {"op": "gt", "rhs": {"kind": "literal", "value": 0}},
                "action": {"text_color": "#111111"},
            }
        ],
    }

    with pytest.raises(ValueError, match="target column label not found"):
        _ = render_table_html(df, style)


def test_render_table_html_fails_for_non_unique_row_label_reference() -> None:
    df = pd.DataFrame({"a": [1.0, 2.0]}, index=["dup", "dup"])
    style = {
        "schema_version": "table-style/0.1",
        "rules": [
            {
                "id": "by_row_label",
                "target": {"scope": "columns", "labels": ["a"]},
                "condition": {
                    "op": "gt",
                    "rhs": {
                        "kind": "row",
                        "row_ref": {"mode": "label", "value": "dup"},
                    },
                },
                "action": {"text_color": "#111111"},
            }
        ],
    }

    with pytest.raises(ValueError, match="must resolve to exactly one row"):
        _ = render_table_html(df, style)


def test_render_table_html_rejects_multiindex() -> None:
    df = pd.DataFrame(
        {"a": [1.0, 2.0]},
        index=pd.MultiIndex.from_tuples([(2026, 1), (2026, 2)]),
    )
    with pytest.raises(ValueError, match="MultiIndex index is not supported"):
        _ = render_table_html(df, {"schema_version": "table-style/0.1"})


def test_render_table_html_always_condition_applies_to_all_cells_in_target() -> None:
    df = pd.DataFrame({"a": [np.nan, 1.0]})
    style = {
        "schema_version": "table-style/0.1",
        "rules": [
            {
                "id": "always_bg",
                "target": {"scope": "columns", "labels": ["a"]},
                "condition": {"op": "always"},
                "action": {"background_color": "#EEEEEE"},
            }
        ],
    }

    html = render_table_html(df, style)
    row0_col_a = _style_for_label(html, df, 0, "a")
    row1_col_a = _style_for_label(html, df, 1, "a")
    assert row0_col_a.get("background-color") == "#EEEEEE"
    assert row1_col_a.get("background-color") == "#EEEEEE"


def test_render_table_html_hides_helper_columns_and_rows_after_style_evaluation() -> None:
    df = pd.DataFrame(
        {
            "visible": [10.0, 20.0, 30.0],
            "_mean": [5.0, 5.0, 5.0],
            "_std": [1.0, 1.0, 1.0],
        },
        index=["keep", "hide", "also_keep"],
    )
    style = {
        "schema_version": "table-style/0.1",
        "rules": [
            {
                "id": "zscore_visible",
                "target": {"scope": "columns", "labels": ["visible"]},
                "condition": {
                    "op": "z_gt",
                    "rhs": {
                        "kind": "zscore",
                        "mean_column": "_mean",
                        "std_column": "_std",
                        "num_std": 2.0,
                    },
                },
                "action": {"background_color": "green"},
            }
        ],
        "options": {
            "hidden_columns": ["_mean", "_std"],
            "hidden_rows": [{"mode": "label", "value": "hide"}],
        },
    }

    html = render_table_html(df, style)
    assert "_mean" not in html
    assert "_std" not in html
    assert ">hide<" not in html

    rendered_df = df.drop(index=["hide"]).loc[:, ["visible"]]
    row0_visible = _style_for_label(html, rendered_df, 0, "visible")
    assert row0_visible.get("background-color") == "green"
    assert html.count("background-color: green") >= 1


def test_render_table_html_can_hide_index_column() -> None:
    df = pd.DataFrame({"forecast_month": ["Jan 2026", "Feb 2026"], "value": [1585.0, 1590.0]})
    style = {
        "schema_version": "table-style/0.1",
        "options": {
            "show_index": False,
        },
    }

    html = render_table_html(df, style)

    assert '<th class="blank level0"' not in html
    assert ">0<" not in html
    assert ">1<" not in html
    assert ">forecast_month<" in html


def test_render_table_html_supports_target_column_positions() -> None:
    df = pd.DataFrame({"a": [1.0], "b": [2.0], "c": [3.0]})
    style = {
        "schema_version": "table-style/0.1",
        "rules": [
            {
                "id": "position_rule",
                "target": {"scope": "columns", "positions": [1]},
                "condition": {"op": "always"},
                "action": {"background_color": "#EEEEEE"},
            }
        ],
    }

    html = render_table_html(df, style)
    row0_col_b = _style_for_label(html, df, 0, "b")
    row0_col_a = _style_for_label(html, df, 0, "a")
    assert row0_col_b.get("background-color") == "#EEEEEE"
    assert row0_col_a.get("background-color") == "lightblue"


def test_render_table_html_fails_for_out_of_range_target_column_position() -> None:
    df = pd.DataFrame({"a": [1.0]})
    style = {
        "schema_version": "table-style/0.1",
        "rules": [
            {
                "id": "bad_position",
                "target": {"scope": "columns", "positions": [3]},
                "condition": {"op": "always"},
                "action": {"text_color": "#111111"},
            }
        ],
    }
    with pytest.raises(ValueError, match="target column position out of range"):
        _ = render_table_html(df, style)


def test_render_table_html_supports_zscore_conditions_and_bottom_border() -> None:
    df = pd.DataFrame(
        {
            "signal": [4.0, -3.0, 0.5],
            "_mean": [1.0, 1.0, 1.0],
            "_std": [1.0, 1.0, 1.0],
        },
        index=["a", "b", "c"],
    )
    style = {
        "schema_version": "table-style/0.1",
        "rules": [
            {
                "id": "signal_high",
                "target": {"scope": "columns", "labels": ["signal"]},
                "condition": {
                    "op": "z_gt",
                    "rhs": {
                        "kind": "zscore",
                        "mean_column": "_mean",
                        "std_column": "_std",
                        "num_std": 1,
                    },
                },
                "action": {"background_color": "#E6F4EA"},
            },
            {
                "id": "signal_low",
                "target": {"scope": "columns", "labels": ["signal"]},
                "condition": {
                    "op": "z_lt",
                    "rhs": {
                        "kind": "zscore",
                        "mean_column": "_mean",
                        "std_column": "_std",
                        "num_std": 1,
                    },
                },
                "action": {"text_color": "#B00020"},
            },
            {
                "id": "row_b_border",
                "target": {"scope": "rows", "labels": ["b"]},
                "condition": {"op": "notna"},
                "action": {"bottom_border": True},
            },
        ],
    }

    html = render_table_html(df, style)
    row0_signal = _style_for_label(html, df, 0, "signal")
    row1_signal = _style_for_label(html, df, 1, "signal")
    row2_signal = _style_for_label(html, df, 2, "signal")

    assert row0_signal.get("background-color") == "#E6F4EA"
    assert row1_signal.get("color") == "#B00020"
    assert row1_signal.get("border-bottom") == "1px solid #000000"
    assert row2_signal.get("background-color") == "lightblue"


def test_render_table_html_supports_target_row_positions() -> None:
    df = pd.DataFrame({"a": [1.0, 2.0], "b": [3.0, 4.0]})
    style = {
        "schema_version": "table-style/0.1",
        "rules": [
            {
                "id": "row1_bg",
                "target": {"scope": "rows", "positions": [1]},
                "condition": {"op": "always"},
                "action": {"background_color": "#EEEEEE"},
            }
        ],
    }

    html = render_table_html(df, style)
    row1_col_a = _style_for_label(html, df, 1, "a")
    row1_col_b = _style_for_label(html, df, 1, "b")
    row0_col_a = _style_for_label(html, df, 0, "a")

    assert row1_col_a.get("background-color") == "#EEEEEE"
    assert row1_col_b.get("background-color") == "#EEEEEE"
    assert row0_col_a.get("background-color") == "lightblue"


def test_render_table_html_supports_lhs_column_conditions() -> None:
    df = pd.DataFrame(
        {
            "key": ["ok", "bad", "ok"],
            "signal": [1.0, -1.0, 2.0],
            "other": [10.0, 20.0, 30.0],
        }
    )
    style = {
        "schema_version": "table-style/0.1",
        "rules": [
            {
                "id": "key_highlight",
                "target": {"scope": "columns", "labels": ["signal", "other"]},
                "condition": {
                    "op": "in",
                    "lhs_column": "key",
                    "rhs": {"kind": "literal", "value": ["ok"]},
                },
                "action": {"background_color": "#E6F4EA"},
            }
        ],
    }

    html = render_table_html(df, style)
    row0_signal = _style_for_label(html, df, 0, "signal")
    row0_other = _style_for_label(html, df, 0, "other")
    row1_signal = _style_for_label(html, df, 1, "signal")

    assert row0_signal.get("background-color") == "#E6F4EA"
    assert row0_other.get("background-color") == "#E6F4EA"
    assert row1_signal.get("background-color") is None


def test_render_table_html_supports_condition_all_of_and_any_of() -> None:
    df = pd.DataFrame(
        {
            "key": [1, -1, 2],
            "signal": [5.0, 6.0, 7.0],
            "baseline": [5.0, 5.0, 6.0],
        }
    )
    style = {
        "schema_version": "table-style/0.1",
        "rules": [
            {
                "id": "all_of_rule",
                "target": {"scope": "columns", "labels": ["signal"]},
                "condition": {
                    "op": "always",
                    "all_of": [
                        {
                            "op": "gt",
                            "lhs_column": "key",
                            "rhs": {"kind": "literal", "value": 0},
                        },
                        {
                            "op": "gt",
                            "lhs_column": "signal",
                            "rhs": {"kind": "column", "label": "baseline"},
                        },
                    ],
                },
                "action": {"background_color": "#E6F4EA"},
            },
            {
                "id": "any_of_rule",
                "target": {"scope": "columns", "labels": ["signal"]},
                "condition": {
                    "op": "always",
                    "any_of": [
                        {
                            "op": "lt",
                            "lhs_column": "key",
                            "rhs": {"kind": "literal", "value": 0},
                        },
                        {
                            "op": "eq",
                            "lhs_column": "signal",
                            "rhs": {"kind": "column", "label": "baseline"},
                        },
                    ],
                },
                "action": {"text_color": "#B00020"},
            },
        ],
    }

    html = render_table_html(df, style)
    row0_signal = _style_for_label(html, df, 0, "signal")
    row1_signal = _style_for_label(html, df, 1, "signal")
    row2_signal = _style_for_label(html, df, 2, "signal")

    assert row0_signal.get("background-color") == "lightblue"
    assert row0_signal.get("color") == "#B00020"

    assert row1_signal.get("background-color") is None
    assert row1_signal.get("color") == "#B00020"

    assert row2_signal.get("background-color") == "#E6F4EA"
    assert row2_signal.get("color") is None


def test_render_table_html_applies_global_styles_and_background_modes() -> None:
    df = pd.DataFrame({"a": [1.0, 2.0], "b": [3.0, 4.0]})
    style = {
        "schema_version": "table-style/0.1",
        "options": {
            "max_rows": 100,
            "global_style": {
                "background_color": "#FAFAFA",
                "one_bg_color": True,
                "header_border_bottom": "1px solid black",
                "table_border": "2px solid black",
                "font_size": "11pt",
                "font_family": "Calibri",
                "header_text_align": "center",
            },
        },
    }

    html = render_table_html(df, style)
    assert "border-bottom: 1px solid black" in html
    assert "border: 2px solid black" in html
    assert "font-family: Calibri" in html
    assert "text-align: center" in html

    row0_col_a = _style_for_label(html, df, 0, "a")
    row1_col_a = _style_for_label(html, df, 1, "a")
    assert row0_col_a.get("background-color") == "#FAFAFA"
    assert row1_col_a.get("background-color") == "#FAFAFA"


def test_render_table_html_supports_global_precision_thousands_and_column_override() -> None:
    df = pd.DataFrame(
        {
            "a": [1234.567],
            "b": [0.1234],
            "c": [None],
        }
    )

    style = {
        "schema_version": "table-style/0.1",
        "format": {
            "na_rep": "-",
            "precision": 1,
            "thousands": ",",
            "columns": {"b": "{:.2%}"},
        },
    }

    html = render_table_html(df, style)
    assert "1,234.6" in html
    assert "12.34%" in html
    assert ">-<" in html
