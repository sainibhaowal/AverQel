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
const { existsSync } = require("node:fs");
const { spawn } = require("node:child_process");

let mainWindow;
let tray;
let isQuitting = false;
let neosisProcess;
let neosisStart;
let neosisUrl;
let neosisOrigin;

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

function neosisHome() {
  return path.join(app.getPath("userData"), "neosis");
}

function isAverQelRenderer(rawUrl) {
  try {
    return new URL(rawUrl).origin === new URL(appStartUrl()).origin;
  } catch {
    return false;
  }
}

function isNeosisRenderer(rawUrl) {
  try {
    return neosisOrigin !== undefined && new URL(rawUrl).origin === neosisOrigin;
  } catch {
    return false;
  }
}

function isWorkspaceSender(event) {
  return event.sender === mainWindow?.webContents
    && (isAverQelRenderer(event.senderFrame?.url ?? "") || isNeosisRenderer(event.senderFrame?.url ?? ""));
}

function launchPackagedNeosis() {
  const runtimeRoot = path.join(process.resourcesPath, "neosis");
  const entry = path.join(runtimeRoot, "node_modules", "@averqel", "neosis", "lib", "bin.js");
  const profilePatch = path.join(runtimeRoot, "averqel-local-profile.patch.yml");
  if (!existsSync(entry)) {
    throw new Error("NeoSIS runtime is missing from this AverQel installation.");
  }
  if (!existsSync(profilePatch)) {
    throw new Error("NeoSIS local profile configuration is missing from this AverQel installation.");
  }
  return spawn(process.execPath, [entry, "web", "--patch", profilePatch, "--host", "127.0.0.1", "--port", "0", "--no-open"], {
    cwd: runtimeRoot,
    env: { ...process.env, ELECTRON_RUN_AS_NODE: "1", NEOSIS_HOME: neosisHome() },
    stdio: ["ignore", "pipe", "pipe", "ipc"],
  });
}

function launchDevelopmentNeosis() {
  const root = path.resolve(__dirname, "../../../neosis");
  const profilePatch = path.resolve(__dirname, "../assets/neosis-local-profile.patch.yml");
  const command = process.platform === "win32" ? "pnpm.cmd" : "pnpm";
  return spawn(command, ["neosis", "web", "--patch", profilePatch, "--host", "127.0.0.1", "--port", "0", "--no-open"], {
    cwd: root,
    env: { ...process.env, NEOSIS_HOME: neosisHome() },
    stdio: ["ignore", "pipe", "pipe", "ipc"],
  });
}

function startNeosis() {
  if (neosisUrl !== undefined) return Promise.resolve(neosisUrl);
  if (neosisStart !== undefined) return neosisStart;
  neosisStart = new Promise((resolve, reject) => {
    let settled = false;
    let timeout;
    const finish = (error, url) => {
      if (settled) return;
      settled = true;
      if (timeout !== undefined) clearTimeout(timeout);
      if (error) {
        neosisStart = undefined;
        reject(error);
        return;
      }
      try {
        const parsed = new URL(url);
        if (parsed.protocol !== "http:" || parsed.hostname !== "127.0.0.1" || !parsed.searchParams.has("token")) {
          throw new Error("NeoSIS returned an unsafe local launch URL.");
        }
        neosisUrl = parsed.toString();
        neosisOrigin = parsed.origin;
        resolve(neosisUrl);
      } catch (validationError) {
        neosisStart = undefined;
        reject(validationError);
      }
    };
    const child = app.isPackaged ? launchPackagedNeosis() : launchDevelopmentNeosis();
    neosisProcess = child;
    let output = "";
    const readOutput = (chunk) => {
      output = (output + String(chunk)).slice(-16384);
      const match = /neosis web: (http:\/\/127\.0\.0\.1:\d+\/\?token=[A-Za-z0-9_-]+)/.exec(output);
      if (match) finish(undefined, match[1]);
    };
    child.stdout?.on("data", readOutput);
    child.stderr?.on("data", readOutput);
    child.on("message", (message) => {
      if (message && message.type === "ready" && typeof message.url === "string") finish(undefined, message.url);
      if (message && message.type === "fatal") finish(new Error(message.message || "NeoSIS failed to start."));
    });
    child.once("error", finish);
    child.once("exit", (code, signal) => {
      if (!settled) finish(new Error(`NeoSIS stopped before it was ready (${code ?? signal ?? "unknown"}).`));
      neosisProcess = undefined;
      neosisUrl = undefined;
      neosisOrigin = undefined;
      neosisStart = undefined;
    });
    timeout = setTimeout(() => finish(new Error("NeoSIS did not become ready within 60 seconds.")), 60000);
  });
  return neosisStart;
}

async function openNeosis() {
  const url = await startNeosis();
  await mainWindow?.loadURL(url);
}

async function openAverQel() {
  await mainWindow?.loadURL(appStartUrl());
}

function stopNeosis() {
  const child = neosisProcess;
  neosisProcess = undefined;
  neosisStart = undefined;
  neosisUrl = undefined;
  neosisOrigin = undefined;
  if (child && child.exitCode === null) child.kill("SIGTERM");
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 960,
    minHeight: 640,
    title: "AverQel",
    titleBarStyle: "hidden",
    ...(process.platform === "darwin"
      ? {}
      : {
          titleBarOverlay: {
            color: "#34332f",
            symbolColor: "#63d6df",
            height: 40,
          },
        }),
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
      { label: "Open AverQel Workspace", click: () => void openAverQel() },
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
ipcMain.handle("workspace:current", (event) => {
  if (!isWorkspaceSender(event)) return null;
  return isNeosisRenderer(event.senderFrame?.url ?? "") ? "neosis" : "averqel";
});
ipcMain.handle("workspace:open-neosis", async (event) => {
  if (!isWorkspaceSender(event)) return { ok: false, error: "Unauthorized workspace request." };
  try {
    await openNeosis();
    return { ok: true };
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : "NeoSIS could not be started." };
  }
});
ipcMain.handle("workspace:open-averqel", async (event) => {
  if (!isWorkspaceSender(event)) return { ok: false, error: "Unauthorized workspace request." };
  try {
    await openAverQel();
    return { ok: true };
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : "AverQel could not be opened." };
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
  stopNeosis();
});

app.on("window-all-closed", () => {
  // Keep the app available from the tray on every desktop platform.
});
