"""Sphinx configuration for the Runbook documentation site."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for package in ("runbook-core", "runbook-data", "runbook-sdk", "runbook-services", "runbook-worker"):
    sys.path.insert(0, str(ROOT / "packages" / "runbook" / package / "src"))

project = "Runbook"
copyright = "2026, redcombojnr and contributors"
author = "redcombojnr and contributors"
release = "0.2.0"

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
html_baseurl = "https://redcombojnr.github.io/runbook-platform/"
html_theme_options = {
    "source_repository": "https://github.com/redcombojnr/runbook-platform",
    "source_branch": "main",
    "source_directory": "docs/",
}
