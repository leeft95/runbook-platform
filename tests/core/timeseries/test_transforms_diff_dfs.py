from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from runbook.core.timeseries.transforms import diff_dfs


def test_diff_dfs_returns_new_and_updated_rows_from_updated_payload() -> None:
    existing = pd.DataFrame(
        {
            "id": [1, 2],
            "value": [10.0, 20.0],
            "note": [np.nan, "same"],
        }
    )
    updated = pd.DataFrame(
        {
            "id": [1, 2, 3],
            "value": [10.0, 21.0, 30.0],
            "note": [np.nan, "same", "new"],
            "updated_only": ["x", "y", "z"],
        }
    )

    out = diff_dfs(existing, updated, on=["id"]).sort_values(by=["id"]).reset_index(drop=True)

    assert out["id"].tolist() == [2, 3]
    assert out["value"].tolist() == [21.0, 30.0]
    assert out["note"].tolist() == ["same", "new"]
    assert out["update_type"].tolist() == ["updated", "new"]
    assert "updated_only" not in out.columns


def test_diff_dfs_treats_nan_equal_and_only_flags_real_changes() -> None:
    existing = pd.DataFrame({"id": [1, 2], "value": [np.nan, 5.0]})
    updated = pd.DataFrame({"id": [1, 2], "value": [np.nan, np.nan]})

    out = diff_dfs(existing, updated, on=["id"])

    assert out["id"].tolist() == [2]
    assert out["update_type"].tolist() == ["updated"]
    assert np.isnan(out.loc[0, "value"])


def test_diff_dfs_rejects_non_unique_keys() -> None:
    existing = pd.DataFrame({"id": [1, 1], "value": [10.0, 11.0]})
    updated = pd.DataFrame({"id": [1], "value": [12.0]})

    with pytest.raises(ValueError, match="must uniquely identify rows"):
        diff_dfs(existing, updated, on=["id"])
