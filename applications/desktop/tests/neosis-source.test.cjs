const assert = require("node:assert/strict");
const { mkdtempSync, mkdirSync, rmSync, writeFileSync } = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");
const { resolveNeosisSourceRoot } = require("../electron/neosis-source.cjs");

function createCheckout(root) {
  mkdirSync(root, { recursive: true });
  writeFileSync(path.join(root, "package.json"), '{"name":"neosis"}\n');
  return root;
}

test("uses NEOSIS_SOURCE_DIR when configured", (context) => {
  const temporaryRoot = mkdtempSync(path.join(os.tmpdir(), "averqel-neosis-path-"));
  context.after(() => rmSync(temporaryRoot, { recursive: true, force: true }));
  const sourceRoot = createCheckout(path.join(temporaryRoot, "custom checkout"));

  assert.equal(
    resolveNeosisSourceRoot(path.join(temporaryRoot, "AverQel/applications/desktop/electron"), {
      NEOSIS_SOURCE_DIR: sourceRoot,
    }),
    sourceRoot,
  );
});

test("finds a NeoSIS checkout adjacent to the AverQel repository", (context) => {
  const projectsRoot = mkdtempSync(path.join(os.tmpdir(), "averqel-neosis-path-"));
  context.after(() => rmSync(projectsRoot, { recursive: true, force: true }));
  const averqelRoot = path.join(projectsRoot, "AverQel");
  const electronDirectory = path.join(averqelRoot, "applications/desktop/electron");
  const sourceRoot = createCheckout(path.join(projectsRoot, "AverQel Neosis"));

  assert.equal(resolveNeosisSourceRoot(electronDirectory, {}), sourceRoot);
});

test("prefers the nested workspace checkout before the adjacent checkout", (context) => {
  const projectsRoot = mkdtempSync(path.join(os.tmpdir(), "averqel-neosis-path-"));
  context.after(() => rmSync(projectsRoot, { recursive: true, force: true }));
  const averqelRoot = path.join(projectsRoot, "AverQel");
  const electronDirectory = path.join(averqelRoot, "applications/desktop/electron");
  const nestedRoot = createCheckout(path.join(averqelRoot, "neosis"));
  createCheckout(path.join(projectsRoot, "AverQel Neosis"));

  assert.equal(resolveNeosisSourceRoot(electronDirectory, {}), nestedRoot);
});

test("fails with the checked paths when no checkout exists", (context) => {
  const projectsRoot = mkdtempSync(path.join(os.tmpdir(), "averqel-neosis-path-"));
  context.after(() => rmSync(projectsRoot, { recursive: true, force: true }));
  const electronDirectory = path.join(projectsRoot, "AverQel/applications/desktop/electron");

  assert.throws(() => resolveNeosisSourceRoot(electronDirectory, {}), /NeoSIS source checkout was not found/);
});
