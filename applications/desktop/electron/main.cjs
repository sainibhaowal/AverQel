const {
  app,
  BrowserWindow,
  Menu,
  ipcMain,
  safeStorage,
  shell,
} = require("electron");
const path = require("node:path");
const { registerAppLifecycle } = require("./app-lifecycle.cjs");
const {
  createOAuthWindow,
  interceptOAuthStartNavigation,
  parseOAuthStartUrl,
} = require("./oauth-window.cjs");
const { CodexDesktopRuntime } = require("./codex-runtime.cjs");
const { registerCodexIpcHandlers } = require("./codex-ipc.cjs");
const { LocalRuntime } = require("./local-runtime.cjs");
const { registerLocalRuntimeIpcHandlers } = require("./local-runtime-ipc.cjs");

let mainWindow;
let oauthWindow;
let codexRuntime;
let localRuntime;

const trustedHosts = new Set([
  "averqel.com",
  "localhost",
  "127.0.0.1",
  "accounts.google.com",
  "github.com",
]);

function isTrustedUrl(rawUrl) {
  try {
    const url = new URL(rawUrl);
    return (url.protocol === "https:" || url.protocol === "http:") && trustedHosts.has(url.hostname);
  } catch {
    return rawUrl.startsWith("file:");
  }
}

function appStartUrl() {
  if (!app.isPackaged) {
    return process.env.ELECTRON_START_URL || "https://localhost";
  }
  return process.env.ELECTRON_PRODUCTION_URL || "https://averqel.com";
}

function isAverQelRenderer(rawUrl) {
  try {
    return new URL(rawUrl).origin === new URL(appStartUrl()).origin;
  } catch {
    return false;
  }
}

function isAverQelSender(event) {
  return event.sender === mainWindow?.webContents
    && isAverQelRenderer(event.senderFrame?.url ?? "");
}

function allowedOAuthStartOrigins() {
  return [appStartUrl(), process.env.NEXT_PUBLIC_API_URL].filter(Boolean);
}

function openOAuthWindow(startUrl, provider) {
  if (oauthWindow && !oauthWindow.isDestroyed()) {
    oauthWindow.focus();
    return true;
  }

  oauthWindow = createOAuthWindow({
    BrowserWindow,
    parentWindow: mainWindow,
    startUrl,
    allowedOrigins: allowedOAuthStartOrigins(),
    callbackOrigin: appStartUrl(),
    onComplete: (callbackUrl) => {
      oauthWindow = null;
      if (!mainWindow || mainWindow.isDestroyed()) return;
      void mainWindow.loadURL(callbackUrl).catch(() => undefined);
    },
    onCancel: (cancelledProvider) => {
      oauthWindow = null;
      if (!mainWindow || mainWindow.isDestroyed()) return;
      const loginUrl = new URL("/auth/login", appStartUrl());
      loginUrl.searchParams.set("oauth", "error");
      loginUrl.searchParams.set("provider", cancelledProvider || provider);
      loginUrl.searchParams.set("reason", "cancelled");
      void mainWindow.loadURL(loginUrl.toString()).catch(() => undefined);
    },
  });

  return Boolean(oauthWindow);
}

function handleOAuthStartNavigation(event, rawUrl) {
  return interceptOAuthStartNavigation(
    event,
    rawUrl,
    allowedOAuthStartOrigins(),
    (startUrl, provider) => {
      if (openOAuthWindow(startUrl, provider)) return;
      const loginUrl = new URL("/auth/login", appStartUrl());
      loginUrl.searchParams.set("oauth", "error");
      loginUrl.searchParams.set("provider", provider);
      loginUrl.searchParams.set("reason", "provider");
      void mainWindow?.loadURL(loginUrl.toString()).catch(() => undefined);
    },
  );
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 960,
    minHeight: 640,
    frame: false,
    title: "AverQel",
    icon: path.join(__dirname, "../assets/icon.png"),
    backgroundColor: "#070b0d",
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      spellcheck: true,
    },
  });

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    const oauthStart = parseOAuthStartUrl(url, allowedOAuthStartOrigins());
    if (oauthStart) {
      void openOAuthWindow(oauthStart.url.toString(), oauthStart.provider);
      return { action: "deny" };
    }
    if (!isTrustedUrl(url)) {
      void shell.openExternal(url);
    }
    return { action: "deny" };
  });

  // Keep the native Electron title branded even if Next.js metadata from a
  // previously cached development render tries to replace it.
  mainWindow.webContents.on("page-title-updated", (event) => {
    event.preventDefault();
    mainWindow?.setTitle("AverQel");
  });

  mainWindow.webContents.on("will-navigate", (event, url) => {
    if (handleOAuthStartNavigation(event, url)) return;
    if (!isTrustedUrl(url)) {
      event.preventDefault();
      void shell.openExternal(url);
    }
  });

  mainWindow.on("closed", () => {
    mainWindow = null;
  });

  void mainWindow.loadURL(appStartUrl());
}

function showWindow() {
  if (!mainWindow) {
    if (!app.isReady()) return;
    createWindow();
    return;
  }
  if (mainWindow.isMinimized()) mainWindow.restore();
  mainWindow.show();
  mainWindow.focus();
}

const hasSingleInstanceLock = registerAppLifecycle({ app, showWindow });

ipcMain.handle("window:minimize", () => mainWindow?.minimize());
ipcMain.handle("window:close", () => mainWindow?.close());
ipcMain.handle("window:toggle-maximize", () => {
  if (!mainWindow) return false;
  if (mainWindow.isMaximized()) mainWindow.unmaximize();
  else mainWindow.maximize();
  return mainWindow.isMaximized();
});
ipcMain.handle("window:is-maximized", () => Boolean(mainWindow?.isMaximized()));
ipcMain.handle("open-external", (_event, rawUrl) => {
  if (typeof rawUrl !== "string") return false;
  try {
    const url = new URL(rawUrl);
    if (url.protocol !== "https:" && url.protocol !== "http:") return false;
    void shell.openExternal(url.toString());
    return true;
  } catch {
    return false;
  }
});
registerCodexIpcHandlers({
  ipcMain,
  getRuntime: () => codexRuntime,
  isAverQelSender,
});
registerLocalRuntimeIpcHandlers({
  ipcMain,
  getRuntime: () => localRuntime,
  isAverQelSender,
});

app.whenReady().then(() => {
  if (!hasSingleInstanceLock) return;
  // AverQel uses its own in-app controls; do not show Electron's default menu.
  Menu.setApplicationMenu(null);
  codexRuntime = new CodexDesktopRuntime({
    app,
    safeStorage,
    shell,
    emit: (streamId, frame) => {
      if (!mainWindow?.isDestroyed()) {
        mainWindow.webContents.send("codex:stream-event", { streamId, ...frame });
      }
    },
  });
  localRuntime = new LocalRuntime({
    emit: (streamId, frame) => {
      if (!mainWindow?.isDestroyed()) {
        mainWindow.webContents.send("local-runtime:stream-event", { streamId, ...frame });
      }
    },
  });
  createWindow();
  app.on("activate", showWindow);
});

app.on("before-quit", () => {
  codexRuntime?.cancelAllStreams?.();
  localRuntime?.cancelAllStreams?.();
});
