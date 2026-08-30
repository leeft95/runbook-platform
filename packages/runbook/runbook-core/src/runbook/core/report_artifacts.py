from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

import pandas as pd
from runbook.core.table import (
    StyleInput,
    TableArtifactRef,
    TableLink,
    render_table_html,
    table_style_hash,
    table_style_payload,
)

_ARTIFACT_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def validate_artifact_name(name: str) -> str:
    """Validate artifact name."""
    candidate = str(name).strip()
    if not candidate or not _ARTIFACT_NAME_RE.fullmatch(candidate):
        raise ValueError(f"Artifact name must contain only letters, numbers, '.', '_', or '-': {name!r}")
    return candidate


@dataclass(frozen=True)
class RuntimeArtifactPayloads:
    plot_jsons: dict[str, Any] = field(default_factory=dict)
    table_styles: dict[str, Any] = field(default_factory=dict)
    table_htmls: dict[str, str] = field(default_factory=dict)


class ArtifactRegistry:
    def __init__(
        self,
        *,
        table_ref_resolver: Callable[[str], str],
        table_writer: Callable[[str, pd.DataFrame], None],
    ):
        self._table_ref_resolver = table_ref_resolver
        self._table_writer = table_writer
        self._plot_jsons: dict[str, Any] = {}
        self._table_styles: dict[str, Any] = {}
        self._table_htmls: dict[str, str] = {}

    def plot(self, figure: object, *, name: str, fmt: str = "plotly_json") -> str:
        """Handle plot."""
        artifact_name = validate_artifact_name(name)
        if fmt != "plotly_json":
            raise ValueError(f"Unsupported plot artifact fmt: {fmt!r}")

        to_plotly_json = getattr(figure, "to_plotly_json", None)
        if callable(to_plotly_json):
            payload = to_plotly_json()
        elif isinstance(figure, Mapping):
            payload = dict(figure)
        else:
            raise TypeError("ctx.artifact.plot expects a Plotly figure or mapping payload")

        ref = f"plots/{artifact_name}.json"
        existing = self._plot_jsons.get(ref)
        if existing is not None and existing != payload:
            raise ValueError(f"Duplicate plot artifact name with different payload: {name}")
        self._plot_jsons[ref] = payload
        return ref

    def table(
        self,
        df: pd.DataFrame,
        *,
        name: str,
        style: StyleInput | None = None,
        style_df: pd.DataFrame | None = None,
        style_key: str | None = None,
        max_rows: int | None = None,
    ) -> TableArtifactRef:
        """Handle table."""
        if not isinstance(df, pd.DataFrame):
            raise TypeError(f"ctx.artifact.table expects a pandas.DataFrame, got {type(df)!r}")

        artifact_name = validate_artifact_name(name)
        self._table_writer(artifact_name, df)
        data_ref = self._table_ref_resolver(artifact_name)

        should_materialize_style = any(value is not None for value in (style, style_df, style_key, max_rows))
        if not should_materialize_style:
            return TableArtifactRef(data_ref=data_ref)

        payload = table_style_payload(style, style_key=style_key, max_rows=max_rows)
        style_hash = table_style_hash(style, style_key=style_key, max_rows=max_rows)
        style_ref = f"styles/{artifact_name}.{style_hash}.json"
        html_ref = f"tables/{artifact_name}.{style_hash}.html"
        html = render_table_html(
            df,
            style,
            style_df=style_df,
            style_key=style_key,
            max_rows=max_rows,
        )

        existing_style = self._table_styles.get(style_ref)
        if existing_style is not None and existing_style != payload:
            raise ValueError(f"Duplicate table style artifact name with different payload: {name}")
        existing_html = self._table_htmls.get(html_ref)
        if existing_html is not None and existing_html != html:
            raise ValueError(f"Duplicate table html artifact name with different payload: {name}")

        self._table_styles[style_ref] = payload
        self._table_htmls[html_ref] = html

        resolved_style_key = payload.get("style_key")
        if not isinstance(resolved_style_key, str) or not resolved_style_key:
            resolved_style_key = None

        return TableArtifactRef(
            data_ref=data_ref,
            style_ref=style_ref,
            html_ref=html_ref,
            style_key=resolved_style_key,
            links=[TableLink.model_validate(link) for link in payload.get("links", [])] or None,
        )

    def payloads(self) -> RuntimeArtifactPayloads:
        """Handle payloads."""
        return RuntimeArtifactPayloads(
            plot_jsons=dict(self._plot_jsons),
            table_styles=dict(self._table_styles),
            table_htmls=dict(self._table_htmls),
        )
