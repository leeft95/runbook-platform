"""Portable image sources shared by report authoring and manifest validation."""

import base64
import binascii
from urllib.parse import urlsplit

from runbook.core.table.models import validate_link_url


def image_mime_type(data: bytes) -> str:
    """Identify a supported raster image from its signature."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        mime = "image/png"
    elif data.startswith(b"\xff\xd8\xff"):
        mime = "image/jpeg"
    elif data.startswith((b"GIF87a", b"GIF89a")):
        mime = "image/gif"
    elif data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        mime = "image/webp"
    else:
        raise ValueError("Embedded images must be PNG, JPEG, GIF, or WebP")
    return mime


def image_data_uri(data: bytes) -> str:
    """Embed a raster image, identifying its format from its signature."""
    return f"data:{image_mime_type(data)};base64,{base64.b64encode(data).decode('ascii')}"


def validate_image_ref(value: str) -> str:
    """Require a traversal-free BlobStore key in an images directory."""
    if not isinstance(value, str):
        raise ValueError("Image ref must be a string BlobStore key")
    parts = value.split("/")
    if (
        any(part in {"", ".", ".."} for part in parts)
        or "images" not in parts[:-1]
        or any(char.isspace() or ord(char) < 32 or char in "\\:?#" for char in value)
    ):
        raise ValueError("Image ref must be a relative BlobStore key under images/, without traversal or a URL scheme")
    return value


def validate_image_src(value: str) -> str:
    """Allow absolute web URLs and base64 raster images in persisted reports."""
    if value.startswith("data:"):
        header, separator, encoded = value.partition(",")
        if not separator or header not in {
            "data:image/png;base64",
            "data:image/jpeg;base64",
            "data:image/gif;base64",
            "data:image/webp;base64",
        }:
            raise ValueError("Image data URLs must contain base64 PNG, JPEG, GIF, or WebP")
        try:
            canonical = image_data_uri(base64.b64decode(encoded, validate=True))
        except (ValueError, binascii.Error) as exc:
            raise ValueError("Invalid embedded image data") from exc
        if canonical.partition(",")[0] != header:
            raise ValueError("Image MIME type does not match its data")
        return canonical
    validate_link_url(value)
    parsed = urlsplit(value)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Image src must be an absolute HTTP(S) URL or embedded raster image")
    return parsed.geturl()
