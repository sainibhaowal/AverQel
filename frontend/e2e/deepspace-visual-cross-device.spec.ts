import { expect, test } from "./fixtures";

const conversationId = "00000000-0000-0000-0000-000000000301";
const messageId = "00000000-0000-0000-0000-000000000399";
const blockId = "cross-device-chart";

test.describe("DeepSpace visual cross-device persistence", () => {
  test("a revisioned chart edit reloads in a second authenticated browser context", async ({
    authenticatedPage,
    browser,
  }) => {
    let block: Record<string, unknown> = {
      id: blockId,
      block_id: blockId,
      type: "chart",
      title: "Cross-device trend",
      chart_type: "line",
      series: [
        { label: "Q1", value: 10 },
        { label: "Q2", value: 20 },
      ],
      revision: 0,
      schema_version: 1,
    };
    let revision = 0;
    const message = () => ({
      id: messageId,
      role: "assistant",
      content: `\`\`\`chart\n${JSON.stringify(block)}\n\`\`\``,
      metadata_json: {
        visual_blocks: { [blockId]: { revision, schema_version: 1, block } },
      },
      created_at: "2026-10-16T10:00:00Z",
      active_version_id: "version-1",
      active_version_index: 1,
      version_count: 1,
      versions: [],
    });

    const installVisualApi = async (page: typeof authenticatedPage) => {
      await page.route(
        (url) =>
          new URL(url).pathname ===
          `/api/v1/deepspace/chats/${conversationId}/messages/${messageId}/visual-block`,
        async (route) => {
          const request = route.request().postDataJSON() as {
            expected_revision?: number;
            block: Record<string, unknown>;
          };
          if (request.expected_revision !== revision) {
            await route.fulfill({ status: 409, contentType: "application/json", body: "{}" });
            return;
          }
          revision += 1;
          block = { ...request.block, revision, source_markdown: null };
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify(message()),
          });
        },
      );
      await page.route(
        (url) => new URL(url).pathname === `/api/v1/deepspace/chats/${conversationId}/messages`,
        async (route) => {
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({ messages: [message()] }),
          });
        },
      );
    };

    await installVisualApi(authenticatedPage);
    await authenticatedPage.route("**/login", (route) =>
      route.fulfill({
        status: 200,
        contentType: "text/html",
        body: "<!doctype html><title>E2E</title>",
      }),
    );
    await authenticatedPage.goto("/login", { waitUntil: "domcontentloaded" });
    const edit = await authenticatedPage.evaluate(
      async ({ conversationId, messageId }) => {
        const token = window.localStorage.getItem("averqel_token");
        const response = await fetch(
          `/api/v1/deepspace/chats/${conversationId}/messages/${messageId}/visual-block`,
          {
            method: "PATCH",
            headers: {
              "Content-Type": "application/json",
              ...(token ? { Authorization: `Bearer ${token}` } : {}),
            },
            body: JSON.stringify({
              block_id: "cross-device-chart",
              expected_revision: 0,
              block: {
                id: "cross-device-chart",
                block_id: "cross-device-chart",
                type: "chart",
                title: "Cross-device trend",
                chart_type: "line",
                series: [
                  { label: "Q1", value: 99 },
                  { label: "Q2", value: 20 },
                ],
                revision: 1,
                schema_version: 1,
              },
            }),
          },
        );
        return { status: response.status, message: await response.json() };
      },
      { conversationId, messageId },
    );
    expect(edit.status).toBe(200);
    expect(revision).toBe(1);

    const secondContext = await browser.newContext();
    const authState = await authenticatedPage.evaluate(() => ({
      token: window.localStorage.getItem("averqel_token"),
      tenant: window.localStorage.getItem("averqel_tenant_id"),
      user: window.localStorage.getItem("averqel_user"),
    }));
    await secondContext.addInitScript((state) => {
      if (state.token) window.localStorage.setItem("averqel_token", state.token);
      if (state.tenant) window.localStorage.setItem("averqel_tenant_id", state.tenant);
      if (state.user) window.localStorage.setItem("averqel_user", state.user);
    }, authState);
    const secondPage = await secondContext.newPage();
    await secondPage.route("**/login", (route) =>
      route.fulfill({
        status: 200,
        contentType: "text/html",
        body: "<!doctype html><title>E2E</title>",
      }),
    );
    await secondPage.route("**/api/v1/**", async (route) => {
      await route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
    });
    await installVisualApi(secondPage);
    try {
      await secondPage.goto("/login", { waitUntil: "domcontentloaded" });
      const reload = await secondPage.evaluate(async (conversationId) => {
        const token = window.localStorage.getItem("averqel_token");
        const response = await fetch(`/api/v1/deepspace/chats/${conversationId}/messages`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        return { status: response.status, payload: await response.json() };
      }, conversationId);
      expect(reload.status).toBe(200);
      expect(reload.payload.messages[0].content).toContain('"value":99');
      expect(reload.payload.messages[0].metadata_json.visual_blocks[blockId].revision).toBe(1);
    } finally {
      await secondContext.close();
    }
  });
});
