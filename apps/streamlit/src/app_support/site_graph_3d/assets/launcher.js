// Streamlit CCv2 launcher for the 3D site-graph viewer. Renders a button that
// matches Streamlit's secondary buttons; on click it turns the pre-assembled
// standalone viewer HTML (data.html) into a Blob and opens it in a new tab. The
// click handler runs synchronously inside the user gesture, so the tab opens
// without tripping the popup blocker. CCv2 runs in the page context (no iframe),
// so window/document access here is the top document.
const ICON = `
<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" focusable="false">
  <circle cx="14.5" cy="9" r="5"></circle>
  <circle cx="6.5" cy="15.5" r="3.4"></circle>
  <circle cx="16.5" cy="17.5" r="2.4"></circle>
</svg>`;

const instances = new WeakMap();

export default function (component) {
  const { data, parentElement } = component;

  let instance = instances.get(parentElement);
  if (!instance) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "sg-launch-btn";
    button.innerHTML = `${ICON}<span class="sg-launch-label"></span>`;
    instance = { button, data };
    instances.set(parentElement, instance);
    button.addEventListener("click", () => {
      if (instance.data.disabled) return;
      openViewer(instance.data.html);
    });
    parentElement.appendChild(button);
  }

  instance.data = data;
  instance.button.querySelector(".sg-launch-label").textContent =
    data.label || "Explore in 3D";
  instance.button.title = data.help || "";
  instance.button.disabled = Boolean(data.disabled);
  instance.button.setAttribute("aria-disabled", String(Boolean(data.disabled)));

  return () => {
    parentElement.innerHTML = "";
    instances.delete(parentElement);
  };
}

function openViewer(html) {
  if (!html) return;
  const blob = new Blob([html], { type: "text/html" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.target = "_blank";
  anchor.rel = "noopener noreferrer";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  // Give the new tab time to read the blob before releasing it.
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}
