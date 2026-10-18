import { test as base, type Page } from "@playwright/test";

type DeepSpaceFixtures = {
  authenticatedPage: Page;
  adminPage: Page;
};

const LOCAL_E2E_TENANT_ID = "e2e-local-tenant";
const LOCAL_E2E_USER_ID = "e2e-local-user";
const LOCAL_E2E_TOKEN = `e30.${Buffer.from(
  JSON.stringify({
    exp: Math.floor(Date.now() / 1000) + 60 * 60,
    tenant_id: LOCAL_E2E_TENANT_ID,
  }),
).toString("base64url")}.local-only`;

/**
 * Staging authentication is supplied through Playwright storage state or a
 * short-lived staging token. No production credentials belong in the repo.
 */
async function configureAuthenticatedPage(page: Page, localRoles: string[]) {
  const externalRun =
    process.env.DEEPSPACE_E2E_ALLOW_EXTERNAL === "1" && Boolean(process.env.DEEPSPACE_E2E_BASE_URL);
  const token = externalRun ? process.env.DEEPSPACE_E2E_AUTH_TOKEN : LOCAL_E2E_TOKEN;
  const tenantId = externalRun ? process.env.DEEPSPACE_E2E_TENANT_ID : LOCAL_E2E_TENANT_ID;
  const userId = externalRun ? process.env.DEEPSPACE_E2E_USER_ID : LOCAL_E2E_USER_ID;
  const userEmail = externalRun ? process.env.DEEPSPACE_E2E_USER_EMAIL : undefined;
  const roles = (externalRun ? (process.env.DEEPSPACE_E2E_ROLES ?? "user") : localRoles.join(","))
    .split(",")
    .map((role) => role.trim())
    .filter(Boolean);
  if (!token) return;

  if (!externalRun) {
    await page.route("**/api/v1/**", async (route) => {
      const request = route.request();
      const pathname = new URL(request.url()).pathname.replace(/^\/api\/v1/, "").replace(/\/$/, "");
      const method = request.method();
      const emptyList = { items: [] };
      const localConversationId = "00000000-0000-0000-0000-000000000301";
      let body: unknown = {};

      if (pathname === "/health/ready") {
        body = { status: "ok" };
      } else if (pathname === "/dashboard/overview") {
        body = {
          stats: {
            total_documents: 0,
            total_queries: 0,
            storage_used_bytes: 0,
            active_jobs: 0,
          },
          document_breakdown: {
            indexed: 0,
            processing: 0,
            failed: 0,
            queued: 0,
            quarantined: 0,
          },
          recent_documents: [],
          provider_runtimes: [],
          collections: [],
          recent_activity: [],
          activity_trend: [],
          provider_trend: [],
        };
      } else if (pathname === "/notifications" || pathname === "/collections/notifications") {
        body = [];
      } else if (pathname === "/collections" || pathname === "/collections/invitations") {
        body = [];
      } else if (pathname === "/queries/capabilities/chat") {
        body = { supports_thinking: false, supports_thinking_toggle: false };
      } else if (pathname === "/dashboard/query-stats") {
        body = { total_queries: 0, successful_queries: 0, failed_queries: 0 };
      } else if (pathname === "/plans/current") {
        body = {
          current_plan: { name: "E2E", storage_limit_bytes: 1_000_000 },
          usage: { total_bytes: 0 },
        };
      } else if (pathname === "/auth/profile") {
        body = {
          user_id: LOCAL_E2E_USER_ID,
          tenant_id: LOCAL_E2E_TENANT_ID,
          collection_code: "E2E",
          email: "e2e@example.org",
          display_name: "E2E User",
          avatar: null,
          roles: localRoles,
          status: "active",
          created_at: "2026-01-01T00:00:00Z",
          last_login_at: null,
          totp_enabled: false,
          onboarding_completed: true,
        };
      } else if (pathname === "/providers" || pathname === "/providers/assignments") {
        body = emptyList;
      } else if (pathname === "/documents") {
        body = { items: [] };
      } else if (pathname === "/providers/catalog/supported-types") {
        body = { items: [] };
      } else if (pathname === "/mcp/servers") {
        body = [];
      } else if (pathname === "/mcp/marketplace") {
        body = { items: [], page: 1, page_size: 20, total: 0, pages: 1 };
      } else if (pathname === "/mcp/marketplace/facets") {
        body = { categories: [], transports: [], auth_types: [], trust_statuses: [] };
      } else if (pathname === "/deepspace/chats" && method === "GET") {
        body = {
          items: [
            {
              id: localConversationId,
              title: "Local E2E conversation",
              updated_at: new Date().toISOString(),
              content_html: "",
            },
          ],
        };
      } else if (pathname === "/deepspace/chats/operational-summary") {
        body = null;
      } else if (/^\/deepspace\/chats\/[^/]+\/messages$/.test(pathname)) {
        body = { messages: [] };
      } else if (/^\/deepspace\/chats\/[^/]+\/queue/.test(pathname)) {
        body = { items: [], paused: false, reason: null, failed_request_id: null };
      } else if (pathname.endsWith("/stream")) {
        body = { error: "This E2E request must be mocked by its spec." };
      }

      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(body),
      });
    });
  }

  await page.addInitScript(
    ({ accessToken, tenant, user }) => {
      window.localStorage.setItem("averqel_token", accessToken);
      if (tenant) window.localStorage.setItem("averqel_tenant_id", tenant);
      if (user) window.localStorage.setItem("averqel_user", JSON.stringify(user));
      window.localStorage.setItem("averqel_remember", "true");
    },
    {
      accessToken: token,
      tenant: tenantId ?? "",
      user: userId
        ? {
            id: userId,
            email: userEmail ?? "e2e@example.org",
            tenant_id: tenantId ?? "",
            roles,
          }
        : null,
    },
  );
}

export const test = base.extend<DeepSpaceFixtures>({
  authenticatedPage: async ({ page }, provide) => {
    await configureAuthenticatedPage(page, ["user"]);
    await provide(page);
  },
  adminPage: async ({ page }, provide) => {
    await configureAuthenticatedPage(page, ["admin"]);
    await provide(page);
  },
});

// Attach browser-side diagnostics to the Playwright result. These are kept as
// artifacts rather than printed as secrets or mixed into the normal test log.
// A failed request is useful evidence, while the test itself remains the
// authority for whether the user-visible contract failed.
test.afterEach(async ({ page }, testInfo) => {
  let diagnostics: unknown = null;
  try {
    diagnostics = await page.evaluate(() => {
      const value = (window as Window & { __averqelE2EDiagnostics?: unknown })
        .__averqelE2EDiagnostics;
      return value ?? null;
    });
  } catch {
    // The browser may already be closed after a timeout or cancellation. The
    // primary Playwright failure remains the useful diagnostic in that case.
  }
  if (diagnostics !== null) {
    await testInfo.attach("browser-diagnostics", {
      body: JSON.stringify(diagnostics, null, 2),
      contentType: "application/json",
    });
  }
});

// Keep this listener in the shared fixture so every authenticated spec gets
// the same request and console evidence. It does not fail a test by itself;
// some suites intentionally exercise provider/API failures.
test.beforeEach(async ({ page }) => {
  const consoleErrors: string[] = [];
  const pageErrors: string[] = [];
  const failedRequests: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("requestfailed", (request) => {
    failedRequests.push(
      `${request.method()} ${request.url()} · ${request.failure()?.errorText ?? "failed"}`,
    );
  });
  await page.addInitScript(() => {
    (window as Window & { __averqelE2EDiagnostics?: unknown }).__averqelE2EDiagnostics = null;
  });
  const publish = () => {
    void page
      .evaluate(
        ({
          consoleErrors: nextConsoleErrors,
          pageErrors: nextPageErrors,
          failedRequests: nextFailedRequests,
        }) => {
          (window as Window & { __averqelE2EDiagnostics?: unknown }).__averqelE2EDiagnostics = {
            consoleErrors: nextConsoleErrors,
            pageErrors: nextPageErrors,
            failedRequests: nextFailedRequests,
          };
        },
        { consoleErrors, pageErrors, failedRequests },
      )
      .catch(() => undefined);
  };
  page.on("console", publish);
  page.on("pageerror", publish);
  page.on("requestfailed", publish);
});

export { expect } from "@playwright/test";
