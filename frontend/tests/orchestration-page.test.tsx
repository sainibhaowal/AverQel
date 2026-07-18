import { render, screen, fireEvent, act } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import OrchestrationPageClient from "../app/dashboard/orchestration/_components/OrchestrationPageClient";

const fetchWithAuthMock = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api", () => ({
  fetchWithAuth: fetchWithAuthMock,
}));

describe("OrchestrationPageClient", () => {
  beforeEach(() => {
    fetchWithAuthMock.mockReset();
  });

  it("renders the unified orchestration snapshot and mission graph", async () => {
    fetchWithAuthMock.mockImplementation(async (url) => {
      if (url.includes("/deepspace/chats/orchestration")) {
        return new Response(
          JSON.stringify({
            timestamp: "2026-05-22T08:40:00Z",
            runtime: {
              model_name: "orchestration-test-model",
              provider_type: "test-provider",
              context_limit: 128000,
              context_limit_source: "runtime",
              tool_count: 35,
            },
            vitals: {
              internet: "connected",
              llm: "connected",
              web_search: "available",
              sources: 5,
              connector_statuses: { active: 3 },
              proactive_daemon: {
                enabled: true,
                phase: "running",
                timestamp: "2026-05-22T08:30:00Z",
                interval_seconds: 300,
                healthy: true,
              },
            },
            subagents: {
              runs: [
                {
                  run_id: "run-1",
                  tenant_id: "tenant-1",
                  user_id: "user-1",
                  parent_id: "",
                  subagent_type: "research",
                  prompt: "Research the market update.",
                  status: "running",
                  slot_index: 1,
                  summary: "Collecting evidence from sources.",
                  final_output: "",
                  error: "",
                  step_count: 4,
                  duration_ms: 1000,
                  last_tool_name: "web_search",
                  last_tool_id: "tool-1",
                  last_tool_output: "results",
                  heartbeat_at: "2026-05-22T08:35:00Z",
                  created_at: "2026-05-22T08:30:00Z",
                  started_at: "2026-05-22T08:30:00Z",
                  updated_at: "2026-05-22T08:35:00Z",
                  completed_at: null,
                  cancel_requested: false,
                  last_event_type: "tool_result",
                  last_event_message: "Working",
                },
              ],
              active: [
                {
                  run_id: "run-1",
                  tenant_id: "tenant-1",
                  user_id: "user-1",
                  parent_id: "",
                  subagent_type: "research",
                  prompt: "Research the market update.",
                  status: "running",
                  slot_index: 1,
                  summary: "Collecting evidence from sources.",
                  final_output: "",
                  error: "",
                  step_count: 4,
                  duration_ms: 1000,
                  last_tool_name: "web_search",
                  last_tool_id: "tool-1",
                  last_tool_output: "results",
                  heartbeat_at: "2026-05-22T08:35:00Z",
                  created_at: "2026-05-22T08:30:00Z",
                  started_at: "2026-05-22T08:30:00Z",
                  updated_at: "2026-05-22T08:35:00Z",
                  completed_at: null,
                  cancel_requested: false,
                  last_event_type: "tool_result",
                  last_event_message: "Working",
                },
              ],
              max_concurrency: 4,
              daemon_heartbeat: {
                phase: "running",
                timestamp: "2026-05-22T08:30:00Z",
                interval_seconds: 300,
              },
            },
            tasks: {
              all: [
                {
                  id: "task-1",
                  content: "Draft follow-up email",
                  status: "pending",
                  activeForm: "Draft follow-up email",
                  priority: 80,
                  thread_id: null,
                  metadata_json: {},
                  automation_json: { prompt: "Draft the email and queue it for approval." },
                  is_recurring: true,
                  enabled: true,
                  next_run_at: "2026-05-22T09:00:00Z",
                  last_run_at: null,
                  created_at: "2026-05-22T08:00:00Z",
                  updated_at: "2026-05-22T08:00:00Z",
                },
                {
                  id: "task-2",
                  content: "Review connector health",
                  status: "in_progress",
                  activeForm: "Review connector health",
                  priority: 70,
                  thread_id: null,
                  metadata_json: { source: "connector" },
                  automation_json: {},
                  is_recurring: false,
                  enabled: true,
                  next_run_at: null,
                  last_run_at: null,
                  created_at: "2026-05-22T08:05:00Z",
                  updated_at: "2026-05-22T08:05:00Z",
                },
              ],
              active: [
                {
                  id: "task-1",
                  content: "Draft follow-up email",
                  status: "pending",
                  activeForm: "Draft follow-up email",
                  priority: 80,
                  thread_id: null,
                  metadata_json: {},
                  automation_json: { prompt: "Draft the email and queue it for approval." },
                  is_recurring: true,
                  enabled: true,
                  next_run_at: "2026-05-22T09:00:00Z",
                  last_run_at: null,
                  created_at: "2026-05-22T08:00:00Z",
                  updated_at: "2026-05-22T08:00:00Z",
                },
                {
                  id: "task-2",
                  content: "Review connector health",
                  status: "in_progress",
                  activeForm: "Review connector health",
                  priority: 70,
                  thread_id: null,
                  metadata_json: { source: "connector" },
                  automation_json: {},
                  is_recurring: false,
                  enabled: true,
                  next_run_at: null,
                  last_run_at: null,
                  created_at: "2026-05-22T08:05:00Z",
                  updated_at: "2026-05-22T08:05:00Z",
                },
              ],
            },
            activities: [
              {
                id: "activity-1",
                type: "sync",
                description: "Synced Gmail connector into the proactive workspace.",
                source: "gmail",
                metadata_json: { connector_id: "gmail-1" },
                created_at: "2026-05-22T08:10:00Z",
              },
            ],
            tool_catalog: {
              count: 35,
              names: ["web_search", "gmail_send", "github_search"],
              active: ["web_search"],
            },
            missions: {
              active: [
                {
                  mission_id: "mission-1",
                  objective: "Research and analyze the migration plan.",
                  status: "running",
                  summary: "Synthesizing parallel lanes.",
                  last_event_type: "mission_graph",
                  approval_queue: [],
                },
              ],
              count: 1,
              heartbeat: {
                phase: "running",
                timestamp: "2026-05-22T08:45:00Z",
                interval_seconds: 300,
              },
            },
            summary: {
              active_subagents: 1,
              active_tasks: 2,
              recent_activities: 1,
              tool_count: 35,
              connector_count: 5,
              parallel_capacity: 4,
              activity_types: { sync: 1 },
              connector_statuses: { active: 3 },
              daemon_healthy: true,
            },
            graph: {
              nodes: [
                {
                  id: "open_chat",
                  label: "AverQel Mission Core",
                  kind: "core",
                  world: "control",
                  x: 0,
                  y: 0,
                  z: 120,
                  status: "active",
                  tone: "primary",
                  meta: {},
                },
                {
                  id: "subagent_swarm",
                  label: "Subagent Swarm · 1 runs",
                  kind: "swarm",
                  world: "parallel",
                  x: 0,
                  y: -420,
                  z: 120,
                  status: "active",
                  tone: "cyan",
                  meta: {},
                },
                {
                  id: "proactive_workspace",
                  label: "Proactive Workspace",
                  kind: "workspace",
                  world: "background",
                  x: -80,
                  y: 620,
                  z: 50,
                  status: "active",
                  tone: "emerald",
                  meta: {},
                },
                {
                  id: "connector_mesh",
                  label: "Connector Mesh",
                  kind: "connector",
                  world: "connectors",
                  x: 560,
                  y: 170,
                  z: 85,
                  status: "active",
                  tone: "violet",
                  meta: {},
                },
                {
                  id: "activity_stream",
                  label: "Activity Stream · 1 events",
                  kind: "stream",
                  world: "surface",
                  x: 620,
                  y: -300,
                  z: 45,
                  status: "active",
                  tone: "rose",
                  meta: {},
                },
                {
                  id: "task_task-1",
                  label: "Draft follow-up email",
                  kind: "task",
                  world: "background",
                  x: 0,
                  y: 680,
                  z: 110,
                  status: "pending",
                  tone: "amber",
                  meta: { content: "Draft follow-up email" },
                },
              ],
              edges: [
                {
                  source: "open_chat",
                  target: "subagent_swarm",
                  label: "delegate",
                  tone: "cyan",
                  kind: "subagent",
                },
                {
                  source: "open_chat",
                  target: "proactive_workspace",
                  label: "handoff",
                  tone: "emerald",
                  kind: "task",
                },
              ],
              worlds: [
                { id: "control", label: "Mission Control", description: "Main plane." },
                { id: "parallel", label: "Parallel Workers", description: "Fan-out lanes." },
                { id: "background", label: "Proactive Layer", description: "24/7 work." },
                { id: "systems", label: "System Mesh", description: "Health." },
                { id: "memory", label: "Durable Memory", description: "Ledger." },
              ],
            },
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          },
        );
      }

      if (url.includes("/deepspace/chats")) {
        return new Response(
          JSON.stringify({
            items: [
              {
                id: "chat-1",
                title: "Test Chat Session",
                updated_at: "2026-05-22T08:00:00Z",
              },
            ],
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          },
        );
      }

      if (url.includes("/integrations/connectors")) {
        return new Response(
          JSON.stringify([
            {
              id: "conn-1",
              name: "Gmail Sync Connector",
              integration_id: "int-1",
              status: "active",
              collection_id: null,
            },
          ]),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          },
        );
      }

      if (url.includes("/integrations")) {
        return new Response(
          JSON.stringify([
            {
              id: "int-1",
              name: "Gmail Sync Connector",
              slug: "gmail",
              description:
                "Monitors and processes inbound emails, triggering autonomous pipeline runs.",
              ui_metadata: {},
              is_active: true,
            },
          ]),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          },
        );
      }

      return new Response(JSON.stringify({}), { status: 404 });
    });

    const { container } = render(<OrchestrationPageClient />);

    // 1. Verify Federated Session Orchestrator dashboard renders initially
    expect(await screen.findByText(/Federated Session Orchestrator/i)).toBeInTheDocument();
    expect(screen.getByText(/System Master View/i)).toBeInTheDocument();
    expect(screen.getByText(/All Sessions/i)).toBeInTheDocument();
    expect(screen.getByText(/Proactive Agents/i)).toBeInTheDocument();

    // 2. Click the "Enter Control Room" button to drill down
    const enterButton = screen.getByText(/Enter Control Room/i);
    await act(async () => {
      fireEvent.click(enterButton);
    });

    // 3. Verify it shows the Global Control Room canvas
    expect(await screen.findByText(/Global Control Room/i)).toBeInTheDocument();
    expect(screen.getByLabelText("Orchestration overview")).toBeInTheDocument();

    expect(screen.getAllByText("AverQel Mission Core").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Subagent Swarm · 1 runs").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Proactive Workspace").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Connector Mesh").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Draft follow-up email").length).toBeGreaterThan(0);
    expect(container.querySelectorAll("[data-orchestration-node='true']").length).toBeGreaterThan(
      0,
    );
    expect(screen.getByLabelText("Zoom in")).toBeInTheDocument();
    expect(screen.getByLabelText("Zoom out")).toBeInTheDocument();
    expect(screen.getByLabelText("Reset camera")).toBeInTheDocument();
    expect(screen.getByText("1 active subagents")).toBeInTheDocument();
  });
});
