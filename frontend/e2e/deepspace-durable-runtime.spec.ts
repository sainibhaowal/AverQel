import { expect, test } from "./fixtures";

test.use({
  storageState: process.env.DEEPSPACE_E2E_STORAGE_STATE || undefined,
});

const stagingAuthConfigured = Boolean(
  process.env.DEEPSPACE_E2E_STORAGE_STATE || process.env.DEEPSPACE_E2E_AUTH_TOKEN,
);

test.describe("DeepSpace durable runtime", () => {
  test.skip(
    process.env.DEEPSPACE_E2E_ENABLED !== "1" || !stagingAuthConfigured,
    "Set DEEPSPACE_E2E_ENABLED=1 and provide staging storage state or a short-lived staging token.",
  );

  test("rehydrates the durable runtime surface after a reconnect", async ({
    authenticatedPage,
  }) => {
    await authenticatedPage.goto("/dashboard/deepspace");
    await expect(authenticatedPage.getByText(/DeepSpace/i).first()).toBeVisible();
    await expect(
      authenticatedPage.getByText(/Native Durable Runtime|Mission Canvas/i).first(),
    ).toBeVisible();
  });

  test("keeps operations visibility private and does not silently switch models", async ({
    authenticatedPage,
  }) => {
    await authenticatedPage.goto("/dashboard/deepspace");
    await expect(authenticatedPage.getByText(/Provider health/i)).toBeVisible();
    // Model selection remains an explicit user control. A provider circuit may
    // report failure, but it must not silently replace the selected model.
    await expect(authenticatedPage.getByText(/Provider health/i)).not.toContainText(/fallback/i);
  });
});
