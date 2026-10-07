const { existsSync } = require("node:fs");
const path = require("node:path");

function resolveNeosisSourceRoot(electronDirectory, environment = process.env) {
  const configuredRoot = environment.NEOSIS_SOURCE_DIR?.trim();
  const candidates = configuredRoot
    ? [path.resolve(configuredRoot)]
    : [
        path.resolve(electronDirectory, "../../../neosis"),
        path.resolve(electronDirectory, "../../../../AverQel Neosis"),
      ];
  const root = candidates.find((candidate) => existsSync(path.join(candidate, "package.json")));
  if (!root) {
    throw new Error(`NeoSIS source checkout was not found. Checked: ${candidates.join(", ")}`);
  }
  return root;
}

module.exports = { resolveNeosisSourceRoot };
