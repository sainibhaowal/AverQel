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
  await expect(heading).toContainText("Turn your documents into");
  await expect(heading).toContainText("grounded answers and useful work");
  await expect(page.getByText("Your Private AI Workspace")).toBeVisible();
  await expect(page.getByRole("link", { name: "Start Using AverQel" }).first()).toBeVisible();
  await expect.poll(() => hydrationErrors).toEqual([]);
});
