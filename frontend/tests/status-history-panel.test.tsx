import { fireEvent, render, screen } from "@testing-library/react";

import StatusHistoryPanel from "../app/dashboard/query/_components/StatusHistoryPanel";
import type { QueryStatusEntry } from "../app/dashboard/query/_lib/stream-protocol";

const completedEntries: QueryStatusEntry[] = [
  {
    code: "context",
    label: "Loading Conversation Context",
    state: "completed",
    detail: "Loaded 10 prior messages",
    timestamp: "2026-03-29T09:00:00.000Z",
    durationMs: 120,
  },
  {
    code: "retrieval",
    label: "Retrieving Evidence",
    state: "running",
    detail: "Hybrid search in progress",
    timestamp: "2026-03-29T09:00:01.000Z",
  },
  {
    code: "retrieval",
    label: "Retrieving Evidence",
    state: "completed",
    detail: "Retrieved 5 chunks from 1 document",
    timestamp: "2026-03-29T09:00:02.000Z",
    durationMs: 840,
  },
  {
    code: "grounding",
    label: "Grounding Answer",
    state: "completed",
    detail: "Prepared 3 citations",
    timestamp: "2026-03-29T09:00:03.000Z",
    durationMs: 90,
  },
];

describe("StatusHistoryPanel", () => {
  it("collapses completed timelines by default and shows a compact summary", () => {
    render(<StatusHistoryPanel entries={completedEntries} isStreaming={false} />);

    expect(screen.getByText("Status Timeline")).toBeInTheDocument();
    expect(screen.getByText("3 steps")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /view timeline/i })).toBeInTheDocument();
    expect(screen.queryByText("01")).not.toBeInTheDocument();
    expect(screen.getByText("Grounding Answer")).toBeInTheDocument();
  });

  it("expands on demand and shows the merged ordered steps", () => {
    render(<StatusHistoryPanel entries={completedEntries} isStreaming={false} />);

    fireEvent.click(screen.getByRole("button", { name: /view timeline/i }));

    expect(screen.getByRole("button", { name: /hide timeline/i })).toBeInTheDocument();
    expect(screen.getByText("01")).toBeInTheDocument();
    expect(screen.getByText("02")).toBeInTheDocument();
    expect(screen.getByText("03")).toBeInTheDocument();
    expect(screen.getAllByText("Retrieving Evidence")).toHaveLength(1);
  });

  it("stays expanded while streaming so the live phase remains visible", () => {
    render(
      <StatusHistoryPanel
        entries={[
          ...completedEntries,
          {
            code: "synthesis",
            label: "Synthesizing Answer",
            state: "running",
            detail: "Generating final answer",
            timestamp: "2026-03-29T09:00:04.000Z",
          },
        ]}
        isStreaming={true}
      />,
    );

    expect(screen.getByRole("button", { name: /hide timeline/i })).toBeInTheDocument();
    expect(screen.getByText("Synthesizing Answer")).toBeInTheDocument();
    expect(screen.getByText("live")).toBeInTheDocument();
  });
});
