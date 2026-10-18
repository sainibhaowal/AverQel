function registerLocalRuntimeIpcHandlers({ ipcMain, getRuntime, isAverQelSender }) {
  const runtime = () => getRuntime();
  const authorize = (event, action) => {
    if (!isAverQelSender(event)) throw new Error(`Unauthorized local runtime ${action} request.`);
  };
  ipcMain.handle("local-runtime:status", async (event) => {
    authorize(event, "status");
    return runtime().status();
  });
  ipcMain.handle("local-runtime:stream-start", async (event, input) => {
    authorize(event, "inference");
    if (!input || typeof input !== "object" || Array.isArray(input)) throw new Error("Invalid local runtime request.");
    return runtime().startStream(input);
  });
  ipcMain.handle("local-runtime:stream-cancel", (event, streamId) => {
    authorize(event, "inference");
    if (typeof streamId !== "string") return false;
    return runtime().cancelStream(streamId);
  });
}

module.exports = { registerLocalRuntimeIpcHandlers };
