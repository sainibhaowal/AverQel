const assert = require("node:assert/strict");
const { createRequire } = require("node:module");
const path = require("node:path");
const test = require("node:test");

const desktopRoot = path.resolve(__dirname, "..");
const desktopPackage = require("../package.json");
const electronBuilderRequire = createRequire(
  require.resolve("electron-builder", { paths: [desktopRoot] }),
);
const { FileMatcher } = electronBuilderRequire(
  "app-builder-lib/out/fileMatcher.js",
);

test("copies NeoSIS node_modules from a FileMatcher root that is not pruned", () => {
  const resource = desktopPackage.build.extraResources.find(
    (entry) =>
      entry.from === ".neosis-runtime/neosis/node_modules" &&
      entry.to === "neosis/node_modules",
  );
  assert.ok(
    resource,
    "NeoSIS dependencies must have a dedicated extraResources mapping",
  );

  const matcher = new FileMatcher(
    path.resolve(desktopRoot, resource.from),
    resource.to,
    (value) => value,
    resource.filter,
  );
  const accepts = matcher.createFilter();
  const source = path.resolve(desktopRoot, resource.from);
  const entries = [
    ["@averqel", true],
    ["@averqel/neosis", true],
    ["@averqel/neosis/lib", true],
    ["@averqel/neosis/lib/bin.js", false],
  ];

  for (const [relativePath, isDirectory] of entries) {
    assert.equal(
      accepts(path.join(source, relativePath), {
        isDirectory: () => isDirectory,
      }),
      true,
      `Electron Builder should include ${relativePath}`,
    );
  }

  const previousRoot = path.resolve(desktopRoot, ".neosis-runtime/neosis");
  const previousMatcher = new FileMatcher(
    previousRoot,
    "neosis",
    (value) => value,
    ["**/*"],
  );
  assert.equal(
    previousMatcher.createFilter()(path.join(previousRoot, "node_modules"), {
      isDirectory: () => true,
    }),
    false,
    "the former broad mapping reproduces Electron Builder's root-node_modules exclusion",
  );
});
