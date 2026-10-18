const assert = require("node:assert/strict");
const { EventEmitter } = require("node:events");
const { PassThrough, Readable, Writable } = require("node:stream");
const { mkdtemp, rm } = require("node:fs/promises");
const test = require("node:test");
const os = require("node:os");
const path = require("node:path");

const {
  CodexAppServerClient,
  classifyCodexLoginStatus,
  createRestrictedCodexCliAppServerArgs,
  resolveCodexExecutable,
  runCodexLoginStatus,
} = require("../electron/codex-cli.cjs");
const { CodexDesktopRuntime } = require("../electron/codex-runtime.cjs");

test("finds Codex from PATH without looking through credential files", () => {
  const candidates = new Set([path.resolve("/second/codex")]);
  const result = resolveCodexExecutable({
    env: { PATH: "/first:/second" },
    platform: "linux",
    home: "/user",
    exists: (candidate) => candidates.has(candidate),
    isExecutable: () => true,
    readDirectory: () => [],
  });

  assert.equal(result, path.resolve("/second/codex"));
});

test("login status distinguishes ChatGPT login from API-key billing", () => {
  assert.equal(classifyCodexLoginStatus(0, "Logged in using ChatGPT"), "chatgpt");
  assert.equal(classifyCodexLoginStatus(0, "Logged in using API key"), "api_key");
  assert.equal(classifyCodexLoginStatus(0, "Logged in using an API key"), "api_key");
  assert.equal(classifyCodexLoginStatus(0, "Logged in using workload identity"), "other_authenticated_method");
  assert.equal(classifyCodexLoginStatus(1, "Not logged in"), "not_authenticated");
  assert.equal(classifyCodexLoginStatus(1, "Unexpected CLI failure"), "unavailable");
  assert.equal(classifyCodexLoginStatus(null, ""), "unavailable");
});

test("runs CLI login status without a shell and returns only the authentication method", async () => {
  const child = new EventEmitter();
  child.stdout = new PassThrough();
  child.stderr = new PassThrough();
  child.kill = () => {};
  let invocation;
  const result = runCodexLoginStatus("/opt/codex", {
    platform: "linux",
    env: { PATH: "/opt", OPENAI_API_KEY: "api-secret", REGISTRY_TOKEN: "registry-secret" },
    spawnProcess: (command, args, options) => {
      invocation = { command, args, options };
      process.nextTick(() => {
        child.stderr.write("Logged in using ChatGPT\nprivate@example.test\n");
        child.emit("close", 0);
      });
      return child;
    },
  });

  assert.deepEqual(await result, { method: "chatgpt" });
  assert.equal(invocation.command, "/opt/codex");
  assert.deepEqual(invocation.args, ["login", "status"]);
  assert.equal(invocation.options.cwd, os.tmpdir());
  assert.equal(invocation.options.env.PATH, "/opt");
  assert.equal(invocation.options.env.OPENAI_API_KEY, undefined);
  assert.equal(invocation.options.env.REGISTRY_TOKEN, undefined);
  assert.equal(invocation.options.shell, false);
  assert.equal(invocation.options.stdio[0], "ignore");
  assert.equal(invocation.options.stdio[2], "pipe");
});

test("reports a CLI launch failure as unavailable instead of an unauthenticated account", async () => {
  const child = new EventEmitter();
  child.stdout = new PassThrough();
  child.stderr = new PassThrough();
  child.kill = () => {};
  const result = runCodexLoginStatus("/opt/codex", {
    env: {},
    platform: "linux",
    spawnProcess: () => {
      process.nextTick(() => child.emit("error", new Error("launch failed")));
      return child;
    },
  });

  assert.deepEqual(await result, { method: "unavailable" });
});

test("uses the Codex app-server protocol over stdio and keeps login data out of its public result", async () => {
  const requests = [];
  const spawnProcess = (command, args, options) => {
    assert.equal(command, "/opt/codex");
    assert.equal(args[0], "app-server");
    assert.equal(options.shell, false);
    assert.equal(options.cwd, os.tmpdir());
    assert.equal(options.env.PATH, "/usr/bin");
    assert.equal(options.env.OPENAI_API_KEY, undefined);
    assert.equal(options.env.GITHUB_TOKEN, undefined);
    const child = new EventEmitter();
    child.stdout = new PassThrough();
    child.stdin = new Writable({
      write(chunk, _encoding, callback) {
        const request = JSON.parse(chunk.toString("utf8"));
        requests.push(request);
        if (request.id) {
          const result = request.method === "account/read"
            ? { account: { type: "chatgpt", email: "private@example.test", planType: "plus" } }
            : {};
          process.nextTick(() => child.stdout.write(`${JSON.stringify({ id: request.id, result })}\n`));
        }
        callback();
      },
    });
    child.kill = () => child.emit("close", 0);
    return child;
  };
  const client = new CodexAppServerClient({
    executable: "/opt/codex",
    env: { PATH: "/usr/bin", OPENAI_API_KEY: "api-secret", GITHUB_TOKEN: "github-secret" },
    spawnProcess,
  });
  await client.start();
  const account = await client.request("account/read", { refreshToken: false });
  client.close();

  assert.equal(account.account.email, "private@example.test");
  assert.ok(requests.some((request) => request.method === "initialize"));
  assert.ok(requests.some((request) => request.method === "initialize" && request.params.capabilities?.experimentalApi === true));
  assert.ok(requests.some((request) => request.method === "initialized"));
  assert.ok(requests.some((request) => request.method === "account/read"));
  const args = createRestrictedCodexCliAppServerArgs();
  assert.ok(!args.some((argument) => argument.startsWith("model_provider=")));
  assert.ok(!args.some((argument) => argument.includes("model_providers.")));
  assert.ok(args.includes("default_permissions='averqel_chatgpt_plan_v1'"));
  assert.ok(args.includes("permissions.averqel_chatgpt_plan_v1.filesystem={':root'='deny',':minimal'='read'}"));
  assert.ok(args.includes("features.shell_tool=false"));
  assert.ok(args.includes("features.multi_agent=false"));
  assert.ok(args.includes("features.hooks=false"));
  assert.ok(args.includes("project_doc_max_bytes=0"));
  assert.ok(args.includes("history.persistence='none'"));
  assert.ok(args.includes("web_search='disabled'"));
  assert.ok(args.includes("mcp_servers={}"));
  assert.ok(!args.some((argument) => /access_token|refresh_token/i.test(argument)));
});

function createFakeAppServer({
  onTurnStart,
  instances,
  permissionProfileAllowed = true,
  activePermissionProfileId = "averqel_chatgpt_plan_v1",
}) {
  return class FakeAppServer {
    constructor(options) {
      const { onServerRequest } = options;
      this.onServerRequest = onServerRequest;
      this.notifications = new Set();
      this.closed = false;
      this.requests = [];
      this.calls = [];
      instances.push({ ...options, requests: this.requests, calls: this.calls });
    }

    async start() {}

    onNotification(handler) {
      this.notifications.add(handler);
      return () => this.notifications.delete(handler);
    }

    async request(method, params) {
      this.requests.push(method);
      this.calls.push({ method, params });
      if (method === "permissionProfile/list") {
        return {
          data: [{ id: "averqel_chatgpt_plan_v1", allowed: permissionProfileAllowed }],
        };
      }
      if (method === "account/read") {
        return { account: { type: "chatgpt", email: "private@example.test", planType: "plus" } };
      }
      if (method === "model/list") {
        return {
          data: [
            {
              id: "gpt-5-codex",
              model: "gpt-5-codex",
              displayName: "GPT-5 Codex",
              hidden: false,
              supportedReasoningEfforts: [
                { reasoningEffort: "minimal", description: "Minimal" },
                { reasoningEffort: "low", description: "Low" },
                { reasoningEffort: "medium", description: "Medium" },
                { reasoningEffort: "high", description: "High" },
                { reasoningEffort: "xhigh", description: "Extra high" },
                { reasoningEffort: "max", description: "Maximum" },
                { reasoningEffort: "ultra", description: "Ultra" },
                { reasoningEffort: "tier-5", description: "Vendor level" },
              ],
            },
            { id: "hidden-model", model: "hidden-model", displayName: "Hidden", hidden: true },
          ],
          nextCursor: null,
        };
      }
      if (method === "thread/start") {
        return {
          thread: { id: "thread-test" },
          activePermissionProfile: activePermissionProfileId ? { id: activePermissionProfileId } : null,
        };
      }
      if (method === "turn/start") {
        queueMicrotask(() => onTurnStart?.(this, params));
        return {};
      }
      return {};
    }

    emit(method, params) {
      for (const handler of this.notifications) handler(method, params);
    }

    close() {
      this.closed = true;
    }
  };
}

function createRuntime({
  onTurnStart,
  permissionProfileAllowed = true,
  activePermissionProfileId,
} = {}) {
  const frames = [];
  const appServerInstances = [];
  const runtime = new CodexDesktopRuntime({
    app: { getPath: () => os.tmpdir() },
    safeStorage: { isEncryptionAvailable: () => false },
    shell: {},
    emit: (_streamId, frame) => frames.push(frame),
    codexCli: {
      env: { PATH: "/opt" },
      home: "/test-home",
      platform: "linux",
      resolveExecutable: () => "/opt/codex",
      runLoginStatus: async () => ({ method: "chatgpt" }),
      AppServerClient: createFakeAppServer({
        onTurnStart,
        instances: appServerInstances,
        permissionProfileAllowed,
        activePermissionProfileId,
      }),
    },
  });
  return { runtime, frames, appServerInstances };
}

async function waitForClosed(frames) {
  for (let attempt = 0; attempt < 100; attempt += 1) {
    if (frames.some((frame) => frame.kind === "closed")) return;
    await new Promise((resolve) => setTimeout(resolve, 5));
  }
  assert.fail("Codex stream did not close");
}

test("detects a signed-in CLI account and streams a model response without storing its email", async () => {
  const { runtime, frames, appServerInstances } = createRuntime({
    onTurnStart: (client, params) => {
      assert.equal(appServerInstances.at(-1).cwd, params.cwd);
      assert.equal(path.dirname(params.cwd), os.tmpdir());
      assert.equal(params.permissions, "averqel_chatgpt_plan_v1");
      assert.equal(params.sandboxPolicy, undefined);
      client.emit("item/agentMessage/delta", { delta: "Hello from Codex." });
      client.emit("turn/completed", { turn: { status: "completed" } });
    },
  });
  const status = await runtime.status();
  assert.equal(status.available, true);
  assert.equal(status.chatgptSignInAvailable, false);
  assert.equal(status.accounts[0].source, "codex_cli");
  assert.equal(status.accounts[0].planType, "plus");
  assert.equal(status.accounts[0].email, null);

  const models = await runtime.models(status.accounts[0].id);
  assert.deepEqual(models.map((model) => model.id), ["gpt-5-codex"]);
  assert.deepEqual(models[0].supportedReasoningEfforts, [
    "minimal",
    "low",
    "medium",
    "high",
    "very_high",
    "extreme_high",
    "ultra",
    "tier_5",
  ]);
  assert.deepEqual(models[0].reasoningEffortValues, {
    minimal: "minimal",
    low: "low",
    medium: "medium",
    high: "high",
    very_high: "xhigh",
    extreme_high: "max",
    ultra: "ultra",
    tier_5: "tier-5",
  });
  assert.ok(appServerInstances.slice(0, 2).every((options) => options.cwd === os.tmpdir()));
  const start = await runtime.startStream({
    streamId: "123e4567-e89b-12d3-a456-426614174000",
    accountId: status.accounts[0].id,
    request: {
      model: "gpt-5-codex",
      input: [{ role: "user", content: [{ type: "input_text", text: "Hello" }] }],
      instructions: "Be concise.",
      reasoning: { effort: "tier-5" },
    },
  });
  assert.deepEqual(start, { started: true });
  await waitForClosed(frames);
  assert.ok(frames.some((frame) => frame.event?.type === "response.output_text.delta"));
  assert.ok(frames.some((frame) => frame.event?.type === "response.completed"));
  const cliCalls = appServerInstances.at(-1).calls;
  const threadStart = cliCalls.find((call) => call.method === "thread/start");
  const turnStart = cliCalls.find((call) => call.method === "turn/start");
  assert.ok(threadStart);
  assert.equal(threadStart.params.modelProvider, "openai");
  assert.equal(threadStart.params.permissions, "averqel_chatgpt_plan_v1");
  assert.equal(turnStart.params.effort, "tier-5");
});

test("passes the maximum reasoning value through the ChatGPT Responses route", async () => {
  let requestBody;
  const runtime = new CodexDesktopRuntime({
    app: { getPath: () => os.tmpdir() },
    safeStorage: { isEncryptionAvailable: () => false },
    shell: {},
    emit: () => {},
    fetchImpl: async (_url, options) => {
      requestBody = JSON.parse(options.body);
      return {
        ok: true,
        body: Readable.from([Buffer.from('data: {"type":"response.completed"}\n\n')]),
        headers: new Headers(),
      };
    },
  });
  runtime._accessToken = async () => "test-access-token";

  await runtime._streamResponses({
    streamId: "423e4567-e89b-12d3-a456-426614174000",
    accountId: "test-account",
    request: {
      model: "gpt-5.6-luna",
      input: [{ role: "user", content: [{ type: "input_text", text: "Reply OK" }] }],
      reasoning: { effort: "max" },
    },
    signal: new AbortController().signal,
  });

  assert.deepEqual(requestBody.reasoning, { effort: "max" });
  assert.equal(requestBody.store, false);
});

test("passes an advertised provider-specific effort through the ChatGPT Responses route", async () => {
  let requestBody;
  const runtime = new CodexDesktopRuntime({
    app: { getPath: () => os.tmpdir() },
    safeStorage: { isEncryptionAvailable: () => false },
    shell: {},
    emit: () => {},
    fetchImpl: async (_url, options) => {
      requestBody = JSON.parse(options.body);
      return {
        ok: true,
        body: Readable.from([Buffer.from('data: {"type":"response.completed"}\n\n')]),
        headers: new Headers(),
      };
    },
  });
  runtime._accessToken = async () => "test-access-token";

  await runtime._streamResponses({
    streamId: "523e4567-e89b-12d3-a456-426614174000",
    accountId: "test-account",
    request: {
      model: "gpt-account-model",
      input: [{ role: "user", content: [{ type: "input_text", text: "Reply OK" }] }],
      reasoning: { effort: "tier-five" },
    },
    signal: new AbortController().signal,
  });

  assert.deepEqual(requestBody.reasoning, { effort: "tier-five" });
});

test("preserves only reasoning levels present in a browser account model catalog", async () => {
  const runtime = new CodexDesktopRuntime({
    app: { getPath: () => os.tmpdir() },
    safeStorage: { isEncryptionAvailable: () => false },
    shell: {},
    emit: () => {},
    fetchImpl: async (_url, options) => {
      assert.equal(options.headers.authorization, "Bearer test-token");
      return {
        ok: true,
        json: async () => ({
          models: [
            {
              visibility: "list",
              slug: "gpt-account-catalog",
              supported_reasoning_efforts: ["minimal", "ultra", "tier-5"],
            },
            { visibility: "list", slug: "gpt-profile-only" },
          ],
        }),
      };
    },
  });
  runtime._codexCliStatus = async () => ({ method: "not_installed", accountId: null });
  runtime._accessToken = async () => "test-token";

  const models = await runtime.models("browser-account");

  assert.deepEqual(models[0].supportedReasoningEfforts, ["minimal", "ultra", "tier_5"]);
  assert.deepEqual(models[0].reasoningEffortValues, {
    minimal: "minimal",
    ultra: "ultra",
    tier_5: "tier-5",
  });
  assert.equal(models[1].supportedReasoningEfforts, undefined);
});

test("returns Codex CLI function calls to the existing AverQel tool handler", async () => {
  let delegatedResult;
  const { runtime, frames, appServerInstances } = createRuntime({
    onTurnStart: async (client) => {
      delegatedResult = await client.onServerRequest({
        id: 15,
        method: "item/tool/call",
        params: { callId: "call_test", namespace: "averqel", tool: "lookup", arguments: { query: "weather" } },
      });
    },
  });
  const status = await runtime.status();
  await runtime.startStream({
    streamId: "223e4567-e89b-12d3-a456-426614174000",
    accountId: status.accounts[0].id,
    request: {
      model: "gpt-5-codex",
      input: [{ role: "user", content: [{ type: "input_text", text: "Look up weather" }] }],
      tools: [{
        type: "namespace",
        name: "averqel",
        tools: [{ type: "function", name: "lookup", parameters: { type: "object", properties: { query: { type: "string" } } } }],
      }],
    },
  });
  await waitForClosed(frames);

  assert.equal(delegatedResult.success, false);
  assert.ok(frames.some((frame) => frame.event?.type === "response.output_item.added"));
  assert.ok(frames.some((frame) => frame.event?.type === "response.function_call_arguments.done"));
  assert.ok(frames.some((frame) => frame.event?.type === "response.completed"));
});

test("coalesces top-level function tools into one unique AverQel namespace", async () => {
  const { runtime, frames, appServerInstances } = createRuntime({
    onTurnStart: (client) => {
      client.emit("turn/completed", { turn: { status: "completed" } });
    },
  });
  const status = await runtime.status();

  await runtime.startStream({
    streamId: "323e4567-e89b-12d3-a456-426614174000",
    accountId: status.accounts[0].id,
    request: {
      model: "gpt-5-codex",
      input: [{ role: "user", content: [{ type: "input_text", text: "Search" }] }],
      tools: [
        { type: "function", name: "lookup", parameters: { type: "object", properties: {} } },
        { type: "function", name: "search", parameters: { type: "object", properties: {} } },
      ],
    },
  });
  await waitForClosed(frames);

  const threadStart = appServerInstances.at(-1).calls.find((call) => call.method === "thread/start");
  assert.deepEqual(threadStart.params.dynamicTools, [
    {
      type: "namespace",
      name: "averqel",
      description: "Tools available to the AverQel agent.",
      tools: [
        { type: "function", name: "lookup", description: "", inputSchema: { type: "object", properties: {} } },
        { type: "function", name: "search", description: "", inputSchema: { type: "object", properties: {} } },
      ],
    },
  ]);
  assert.ok(appServerInstances.at(-1).calls.some((call) => call.method === "turn/start"));
  assert.ok(frames.some((frame) => frame.event?.type === "response.completed"));
});

test("fails closed when the Codex CLI cannot provide the restricted inference profile", async () => {
  const { runtime } = createRuntime({ permissionProfileAllowed: false });
  const status = await runtime.status();

  assert.equal(status.available, false);
  assert.deepEqual(status.accounts, []);
});

test("does not start a model turn if Codex did not activate the restricted profile", async () => {
  const { runtime, frames, appServerInstances } = createRuntime({ activePermissionProfileId: ":read-only" });
  const status = await runtime.status();
  await runtime.startStream({
    streamId: "323e4567-e89b-12d3-a456-426614174000",
    accountId: status.accounts[0].id,
    request: {
      model: "gpt-5-codex",
      input: [{ role: "user", content: [{ type: "input_text", text: "No inference should start." }] }],
    },
  });
  await waitForClosed(frames);

  assert.ok(!appServerInstances.at(-1).requests.includes("turn/start"));
  assert.ok(frames.some((frame) => frame.kind === "error"));
});

test("removes browser credentials locally and reports whether OpenAI confirmed revocation", async (t) => {
  const userData = await mkdtemp(path.join(os.tmpdir(), "averqel-codex-disconnect-test-"));
  t.after(() => rm(userData, { recursive: true, force: true }));
  const responses = [false, true];
  const runtime = new CodexDesktopRuntime({
    app: { getPath: (name) => name === "userData" ? userData : os.tmpdir() },
    safeStorage: {
      isEncryptionAvailable: () => true,
      getSelectedStorageBackend: () => "gnome_libsecret",
      encryptString: (value) => Buffer.from(value),
      decryptString: (value) => value.toString("utf8"),
    },
    shell: {},
    emit: () => {},
    fetchImpl: async () => ({ ok: responses.shift() }),
  });
  runtime._getOidcConfig = async () => ({
    revocation_endpoint: "https://auth.openai.com/api/accounts/oauth/revoke",
  });

  for (const [index, expectedRevoked] of [false, true].entries()) {
    const accountId = `account-${index}`;
    await runtime._updateStore((store) => {
      store.accounts.push({
        id: accountId,
        email: "user@example.test",
        name: "User",
        client_id: "registered-client",
        refresh_token: "test-refresh-token",
      });
    });

    assert.deepEqual(await runtime.disconnect(accountId), { revoked: expectedRevoked });
    const store = await runtime._readStore();
    assert.ok(!store.accounts.some((account) => account.id === accountId));
  }
});
