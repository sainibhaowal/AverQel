const { existsSync } = require("node:fs");
const path = require("node:path");

function getPackagedNeosisPaths(resourcesPath) {
  const root = path.join(resourcesPath, "neosis");
  return {
    root,
    entry: path.join(
      root,
      "node_modules",
      "@averqel",
      "neosis",
      "lib",
      "bin.js",
    ),
    profilePatch: path.join(root, "averqel-local-profile.patch.yml"),
  };
}

function hasPackagedNeosisRuntime(
  resourcesPath,
  isPackaged,
  fileExists = existsSync,
) {
  if (!isPackaged) return false;
  const { entry, profilePatch } = getPackagedNeosisPaths(resourcesPath);
  return fileExists(entry) && fileExists(profilePatch);
}

module.exports = { getPackagedNeosisPaths, hasPackagedNeosisRuntime };
