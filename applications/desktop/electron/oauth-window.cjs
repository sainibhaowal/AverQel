const OAUTH_START_PATH = /(?:^|\/)auth\/oauth\/(google|github)\/start$/;

function normalizeOrigins(origins) {
  return new Set(
    [...(origins || [])].flatMap((value) => {
      try {
        return [new URL(value).origin];
      } catch {
        return [];
      }
    }),
  );
}

function parseOAuthStartUrl(rawUrl, allowedOrigins) {
  if (typeof rawUrl !== "string") return null;

  let url;
  try {
    url = new URL(rawUrl);
  } catch {
    return null;
  }

  const origins = normalizeOrigins(allowedOrigins);
  const providerMatch = url.pathname.match(OAUTH_START_PATH);
  const returnTo = url.searchParams.get("return_to");
  const localHttp =
    url.protocol === "http:" &&
    ["localhost", "127.0.0.1", "[::1]"].includes(url.hostname);

  if (
    !origins.has(url.origin) ||
    (url.protocol !== "https:" && !localHttp) ||
    !providerMatch ||
    (returnTo !== null && returnTo !== "/auth/login")
  ) {
    return null;
  }

  return { provider: providerMatch[1], url };
}

function parseOAuthCallbackUrl(rawUrl, provider, callbackOrigin) {
  if (typeof rawUrl !== "string") return null;

  let url;
  try {
    url = new URL(rawUrl);
    callbackOrigin = new URL(callbackOrigin).origin;
  } catch {
    return null;
  }

  if (
    url.origin !== callbackOrigin ||
    url.pathname !== "/auth/login" ||
    url.searchParams.get("provider") !== provider ||
    !["success", "2fa", "error"].includes(url.searchParams.get("oauth"))
  ) {
    return null;
  }

  return url;
}

function interceptOAuthStartNavigation(event, rawUrl, allowedOrigins, onStart) {
  const start = parseOAuthStartUrl(rawUrl, allowedOrigins);
  if (!start) return false;

  event.preventDefault();
  onStart(start.url.toString(), start.provider);
  return true;
}

function createOAuthWindow({
  BrowserWindow,
  parentWindow,
  startUrl,
  allowedOrigins,
  callbackOrigin,
  onComplete,
  onCancel,
}) {
  const start = parseOAuthStartUrl(startUrl, allowedOrigins);
  if (!start || !parentWindow || parentWindow.isDestroyed()) return null;

  const authWindow = new BrowserWindow({
    parent: parentWindow,
    modal: true,
    width: 520,
    height: 720,
    minWidth: 460,
    minHeight: 600,
    useContentSize: true,
    show: true,
    title: "Sign in to AverQel",
    backgroundColor: "#ffffff",
    autoHideMenuBar: true,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  let finished = false;
  const handleNavigation = (event, rawUrl) => {
    const callback = parseOAuthCallbackUrl(rawUrl, start.provider, callbackOrigin);
    if (!callback) return;

    event.preventDefault();
    if (finished) return;
    finished = true;
    onComplete(callback.toString());
    authWindow.close();
  };

  authWindow.webContents.on("will-redirect", handleNavigation);
  authWindow.webContents.on("will-navigate", handleNavigation);
  authWindow.on("closed", () => {
    if (finished) return;
    finished = true;
    onCancel(start.provider);
  });

  try {
    Promise.resolve(authWindow.loadURL(start.url.toString())).catch(() => {
      if (!finished && !authWindow.isDestroyed()) authWindow.close();
    });
  } catch {
    if (!authWindow.isDestroyed()) authWindow.close();
  }

  return authWindow;
}

module.exports = {
  createOAuthWindow,
  interceptOAuthStartNavigation,
  parseOAuthCallbackUrl,
  parseOAuthStartUrl,
};
