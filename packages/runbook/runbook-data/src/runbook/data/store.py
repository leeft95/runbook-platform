"""Compatibility exports for the core blob-store primitive."""

from runbook.core.storage import DEFAULT_STORE_URI, BlobStore, open_blob_store

__all__ = ["BlobStore", "DEFAULT_STORE_URI", "open_blob_store"]
