import { cpSync, existsSync, rmSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";

const desktopRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const workspaceRoot = path.resolve(desktopRoot, "..", "..");
const configuredNeosisRoot = process.env.NEOSIS_SOURCE_DIR?.trim();
const neosisCandidates = configuredNeosisRoot
  ? [path.resolve(configuredNeosisRoot)]
  : [
      path.join(workspaceRoot, "neosis"),
      path.resolve(workspaceRoot, "..", "AverQel Neosis"),
    ];
const neosisRoot = neosisCandidates.find((candidate) => existsSync(path.join(candidate, "package.json")))
  ?? neosisCandidates[0];
const targetByPlatform = {
  linux: "linux-x64",
  win32: "win-x64",
};
const target = process.arch === "x64" ? targetByPlatform[process.platform] : undefined;
const output = path.join(desktopRoot, ".neosis-runtime");

if (target === undefined) {
  throw new Error(`NeoSIS runtime preparation supports Linux x64 and Windows x64 builds; received ${process.platform}-${process.arch}.`);
}
if (!existsSync(path.join(neosisRoot, "package.json"))) {
  throw new Error(`NeoSIS source checkout was not found at ${neosisRoot}.`);
}

const pnpmArgs = ["--dir", neosisRoot, "--filter", "@averqel/neosis-desktop", "run", "prepare:package", "--", target];
const packageManagerScript = process.env.npm_execpath;
const command = packageManagerScript ? process.execPath : process.platform === "win32" ? "pnpm.cmd" : "pnpm";
const args = packageManagerScript ? [packageManagerScript, ...pnpmArgs] : pnpmArgs;
const result = spawnSync(
  command,
  args,
  { cwd: workspaceRoot, stdio: "inherit", env: process.env, shell: !packageManagerScript && process.platform === "win32" },
);
if (result.status !== 0) {
  throw new Error(`NeoSIS production runtime preparation failed with status ${String(result.status)}.`);
}

const preparedRoot = path.join(neosisRoot, "apps", "desktop", ".desktop-build", "targets", target);
const runtime = path.join(preparedRoot, "neosis");
if (!existsSync(runtime)) {
  throw new Error("NeoSIS preparation completed without its required production runtime resources.");
}

rmSync(output, { recursive: true, force: true });
cpSync(runtime, path.join(output, "neosis"), { recursive: true, dereference: true });
