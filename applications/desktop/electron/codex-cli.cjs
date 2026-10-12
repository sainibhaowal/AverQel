const { spawn } = require("node:child_process");
const { accessSync, constants, existsSync, readdirSync } = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const APP_SERVER_TIMEOUT_MS = 20_000;
const MAX_PROTOCOL_LINE_BYTES = 8_000_000;
const MAX_CAPTURED_STATUS_BYTES = 8_192;

function sanitizeCodexProcessEnv(env) {
  const result = { ...env };
  for (const key of Object.keys(result)) {
    if (/(?:API_?KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|AUTHORIZATION)/i.test(key)) {
      delete result[key];
    }
  }
  return result;
}

function candidateExecutableNames(platform) {
  return platform === "win32"
    ? ["codex.exe", "codex.cmd", "codex.bat"]
    : ["codex"];
}

function resolveCodexExecutable({
  env = process.env,
  platform = process.platform,
  home = os.homedir(),
  exists = existsSync,
  isExecutable = (candidate) => {
    try {
      accessSync(candidate, constants.X_OK);
      return true;
    } catch {
      return false;
    }
  },
  readDirectory = readdirSync,
} = {}) {
  const names = candidateExecutableNames(platform);
  const directories = [];
  const explicit = typeof env.CODEX_CLI_PATH === "string" ? env.CODEX_CLI_PATH.trim() : "";
  if (explicit) {
    if (path.isAbsolute(explicit) && exists(explicit) &&
        (platform === "win32" || isExecutable(explicit))) return explicit;
    return null;
  }

  const pathDelimiter = platform === "win32" ? ";" : path.delimiter;
  for (const entry of String(env.PATH || "").split(pathDelimiter)) {
    if (entry) directories.push(entry);
  }

  const userHome = platform === "win32" && env.USERPROFILE ? env.USERPROFILE : home;
  const userPaths = platform === "win32"
    ? [
        path.join(userHome, "AppData", "Roaming", "npm"),
        path.join(userHome, "AppData", "Local", "Programs", "Codex"),
        path.join(userHome, "AppData", "Local", "Microsoft", "WinGet", "Links"),
      ]
    : [
        path.join(userHome, ".local", "bin"),
        path.join(userHome, ".local", "share", "pnpm"),
        path.join(userHome, ".npm-global", "bin"),
        path.join(userHome, ".volta", "bin"),
        path.join(userHome, ".bun", "bin"),
        path.join(userHome, ".asdf", "shims"),
      ];
  directories.push(...userPaths);

  if (platform !== "win32") {
    directories.push("/opt/homebrew/bin", "/usr/local/bin", "/usr/bin");
    const nodeVersions = path.join(userHome, ".nvm", "versions", "node");
    try {
      for (const entry of readDirectory(nodeVersions, { withFileTypes: true }).slice(0, 32)) {
        if (entry.isDirectory()) directories.push(path.join(nodeVersions, entry.name, "bin"));
      }
    } catch {
      // NVM is optional; PATH and the common package-manager locations remain checked.
    }
  }

  const seen = new Set();
  for (const directory of directories) {
    for (const name of names) {
      const candidate = path.resolve(directory, name);
      if (seen.has(candidate)) continue;
      seen.add(candidate);
      try {
        if (exists(candidate) && (platform === "win32" || isExecutable(candidate))) return candidate;
      } catch {
        // Skip inaccessible PATH entries and continue with the remaining candidates.
      }
    }
  }
  return null;
}

function buildInvocation(executable, args, { platform = process.platform, env = process.env } = {}) {
  if (platform !== "win32" || !/\.(?:cmd|bat)$/i.test(executable)) {
    return { command: executable, args };
  }
  if (/[\r\n%!]/.test(executable)) {
    throw new Error("Codex CLI is installed in a path that cannot be launched safely on Windows.");
  }
  // The only arguments passed here are fixed Codex subcommands and app-server
  // settings created by this module. Do not pass renderer-provided strings.
  const quote = (value) => `"${String(value).replace(/"/g, '""')}"`;
  const command = [quote(executable), ...args.map(quote)].join(" ");
  return {
    command: env.ComSpec || env.COMSPEC || "cmd.exe",
    args: ["/d", "/s", "/c", `"${command}"`],
  };
}

function classifyCodexLoginStatus(exitCode, output) {
  if (!Number.isInteger(exitCode)) return "unavailable";
  if (exitCode !== 0) {
    return /not\s+(?:currently\s+)?logged\s+in|not\s+authenticated|no\s+active\s+session/i.test(output)
      ? "not_authenticated"
      : "unavailable";
  }
  if (/logged in using chatgpt/i.test(output)) return "chatgpt";
  if (/logged in using (?:an? )?api[- ]?key/i.test(output)) return "api_key";
  if (/logged in using/i.test(output)) return "other_authenticated_method";
  return "unavailable";
}

function runCodexLoginStatus(executable, {
  env = process.env,
  platform = process.platform,
  spawnProcess = spawn,
  timeoutMs = 1_500,
  cwd = os.tmpdir(),
} = {}) {
  if (!executable) return Promise.resolve({ method: "not_installed" });
  const childEnv = sanitizeCodexProcessEnv(env);
  let invocation;
  try {
    invocation = buildInvocation(executable, ["login", "status"], { platform, env });
  } catch {
    return Promise.resolve({ method: "unavailable" });
  }
  return new Promise((resolve) => {
    let child;
    let stdout = "";
    let stderr = "";
    let settled = false;
    let timedOut = false;
    let timer;
    const finish = (exitCode) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve({
        method: timedOut
          ? "unavailable"
          : classifyCodexLoginStatus(exitCode, `${stdout}\n${stderr}`),
      });
    };
    try {
      child = spawnProcess(invocation.command, invocation.args, {
        env: childEnv,
        cwd,
        stdio: ["ignore", "pipe", "pipe"],
        windowsHide: true,
        shell: false,
      });
    } catch {
      finish(null);
      return;
    }
    const captureStatusOutput = (stream) => (chunk) => {
      const capturedBytes = Buffer.byteLength(stdout, "utf8") + Buffer.byteLength(stderr, "utf8");
      const remainingBytes = MAX_CAPTURED_STATUS_BYTES - capturedBytes;
      if (remainingBytes <= 0) return;
      const bytes = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
      const boundedChunk = bytes.subarray(0, remainingBytes).toString("utf8");
      if (stream === "stdout") stdout += boundedChunk;
      else stderr += boundedChunk;
    };
    child.stdout?.on("data", captureStatusOutput("stdout"));
    // Codex CLI versions have emitted the status summary on stderr. Keep both
    // streams bounded and classify locally; never return their contents.
    child.stderr?.on("data", captureStatusOutput("stderr"));
    child.once("error", () => finish(null));
    child.once("close", (code) => finish(code));
    timer = setTimeout(() => {
      timedOut = true;
      child.kill();
      finish(null);
    }, timeoutMs);
  });
}

function codexCliAccountId(executable, { env = process.env, home = os.homedir(), identity = "" } = {}) {
  if (!executable) return null;
  const codexHome = env.CODEX_HOME || path.join(home, ".codex");
  const crypto = require("node:crypto");
  return crypto
    .createHash("sha256")
    .update(`codex-cli\0${path.resolve(executable)}\0${path.resolve(codexHome)}\0${String(identity).trim().toLowerCase()}`)
    .digest("hex")
    .slice(0, 32);
}

function createRestrictedCodexCliAppServerArgs() {
  const permissions = "averqel_chatgpt_plan_v1";
  return [
    "app-server",
    "--listen",
    "stdio://",
    "-c",
    `default_permissions='${permissions}'`,
    "-c",
    `permissions.${permissions}.filesystem={':root'='deny',':minimal'='read'}`,
    "-c",
    "features.shell_tool=false",
    "-c",
    "features.multi_agent=false",
    "-c",
    "features.apps=false",
    "-c",
    "features.remote_plugin=false",
    "-c",
    "features.hooks=false",
    "-c",
    "plugins={}",
    "-c",
    "mcp_servers={}",
    "-c",
    "web_search='disabled'",
    "-c",
    "tools.web_search=false",
    "-c",
    "tools.view_image=false",
    "-c",
    "project_doc_max_bytes=0",
    "-c",
    "history.persistence='none'",
    "-c",
    "skills.config=[]",
  ];
}

class CodexAppServerClient {
  constructor({
    executable,
    env = process.env,
    platform = process.platform,
    spawnProcess = spawn,
    cwd = os.tmpdir(),
    requestTimeoutMs = APP_SERVER_TIMEOUT_MS,
    onServerRequest = null,
  }) {
    this.executable = executable;
    this.env = sanitizeCodexProcessEnv(env);
    this.platform = platform;
    this.spawnProcess = spawnProcess;
    this.cwd = cwd;
    this.requestTimeoutMs = requestTimeoutMs;
    this.onServerRequest = onServerRequest;
    this.child = null;
    this.nextRequestId = 1;
    this.pending = new Map();
    this.notificationHandlers = new Set();
    this.buffer = "";
    this.closed = false;
  }

  async start() {
    if (this.child) return;
  const invocation = buildInvocation(this.executable, createRestrictedCodexCliAppServerArgs(), {
      platform: this.platform,
      env: this.env,
    });
    this.child = this.spawnProcess(invocation.command, invocation.args, {
      env: this.env,
      cwd: this.cwd,
      stdio: ["pipe", "pipe", "ignore"],
      windowsHide: true,
      shell: false,
    });
    this.child.stdout?.on("data", (chunk) => this._onStdout(chunk));
    this.child.once("error", () => this._failPending(new Error("Codex CLI app-server could not start.")));
    this.child.once("close", (code) => {
      if (!this.closed) {
        this._failPending(
          new Error(code === 0
            ? "Codex CLI app-server closed unexpectedly."
            : "Codex CLI app-server could not complete the request."),
        );
      }
      this.closed = true;
    });
    await this.request("initialize", {
      clientInfo: { name: "averqel", title: "AverQel", version: "0.1.6" },
      capabilities: { experimentalApi: true },
    });
    this.notify("initialized", {});
  }

  onNotification(handler) {
    this.notificationHandlers.add(handler);
    return () => this.notificationHandlers.delete(handler);
  }

  notify(method, params) {
    this._write({ method, params });
  }

  request(method, params, timeoutMs = this.requestTimeoutMs) {
    const id = this.nextRequestId++;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error("Codex CLI app-server did not respond in time."));
      }, timeoutMs);
      this.pending.set(id, { resolve, reject, timer });
      try {
        this._write({ id, method, params });
      } catch {
        clearTimeout(timer);
        this.pending.delete(id);
        reject(new Error("Codex CLI app-server connection closed."));
      }
    });
  }

  respondToServerRequest(id, result) {
    this._write({ id, result });
  }

  _write(value) {
    if (!this.child || this.closed || !this.child.stdin?.writable) {
      throw new Error("Codex CLI app-server connection closed.");
    }
    this.child.stdin.write(`${JSON.stringify(value)}\n`);
  }

  _onStdout(chunk) {
    this.buffer += chunk.toString("utf8");
    if (Buffer.byteLength(this.buffer, "utf8") > MAX_PROTOCOL_LINE_BYTES) {
      this._failPending(new Error("Codex CLI app-server returned an oversized message."));
      this.close();
      return;
    }
    let boundary = this.buffer.indexOf("\n");
    while (boundary >= 0) {
      const line = this.buffer.slice(0, boundary).trim();
      this.buffer = this.buffer.slice(boundary + 1);
      if (line) this._handleLine(line);
      boundary = this.buffer.indexOf("\n");
    }
  }

  _handleLine(line) {
    let message;
    try {
      message = JSON.parse(line);
    } catch {
      this._failPending(new Error("Codex CLI app-server returned an invalid protocol message."));
      this.close();
      return;
    }
    if (Object.hasOwn(message, "id") && this.pending.has(message.id)) {
      const pending = this.pending.get(message.id);
      this.pending.delete(message.id);
      clearTimeout(pending.timer);
      if (message.error) {
        pending.reject(new Error("Codex CLI app-server rejected a request."));
      } else {
        pending.resolve(message.result || {});
      }
      return;
    }
    if (typeof message.method !== "string") return;
    if (Object.hasOwn(message, "id")) {
      void this._handleServerRequest(message);
      return;
    }
    for (const handler of this.notificationHandlers) {
      try {
        handler(message.method, message.params || {});
      } catch {
        // Notification consumers cannot break the app-server transport.
      }
    }
  }

  async _handleServerRequest(message) {
    try {
      const result = await this.onServerRequest?.(message);
      if (result !== undefined) this.respondToServerRequest(message.id, result);
      else this.respondToServerRequest(message.id, {});
    } catch {
      try {
        this.respondToServerRequest(message.id, {});
      } catch {
        // The connection may have closed while the callback was running.
      }
    }
  }

  _failPending(error) {
    for (const [id, pending] of this.pending) {
      clearTimeout(pending.timer);
      pending.reject(error);
      this.pending.delete(id);
    }
  }

  close() {
    if (this.closed) return;
    this.closed = true;
    this._failPending(new Error("Codex CLI app-server connection closed."));
    this.child?.kill();
  }
}

module.exports = {
  CodexAppServerClient,
  classifyCodexLoginStatus,
  codexCliAccountId,
  createRestrictedCodexCliAppServerArgs,
  resolveCodexExecutable,
  runCodexLoginStatus,
};
