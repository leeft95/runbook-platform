"""Sphinx configuration for the Runbook documentation site."""

from __future__ import annotations

import sys
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for package in ("runbook-core", "runbook-data", "runbook-sdk", "runbook-services", "runbook-worker"):
    sys.path.insert(0, str(ROOT / "packages" / "runbook" / package / "src"))

project = "Runbook"
copyright = "2026, leeft95 and contributors"
author = "leeft95 and contributors"
try:
    release = metadata.version("runbook-services")
except metadata.PackageNotFoundError:
    release = "development"

extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.githubpages",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

source_suffix = {".rst": "restructuredtext", ".md": "markdown"}
myst_heading_anchors = 3
autodoc_default_options = {
    "members": True,
    "member-order": "bysource",
    "show-inheritance": True,
}
autodoc_typehints = "description"
autodoc_preserve_defaults = True

html_theme = "furo"
html_title = "Runbook documentation"
html_baseurl = "https://leeft95.github.io/runbook-platform/"
html_static_path = ["_static"]
html_theme_options = {
    "source_repository": "https://github.com/leeft95/runbook-platform",
    "source_branch": "main",
    "source_directory": "docs/",
}
