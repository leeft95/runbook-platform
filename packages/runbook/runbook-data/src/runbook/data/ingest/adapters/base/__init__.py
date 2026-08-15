"""Reusable acquisition capabilities shared by source adapters."""

from runbook.data.ingest.adapters.base.contracts import SourceAdapter
from runbook.data.ingest.adapters.base.http import HttpAdapter
from runbook.data.ingest.adapters.base.local_file import LocalFileAdapter

__all__ = ["HttpAdapter", "LocalFileAdapter", "SourceAdapter"]
