from __future__ import annotations

import re

import pandas as pd
from runbook.core.table.builder import normalize_table_style
from runbook.sdk.table_style import (
    action,
    condition,
    format_percent,
    legacy_zscore_band_rules,
    render_table_html,
    rhs_literal,
    rhs_zscore,
    rule,
    table_style,
    table_style_hash,
    table_style_payload,
    target_column_positions,
    target_columns,
)


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


def test_sdk_table_style_builders_produce_valid_canonical_plan() -> None:
    style = table_style(
        key="returns_v1",
        formats=[format_percent("returns", digits=2)],
        rules=[
            rule(
                "negative_red",
                target_columns(["returns"]),
                condition("lt", rhs=rhs_literal(0)),
                action(text_color="#B00020", font_weight="600"),
            )
        ],
        max_rows=100,
        na_rep="-",
    )

    plan = normalize_table_style(style)
    assert style["schema_version"] == "table-style/0.2"
    assert plan.style_key == "returns_v1"
    assert plan.format.columns["returns"].kind == "percent"
    assert plan.options.max_rows == 100


def test_sdk_table_style_hash_and_payload_are_deterministic() -> None:
    style_a = table_style(
        key="k",
        formats=[format_percent("returns", digits=2)],
        rules=[
            rule(
                "r",
                target_columns(["returns"]),
                condition("gt", rhs=rhs_literal(0)),
                action(background_color="#E6F4EA"),
            )
        ],
    )
    style_b = table_style(
        key="k",
        formats=[format_percent("returns", digits=2)],
        rules=[
            rule(
                "r",
                target_columns(["returns"]),
                condition("gt", rhs=rhs_literal(0)),
                action(background_color="#E6F4EA"),
            )
        ],
    )

    assert table_style_payload(style_a) == table_style_payload(style_b)
    assert table_style_hash(style_a) == table_style_hash(style_b)


def test_sdk_table_style_preserves_typed_links_in_the_versioned_payload() -> None:
    style = table_style(
        links=[
            {
                "area": "header",
                "field": "month",
                "destination": {"kind": "plot", "value": "plots/month"},
            }
        ]
    )

    payload = table_style_payload(style)

    assert payload["schema_version"] == "table-style/0.2"
    assert payload["links"] == [
        {"area": "header", "field": "month", "destination": {"kind": "plot", "value": "plots/month"}}
    ]


def test_sdk_render_table_html_applies_rule() -> None:
    df = pd.DataFrame({"returns": [0.1, -0.2]}, index=["a", "b"])
    style = table_style(
        formats=[format_percent("returns", digits=1)],
        rules=[
            rule(
                "negative_red",
                target_columns(["returns"]),
                condition("lt", rhs=rhs_literal(0)),
                action(text_color="#B00020"),
            )
        ],
    )

    html = render_table_html(df, style)

    assert "10.0%" in html
    assert "-20.0%" in html
    assert "color: #B00020" in html


def test_sdk_table_style_can_hide_index_column() -> None:
    df = pd.DataFrame({"forecast_month": ["Jan 2026", "Feb 2026"], "value": [1585.0, 1590.0]})
    style = table_style(show_index=False)

    html = render_table_html(df, style)

    assert '<th class="blank level0"' not in html
    assert ">0<" not in html
    assert ">1<" not in html


def test_sdk_rule_defaults_condition_to_always() -> None:
    df = pd.DataFrame({"returns": [0.1, None]}, index=["a", "b"])
    style = table_style(
        rules=[
            rule(
                "always_bg",
                target_columns(["returns"]),
                action=action(background_color="#E6F4EA"),
            )
        ],
    )
    html = render_table_html(df, style)
    row0 = _style_for_cell(html, 0, 0)
    row1 = _style_for_cell(html, 1, 0)
    assert row0.get("background-color") == "#E6F4EA"
    assert row1.get("background-color") == "#E6F4EA"


def test_sdk_target_column_positions_helper() -> None:
    df = pd.DataFrame({"a": [1.0], "b": [2.0]})
    style = table_style(
        rules=[
            rule(
                "pos_target",
                target_column_positions([1]),
                action=action(background_color="#E6F4EA"),
            )
        ]
    )
    html = render_table_html(df, style)
    row0_col_a = _style_for_cell(html, 0, 0)
    row0_col_b = _style_for_cell(html, 0, 1)
    assert row0_col_b.get("background-color") == "#E6F4EA"
    assert row0_col_a.get("background-color") == "lightblue"


def test_sdk_legacy_zscore_band_rules_and_border_action() -> None:
    df = pd.DataFrame(
        {
            "signal": [4.0, -3.0],
            "_mean": [1.0, 1.0],
            "_std": [1.0, 1.0],
        },
        index=["a", "b"],
    )
    style = table_style(
        rules=[
            *legacy_zscore_band_rules(
                target_column="signal",
                mean_column="_mean",
                std_column="_std",
            ),
            rule(
                "border_row_b",
                target_columns(["signal"]),
                condition("eq", rhs=rhs_literal(-3.0)),
                action(border_right="2px solid black", bottom_border=True),
            ),
            rule(
                "z_gt_custom",
                target_columns(["signal"]),
                condition(
                    "z_gt",
                    rhs=rhs_zscore(mean_column="_mean", std_column="_std", num_std=2.0),
                ),
                action(text_color="#222222"),
            ),
        ]
    )
    html = render_table_html(df, style)
    assert "background-color: green" in html
    assert "background-color: #FF8787" in html
    assert "border-right: 2px solid black" in html
    assert "border-bottom: 1px solid #000000" in html
    assert "color: #222222" in html


def test_sdk_condition_supports_lhs_column_and_composites() -> None:
    df = pd.DataFrame(
        {
            "key": [1, -1, 2],
            "signal": [5.0, 6.0, 7.0],
            "baseline": [5.0, 5.0, 6.0],
        }
    )
    style = table_style(
        rules=[
            rule(
                "all_of_rule",
                target_columns(["signal"]),
                condition(
                    "always",
                    all_of=[
                        condition("gt", rhs=rhs_literal(0), lhs_column="key"),
                        condition(
                            "gt",
                            rhs={"kind": "column", "label": "baseline"},
                            lhs_column="signal",
                        ),
                    ],
                ),
                action(background_color="#E6F4EA"),
            ),
            rule(
                "any_of_rule",
                target_columns(["signal"]),
                condition(
                    "always",
                    any_of=[
                        condition("lt", rhs=rhs_literal(0), lhs_column="key"),
                        condition(
                            "eq",
                            rhs={"kind": "column", "label": "baseline"},
                            lhs_column="signal",
                        ),
                    ],
                ),
                action(text_color="#B00020"),
            ),
        ]
    )
    html = render_table_html(df, style)
    assert html.count("background-color: #E6F4EA") == 1
    assert html.count("color: #B00020") == 2
