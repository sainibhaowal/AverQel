import { expect, test } from "@playwright/test";

test("homepage renders the visual workspace hero without hydration failures", async ({ page }) => {
  const hydrationErrors: string[] = [];
  page.on("pageerror", (error) => {
    if (/hydration|Minified React error #418/i.test(error.message)) {
      hydrationErrors.push(error.message);
    }
  });

  await page.goto("/");

  const heading = page.getByRole("heading", { level: 1 });
  await expect(heading).toHaveText("One workspace for knowledge, AI, and action.");
  await expect(page.getByText("Your Connected AI Workspace")).toBeVisible();
  await expect(page.getByRole("link", { name: "Create your workspace" })).toBeVisible();
  await expect.poll(() => hydrationErrors).toEqual([]);
});
