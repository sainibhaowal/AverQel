import { defineConfig, devices } from "@playwright/test";

const externalBaseUrl = process.env.DEEPSPACE_E2E_BASE_URL;
const localBaseUrl = "http://127.0.0.1:3103";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: "line",
  timeout: 30_000,
  use: {
    baseURL: externalBaseUrl || localBaseUrl,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  // An explicit base URL targets a deployed/staging environment and must never spawn a second
  // local server. Local runs use the Node resolved from PATH instead of a machine-specific NVM path.
  webServer: externalBaseUrl
    ? undefined
    : {
        command: 'bash ./scripts/run-with-runtime-env.sh "npx next dev --webpack -p 3103"',
        url: localBaseUrl,
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
