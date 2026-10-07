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
      } else if (pathname === "/notifications" || pathname === "/collections/notifications") {
        body = [];
      } else if (pathname === "/providers" || pathname === "/providers/assignments") {
        body = emptyList;
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

export { expect } from "@playwright/test";
