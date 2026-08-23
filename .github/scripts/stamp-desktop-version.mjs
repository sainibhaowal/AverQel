#!/usr/bin/env node

import { readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

const version = process.argv[2] || "";
if (!/^\d+\.\d+\.\d+$/.test(version)) {
  throw new Error(`Expected desktop version MAJOR.MINOR.PATCH, received: ${version || "(empty)"}`);
}

const desktopDir = resolve(process.cwd(), "applications/desktop");
const tauriConfigPath = resolve(desktopDir, "src-tauri/tauri.conf.json");
const cargoTomlPath = resolve(desktopDir, "src-tauri/Cargo.toml");
const packageJsonPath = resolve(desktopDir, "package.json");

const tauriConfig = JSON.parse(await readFile(tauriConfigPath, "utf8"));
tauriConfig.version = version;
await writeFile(tauriConfigPath, `${JSON.stringify(tauriConfig, null, 2)}\n`);

const packageJson = JSON.parse(await readFile(packageJsonPath, "utf8"));
packageJson.version = version;
await writeFile(packageJsonPath, `${JSON.stringify(packageJson, null, 2)}\n`);

const cargoToml = await readFile(cargoTomlPath, "utf8");
const stampedCargoToml = cargoToml.replace(
  /(^\[package\][\s\S]*?^version\s*=\s*)"[^"]+"/m,
  `$1"${version}"`,
);
if (stampedCargoToml === cargoToml) {
  throw new Error("Could not find the package version in applications/desktop/src-tauri/Cargo.toml");
}
await writeFile(cargoTomlPath, stampedCargoToml);

console.log(`Stamped AverQel desktop release version ${version}`);
