import { expect, test } from "./fixtures";

test("feedback campaign empty state has readable light-theme contrast", async ({
  authenticatedPage: page,
}) => {
  test.setTimeout(60_000);

  await page.addInitScript(() => {
    window.localStorage.setItem("averqel-theme", "light");
  });

  await page.route("**/api/v1/support/encryption/admin-public-key", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ key_id: "e2e-admin-key", public_key: "e2e-admin-public-key" }),
    });
  });

  await page.route("**/api/v1/support/encryption/me", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({
        status: 404,
        contentType: "application/json",
        body: JSON.stringify({ detail: "No support key is registered." }),
      });
      return;
    }

    const backup = route.request().postDataJSON() as { key_id: string; public_key: string };
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ key_id: backup.key_id, public_key: backup.public_key }),
    });
  });

  await page.route("**/api/v1/app-feedback/campaigns", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: "[]" });
  });

  await page.route("**/api/v1/app-feedback/mine", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: "[]" });
  });

  await page.goto("/dashboard/feedback", { waitUntil: "domcontentloaded" });
  await page.getByLabel("New passphrase (14+ characters)").fill("E2E-feedback-passphrase-2026");
  await page.getByLabel("Confirm passphrase").fill("E2E-feedback-passphrase-2026");
  await page.getByRole("button", { name: "Create encrypted key" }).click();

  const emptyState = page.locator(".feedback-campaigns-empty");
  await expect(emptyState).toContainText(
    "No campaigns are active right now. You can still submit feedback using the form.",
  );
  await expect(emptyState).toHaveCSS("border-top-color", "rgb(97, 148, 119)");
  await expect(emptyState).toHaveCSS("background-image", /linear-gradient/);
  await expect(emptyState.locator("p")).toHaveCSS("color", "rgb(49, 88, 68)");
  await expect(page.locator("html")).not.toHaveClass(/dark/);
});
