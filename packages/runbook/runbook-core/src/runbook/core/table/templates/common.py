from __future__ import annotations

import re
import typing as tp
import unicodedata

from ..models import (
    ConditionOp,
    TableAction,
    TableColumnRHS,
    TableCondition,
    TableLink,
    TableLinkDestination,
    TableLinkKind,
    TableLiteralRHS,
    TableRule,
    TableTarget,
    TableZScoreRHS,
    TargetScope,
)

ColumnRef = int | str


def _slugify_link_part(value: object) -> str:
    """Normalize a link name component to a stable lowercase hyphen slug."""
    normalized = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")


def _build_plot_link_metadata(
    table_name: object,
    plot_columns: tp.Sequence[tuple[str, str]],
    rendered_columns: tp.Sequence[str],
    *,
    column_plot_links: bool | list[str],
    all_plots_link: bool,
) -> tuple[list[str], list[TableLink], str | None]:
    """Build deterministic plot names and semantic table links."""
    table_slug = _slugify_link_part(table_name)
    if not table_slug:
        raise ValueError("table/header name must contain a slug when plot links are requested")

    plot_names: list[str] = []
    plot_columns_by_name: dict[str, str] = {}
    seen_names: set[str] = set()
    for column, plot_type in plot_columns:
        column_name = str(column)
        column_slug = _slugify_link_part(column_name)
        if not column_slug:
            raise ValueError(f"Column '{column_name}' cannot be normalized for a plot link")
        plot_type_slug = _slugify_link_part(plot_type)
        name = f"{table_slug}-{column_slug}-{plot_type_slug}"
        if name in seen_names:
            raise ValueError(f"Duplicate generated plot name: {name}")
        seen_names.add(name)
        plot_names.append(name)
        plot_columns_by_name[column_name] = name

    rendered = {str(column) for column in rendered_columns}
    eligible = [column for column, _ in plot_columns if str(column) in rendered]
    if column_plot_links is True:
        selected = set(eligible)
    elif isinstance(column_plot_links, list):
        selected = set()
        known = set(plot_columns_by_name)
        for column in column_plot_links:
            if not isinstance(column, str) or column not in known:
                raise ValueError(f"Column '{column}' is unknown or has no generated plot")
            if column not in rendered:
                raise ValueError(f"Column '{column}' cannot be linked as a rendered header")
            selected.add(column)
    else:
        selected = set()

    links = [
        TableLink(
            area="header",
            field=column,
            destination=TableLinkDestination(kind=TableLinkKind.plot, value=plot_columns_by_name[column]),
        )
        for column in eligible
        if column in selected
    ]
    all_plots_name = f"{table_slug}-plots" if all_plots_link else None
    if all_plots_name is not None:
        links.append(
            TableLink(
                area="index_header",
                destination=TableLinkDestination(kind=TableLinkKind.plot, value=all_plots_name),
            )
        )
    return plot_names, links, all_plots_name


def _resolve_column_position(columns: tp.Sequence[str], ref: ColumnRef) -> int | None:
    """Resolve column position."""
    if isinstance(ref, int):
        return ref if 0 <= ref < len(columns) else None
    if isinstance(ref, str):
        try:
            return list(columns).index(ref)
        except ValueError:
            return None
    return None


def _resolve_target_positions(columns: tp.Sequence[str], refs: tp.Sequence[ColumnRef]) -> tuple[int, ...] | None:
    """Resolve target positions."""
    resolved: list[int] = []
    for ref in refs:
        position = _resolve_column_position(columns, ref)
        if position is None:
            return None
        resolved.append(position)
    return tuple(resolved)


def highlight_zscore(
    columns: tp.Sequence[str],
    zscore_targets: tp.Sequence[
        tuple[ColumnRef, ColumnRef, ColumnRef] | tuple[ColumnRef, ColumnRef, ColumnRef, ColumnRef]
    ],
) -> list[TableRule]:
    """Build z-score band rules from 3-item and 4-item tuple forms."""
    rules: list[TableRule] = []
    for target in zscore_targets:
        lhs_column: str | None = None
        if len(target) == 3:
            resolved = _resolve_target_positions(columns, tp.cast(tuple[ColumnRef, ColumnRef, ColumnRef], target))
            if resolved is None:
                continue
            target_pos, mean_pos, std_pos = resolved
        elif len(target) == 4:
            resolved = _resolve_target_positions(
                columns,
                tp.cast(tuple[ColumnRef, ColumnRef, ColumnRef, ColumnRef], target),
            )
            if resolved is None:
                continue
            target_pos, signal_pos, mean_pos, std_pos = resolved
            lhs_column = columns[signal_pos]
        else:
            continue

        mean_col = columns[mean_pos]
        std_col = columns[std_pos]

        rules.extend(
            [
                TableRule(
                    id=f"col{target_pos}_z_gt_1",
                    target=TableTarget(scope=TargetScope.columns, positions=[target_pos]),
                    condition=TableCondition(
                        op=ConditionOp.z_gt,
                        lhs_column=lhs_column,
                        rhs=TableZScoreRHS(mean_column=mean_col, std_column=std_col, num_std=1.0),
                    ),
                    action=TableAction(background_color="lightgreen"),
                ),
                TableRule(
                    id=f"col{target_pos}_z_gt_2",
                    target=TableTarget(scope=TargetScope.columns, positions=[target_pos]),
                    condition=TableCondition(
                        op=ConditionOp.z_gt,
                        lhs_column=lhs_column,
                        rhs=TableZScoreRHS(mean_column=mean_col, std_column=std_col, num_std=2.0),
                    ),
                    action=TableAction(background_color="green"),
                ),
                TableRule(
                    id=f"col{target_pos}_z_lt_1",
                    target=TableTarget(scope=TargetScope.columns, positions=[target_pos]),
                    condition=TableCondition(
                        op=ConditionOp.z_lt,
                        lhs_column=lhs_column,
                        rhs=TableZScoreRHS(mean_column=mean_col, std_column=std_col, num_std=1.0),
                    ),
                    action=TableAction(background_color="#FFA94D"),
                ),
                TableRule(
                    id=f"col{target_pos}_z_lt_2",
                    target=TableTarget(scope=TargetScope.columns, positions=[target_pos]),
                    condition=TableCondition(
                        op=ConditionOp.z_lt,
                        lhs_column=lhs_column,
                        rhs=TableZScoreRHS(mean_column=mean_col, std_column=std_col, num_std=2.0),
                    ),
                    action=TableAction(background_color="#FF8787"),
                ),
            ]
        )
    return rules


def membership_rules(
    columns: tp.Sequence[str],
    membership_targets: tp.Sequence[
        tuple[ColumnRef, ColumnRef, tp.Sequence[tp.Any] | None, tp.Sequence[tp.Any] | None]
    ],
    true_color: str = "#C6EFCE",
    false_color: str = "#FFC7CE",
) -> list[TableRule]:
    """Build key-membership highlight rules (stylehighlight_by_key* family)."""
    rules: list[TableRule] = []
    for target_ref, key_ref, true_values, false_values in membership_targets:
        resolved = _resolve_target_positions(columns, (target_ref, key_ref))
        if resolved is None:
            continue
        target_pos, key_pos = resolved

        key_col = columns[key_pos]

        if true_values:
            rules.append(
                TableRule(
                    id=f"col{target_pos}_key_in_true",
                    target=TableTarget(scope=TargetScope.columns, positions=[target_pos]),
                    condition=TableCondition(
                        op=ConditionOp.in_,
                        lhs_column=key_col,
                        rhs=TableLiteralRHS(value=list(true_values)),
                    ),
                    action=TableAction(background_color=true_color),
                )
            )

        if false_values:
            rules.append(
                TableRule(
                    id=f"col{target_pos}_key_in_false",
                    target=TableTarget(scope=TargetScope.columns, positions=[target_pos]),
                    condition=TableCondition(
                        op=ConditionOp.in_,
                        lhs_column=key_col,
                        rhs=TableLiteralRHS(value=list(false_values)),
                    ),
                    action=TableAction(background_color=false_color),
                )
            )

    return rules


def sign_rules(
    columns: tp.Sequence[str],
    sign_targets: tp.Sequence[tuple[ColumnRef, ColumnRef]],
    positive_color: str = "#C6EFCE",
    negative_color: str = "#FFC7CE",
) -> list[TableRule]:
    """Build sign highlight rules (style_negative_positive / style_Neglight basic cases)."""
    rules: list[TableRule] = []
    for target_ref, source_ref in sign_targets:
        resolved = _resolve_target_positions(columns, (target_ref, source_ref))
        if resolved is None:
            continue
        target_pos, source_pos = resolved

        source_col = columns[source_pos]
        rules.extend(
            [
                TableRule(
                    id=f"col{target_pos}_src{source_pos}_gt_zero",
                    target=TableTarget(scope=TargetScope.columns, positions=[target_pos]),
                    condition=TableCondition(
                        op=ConditionOp.gt,
                        lhs_column=source_col,
                        rhs=TableLiteralRHS(value=0),
                    ),
                    action=TableAction(background_color=positive_color),
                ),
                TableRule(
                    id=f"col{target_pos}_src{source_pos}_lt_zero",
                    target=TableTarget(scope=TargetScope.columns, positions=[target_pos]),
                    condition=TableCondition(
                        op=ConditionOp.lt,
                        lhs_column=source_col,
                        rhs=TableLiteralRHS(value=0),
                    ),
                    action=TableAction(background_color=negative_color),
                ),
            ]
        )
    return rules


def range_rules(
    columns: tp.Sequence[str],
    range_targets: tp.Sequence[tuple[ColumnRef, ColumnRef, float, float]],
    above_color: str = "#C6EFCE",
    below_color: str = "#FFC7CE",
) -> list[TableRule]:
    """Build threshold/range rules (style_Neglight_on_range pattern)."""
    rules: list[TableRule] = []
    for target_ref, source_ref, lower, upper in range_targets:
        resolved = _resolve_target_positions(columns, (target_ref, source_ref))
        if resolved is None:
            continue
        target_pos, source_pos = resolved
        if lower > upper:
            continue

        source_col = columns[source_pos]
        rules.extend(
            [
                TableRule(
                    id=f"col{target_pos}_src{source_pos}_gt_upper",
                    target=TableTarget(scope=TargetScope.columns, positions=[target_pos]),
                    condition=TableCondition(
                        op=ConditionOp.gt,
                        lhs_column=source_col,
                        rhs=TableLiteralRHS(value=upper),
                    ),
                    action=TableAction(background_color=above_color),
                ),
                TableRule(
                    id=f"col{target_pos}_src{source_pos}_lt_lower",
                    target=TableTarget(scope=TargetScope.columns, positions=[target_pos]),
                    condition=TableCondition(
                        op=ConditionOp.lt,
                        lhs_column=source_col,
                        rhs=TableLiteralRHS(value=lower),
                    ),
                    action=TableAction(background_color=below_color),
                ),
            ]
        )
    return rules


def column_compare_rules(
    columns: tp.Sequence[str],
    compare_targets: tp.Sequence[tuple[ColumnRef, ColumnRef, ColumnRef]],
    gt_color: str = "#C6EFCE",
    lt_color: str = "#FFC7CE",
) -> list[TableRule]:
    """Build  pairwise column-compare rules (used by style_Neglight multi-column cases)."""
    rules: list[TableRule] = []
    for target_ref, lhs_ref, rhs_ref in compare_targets:
        resolved = _resolve_target_positions(columns, (target_ref, lhs_ref, rhs_ref))
        if resolved is None:
            continue
        target_pos, lhs_pos, rhs_pos = resolved

        lhs_col = columns[lhs_pos]
        rhs_col = columns[rhs_pos]
        rules.extend(
            [
                TableRule(
                    id=f"col{target_pos}_src{lhs_pos}_gt_src{rhs_pos}",
                    target=TableTarget(scope=TargetScope.columns, positions=[target_pos]),
                    condition=TableCondition(
                        op=ConditionOp.gt,
                        lhs_column=lhs_col,
                        rhs=TableColumnRHS(label=rhs_col),
                    ),
                    action=TableAction(background_color=gt_color),
                ),
                TableRule(
                    id=f"col{target_pos}_src{lhs_pos}_lt_src{rhs_pos}",
                    target=TableTarget(scope=TargetScope.columns, positions=[target_pos]),
                    condition=TableCondition(
                        op=ConditionOp.lt,
                        lhs_column=lhs_col,
                        rhs=TableColumnRHS(label=rhs_col),
                    ),
                    action=TableAction(background_color=lt_color),
                ),
            ]
        )
    return rules


def band_compare_rules(
    columns: tp.Sequence[str],
    band_targets: tp.Sequence[tuple[ColumnRef, ColumnRef, ColumnRef, ColumnRef]],
    strong_up_color: str = "green",
    weak_up_color: str = "#C6EFCE",
    weak_down_color: str = "#FFC7CE",
    strong_down_color: str = "#FFA94D",
) -> list[TableRule]:
    """Build 4-band compare rules using weak/strong reference columns."""
    rules: list[TableRule] = []
    for target_ref, lhs_ref, weak_ref, strong_ref in band_targets:
        resolved = _resolve_target_positions(columns, (target_ref, lhs_ref, weak_ref, strong_ref))
        if resolved is None:
            continue
        target_pos, lhs_pos, weak_ref_pos, strong_ref_pos = resolved

        lhs_col = columns[lhs_pos]
        weak_ref_col = columns[weak_ref_pos]
        strong_ref_col = columns[strong_ref_pos]
        rules.extend(
            [
                TableRule(
                    id=f"col{target_pos}_band_up_weak",
                    target=TableTarget(scope=TargetScope.columns, positions=[target_pos]),
                    condition=TableCondition(
                        op=ConditionOp.gt,
                        lhs_column=lhs_col,
                        rhs=TableColumnRHS(label=weak_ref_col),
                    ),
                    action=TableAction(background_color=weak_up_color),
                ),
                TableRule(
                    id=f"col{target_pos}_band_up_strong",
                    target=TableTarget(scope=TargetScope.columns, positions=[target_pos]),
                    condition=TableCondition(
                        all_of=[
                            TableCondition(
                                op=ConditionOp.gt,
                                lhs_column=lhs_col,
                                rhs=TableColumnRHS(label=weak_ref_col),
                            ),
                            TableCondition(
                                op=ConditionOp.gt,
                                lhs_column=lhs_col,
                                rhs=TableColumnRHS(label=strong_ref_col),
                            ),
                        ]
                    ),
                    action=TableAction(background_color=strong_up_color),
                ),
                TableRule(
                    id=f"col{target_pos}_band_down_weak",
                    target=TableTarget(scope=TargetScope.columns, positions=[target_pos]),
                    condition=TableCondition(
                        op=ConditionOp.lt,
                        lhs_column=lhs_col,
                        rhs=TableColumnRHS(label=weak_ref_col),
                    ),
                    action=TableAction(background_color=weak_down_color),
                ),
                TableRule(
                    id=f"col{target_pos}_band_down_strong",
                    target=TableTarget(scope=TargetScope.columns, positions=[target_pos]),
                    condition=TableCondition(
                        all_of=[
                            TableCondition(
                                op=ConditionOp.lt,
                                lhs_column=lhs_col,
                                rhs=TableColumnRHS(label=weak_ref_col),
                            ),
                            TableCondition(
                                op=ConditionOp.lt,
                                lhs_column=lhs_col,
                                rhs=TableColumnRHS(label=strong_ref_col),
                            ),
                        ]
                    ),
                    action=TableAction(background_color=strong_down_color),
                ),
            ]
        )
    return rules


def highlight_on_key(
    columns: tp.Sequence[str],
    key_targets: tp.Sequence[tuple[ColumnRef, ColumnRef, tp.Sequence[tp.Any] | None, tp.Sequence[tp.Any] | None]],
    true_colour: str = "#C6EFCE",
    false_colour: str = "#FFC7CE",
) -> list[TableRule]:
    """Handle highlight on key."""
    return membership_rules(
        columns=columns,
        membership_targets=key_targets,
        true_color=true_colour,
        false_color=false_colour,
    )


def highlight_on_range(
    columns: tp.Sequence[str],
    range_targets: tp.Sequence[tuple[ColumnRef, ColumnRef, float, float]],
    true_colour: str = "#C6EFCE",
    false_colour: str = "#FFC7CE",
) -> list[TableRule]:
    """Handle highlight on range."""
    return range_rules(
        columns=columns,
        range_targets=range_targets,
        above_color=true_colour,
        below_color=false_colour,
    )


def highlight(
    columns: tp.Sequence[str],
    highlight_targets: tp.Sequence[tuple[ColumnRef, ...]],
    true_colour: str = "#C6EFCE",
    false_colour: str = "#FFC7CE",
    strong_up_colour: str = "green",
    strong_down_colour: str = "#FFA94D",
) -> list[TableRule]:
    """tuple columns based styling rules
    One position means "style this column from its own sign".
    Two positions mean "style target_pos using the sign of source_pos".
    Three positions mean "style target_pos by comparing it directly to upper and lower reference columns".
    Four positions mean "style target_pos using a separate lhs signal column compared to upper and lower references".
    Five positions mean "style the target column itself across strong/weak up and down bands".
    Six positions mean "style target_pos using a separate signal column evaluated across strong/weak bands".
    Returns list of TableRule
    """
    rules: list[TableRule] = []
    for index, target in enumerate(highlight_targets):
        if not target:
            continue
        resolved = _resolve_target_positions(columns, target)
        if resolved is None:
            continue

        if len(resolved) == 1:
            # One position means "style this column from its own sign".
            target_pos = resolved[0]
            rules.extend(
                sign_rules(
                    columns=columns,
                    sign_targets=[(target_pos, target_pos)],
                    positive_color=true_colour,
                    negative_color=false_colour,
                )
            )
            continue

        if len(resolved) == 2:
            # Two positions mean "style target_pos using the sign of source_pos".
            rules.extend(
                sign_rules(
                    columns=columns,
                    sign_targets=[tp.cast(tuple[int, int], resolved)],
                    positive_color=true_colour,
                    negative_color=false_colour,
                )
            )
            continue

        if len(resolved) == 3:
            # Three positions mean "style target_pos by comparing it directly to upper and lower reference columns".
            target_pos, gt_ref_pos, lt_ref_pos = tp.cast(tuple[int, int, int], resolved)
            target_col = columns[target_pos]
            rules.extend(
                [
                    TableRule(
                        id=f"highlight_{index}_gt",
                        target=TableTarget(scope=TargetScope.columns, positions=[target_pos]),
                        condition=TableCondition(
                            op=ConditionOp.gt,
                            lhs_column=target_col,
                            rhs=TableColumnRHS(label=columns[gt_ref_pos]),
                        ),
                        action=TableAction(background_color=true_colour),
                    ),
                    TableRule(
                        id=f"highlight_{index}_lt",
                        target=TableTarget(scope=TargetScope.columns, positions=[target_pos]),
                        condition=TableCondition(
                            op=ConditionOp.lt,
                            lhs_column=target_col,
                            rhs=TableColumnRHS(label=columns[lt_ref_pos]),
                        ),
                        action=TableAction(background_color=false_colour),
                    ),
                ]
            )
            continue

        if len(resolved) == 4:
            # Four positions mean "style target_pos using a separate lhs signal column compared to upper and lower references".
            target_pos, lhs_pos, gt_ref_pos, lt_ref_pos = tp.cast(tuple[int, int, int, int], resolved)
            lhs_col = columns[lhs_pos]
            rules.extend(
                [
                    TableRule(
                        id=f"highlight_{index}_lhs_gt",
                        target=TableTarget(scope=TargetScope.columns, positions=[target_pos]),
                        condition=TableCondition(
                            op=ConditionOp.gt,
                            lhs_column=lhs_col,
                            rhs=TableColumnRHS(label=columns[gt_ref_pos]),
                        ),
                        action=TableAction(background_color=true_colour),
                    ),
                    TableRule(
                        id=f"highlight_{index}_lhs_lt",
                        target=TableTarget(scope=TargetScope.columns, positions=[target_pos]),
                        condition=TableCondition(
                            op=ConditionOp.lt,
                            lhs_column=lhs_col,
                            rhs=TableColumnRHS(label=columns[lt_ref_pos]),
                        ),
                        action=TableAction(background_color=false_colour),
                    ),
                ]
            )
            continue

        if len(resolved) == 5:
            # Five positions mean "style the target column itself across strong/weak up and down bands".
            target_pos, strong_up_pos, weak_up_pos, weak_down_pos, strong_down_pos = tp.cast(
                tuple[int, int, int, int, int],
                resolved,
            )
            lhs_col = columns[target_pos]
            strong_up_col = columns[strong_up_pos]
            weak_up_col = columns[weak_up_pos]
            weak_down_col = columns[weak_down_pos]
            strong_down_col = columns[strong_down_pos]
            rules.extend(
                [
                    TableRule(
                        id=f"highlight_{index}_weak_up",
                        target=TableTarget(scope=TargetScope.columns, positions=[target_pos]),
                        condition=TableCondition(
                            all_of=[
                                TableCondition(
                                    op=ConditionOp.lt,
                                    lhs_column=lhs_col,
                                    rhs=TableColumnRHS(label=strong_up_col),
                                ),
                                TableCondition(
                                    op=ConditionOp.gt,
                                    lhs_column=lhs_col,
                                    rhs=TableColumnRHS(label=weak_up_col),
                                ),
                            ]
                        ),
                        action=TableAction(background_color=true_colour),
                    ),
                    TableRule(
                        id=f"highlight_{index}_strong_up",
                        target=TableTarget(scope=TargetScope.columns, positions=[target_pos]),
                        condition=TableCondition(
                            op=ConditionOp.gt,
                            lhs_column=lhs_col,
                            rhs=TableColumnRHS(label=strong_up_col),
                        ),
                        action=TableAction(background_color=strong_up_colour),
                    ),
                    TableRule(
                        id=f"highlight_{index}_weak_down",
                        target=TableTarget(scope=TargetScope.columns, positions=[target_pos]),
                        condition=TableCondition(
                            all_of=[
                                TableCondition(
                                    op=ConditionOp.lt,
                                    lhs_column=lhs_col,
                                    rhs=TableColumnRHS(label=weak_down_col),
                                ),
                                TableCondition(
                                    op=ConditionOp.gt,
                                    lhs_column=lhs_col,
                                    rhs=TableColumnRHS(label=strong_down_col),
                                ),
                            ]
                        ),
                        action=TableAction(background_color=false_colour),
                    ),
                    TableRule(
                        id=f"highlight_{index}_strong_down",
                        target=TableTarget(scope=TargetScope.columns, positions=[target_pos]),
                        condition=TableCondition(
                            op=ConditionOp.lt,
                            lhs_column=lhs_col,
                            rhs=TableColumnRHS(label=strong_down_col),
                        ),
                        action=TableAction(background_color=strong_down_colour),
                    ),
                ]
            )
            continue

        if len(resolved) == 6:
            # Six positions mean "style target_pos using a separate signal column evaluated across strong/weak bands".
            (
                target_pos,
                lhs_pos,
                strong_up_pos,
                weak_up_pos,
                weak_down_pos,
                strong_down_pos,
            ) = tp.cast(tuple[int, int, int, int, int, int], resolved)
            lhs_col = columns[lhs_pos]
            rules.extend(
                [
                    TableRule(
                        id=f"highlight_{index}_weak_up",
                        target=TableTarget(scope=TargetScope.columns, positions=[target_pos]),
                        condition=TableCondition(
                            all_of=[
                                TableCondition(
                                    op=ConditionOp.lt,
                                    lhs_column=lhs_col,
                                    rhs=TableColumnRHS(label=columns[strong_up_pos]),
                                ),
                                TableCondition(
                                    op=ConditionOp.gt,
                                    lhs_column=lhs_col,
                                    rhs=TableColumnRHS(label=columns[weak_up_pos]),
                                ),
                            ]
                        ),
                        action=TableAction(background_color=true_colour),
                    ),
                    TableRule(
                        id=f"highlight_{index}_strong_up",
                        target=TableTarget(scope=TargetScope.columns, positions=[target_pos]),
                        condition=TableCondition(
                            op=ConditionOp.gt,
                            lhs_column=lhs_col,
                            rhs=TableColumnRHS(label=columns[strong_up_pos]),
                        ),
                        action=TableAction(background_color=strong_up_colour),
                    ),
                    TableRule(
                        id=f"highlight_{index}_weak_down",
                        target=TableTarget(scope=TargetScope.columns, positions=[target_pos]),
                        condition=TableCondition(
                            all_of=[
                                TableCondition(
                                    op=ConditionOp.lt,
                                    lhs_column=lhs_col,
                                    rhs=TableColumnRHS(label=columns[weak_down_pos]),
                                ),
                                TableCondition(
                                    op=ConditionOp.gt,
                                    lhs_column=lhs_col,
                                    rhs=TableColumnRHS(label=columns[strong_down_pos]),
                                ),
                            ]
                        ),
                        action=TableAction(background_color=false_colour),
                    ),
                    TableRule(
                        id=f"highlight_{index}_strong_down",
                        target=TableTarget(scope=TargetScope.columns, positions=[target_pos]),
                        condition=TableCondition(
                            op=ConditionOp.lt,
                            lhs_column=lhs_col,
                            rhs=TableColumnRHS(label=columns[strong_down_pos]),
                        ),
                        action=TableAction(background_color=strong_down_colour),
                    ),
                ]
            )
    return rules


def color_negative_red(
    columns: tp.Sequence[str],
    negative_targets: tp.Sequence[tuple[ColumnRef, ColumnRef]],
    negative_text_color: str = "red",
) -> list[TableRule]:
    """equivalent for color_negative_red: negative values are red."""
    rules: list[TableRule] = []
    for target_ref, source_ref in negative_targets:
        resolved = _resolve_target_positions(columns, (target_ref, source_ref))
        if resolved is None:
            continue
        target_pos, source_pos = resolved
        source_col = columns[source_pos]
        rules.append(
            TableRule(
                id=f"col{target_pos}_src{source_pos}_neg_red",
                target=TableTarget(scope=TargetScope.columns, positions=[target_pos]),
                condition=TableCondition(
                    op=ConditionOp.lt,
                    lhs_column=source_col,
                    rhs=TableLiteralRHS(value=0),
                ),
                action=TableAction(text_color=negative_text_color),
            )
        )
    return rules


__all__ = [
    "band_compare_rules",
    "color_negative_red",
    "column_compare_rules",
    "highlight",
    "highlight_on_key",
    "highlight_on_range",
    "highlight_zscore",
    "membership_rules",
    "range_rules",
    "sign_rules",
]
