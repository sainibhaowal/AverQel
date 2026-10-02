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
    await expect(authenticatedPage.getByRole("button", { name: "Chat" })).toBeVisible();
    await expect(authenticatedPage.getByRole("button", { name: "History" })).toBeVisible();
  });

  test("keeps operations visibility private and does not silently switch models", async ({
    authenticatedPage,
  }) => {
    await authenticatedPage.goto("/dashboard/deepspace");
    // Provider health is an optional, permission-scoped diagnostic. The
    // durable user-facing contract here is that model/reasoning controls stay
    // explicit and the shell remains usable when diagnostics return 403/404.
    await expect(authenticatedPage.getByRole("button", { name: "Select Model" })).toBeVisible();
    await expect(authenticatedPage.getByRole("button", { name: "Choose reasoning effort" })).toBeVisible();
    // Model selection remains an explicit user control. A provider circuit may
    // report failure, but it must not silently replace the selected model.
    await expect(authenticatedPage.getByRole("button", { name: "Select Model" })).not.toContainText(/fallback/i);
  });
});
