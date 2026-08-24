from __future__ import annotations

from io import BytesIO

import pandas as pd
from runbook.data.config import SourceConfig
from runbook.data.ingest.models import AcquisitionResult, CuratedFrame


def parse_external(
    *,
    source_config: SourceConfig,
    dataset_alias: str,
    acquired: AcquisitionResult,
) -> list[CuratedFrame]:
    frame = pd.read_csv(BytesIO(acquired.payload))
    timestamps = pd.to_datetime(frame["timestamp"], utc=True)
    frame["timestamp"] = timestamps
    return [
        CuratedFrame(
            output_alias=dataset_alias,
            frame=frame,
            watermark=timestamps.max().to_pydatetime(),
            partition={"bucket": "all"},
            merge_keys=("timestamp",),
        )
    ]
