"""Localized labels for the standalone 3D site-graph viewer (new-tab page).

These strings render inside the browser tab the viewer opens — a self-contained
HTML page, not a Streamlit component — so they live beside the feature rather
than in the Streamlit i18n catalog. English and Indonesian are kept key-for-key
in sync (parity-tested) to mirror the app's bilingual UI. The launcher injects
the selected language's mapping into the viewer, and the viewer reads keys
defensively, so a missing key degrades to a readable fallback rather than
breaking the scene.
"""

from __future__ import annotations

__all__ = ["VIEWER_LABELS_EN", "VIEWER_LABELS_ID", "viewer_labels"]

VIEWER_LABELS_EN: dict[str, str] = {
    "title": "Site Orrery",
    "controls_title": "Controls",
    "ctrl_rotate": "Rotate",
    "ctrl_rotate_hint": "Left-drag",
    "ctrl_pan": "Pan",
    "ctrl_pan_hint": "Right-drag",
    "ctrl_zoom": "Zoom",
    "ctrl_zoom_hint": "Scroll",
    "ctrl_move": "Move",
    "ctrl_move_hint": "W A S D / Arrows",
    "ctrl_reset": "Reset view",
    "ctrl_reset_hint": "R",
    "ctrl_focus": "Inspect a page",
    "ctrl_focus_hint": "Click a planet",
    "help_show": "Controls",
    "help_hide": "Hide",
    "panel_seed": "Seed page (root)",
    "panel_discovered_from": "Discovered from",
    "panel_size": "Page size",
    "panel_status": "Status",
    "panel_depth": "Depth",
    "panel_round": "Final round",
    "panel_links": "Links discovered",
    "panel_open_page": "Open page in new tab",
    "panel_preview_loading": "Loading live preview\u2026",
    "panel_preview_blocked": (
        "This site blocks embedding, so the live preview can't load here. "
        "Use \u201cOpen page in new tab\u201d above."
    ),
    "panel_close": "Close",
    "status_success": "Success",
    "status_fail": "Failed",
    "status_skipped": "Skipped",
    "status_discovered": "Discovered",
    "hud_pages": "Pages",
    "hud_depth": "Max depth",
    "legend_title": "Legend",
}

VIEWER_LABELS_ID: dict[str, str] = {
    "title": "Site Orrery",
    "controls_title": "Kontrol",
    "ctrl_rotate": "Putar",
    "ctrl_rotate_hint": "Seret kiri",
    "ctrl_pan": "Geser",
    "ctrl_pan_hint": "Seret kanan",
    "ctrl_zoom": "Zoom",
    "ctrl_zoom_hint": "Gulir",
    "ctrl_move": "Pindah",
    "ctrl_move_hint": "W A S D / Panah",
    "ctrl_reset": "Atur ulang tampilan",
    "ctrl_reset_hint": "R",
    "ctrl_focus": "Periksa halaman",
    "ctrl_focus_hint": "Klik planet",
    "help_show": "Kontrol",
    "help_hide": "Sembunyikan",
    "panel_seed": "Halaman awal (root)",
    "panel_discovered_from": "Ditemukan dari",
    "panel_size": "Ukuran halaman",
    "panel_status": "Status",
    "panel_depth": "Kedalaman",
    "panel_round": "Ronde akhir",
    "panel_links": "Tautan ditemukan",
    "panel_open_page": "Buka halaman di tab baru",
    "panel_preview_loading": "Memuat pratinjau langsung\u2026",
    "panel_preview_blocked": (
        "Situs ini memblokir penyematan, jadi pratinjau langsung tidak dapat dimuat di sini. "
        "Gunakan \u201cBuka halaman di tab baru\u201d di atas."
    ),
    "panel_close": "Tutup",
    "status_success": "Berhasil",
    "status_fail": "Gagal",
    "status_skipped": "Dilewati",
    "status_discovered": "Ditemukan",
    "hud_pages": "Halaman",
    "hud_depth": "Kedalaman maks",
    "legend_title": "Keterangan",
}

_CATALOG: dict[str, dict[str, str]] = {"en": VIEWER_LABELS_EN, "id": VIEWER_LABELS_ID}


def viewer_labels(language: str) -> dict[str, str]:
    """Return the viewer label mapping for *language*, defaulting to English."""
    return _CATALOG.get((language or "").strip().lower(), VIEWER_LABELS_EN)
