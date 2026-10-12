import { describe, expect, it } from "vitest";

import {
  deepSpaceThreadReducer,
  initialDeepSpaceThreadState,
} from "../app/dashboard/deepspace/_lib/deepspace-thread";

describe("DeepSpace regeneration state", () => {
  it("keeps the old answer visible until the durable regeneration starts", () => {
    const message = {
      id: "assistant-saved-answer",
      role: "assistant" as const,
      content: "Saved answer",
      rawContent: "Saved answer",
      createdAt: "2026-01-01T00:00:00Z",
      status: "ready" as const,
      blocks: [],
      versions: [
        {
          id: "version-1",
          version_index: 1,
          content: "Saved answer",
          source_type: "assistant",
          created_at: "2026-01-01T00:00:00Z",
        },
      ],
    };
    const queuedState = {
      ...initialDeepSpaceThreadState,
      messages: [message],
    };

    expect(queuedState.messages[0]?.content).toBe("Saved answer");

    const streamingState = deepSpaceThreadReducer(queuedState, {
      type: "stream_event",
      event: {
        event: "start",
        data: {
          conversation_id: "conversation-1",
          message_id: message.id,
          regenerating: true,
        },
      },
    });

    expect(streamingState.messages[0]).toMatchObject({
      id: message.id,
      content: "",
      rawContent: "",
      status: "streaming",
      versions: message.versions,
    });
    expect(queuedState.messages[0]?.content).toBe("Saved answer");
  });
});
