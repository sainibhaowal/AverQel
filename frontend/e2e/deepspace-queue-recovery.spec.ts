import { expect, test } from "./fixtures";

const conversationId = "00000000-0000-0000-0000-000000000301";

test.describe("DeepSpace queue recovery", () => {
  // The isolated Next server compiles this large route on first use.
  test.describe.configure({ timeout: 60_000 });

  test("resumes the queue and waits for a worker claim before attaching", async ({
    authenticatedPage,
  }) => {
    let paused = true;
    let workerClaimed = false;
    let workerStarted = false;
    const streamBodies: Array<Record<string, unknown>> = [];

    await authenticatedPage.route(
      `**/api/v1/deepspace/chats/${conversationId}/queue/state`,
      async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            paused,
            active_request_id: workerClaimed ? "queued-next" : null,
          }),
        });
      },
    );
    await authenticatedPage.route(
      `**/api/v1/deepspace/chats/${conversationId}/queue`,
      async (route) => {
        const turns = workerStarted
          ? []
          : [
              {
                client_request_id: "queued-next",
                prompt: "Run the first pending prompt",
                priority: 0,
                sequence: 1,
                status: "queued",
              },
            ];
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(turns),
        });
      },
    );
    await authenticatedPage.route(
      `**/api/v1/deepspace/chats/${conversationId}/queue/resume`,
      async (route) => {
        paused = false;
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ paused: false, active_request_id: null }),
        });
      },
    );
    await authenticatedPage.route("**/api/v1/deepspace/chats/stream", async (route) => {
      const body = JSON.parse(route.request().postData() ?? "{}") as Record<string, unknown>;
      streamBodies.push(body);
      workerStarted = true;
      await route.fulfill({
        status: 200,
        contentType: "text/event-stream; charset=utf-8",
        headers: { "Cache-Control": "no-cache" },
        body:
          `event: start\ndata: {"conversation_id":"${conversationId}","message_id":"assistant-next","client_request_id":"queued-next"}\n\n` +
          `event: done\ndata: {"conversation_id":"${conversationId}","message_id":"assistant-next","status":"completed"}\n\n`,
      });
    });

    await authenticatedPage.goto("/dashboard/deepspace");
    const resumeButton = authenticatedPage.getByRole("button", { name: "Resume queue" });
    await expect(resumeButton).toBeVisible();
    await expect(authenticatedPage.getByText("Run the first pending prompt")).toBeVisible();
    await resumeButton.click();

    await expect.poll(() => streamBodies.length).toBe(0);
    workerClaimed = true;
    await expect.poll(() => streamBodies.length).toBe(1);
    expect(streamBodies[0]).toMatchObject({
      conversation_id: conversationId,
      client_request_id: "queued-next",
      reconnect: true,
    });
    await expect(authenticatedPage.getByRole("button", { name: "Resume queue" })).toHaveCount(0);
  });

  test("retries a failed prompt as a new request and reconnects to that attempt", async ({
    authenticatedPage,
  }) => {
    let retryCreated = false;
    let workerClaimed = false;
    const retryPayload: { current: Record<string, unknown> | null } = { current: null };
    const streamBodies: Array<Record<string, unknown>> = [];

    await authenticatedPage.route(
      `**/api/v1/deepspace/chats/${conversationId}/queue/state`,
      async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            paused: false,
            active_request_id: retryCreated && workerClaimed ? "retry-attempt" : null,
          }),
        });
      },
    );
    await authenticatedPage.route(
      `**/api/v1/deepspace/chats/${conversationId}/queue`,
      async (route) => {
        const turns = retryCreated
          ? [
              {
                client_request_id: "retry-attempt",
                prompt: "Retry this saved prompt",
                priority: 1,
                sequence: 2,
                status: "queued",
              },
            ]
          : [
              {
                client_request_id: "failed-turn",
                prompt: "Retry this saved prompt",
                priority: 0,
                sequence: 1,
                status: "failed",
                error: "provider temporarily unavailable",
              },
            ];
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(turns),
        });
      },
    );
    await authenticatedPage.route(
      `**/api/v1/deepspace/chats/${conversationId}/queue/failed-turn/retry`,
      async (route) => {
        retryPayload.current = JSON.parse(route.request().postData() ?? "{}") as Record<
          string,
          unknown
        >;
        retryCreated = true;
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            client_request_id: "retry-attempt",
            prompt: "Retry this saved prompt",
            priority: 1,
            sequence: 2,
            status: "queued",
          }),
        });
      },
    );
    await authenticatedPage.route("**/api/v1/deepspace/chats/stream", async (route) => {
      const body = JSON.parse(route.request().postData() ?? "{}") as Record<string, unknown>;
      streamBodies.push(body);
      await route.fulfill({
        status: 200,
        contentType: "text/event-stream; charset=utf-8",
        headers: { "Cache-Control": "no-cache" },
        body:
          `event: start\ndata: {"conversation_id":"${conversationId}","message_id":"assistant-retry","client_request_id":"retry-attempt"}\n\n` +
          `event: lifecycle\ndata: {"phase":"retry_from_start","message":"Restarting the saved prompt."}\n\n` +
          `event: done\ndata: {"conversation_id":"${conversationId}","message_id":"assistant-retry","status":"completed"}\n\n`,
      });
    });

    await authenticatedPage.goto("/dashboard/deepspace");
    await authenticatedPage.getByRole("button", { name: "Retry prompt" }).click();

    await expect.poll(() => streamBodies.length).toBe(0);
    workerClaimed = true;
    await expect.poll(() => streamBodies.length).toBe(1);
    expect(retryPayload.current?.client_request_id).toEqual(expect.any(String));
    expect(streamBodies[0]).toMatchObject({
      conversation_id: conversationId,
      client_request_id: "retry-attempt",
      reconnect: true,
    });
  });

  test("edits a pending prompt in place and preserves its FIFO position", async ({
    authenticatedPage,
  }) => {
    const queueRows = [
      {
        client_request_id: "queue-first",
        prompt: "First pending prompt",
        priority: 0,
        sequence: 1,
        status: "queued",
      },
      {
        client_request_id: "queue-middle",
        prompt: "Original middle prompt",
        priority: 0,
        sequence: 2,
        status: "queued",
      },
      {
        client_request_id: "queue-last",
        prompt: "Last pending prompt",
        priority: 0,
        sequence: 3,
        status: "queued",
      },
    ];
    const editPayload: { current: Record<string, unknown> | null } = { current: null };

    await authenticatedPage.route(
      `**/api/v1/deepspace/chats/${conversationId}/queue`,
      async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(queueRows),
        });
      },
    );
    await authenticatedPage.route(
      `**/api/v1/deepspace/chats/${conversationId}/queue/queue-middle`,
      async (route) => {
        editPayload.current = JSON.parse(route.request().postData() ?? "{}") as Record<
          string,
          unknown
        >;
        queueRows[1]!.prompt = String(editPayload.current.message);
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(queueRows[1]),
        });
      },
    );

    await authenticatedPage.goto("/dashboard/deepspace");
    await authenticatedPage.getByRole("button", { name: "Edit queued message 2" }).click();
    const composer = authenticatedPage.getByPlaceholder("Edit queued prompt…");
    await expect(composer).toHaveValue("Original middle prompt");
    await composer.fill("Revised middle prompt");
    await authenticatedPage.getByRole("button", { name: "Save queued prompt" }).click();

    await expect
      .poll(() => editPayload.current)
      .toEqual({ message: "Revised middle prompt", expected_prompt: "Original middle prompt" });
    const queue = authenticatedPage.locator('[aria-label="Queued messages"]');
    const rowIds = await queue
      .locator("[data-queue-turn-id]")
      .evaluateAll((rows) => rows.map((row) => row.getAttribute("data-queue-turn-id")));
    expect(rowIds).toEqual(["queue-first", "queue-middle", "queue-last"]);
    await expect(queue.locator('[data-queue-turn-id="queue-middle"]')).toContainText(
      "Revised middle prompt",
    );
    await expect(queue.getByText("Original middle prompt")).toHaveCount(0);
    await expect(authenticatedPage.getByPlaceholder("Message DeepSpace...")).toBeVisible();
  });

  test("queues regeneration from the saved turn and keeps its answer visible until start", async ({
    authenticatedPage,
  }) => {
    const assistantMessageId = "00000000-0000-0000-0000-000000000302";
    const userMessageId = "00000000-0000-0000-0000-000000000303";
    const history = [
      {
        id: userMessageId,
        role: "user",
        content: "Summarize the saved report",
        metadata_json: {},
        created_at: "2026-01-01T00:00:00Z",
        versions: [],
      },
      {
        id: assistantMessageId,
        role: "assistant",
        content: "Saved answer",
        metadata_json: { status: "ready" },
        created_at: "2026-01-01T00:00:01Z",
        active_version_index: 1,
        version_count: 1,
        versions: [
          {
            id: "00000000-0000-0000-0000-000000000304",
            version_index: 1,
            content: "Saved answer",
            source_type: "assistant",
            created_at: "2026-01-01T00:00:01Z",
          },
        ],
      },
    ];
    let queuedAt: number | null = null;
    let requestPayload: Record<string, unknown> | null = null;
    let resolveStreamRequest: (() => void) | undefined;
    const streamRequestReceived = new Promise<void>((resolve) => {
      resolveStreamRequest = resolve;
    });
    let streamBody: Record<string, unknown> | null = null;

    await authenticatedPage.route(
      `**/api/v1/deepspace/chats/${conversationId}/messages`,
      async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ messages: history }),
        });
      },
    );
    await authenticatedPage.route(
      `**/api/v1/deepspace/chats/${conversationId}/queue/state`,
      async (route) => {
        const workerClaimed = queuedAt !== null && Date.now() - queuedAt >= 500;
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            paused: false,
            active_request_id: workerClaimed ? "regen-run" : null,
          }),
        });
      },
    );
    await authenticatedPage.route(
      `**/api/v1/deepspace/chats/${conversationId}/queue`,
      async (route) => {
        if (route.request().method() === "POST") {
          requestPayload = JSON.parse(route.request().postData() ?? "{}") as Record<
            string,
            unknown
          >;
          queuedAt = Date.now();
        }
        const workerClaimed = queuedAt !== null && Date.now() - queuedAt >= 500;
        const turn = {
          client_request_id: "regen-run",
          regenerate_message_id: assistantMessageId,
          prompt: "Summarize the saved report",
          priority: 0,
          sequence: 1,
          status: workerClaimed ? "running" : "queued",
        };
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(route.request().method() === "POST" || queuedAt ? [turn] : []),
        });
      },
    );
    await authenticatedPage.route("**/api/v1/deepspace/chats/stream", async (route) => {
      streamBody = JSON.parse(route.request().postData() ?? "{}") as Record<string, unknown>;
      resolveStreamRequest?.();
      await new Promise((resolve) => setTimeout(resolve, 300));
      history[1]!.content = "Fresh regenerated answer";
      history[1]!.metadata_json = { status: "ready" };
      await route.fulfill({
        status: 200,
        contentType: "text/event-stream; charset=utf-8",
        headers: { "Cache-Control": "no-cache" },
        body:
          `event: start\ndata: {"conversation_id":"${conversationId}","message_id":"${assistantMessageId}","regenerating":true}\n\n` +
          `event: delta\ndata: {"text":"Fresh regenerated answer"}\n\n` +
          `event: done\ndata: {"conversation_id":"${conversationId}","message_id":"${assistantMessageId}","status":"ready"}\n\n`,
      });
    });

    await authenticatedPage.goto("/dashboard/deepspace");
    await expect(authenticatedPage.getByText("Saved answer", { exact: true })).toBeVisible();
    await authenticatedPage.getByRole("button", { name: "Regenerate response" }).click();

    await streamRequestReceived;
    await expect(authenticatedPage.getByText("Saved answer", { exact: true })).toBeVisible();
    expect(requestPayload).toMatchObject({
      message: "",
      regenerate_message_id: assistantMessageId,
    });
    expect(streamBody).toMatchObject({
      conversation_id: conversationId,
      client_request_id: "regen-run",
      reconnect: true,
    });
    await expect(
      authenticatedPage.getByText("Fresh regenerated answer", { exact: true }),
    ).toBeVisible();
  });
});
