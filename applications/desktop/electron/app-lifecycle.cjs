function registerAppLifecycle({ app, showWindow }) {
  if (!app.requestSingleInstanceLock()) {
    app.quit();
    return false;
  }

  app.on("second-instance", showWindow);
  app.on("window-all-closed", () => app.quit());
  return true;
}

module.exports = { registerAppLifecycle };
