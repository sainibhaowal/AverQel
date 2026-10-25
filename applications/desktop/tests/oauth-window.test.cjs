const assert = require("node:assert/strict");
const { EventEmitter } = require("node:events");
const test = require("node:test");

const {
  createOAuthWindow,
  interceptOAuthStartNavigation,
  parseOAuthCallbackUrl,
  parseOAuthStartUrl,
} = require("../electron/oauth-window.cjs");

const allowedOrigins = ["https://averqel.com/api/v1"];
const googleStartUrl =
  "https://averqel.com/api/v1/auth/oauth/google/start?return_to=%2Fauth%2Flogin";

class FakeAuthWindow extends EventEmitter {
  constructor(options) {
    super();
    this.options = options;
    this.loadedUrls = [];
    this.destroyed = false;
    this.webContents = new EventEmitter();
  }

  loadURL(url) {
    this.loadedUrls.push(url);
    return Promise.resolve();
  }

  focus() {}

  close() {
    if (this.destroyed) return;
    this.destroyed = true;
    this.emit("closed");
  }

  isDestroyed() {
    return this.destroyed;
  }
}

test("accepts only trusted Google and GitHub login start URLs", () => {
  assert.equal(parseOAuthStartUrl(googleStartUrl, allowedOrigins).provider, "google");
  assert.equal(
    parseOAuthStartUrl(
      "https://averqel.com/api/v1/auth/oauth/github/start?return_to=%2Fauth%2Flogin",
      allowedOrigins,
    ).provider,
    "github",
  );
  assert.equal(
    parseOAuthStartUrl("https://attacker.example/auth/oauth/google/start", allowedOrigins),
    null,
  );
  assert.equal(
    parseOAuthStartUrl(
      "https://averqel.com/api/v1/auth/oauth/google/start?return_to=https%3A%2F%2Fattacker.example",
      allowedOrigins,
    ),
    null,
  );
});

test("intercepts OAuth navigation before it replaces the main page", () => {
  let prevented = false;
  let opened;
  const intercepted = interceptOAuthStartNavigation(
    { preventDefault: () => { prevented = true; } },
    googleStartUrl,
    allowedOrigins,
    (url, provider) => { opened = { url, provider }; },
  );

  assert.equal(intercepted, true);
  assert.equal(prevented, true);
  assert.deepEqual(opened, { url: googleStartUrl, provider: "google" });
});

test("opens a compact sandboxed window and returns the callback to the app", () => {
  const parentWindow = { isDestroyed: () => false };
  let authWindow;
  let completedUrl;
  let cancelledProvider;
  const opened = createOAuthWindow({
    BrowserWindow: class extends FakeAuthWindow {
      constructor(options) {
        super(options);
        authWindow = this;
      }
    },
    parentWindow,
    startUrl: googleStartUrl,
    allowedOrigins,
    callbackOrigin: "https://averqel.com",
    onComplete: (url) => { completedUrl = url; },
    onCancel: (provider) => { cancelledProvider = provider; },
  });

  assert.equal(opened, authWindow);
  assert.equal(authWindow.options.parent, parentWindow);
  assert.equal(authWindow.options.modal, true);
  assert.equal(authWindow.options.width, 520);
  assert.equal(authWindow.options.height, 720);
  assert.equal(authWindow.options.webPreferences.nodeIntegration, false);
  assert.equal(authWindow.options.webPreferences.contextIsolation, true);
  assert.equal(authWindow.options.webPreferences.sandbox, true);
  assert.equal("partition" in authWindow.options.webPreferences, false);
  assert.deepEqual(authWindow.loadedUrls, [googleStartUrl]);

  const callbackUrl = "https://averqel.com/auth/login?oauth=success&provider=google";
  let prevented = false;
  authWindow.webContents.emit("will-redirect", {
    preventDefault: () => { prevented = true; },
  }, callbackUrl);

  assert.equal(prevented, true);
  assert.equal(completedUrl, callbackUrl);
  assert.equal(cancelledProvider, undefined);
  assert.equal(authWindow.isDestroyed(), true);
});

test("closing the sign-in window reports cancellation", () => {
  let cancelledProvider;
  const authWindow = createOAuthWindow({
    BrowserWindow: FakeAuthWindow,
    parentWindow: { isDestroyed: () => false },
    startUrl: googleStartUrl,
    allowedOrigins,
    callbackOrigin: "https://averqel.com",
    onComplete: () => assert.fail("A closed sign-in window cannot complete OAuth."),
    onCancel: (provider) => { cancelledProvider = provider; },
  });

  authWindow.close();
  assert.equal(cancelledProvider, "google");
});

test("accepts only the matching OAuth callback on the AverQel login route", () => {
  assert.ok(
    parseOAuthCallbackUrl(
      "https://averqel.com/auth/login?oauth=2fa&provider=google",
      "google",
      "https://averqel.com/",
    ),
  );
  assert.equal(
    parseOAuthCallbackUrl(
      "https://attacker.example/auth/login?oauth=success&provider=google",
      "google",
      "https://averqel.com/",
    ),
    null,
  );
  assert.equal(
    parseOAuthCallbackUrl(
      "https://averqel.com/auth/login?oauth=success&provider=github",
      "google",
      "https://averqel.com/",
    ),
    null,
  );
});
