import { test as base, type Page } from "@playwright/test";

type DeepSpaceFixtures = {
  authenticatedPage: Page;
};

/**
 * Staging authentication is supplied through Playwright storage state or a
 * short-lived staging token. No production credentials belong in the repo.
 */
export const test = base.extend<DeepSpaceFixtures>({
  authenticatedPage: async ({ page }, provide) => {
    const token = process.env.DEEPSPACE_E2E_AUTH_TOKEN;
    const tenantId = process.env.DEEPSPACE_E2E_TENANT_ID;
    const userId = process.env.DEEPSPACE_E2E_USER_ID;
    const userEmail = process.env.DEEPSPACE_E2E_USER_EMAIL;
    const roles = (process.env.DEEPSPACE_E2E_ROLES ?? "user")
      .split(",")
      .map((role) => role.trim())
      .filter(Boolean);
    if (token) {
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
    await provide(page);
  },
});

export { expect } from "@playwright/test";
