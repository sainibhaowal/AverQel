import { render, screen } from "@testing-library/react";

import AssistantMessage from "../app/dashboard/query/_components/AssistantMessage";
import type { QueryThreadMessage } from "../app/dashboard/query/_lib/stream-protocol";

const message: QueryThreadMessage = {
  id: "assistant-mobile-1",
  role: "assistant",
  content: "## Mobile summary\n\nThe answer layout should remain readable on smaller widths.",
  rawContent: "## Mobile summary\n\nThe answer layout should remain readable on smaller widths.",
  createdAt: new Date().toISOString(),
  status: "ready",
  citations: [],
  blocks: [
    {
      id: "followup-card-1",
      type: "card",
      title: "Mobile block",
      content: "Cards should not break the reading rhythm.",
      tone: "info",
    },
  ],
  artifacts: [],
  trace: null,
  followups: ["Open the supporting source"],
  statusHistory: [],
  output: [],
  files: [],
  structured: null,
  error: null,
  activeVersionId: "assistant-mobile-1-v1",
  activeVersionIndex: 1,
  versionCount: 1,
  versions: [
    {
      id: "assistant-mobile-1-v1",
      versionIndex: 1,
      sourceType: "initial",
      createdAt: new Date().toISOString(),
      content: "## Mobile summary\n\nThe answer layout should remain readable on smaller widths.",
      rawContent:
        "## Mobile summary\n\nThe answer layout should remain readable on smaller widths.",
      citations: [],
      blocks: [
        {
          id: "followup-card-1",
          type: "card",
          title: "Mobile block",
          content: "Cards should not break the reading rhythm.",
          tone: "info",
        },
      ],
      artifacts: [],
      trace: null,
      followups: ["Open the supporting source"],
      statusHistory: [],
      output: [],
      files: [],
      structured: null,
      error: null,
      status: "ready",
    },
  ],
};

describe("query mobile layout regression", () => {
  it("keeps the answer body and followups present without rendering decorative card panels", () => {
    render(
      <AssistantMessage
        message={message}
        isStreaming={false}
        onRetry={() => {}}
        onPreviewDocument={() => {}}
        onFollowupSelect={() => {}}
      />,
    );

    expect(screen.getByText("Mobile summary")).toBeInTheDocument();
    expect(screen.queryByText("Mobile block")).not.toBeInTheDocument();
    expect(screen.getByText("Open the supporting source")).toBeInTheDocument();
  });
});
