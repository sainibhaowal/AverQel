const assert = require("node:assert/strict");
const test = require("node:test");

const { registerLocalRuntimeIpcHandlers } = require("../electron/local-runtime-ipc.cjs");

function setup() {
  const handlers = new Map();
  const calls = [];
  const runtime = {
    status: () => ({ available: true }),
    startStream: (...args) => { calls.push(["startStream", ...args]); return { accepted: true }; },
    cancelStream: (...args) => { calls.push(["cancelStream", ...args]); return true; },
  };
  registerLocalRuntimeIpcHandlers({
    ipcMain: { handle: (channel, handler) => handlers.set(channel, handler) },
    getRuntime: () => runtime,
    isAverQelSender: (event) => event?.authorized === true,
  });
  return { handlers, calls };
}

test("local runtime IPC rejects untrusted renderers", async () => {
  const { handlers, calls } = setup();
  await assert.rejects(handlers.get("local-runtime:status")({ authorized: false }), /Unauthorized/);
  await assert.rejects(handlers.get("local-runtime:stream-start")({ authorized: false }, {}), /Unauthorized/);
  assert.throws(() => handlers.get("local-runtime:stream-cancel")({ authorized: false }, "id"), /Unauthorized/);
  assert.deepEqual(calls, []);
});

test("local runtime IPC forwards authorized requests", async () => {
  const { handlers, calls } = setup();
  const event = { authorized: true };
  assert.deepEqual(await handlers.get("local-runtime:status")(event), { available: true });
  const input = { streamId: "00000000-0000-4000-8000-000000000001", providerType: "ollama", baseUrl: "http://127.0.0.1:11434", request: {} };
  assert.deepEqual(await handlers.get("local-runtime:stream-start")(event, input), { accepted: true });
  assert.equal(await handlers.get("local-runtime:stream-cancel")(event, input.streamId), true);
  assert.deepEqual(calls, [["startStream", input], ["cancelStream", input.streamId]]);
});
