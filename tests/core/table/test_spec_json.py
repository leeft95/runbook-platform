from __future__ import annotations

import json
from pathlib import Path

from runbook.core.table.models import TableArtifactRef, TableStylePlan


def test_table_spec_json_matches_model_schema() -> None:
    spec_path = Path("packages/runbook/runbook-core/src/runbook/core/table/spec.json")
    committed_schema = json.loads(spec_path.read_text(encoding="utf-8"))
    assert committed_schema["$defs"]["table_style_plan"] == TableStylePlan.model_json_schema()
    assert committed_schema["$defs"]["table_artifact_ref"] == TableArtifactRef.model_json_schema()
