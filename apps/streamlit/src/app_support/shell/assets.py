"""Static presentation assets extracted from ``streamlit_app.py``.

Inert markup/data (icon data URIs, the portfolio-modal HTML/CSS/JS, and the
language-selector CSS) plus the theme-aware GitHub-icon selector. No app logic or
session state — the shell's render functions import these.
"""

from __future__ import annotations

import streamlit as st

_LINKEDIN_ICON_DATA_URI = (
    "data:image/svg+xml;base64,"
    "PHN2ZyB4bWxucz0naHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmcnIHZpZXdCb3g9JzAgMCA1MTIg"
    "NTEyJz48cmVjdCB3aWR0aD0nNTEyJyBoZWlnaHQ9JzUxMicgcng9JzcyJyBmaWxsPScjMEE3"
    "RUI3Jy8+PGNpcmNsZSBjeD0nMTQyJyBjeT0nMTQyJyByPSc0NCcgZmlsbD0nd2hpdGUnLz48"
    "cmVjdCB4PScxMDgnIHk9JzIwMicgd2lkdGg9JzY4JyBoZWlnaHQ9JzIxNCcgcng9JzEyJyBm"
    "aWxsPSd3aGl0ZScvPjxwYXRoIGZpbGw9J3doaXRlJyBkPSdNMjA1IDIwMmg2N3YzMWMxNS0y"
    "MyA0MC0zNSA3Mi0zNSA0OCAwIDgwIDMyIDgwIDEwMXYxMTdoLTY5VjMwN2MwLTM1LTEzLTUy"
    "LTQwLTUyLTI4IDAtNDIgMjAtNDIgNTh2MTAzaC02OHonLz48L3N2Zz4="
)
_GITHUB_ICON_DATA_URI = (
    "data:image/svg+xml;base64,"
    "PHN2ZyB4bWxucz0naHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmcnIHZpZXdCb3g9JzAgMCA5OCA5"
    "Nic+PHBhdGggZmlsbD0nYmxhY2snIGZpbGwtcnVsZT0nZXZlbm9kZCcgZD0nTTQ4LjkgMEMyMS45"
    "IDAgMCAyMiAwIDQ5LjFjMCAyMS43IDE0IDQwLjEgMzMuNSA0Ni42IDIuNS41IDMuMy0xLjEgMy4z"
    "LTIuNCAwLTEuMi0uMS01LjItLjEtOS40LTEzLjYgMy0xNi41LTUuOS0xNi41LTUuOS0yLjIt"
    "NS43LTUuNC03LjItNS40LTcuMi00LjQtMyAuMy0zIC4zLTMgNC45LjMgNy41IDUuMSA3LjUgNS4x"
    "IDQuMyA3LjUgMTEuNCA1LjMgMTQuMiA0LjEuNC0zLjIgMS43LTUuMyAzLjEtNi41LTEwLjktMS4y"
    "LTIyLjMtNS41LTIyLjMtMjQuNCAwLTUuNCAxLjktOS44IDUtMTMuMi0uNS0xLjItMi4yLTYuMy41"
    "LTEzIDAgMCA0LjEtMS4zIDEzLjQgNSAzLjktMS4xIDgtMS42IDEyLjItMS42czguMy42IDEyLjIg"
    "MS42YzkuMy02LjMgMTMuNC01IDEzLjQtNSAyLjcgNi43IDEgMTEuOC41IDEzIDMuMSAzLjQgNSA3"
    "LjggNSAxMy4yIDAgMTguOS0xMS41IDIzLjEtMjIuNCAyNC40IDEuOCAxLjYgMy4zIDQuNiAzLjMg"
    "OS4zIDAgNi43LS4xIDEyLjEtLjEgMTMuOCAwIDEuMy45IDIuOSAzLjQgMi40Qzg0IDg5LjEgOTgg"
    "NzAuNyA5OCA0OS4xIDk4IDIyIDc2IDAgNDguOSAweicgY2xpcC1ydWxlPSdldmVub2RkJy8+"
    "PC9zdmc+"
)
# White-fill variant for dark themes, where the black mark is nearly invisible.
_GITHUB_ICON_DARK_DATA_URI = (
    "data:image/svg+xml;base64,"
    "PHN2ZyB4bWxucz0naHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmcnIHZpZXdCb3g9JzAgMCA5OCA5"
    "Nic+PHBhdGggZmlsbD0nd2hpdGUnIGZpbGwtcnVsZT0nZXZlbm9kZCcgZD0nTTQ4LjkgMEMyMS45"
    "IDAgMCAyMiAwIDQ5LjFjMCAyMS43IDE0IDQwLjEgMzMuNSA0Ni42IDIuNS41IDMuMy0xLjEgMy4z"
    "LTIuNCAwLTEuMi0uMS01LjItLjEtOS40LTEzLjYgMy0xNi41LTUuOS0xNi41LTUuOS0yLjIt"
    "NS43LTUuNC03LjItNS40LTcuMi00LjQtMyAuMy0zIC4zLTMgNC45LjMgNy41IDUuMSA3LjUgNS4x"
    "IDQuMyA3LjUgMTEuNCA1LjMgMTQuMiA0LjEuNC0zLjIgMS43LTUuMyAzLjEtNi41LTEwLjktMS4y"
    "LTIyLjMtNS41LTIyLjMtMjQuNCAwLTUuNCAxLjktOS44IDUtMTMuMi0uNS0xLjItMi4yLTYuMy41"
    "LTEzIDAgMCA0LjEtMS4zIDEzLjQgNSAzLjktMS4xIDgtMS42IDEyLjItMS42czguMy42IDEyLjIg"
    "MS42YzkuMy02LjMgMTMuNC01IDEzLjQtNSAyLjcgNi43IDEgMTEuOC41IDEzIDMuMSAzLjQgNSA3"
    "LjggNSAxMy4yIDAgMTguOS0xMS41IDIzLjEtMjIuNCAyNC40IDEuOCAxLjYgMy4zIDQuNiAzLjMg"
    "OS4zIDAgNi43LS4xIDEyLjEtLjEgMTMuOCAwIDEuMy45IDIuOSAzLjQgMi40Qzg0IDg5LjEgOTgg"
    "NzAuNyA5OCA0OS4xIDk4IDIyIDc2IDAgNDguOSAweicgY2xpcC1ydWxlPSdldmVub2RkJy8+"
    "PC9zdmc+"
)


def _github_icon_data_uri() -> str:
    """Return the GitHub mark matching the active theme (white on dark, black on light)."""
    try:
        is_dark = st.context.theme.type == "dark"
    except Exception:  # noqa: BLE001 - theme is best-effort; default to the light-mode mark
        is_dark = False
    return _GITHUB_ICON_DARK_DATA_URI if is_dark else _GITHUB_ICON_DATA_URI


_AUTHOR_PHOTO_URL = "https://media.licdn.com/dms/image/v2/D5603AQEraqyhOd5bOg/profile-displayphoto-shrink_200_200/profile-displayphoto-shrink_200_200/0/1731589103775?e=2147483647&v=beta&t=RTXvNnlM_jS1bPSRiBSC1hBfeIAAwhYVxXKv3ON9MUs"


_PORTFOLIO_MODAL_HTML = """
<div id="crawl4md-portfolio-modal-root"></div>
"""

_PORTFOLIO_MODAL_CSS = """
:host {
    font-family: var(--st-font, "Source Sans Pro", sans-serif);
}

#crawl4md-portfolio-modal-root {
    display: contents;
}

.portfolio-modal-overlay {
    position: fixed;
    inset: 0;
    z-index: 10000;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 24px;
    background: rgba(17, 24, 39, 0.48);
    backdrop-filter: blur(2px);
}

.portfolio-modal-overlay[hidden] {
    display: none;
}

.portfolio-modal-panel {
    position: relative;
    width: min(560px, calc(100vw - 32px));
    max-height: min(82vh, 720px);
    overflow: auto;
    box-sizing: border-box;
    padding: 24px;
    color: var(--st-text-color, #111827);
    background: var(--st-background-color, #ffffff);
    border: 1px solid var(--st-border-color, rgba(49, 51, 63, 0.2));
    border-radius: var(--st-base-radius, 8px);
    box-shadow: 0 20px 60px rgba(15, 23, 42, 0.28);
}

.portfolio-modal-close {
    position: absolute;
    top: 10px;
    right: 10px;
    width: 36px;
    height: 36px;
    border: 1px solid var(--st-border-color, rgba(49, 51, 63, 0.2));
    border-radius: var(--st-button-radius, 8px);
    color: var(--st-text-color, #111827);
    background: var(--st-secondary-background-color, #f3f4f6);
    cursor: pointer;
    font-size: 18px;
    line-height: 1;
}

.portfolio-modal-header {
    display: flex;
    gap: 16px;
    align-items: center;
    padding-right: 34px;
}

.portfolio-modal-avatar {
    width: 84px;
    height: 84px;
    flex: 0 0 auto;
    object-fit: cover;
    border-radius: 50%;
    border: 1px solid var(--st-border-color, rgba(49, 51, 63, 0.2));
}

.portfolio-modal-title {
    margin: 0;
    color: var(--st-heading-color, var(--st-text-color, #111827));
    font: 700 1.35rem/1.25 var(--st-heading-font, var(--st-font, sans-serif));
}

.portfolio-modal-kicker {
    margin: 6px 0 0;
    color: var(--st-text-color, #111827);
    opacity: 0.72;
    font-size: 0.95rem;
}

.portfolio-modal-copy {
    margin: 18px 0 0;
    font-size: 0.98rem;
    line-height: 1.6;
}

.portfolio-modal-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 10px 18px;
    margin-top: 20px;
}

.portfolio-modal-link {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    color: var(--st-link-color, var(--st-primary-color, #ff4b4b));
    text-decoration: none;
    font-weight: 600;
}

.portfolio-modal-link:hover {
    text-decoration: underline;
}

.portfolio-modal-doc-link {
    color: var(--st-link-color, var(--st-primary-color, #ff4b4b));
    text-decoration: none;
    font-weight: 600;
}

.portfolio-modal-doc-link:hover {
    text-decoration: underline;
}

.portfolio-modal-icon-image {
    width: 22px;
    height: 22px;
    flex: 0 0 auto;
    object-fit: contain;
}

@media (max-width: 520px) {
    .portfolio-modal-panel {
        padding: 20px;
    }

    .portfolio-modal-header {
        align-items: flex-start;
    }

    .portfolio-modal-avatar {
        width: 64px;
        height: 64px;
    }
}
"""

_PORTFOLIO_MODAL_JS = """
const MODAL_VISIBLE_CLASS = "is-visible"

function readPayload(storageKey) {
    try {
        const rawValue = window.localStorage.getItem(storageKey)
        if (!rawValue) return { version: 1, sessions: [] }
        const parsed = JSON.parse(rawValue)
        if (Array.isArray(parsed)) return { version: 1, sessions: parsed }
        if (parsed && typeof parsed === "object") return parsed
    } catch {
        return { version: 1, sessions: [] }
    }
    return { version: 1, sessions: [] }
}

function utcNow() {
    return new Date().toISOString().replace(".000Z", "Z")
}

function writeTimestamp(storageKey, field, value) {
    if (!storageKey || !field) return
    try {
        const payload = readPayload(storageKey)
        payload.version = 1
        payload[field] = value
        window.localStorage.setItem(storageKey, JSON.stringify(payload))
    } catch {
        return
    }
}

function appendText(parent, tagName, className, text) {
    const element = document.createElement(tagName)
    element.className = className
    element.textContent = text || ""
    parent.appendChild(element)
    return element
}

function appendLink(parent, href, label, iconUrl, iconClass) {
    const link = document.createElement("a")
    link.className = iconClass ? `portfolio-modal-link ${iconClass}` : "portfolio-modal-link"
    link.href = href || "#"
    link.target = "_blank"
    link.rel = "noopener noreferrer"
    const icon = document.createElement("img")
    icon.className = iconClass
        ? `portfolio-modal-icon-image ${iconClass}`
        : "portfolio-modal-icon-image"
    icon.setAttribute("aria-hidden", "true")
    icon.alt = ""
    icon.src = iconUrl || ""
    link.appendChild(icon)
    link.appendChild(document.createTextNode(label || ""))
    parent.appendChild(link)
}

function updateIconSrc(overlay, iconClass, iconUrl) {
    if (typeof iconUrl !== "string" || !iconUrl) return
    const icon = overlay.querySelector(`.portfolio-modal-icon-image.${iconClass}`)
    if (icon && icon.getAttribute("src") !== iconUrl) icon.src = iconUrl
}

const instances = new WeakMap()

export default function (component) {
    const { data, parentElement } = component
    const root = parentElement.querySelector("#crawl4md-portfolio-modal-root")
    if (!root) return

    let instance = instances.get(parentElement)
    if (!instance) {
        instance = { timer: null, open: false, overlay: null, onKeyDown: null }
        instances.set(parentElement, instance)
    }

    if (data.shouldShow !== true) {
        if (instance.timer) window.clearTimeout(instance.timer)
        if (instance.onKeyDown) document.removeEventListener("keydown", instance.onKeyDown)
        root.innerHTML = ""
        instance.timer = null
        instance.open = false
        instance.overlay = null
        instance.onKeyDown = null
        return
    }

    if (instance.overlay) {
        if (!root.contains(instance.overlay)) root.appendChild(instance.overlay)
        // Theme toggles re-run this component with new icon URLs; refresh the
        // existing overlay so the mark recolors on every toggle, not just once.
        updateIconSrc(instance.overlay, "github", data.githubIconUrl)
        updateIconSrc(instance.overlay, "linkedin", data.linkedinIconUrl)
        return
    }

    root.innerHTML = ""

    const overlay = document.createElement("div")
    overlay.className = "portfolio-modal-overlay"
    overlay.hidden = true

    const panel = document.createElement("section")
    panel.className = "portfolio-modal-panel"
    panel.setAttribute("role", "dialog")
    panel.setAttribute("aria-modal", "true")
    panel.setAttribute("aria-labelledby", "portfolio-modal-title")

    const closeButton = document.createElement("button")
    closeButton.className = "portfolio-modal-close"
    closeButton.type = "button"
    closeButton.setAttribute("aria-label", data.closeLabel || "Close")
    closeButton.textContent = "x"
    panel.appendChild(closeButton)

    const header = document.createElement("div")
    header.className = "portfolio-modal-header"
    const image = document.createElement("img")
    image.className = "portfolio-modal-avatar"
    image.src = data.photoUrl || ""
    image.alt = data.photoAlt || ""
    header.appendChild(image)
    const headerText = document.createElement("div")
    const title = appendText(headerText, "h2", "portfolio-modal-title", data.title)
    title.id = "portfolio-modal-title"
    appendText(headerText, "p", "portfolio-modal-kicker", data.tagline)
    header.appendChild(headerText)
    panel.appendChild(header)

    appendText(panel, "p", "portfolio-modal-copy", data.body)
    appendText(panel, "p", "portfolio-modal-copy", data.cta)

    const docLinks = document.createElement("p")
    docLinks.className = "portfolio-modal-copy"
    const readmeLink = document.createElement("a")
    readmeLink.className = "portfolio-modal-doc-link"
    readmeLink.href = data.readmeUrl || "#"
    readmeLink.target = "_blank"
    readmeLink.rel = "noopener noreferrer"
    readmeLink.textContent = data.readmeLabel || ""
    const sep = document.createTextNode(" \u00b7 ")
    const stReadmeLink = document.createElement("a")
    stReadmeLink.className = "portfolio-modal-doc-link"
    stReadmeLink.href = data.streamlitReadmeUrl || "#"
    stReadmeLink.target = "_blank"
    stReadmeLink.rel = "noopener noreferrer"
    stReadmeLink.textContent = data.streamlitReadmeLabel || ""
    docLinks.appendChild(readmeLink)
    docLinks.appendChild(sep)
    docLinks.appendChild(stReadmeLink)
    panel.appendChild(docLinks)

    const actions = document.createElement("div")
    actions.className = "portfolio-modal-actions"
    appendLink(actions, data.linkedinUrl, data.linkedinLabel, data.linkedinIconUrl, "linkedin")
    appendLink(actions, data.githubUrl, data.githubLabel, data.githubIconUrl, "github")
    panel.appendChild(actions)
    overlay.appendChild(panel)
    root.appendChild(overlay)

    function dismiss() {
        if (!instance.open) return
        writeTimestamp(data.storageKey, data.lastDismissedField, utcNow())
        overlay.classList.remove(MODAL_VISIBLE_CLASS)
        overlay.hidden = true
        instance.open = false
        document.removeEventListener("keydown", onKeyDown)
    }

    function onKeyDown(event) {
        if (event.key === "Escape") dismiss()
    }

    instance.overlay = overlay
    instance.onKeyDown = onKeyDown

    overlay.addEventListener("click", event => {
        if (event.target === overlay) dismiss()
    })
    closeButton.addEventListener("click", dismiss)

    const delayMs = Math.max(0, Number(data.delaySeconds || 0)) * 1000
    instance.timer = window.setTimeout(() => {
        instance.timer = null
        overlay.hidden = false
        overlay.classList.add(MODAL_VISIBLE_CLASS)
        instance.open = true
        writeTimestamp(data.storageKey, data.lastShownField, utcNow())
        document.addEventListener("keydown", onKeyDown)
        closeButton.focus()
    }, delayMs)

    return () => {
        if (instance.timer) window.clearTimeout(instance.timer)
        document.removeEventListener("keydown", onKeyDown)
        root.innerHTML = ""
        instances.delete(parentElement)
    }
}
"""


# The language selector's label sits small, dim, and right-docked just above the EN/ID
# control (scoped to the keyed wrapper so only this widget's label is restyled).
_LANGUAGE_SELECTOR_WRAP_KEY = "language_selector_wrap"
_LANGUAGE_SELECTOR_CSS = f"""
<style>
.st-key-{_LANGUAGE_SELECTOR_WRAP_KEY} [data-testid="stWidgetLabel"] {{
    justify-content: flex-end;
    margin-bottom: -0.3rem;
}}
.st-key-{_LANGUAGE_SELECTOR_WRAP_KEY} [data-testid="stWidgetLabel"] p {{
    font-size: 0.8rem;
    opacity: 0.6;
}}
</style>
"""
