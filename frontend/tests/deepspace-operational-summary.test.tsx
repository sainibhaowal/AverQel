import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import DeepSpaceOperationalSummary, {
  type OperationalSummary,
} from "../app/dashboard/deepspace/_components/DeepSpaceOperationalSummary";

const populatedSummary: OperationalSummary = {
  sample_size: 4,
  failure_rate: 0.25,
  p50_latency_ms: 420,
  p95_latency_ms: 980,
  providers: [
    {
      provider: "openai:gpt-4.1",
      sample_size: 4,
      failure_rate: 0.25,
      p50_latency_ms: 420,
      p95_latency_ms: 980,
    },
  ],
};

const noUsageSummary: OperationalSummary = {
  sample_size: 0,
  failure_rate: 0,
  p50_latency_ms: null,
  p95_latency_ms: null,
  providers: [],
};

const originalClipboard = Object.getOwnPropertyDescriptor(navigator, "clipboard");

afterEach(() => {
  if (originalClipboard) {
    Object.defineProperty(navigator, "clipboard", originalClipboard);
  } else {
    Reflect.deleteProperty(navigator, "clipboard");
  }
});

function openDetails() {
  const details = screen.getByText(/Provider health/).closest("details");
  const summary = details?.querySelector("summary");
  if (!summary) throw new Error("Provider health disclosure was not rendered.");
  fireEvent.click(summary);
  return details;
}

describe("DeepSpaceOperationalSummary", () => {
  it("starts collapsed and keeps the compact provider summary visible", () => {
    render(
      <DeepSpaceOperationalSummary summary={populatedSummary} conversationId="conversation-123" />,
    );

    const details = screen.getByText(/Provider health/).closest("details");
    expect(details).not.toHaveAttribute("open");
    expect(screen.getByText(/4 recent turns · 25% failures/)).toBeInTheDocument();
    expect(details?.querySelector("summary")).toHaveTextContent("Provider health");
  });

  it("shows provider/model aggregates and the existing conversation ID when expanded", () => {
    render(
      <DeepSpaceOperationalSummary summary={populatedSummary} conversationId="conversation-123" />,
    );

    const details = openDetails();

    expect(details).toHaveAttribute("open");
    expect(screen.getByText("openai")).toBeInTheDocument();
    expect(screen.getByText("gpt-4.1")).toBeInTheDocument();
    expect(screen.getByText("Turns").parentElement).toHaveTextContent("4");
    expect(screen.getByText("Failures").parentElement).toHaveTextContent("25%");
    expect(screen.getByText("P50 latency").parentElement).toHaveTextContent("420 ms");
    expect(screen.getByText("P95 latency").parentElement).toHaveTextContent("980 ms");
    expect(screen.getByText("conversation-123")).toBeInTheDocument();
  });

  it("copies the current conversation ID and reports clipboard failures accessibly", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
    render(
      <DeepSpaceOperationalSummary summary={populatedSummary} conversationId="conversation-123" />,
    );
    openDetails();

    fireEvent.click(screen.getByRole("button", { name: "Copy conversation ID" }));

    await waitFor(() => expect(screen.getByText("Copied")).toBeInTheDocument());
    expect(writeText).toHaveBeenCalledWith("conversation-123");

    const rejectedWrite = vi.fn().mockRejectedValue(new Error("Clipboard permission denied."));
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: rejectedWrite },
    });
    fireEvent.click(screen.getByRole("button", { name: "Copy conversation ID" }));

    await waitFor(() =>
      expect(screen.getByRole("status")).toHaveTextContent(/Clipboard unavailable.*manually/),
    );
    expect(screen.getByText("conversation-123")).toBeInTheDocument();
  });

  it("shows a truthful no-usage state without zero failure or latency figures", () => {
    render(
      <DeepSpaceOperationalSummary summary={noUsageSummary} conversationId="conversation-123" />,
    );

    expect(screen.getByText("Provider health · No recent usage yet")).toBeInTheDocument();
    expect(screen.queryByText(/0% failures/)).not.toBeInTheDocument();
    expect(screen.getByText(/Provider health/).closest("summary")).not.toHaveTextContent(
      /p50|p95/i,
    );

    openDetails();

    expect(screen.getByText(/No recent usage yet\. Provider statistics/)).toBeInTheDocument();
    expect(screen.getByText("conversation-123")).toBeInTheDocument();
  });

  it("does not invent a conversation ID when no conversation is selected", () => {
    render(<DeepSpaceOperationalSummary summary={noUsageSummary} conversationId={null} />);

    openDetails();

    expect(screen.getByText("No conversation is selected.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Copy conversation ID" })).not.toBeInTheDocument();
  });
});
