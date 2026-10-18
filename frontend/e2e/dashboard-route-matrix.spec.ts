import { expect, test } from "./fixtures";

// This is a reachability matrix, not a substitute for the workflow suites.
// It catches route-level regressions (missing chunks, server errors, auth
// redirects, and shell crashes) for each major authenticated surface.
const authenticatedRoutes = [
  "/dashboard",
  "/dashboard/deepspace",
  "/dashboard/documents",
  "/dashboard/query",
  "/dashboard/collections",
  "/dashboard/mcp",
  "/dashboard/settings/profile",
  "/dashboard/settings/providers",
] as const;

test.describe("authenticated dashboard route matrix", () => {
  test.describe.configure({ timeout: 60_000 });

  test("renders the requested DeepSpace logo in the aligned nav slot", async ({
    authenticatedPage,
  }) => {
    await authenticatedPage.goto("/dashboard", { waitUntil: "domcontentloaded" });

    const deepSpaceLink = authenticatedPage.getByRole("link", { name: "DeepSpace", exact: true });
    await expect(deepSpaceLink).toBeVisible();
    await expect(deepSpaceLink).toContainText("DeepSpace");
    const deepSpaceMark = deepSpaceLink.locator("img");
    await expect(deepSpaceMark).toHaveAttribute(
      "src",
      /DeepSpace(?:%20| )Logo\/DeepSpace_Logo_Only_NoBlack_Exact\.svg/,
    );
    await expect(deepSpaceMark).toHaveAttribute("width", "18");
    await expect(deepSpaceMark).toHaveAttribute("height", "18");
    await expect(deepSpaceMark).toHaveCSS("display", "block");
    await expect(deepSpaceMark).toHaveCSS("object-fit", "contain");
  });

  test("renders one rotating wormhole asset beside the DeepSpace response avatar", async ({
    authenticatedPage,
  }) => {
    await authenticatedPage.goto("/dashboard/deepspace", { waitUntil: "domcontentloaded" });

    const wormhole = authenticatedPage.locator(".deepspace-wormhole").first();
    await expect(wormhole).toBeVisible({ timeout: 30_000 });
    const asset = wormhole.locator("img");
    await expect(asset).toHaveCount(1);
    await expect(asset).toHaveAttribute(
      "src",
      /AverQel(?:%20| )Logo\/deepspace-wormhole-aperture\.svg/,
    );
    await expect(asset).toHaveClass(/deepspace-wormhole__asset/);
    await expect(asset).toHaveCSS("animation-name", "deepspace-wormhole-rotate");
  });

  for (const route of authenticatedRoutes) {
    test(`${route} renders without a server error`, async ({ authenticatedPage }) => {
      const pageErrors: string[] = [];
      authenticatedPage.on("pageerror", (error) => pageErrors.push(error.message));
      const response = await authenticatedPage.goto(route, { waitUntil: "domcontentloaded" });
      expect(
        response?.status(),
        `${route} should return a successful document response`,
      ).toBeLessThan(400);
      await expect(authenticatedPage.locator("body")).not.toContainText("Internal Server Error");
      await expect(authenticatedPage.locator("body")).not.toContainText("Application error");
      await authenticatedPage.waitForTimeout(250);
      expect(pageErrors, `${route} should not throw in the browser`).toEqual([]);
    });
  }
});
