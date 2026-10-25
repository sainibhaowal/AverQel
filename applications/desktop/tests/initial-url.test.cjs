const assert = require("node:assert/strict");
const test = require("node:test");

const { loginUrlForOrigin } = require("../electron/initial-url.cjs");

test("opens the login route on the packaged AverQel origin", () => {
  assert.equal(loginUrlForOrigin("https://averqel.com"), "https://averqel.com/auth/login");
});

test("opens the login route for a development origin without retaining a path or query", () => {
  assert.equal(
    loginUrlForOrigin("https://averqel.localhost/landing?preview=true"),
    "https://averqel.localhost/auth/login",
  );
});
