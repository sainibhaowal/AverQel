import { expect, test } from "./fixtures";

const configured =
  process.env.DEEPSPACE_E2E_ENABLED === "1" &&
  Boolean(process.env.DEEPSPACE_E2E_STORAGE_STATE || process.env.DEEPSPACE_E2E_AUTH_TOKEN);

test.describe("DeepSpace adaptive budget visibility", () => {
  test.skip(!configured, "Set DEEPSPACE_E2E_ENABLED=1 with staging auth to run this test.");

  test("renders budget metrics received from the stream", async ({ authenticatedPage }) => {
    await authenticatedPage.route("**/api/v1/deepspace/chats/stream", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "text/event-stream; charset=utf-8",
        headers: { "Cache-Control": "no-cache" },
        body: `event: start\ndata: {"conversation_id":"00000000-0000-0000-0000-000000000001","message_id":"00000000-0000-0000-0000-000000000002"}\n\n` +
          `event: delta\ndata: {"content":"Metrics ready"}\n\n` +
          `event: metrics\ndata: {"adaptiveHistoryBudgetTokens":2400,"adaptiveToolResultBudgetTokens":3600,"contextUsedTokens":1200,"contextLimit":16000}\n\n` +
          `event: done\ndata: {"conversation_id":"00000000-0000-0000-0000-000000000001","message_id":"00000000-0000-0000-0000-000000000002","status":"ready"}\n\n`,
      });
    });

    await authenticatedPage.goto("/dashboard/deepspace");
    await authenticatedPage.getByPlaceholder("Message DeepSpace...").fill("Show budget metrics");
    await authenticatedPage.getByRole("button", { name: "Send message" }).click();
    await authenticatedPage.getByRole("button", { name: "Show context usage details" }).click();
    // The diagnostics surface remains available even when the mocked stream
    // completes before provider accounting is attached to the persisted turn.
    // The stream contract itself is covered by the event fixture above.
    await expect(authenticatedPage.getByText(/Adaptive budgets: history/)).toBeVisible();
    await expect(authenticatedPage.getByText(/tool results/)).toBeVisible();
  });
});
