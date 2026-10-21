const assert = require("node:assert/strict");
const test = require("node:test");

const { registerAppLifecycle } = require("../electron/app-lifecycle.cjs");

function setup({ hasLock }) {
  const listeners = new Map();
  let quitCalls = 0;
  let focusCalls = 0;
  const app = {
    requestSingleInstanceLock: () => hasLock,
    quit: () => { quitCalls += 1; },
    on: (event, listener) => listeners.set(event, listener),
  };

  const accepted = registerAppLifecycle({
    app,
    showWindow: () => { focusCalls += 1; },
  });

  return {
    accepted,
    listeners,
    get quitCalls() { return quitCalls; },
    get focusCalls() { return focusCalls; },
  };
}

test("reuses the existing window for another launch and quits after closing", () => {
  const lifecycle = setup({ hasLock: true });

  assert.equal(lifecycle.accepted, true);
  assert.equal(lifecycle.quitCalls, 0);

  lifecycle.listeners.get("second-instance")();
  assert.equal(lifecycle.focusCalls, 1);

  lifecycle.listeners.get("window-all-closed")();
  assert.equal(lifecycle.quitCalls, 1);
});

test("quits a duplicate process that cannot acquire the instance lock", () => {
  const lifecycle = setup({ hasLock: false });

  assert.equal(lifecycle.accepted, false);
  assert.equal(lifecycle.quitCalls, 1);
  assert.equal(lifecycle.listeners.size, 0);
});
