#!/usr/bin/env node

import { readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

const version = process.argv[2] || "";
if (!/^\d+\.\d+\.\d+$/.test(version)) {
  throw new Error(`Expected desktop version MAJOR.MINOR.PATCH, received: ${version || "(empty)"}`);
}

const desktopDir = resolve(process.cwd(), "applications/desktop");
const packageJsonPath = resolve(desktopDir, "package.json");

const packageJson = JSON.parse(await readFile(packageJsonPath, "utf8"));
packageJson.version = version;
await writeFile(packageJsonPath, `${JSON.stringify(packageJson, null, 2)}\n`);

console.log(`Stamped AverQel Electron desktop release version ${version}`);
