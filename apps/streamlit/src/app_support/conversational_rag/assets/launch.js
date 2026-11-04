// CCv2 launcher for a build's read-only showcase. Renders an icon-only button that
// opens the signed showcase URL (data.url, resolved against the app's base URL) in a
// new browser tab on click; with data.auto_open it also opens on each fresh request
// (a false->true transition, e.g. right after a Build & launch / Launch click, while
// the browser's transient activation is still valid). The click handler runs inside
// the user gesture, so the tab opens without tripping the popup blocker.
// CCv2 runs in the page context (no iframe), so window/document here are the top
// document.
const ICON = `
<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" focusable="false">
  <path d="M9.19 6.35c-2.04 2.29-3.44 5.58-3.57 5.89L2 10.69l4.05-4.05c.47-.47 1.15-.68 1.81-.55l1.33.26zM11.17 17s3.74-1.55 5.89-3.7c5.4-5.4 4.5-9.62 4.21-10.57-.95-.3-5.17-1.19-10.57 4.21C8.55 9.09 7 12.83 7 12.83L11.17 17zm6.48-2.19c-2.29 2.04-5.58 3.44-5.89 3.57L13.31 22l4.05-4.05c.47-.47.68-1.15.55-1.81l-.26-1.33zM9 18c0 .83-.34 1.58-.88 2.12C6.94 21.3 2 22 2 22s.7-4.94 1.88-6.12C4.42 15.34 5.17 15 6 15c1.66 0 3 1.34 3 3zm4-9c0-1.1.9-2 2-2s2 .9 2 2-.9 2-2 2-2-.9-2-2z"></path>
</svg>`;

const instances = new WeakMap();

export default function (component) {
  const { data, parentElement } = component;

  let instance = instances.get(parentElement);
  if (!instance) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "sc-launch-btn";
    button.innerHTML = ICON;
    instance = { button, data, lastAutoOpen: false };
    instances.set(parentElement, instance);
    button.addEventListener("click", () => openTab(instance.data.url));
    parentElement.appendChild(button);
  }

  instance.data = data;
  const label = data.label || "Launch";
  instance.button.title = data.help || label;
  instance.button.setAttribute("aria-label", label);
  // Open on a fresh auto_open request (false -> true transition), not only once: a
  // relaunch re-raises auto_open after it was reset, and re-firing opens the tab again
  // within the click's still-valid transient activation. The explicit click is the
  // reliable fallback when a popup blocker stops the programmatic open.
  const wantsOpen = Boolean(data.auto_open);
  if (wantsOpen && !instance.lastAutoOpen) {
    openTab(data.url);
  }
  instance.lastAutoOpen = wantsOpen;

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
