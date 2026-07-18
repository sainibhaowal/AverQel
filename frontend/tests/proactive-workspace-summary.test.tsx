import type { ReactNode } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const fetchWithAuthMock = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api", () => ({
  fetchWithAuth: fetchWithAuthMock,
}));

vi.mock("framer-motion", () => ({
  motion: {
    div: ({ children, ...props }: { children?: ReactNode; [key: string]: unknown }) => {
      const domProps = { ...props };
      delete domProps.initial;
      delete domProps.animate;
      delete domProps.transition;
      delete domProps.whileInView;
      delete domProps.viewport;
      return <div {...domProps}>{children}</div>;
    },
  },
  AnimatePresence: ({ children }: { children?: ReactNode }) => <>{children}</>,
}));

import ProactiveWorkspaceClient from "../app/dashboard/proactive/_components/ProactiveWorkspaceClient";

describe("ProactiveWorkspaceClient connector summary", () => {
  beforeEach(() => {
    fetchWithAuthMock.mockReset();
    fetchWithAuthMock.mockImplementation((url: string) => {
      if (url === "/deepspace/chats/runtime") {
        return Promise.resolve(
          new Response(
            JSON.stringify({ model_name: "test-model", provider_type: "test-provider" }),
          ),
        );
      }
      if (url === "/deepspace/chats/vitals") {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              internet: "connected",
              llm: "connected",
              web_search: "available",
              sources: 3,
            }),
          ),
        );
      }
      if (url === "/deepspace/chats/activity?limit=100") {
        return Promise.resolve(new Response(JSON.stringify([])));
      }
      if (url === "/integrations/connectors") {
        return Promise.resolve(
          new Response(
            JSON.stringify([
              {
                id: "connector-1",
                name: "GitHub",
                status: "ACTIVE",
                last_sync_at: null,
                integration_id: "integration-1",
              },
            ]),
          ),
        );
      }
      if (url === "/integrations/connectors/summary") {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              total_connectors: 1,
              active_count: 1,
              syncing_count: 0,
              paused_count: 0,
              error_count: 0,
              healthy_count: 1,
              stale_count: 0,
              retryable_count: 0,
              due_sync_count: 0,
              recent_audit_count: 0,
              status_breakdown: { active: 1 },
              integration_breakdown: { github: 1 },
              error_domain_breakdown: {},
              health_status_breakdown: { healthy: 1 },
              retry_state_breakdown: { none: 1 },
              attention_connectors: [],
              daemon_heartbeat: {
                phase: "running",
                timestamp: "2026-06-06T00:00:00Z",
                interval_seconds: 300,
              },
            }),
          ),
        );
      }
      if (url === "/deepspace/chats/tasks") {
        return Promise.resolve(new Response(JSON.stringify([])));
      }
      if (url === "/deepspace/chats/tasks/summary") {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              total: 0,
              pending: 0,
              in_progress: 0,
              completed: 0,
              recurring: 0,
              enabled: 0,
              paused: 0,
              due: 0,
              approval_required: 0,
              source_breakdown: {},
              recent_activity_count: 0,
              recent_error_count: 0,
              recent_cycle_count: 2,
              recent_cycle_failure_count: 1,
              gmail_scan_failure_count: 1,
              gmail_message_failure_count: 0,
              last_cycle_at: "2026-06-06T00:00:00Z",
              last_cycle_status: "degraded",
            }),
          ),
        );
      }
      if (url === "/deepspace/chats/memory/lifecycle") {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              memory_count: 2,
              embedded_count: 2,
              pgvector_count: 2,
              embedding_coverage: 1,
              duplicate_count: 0,
              scope_breakdown: { session: 1, user: 1 },
              retention_breakdown: { stale: 1, persistent: 1 },
              stale_count: 1,
              average_decay_score: 0.42,
              sample_queries: [],
              retention_policy: {
                session_retention_days: 7,
                decay_half_life_days: 120,
              },
              session_retention_days: 7,
              stale_memory_ids: ["memory-1"],
              stale_preview_count: 1,
              attention_memories: [],
            }),
          ),
        );
      }
      if (url === "/collections/notifications") {
        return Promise.resolve(new Response(JSON.stringify([])));
      }
      return Promise.resolve(new Response(JSON.stringify({})));
    });
  });

  it("renders the connector fleet summary pills", async () => {
    render(<ProactiveWorkspaceClient />);

    await waitFor(() => {
      expect(screen.getByText("1/1 active")).toBeInTheDocument();
    });
    expect(screen.getAllByText("0 retryable").length).toBeGreaterThan(0);
    expect(screen.getAllByText("0 due syncs").length).toBeGreaterThan(0);
    expect(screen.getAllByText("0 retry queue").length).toBeGreaterThan(0);
    expect(screen.getAllByText("1 healthy").length).toBeGreaterThan(0);
    expect(screen.getByText("Proactive Cycles")).toBeInTheDocument();
    expect(screen.getAllByText("1 Gmail scan failures").length).toBeGreaterThan(0);
    expect(screen.getAllByText("degraded cycle").length).toBeGreaterThan(0);
    expect(screen.getAllByText("2 memories").length).toBeGreaterThan(0);
    expect(screen.getAllByText("1 stale").length).toBeGreaterThan(0);
  });
});
