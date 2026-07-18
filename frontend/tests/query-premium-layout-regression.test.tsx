import { render, screen } from "@testing-library/react";

import AssistantMessage from "../app/dashboard/query/_components/AssistantMessage";
import type { QueryThreadMessage } from "../app/dashboard/query/_lib/stream-protocol";

const message: QueryThreadMessage = {
  id: "assistant-premium-1",
  role: "assistant",
  content:
    "### Summary\n\nThe answer body remains primary while structured blocks stay integrated.",
  rawContent:
    "### Summary\n\nThe answer body remains primary while structured blocks stay integrated.",
  createdAt: new Date().toISOString(),
  status: "ready",
  citations: [],
  blocks: [
    {
      id: "card-1",
      type: "card",
      title: "Key Finding",
      content: "Blocks should feel native to the answer surface.",
      tone: "info",
    },
  ],
  artifacts: [],
  trace: null,
  followups: ["Show the source evidence"],
  statusHistory: [],
  output: [],
  files: [],
  structured: null,
  error: null,
  activeVersionId: "assistant-premium-1-v1",
  activeVersionIndex: 1,
  versionCount: 1,
  versions: [
    {
      id: "assistant-premium-1-v1",
      versionIndex: 1,
      sourceType: "initial",
      createdAt: new Date().toISOString(),
      content:
        "### Summary\n\nThe answer body remains primary while structured blocks stay integrated.",
      rawContent:
        "### Summary\n\nThe answer body remains primary while structured blocks stay integrated.",
      citations: [],
      blocks: [
        {
          id: "card-1",
          type: "card",
          title: "Key Finding",
          content: "Blocks should feel native to the answer surface.",
          tone: "info",
        },
      ],
      artifacts: [],
      trace: null,
      followups: ["Show the source evidence"],
      statusHistory: [],
      output: [],
      files: [],
      structured: null,
      error: null,
      status: "ready",
    },
  ],
};

describe("premium assistant layout regression", () => {
  it("renders answer text and followups while ignoring decorative card blocks", () => {
    render(
      <AssistantMessage
        message={message}
        isStreaming={false}
        onRetry={() => {}}
        onPreviewDocument={() => {}}
        onFollowupSelect={() => {}}
      />,
    );

    expect(screen.getByText("Summary")).toBeInTheDocument();
    expect(screen.queryByText("Key Finding")).not.toBeInTheDocument();
    expect(screen.getByText("Show the source evidence")).toBeInTheDocument();
    expect(screen.getByText("AverQel AI")).toBeInTheDocument();
  });

  it("keeps the main answer surface stable in streaming mode even if card events are present", () => {
    render(
      <AssistantMessage
        message={{
          ...message,
          status: "streaming",
          blocks: [
            {
              id: "card-1",
              type: "card",
              title: "Key Finding",
              content: "Blocks should update without waiting for the full answer.",
              tone: "info",
              incomplete: true,
            },
          ],
          versions: [
            {
              ...message.versions[0]!,
              status: "streaming",
              blocks: [
                {
                  id: "card-1",
                  type: "card",
                  title: "Key Finding",
                  content: "Blocks should update without waiting for the full answer.",
                  tone: "info",
                  incomplete: true,
                },
              ],
            },
          ],
        }}
        isStreaming={true}
        onRetry={() => {}}
        onPreviewDocument={() => {}}
        onFollowupSelect={() => {}}
      />,
    );

    expect(screen.queryByText("Key Finding")).not.toBeInTheDocument();
    expect(screen.getByText("Summary")).toBeInTheDocument();
  });

  it("does not render decorative card content as a separate block", () => {
    render(
      <AssistantMessage
        message={{
          ...message,
          blocks: [
            {
              id: "card-1",
              type: "card",
              title: "Key Finding",
              content: "**Important**\n\n- First point\n- Second point",
              tone: "info",
            },
          ],
          versions: [
            {
              ...message.versions[0]!,
              blocks: [
                {
                  id: "card-1",
                  type: "card",
                  title: "Key Finding",
                  content: "**Important**\n\n- First point\n- Second point",
                  tone: "info",
                },
              ],
            },
          ],
        }}
        isStreaming={false}
        onRetry={() => {}}
        onPreviewDocument={() => {}}
        onFollowupSelect={() => {}}
      />,
    );

    expect(screen.queryByText("Important")).not.toBeInTheDocument();
    expect(screen.queryByText("First point")).not.toBeInTheDocument();
    expect(screen.getByText("Summary")).toBeInTheDocument();
  });
});
