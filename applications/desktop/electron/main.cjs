const {
  app,
  BrowserWindow,
  Menu,
  Tray,
  ipcMain,
  nativeImage,
  shell,
} = require("electron");
const path = require("node:path");

let mainWindow;
let tray;
let isQuitting = false;

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

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 960,
    minHeight: 640,
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
    if (!isTrustedUrl(url)) {
      event.preventDefault();
      void shell.openExternal(url);
    }
  });

  mainWindow.on("close", (event) => {
    if (!isQuitting) {
      event.preventDefault();
      mainWindow.hide();
    }
  });

  mainWindow.on("closed", () => {
    mainWindow = null;
  });

  void mainWindow.loadURL(appStartUrl());
}

function showWindow() {
  if (!mainWindow) {
    createWindow();
    return;
  }
  mainWindow.show();
  mainWindow.focus();
}

function createTray() {
  const iconPath = path.join(__dirname, "../assets/icon.png");
  tray = new Tray(nativeImage.createFromPath(iconPath));
  tray.setToolTip("AverQel");
  tray.setContextMenu(
    Menu.buildFromTemplate([
      { label: "Show AverQel", click: showWindow },
      { type: "separator" },
      {
        label: "Quit",
        click: () => {
          isQuitting = true;
          app.quit();
        },
      },
    ]),
  );
  tray.on("click", showWindow);
}

ipcMain.handle("window:minimize", () => mainWindow?.minimize());
ipcMain.handle("window:toggle-maximize", () => {
  if (!mainWindow) return false;
  if (mainWindow.isMaximized()) mainWindow.unmaximize();
  else mainWindow.maximize();
  return mainWindow.isMaximized();
});
ipcMain.handle("window:is-maximized", () => Boolean(mainWindow?.isMaximized()));
ipcMain.handle("window:hide", () => mainWindow?.hide());
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

app.whenReady().then(() => {
  // AverQel uses its own in-app controls and tray menu; do not show Electron's
  // default File/Edit/View/Window menu bar in the desktop window.
  Menu.setApplicationMenu(null);
  createWindow();
  createTray();
  app.on("activate", showWindow);
});

app.on("before-quit", () => {
  isQuitting = true;
});

app.on("window-all-closed", () => {
  // Keep the app available from the tray on every desktop platform.
});
