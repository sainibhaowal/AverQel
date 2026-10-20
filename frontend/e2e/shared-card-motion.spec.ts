import { expect, test } from "@playwright/test";

test("shared panel edge stays still at rest and moves only during interaction", async ({ page }) => {
  await page.goto("/documentation");

  const panel = page.locator("nav.theme-panel");
  await expect(panel).toBeVisible();

  const idleAnimation = await panel.evaluate((element) =>
    getComputedStyle(element, "::after").animationName,
  );
  expect(idleAnimation).toBe("none");

  await panel.hover();
  const hoverAnimation = await panel.evaluate((element) =>
    getComputedStyle(element, "::after").animationName,
  );
  expect(hoverAnimation).toBe("border-trace");
});
