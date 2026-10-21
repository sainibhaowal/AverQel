import { expect, test } from "./fixtures";

const avatarImage =
  "data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciPjwvc3ZnPg==";

test("selected support user photo has no green tile, border, or shadow", async ({
  adminPage: page,
}) => {
  test.setTimeout(60_000);

  await page.addInitScript(() => {
    window.localStorage.setItem("averqel-theme", "light");
  });

  await page.route("**/api/v1/support/encryption/admin-private-key", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({
        status: 404,
        contentType: "application/json",
        body: JSON.stringify({ detail: "No admin key is registered." }),
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

  await page.route("**/api/v1/support/admin/queue**", async (route) => {
    const ticket = {
      id: "ticket-avatar-e2e",
      user_id: "avatar-user-e2e",
      user_email: "avatar-user@example.org",
      subject: "Avatar display check",
      description: "A fixture ticket for the avatar browser test.",
      category: "question",
      status: "open",
      priority: "normal",
      assigned_admin_id: null,
      created_at: "2026-10-20T09:00:00Z",
      updated_at: "2026-10-20T09:00:00Z",
      first_response_due_at: null,
      resolution_due_at: null,
      encrypted_payload: null,
    };

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        open_count: 1,
        overdue_count: 0,
        total: 1,
        users: [
          {
            user_id: "avatar-user-e2e",
            display_name: "Avatar User",
            avatar: avatarImage,
          },
        ],
        items: [ticket],
      }),
    });
  });

  await page.goto("/dashboard/admin/support", { waitUntil: "domcontentloaded" });
  await page.getByLabel("New passphrase (14+ characters)").fill("E2E-support-passphrase-2026");
  await page.getByLabel("Confirm passphrase").fill("E2E-support-passphrase-2026");
  await page.getByRole("button", { name: "Create encrypted key" }).click();

  const avatar = page.locator(`img[src="${avatarImage}"]`).first();
  await expect(avatar).toBeVisible();

  const avatarShell = avatar.locator("..");
  await expect(avatarShell).toHaveCSS("background-image", "none");
  await expect(avatarShell).toHaveCSS("background-color", "rgba(0, 0, 0, 0)");
  await expect(avatarShell).toHaveCSS("border-top-width", "0px");
  await expect(avatarShell).toHaveCSS("box-shadow", "none");
});
