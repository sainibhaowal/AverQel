const assert = require("node:assert/strict");
const test = require("node:test");

const { LocalRuntime, localUrl } = require("../electron/local-runtime.cjs");

function response(body, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => (typeof body === "string" ? body : JSON.stringify(body)),
    body: body instanceof ReadableStream ? body : undefined,
  };
}

async function waitForClosed(frames) {
  for (let index = 0; index < 100 && !frames.some((frame) => frame.kind === "closed"); index += 1) {
    await new Promise((resolve) => setTimeout(resolve, 1));
  }
  assert.ok(frames.some((frame) => frame.kind === "closed"));
}

test("local runtime accepts only loopback URLs and normalizes provider paths", () => {
  assert.equal(localUrl("lmstudio", "http://127.0.0.1:1234"), "http://127.0.0.1:1234/v1");
  assert.equal(localUrl("ollama", "http://localhost:11434/v1"), "http://localhost:11434");
  assert.throws(() => localUrl("ollama", "https://example.test"), /loopback/);
  assert.throws(() => localUrl("ollama", "http://user:pass@127.0.0.1:11434"), /credentials/);
});

test("local runtime discovers Ollama models without exposing credentials", async () => {
  const frames = [];
  const runtime = new LocalRuntime({
    emit: (_streamId, frame) => frames.push(frame),
    fetchImpl: async (url, options) => {
      assert.equal(url, "http://127.0.0.1:11434/api/tags");
      assert.equal(options.headers.accept, "application/json");
      return response({ models: [{ name: "llama3.2:latest" }] });
    },
  });
  await runtime.startStream({
    streamId: "00000000-0000-4000-8000-000000000001",
    providerType: "ollama",
    baseUrl: "http://127.0.0.1:11434",
    operation: "models",
    request: {},
  });
  await waitForClosed(frames);
  assert.deepEqual(frames.find((frame) => frame.event?.type === "result")?.event.result.models, [
    { name: "llama3.2:latest", kind: "chat", display_name: "llama3.2:latest", capabilities: { local: true } },
  ]);
});

test("local runtime normalizes OpenAI-compatible streaming deltas", async () => {
  const frames = [];
  const stream = new ReadableStream({
    start(controller) {
      controller.enqueue(new TextEncoder().encode('data: {"choices":[{"delta":{"content":"hello"}}]}\n\n'));
      controller.enqueue(new TextEncoder().encode('data: [DONE]\n\n'));
      controller.close();
    },
  });
  const runtime = new LocalRuntime({
    emit: (_streamId, frame) => frames.push(frame),
    fetchImpl: async (url, options) => {
      assert.equal(url, "http://localhost:1234/v1/chat/completions");
      const payload = JSON.parse(options.body);
      assert.equal(payload.stream, true);
      assert.equal(payload.model, "local-model");
      return response(stream);
    },
  });
  await runtime.startStream({
    streamId: "00000000-0000-4000-8000-000000000002",
    providerType: "lmstudio",
    baseUrl: "http://localhost:1234/v1",
    request: { model: "local-model", messages: [{ role: "user", content: "hi" }] },
  });
  await waitForClosed(frames);
  assert.equal(frames.find((frame) => frame.event?.type === "delta")?.event.text, "hello");
  assert.ok(frames.some((frame) => frame.event?.type === "completed"));
});
