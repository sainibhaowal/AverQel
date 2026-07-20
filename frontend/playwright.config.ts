import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: "line",
  timeout: 30_000,
  use: {
    baseURL: process.env.DEEPSPACE_E2E_BASE_URL || "http://127.0.0.1:3103",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  webServer: {
    command:
      'bash ./scripts/run-with-runtime-env.sh "/home/ravi/.nvm/versions/node/v22.22.0/bin/node ./node_modules/next/dist/bin/next dev --webpack -p 3103"',
    url: "http://127.0.0.1:3103",
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
