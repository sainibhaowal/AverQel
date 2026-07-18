import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

const getMock = vi.fn();
const deleteMock = vi.fn();

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
    delete: (...args: unknown[]) => deleteMock(...args),
  },
}));

import MemoryPanel from "../app/dashboard/deepspace/_components/MemoryPanel";

describe("MemoryPanel lifecycle telemetry", () => {
  it("renders lifecycle health signals alongside the memory list", async () => {
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
      if (endpoint === "/deepspace/chats/memory/lifecycle") {
        return {
          memory_count: 1,
          embedded_count: 1,
          pgvector_count: 1,
          embedding_coverage: 1,
          duplicate_count: 0,
          scope_breakdown: { user: 1 },
          retention_breakdown: { persistent: 1 },
          stale_count: 0,
          stale_session_count: 0,
          average_decay_score: 0.12,
          memory_health_score: 94,
          retention_risk_count: 0,
          sample_queries: [],
          retention_policy: {
            session_retention_days: 7,
            decay_half_life_days: 120,
          },
          session_retention_days: 7,
          stale_memory_ids: [],
          stale_preview_count: 0,
          attention_memories: [],
        };
      }
      throw new Error(`Unexpected endpoint: ${endpoint}`);
    });

    render(<MemoryPanel />);

    await waitFor(() => {
      expect(screen.getByText("Universal Memory")).toBeInTheDocument();
    });
    expect(await screen.findByText("100%")).toBeInTheDocument();
    expect(screen.getByText("1/1")).toBeInTheDocument();
    expect(screen.getByText("0.12")).toBeInTheDocument();
    expect(screen.getByText("94/100")).toBeInTheDocument();
    expect(screen.getByText(/Retention policy: 7 day session window/i)).toBeInTheDocument();
    expect(screen.getByText(/Prefer concise summaries before sending\./i)).toBeInTheDocument();
  });

  it("supports searching while keeping lifecycle telemetry available", async () => {
    getMock.mockImplementation(async (endpoint: string) => {
      if (endpoint === "/deepspace/chats/memory") {
        return [];
      }
      if (endpoint === "/deepspace/chats/memory/lifecycle") {
        return {
          memory_count: 0,
          embedded_count: 0,
          pgvector_count: 0,
          embedding_coverage: 1,
          duplicate_count: 0,
          scope_breakdown: {},
          retention_breakdown: {},
          stale_count: 0,
          stale_session_count: 0,
          average_decay_score: 0,
          memory_health_score: 100,
          retention_risk_count: 0,
          sample_queries: [],
          retention_policy: {
            session_retention_days: 7,
            decay_half_life_days: 120,
          },
          session_retention_days: 7,
          stale_memory_ids: [],
          stale_preview_count: 0,
          attention_memories: [],
        };
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

    fireEvent.change(screen.getByPlaceholderText(/search across sessions/i), {
      target: { value: "urgent" },
    });
    fireEvent.keyDown(screen.getByPlaceholderText(/search across sessions/i), {
      key: "Enter",
      code: "Enter",
    });

    expect(await screen.findByText(/Urgent replies should be short\./i)).toBeInTheDocument();
    expect(screen.getByText(/Score: 91%/i)).toBeInTheDocument();
    expect(screen.getByText(/Retention policy: 7 day session window/i)).toBeInTheDocument();
  });
});
