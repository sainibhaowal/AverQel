import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const markdownRendererMock = vi.fn(({ content }: { content: string }) => (
  <div>Markdown: {content}</div>
));

vi.mock("../app/dashboard/query/_components/MarkdownRenderer", () => ({
  default: (props: { content: string }) => markdownRendererMock(props),
}));

import DeepSpaceThread from "../app/dashboard/deepspace/_components/DeepSpaceThread";

describe("DeepSpaceThread streaming preview", () => {
  it("shows a rich preview while streaming by mounting the markdown renderer", () => {
    render(
      <DeepSpaceThread
        messages={[
          {
            id: "assistant_streaming_1",
            role: "assistant",
            content: "Streaming answer text",
            rawContent: "Streaming answer text",
            createdAt: new Date().toISOString(),
            status: "streaming",
          },
        ]}
        emptyPrompts={[]}
        onPromptSelect={() => {}}
        onInsertLatestAnswer={() => {}}
      />,
    );

    expect(screen.getByText("Markdown: Streaming answer text")).toBeInTheDocument();
    expect(markdownRendererMock).toHaveBeenCalledTimes(1);
  });

  it("renders the rich markdown view once the message is complete", () => {
    markdownRendererMock.mockClear();

    render(
      <DeepSpaceThread
        messages={[
          {
            id: "assistant_ready_1",
            role: "assistant",
            content: "Finished answer text",
            rawContent: "Finished answer text",
            createdAt: new Date().toISOString(),
            status: "ready",
          },
        ]}
        emptyPrompts={[]}
        onPromptSelect={() => {}}
        onInsertLatestAnswer={() => {}}
      />,
    );

    expect(screen.getByText("Markdown: Finished answer text")).toBeInTheDocument();
    expect(markdownRendererMock).toHaveBeenCalledTimes(1);
  });

  it("does not rerun the markdown renderer when local copy state changes", () => {
    markdownRendererMock.mockClear();
    const message = {
      id: "assistant_copy_1",
      role: "assistant" as const,
      content: "Copyable answer text",
      rawContent: "Copyable answer text",
      createdAt: new Date().toISOString(),
      status: "ready" as const,
    };

    const { rerender } = render(
      <DeepSpaceThread
        messages={[message]}
        emptyPrompts={[]}
        onPromptSelect={() => {}}
        onInsertLatestAnswer={() => {}}
      />,
    );

    expect(markdownRendererMock).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: /copy/i }));
    expect(markdownRendererMock).toHaveBeenCalledTimes(1);

    rerender(
      <DeepSpaceThread
        messages={[message]}
        emptyPrompts={[]}
        onPromptSelect={() => undefined}
        onInsertLatestAnswer={() => undefined}
      />,
    );

    expect(markdownRendererMock).toHaveBeenCalledTimes(1);
  });
});
