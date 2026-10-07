const { contextBridge, ipcRenderer } = require("electron");
let workspaceObserver;
let activeWorkspace;
let titlebarTitle;
let titlebarSwitch;

const TITLEBAR_HEIGHT = 40;

function createBrandMark(isNeosis) {
  if (!isNeosis) {
    const letter = document.createElement("span");
    letter.textContent = "A";
    letter.setAttribute("aria-hidden", "true");
    letter.style.cssText = "display:inline-flex;width:16px;height:16px;align-items:center;justify-content:center;border:1px solid rgba(34,211,238,.45);border-radius:5px;color:#67d8e4;font-size:10px;font-weight:800;line-height:1";
    return letter;
  }

  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 128 96");
  svg.setAttribute("width", "19");
  svg.setAttribute("height", "15");
  svg.setAttribute("aria-hidden", "true");
  svg.style.cssText = "display:block;flex:none";

  const defs = document.createElementNS("http://www.w3.org/2000/svg", "defs");
  const gradient = document.createElementNS("http://www.w3.org/2000/svg", "linearGradient");
  gradient.id = "averqel-neosis-titlebar-gradient";
  gradient.setAttribute("x1", "0%");
  gradient.setAttribute("y1", "0%");
  gradient.setAttribute("x2", "100%");
  gradient.setAttribute("y2", "100%");
  for (const [offset, color] of [
    ["0%", "#ff1744"], ["18%", "#ff8a00"], ["36%", "#ffd600"],
    ["54%", "#31d158"], ["70%", "#00c7e8"], ["84%", "#397bff"], ["100%", "#c13cff"],
  ]) {
    const stop = document.createElementNS("http://www.w3.org/2000/svg", "stop");
    stop.setAttribute("offset", offset);
    stop.setAttribute("stop-color", color);
    gradient.append(stop);
  }
  defs.append(gradient);

  const mark = document.createElementNS("http://www.w3.org/2000/svg", "path");
  mark.setAttribute("d", "M12 27C16 15 28 8 43 10L53 2L53 15C66 15 79 21 90 31C99 39 106 48 116 51C108 58 99 60 90 57C87 69 79 78 67 84C52 91 35 88 23 79C12 71 7 59 8 46C8 38 9 32 12 27ZM31 9L22 2L24 18C19 20 15 23 12 27ZM70 35A4 4 0 1 0 70 43A4 4 0 1 0 70 35ZM20 50C29 39 42 35 56 39C47 43 41 49 38 57C35 66 39 73 46 80C34 78 25 72 20 64C17 59 17 54 20 50Z");
  mark.setAttribute("fill", "url(#averqel-neosis-titlebar-gradient)");
  mark.setAttribute("fill-rule", "evenodd");
  mark.setAttribute("clip-rule", "evenodd");

  const accent = document.createElementNS("http://www.w3.org/2000/svg", "path");
  accent.setAttribute("d", "M82 25C91 33 99 43 106 49C98 49 91 52 85 56");
  accent.setAttribute("stroke", "url(#averqel-neosis-titlebar-gradient)");
  accent.setAttribute("stroke-width", "3");
  accent.setAttribute("stroke-linecap", "round");
  accent.setAttribute("opacity", ".92");
  svg.append(defs, mark, accent);
  return svg;
}

function createWorkspaceButton() {
  const button = document.createElement("button");
  button.type = "button";
  button.style.cssText = [
    "display:inline-flex", "align-items:center", "gap:8px", "height:29px", "padding:0 10px",
    "border:1px solid rgba(45,212,191,.28)", "border-radius:8px", "background:rgba(13,148,136,.13)",
    "color:#e7eeee", "font:600 12px system-ui,sans-serif", "cursor:pointer", "white-space:nowrap",
    "-webkit-app-region:no-drag", "app-region:no-drag", "pointer-events:auto", "transition:background .15s,border-color .15s",
  ].join(";");
  button.addEventListener("mouseenter", () => {
    button.style.background = "rgba(13,148,136,.24)";
    button.style.borderColor = "rgba(45,212,191,.48)";
  });
  button.addEventListener("mouseleave", () => {
    button.style.background = "rgba(13,148,136,.13)";
    button.style.borderColor = "rgba(45,212,191,.28)";
  });

  let status;
  const renderTarget = () => {
    const target = activeWorkspace === "neosis" ? "averqel" : "neosis";
    const label = target === "neosis" ? "NeoSIS" : "AverQel";
    const badge = target === "neosis" ? "Local" : "Web";
    button.dataset.targetWorkspace = target;
    button.setAttribute("aria-label", `Switch to ${label} workspace`);
    button.title = `Switch to ${label} workspace`;
    const text = document.createElement("span");
    text.textContent = label;
    status = document.createElement("span");
    status.textContent = badge;
    status.style.cssText = "color:#9caeae;font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.08em";
    button.replaceChildren(createBrandMark(target === "neosis"), text, status);
  };
  button.renderTarget = renderTarget;
  renderTarget();
  button.addEventListener("click", async () => {
    if (button.disabled) return;
    button.disabled = true;
    button.style.cursor = "wait";
    await refreshWorkspaceState();
    const target = activeWorkspace === "neosis" ? "averqel" : "neosis";
    const label = target === "neosis" ? "NeoSIS" : "AverQel";
    const badge = target === "neosis" ? "Local" : "Web";
    renderTarget();
    status.textContent = "Starting";
    button.title = `Opening ${label} workspace…`;
    try {
      const result = await ipcRenderer.invoke(target === "neosis" ? "workspace:open-neosis" : "workspace:open-averqel");
      if (!result?.ok) {
        status.textContent = "Retry";
        button.title = result?.error || `${label} could not be opened.`;
      } else {
        status.textContent = badge;
      }
    } catch (error) {
      status.textContent = "Retry";
      button.title = error instanceof Error ? error.message : `${label} could not be opened.`;
    } finally {
      button.disabled = false;
      button.style.cursor = "pointer";
    }
  });
  return button;
}

function isNeosisPage() {
  return location.hostname === "127.0.0.1" && new URLSearchParams(location.search).has("token");
}

async function refreshWorkspaceState() {
  try {
    const workspace = await ipcRenderer.invoke("workspace:current");
    if (workspace !== "averqel" && workspace !== "neosis") return;
    activeWorkspace = workspace;
    if (titlebarTitle) titlebarTitle.textContent = workspace === "neosis" ? "NeoSIS" : "AverQel";
    titlebarSwitch?.renderTarget?.();
  } catch {
    // Keep the URL-derived state if the main process is not ready yet.
  }
}

function installTitlebarLayout() {
  const spacer = document.getElementById("averqel-electron-titlebar-spacer");
  const root = spacer?.nextElementSibling;
  if (!spacer || !root || root.tagName !== "DIV") return;

  let style = document.getElementById("averqel-electron-titlebar-style");
  if (!style) {
    style = document.createElement("style");
    style.id = "averqel-electron-titlebar-style";
    style.textContent = `
      body > #averqel-electron-titlebar-spacer + div {
        height: calc(100svh - ${TITLEBAR_HEIGHT}px) !important;
        min-height: calc(100svh - ${TITLEBAR_HEIGHT}px) !important;
      }
      .app-shell-grid {
        height: calc(100svh - ${TITLEBAR_HEIGHT}px) !important;
      }
      .app-shell-grid > .dashboard-sidebar-shell {
        height: calc(100svh - ${TITLEBAR_HEIGHT}px - 2rem) !important;
      }
      .app-shell-grid > div.relative.my-2 {
        height: calc(100svh - ${TITLEBAR_HEIGHT}px - 1rem) !important;
      }
      @media (min-width: 640px) {
        .app-shell-grid > div.relative.my-2 {
          height: calc(100svh - ${TITLEBAR_HEIGHT}px - 2rem) !important;
        }
      }
    `;
    (document.head || document.documentElement).append(style);
  }
}

function createTitlebar() {
  const existing = document.getElementById("averqel-electron-titlebar");
  if (existing) {
    titlebarTitle = existing.querySelector("[data-titlebar-app-name]");
    titlebarSwitch = existing.querySelector("button");
    void refreshWorkspaceState();
    return existing;
  }

  const bar = document.createElement("div");
  bar.id = "averqel-electron-titlebar";
  bar.setAttribute("role", "banner");
  bar.setAttribute("aria-label", "AverQel desktop title bar");
  bar.style.cssText = [
    "position:fixed", "top:0", "left:0", "right:0", `height:${TITLEBAR_HEIGHT}px`, "z-index:2147483646",
    "display:flex", "align-items:center", "box-sizing:border-box", "overflow:hidden",
    "border-top:2px solid #54cbd5", "border-bottom:1px solid rgba(148,163,140,.16)",
    "background:#34332f", "color:#f4f5f2", "font:500 12px system-ui,-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif",
    "-webkit-app-region:drag", "app-region:drag", "user-select:none",
  ].join(";");

  const title = document.createElement("div");
  activeWorkspace ??= isNeosisPage() ? "neosis" : "averqel";
  title.textContent = activeWorkspace === "neosis" ? "NeoSIS" : "AverQel";
  title.dataset.titlebarAppName = "true";
  title.setAttribute("aria-hidden", "true");
  title.style.cssText = "position:absolute;left:50%;top:0;height:100%;transform:translateX(-50%);display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:650;letter-spacing:.01em;white-space:nowrap;pointer-events:none;-webkit-app-region:drag";

  const controls = document.createElement("div");
  const isMac = process.platform === "darwin";
  controls.style.cssText = isMac
    ? "position:absolute;left:80px;right:0;top:0;height:100%;display:flex;align-items:center;padding-left:10px;pointer-events:none"
    : "position:absolute;left:env(titlebar-area-x, 0px);width:env(titlebar-area-width, 100%);top:0;height:100%;display:flex;align-items:center;padding-left:10px;pointer-events:none";

  titlebarSwitch = createWorkspaceButton();
  controls.append(titlebarSwitch);
  titlebarTitle = title;
  bar.append(title, controls);
  void refreshWorkspaceState();
  bar.addEventListener("dblclick", (event) => {
    if (!event.target.closest("button")) void ipcRenderer.invoke("window:toggle-maximize");
  });

  return bar;
}

function installWorkspaceControls() {
  if (!document.body) return;
  if (document.title !== "AverQel") document.title = "AverQel";

  // Remove the older sidebar switch if an already-deployed frontend still has it.
  document.querySelector('[aria-label="Desktop workspaces"]')?.remove();
  document.getElementById("averqel-neosis-switch")?.remove();
  document.getElementById("averqel-return-switch")?.remove();

  let root = Array.from(document.body.children).find((child) =>
    child.tagName === "DIV" && child.id !== "averqel-electron-titlebar" && child.id !== "averqel-electron-titlebar-spacer"
  );
  if (!root) return;

  let spacer = document.getElementById("averqel-electron-titlebar-spacer");
  if (!spacer) {
    spacer = document.createElement("div");
    spacer.id = "averqel-electron-titlebar-spacer";
    spacer.setAttribute("aria-hidden", "true");
    spacer.style.cssText = `display:block;flex:none;width:100%;height:${TITLEBAR_HEIGHT}px;pointer-events:none`;
    document.body.insertBefore(spacer, root);
  } else if (spacer.nextElementSibling !== root) {
    document.body.insertBefore(spacer, root);
  }

  installTitlebarLayout();
  if (!document.getElementById("averqel-electron-titlebar")) {
    document.documentElement.append(createTitlebar());
  }
}

function observeWorkspaceNavigation() {
  installWorkspaceControls();
  if (!document.documentElement || workspaceObserver) return;
  workspaceObserver = new MutationObserver(installWorkspaceControls);
  workspaceObserver.observe(document.documentElement, { childList: true, subtree: true });

  for (const method of ["pushState", "replaceState"]) {
    try {
      const original = history[method];
      history[method] = (...args) => {
        const result = original.apply(history, args);
        queueMicrotask(installWorkspaceControls);
        return result;
      };
    } catch {
      // The DOM observer and popstate listener still cover page navigation.
    }
  }
  window.addEventListener("popstate", installWorkspaceControls);
}

if (document.readyState === "loading") {
  window.addEventListener("DOMContentLoaded", observeWorkspaceNavigation, { once: true });
} else {
  observeWorkspaceNavigation();
}

contextBridge.exposeInMainWorld("electron", {
  isElectron: true,
  window: {
    minimize: () => ipcRenderer.invoke("window:minimize"),
    toggleMaximize: () => ipcRenderer.invoke("window:toggle-maximize"),
    isMaximized: () => ipcRenderer.invoke("window:is-maximized"),
    hide: () => ipcRenderer.invoke("window:hide"),
  },
  openExternal: (url) => ipcRenderer.invoke("open-external", url),
  workspace: {
    openNeosis: () => ipcRenderer.invoke("workspace:open-neosis"),
    openAverQel: () => ipcRenderer.invoke("workspace:open-averqel"),
  },
});
