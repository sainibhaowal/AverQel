const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const desktopRoot = path.resolve(__dirname, "..");
const packageJson = JSON.parse(
  readFileSync(path.join(desktopRoot, "package.json"), "utf8"),
);

test("desktop packages only the shared AverQel frontend as an extra resource", () => {
  assert.deepEqual(packageJson.build.extraResources, [
    { from: "../../frontend/out", to: "frontend" },
  ]);

  for (const scriptName of ["build", "build:linux", "build:windows", "build:mac"]) {
    assert.doesNotMatch(packageJson.scripts[scriptName], /neosis/iu);
  }

  assert.equal(packageJson.scripts["prepare:neosis-runtime"], undefined);
});
