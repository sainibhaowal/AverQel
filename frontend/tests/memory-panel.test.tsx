import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

const getMock = vi.fn();

vi.mock("framer-motion", () => ({
  motion: {
    div: ({ children, ...props }: { children?: ReactNode; [key: string]: unknown }) => {
      const domProps = { ...props };
      delete domProps.initial;
      delete domProps.animate;
      delete domProps.exit;
      delete domProps.layout;
      return <div {...domProps}>{children}</div>;
    },
  },
  AnimatePresence: ({ children }: { children?: ReactNode }) => <>{children}</>,
}));

vi.mock("@/lib/api", () => ({
  apiV1: {
    get: (...args: unknown[]) => getMock(...args),
    delete: vi.fn(),
  },
}));

import MemoryPanel from "../app/dashboard/deepspace/_components/MemoryPanel";

describe("MemoryPanel", () => {
  it("loads and searches persistent memories", async () => {
    getMock.mockImplementation(async (endpoint: string) => {
      if (endpoint === "/deepspace/chats/memory") {
        return [
          {
            id: "memory-1",
            key: "workflow_note",
            value: "Prefer concise summaries before sending.",
            scope: "user",
            created_at: "2026-06-01T00:00:00.000Z",
          },
        ];
      }
      if (endpoint.startsWith("/deepspace/chats/memory/search")) {
        return {
          results: [
            {
              id: "memory-2",
              key: "search_note",
              value: "Urgent replies should be short.",
              scope: "user",
              relevance_score: 0.91,
              created_at: "2026-06-01T00:00:00.000Z",
            },
          ],
        };
      }
      throw new Error(`Unexpected endpoint: ${endpoint}`);
    });

    render(<MemoryPanel />);

    await waitFor(() => {
      expect(screen.getByText("Universal Memory")).toBeInTheDocument();
    });
    expect(await screen.findByText(/Prefer concise summaries before sending\./i)).toBeInTheDocument();

    const input = screen.getByPlaceholderText(/search across sessions/i);
    fireEvent.change(input, { target: { value: "urgent" } });
    fireEvent.keyDown(input, { key: "Enter", code: "Enter" });

    expect(await screen.findByText(/Urgent replies should be short\./i)).toBeInTheDocument();
    expect(screen.getByText(/Score: 91%/i)).toBeInTheDocument();
  });
});
