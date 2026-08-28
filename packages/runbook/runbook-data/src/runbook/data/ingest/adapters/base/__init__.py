"""Reusable acquisition capabilities shared by source adapters."""

from runbook.data.ingest.adapters.base.contracts import HistoricalSourceAdapter, SourceAdapter
from runbook.data.ingest.adapters.base.http import HttpAdapter
from runbook.data.ingest.adapters.base.local_file import LocalFileAdapter

__all__ = ["HistoricalSourceAdapter", "HttpAdapter", "LocalFileAdapter", "SourceAdapter"]
