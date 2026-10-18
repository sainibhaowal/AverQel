const assert = require("node:assert/strict");
const test = require("node:test");

const {
  resolveAverQelReturnUrl,
} = require("../electron/workspace-navigation.cjs");

test("returns to the last AverQel page on the same origin", () => {
  assert.equal(
    resolveAverQelReturnUrl(
      "https://averqel.com/dashboard/settings/providers?tab=openai#codex",
      "https://averqel.com",
    ),
    "https://averqel.com/dashboard/settings/providers?tab=openai#codex",
  );
});

test("returns to the authenticated dashboard if no AverQel page was saved", () => {
  assert.equal(
    resolveAverQelReturnUrl(null, "https://averqel.com"),
    "https://averqel.com/dashboard",
  );
});

test("does not navigate to a saved URL from another origin", () => {
  assert.equal(
    resolveAverQelReturnUrl(
      "https://attacker.example/path",
      "https://averqel.com",
    ),
    "https://averqel.com/dashboard",
  );
});

test("supports the same-origin local desktop development URL", () => {
  assert.equal(
    resolveAverQelReturnUrl(
      "http://127.0.0.1:1030/dashboard",
      "http://127.0.0.1:1030",
    ),
    "http://127.0.0.1:1030/dashboard",
  );
});
