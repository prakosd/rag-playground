// CCv2 launcher for a build's read-only showcase. Renders a button that opens the
// signed showcase URL (data.url, resolved against the app's base URL) in a new
// browser tab on click; with data.auto_open it also attempts to open once on mount
// (best-effort — a popup blocker may require the explicit click). The click handler
// runs inside the user gesture, so the tab opens without tripping the popup blocker.
// CCv2 runs in the page context (no iframe), so window/document here are the top
// document.
const ICON = `
<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" focusable="false">
  <path d="M14 3v2h3.59l-9.3 9.29 1.42 1.42L19 6.41V10h2V3h-7z"></path>
  <path d="M19 19H5V5h7V3H5a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7h-2v7z"></path>
</svg>`;

const instances = new WeakMap();

export default function (component) {
  const { data, parentElement } = component;

  let instance = instances.get(parentElement);
  if (!instance) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "sc-launch-btn";
    button.innerHTML = `${ICON}<span class="sc-launch-label"></span>`;
    instance = { button, data, opened: false };
    instances.set(parentElement, instance);
    button.addEventListener("click", () => openTab(instance.data.url));
    parentElement.appendChild(button);
  }

  instance.data = data;
  instance.button.querySelector(".sc-launch-label").textContent = data.label || "Launch";
  instance.button.title = data.help || "";
  // Best-effort auto-open once (right after a Build & launch click, the browser's
  // transient activation is usually still valid). The explicit click is the reliable
  // fallback when a popup blocker stops it.
  if (data.auto_open && !instance.opened) {
    instance.opened = true;
    openTab(data.url);
  }

  return () => {
    parentElement.innerHTML = "";
    instances.delete(parentElement);
  };
}

function openTab(path) {
  if (!path) return;
  const anchor = document.createElement("a");
  // Resolve against the app root (base dir), not the launching page: Streamlit
  // sets no <base>, so document.baseURI is /<page>; opening /<page>?show=… makes
  // Streamlit's router 404 the unknown path before the showcase (root page) loads.
  const appRoot = new URL(".", document.baseURI).href;
  anchor.href = new URL(path, appRoot).href;
  anchor.target = "_blank";
  anchor.rel = "noopener noreferrer";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
}
