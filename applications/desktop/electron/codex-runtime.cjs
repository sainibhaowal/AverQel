const crypto = require("node:crypto");
const http = require("node:http");
const os = require("node:os");
const path = require("node:path");
const { chmod, mkdir, mkdtemp, open, readFile, rename, rm, unlink } = require("node:fs/promises");
const {
  CodexAppServerClient,
  codexCliAccountId,
  resolveCodexExecutable,
  runCodexLoginStatus,
} = require("./codex-cli.cjs");

const ISSUER = "https://auth.openai.com";
const TOKEN_ENDPOINT = `${ISSUER}/api/accounts/oauth/token`;
const RESOURCE = "https://api.openai.com/v1";
const REQUIRED_SCOPES = [
  "openid",
  "profile",
  "email",
  "offline_access",
  "resource.invoke",
  "chatgpt.tokens.use.direct",
];
const SAFE_RESPONSE_EVENTS = new Set([
  "response.output_text.delta",
  "response.output_item.added",
  "response.function_call_arguments.delta",
  "response.function_call_arguments.done",
  "response.completed",
  "response.failed",
  "response.incomplete",
  "error",
]);
const MAX_INFERENCE_BODY_BYTES = 40_000_000;
const MAX_CONCURRENT_STREAMS = 4;
const SAFE_ERROR_CODE = /^[A-Za-z0-9_.-]{1,96}$/;
const SAFE_REQUEST_ID = /^[A-Za-z0-9_.:-]{1,128}$/;
const SAFE_CLIENT_ID = /^[A-Za-z0-9_.:-]{1,128}$/;
const SAFE_CODEX_REASONING_EFFORT = /^(?:none|[A-Za-z][A-Za-z0-9_-]{0,19})$/;
const CODEX_CLI_STATUS_CACHE_MS = 15_000;
const CODEX_CLI_PERMISSION_PROFILE = "averqel_chatgpt_plan_v1";
const CODEX_API_TO_UI_REASONING_EFFORT = new Map([
  ["low", "low"],
  ["medium", "medium"],
  ["high", "high"],
  ["xhigh", "very_high"],
  ["max", "extreme_high"],
  ["minimal", "minimal"],
  ["ultra", "ultra"],
]);

function normalizeCodexEffort(value) {
  if (typeof value !== "string") return null;
  const native = value.trim();
  const lower = native.toLowerCase();
  const canonical = CODEX_API_TO_UI_REASONING_EFFORT.get(lower) || lower.replaceAll("-", "_");
  if (!/^[a-z][a-z0-9_-]{0,19}$/.test(canonical)) return null;
  return { canonical, native };
}

function codexReasoningEfforts(model) {
  if (!Array.isArray(model?.supportedReasoningEfforts)) return undefined;
  const efforts = [];
  const effortValues = {};
  for (const entry of model.supportedReasoningEfforts) {
    const upstreamEffort = typeof entry === "string" ? entry : entry?.reasoningEffort;
    const normalized = normalizeCodexEffort(upstreamEffort);
    if (normalized && !efforts.includes(normalized.canonical) && efforts.length < 32) {
      efforts.push(normalized.canonical);
      effortValues[normalized.canonical] = normalized.native;
    }
  }
  return { efforts, effortValues };
}

function advertisedBrowserEfforts(model) {
  const raw = model?.supported_reasoning_efforts ?? model?.supportedReasoningEfforts;
  if (!Array.isArray(raw)) return undefined;
  return codexReasoningEfforts({ supportedReasoningEfforts: raw });
}

function encodeBase64Url(value) {
  return Buffer.from(value).toString("base64url");
}

function safeEqual(left, right) {
  const a = Buffer.from(String(left));
  const b = Buffer.from(String(right));
  return a.length === b.length && crypto.timingSafeEqual(a, b);
}

function loopbackAddress(address) {
  return address === "127.0.0.1" || address === "::1" || address === "::ffff:127.0.0.1";
}

function publicAccount(account) {
  return {
    id: account.id,
    email: account.email || null,
    name: account.name || null,
    connected: true,
  };
}

function codexCliInput(items) {
  const transcript = [];
  const images = [];
  const textOf = (content) => {
    if (typeof content === "string") return content;
    if (!Array.isArray(content)) return "";
    const text = [];
    for (const part of content) {
      if (!part || typeof part !== "object") continue;
      if (["text", "input_text", "output_text"].includes(part.type) && typeof part.text === "string") {
        text.push(part.text);
      } else if (part.type === "input_image") {
        const url = part.image_url;
        const imageUrl = typeof url === "string" ? url : url?.url;
        if (
          typeof imageUrl === "string" &&
          (imageUrl.startsWith("https://") || imageUrl.startsWith("data:image/")) &&
          images.length < 10
        ) images.push(imageUrl);
        text.push("[Image attached]");
      }
    }
    return text.join("\n");
  };

  for (const item of items) {
    if (!item || typeof item !== "object") continue;
    if (item.type === "function_call") {
      transcript.push(
        `ASSISTANT TOOL CALL (${String(item.name || "unknown")}):\n${String(item.arguments || "{}").slice(0, 16_000)}`,
      );
    } else if (item.type === "function_call_output") {
      transcript.push(
        `TOOL RESULT (${String(item.call_id || "unknown")}):\n${String(item.output || "").slice(0, 100_000)}`,
      );
    } else if (item.role || item.type === "message") {
      const role = ["assistant", "user", "system", "developer"].includes(item.role)
        ? item.role.toUpperCase()
        : "USER";
      const content = textOf(item.content);
      if (content) transcript.push(`${role}:\n${content}`);
    }
  }

  return { input: transcript.join("\n\n").slice(0, 1_000_000), images };
}

function codexCliDynamicTools(tools) {
  if (!Array.isArray(tools)) return [];
  const namespaces = [];
  const usedNames = new Set();
  for (const entry of tools.slice(0, 128)) {
    if (!entry || typeof entry !== "object") continue;
    if (entry.type === "namespace" && typeof entry.name === "string" && Array.isArray(entry.tools)) {
      const functions = [];
      for (const tool of entry.tools) {
        if (
          !tool || tool.type !== "function" || typeof tool.name !== "string" ||
          !/^[A-Za-z0-9_.-]{1,64}$/.test(tool.name) || usedNames.has(tool.name)
        ) continue;
        usedNames.add(tool.name);
        functions.push({
          type: "function",
          name: tool.name,
          description: typeof tool.description === "string" ? tool.description.slice(0, 1_000) : "",
          inputSchema: tool.parameters && typeof tool.parameters === "object"
            ? tool.parameters
            : { type: "object", properties: {} },
        });
      }
      if (functions.length) {
        namespaces.push({
          type: "namespace",
          name: entry.name.slice(0, 64),
          description: typeof entry.description === "string" ? entry.description.slice(0, 1_000) : "",
          tools: functions,
        });
      }
    } else if (entry.type === "function" && typeof entry.name === "string" && !usedNames.has(entry.name)) {
      if (!/^[A-Za-z0-9_.-]{1,64}$/.test(entry.name)) continue;
      usedNames.add(entry.name);
      namespaces.push({
        type: "namespace",
        name: "averqel",
        description: "Tools available to the AverQel agent.",
        tools: [{
          type: "function",
          name: entry.name,
          description: typeof entry.description === "string" ? entry.description.slice(0, 1_000) : "",
          inputSchema: entry.parameters && typeof entry.parameters === "object"
            ? entry.parameters
            : { type: "object", properties: {} },
        }],
      });
    }
  }
  return namespaces;
}

class CodexDesktopRuntime {
  constructor({ app, safeStorage, shell, emit, codexCli = {}, fetchImpl = globalThis.fetch }) {
    this.app = app;
    this.safeStorage = safeStorage;
    this.shell = shell;
    this.emit = emit;
    this.codexCli = codexCli;
    this.fetchImpl = fetchImpl;
    this.refreshes = new Map();
    this.streams = new Map();
    this.storeReadPromise = null;
    this.storeWriteQueue = Promise.resolve();
    this.connectOperation = null;
    this.oidcConfig = null;
    this.jwks = null;
    this.cliStatusCache = null;
    this.cliStatusPromise = null;
    this.cliConnectOperation = null;
  }

  get storePath() {
    return path.join(this.app.getPath("userData"), "codex", "accounts.enc");
  }

  _secureStorageAvailable() {
    if (!this.safeStorage.isEncryptionAvailable()) return false;
    if (process.platform === "linux") {
      const backend = this.safeStorage.getSelectedStorageBackend?.();
      if (!["gnome_libsecret", "kwallet", "kwallet5", "kwallet6"].includes(backend)) {
        return false;
      }
    }
    return true;
  }

  _safeWorkingDirectory() {
    try {
      const temporaryDirectory = this.app.getPath("temp");
      if (typeof temporaryDirectory === "string" && temporaryDirectory.trim()) {
        return temporaryDirectory;
      }
    } catch {
      // Use the operating system's temporary directory if Electron cannot resolve it.
    }
    return os.tmpdir();
  }

  async _readStore() {
    if (this.storeReadPromise) return this.storeReadPromise;
    const operation = this._loadStore();
    this.storeReadPromise = operation;
    try {
      return await operation;
    } finally {
      if (this.storeReadPromise === operation) this.storeReadPromise = null;
    }
  }

  async _loadStore() {
    if (!this._secureStorageAvailable()) {
      throw new Error(
        "Secure operating-system credential storage is unavailable. Enable the system keyring and try again.",
      );
    }
    try {
      const encrypted = await readFile(this.storePath);
      const raw = this.safeStorage.decryptString(encrypted);
      const store = JSON.parse(raw);
      if (!store || typeof store !== "object" || !Array.isArray(store.accounts)) {
        throw new Error("Stored Codex account data is invalid.");
      }
      if (!Array.isArray(store.pendingRegistrations)) store.pendingRegistrations = [];
      let persist = false;
      if (typeof store.hostId !== "string" || !store.hostId.startsWith("urn:uuid:")) {
        store.hostId = `urn:uuid:${crypto.randomUUID()}`;
        persist = true;
      }
      if (store.version !== 2 || persist) {
        store.version = 2;
        await this._writeStore(store);
      }
      return store;
    } catch (error) {
      if (error && error.code === "ENOENT") {
        const store = {
          version: 2,
          hostId: `urn:uuid:${crypto.randomUUID()}`,
          accounts: [],
          pendingRegistrations: [],
        };
        await this._writeStore(store);
        return store;
      }
      throw error;
    }
  }

  async _updateStore(update) {
    const previous = this.storeWriteQueue;
    let release;
    this.storeWriteQueue = new Promise((resolve) => {
      release = resolve;
    });
    await previous;
    try {
      const store = await this._readStore();
      const result = update(store);
      await this._writeStore(store);
      return result;
    } finally {
      release();
    }
  }

  async _writeStore(store) {
    if (!this._secureStorageAvailable()) {
      throw new Error("Secure operating-system credential storage is unavailable.");
    }
    const directory = path.dirname(this.storePath);
    await mkdir(directory, { recursive: true, mode: 0o700 });
    store.version = 2;
    if (!Array.isArray(store.pendingRegistrations)) store.pendingRegistrations = [];
    const encrypted = this.safeStorage.encryptString(JSON.stringify(store));
    const temporary = `${this.storePath}.${process.pid}.${crypto.randomUUID()}.tmp`;
    const handle = await open(temporary, "wx", 0o600);
    try {
      await handle.writeFile(encrypted);
      await handle.sync();
    } finally {
      await handle.close();
    }
    try {
      await rename(temporary, this.storePath);
    } catch (error) {
      await unlink(temporary).catch(() => undefined);
      throw error;
    }
  }

  async status() {
    const cli = await this._codexCliStatus();
    const secureStorageAvailable = this._secureStorageAvailable();
    let savedAccounts = [];
    let chatgptSignInAvailable = secureStorageAvailable;
    let storageMessage;
    if (secureStorageAvailable) {
      try {
        const store = await this._readStore();
        savedAccounts = store.accounts.map((account) => ({
          ...publicAccount(account),
          source: "chatgpt",
        }));
      } catch {
        chatgptSignInAvailable = false;
        storageMessage = "Saved ChatGPT sign-in is unavailable. Resolve the operating-system credential storage issue and retry.";
      }
    }

    const cliAccount = cli.method === "chatgpt" && cli.accountId
      ? {
          id: cli.accountId,
          email: null,
          name: "Codex CLI ChatGPT login",
          connected: true,
          source: "codex_cli",
          planType: cli.planType || null,
        }
      : null;
    const cliMessage = cli.method === "api_key"
      ? "Codex CLI is signed in with an API key. AverQel uses ChatGPT plan access here; choose ChatGPT sign-in to connect that account."
      : cli.method === "not_authenticated"
        ? "Codex CLI is installed but is not signed in to ChatGPT. Continue with ChatGPT to connect an account."
        : cli.method === "unavailable"
          ? "Codex CLI was found, but its sign-in status could not be checked. You can still use ChatGPT sign-in."
          : cli.method === "other_authenticated_method"
            ? "Codex CLI is signed in with another authentication method. Continue with ChatGPT to use a ChatGPT plan account."
            : null;
    const accounts = [...(cliAccount ? [cliAccount] : []), ...savedAccounts];
    const secureStorageMessage = !chatgptSignInAvailable
      ? storageMessage || (process.platform === "linux"
          ? "A secure Linux keyring (such as GNOME Keyring or KWallet) is required for ChatGPT sign-in."
          : "Secure operating-system credential storage is unavailable for ChatGPT sign-in.")
      : undefined;
    return {
      available: Boolean(chatgptSignInAvailable || cliAccount),
      chatgptSignInAvailable,
      accounts,
      ...(secureStorageMessage ? { message: secureStorageMessage } : {}),
      ...(cliMessage ? { cliMessage } : {}),
    };
  }

  async _codexCliStatus({ force = false } = {}) {
    if (this.cliStatusPromise) return this.cliStatusPromise;
    if (
      !force &&
      this.cliStatusCache &&
      Date.now() - this.cliStatusCache.checkedAt < CODEX_CLI_STATUS_CACHE_MS
    ) {
      return this.cliStatusCache.value;
    }
    const operation = (async () => {
      const env = this.codexCli.env || process.env;
      const platform = this.codexCli.platform || process.platform;
      const home = this.codexCli.home || os.homedir();
      const executable = (this.codexCli.resolveExecutable || resolveCodexExecutable)(
        { env, platform, home },
      );
      if (!executable) return { method: "not_installed", executable: null, accountId: null };
      const result = await (this.codexCli.runLoginStatus || runCodexLoginStatus)(executable, {
        env,
        platform,
        spawnProcess: this.codexCli.spawnProcess,
        timeoutMs: 1_500,
        cwd: this._safeWorkingDirectory(),
      });
      if (result.method !== "chatgpt") {
        return { ...result, executable, accountId: null };
      }
      const client = this._newCodexAppServer(
        executable,
        null,
        2_500,
        this._safeWorkingDirectory(),
      );
      try {
        await client.start();
        const account = await this._readCodexCliAccount(client);
        if (typeof account.email !== "string" || !account.email.trim()) {
          return { method: "unavailable", executable, accountId: null };
        }
        return {
          method: "chatgpt",
          executable,
          accountId: codexCliAccountId(executable, { env, home, identity: account.email }),
          planType: typeof account.planType === "string" ? account.planType : null,
        };
      } catch {
        return { method: "unavailable", executable, accountId: null };
      } finally {
        client.close();
      }
    })();
    this.cliStatusPromise = operation;
    try {
      const value = await operation;
      this.cliStatusCache = { checkedAt: Date.now(), value };
      return value;
    } finally {
      if (this.cliStatusPromise === operation) this.cliStatusPromise = null;
    }
  }

  _newCodexAppServer(executable, onServerRequest = null, requestTimeoutMs, cwd) {
    const env = this.codexCli.env || process.env;
    return new (this.codexCli.AppServerClient || CodexAppServerClient)({
      executable,
      env,
      platform: this.codexCli.platform || process.platform,
      spawnProcess: this.codexCli.spawnProcess,
      cwd: cwd || this._safeWorkingDirectory(),
      ...(requestTimeoutMs ? { requestTimeoutMs } : {}),
      onServerRequest,
    });
  }

  async _readCodexCliAccount(client, cwd = this._safeWorkingDirectory()) {
    const profiles = await client.request("permissionProfile/list", { cwd });
    if (!Array.isArray(profiles?.data) || !profiles.data.some(
      (profile) => profile?.id === CODEX_CLI_PERMISSION_PROFILE && profile.allowed === true,
    )) {
      throw new Error("The Codex CLI does not support AverQel's restricted inference profile.");
    }
    const result = await client.request("account/read", { refreshToken: false });
    if (result?.account?.type !== "chatgpt") {
      throw new Error("The Codex CLI does not have a signed-in ChatGPT account. Use ChatGPT sign-in instead.");
    }
    return result.account;
  }

  async _listCodexCliModels(client) {
    const models = [];
    const seen = new Set();
    let cursor = null;
    for (let page = 0; page < 10; page += 1) {
      const result = await client.request("model/list", {
        cursor,
        includeHidden: false,
        limit: 100,
      });
      if (!Array.isArray(result?.data)) {
        throw new Error("Codex CLI returned an invalid model catalog.");
      }
      for (const model of result.data) {
        if (
          !model || model.hidden !== false ||
          typeof model.model !== "string" || !model.model.trim() ||
          model.model.length > 255 || seen.has(model.model)
        ) continue;
        seen.add(model.model);
        const name = typeof model.displayName === "string" && model.displayName.trim()
          ? model.displayName.trim()
          : model.model;
        const reasoningEfforts = codexReasoningEfforts(model);
        models.push({
          id: model.model,
          name: name.slice(0, 255),
          kind: "chat",
          ...(reasoningEfforts ? {
            supportedReasoningEfforts: reasoningEfforts.efforts,
            reasoningEffortValues: reasoningEfforts.effortValues,
          } : {}),
        });
      }
      cursor = typeof result.nextCursor === "string" && result.nextCursor
        ? result.nextCursor
        : null;
      if (!cursor) break;
    }
    if (models.length === 0) throw new Error("Codex CLI did not return any visible ChatGPT models.");
    return models;
  }

  async _loadCodexCliSession(accountId) {
    const cli = await this._codexCliStatus();
    if (cli.method !== "chatgpt" || !cli.executable || cli.accountId !== accountId) {
      throw new Error("The selected Codex CLI ChatGPT login is no longer available. Refresh and try again.");
    }
    const client = this._newCodexAppServer(
      cli.executable,
      null,
      undefined,
      this._safeWorkingDirectory(),
    );
    try {
      await client.start();
      const account = await this._readCodexCliAccount(client);
      if (
        typeof account.email !== "string" ||
        codexCliAccountId(cli.executable, {
          env: this.codexCli.env || process.env,
          home: this.codexCli.home || os.homedir(),
          identity: account.email,
        }) !== accountId
      ) {
        throw new Error("The signed-in Codex CLI account changed. Refresh the account list and try again.");
      }
      const models = await this._listCodexCliModels(client);
      return { cli, models };
    } finally {
      client.close();
    }
  }

  async _connectCodexCli(accountId) {
    if (this.cliConnectOperation) {
      if (this.cliConnectOperation.accountId === accountId) return this.cliConnectOperation.promise;
      throw new Error("A Codex CLI account check is already running in this AverQel window.");
    }
    const promise = (async () => {
      const { cli, models } = await this._loadCodexCliSession(accountId);
      return {
        account: {
          id: cli.accountId,
          email: null,
          name: "Codex CLI ChatGPT login",
          connected: true,
          source: "codex_cli",
          planType: cli.planType || null,
        },
        models,
      };
    })();
    this.cliConnectOperation = { accountId, promise };
    try {
      return await promise;
    } finally {
      if (this.cliConnectOperation?.promise === promise) this.cliConnectOperation = null;
    }
  }

  async _account(accountId, store) {
    const account = store.accounts.find((item) => item.id === accountId);
    if (!account) throw new Error("The selected ChatGPT account is no longer connected.");
    return account;
  }

  async _getOidcConfig() {
    if (this.oidcConfig) return this.oidcConfig;
    const response = await this.fetchImpl(`${ISSUER}/.well-known/openid-configuration`, {
      signal: AbortSignal.timeout(10_000),
      headers: { accept: "application/json" },
    });
    if (!response.ok) throw new Error("OpenAI sign-in metadata could not be loaded.");
    const config = await response.json();
    if (
      config.issuer !== ISSUER ||
      typeof config.jwks_uri !== "string" ||
      !config.jwks_uri.startsWith(`${ISSUER}/`)
    ) {
      throw new Error("OpenAI sign-in metadata failed issuer validation.");
    }
    this.oidcConfig = config;
    return config;
  }

  async _getJwks() {
    if (this.jwks) return this.jwks;
    const config = await this._getOidcConfig();
    const response = await this.fetchImpl(config.jwks_uri, {
      signal: AbortSignal.timeout(10_000),
      headers: { accept: "application/json" },
    });
    if (!response.ok) throw new Error("OpenAI sign-in keys could not be loaded.");
    const jwks = await response.json();
    if (!Array.isArray(jwks.keys)) throw new Error("OpenAI sign-in keys are invalid.");
    this.jwks = jwks;
    return jwks;
  }

  async _validateIdToken(token, { clientId, nonce, expectedSubject } = {}) {
    const segments = String(token || "").split(".");
    if (segments.length !== 3) throw new Error("OpenAI returned an invalid identity token.");
    let header;
    let claims;
    try {
      header = JSON.parse(Buffer.from(segments[0], "base64url").toString("utf8"));
      claims = JSON.parse(Buffer.from(segments[1], "base64url").toString("utf8"));
    } catch {
      throw new Error("OpenAI returned an invalid identity token.");
    }
    if (!header || !claims || typeof header.kid !== "string") {
      throw new Error("OpenAI returned an invalid identity token.");
    }
    const jwks = await this._getJwks();
    const jwk = jwks.keys.find((key) => key.kid === header.kid && (!key.use || key.use === "sig"));
    if (!jwk) {
      this.jwks = null;
      const refreshed = await this._getJwks();
      const replacement = refreshed.keys.find((key) => key.kid === header.kid && (!key.use || key.use === "sig"));
      if (!replacement) throw new Error("OpenAI identity token signature key was not found.");
      return this._verifyIdTokenWithKey(token, segments, header, claims, replacement, {
        clientId,
        nonce,
        expectedSubject,
      });
    }
    return this._verifyIdTokenWithKey(token, segments, header, claims, jwk, {
      clientId,
      nonce,
      expectedSubject,
    });
  }

  _verifyIdTokenWithKey(token, segments, header, claims, jwk, { clientId, nonce, expectedSubject }) {
    const allowed = new Map([
      ["RS256", "RSA-SHA256"],
      ["RS384", "RSA-SHA384"],
      ["RS512", "RSA-SHA512"],
      ["ES256", "sha256"],
      ["ES384", "sha384"],
      ["ES512", "sha512"],
    ]);
    const digest = allowed.get(header.alg);
    if (!digest || (jwk.alg && jwk.alg !== header.alg)) {
      throw new Error("OpenAI identity token uses an unsupported signature algorithm.");
    }
    const key = crypto.createPublicKey({ key: jwk, format: "jwk" });
    const signature = Buffer.from(segments[2], "base64url");
    const signingInput = Buffer.from(`${segments[0]}.${segments[1]}`);
    const verified = crypto.verify(
      digest,
      signingInput,
      header.alg.startsWith("ES") ? { key, dsaEncoding: "ieee-p1363" } : key,
      signature,
    );
    if (!verified) throw new Error("OpenAI identity token signature is invalid.");
    const now = Math.floor(Date.now() / 1000);
    const audiences = Array.isArray(claims.aud) ? claims.aud : [claims.aud];
    const validNotBefore =
      !Object.prototype.hasOwnProperty.call(claims, "nbf") ||
      (Number.isFinite(claims.nbf) && claims.nbf <= now + 5);
    if (
      claims.iss !== ISSUER ||
      !audiences.includes(clientId) ||
      !Number.isFinite(claims.exp) || claims.exp <= now ||
      !Number.isFinite(claims.iat) || claims.iat > now + 5 ||
      !validNotBefore ||
      (audiences.length > 1 && claims.azp !== clientId) ||
      typeof claims.sub !== "string" || !claims.sub
    ) {
      throw new Error("OpenAI identity token claims are invalid.");
    }
    if (nonce && !safeEqual(claims.nonce || "", nonce)) {
      throw new Error("OpenAI sign-in nonce validation failed.");
    }
    if (expectedSubject && claims.sub !== expectedSubject) {
      throw new Error("The ChatGPT account changed during reauthorization.");
    }
    return claims;
  }

  async _authorize(existingAccount, pendingRegistration = null) {
    const store = await this._readStore();
    const state = encodeBase64Url(crypto.randomBytes(32));
    const nonce = encodeBase64Url(crypto.randomBytes(32));
    const verifier = encodeBase64Url(crypto.randomBytes(48));
    const challenge = encodeBase64Url(crypto.createHash("sha256").update(verifier).digest());
    const expectedClientId = existingAccount?.client_id || pendingRegistration?.client_id || null;
    let callbackSettled = false;
    let callbackTimer;

    const callbackServer = http.createServer(async (request, response) => {
      const remote = request.socket.remoteAddress || "";
      const url = new URL(request.url || "/", "http://127.0.0.1");
      if (request.method !== "GET" || url.pathname !== "/auth/callback" || !loopbackAddress(remote)) {
        response.writeHead(404, { "content-type": "text/plain; charset=utf-8" });
        response.end("Not found");
        return;
      }
      if (callbackSettled) {
        response.writeHead(409, { "content-type": "text/plain; charset=utf-8" });
        response.end("This sign-in attempt is already complete.");
        return;
      }
      if (!safeEqual(url.searchParams.get("state") || "", state)) {
        callbackSettled = true;
        response.writeHead(400, { "content-type": "text/plain; charset=utf-8" });
        response.end("Sign-in state validation failed. Close this page and retry in AverQel.");
        callbackServer.emit("codex-auth-result", new Error("OpenAI sign-in state validation failed."));
        return;
      }
      const oauthError = url.searchParams.get("error");
      if (oauthError) {
        callbackSettled = true;
        response.writeHead(200, { "content-type": "text/html; charset=utf-8" });
        response.end("<!doctype html><title>AverQel</title><p>Sign-in was not completed. You can close this page and return to AverQel.</p>");
        callbackServer.emit(
          "codex-auth-result",
          new Error(oauthError === "access_denied" ? "ChatGPT plan access was not authorized." : "OpenAI sign-in was not completed."),
        );
        return;
      }
      const code = url.searchParams.get("code");
      const callbackClientId = url.searchParams.get("client_id");
      const clientId = expectedClientId || callbackClientId;
      if (
        !code || !clientId ||
        !SAFE_CLIENT_ID.test(clientId) ||
        (!expectedClientId && clientId === "dynamic_agent_client") ||
        (expectedClientId && callbackClientId && callbackClientId !== expectedClientId)
      ) {
        callbackSettled = true;
        response.writeHead(400, { "content-type": "text/plain; charset=utf-8" });
        response.end("OpenAI did not complete the account registration. Close this page and retry.");
        callbackServer.emit("codex-auth-result", new Error("OpenAI sign-in returned an incomplete registration."));
        return;
      }
      callbackSettled = true;
      response.writeHead(200, { "content-type": "text/html; charset=utf-8" });
      response.end("<!doctype html><title>AverQel</title><p>ChatGPT sign-in is complete. Return to AverQel.</p>");
      callbackServer.emit("codex-auth-result", { code, clientId, redirectUri });
    });

    const callbackResult = new Promise((resolve, reject) => {
      callbackServer.once("codex-auth-result", (result) => {
        if (result instanceof Error) reject(result);
        else resolve(result);
      });
      callbackTimer = setTimeout(() => {
        if (callbackSettled) return;
        callbackSettled = true;
        reject(new Error("ChatGPT sign-in timed out. Start sign-in again."));
      }, 5 * 60_000);
    });

    let redirectUri;
    try {
      await new Promise((resolve, reject) => {
        callbackServer.once("error", reject);
        callbackServer.listen(0, "127.0.0.1", resolve);
      });
      const address = callbackServer.address();
      if (!address || typeof address === "string") throw new Error("Local sign-in callback did not start.");
      redirectUri = `http://127.0.0.1:${address.port}/auth/callback`;
      const authorizationUrl = new URL(`${ISSUER}/api/accounts/authorize`);
      const params = authorizationUrl.searchParams;
      params.set("client_id", expectedClientId || "dynamic_agent_client");
      if (!expectedClientId) params.set("agent_name_hint", "AverQel");
      params.set("ext_agent_host_id", store.hostId);
      if (existingAccount?.id_token) params.set("id_token_hint", existingAccount.id_token);
      if (existingAccount?.email) params.set("login_hint", existingAccount.email);
      if (existingAccount?.needs_consent || pendingRegistration?.needs_consent) {
        params.set("prompt", "consent");
      }
      params.set("response_type", "code");
      params.set("redirect_uri", redirectUri);
      params.set("scope", REQUIRED_SCOPES.join(" "));
      params.set("resource", RESOURCE);
      params.set("state", state);
      params.set("nonce", nonce);
      params.set("code_challenge_method", "S256");
      params.set("code_challenge", challenge);
      await this.shell.openExternal(authorizationUrl.toString());
      const result = await callbackResult;
      if (!existingAccount) {
        await this._updateStore((currentStore) => {
          if (!currentStore.pendingRegistrations.some((entry) => entry.client_id === result.clientId)) {
            currentStore.pendingRegistrations.push({
              client_id: result.clientId,
              created_at: new Date().toISOString(),
            });
          }
        });
      }
      const form = new URLSearchParams({
        grant_type: "authorization_code",
        client_id: result.clientId,
        code: result.code,
        code_verifier: verifier,
        redirect_uri: result.redirectUri,
        resource: RESOURCE,
      });
      const tokenResponse = await this.fetchImpl(TOKEN_ENDPOINT, {
        method: "POST",
        headers: { "content-type": "application/x-www-form-urlencoded", accept: "application/json" },
        body: form,
        signal: AbortSignal.timeout(20_000),
      });
      const token = await tokenResponse.json().catch(() => ({}));
      if (!tokenResponse.ok) {
        const detail = typeof token.error_description === "string" ? token.error_description : "OpenAI rejected the authorization code.";
        throw new Error(detail.slice(0, 240));
      }
      if (
        typeof token.access_token !== "string" ||
        typeof token.refresh_token !== "string" ||
        typeof token.id_token !== "string" ||
        !Number.isFinite(token.expires_in)
      ) {
        throw new Error("OpenAI returned an incomplete token response.");
      }
      const scopes = String(token.scope || "").split(/\s+/).filter(Boolean);
      if (!REQUIRED_SCOPES.every((scope) => scopes.includes(scope))) {
        await this._updateStore((currentStore) => {
          if (existingAccount) {
            const existingIndex = currentStore.accounts.findIndex((item) => item.id === existingAccount.id);
            if (existingIndex >= 0) {
              currentStore.accounts[existingIndex] = {
                ...currentStore.accounts[existingIndex],
                needs_consent: true,
              };
            }
          } else {
            const pending = currentStore.pendingRegistrations.find(
              (item) => item.client_id === result.clientId,
            );
            if (pending) pending.needs_consent = true;
          }
        });
        throw new Error(
          "ChatGPT plan usage permission was not granted. Continue with ChatGPT again and approve model usage.",
        );
      }
      const claims = await this._validateIdToken(token.id_token, {
        clientId: result.clientId,
        nonce,
        expectedSubject: existingAccount?.subject,
      });
      const accountId = crypto
        .createHash("sha256")
        .update(`${claims.iss}\0${claims.sub}\0${result.clientId}`)
        .digest("hex")
        .slice(0, 32);
      const nextAccount = {
        id: accountId,
        issuer: claims.iss,
        subject: claims.sub,
        email: typeof claims.email === "string" ? claims.email : null,
        name: typeof claims.name === "string" ? claims.name : null,
        client_id: result.clientId,
        host_id: store.hostId,
        needs_consent: false,
        id_token: token.id_token,
        access_token: token.access_token,
        refresh_token: token.refresh_token,
        token_type: "Bearer",
        scopes,
        expires_at: Date.now() + Number(token.expires_in) * 1000,
      };
      await this._updateStore((currentStore) => {
        const existingIndex = currentStore.accounts.findIndex((item) => item.id === accountId);
        if (existingIndex >= 0) currentStore.accounts[existingIndex] = nextAccount;
        else currentStore.accounts.push(nextAccount);
        currentStore.pendingRegistrations = currentStore.pendingRegistrations.filter(
          (item) => item.client_id !== result.clientId,
        );
      });
      return publicAccount(nextAccount);
    } finally {
      clearTimeout(callbackTimer);
      if (callbackServer.listening) await new Promise((resolve) => callbackServer.close(resolve));
    }
  }

  async connect(accountId, source = null) {
    if (source === "codex_cli") {
      if (!accountId) throw new Error("Select the signed-in Codex CLI account first.");
      return this._connectCodexCli(accountId);
    }
    if (source !== "chatgpt" && accountId) {
      const cli = await this._codexCliStatus();
      if (cli.method === "chatgpt" && cli.accountId === accountId) {
        return this._connectCodexCli(accountId);
      }
    }
    if (this.connectOperation) {
      throw new Error("A ChatGPT sign-in is already in progress in this AverQel window.");
    }
    const operation = (async () => {
      const store = await this._readStore();
      const existing = accountId ? await this._account(accountId, store) : null;
      const pending = !existing ? store.pendingRegistrations.at(-1) || null : null;
      const account = await this._authorize(existing, pending);
      try {
        const models = await this.models(account.id);
        return { account, models };
      } catch (error) {
        return {
          account,
          models: [],
          modelError: error instanceof Error ? error.message : "The account model list could not be loaded.",
        };
      }
    })();
    this.connectOperation = operation;
    try {
      return await operation;
    } finally {
      if (this.connectOperation === operation) this.connectOperation = null;
    }
  }

  async _refresh(accountId) {
    const active = this.refreshes.get(accountId);
    if (active) return active;
    const operation = (async () => {
      const store = await this._readStore();
      const account = await this._account(accountId, store);
      const body = new URLSearchParams({
        grant_type: "refresh_token",
        client_id: account.client_id,
        refresh_token: account.refresh_token,
        resource: RESOURCE,
      });
      const response = await this.fetchImpl(TOKEN_ENDPOINT, {
        method: "POST",
        headers: { "content-type": "application/x-www-form-urlencoded", accept: "application/json" },
        body,
        signal: AbortSignal.timeout(20_000),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || typeof payload.access_token !== "string") {
        throw new Error("ChatGPT session expired. Sign in again to use this provider.");
      }
      const scopes = String(payload.scope || account.scopes.join(" ")).split(/\s+/).filter(Boolean);
      if (!scopes.includes("chatgpt.tokens.use.direct")) {
        throw new Error("ChatGPT plan model access is no longer authorized. Sign in again.");
      }
      const refreshedClaims = payload.id_token
        ? await this._validateIdToken(payload.id_token, {
            clientId: account.client_id,
            expectedSubject: account.subject,
          })
        : null;
      const updated = {
        ...account,
        ...(typeof payload.refresh_token === "string" ? { refresh_token: payload.refresh_token } : {}),
        ...(typeof payload.id_token === "string" ? { id_token: payload.id_token } : {}),
        ...(refreshedClaims && typeof refreshedClaims.email === "string" ? { email: refreshedClaims.email } : {}),
        access_token: payload.access_token,
        scopes,
        expires_at: Date.now() + (Number(payload.expires_in) || 3600) * 1000,
      };
      await this._updateStore((currentStore) => {
        const accountIndex = currentStore.accounts.findIndex((item) => item.id === accountId);
        if (accountIndex < 0) {
          throw new Error("The selected ChatGPT account was removed during token refresh.");
        }
        currentStore.accounts[accountIndex] = updated;
      });
      return updated.access_token;
    })();
    this.refreshes.set(accountId, operation);
    try {
      return await operation;
    } finally {
      this.refreshes.delete(accountId);
    }
  }

  async _accessToken(accountId) {
    const store = await this._readStore();
    const account = await this._account(accountId, store);
    if (!account.scopes.includes("chatgpt.tokens.use.direct")) {
      throw new Error("This ChatGPT account is not authorized for model usage.");
    }
    if (account.expires_at > Date.now() + 60_000) return account.access_token;
    return this._refresh(accountId);
  }

  async models(accountId) {
    const cachedCli = this.cliStatusCache?.value;
    const cli = accountId && cachedCli?.accountId === accountId
      ? cachedCli
      : await this._codexCliStatus();
    if (accountId && cli.method === "chatgpt" && accountId === cli.accountId) {
      const { models } = await this._loadCodexCliSession(accountId);
      return models;
    }
    const token = await this._accessToken(accountId);
    const response = await this.fetchImpl(`${RESOURCE}/models`, {
      headers: { authorization: `Bearer ${token}`, accept: "application/json" },
      signal: AbortSignal.timeout(20_000),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error("OpenAI could not load models for this ChatGPT account.");
    }
    if (!Array.isArray(payload.models)) throw new Error("OpenAI returned an invalid account model list.");
    const models = payload.models
      .filter((model) => model && model.visibility === "list" && typeof model.slug === "string")
      .map((model) => {
        const advertisedEfforts = advertisedBrowserEfforts(model);
        return {
          id: model.slug.slice(0, 255),
          name: (typeof model.display_name === "string" && model.display_name.trim())
            ? model.display_name.trim().slice(0, 255)
            : model.slug.slice(0, 255),
          kind: "chat",
          ...(advertisedEfforts ? {
            supportedReasoningEfforts: advertisedEfforts.efforts,
            reasoningEffortValues: advertisedEfforts.effortValues,
          } : {}),
        };
      })
      .filter((model, index, items) => items.findIndex((other) => other.id === model.id) === index);
    if (models.length === 0) throw new Error("No ChatGPT plan models are available for this account.");
    return models;
  }

  async disconnect(accountId) {
    const store = await this._readStore();
    const account = await this._account(accountId, store);
    for (const stream of this.streams.values()) {
      if (stream.accountId === accountId) stream.controller.abort();
    }
    let revocationConfirmed = false;
    try {
      const config = await this._getOidcConfig();
      if (typeof config.revocation_endpoint === "string" && config.revocation_endpoint.startsWith(`${ISSUER}/`)) {
        const body = new URLSearchParams({
          token: account.refresh_token,
          token_type_hint: "refresh_token",
          client_id: account.client_id,
        });
        const response = await this.fetchImpl(config.revocation_endpoint, {
          method: "POST",
          headers: { "content-type": "application/x-www-form-urlencoded" },
          body,
          signal: AbortSignal.timeout(10_000),
        });
        revocationConfirmed = response.ok;
      }
    } catch {
      // Local removal is authoritative for this device even when revocation is unavailable.
    }
    await this._updateStore((currentStore) => {
      currentStore.accounts = currentStore.accounts.filter((item) => item.id !== accountId);
    });
    return { revoked: revocationConfirmed };
  }

  async startStream({ streamId, accountId, request }) {
    if (typeof streamId !== "string" || !/^[0-9a-f-]{36}$/i.test(streamId)) {
      throw new Error("Invalid Codex stream identifier.");
    }
    if (this.streams.has(streamId)) throw new Error("Codex stream is already active.");
    if (this.streams.size >= MAX_CONCURRENT_STREAMS) {
      throw new Error("Too many Codex requests are already running on this desktop.");
    }
    const controller = new AbortController();
    this.streams.set(streamId, { controller, accountId });
    const cli = await this._codexCliStatus();
    const stream = accountId === cli.accountId && cli.method === "chatgpt"
      ? this._streamCodexCli({ streamId, accountId, request, signal: controller.signal })
      : this._streamResponses({ streamId, accountId, request, signal: controller.signal });
    void stream
      .catch((error) => {
        if (controller.signal.aborted) return;
        const details = error && typeof error === "object" ? error : {};
        this.emit(streamId, {
          kind: "error",
          message: error instanceof Error ? error.message : "Codex request failed.",
          ...(Number.isInteger(details.statusCode) ? { httpStatus: details.statusCode } : {}),
          ...(typeof details.code === "string" && SAFE_ERROR_CODE.test(details.code) ? { code: details.code } : {}),
          ...(typeof details.param === "string" ? { param: details.param.slice(0, 96) } : {}),
          ...(typeof details.requestId === "string" && SAFE_REQUEST_ID.test(details.requestId)
            ? { requestId: details.requestId }
            : {}),
        });
      })
      .finally(() => {
        this.streams.delete(streamId);
        this.emit(streamId, { kind: "closed" });
      });
    return { started: true };
  }

  cancelStream(streamId) {
    this.streams.get(streamId)?.controller.abort();
    return true;
  }

  cancelAllStreams() {
    for (const stream of this.streams.values()) stream.controller.abort();
    this.streams.clear();
  }

  async _streamResponses({ streamId, accountId, request, signal }) {
    if (!request || typeof request !== "object" || !/^[\w./:-]{1,255}$/.test(request.model || "")) {
      throw new Error("Codex request has an invalid model.");
    }
    if (!Array.isArray(request.input) || request.input.length === 0 || request.input.length > 256) {
      throw new Error("Codex request has invalid conversation input.");
    }
    const body = {
      model: request.model,
      input: request.input,
      store: false,
      stream: true,
    };
    if (typeof request.instructions === "string" && request.instructions.length <= 32_000) {
      body.instructions = request.instructions;
    }
    if (
      request.reasoning &&
      typeof request.reasoning.effort === "string" &&
      SAFE_CODEX_REASONING_EFFORT.test(request.reasoning.effort)
    ) {
      body.reasoning = { effort: request.reasoning.effort };
    }
    if (Array.isArray(request.tools) && request.tools.length <= 128) body.tools = request.tools;
    if (request.tool_choice && ["auto", "required", "none"].includes(request.tool_choice)) {
      body.tool_choice = request.tool_choice;
    }
    let serializedBody = JSON.stringify(body);
    if (Buffer.byteLength(serializedBody, "utf8") > MAX_INFERENCE_BODY_BYTES) {
      throw new Error("Codex request exceeds the maximum supported size.");
    }
    const token = await this._accessToken(accountId);
    let response;
    try {
      response = await this.fetchImpl(`${RESOURCE}/responses`, {
        method: "POST",
        headers: {
          authorization: `Bearer ${token}`,
          "content-type": "application/json",
          accept: "text/event-stream",
        },
        body: serializedBody,
        signal,
      });
    } finally {
      serializedBody = null;
      body.input = [];
      request.input = [];
    }
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      const apiError = payload?.error && typeof payload.error === "object" ? payload.error : {};
      const detailMessage = typeof payload?.detail === "string" ? payload.detail : null;
      const message = typeof apiError.message === "string"
        ? apiError.message.slice(0, 500)
        : detailMessage
          ? detailMessage.slice(0, 500)
        : `OpenAI Responses request failed with HTTP ${response.status}.`;
      const error = new Error(message);
      error.statusCode = response.status;
      if (typeof apiError.code === "string" && SAFE_ERROR_CODE.test(apiError.code)) {
        error.code = apiError.code;
      }
      if (typeof apiError.param === "string") error.param = apiError.param.slice(0, 96);
      const requestId = response.headers.get("x-request-id") || response.headers.get("openai-request-id");
      if (requestId && SAFE_REQUEST_ID.test(requestId)) error.requestId = requestId;
      throw error;
    }
    if (!response.body) throw new Error("OpenAI did not return a response stream.");
    const decoder = new TextDecoder();
    let pending = "";
    let completed = false;
    const emitSseBlock = (block) => {
      let data = "";
      for (const line of block.split(/\r?\n/)) {
        if (line.startsWith("data:")) data += `${line.slice(5).trimStart()}\n`;
      }
      if (!data.trim() || data.trim() === "[DONE]") return;
      let event;
      try {
        event = JSON.parse(data);
      } catch {
        throw new Error("OpenAI returned an invalid stream event.");
      }
      if (!event || typeof event.type !== "string" || !SAFE_RESPONSE_EVENTS.has(event.type)) return;
      const safe = { type: event.type };
      if (typeof event.delta === "string") safe.delta = event.delta;
      if (Number.isInteger(event.output_index)) safe.output_index = event.output_index;
      if (event.item && typeof event.item === "object" && event.item.type === "function_call") {
        safe.item = {
          type: "function_call",
          ...(typeof event.item.id === "string" ? { id: event.item.id } : {}),
          ...(typeof event.item.call_id === "string" ? { call_id: event.item.call_id } : {}),
          ...(typeof event.item.name === "string" ? { name: event.item.name } : {}),
          ...(typeof event.item.arguments === "string" ? { arguments: event.item.arguments } : {}),
        };
      }
      if (typeof event.arguments === "string") safe.arguments = event.arguments;
      if (event.type === "response.completed") {
        completed = true;
        if (event.response?.usage && typeof event.response.usage === "object") {
          safe.usage = {
            input_tokens: Number(event.response.usage.input_tokens) || 0,
            output_tokens: Number(event.response.usage.output_tokens) || 0,
            total_tokens: Number(event.response.usage.total_tokens) || 0,
          };
        }
      }
      if (
        event.type === "response.failed" ||
        event.type === "response.incomplete" ||
        event.type === "error"
      ) {
        const requestId = response.headers.get("x-request-id") || response.headers.get("openai-request-id");
        if (requestId && SAFE_REQUEST_ID.test(requestId)) safe.request_id = requestId;
      }
      if (event.type === "response.failed" || event.type === "error") {
        const responseError = event.response?.error || event.error || {};
        const message = responseError.message;
        safe.error = {
          ...(typeof responseError.code === "string" && SAFE_ERROR_CODE.test(responseError.code)
            ? { code: responseError.code }
            : {}),
          ...(typeof responseError.param === "string" ? { param: responseError.param.slice(0, 96) } : {}),
          message: typeof message === "string" ? message.slice(0, 500) : "OpenAI Responses request failed.",
        };
      }
      if (event.type === "response.incomplete") {
        safe.error = { message: "OpenAI Responses returned an incomplete response." };
      }
      this.emit(streamId, { kind: "event", event: safe });
    };
    for await (const chunk of response.body) {
      pending += decoder.decode(chunk, { stream: true });
      let boundary = pending.search(/\r?\n\r?\n/);
      while (boundary >= 0) {
        const block = pending.slice(0, boundary);
        const separator = pending.slice(boundary).match(/^\r?\n\r?\n/);
        pending = pending.slice(boundary + (separator?.[0].length || 2));
        emitSseBlock(block);
        boundary = pending.search(/\r?\n\r?\n/);
      }
      if (pending.length > 1_000_000) throw new Error("OpenAI returned an oversized stream event.");
    }
    pending += decoder.decode();
    if (pending.trim()) emitSseBlock(pending);
    if (!signal.aborted && !completed) {
      throw new Error("OpenAI response stream ended before response.completed.");
    }
  }

  async _streamCodexCli({ streamId, accountId, request, signal }) {
    if (!request || typeof request !== "object" || !/^[\w./:-]{1,255}$/.test(request.model || "")) {
      throw new Error("Codex request has an invalid model.");
    }
    if (!Array.isArray(request.input) || request.input.length === 0 || request.input.length > 256) {
      throw new Error("Codex request has invalid conversation input.");
    }
    const cli = await this._codexCliStatus();
    if (cli.method !== "chatgpt" || cli.accountId !== accountId || !cli.executable) {
      throw new Error("The Codex CLI ChatGPT login is no longer available. Sign in again and retry.");
    }

    const { input, images } = codexCliInput(request.input);
    const dynamicTools = request.tool_choice === "none" ? [] : codexCliDynamicTools(request.tools);
    const byteLength = Buffer.byteLength(JSON.stringify({ input, images, dynamicTools }), "utf8");
    if (byteLength > MAX_INFERENCE_BODY_BYTES) {
      throw new Error("Codex request exceeds the maximum supported size.");
    }
    if (signal.aborted) return;

    const scratchDirectory = await mkdtemp(path.join(this.app.getPath("temp"), "averqel-codex-"));
    await chmod(scratchDirectory, 0o700).catch(() => undefined);
    let client;
    let threadId = null;
    let settled = false;
    let delegatedToolCall = false;
    let resolveTurn;
    let timeout;
    const turnResult = new Promise((resolve) => {
      resolveTurn = resolve;
    });
    const finishTurn = (result) => {
      if (settled) return;
      settled = true;
      clearTimeout(timeout);
      resolveTurn(result);
    };
    const onAbort = () => {
      client?.close();
      finishTurn({ kind: "aborted" });
    };
    signal.addEventListener("abort", onAbort, { once: true });
    timeout = setTimeout(() => finishTurn({ kind: "error" }), 300_000);

    const allowedToolNames = new Set(
      dynamicTools.flatMap((namespace) => namespace.tools.map((tool) => tool.name)),
    );
    client = this._newCodexAppServer(cli.executable, (message) => {
      if (message.method === "item/tool/call") {
        const params = message.params || {};
        const toolName = typeof params.tool === "string" ? params.tool : "";
        if (!allowedToolNames.has(toolName)) {
          return {
            success: false,
            contentItems: [{ type: "inputText", text: "This tool is not available to AverQel." }],
          };
        }
        const argumentsText = typeof params.arguments === "string"
          ? params.arguments
          : JSON.stringify(params.arguments ?? {});
        delegatedToolCall = true;
        const callId = typeof params.callId === "string" && SAFE_REQUEST_ID.test(params.callId)
          ? params.callId
          : crypto.randomUUID();
        this.emit(streamId, {
          kind: "event",
          event: {
            type: "response.output_item.added",
            output_index: 0,
            item: {
              type: "function_call",
              id: callId,
              call_id: callId,
              name: toolName,
              arguments: "",
            },
          },
        });
        this.emit(streamId, {
          kind: "event",
          event: {
            type: "response.function_call_arguments.done",
            output_index: 0,
            arguments: argumentsText,
          },
        });
        this.emit(streamId, { kind: "event", event: { type: "response.completed" } });
        finishTurn({ kind: "tool_call" });
        return {
          success: false,
          contentItems: [{ type: "inputText", text: "AverQel will handle this function call." }],
        };
      }
      if (
        message.method === "item/commandExecution/requestApproval" ||
        message.method === "item/fileChange/requestApproval"
      ) {
        return { decision: "decline" };
      }
      if (message.method === "item/permissions/requestApproval") {
        return { decision: "decline" };
      }
      return {};
    }, undefined, scratchDirectory);

    const unsubscribe = client.onNotification((method, params) => {
      if (method === "item/agentMessage/delta" && typeof params.delta === "string") {
        this.emit(streamId, {
          kind: "event",
          event: { type: "response.output_text.delta", delta: params.delta, output_index: 0 },
        });
      } else if (method === "turn/completed") {
        if (
          params.turn?.status === "completed" &&
          !(request.tool_choice === "required" && dynamicTools.length && !delegatedToolCall)
        ) {
          this.emit(streamId, { kind: "event", event: { type: "response.completed" } });
          finishTurn({ kind: "completed" });
        } else {
          finishTurn({ kind: "error" });
        }
      }
    });

    try {
      await client.start();
      await this._readCodexCliAccount(client, scratchDirectory);
      const developerInstructions = [
        "This AverQel request is for model inference. Do not use local files, shell commands, network tools, MCP servers, or other Codex runtime tools. Use only the supplied AverQel function tools when a function is needed.",
        ...(request.tool_choice === "required" && dynamicTools.length
          ? ["You must call one of the supplied AverQel function tools before returning a final answer."]
          : []),
        typeof request.instructions === "string" ? request.instructions.slice(0, 32_000) : "",
      ].filter(Boolean).join("\n\n");
      const startParams = {
        model: request.model,
        modelProvider: "openai",
        cwd: scratchDirectory,
        permissions: CODEX_CLI_PERMISSION_PROFILE,
        approvalPolicy: "on-request",
        ephemeral: true,
        allowProviderModelFallback: false,
        developerInstructions,
        dynamicTools,
      };
      const thread = await client.request("thread/start", startParams);
      if (thread?.activePermissionProfile?.id !== CODEX_CLI_PERMISSION_PROFILE) {
        throw new Error("Codex CLI did not activate AverQel's restricted inference profile.");
      }
      threadId = thread?.thread?.id;
      if (typeof threadId !== "string" || !threadId) {
        throw new Error("Codex CLI did not start a model thread.");
      }
      const turnParams = {
        threadId,
        model: request.model,
        cwd: scratchDirectory,
        permissions: CODEX_CLI_PERMISSION_PROFILE,
        runtimeWorkspaceRoots: [scratchDirectory],
        approvalPolicy: "on-request",
        input: [
          { type: "text", text: input },
          ...images.map((url) => ({ type: "image", url })),
        ],
        ...(request.reasoning?.effort && request.reasoning.effort !== "none"
          ? { effort: request.reasoning.effort }
          : {}),
      };
      await client.request("turn/start", turnParams);
      const result = await turnResult;
      if (result.kind === "error") {
        throw new Error("Codex CLI could not complete this model request. Check the CLI login and model access, then retry.");
      }
    } finally {
      clearTimeout(timeout);
      signal.removeEventListener("abort", onAbort);
      unsubscribe();
      client.close();
      await rm(scratchDirectory, { recursive: true, force: true }).catch(() => undefined);
    }
  }
}

module.exports = { CodexDesktopRuntime };
