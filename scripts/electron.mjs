import http from "node:http";
import https from "node:https";
import { spawn } from "node:child_process";
import { once } from "node:events";
import process from "node:process";
import { setTimeout as delay } from "node:timers/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const mode = process.argv[2] ?? "dev";

const [nodeMajor, nodeMinor] = process.versions.node.split(".").map(Number);
if (nodeMajor < 22 || (nodeMajor === 22 && nodeMinor < 12)) {
  console.error(
    `Electron development requires Node.js >=22.12.0; found ${process.versions.node}. ` +
      "Install/use Node 22, then run `pnpm --dir applications/desktop install --frozen-lockfile`.",
  );
  process.exit(1);
}

if (mode !== "dev") {
  console.error(`Unknown Electron mode: ${mode}`);
  console.error("Usage: pnpm electron dev");
  process.exit(1);
}

const pnpm = process.platform === "win32" ? "pnpm.cmd" : "pnpm";
const frontendUrl = process.env.ELECTRON_START_URL || "http://127.0.0.1:1030";
const childEnvironment = {
  ...process.env,
  ELECTRON_START_URL: frontendUrl,
  // Never let a local Electron session fall back to the production API.
  // Override this explicitly when testing through the local HTTPS proxy.
  NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:1000/api/v1",
};

function start(command, args) {
  return spawn(command, args, {
    cwd: rootDir,
    env: childEnvironment,
    stdio: "inherit",
  });
}

function probe(url) {
  return new Promise((resolve) => {
    const client = url.startsWith("https:") ? https : http;
    const request = client.get(url, { rejectUnauthorized: false }, (response) => {
      response.resume();
      resolve(true);
    });
    request.setTimeout(1000, () => {
      request.destroy();
      resolve(false);
    });
    request.on("error", () => resolve(false));
  });
}

async function waitForFrontend(child) {
  for (let attempt = 0; attempt < 120; attempt += 1) {
    if (child.exitCode !== null) {
      throw new Error("The frontend development server exited before becoming ready.");
    }
    if (await probe(frontendUrl)) return;
    await delay(500);
  }
  throw new Error(`Frontend did not become ready at ${frontendUrl} within 60 seconds.`);
}

let shuttingDown = false;
let frontend;
let electron;

function stop(child) {
  if (child && child.exitCode === null) child.kill();
}

function shutdown(code = 0) {
  if (shuttingDown) return;
  shuttingDown = true;
  stop(electron);
  stop(frontend);
  process.exitCode = code;
}

process.on("SIGINT", () => shutdown(0));
process.on("SIGTERM", () => shutdown(0));

frontend = start(pnpm, ["--dir", "frontend", "dev"]);
frontend.once("error", (error) => {
  console.error(`Could not start the frontend: ${error.message}`);
  shutdown(1);
});
frontend.once("exit", (code) => {
  if (!shuttingDown && code !== 0) {
    console.error(`Frontend development server exited with code ${code ?? "unknown"}.`);
    shutdown(code || 1);
  }
});

try {
  await waitForFrontend(frontend);
  console.log(`Frontend ready at ${frontendUrl}; starting Electron.`);
  electron = start(pnpm, ["--dir", "applications/desktop", "dev"]);
  electron.once("error", (error) => {
    console.error(`Could not start Electron: ${error.message}`);
    shutdown(1);
  });
  electron.once("exit", (code, signal) => {
    if (!shuttingDown) {
      if (signal) console.log(`Electron exited from ${signal}.`);
      shutdown(code ?? 0);
    }
  });
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  shutdown(1);
}

await once(process, "exit");
