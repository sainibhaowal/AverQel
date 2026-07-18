import { render, screen } from "@testing-library/react";

import AssistantMessage from "../app/dashboard/query/_components/AssistantMessage";
import type { QueryThreadMessage } from "../app/dashboard/query/_lib/stream-protocol";

const baseMessage: QueryThreadMessage = {
  id: "assistant-phase-1",
  role: "assistant",
  content: "",
  rawContent: "",
  createdAt: new Date().toISOString(),
  status: "streaming",
  citations: [],
  blocks: [],
  artifacts: [],
  trace: null,
  followups: [],
  statusHistory: [],
  output: [],
  files: [],
  structured: null,
  error: null,
  activeVersionId: "assistant-phase-1-v1",
  activeVersionIndex: 1,
  versionCount: 1,
  versions: [
    {
      id: "assistant-phase-1-v1",
      versionIndex: 1,
      sourceType: "initial",
      createdAt: new Date().toISOString(),
      content: "",
      rawContent: "",
      citations: [],
      blocks: [],
      artifacts: [],
      trace: null,
      followups: [],
      statusHistory: [],
      output: [],
      files: [],
      structured: null,
      error: null,
      status: "streaming",
    },
  ],
};

describe("stream phase UX", () => {
  it("shows explicit grounding state before answer text", () => {
    render(
      <AssistantMessage
        message={{ ...baseMessage, streamPhase: "grounding" }}
        isStreaming={true}
        onRetry={() => {}}
        onPreviewDocument={() => {}}
        onFollowupSelect={() => {}}
      />,
    );

    expect(screen.getByText(/grounding answer/i)).toBeInTheDocument();
  });
});
