import { expect, test } from "@playwright/test";

test("homepage loads and shows the production agentic layer hero", async ({ page }) => {
  await page.goto("/");

  const heading = page.getByRole("heading", { level: 1 });
  await expect(heading).toContainText("The operator-grade agentic system for your");
  await expect(heading).toContainText("research, documents, and productive work");
  await expect(page.getByText("Operator-Grade Agentic Operating Layer")).toBeVisible();
  await expect(page.getByRole("link", { name: "Get Started" })).toBeVisible();
});
