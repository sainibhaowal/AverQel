function registerCodexIpcHandlers({ ipcMain, getRuntime, isAverQelSender }) {
  const runtime = () => getRuntime();
  const authorize = (event, action) => {
    if (!isAverQelSender(event)) throw new Error(`Unauthorized Codex ${action} request.`);
  };

  ipcMain.handle("codex:status", async (event) => {
    authorize(event, "account");
    return runtime().status();
  });
  ipcMain.handle("codex:connect", async (event, accountId, source) => {
    authorize(event, "account");
    if (
      accountId !== undefined &&
      accountId !== null &&
      (typeof accountId !== "string" || accountId.length > 64)
    ) {
      throw new Error("Invalid Codex account identifier.");
    }
    if (source !== undefined && !["chatgpt", "codex_cli"].includes(source)) {
      throw new Error("Invalid Codex account source.");
    }
    return runtime().connect(accountId || null, source || null);
  });
  ipcMain.handle("codex:models", async (event, accountId) => {
    authorize(event, "account");
    if (typeof accountId !== "string" || accountId.length > 64) {
      throw new Error("Invalid Codex account identifier.");
    }
    return runtime().models(accountId);
  });
  ipcMain.handle("codex:disconnect", async (event, accountId) => {
    authorize(event, "account");
    if (typeof accountId !== "string" || accountId.length > 64) {
      throw new Error("Invalid Codex account identifier.");
    }
    const result = await runtime().disconnect(accountId);
    return { ok: true, revoked: result?.revoked === true };
  });
  ipcMain.handle("codex:stream-start", async (event, input) => {
    authorize(event, "inference");
    if (!input || typeof input !== "object" || Array.isArray(input)) {
      throw new Error("Invalid Codex inference request.");
    }
    return runtime().startStream(input);
  });
  ipcMain.handle("codex:stream-cancel", (event, streamId) => {
    authorize(event, "inference");
    if (typeof streamId !== "string") return false;
    return runtime().cancelStream(streamId);
  });
}

module.exports = { registerCodexIpcHandlers };
