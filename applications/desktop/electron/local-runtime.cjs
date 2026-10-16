const LOOPBACK_HOSTS = new Set(["localhost", "127.0.0.1", "::1", "[::1]"]);
const LOCAL_PROVIDERS = new Set(["lmstudio", "ollama"]);
const MAX_STREAMS = 4;
const MAX_REQUEST_BYTES = 2_000_000;
const MAX_LINE_BYTES = 512_000;

function validStreamId(value) {
  return typeof value === "string" && /^[0-9a-f-]{36}$/i.test(value);
}

function localUrl(providerType, value, { native = false } = {}) {
  if (typeof value !== "string" || value.length > 512) {
    throw new Error("A local runtime URL is required.");
  }
  let url;
  try {
    url = new URL(value);
  } catch {
    throw new Error("The local runtime URL is invalid.");
  }
  if (!['http:', 'https:'].includes(url.protocol) || !LOOPBACK_HOSTS.has(url.hostname)) {
    throw new Error("Local runtimes must use a loopback URL.");
  }
  if (url.username || url.password) throw new Error("Local runtime URLs cannot contain credentials.");
  url.hash = "";
  url.search = "";
  let pathname = url.pathname.replace(/\/+$/, "");
  if (providerType === "lmstudio" && !native && !pathname.endsWith("/v1")) pathname += "/v1";
  if (providerType === "ollama" && !native && pathname.endsWith("/v1")) pathname = pathname.slice(0, -3);
  url.pathname = pathname || "/";
  return url.toString().replace(/\/$/, "");
}

function jsonSize(value) {
  try { return Buffer.byteLength(JSON.stringify(value)); } catch { return Infinity; }
}

function safeError(error, fallback) {
  const message = error instanceof Error ? error.message : fallback;
  return String(message || fallback).replace(/[\r\n]+/g, " ").slice(0, 500);
}

class LocalRuntime {
  constructor({ emit, fetchImpl = globalThis.fetch } = {}) {
    this.emit = emit;
    this.fetchImpl = fetchImpl;
    this.streams = new Map();
    this.timers = new Map();
  }

  status() {
    return { available: true, providers: ["lmstudio", "ollama"], active_streams: this.streams.size };
  }

  async startStream({ streamId, providerType, baseUrl, operation = "chat", request = {} }) {
    if (!validStreamId(streamId)) throw new Error("Invalid local runtime stream identifier.");
    if (!LOCAL_PROVIDERS.has(providerType)) throw new Error("Unsupported local runtime provider.");
    if (!['chat', 'health', 'models', 'embed', 'pull'].includes(operation)) throw new Error("Unsupported local runtime operation.");
    if (this.streams.has(streamId)) throw new Error("That local runtime request is already active.");
    if (this.streams.size >= MAX_STREAMS) throw new Error("The desktop local runtime is busy. Wait for an active request to finish.");
    if (!request || typeof request !== "object" || Array.isArray(request) || jsonSize(request) > MAX_REQUEST_BYTES) {
      throw new Error("The local runtime request is invalid or too large.");
    }
    const controller = new AbortController();
    this.streams.set(streamId, controller);
    const requestedTimeout = Number(request.timeout_seconds);
    const timeoutMs = (Number.isFinite(requestedTimeout) ? Math.min(Math.max(requestedTimeout, 5), 900) : operation === "chat" ? 300 : 30) * 1000;
    this.timers.set(streamId, setTimeout(() => controller.abort(), timeoutMs));
    void this._run({ streamId, providerType, baseUrl, operation, request, signal: controller.signal });
    return { accepted: true };
  }

  cancelStream(streamId) {
    const controller = this.streams.get(streamId);
    if (!controller) return false;
    controller.abort();
    return true;
  }

  cancelAllStreams() {
    for (const [streamId, controller] of this.streams) {
      controller.abort();
      const timer = this.timers.get(streamId);
      if (timer) clearTimeout(timer);
    }
    this.timers.clear();
    this.streams.clear();
  }

  _event(streamId, event) { this.emit?.(streamId, { kind: "event", event }); }
  _error(streamId, error, httpStatus, code = "local_runtime_error") {
    this.emit?.(streamId, { kind: "error", message: safeError(error, "Local runtime request failed."), ...(Number.isInteger(httpStatus) ? { httpStatus } : {}), code });
  }

  async _run(input) {
    const { streamId, providerType, baseUrl, operation, request, signal } = input;
    try {
      if (operation === "chat") await this._chat(streamId, providerType, baseUrl, request, signal);
      else if (operation === "health") await this._health(streamId, providerType, baseUrl, signal);
      else if (operation === "models") await this._models(streamId, providerType, baseUrl, signal);
      else if (operation === "embed") await this._embed(streamId, providerType, baseUrl, request, signal);
      else await this._pull(streamId, providerType, baseUrl, request, signal);
    } catch (error) {
      if (!signal.aborted) this._error(streamId, error, error?.httpStatus);
    } finally {
      this.streams.delete(streamId);
      const timer = this.timers.get(streamId);
      if (timer) clearTimeout(timer);
      this.timers.delete(streamId);
      this.emit?.(streamId, { kind: "closed" });
    }
  }

  async _fetchJson(url, options, signal) {
    const response = await this.fetchImpl(url, { ...options, signal });
    const text = await response.text();
    let body = {};
    try { body = text ? JSON.parse(text) : {}; } catch { body = {}; }
    if (!response.ok) {
      const error = new Error(typeof body?.error === "string" ? body.error : `Local runtime returned HTTP ${response.status}.`);
      error.httpStatus = response.status;
      throw error;
    }
    return body;
  }

  async _health(streamId, providerType, baseUrl, signal) {
    const started = Date.now();
    if (providerType === "ollama") {
      await this._fetchJson(`${localUrl(providerType, baseUrl, { native: true })}/api/tags`, { headers: { accept: "application/json" } }, signal);
    } else {
      await this._lmStudioModels(baseUrl, signal);
    }
    this._event(streamId, { type: "result", result: { status: "healthy", latency_ms: Date.now() - started, provider: providerType } });
  }

  async _lmStudioModels(baseUrl, signal) {
    let lastError;
    for (const endpoint of [
      `${localUrl("lmstudio", baseUrl)}/models`,
      `${localUrl("lmstudio", baseUrl, { native: true }).replace(/\/v1$/, "")}/api/v1/models`,
    ]) {
      try {
        return await this._fetchJson(endpoint, { headers: { accept: "application/json" } }, signal);
      } catch (error) {
        lastError = error;
      }
    }
    throw lastError || new Error("LM Studio model listing failed.");
  }

  async _models(streamId, providerType, baseUrl, signal) {
    const models = [];
    if (providerType === "ollama") {
      const body = await this._fetchJson(`${localUrl(providerType, baseUrl, { native: true })}/api/tags`, { headers: { accept: "application/json" } }, signal);
      for (const item of Array.isArray(body.models) ? body.models : []) {
        if (typeof item?.name === "string" && item.name) models.push({ name: item.name, kind: "chat", display_name: item.name, capabilities: { local: true } });
      }
    } else {
      const body = await this._lmStudioModels(baseUrl, signal);
      for (const item of Array.isArray(body.data) ? body.data : []) {
        if (typeof item?.id === "string" && item.id) {
          const embedding = item.type === "embeddings" || /embed/i.test(item.id);
          models.push({ name: item.id, kind: embedding ? "embedding" : "chat", display_name: item.id, capabilities: { local: true, supports_chat: !embedding, supports_embeddings: embedding } });
        }
      }
    }
    this._event(streamId, { type: "result", result: { models, provider: providerType } });
  }

  async _embed(streamId, providerType, baseUrl, request, signal) {
    const input = Array.isArray(request.input) ? request.input.slice(0, 128) : [];
    if (!input.length || typeof request.model !== "string" || !request.model) throw new Error("An embedding model and input are required.");
    let body;
    if (providerType === "ollama") {
      body = await this._fetchJson(`${localUrl(providerType, baseUrl, { native: true })}/api/embed`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ model: request.model, input }) }, signal);
      this._event(streamId, { type: "result", result: { embeddings: Array.isArray(body.embeddings) ? body.embeddings : [], provider: providerType } });
    } else {
      body = await this._fetchJson(`${localUrl(providerType, baseUrl)}/embeddings`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ model: request.model, input }) }, signal);
      const embeddings = (Array.isArray(body.data) ? body.data : []).map((item) => item?.embedding).filter(Array.isArray);
      this._event(streamId, { type: "result", result: { embeddings, provider: providerType } });
    }
  }

  async _pull(streamId, providerType, baseUrl, request, signal) {
    if (providerType !== "ollama") throw new Error("LM Studio model downloads must be managed in LM Studio.");
    if (typeof request.model !== "string" || !request.model.trim()) throw new Error("An Ollama model name is required.");
    await this._fetchJson(`${localUrl(providerType, baseUrl, { native: true })}/api/pull`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ name: request.model.trim(), stream: false }) }, signal);
    this._event(streamId, { type: "result", result: { status: "healthy", model: request.model.trim(), provider: providerType } });
  }

  async _chat(streamId, providerType, baseUrl, request, signal) {
    const url = `${localUrl(providerType, baseUrl)}/chat/completions`;
    const payload = { ...request, stream: true };
    const response = await this.fetchImpl(url, { method: "POST", headers: { "content-type": "application/json", accept: "text/event-stream" }, body: JSON.stringify(payload), signal });
    if (!response.ok) {
      const text = await response.text().catch(() => "");
      const error = new Error(text.slice(0, 500) || `Local runtime returned HTTP ${response.status}.`);
      error.httpStatus = response.status;
      throw error;
    }
    if (!response.body?.getReader) throw new Error("The local runtime did not return a stream.");
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let total = 0;
    const consume = (line) => {
      if (!line.startsWith("data:")) return;
      const raw = line.slice(5).trim();
      if (raw === "[DONE]") { this._event(streamId, { type: "completed" }); return; }
      if (Buffer.byteLength(raw) > MAX_LINE_BYTES) throw new Error("The local runtime sent an oversized stream event.");
      let chunk;
      try { chunk = JSON.parse(raw); } catch { return; }
      const choice = Array.isArray(chunk.choices) ? chunk.choices[0] : null;
      const delta = choice?.delta;
      if (typeof delta?.content === "string" && delta.content) this._event(streamId, { type: "delta", text: delta.content });
      if (typeof delta?.reasoning_content === "string" && delta.reasoning_content) this._event(streamId, { type: "thinking", text: delta.reasoning_content });
      if (Array.isArray(delta?.tool_calls) && delta.tool_calls.length) this._event(streamId, { type: "tool_calls_delta", tool_calls: delta.tool_calls });
      if (chunk.usage && typeof chunk.usage === "object") this._event(streamId, { type: "usage", usage: chunk.usage });
    };
    while (!signal.aborted) {
      const { done, value } = await reader.read();
      if (done) break;
      total += value.byteLength;
      if (total > 16_000_000) throw new Error("The local runtime response exceeded the size limit.");
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split(/\r?\n/);
      buffer = lines.pop() || "";
      for (const line of lines) consume(line);
    }
    if (buffer) consume(buffer);
  }
}

module.exports = { LocalRuntime, localUrl, LOOPBACK_HOSTS };
