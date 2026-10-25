import { expect, test } from "./fixtures";

test.describe("DeepSpace table action overlay", () => {
  test.describe.configure({ timeout: 60_000 });

  test("opens Export below its button over the table without moving rows", async ({
    authenticatedPage,
  }) => {
    const conversationId = "00000000-0000-0000-0000-000000000301";
    const messageId = "00000000-0000-0000-0000-000000000402";
    const markdown = [
      "| Production need | Available option |",
      "| --- | --- |",
      "| Deep reasoning | Ultra |",
      "| Whole-repo context | Ultra / Lightning |",
    ].join("\n");
    let answerAvailable = false;

    await authenticatedPage.route(
      `**/api/v1/deepspace/chats/${conversationId}/messages`,
      async (route) => {
        if (route.request().method() !== "GET") {
          await route.fallback();
          return;
        }
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            messages: answerAvailable
              ? [
                  {
                    id: messageId,
                    role: "assistant",
                    content: markdown,
                    metadata_json: {},
                    created_at: "2026-10-23T10:00:00Z",
                    active_version_id: "table-actions-e2e-version",
                    active_version_index: 1,
                    version_count: 1,
                    versions: [],
                  },
                ]
              : [],
          }),
        });
      },
    );

    await authenticatedPage.route("**/api/v1/deepspace/chats/stream", async (route) => {
      answerAvailable = true;
      await route.fulfill({
        status: 200,
        contentType: "text/event-stream; charset=utf-8",
        headers: { "Cache-Control": "no-cache" },
        body:
          `event: start\ndata: ${JSON.stringify({ conversation_id: conversationId, message_id: messageId })}\n\n` +
          `event: delta\ndata: ${JSON.stringify({ text: markdown })}\n\n` +
          `event: done\ndata: ${JSON.stringify({ conversation_id: conversationId, message_id: messageId, status: "ready" })}\n\n`,
      });
    });

    await authenticatedPage.goto("/dashboard/deepspace", { waitUntil: "domcontentloaded" });
    const composer = authenticatedPage.getByPlaceholder("Message DeepSpace...");
    await expect(composer).toBeVisible();
    await composer.fill("Compare these production needs");
    await authenticatedPage.getByRole("button", { name: "Send message" }).click();

    const table = authenticatedPage.getByRole("table");
    await expect(table).toBeVisible();
    const exportButton = authenticatedPage.getByRole("button", { name: "Export table" });
    await table.hover();

    const toolbar = exportButton.locator("xpath=ancestor::*[@role='group'][1]").locator("xpath=..");
    await expect(toolbar).toHaveCSS("opacity", "1");
    const tableBefore = await table.boundingBox();
    const headerBefore = await table.locator("thead tr").boundingBox();
    const buttonBox = await exportButton.boundingBox();
    await exportButton.click();

    const menu = authenticatedPage.locator("[data-table-export-menu]");
    await expect(menu).toBeVisible();
    await expect(menu.getByRole("button", { name: "CSV" })).toBeVisible();
    const menuBox = await menu.boundingBox();
    const tableAfter = await table.boundingBox();

    expect(buttonBox).not.toBeNull();
    expect(menuBox).not.toBeNull();
    expect(tableBefore).not.toBeNull();
    expect(headerBefore).not.toBeNull();
    expect(tableAfter?.y).toBe(tableBefore?.y);
    expect(menuBox!.y).toBeGreaterThanOrEqual(buttonBox!.y + buttonBox!.height);
    expect(Math.abs(menuBox!.x + menuBox!.width - (buttonBox!.x + buttonBox!.width))).toBeLessThan(
      8,
    );
    expect(menuBox!.y).toBeLessThan(headerBefore!.y + headerBefore!.height);
    expect(await menu.evaluate((element) => element.parentElement === document.body)).toBe(true);
  });
});
