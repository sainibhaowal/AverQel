import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import DeepSpaceThread from "../app/dashboard/deepspace/_components/DeepSpaceThread";

describe("DeepSpaceThread virtualization", () => {
  it("renders a bounded window from a long mission when scroll metrics are provided", () => {
    const messages = Array.from({ length: 80 }, (_, index) => ({
      id: `msg-${index + 1}`,
      role: "assistant" as const,
      content: `Message ${index + 1}`,
      rawContent: `Message ${index + 1}`,
      createdAt: new Date().toISOString(),
      status: "ready" as const,
    }));

    render(
      <DeepSpaceThread
        messages={messages}
        emptyPrompts={[]}
        scrollMetrics={{
          scrollTop: 7000,
          viewportHeight: 900,
        }}
        onPromptSelect={() => {}}
        onInsertLatestAnswer={() => {}}
      />,
    );

    expect(screen.queryByText(/^Message 1$/)).not.toBeInTheDocument();
    expect(screen.getByText(/^Message 31$/)).toBeInTheDocument();
    expect(screen.queryByText(/^Message 80$/)).not.toBeInTheDocument();
  });

  it("falls back safely to the tail of the thread when scroll metrics are past the end", () => {
    const messages = Array.from({ length: 32 }, (_, index) => ({
      id: `msg-${index + 1}`,
      role: "assistant" as const,
      content: `Message ${index + 1}`,
      rawContent: `Message ${index + 1}`,
      createdAt: new Date().toISOString(),
      status: "ready" as const,
    }));

    render(
      <DeepSpaceThread
        messages={messages}
        emptyPrompts={[]}
        scrollMetrics={{
          scrollTop: 100000,
          viewportHeight: 900,
        }}
        onPromptSelect={() => {}}
        onInsertLatestAnswer={() => {}}
      />,
    );

    expect(screen.getByText(/^Message 32$/)).toBeInTheDocument();
    expect(screen.queryByText(/^Message 1$/)).not.toBeInTheDocument();
  });
});
