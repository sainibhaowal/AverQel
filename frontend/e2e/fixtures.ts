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
    if (token) {
      await page.addInitScript(
        ({ accessToken, tenant }) => {
          window.localStorage.setItem("averqel_token", accessToken);
          if (tenant) window.localStorage.setItem("averqel_tenant_id", tenant);
        },
        { accessToken: token, tenant: tenantId ?? "" },
      );
    }
    await provide(page);
  },
});

export { expect } from "@playwright/test";
