const assert = require("node:assert/strict");
const test = require("node:test");

const { registerCodexIpcHandlers } = require("../electron/codex-ipc.cjs");

function setup() {
  const handlers = new Map();
  const calls = [];
  const runtime = Object.fromEntries([
    "status",
    "connect",
    "models",
    "disconnect",
    "startStream",
    "cancelStream",
  ].map((method) => [method, (...args) => {
    calls.push({ method, args });
    return Promise.resolve({ method, args });
  }]));
  registerCodexIpcHandlers({
    ipcMain: { handle: (channel, handler) => handlers.set(channel, handler) },
    getRuntime: () => runtime,
    isAverQelSender: (event) => event?.authorized === true,
  });
  return { handlers, calls };
}

test("blocks every Codex IPC route unless the sender is the trusted AverQel renderer", async () => {
  const { handlers, calls } = setup();
  const event = { authorized: false };

  await assert.rejects(handlers.get("codex:status")(event), /Unauthorized Codex account request/);
  await assert.rejects(handlers.get("codex:connect")(event, "account"), /Unauthorized Codex account request/);
  await assert.rejects(handlers.get("codex:models")(event, "account"), /Unauthorized Codex account request/);
  await assert.rejects(handlers.get("codex:disconnect")(event, "account"), /Unauthorized Codex account request/);
  await assert.rejects(handlers.get("codex:stream-start")(event, {}), /Unauthorized Codex inference request/);
  assert.throws(() => handlers.get("codex:stream-cancel")(event, "stream"), /Unauthorized Codex inference request/);
  assert.deepEqual(calls, []);
});

test("validates account and inference arguments before calling the local runtime", async () => {
  const { handlers, calls } = setup();
  const event = { authorized: true };

  await assert.rejects(handlers.get("codex:connect")(event, 123), /Invalid Codex account identifier/);
  await assert.rejects(handlers.get("codex:connect")(event, "account", "arbitrary"), /Invalid Codex account source/);
  await assert.rejects(handlers.get("codex:models")(event, "x".repeat(65)), /Invalid Codex account identifier/);
  await assert.rejects(handlers.get("codex:disconnect")(event, null), /Invalid Codex account identifier/);
  await assert.rejects(handlers.get("codex:stream-start")(event, []), /Invalid Codex inference request/);
  assert.deepEqual(calls, []);
});

test("passes authorized requests through with the validated source and identifiers", async () => {
  const { handlers, calls } = setup();
  const event = { authorized: true };

  assert.deepEqual(await handlers.get("codex:status")(event), { method: "status", args: [] });
  assert.deepEqual(await handlers.get("codex:connect")(event, "account", "codex_cli"), {
    method: "connect",
    args: ["account", "codex_cli"],
  });
  assert.deepEqual(await handlers.get("codex:models")(event, "account"), {
    method: "models",
    args: ["account"],
  });
  assert.deepEqual(await handlers.get("codex:disconnect")(event, "account"), { ok: true, revoked: false });
  const input = { streamId: "stream", accountId: "account", request: { model: "gpt" } };
  assert.deepEqual(await handlers.get("codex:stream-start")(event, input), {
    method: "startStream",
    args: [input],
  });
  assert.deepEqual(await handlers.get("codex:stream-cancel")(event, "stream"), {
    method: "cancelStream",
    args: ["stream"],
  });
  assert.deepEqual(calls.map(({ method }) => method), [
    "status",
    "connect",
    "models",
    "disconnect",
    "startStream",
    "cancelStream",
  ]);
});
