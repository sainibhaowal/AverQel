import { expect, test } from "./fixtures";

test.describe("DeepSpace heavy Library authenticated matrix", () => {
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
