"""Render the synthetic COT fixture using Runbook's shared table models."""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

import pandas as pd
from runbook.core.table import TableStylePlan, cot_table, render_table_html


def main() -> None:
    """Write a standalone preview and its reusable JSON style plan."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path(tempfile.gettempdir()) / "runbook-cot-preview")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    summary = pd.read_csv(root / "data/fixtures/cot/summary.csv")
    payload = cot_table(
        summary,
        header="Speculators Net Position (Managed money)",
        label_column="24-Jun to 01-Jul",
        position_column="Net Position (MM)",
        group_column="Group",
    )["Speculators Net Position (Managed money)"]
    plan = TableStylePlan.model_validate(payload["style"])
    table = render_table_html(payload["data"], plan)
    document = (
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>COT table preview</title><body style="font-family:Calibri,Arial,sans-serif;margin:24px">'
        "<h2>Speculators Net Position (Managed money)</h2>"
        "<p>Synthetic fixture · 24 June–1 July 2025</p>"
        f'<div style="overflow-x:auto">{table}</div>'
        "</body></html>"
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "index.html").write_text(document, encoding="utf-8")
    (args.output_dir / "style.json").write_text(plan.model_dump_json(indent=2, exclude_none=True), encoding="utf-8")
    print(args.output_dir / "index.html")


if __name__ == "__main__":
    main()
