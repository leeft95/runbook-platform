"""Generic CSV time-series parser for source-blind Stage 2 curation."""

from __future__ import annotations

from io import BytesIO

import pandas as pd
from runbook.data.config import SourceConfig
from runbook.data.ingest.models import AcquisitionResult, CuratedFrame


def parse_csv_timeseries(
    *,
    source_config: SourceConfig,
    dataset_alias: str,
    acquired: AcquisitionResult,
) -> list[CuratedFrame]:
    """Parse one CSV payload into a deterministic appendable time series."""
    timestamp_column = source_config.params.get("timestamp_column")
    if not isinstance(timestamp_column, str) or not timestamp_column:
        raise ValueError("csv_timeseries_v1 requires params.timestamp_column")
    try:
        frame = pd.read_csv(BytesIO(acquired.payload))
    except Exception as exc:
        raise ValueError("csv_timeseries_v1 payload is not valid CSV") from exc
    if frame.empty:
        raise ValueError("csv_timeseries_v1 payload contains no rows")
    if timestamp_column not in frame.columns:
        raise ValueError(f"timestamp column is missing: {timestamp_column!r}")
    timestamps = pd.to_datetime(frame[timestamp_column], utc=True, errors="coerce")
    if timestamps.isna().any():
        raise ValueError(f"timestamp column contains invalid values: {timestamp_column!r}")
    frame = frame.copy()
    frame[timestamp_column] = timestamps
    frame = (
        frame.sort_values(timestamp_column, kind="mergesort")
        .drop_duplicates(timestamp_column, keep="last")
        .reset_index(drop=True)
    )
    watermark = frame[timestamp_column].max().to_pydatetime()
    return [
        CuratedFrame(
            output_alias=dataset_alias,
            frame=frame,
            watermark=watermark,
            partition={},
            merge_keys=(timestamp_column,),
        )
    ]


__all__ = ["parse_csv_timeseries"]
