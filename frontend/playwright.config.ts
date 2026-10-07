import { defineConfig, devices } from "@playwright/test";

const externalBaseUrl = process.env.DEEPSPACE_E2E_BASE_URL;
const externalE2ERequested = process.env.DEEPSPACE_E2E_ALLOW_EXTERNAL === "1";
const externalE2EAllowed = Boolean(externalBaseUrl && externalE2ERequested);
const hasExternalAuth = Boolean(
  process.env.DEEPSPACE_E2E_STORAGE_STATE || process.env.DEEPSPACE_E2E_AUTH_TOKEN,
);
const localBaseUrl = "http://127.0.0.1:3103";

if (externalBaseUrl && !externalE2EAllowed) {
  throw new Error(
    "External browser E2E is disabled by default. Set DEEPSPACE_E2E_ALLOW_EXTERNAL=1 only " +
      "when you intend to run against the explicitly configured target.",
  );
}

if (externalE2ERequested && !externalBaseUrl) {
  throw new Error("DEEPSPACE_E2E_ALLOW_EXTERNAL=1 requires an explicit DEEPSPACE_E2E_BASE_URL.");
}

if (hasExternalAuth && !externalE2EAllowed) {
  throw new Error(
    "Browser E2E credentials were provided without explicit external-target approval. " +
      "Unset the credentials for local mocked tests, or set DEEPSPACE_E2E_ALLOW_EXTERNAL=1 " +
      "with DEEPSPACE_E2E_BASE_URL for an intentional external run.",
  );
}

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  // The local Next dev server compiles the full app on demand. Running all
  // browser specs in parallel starves that server and makes pages time out
  // before their client bundles finish loading, so use the same serial mode
  // locally and in CI.
  workers: 1,
  reporter: "line",
  timeout: 30_000,
  use: {
    baseURL: externalBaseUrl || localBaseUrl,
    // Browser credentials are only loaded for the explicitly approved target.
    storageState: externalE2EAllowed
      ? process.env.DEEPSPACE_E2E_STORAGE_STATE || undefined
      : undefined,
    ignoreHTTPSErrors: Boolean(externalBaseUrl?.startsWith("https://localhost")),
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  // An explicit base URL targets an external environment and requires a second
  // explicit opt-in. Local runs are loopback-only and never reuse a live server.
  webServer: externalBaseUrl
    ? undefined
    : {
        command: "bash ./scripts/start-e2e-server.sh",
        // The launcher uses an env-free temporary source snapshot, binds only
        // loopback, and sends API requests to the closed local test sink.
        url: localBaseUrl,
        reuseExistingServer: false,
        timeout: 120_000,
      },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
