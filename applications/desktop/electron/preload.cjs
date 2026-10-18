const { contextBridge, ipcRenderer } = require("electron");
let shellObserver;

const TITLEBAR_HEIGHT = 40;
const NEOSIS_SWITCH_HEIGHT = 40;
const CANONICAL_BRAND_ORIGIN = "https://averqel.com";

function createWindowControl({ label, glyph, channel, className = "" }) {
  const button = document.createElement("button");
  button.type = "button";
  button.setAttribute("aria-label", label);
  button.dataset.windowControl = channel;
  button.textContent = glyph;
  button.style.cssText = [
    "display:inline-flex",
    "width:30px",
    "height:28px",
    "align-items:center",
    "justify-content:center",
    "border:1px solid rgba(148,163,184,.18)",
    "border-radius:9px",
    "background:rgba(255,255,255,.035)",
    "color:#dce7e8",
    "font:500 17px/1 system-ui,sans-serif",
    "cursor:pointer",
    "pointer-events:auto",
    "-webkit-app-region:no-drag",
    "app-region:no-drag",
    "transition:background .15s,border-color .15s,color .15s",
    className,
  ].join(";");
  button.addEventListener("mouseenter", () => {
    button.style.background =
      channel === "window:close"
        ? "rgba(239,68,68,.85)"
        : "rgba(255,255,255,.12)";
    button.style.borderColor =
      channel === "window:close"
        ? "rgba(248,113,113,.8)"
        : "rgba(148,163,184,.32)";
    if (channel === "window:close") button.style.color = "#fff";
  });
  button.addEventListener("mouseleave", () => {
    button.style.background = "rgba(255,255,255,.035)";
    button.style.borderColor = "rgba(148,163,184,.18)";
    button.style.color = "#dce7e8";
  });
  return button;
}

function createBrandAsset({ fileName, alt, width, height, className = "" }) {
  const image = document.createElement("img");
  image.src = new URL(`/brand/${fileName}`, location.href).toString();
  image.addEventListener(
    "error",
    () => {
      // NeoSIS runs on its own loopback origin and does not carry AverQel's
      // public assets. Keep the local URL for normal web/app pages, then use
      // the canonical source if that origin cannot serve the mark.
      if (image.dataset.brandFallback === "true") return;
      image.dataset.brandFallback = "true";
      image.src = new URL(`/brand/${fileName}`, CANONICAL_BRAND_ORIGIN).toString();
    },
    { once: true },
  );
  image.alt = alt;
  image.width = width;
  image.height = height;
  image.draggable = false;
  image.style.cssText = [
    `width:${width}px`,
    `height:${height}px`,
    "display:block",
    "object-fit:contain",
    "flex:none",
    "pointer-events:none",
    "-webkit-app-region:drag",
    "app-region:drag",
    className,
  ].join(";");
  return image;
}

function createTitlebar() {
  const bar = document.createElement("div");
  bar.id = "averqel-electron-titlebar";
  bar.setAttribute("role", "toolbar");
  bar.setAttribute("aria-label", "Window controls");
  bar.style.cssText = [
    "position:fixed",
    "top:0",
    "left:0",
    "right:0",
    `height:${TITLEBAR_HEIGHT}px`,
    "z-index:2147483646",
    "display:flex",
    "align-items:center",
    "justify-content:space-between",
    "box-sizing:border-box",
    "overflow:hidden",
    "padding:0 10px",
    "border-bottom:1px solid rgba(148,163,184,.12)",
    "background:#070b0d",
    "user-select:none",
    "-webkit-app-region:drag",
    "app-region:drag",
  ].join(";");

  const brand = document.createElement("div");
  brand.setAttribute("role", "img");
  brand.setAttribute("aria-label", "AverQel");
  brand.style.cssText = [
    "display:flex",
    "align-items:center",
    "gap:6px",
    "min-width:0",
    "height:100%",
    "pointer-events:none",
    "-webkit-app-region:drag",
    "app-region:drag",
  ].join(";");
  brand.append(
    createBrandAsset({
      fileName: "AverQel_Icon.svg",
      alt: "AverQel icon",
      width: 38,
      height: 24,
    }),
    createBrandAsset({
      fileName: "AverQel_Text.svg",
      alt: "AverQel",
      width: 124,
      height: 23,
      className: "averqel-electron-wordmark",
    }),
  );

  const controls = document.createElement("div");
  controls.setAttribute("role", "group");
  controls.setAttribute(
    "aria-label",
    "Minimize, maximize, and close the window",
  );
  controls.style.cssText =
    "display:flex;align-items:center;gap:6px;pointer-events:none;-webkit-app-region:no-drag;app-region:no-drag";

  const minimize = createWindowControl({
    label: "Minimize window",
    glyph: "−",
    channel: "window:minimize",
  });
  const maximize = createWindowControl({
    label: "Maximize window",
    glyph: "□",
    channel: "window:toggle-maximize",
  });
  const close = createWindowControl({
    label: "Close window",
    glyph: "×",
    channel: "window:close",
  });

  const setMaximized = (value) => {
    const maximized = value === true;
    maximize.textContent = maximized ? "▣" : "□";
    maximize.setAttribute(
      "aria-label",
      maximized ? "Restore window" : "Maximize window",
    );
  };
  const toggleMaximize = async () => {
    try {
      setMaximized(await ipcRenderer.invoke("window:toggle-maximize"));
    } catch {
      // Keep the current control label if Electron cannot update the window.
    }
  };

  minimize.addEventListener(
    "click",
    () => void ipcRenderer.invoke("window:minimize").catch(() => undefined),
  );
  maximize.addEventListener("click", () => void toggleMaximize());
  close.addEventListener(
    "click",
    () => void ipcRenderer.invoke("window:close").catch(() => undefined),
  );
  void ipcRenderer
    .invoke("window:is-maximized")
    .then(setMaximized)
    .catch(() => undefined);

  controls.append(minimize, maximize, close);
  bar.append(brand, controls);
  bar.addEventListener("dblclick", (event) => {
    if (!event.target.closest("button")) void toggleMaximize();
  });
  return bar;
}

function createNeosisReturnStrip() {
  const strip = document.createElement("div");
  strip.id = "averqel-electron-neosis-return-strip";
  strip.setAttribute("role", "group");
  strip.setAttribute("aria-label", "Workspace switch");
  strip.style.cssText = [
    `height:${NEOSIS_SWITCH_HEIGHT}px`,
    "width:100%",
    "box-sizing:border-box",
    "display:flex",
    "flex:none",
    "align-items:center",
    "justify-content:center",
    "background:rgba(7,11,13,.96)",
    "border-bottom:1px solid rgba(148,163,184,.12)",
  ].join(";");

  const button = document.createElement("button");
  button.type = "button";
  button.setAttribute("aria-label", "Return to AverQel dashboard");
  button.textContent = "←  AverQel";
  button.style.cssText = [
    "display:inline-flex",
    "align-items:center",
    "justify-content:center",
    "height:30px",
    "padding:0 14px",
    "border:1px solid rgba(45,212,191,.28)",
    "border-radius:9px",
    "background:rgba(13,148,136,.13)",
    "color:#e7eeee",
    "font:600 12px system-ui,sans-serif",
    "cursor:pointer",
    "white-space:nowrap",
  ].join(";");
  button.addEventListener("click", async () => {
    if (button.disabled) return;
    button.disabled = true;
    button.textContent = "Opening AverQel…";
    try {
      const result = await ipcRenderer.invoke("workspace:open-averqel");
      if (!result?.ok) {
        button.textContent = "Retry AverQel";
        button.setAttribute(
          "aria-label",
          result?.error || "AverQel could not be opened. Try again.",
        );
      }
    } catch (error) {
      button.textContent = "Retry AverQel";
      button.setAttribute(
        "aria-label",
        error instanceof Error
          ? error.message
          : "AverQel could not be opened. Try again.",
      );
    } finally {
      button.disabled = false;
    }
  });
  strip.append(button);
  return strip;
}

function installShellLayout(isNeosis) {
  const spacer = document.getElementById("averqel-electron-titlebar-spacer");
  const root = spacer?.nextElementSibling;
  if (!spacer || !root || root.tagName !== "DIV") return;

  let style = document.getElementById("averqel-electron-shell-style");
  if (!style) {
    style = document.createElement("style");
    style.id = "averqel-electron-shell-style";
    style.textContent = `
      body > #averqel-electron-titlebar-spacer + div {
        height: calc(100svh - ${TITLEBAR_HEIGHT}px) !important;
        min-height: calc(100svh - ${TITLEBAR_HEIGHT}px) !important;
      }
      body > #averqel-electron-titlebar-spacer + #averqel-electron-neosis-return-strip + div {
        height: calc(100svh - ${TITLEBAR_HEIGHT + NEOSIS_SWITCH_HEIGHT}px) !important;
        min-height: calc(100svh - ${TITLEBAR_HEIGHT + NEOSIS_SWITCH_HEIGHT}px) !important;
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
      .averqel-electron-wordmark {
        transform: translateY(1px);
        filter: invert(1) hue-rotate(-8deg) saturate(1);
        animation: averqel-electron-q-color-sweep 9s linear infinite;
        will-change: filter;
      }
      @keyframes averqel-electron-q-color-sweep {
        0%, 100% { filter: invert(1) hue-rotate(-8deg) saturate(1); }
        20% { filter: invert(1) hue-rotate(18deg) saturate(1.05); }
        40% { filter: invert(1) hue-rotate(38deg) saturate(1.08); }
        60% { filter: invert(1) hue-rotate(58deg) saturate(1.04); }
        80% { filter: invert(1) hue-rotate(26deg) saturate(1.06); }
      }
      @media (prefers-reduced-motion: reduce) {
        .averqel-electron-wordmark { animation: none; filter: invert(1); transform: translateY(1px); }
      }
    `;
    (document.head || document.documentElement).append(style);
  }

  document.documentElement.style.setProperty(
    "--averqel-desktop-chrome-height",
    `${TITLEBAR_HEIGHT}px`,
  );
  document.documentElement.style.setProperty(
    "--averqel-desktop-content-offset",
    `${TITLEBAR_HEIGHT + (isNeosis ? NEOSIS_SWITCH_HEIGHT : 0)}px`,
  );
}

function installShellChrome() {
  if (!document.body) return;
  if (document.title !== "AverQel") document.title = "AverQel";

  const isNeosis =
    location.hostname === "127.0.0.1" &&
    new URLSearchParams(location.search).has("token");
  const root = Array.from(document.body.children).find(
    (child) =>
      child.tagName === "DIV" &&
      child.id !== "averqel-electron-titlebar" &&
      child.id !== "averqel-electron-titlebar-spacer" &&
      child.id !== "averqel-electron-neosis-return-strip",
  );
  if (!root) return;

  let spacer = document.getElementById("averqel-electron-titlebar-spacer");
  if (!spacer) {
    spacer = document.createElement("div");
    spacer.id = "averqel-electron-titlebar-spacer";
    spacer.setAttribute("aria-hidden", "true");
    spacer.style.cssText = `display:block;flex:none;width:100%;height:${TITLEBAR_HEIGHT}px;pointer-events:none`;
  }
  if (spacer.parentElement !== document.body)
    document.body.insertBefore(spacer, root);

  let switchStrip = document.getElementById(
    "averqel-electron-neosis-return-strip",
  );
  if (isNeosis) {
    if (!switchStrip) switchStrip = createNeosisReturnStrip();
    if (spacer.nextElementSibling !== switchStrip)
      document.body.insertBefore(switchStrip, spacer.nextSibling);
    if (switchStrip.nextElementSibling !== root)
      document.body.insertBefore(root, switchStrip.nextSibling);
  } else {
    switchStrip?.remove();
    if (spacer.nextElementSibling !== root)
      document.body.insertBefore(root, spacer.nextSibling);
  }

  installShellLayout(isNeosis);
  if (!document.getElementById("averqel-electron-titlebar")) {
    document.documentElement.append(createTitlebar());
  }
}

function observeShellNavigation() {
  installShellChrome();
  if (!document.documentElement || shellObserver) return;
  shellObserver = new MutationObserver(installShellChrome);
  shellObserver.observe(document.documentElement, {
    childList: true,
    subtree: true,
  });

  for (const method of ["pushState", "replaceState"]) {
    try {
      const original = history[method];
      history[method] = (...args) => {
        const result = original.apply(history, args);
        queueMicrotask(installShellChrome);
        return result;
      };
    } catch {
      // The DOM observer and popstate listener still cover client-side navigation.
    }
  }
  window.addEventListener("popstate", installShellChrome);
}

if (document.readyState === "loading") {
  window.addEventListener("DOMContentLoaded", observeShellNavigation, {
    once: true,
  });
} else {
  observeShellNavigation();
}

contextBridge.exposeInMainWorld("electron", {
  isElectron: true,
  window: {
    minimize: () => ipcRenderer.invoke("window:minimize"),
    close: () => ipcRenderer.invoke("window:close"),
    toggleMaximize: () => ipcRenderer.invoke("window:toggle-maximize"),
    isMaximized: () => ipcRenderer.invoke("window:is-maximized"),
    hide: () => ipcRenderer.invoke("window:hide"),
  },
  openExternal: (url) => ipcRenderer.invoke("open-external", url),
  workspace: {
    neosisAvailable: () => ipcRenderer.invoke("workspace:neosis-available"),
    openNeosis: () => ipcRenderer.invoke("workspace:open-neosis"),
    openAverQel: () => ipcRenderer.invoke("workspace:open-averqel"),
  },
  codex: {
    status: () => ipcRenderer.invoke("codex:status"),
    connect: (accountId, source) =>
      ipcRenderer.invoke("codex:connect", accountId, source),
    models: (accountId) => ipcRenderer.invoke("codex:models", accountId),
    disconnect: (accountId) =>
      ipcRenderer.invoke("codex:disconnect", accountId),
    startStream: (input) => ipcRenderer.invoke("codex:stream-start", input),
    cancelStream: (streamId) =>
      ipcRenderer.invoke("codex:stream-cancel", streamId),
    onStreamEvent: (callback) => {
      if (typeof callback !== "function") return () => undefined;
      const listener = (_event, payload) => callback(payload);
      ipcRenderer.on("codex:stream-event", listener);
      return () => ipcRenderer.removeListener("codex:stream-event", listener);
    },
  },
  localRuntime: {
    status: () => ipcRenderer.invoke("local-runtime:status"),
    startStream: (input) => ipcRenderer.invoke("local-runtime:stream-start", input),
    cancelStream: (streamId) => ipcRenderer.invoke("local-runtime:stream-cancel", streamId),
    onStreamEvent: (callback) => {
      if (typeof callback !== "function") return () => undefined;
      const listener = (_event, payload) => callback(payload);
      ipcRenderer.on("local-runtime:stream-event", listener);
      return () => ipcRenderer.removeListener("local-runtime:stream-event", listener);
    },
  },
});
