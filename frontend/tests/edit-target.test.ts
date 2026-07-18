import { describe, expect, it, vi } from "vitest";

import { resolveLatestEditableMessageId } from "../app/dashboard/query/_lib/edit-target";

describe("resolveLatestEditableMessageId", () => {
  it("returns the latest persisted user message id from conversation history", async () => {
    const fetcher = vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            messages: [
              { id: "assistant-1", role: "assistant" },
              { id: "019dca4d-cb43-7721-a11b-6f9a3d131a6b", role: "user" },
              { id: "assistant-2", role: "assistant" },
            ],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
    );

    await expect(
      resolveLatestEditableMessageId({
        fetcher,
        endpointBase: "/deepspace/chats",
        conversationId: "conv-1",
        fallbackMessageId: "user_1777216373516_0v7i3arc",
      }),
    ).resolves.toBe("019dca4d-cb43-7721-a11b-6f9a3d131a6b");
  });

  it("falls back to the provided id when history cannot be loaded", async () => {
    const fetcher = vi.fn(async () => new Response("not found", { status: 404 }));

    await expect(
      resolveLatestEditableMessageId({
        fetcher,
        endpointBase: "/deepspace/chats",
        conversationId: "conv-1",
        fallbackMessageId: "user_1777216373516_0v7i3arc",
      }),
    ).resolves.toBe("user_1777216373516_0v7i3arc");
  });
});
