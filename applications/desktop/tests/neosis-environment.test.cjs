const assert = require("node:assert/strict");
const test = require("node:test");
const { createNeosisEnvironment } = require("../electron/neosis-environment.cjs");

test("passes the NeoSIS home and safe operating-system runtime variables only", () => {
  const environment = createNeosisEnvironment(
    {
      PATH: "/usr/bin",
      HOME: "/home/test-user",
      LANG: "en_US.UTF-8",
      OPENAI_API_KEY: "must-not-cross",
      DATABASE_URL: "must-not-cross",
      ELECTRON_PRODUCTION_URL: "must-not-cross",
      NEXT_PUBLIC_API_URL: "must-not-cross",
      NODE_OPTIONS: "must-not-cross",
      GH_TOKEN: "must-not-cross",
    },
    "/home/test-user/.config/averqel/neosis",
  );

  assert.deepEqual(environment, {
    PATH: "/usr/bin",
    HOME: "/home/test-user",
    LANG: "en_US.UTF-8",
    NEOSIS_HOME: "/home/test-user/.config/averqel/neosis",
  });
});

test("enables Electron's Node mode only for the packaged runtime child", () => {
  const packagedEnvironment = createNeosisEnvironment({ PATH: "/usr/bin" }, "/tmp/neosis", {
    electronRunAsNode: true,
  });
  const developmentEnvironment = createNeosisEnvironment({ PATH: "/usr/bin" }, "/tmp/neosis");

  assert.equal(packagedEnvironment.ELECTRON_RUN_AS_NODE, "1");
  assert.equal("ELECTRON_RUN_AS_NODE" in developmentEnvironment, false);
});
