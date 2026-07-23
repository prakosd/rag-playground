"""3D site-graph "universe" viewer support for the crawl4md Streamlit app.

This package turns a crawl's ``site_graph.jsonl`` into an interactive Three.js
solar-system view opened in a new browser tab. Responsibilities split cleanly:

- :mod:`app_support.site_graph_3d.graph_data` is pure Python (no Streamlit): it
  shapes the raw crawl records into a JSON-ready node/edge model with derived
  visual attributes (size, richness, colour category). It is fully unit-tested.
- :mod:`app_support.site_graph_3d.launcher` is the thin Streamlit adapter that
  assembles the standalone viewer HTML from the frontend assets and mounts the
  inline component button that opens it in a new tab.

The ``crawl4md`` library stays untouched — it already emits ``site_graph.jsonl``;
everything here is app/UI only.
"""

from __future__ import annotations

from app_support.site_graph_3d.graph_data import build_site_graph_model
from app_support.site_graph_3d.viewer_assembler import build_viewer_html
from app_support.site_graph_3d.viewer_labels import viewer_labels

__all__ = ["build_site_graph_model", "build_viewer_html", "viewer_labels"]
