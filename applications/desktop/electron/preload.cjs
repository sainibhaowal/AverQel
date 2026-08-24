const { contextBridge, ipcRenderer } = require("electron");

window.addEventListener("DOMContentLoaded", () => {
  document.title = "AverQel";
});

contextBridge.exposeInMainWorld("electron", {
  isElectron: true,
  window: {
    minimize: () => ipcRenderer.invoke("window:minimize"),
    toggleMaximize: () => ipcRenderer.invoke("window:toggle-maximize"),
    isMaximized: () => ipcRenderer.invoke("window:is-maximized"),
    hide: () => ipcRenderer.invoke("window:hide"),
  },
  openExternal: (url) => ipcRenderer.invoke("open-external", url),
});
