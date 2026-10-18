const assert = require("node:assert/strict");
const test = require("node:test");

const {
  getPackagedNeosisPaths,
  hasPackagedNeosisRuntime,
} = require("../electron/neosis-runtime.cjs");

test("recognizes NeoSIS only in a packaged app with its runtime and profile", () => {
  const paths = getPackagedNeosisPaths("/app/resources");
  const files = new Set([paths.entry, paths.profilePatch]);
  const fileExists = (file) => files.has(file);

  assert.equal(
    hasPackagedNeosisRuntime("/app/resources", true, fileExists),
    true,
  );
  assert.equal(
    hasPackagedNeosisRuntime("/app/resources", false, fileExists),
    false,
  );

  files.delete(paths.entry);
  assert.equal(
    hasPackagedNeosisRuntime("/app/resources", true, fileExists),
    false,
  );

  files.add(paths.entry);
  files.delete(paths.profilePatch);
  assert.equal(
    hasPackagedNeosisRuntime("/app/resources", true, fileExists),
    false,
  );
});
