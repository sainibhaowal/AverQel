const assert = require("node:assert/strict");
const { mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync, existsSync, statSync } = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

async function loadPreparer() {
  return import("../scripts/prepare-neosis-package-env.mjs");
}

function createCheckout(root, platform = "linux", additions = []) {
  const desktopRoot = path.join(root, "apps", "desktop");
  mkdirSync(desktopRoot, { recursive: true });
  const template = [
    "NEOSIS_DESKTOP_APP_ID=com.example.neosis",
    "NEOSIS_DESKTOP_AUTO_UPDATE_ENV=test",
    "NEOSIS_DESKTOP_MANDATORY_UPDATE_TEST_ORIGIN=",
    "NEOSIS_DESKTOP_MANDATORY_UPDATE_CONFIG='{" + '"allowedAuthOrigins":["https://login.example.com"]' + "}'",
    ...additions,
    "",
  ].join("\n");
  writeFileSync(path.join(desktopRoot, `.env.${platform}.example`), template);
  return desktopRoot;
}

test("writes only the target platform's minimal preparation config without credentials", async (context) => {
  const temporaryRoot = mkdtempSync(path.join(os.tmpdir(), "averqel-neosis-env-"));
  context.after(() => rmSync(temporaryRoot, { recursive: true, force: true }));
  const desktopRoot = createCheckout(temporaryRoot, "windows", [
    "NEOSIS_DESKTOP_WINDOWS_TOKEN_PIN=must-not-copy",
    "NEOSIS_DESKTOP_WINDOWS_KEY_CONTAINER=must-not-copy",
  ]);
  const { prepareNeosisPackageEnvironment } = await loadPreparer();

  const outputPath = await prepareNeosisPackageEnvironment(temporaryRoot, "win32");
  const contents = readFileSync(outputPath, "utf8");

  assert.equal(path.basename(outputPath), ".env.windows");
  assert.equal(
    contents,
    [
      "NEOSIS_DESKTOP_APP_ID=com.example.neosis",
      "NEOSIS_DESKTOP_AUTO_UPDATE_ENV=test",
      "NEOSIS_DESKTOP_MANDATORY_UPDATE_TEST_ORIGIN=https://test.example.com",
      `NEOSIS_DESKTOP_MANDATORY_UPDATE_CONFIG='{"allowedAuthOrigins":["https://login.example.com"]}'`,
      "",
    ].join("\n"),
  );
  assert.equal(existsSync(path.join(desktopRoot, ".env.linux")), false);
  assert.equal(statSync(outputPath).mode & 0o077, 0);
});

test("preserves an existing local package config instead of overwriting it", async (context) => {
  const temporaryRoot = mkdtempSync(path.join(os.tmpdir(), "averqel-neosis-env-"));
  context.after(() => rmSync(temporaryRoot, { recursive: true, force: true }));
  const desktopRoot = createCheckout(temporaryRoot);
  const outputPath = path.join(desktopRoot, ".env.linux");
  writeFileSync(outputPath, "local-only-setting=preserve\n");
  const { prepareNeosisPackageEnvironment } = await loadPreparer();

  await assert.rejects(
    prepareNeosisPackageEnvironment(temporaryRoot, "linux"),
    /refusing to overwrite/,
  );
  assert.equal(readFileSync(outputPath, "utf8"), "local-only-setting=preserve\n");
});

test("rejects templates without a valid test policy before creating a config", async (context) => {
  const temporaryRoot = mkdtempSync(path.join(os.tmpdir(), "averqel-neosis-env-"));
  context.after(() => rmSync(temporaryRoot, { recursive: true, force: true }));
  const desktopRoot = createCheckout(temporaryRoot, "linux", [
    "NEOSIS_DESKTOP_MANDATORY_UPDATE_CONFIG='{}'",
  ]);
  const { prepareNeosisPackageEnvironment } = await loadPreparer();

  await assert.rejects(
    prepareNeosisPackageEnvironment(temporaryRoot, "linux"),
    /test policy requires allowedAuthOrigins/,
  );
  assert.equal(existsSync(path.join(desktopRoot, ".env.linux")), false);
});

test("refuses unsupported desktop release platforms", async () => {
  const { prepareNeosisPackageEnvironment } = await loadPreparer();

  await assert.rejects(
    prepareNeosisPackageEnvironment("/unused", "darwin"),
    /does not support darwin/,
  );
});
