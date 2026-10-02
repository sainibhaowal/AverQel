import { expect, test } from "./fixtures";

const configured =
  process.env.DEEPSPACE_E2E_ENABLED === "1" &&
  Boolean(process.env.DEEPSPACE_E2E_STORAGE_STATE || process.env.DEEPSPACE_E2E_AUTH_TOKEN);

test.describe("DeepSpace heavy Library authenticated matrix", () => {
  test.skip(!configured, "Set DEEPSPACE_E2E_ENABLED=1 with staging auth to run this matrix.");

  for (const viewport of ["desktop", "tablet"] as const) {
    test(`${viewport} keeps Library and artifact surfaces reachable`, async ({
      authenticatedPage,
    }) => {
      await authenticatedPage.setViewportSize(
        viewport === "desktop" ? { width: 1440, height: 900 } : { width: 900, height: 900 },
      );
      await authenticatedPage.goto("/dashboard/deepspace");
      await expect(authenticatedPage.getByText(/DeepSpace/i).first()).toBeVisible();
      await expect(authenticatedPage.locator("body")).not.toContainText("Internal Server Error");
    });
  }
});
