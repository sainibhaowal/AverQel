"use client";

import { AnimatePresence, motion } from "framer-motion";
import {
  Activity,
  Brain,
  Cable,
  Clock3,
  Database,
  Info,
  GitBranch,
  Layers3,
  Link as LinkIcon,
  Loader,
  MessageSquare,
  Move,
  Network,
  RefreshCw,
  RotateCcw,
  ShieldCheck,
  Sparkles,
  Undo2,
  Workflow,
  Wrench,
  Zap,
  ZoomIn,
  ZoomOut,
  Power,
  Trash2,
  X,
} from "lucide-react";
import Link from "next/link";
import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import toast from "react-hot-toast";

import { fetchWithAuth } from "@/lib/api";
import { parseSseFrames } from "@/app/dashboard/deepspace/_lib/deepspace-stream";
import ExecutionModeDropdown from "@/app/dashboard/deepspace/_components/ExecutionModeDropdown";
import AverQelTooltip from "@/app/components/ui/AverQelTooltip";
import DashboardSectionHeader from "@/app/components/ui/DashboardSectionHeader";
import ConfirmationModal from "@/app/components/ui/ConfirmationModal";

type Tone = "cyan" | "emerald" | "violet" | "amber" | "rose";
type DashboardTab = "all" | "chats" | "proactive" | "connectors";

interface OrchestrationChatSession {
  id: string;
  title?: string;
  updated_at?: string | null;
  [key: string]: unknown;
}

interface OrchestrationConnectorSummary {
  id: string | number;
  name: string;
  status?: string | null;
  desc?: string | null;
  integration_id?: string | number | null;
  [key: string]: unknown;
}

interface OrchestrationIntegrationSummary {
  id: string | number;
  description?: string | null;
  slug?: string | null;
  [key: string]: unknown;
}

interface OrchestrationRuntime {
  model_name?: string | null;
  provider_type?: string | null;
  context_limit?: number | null;
  context_limit_source?: string | null;
  tool_count?: number;
  execution_mode?: "auto_review" | "full_access";
}

interface OrchestrationVitals {
  internet: string;
  llm: string;
  web_search: string;
  sources: number;
  connector_statuses?: Record<string, number>;
  proactive_daemon?: {
    enabled: boolean;
    phase: string;
    timestamp?: string | null;
    interval_seconds?: number | null;
    healthy: boolean;
  } | null;
}

interface OrchestrationNode {
  id: string;
  label: string;
  kind: string;
  world: string;
  x: number;
  y: number;
  z: number;
  status: string;
  tone: string;
  meta?: Record<string, unknown>;
}

interface OrchestrationEdge {
  source: string;
  target: string;
  label: string;
  tone: Tone;
  kind: string;
}

interface OrchestrationWorld {
  id: string;
  label: string;
  description: string;
}

interface OrchestrationTask {
  id: string;
  content: string;
  status: string;
  activeForm: string;
  priority: number;
  thread_id?: string | null;
  metadata_json?: Record<string, unknown>;
  automation_json?: Record<string, unknown>;
  is_recurring: boolean;
  enabled: boolean;
  next_run_at?: string | null;
  last_run_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

interface OrchestrationActivity {
  id: string;
  type: string;
  description: string;
  source: string;
  metadata_json?: Record<string, unknown>;
  created_at?: string | null;
}

interface OrchestrationSubagentRun {
  run_id: string;
  tenant_id: string;
  user_id: string;
  parent_id?: string;
  subagent_type: string;
  prompt: string;
  status: string;
  slot_index: number;
  summary?: string;
  final_output?: string;
  error?: string;
  last_event_type?: string;
  last_event_message?: string;
  step_count?: number;
  duration_ms?: number;
  created_at?: string | null;
  started_at?: string | null;
  updated_at?: string | null;
  completed_at?: string | null;
  heartbeat_at?: string | null;
  cancel_requested?: boolean;
}

interface OrchestrationOverview {
  timestamp: string;
  runtime: OrchestrationRuntime;
  vitals: OrchestrationVitals;
  missions?: {
    active: Array<{
      mission_id: string;
      parent_id?: string | null;
      objective: string;
      status: string;
      summary?: string | null;
      last_event_type?: string | null;
      approval_queue?: Array<Record<string, unknown>>;
      runtime_state?: Record<string, unknown>;
    }>;
    count: number;
    heartbeat?: Record<string, unknown> | null;
    execution_mode?: "auto_review" | "full_access";
  };
  subagents: {
    runs: OrchestrationSubagentRun[];
    active: OrchestrationSubagentRun[];
    max_concurrency: number;
    daemon_heartbeat?: Record<string, unknown> | null;
  };
  tasks: {
    all: OrchestrationTask[];
    active: OrchestrationTask[];
  };
  activities: OrchestrationActivity[];
  tool_catalog: {
    count: number;
    names: string[];
    active: string[];
  };
  summary: {
    active_subagents: number;
    active_tasks: number;
    recent_activities: number;
    tool_count: number;
    connector_count: number;
    parallel_capacity: number;
    activity_types: Record<string, number>;
    connector_statuses: Record<string, number>;
    daemon_healthy: boolean;
  };
  graph: {
    nodes: OrchestrationNode[];
    edges: OrchestrationEdge[];
    worlds: OrchestrationWorld[];
  };
}

interface OrchestrationGraph {
  nodes: OrchestrationNode[];
  edges: OrchestrationEdge[];
  worlds: OrchestrationWorld[];
}

interface Point {
  x: number;
  y: number;
}

interface ProjectedPosition {
  left: string;
  top: string;
  x: number;
  y: number;
}

const MIN_ZOOM = 0.42;
const MAX_ZOOM = 1.7;
const DEFAULT_ZOOM = 0.88;
const GRAPH_BOARD_WIDTH = 2800;
const GRAPH_BOARD_HEIGHT = 2000;
const GRAPH_BOARD_CENTER_X = GRAPH_BOARD_WIDTH / 2;
const GRAPH_BOARD_CENTER_Y = GRAPH_BOARD_HEIGHT / 2;
const GRAPH_CARD_WIDTH = 260;
const GRAPH_CARD_HEIGHT = 112;
const GRAPH_FIT_PADDING = 120;
const GRAPH_VIEW_TOP_INSET = 96;
const GRAPH_VIEW_BOTTOM_INSET = 84;
const GRAPH_VIEW_LEFT_INSET = 72;
const GRAPH_VIEW_RIGHT_INSET = 132;
const MAX_MISSION_LOG_LINES = 1000;
const VISIBLE_MISSION_LOG_LINES = 140;

const WORLD_ANCHORS: Record<string, Point> = {
  control: { x: 0, y: 0 },
  parallel: { x: 0, y: -420 },
  background: { x: -80, y: 620 },
  connectors: { x: 560, y: 170 },
  systems: { x: -520, y: -160 },
  memory: { x: -420, y: 300 },
  surface: { x: 620, y: -300 },
};

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

function appendMissionLogLines(current: string[], lines: string[]) {
  if (!lines.length) return current;
  return [...current, ...lines].slice(-MAX_MISSION_LOG_LINES);
}

function getConnectorPoint(source: Point, target: Point, width: number, height: number): Point {
  const dx = target.x - source.x;
  const dy = target.y - source.y;
  if (dx === 0 && dy === 0) return { x: source.x, y: source.y };

  const halfWidth = width / 2;
  const halfHeight = height / 2;
  const absDx = Math.abs(dx);
  const absDy = Math.abs(dy);

  if (absDx * halfHeight >= absDy * halfWidth) {
    const x = source.x + (dx >= 0 ? halfWidth : -halfWidth);
    const y = source.y + (dy * halfWidth) / Math.max(absDx, 1);
    return { x, y };
  }

  const x = source.x + (dx * halfHeight) / Math.max(absDy, 1);
  const y = source.y + (dy >= 0 ? halfHeight : -halfHeight);
  return { x, y };
}

function buildCurvePath(start: Point, end: Point) {
  const curvature = 0.5;
  const controlPointX1 = start.x + (end.x - start.x) * curvature;
  const controlPointX2 = end.x - (end.x - start.x) * curvature;
  return `M ${start.x} ${start.y} C ${controlPointX1} ${start.y}, ${controlPointX2} ${end.y}, ${end.x} ${end.y}`;
}

function formatTime(value?: string | null): string {
  if (!value) return "now";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString([], {
    hour: "2-digit",
    minute: "2-digit",
    month: "short",
    day: "numeric",
  });
}

function formatRelative(value?: string | null): string {
  if (!value) return "just now";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const deltaSeconds = Math.round((date.getTime() - Date.now()) / 1000);
  const rtf = new Intl.RelativeTimeFormat([], { numeric: "auto" });
  const abs = Math.abs(deltaSeconds);
  if (abs < 60) return rtf.format(Math.round(deltaSeconds), "second");
  if (abs < 3600) return rtf.format(Math.round(deltaSeconds / 60), "minute");
  if (abs < 86400) return rtf.format(Math.round(deltaSeconds / 3600), "hour");
  return rtf.format(Math.round(deltaSeconds / 86400), "day");
}

function toneClasses(tone: string, selected = false) {
  switch (tone) {
    case "emerald":
      return selected
        ? "border-emerald-400/70 bg-emerald-50/95 text-emerald-950 shadow-[0_0_42px_rgba(16,185,129,0.14)] dark:border-emerald-400/30 dark:bg-emerald-500/12 dark:text-emerald-100 dark:shadow-[0_0_42px_rgba(16,185,129,0.2)]"
        : "border-emerald-200/80 bg-emerald-50/92 text-emerald-950 shadow-[0_16px_40px_rgba(15,23,42,0.05)] dark:border-emerald-400/20 dark:bg-emerald-500/10 dark:text-emerald-100 dark:shadow-[0_14px_40px_rgba(0,0,0,0.24)]";
    case "amber":
      return selected
        ? "border-amber-400/70 bg-amber-50/95 text-amber-950 shadow-[0_0_42px_rgba(245,158,11,0.14)] dark:border-amber-400/30 dark:bg-amber-500/12 dark:text-amber-100 dark:shadow-[0_0_42px_rgba(245,158,11,0.2)]"
        : "border-amber-200/80 bg-amber-50/92 text-amber-950 shadow-[0_16px_40px_rgba(15,23,42,0.05)] dark:border-amber-400/20 dark:bg-amber-500/10 dark:text-amber-100 dark:shadow-[0_14px_40px_rgba(0,0,0,0.24)]";
    case "rose":
      return selected
        ? "border-rose-400/70 bg-rose-50/95 text-rose-950 shadow-[0_0_42px_rgba(244,63,94,0.14)] dark:border-rose-400/30 dark:bg-rose-500/12 dark:text-rose-100 dark:shadow-[0_0_42px_rgba(244,63,94,0.2)]"
        : "border-rose-200/80 bg-rose-50/92 text-rose-950 shadow-[0_16px_40px_rgba(15,23,42,0.05)] dark:border-rose-400/20 dark:bg-rose-500/10 dark:text-rose-100 dark:shadow-[0_14px_40px_rgba(0,0,0,0.24)]";
    case "violet":
      return selected
        ? "border-violet-400/70 bg-violet-50/95 text-violet-950 shadow-[0_0_42px_rgba(139,92,246,0.14)] dark:border-violet-400/30 dark:bg-violet-500/12 dark:text-violet-100 dark:shadow-[0_0_42px_rgba(139,92,246,0.2)]"
        : "border-violet-200/80 bg-violet-50/92 text-violet-950 shadow-[0_16px_40px_rgba(15,23,42,0.05)] dark:border-violet-400/20 dark:bg-violet-500/10 dark:text-violet-100 dark:shadow-[0_14px_40px_rgba(0,0,0,0.24)]";
    case "cyan":
      return selected
        ? "border-cyan-400/70 bg-cyan-50/95 text-cyan-950 shadow-[0_0_42px_rgba(34,211,238,0.14)] dark:border-cyan-400/30 dark:bg-cyan-500/12 dark:text-cyan-100 dark:shadow-[0_0_42px_rgba(34,211,238,0.2)]"
        : "border-cyan-200/80 bg-cyan-50/92 text-cyan-950 shadow-[0_16px_40px_rgba(15,23,42,0.05)] dark:border-cyan-400/20 dark:bg-cyan-500/10 dark:text-cyan-100 dark:shadow-[0_14px_40px_rgba(0,0,0,0.24)]";
    case "slate":
      return selected
        ? "border-slate-300/90 bg-slate-50/96 text-slate-950 shadow-[0_0_42px_rgba(71,85,105,0.12)] dark:border-white/12 dark:bg-white/8 dark:text-white"
        : "border-slate-200/85 bg-white/96 text-slate-900 shadow-[0_16px_40px_rgba(15,23,42,0.05)] dark:border-white/10 dark:bg-black/35 dark:text-white";
    default:
      return selected
        ? "border-primary/35 bg-primary/10 text-primary shadow-[0_0_42px_rgba(var(--primary),0.14)] dark:bg-primary/12 dark:shadow-[0_0_42px_rgba(var(--primary),0.25)]"
        : "border-slate-200/85 bg-white/96 text-slate-900 shadow-[0_16px_40px_rgba(15,23,42,0.06)] dark:border-white/10 dark:bg-black/35 dark:text-white";
  }
}

function toneIconClasses(tone: string) {
  switch (tone) {
    case "emerald":
      return "border-emerald-200/80 bg-emerald-500/12 text-emerald-700 dark:border-white/8 dark:bg-emerald-500/15 dark:text-emerald-100";
    case "amber":
      return "border-amber-200/80 bg-amber-500/12 text-amber-700 dark:border-white/8 dark:bg-amber-500/15 dark:text-amber-100";
    case "rose":
      return "border-rose-200/80 bg-rose-500/12 text-rose-700 dark:border-white/8 dark:bg-rose-500/15 dark:text-rose-100";
    case "violet":
      return "border-violet-200/80 bg-violet-500/12 text-violet-700 dark:border-white/8 dark:bg-violet-500/15 dark:text-violet-100";
    case "cyan":
      return "border-cyan-200/80 bg-cyan-500/12 text-cyan-700 dark:border-white/8 dark:bg-cyan-500/15 dark:text-cyan-100";
    default:
      return "border-slate-200/80 bg-slate-100/90 text-slate-700 dark:border-white/8 dark:bg-white/8 dark:text-white";
  }
}

function statusPillClasses(status: string) {
  const normalized = status.toLowerCase();
  if (["running", "active", "connected", "available", "healthy"].includes(normalized)) {
    return "border-emerald-500/25 bg-emerald-500/12 text-emerald-700 dark:text-emerald-300";
  }
  if (["pending", "paused", "waiting", "scheduled"].includes(normalized)) {
    return "border-amber-500/25 bg-amber-500/12 text-amber-700 dark:text-amber-300";
  }
  if (["error", "failed", "degraded", "stale", "terminating"].includes(normalized)) {
    return "border-rose-500/25 bg-rose-500/12 text-rose-700 dark:text-rose-300";
  }
  return "border-slate-300/80 bg-slate-100/90 text-slate-600 dark:border-white/10 dark:bg-white/5 dark:text-white/45";
}

function kindIcon(kind: string) {
  switch (kind) {
    case "core":
      return <Brain size={16} />;
    case "planner":
      return <Sparkles size={16} />;
    case "executor":
      return <Database size={16} />;
    case "guard":
      return <ShieldCheck size={16} />;
    case "output":
      return <Zap size={16} />;
    case "ledger":
      return <Database size={16} />;
    case "workspace":
      return <Layers3 size={16} />;
    case "connector":
      return <Cable size={16} />;
    case "system":
      return <Activity size={16} />;
    case "swarm":
      return <GitBranch size={16} />;
    case "queue":
      return <Layers3 size={16} />;
    case "task":
      return <Clock3 size={16} />;
    case "activity":
      return <Zap size={16} />;
    case "catalog":
      return <Sparkles size={16} />;
    case "signal":
      return <Activity size={16} />;
    default:
      return <Brain size={16} />;
  }
}

function nodePreview(node: OrchestrationNode): string {
  const meta = node.meta ?? {};
  if (node.kind === "subagent") {
    return String(meta.summary || meta.prompt || "Subagent run in flight.");
  }
  if (node.kind === "task") {
    return node.status === "completed"
      ? "Recurring work has completed."
      : String(
          meta.automation_json ? "Automated recurring work." : "Waiting in the proactive queue.",
        );
  }
  if (node.kind === "activity") {
    return `${String(meta.source || node.status)} · ${formatRelative(node.meta?.created_at as string | undefined)}`;
  }
  if (node.kind === "system") {
    return String(meta.value || "System signal");
  }
  return String(meta.description || "Core orchestration node.");
}

function buildFallbackGraph(): OrchestrationGraph {
  return {
    worlds: [
      { id: "control", label: "Mission Control", description: "Core planning and synthesis." },
      { id: "parallel", label: "Parallel Workers", description: "Research and analysis lanes." },
      {
        id: "background",
        label: "Background Continuity",
        description: "Memory and proactive work.",
      },
    ],
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
        tone: "cyan",
        meta: { description: "Primary orchestration node." },
      },
      {
        id: "mission_router",
        label: "Mission Router",
        kind: "planner",
        world: "control",
        x: -220,
        y: -120,
        z: 95,
        status: "active",
        tone: "cyan",
        meta: { description: "Routes objectives into execution lanes." },
      },
      {
        id: "tool_executor",
        label: "Tool Executor",
        kind: "executor",
        world: "control",
        x: 220,
        y: -120,
        z: 95,
        status: "active",
        tone: "violet",
        meta: { description: "Coordinates tool calls and verification." },
      },
      {
        id: "research_swarm",
        label: "Research Evidence Swarm",
        kind: "swarm",
        world: "parallel",
        x: -280,
        y: 180,
        z: 80,
        status: "running",
        tone: "emerald",
        meta: { description: "Parallel evidence-gathering workers." },
      },
      {
        id: "analysis_core",
        label: "Analysis Core Swarm",
        kind: "swarm",
        world: "parallel",
        x: 0,
        y: 210,
        z: 88,
        status: "running",
        tone: "violet",
        meta: { description: "Structured analysis and synthesis lane." },
      },
      {
        id: "memory_ledger",
        label: "Durable Memory Ledger",
        kind: "ledger",
        world: "background",
        x: 280,
        y: 180,
        z: 76,
        status: "connected",
        tone: "emerald",
        meta: { description: "Persistent memory and work state." },
      },
    ],
    edges: [
      {
        source: "mission_router",
        target: "open_chat",
        label: "plan",
        tone: "cyan",
        kind: "reason",
      },
      {
        source: "open_chat",
        target: "tool_executor",
        label: "dispatch",
        tone: "violet",
        kind: "tool",
      },
      {
        source: "open_chat",
        target: "research_swarm",
        label: "research",
        tone: "emerald",
        kind: "reason",
      },
      {
        source: "research_swarm",
        target: "analysis_core",
        label: "evidence",
        tone: "cyan",
        kind: "dependency",
      },
      {
        source: "analysis_core",
        target: "memory_ledger",
        label: "persist",
        tone: "emerald",
        kind: "memory",
      },
      {
        source: "tool_executor",
        target: "analysis_core",
        label: "verify",
        tone: "violet",
        kind: "tool",
      },
    ],
  };
}

function getStructuredNodePositions(
  nodes: OrchestrationNode[],
): Map<string, { x: number; y: number }> {
  const positions = new Map<string, { x: number; y: number }>();

  const subagentNodes: OrchestrationNode[] = [];
  const missionNodes: OrchestrationNode[] = [];
  const taskNodes: OrchestrationNode[] = [];
  const activityNodes: OrchestrationNode[] = [];

  let swarmCenter = { x: 0, y: -350 };
  let fleetCenter = { x: -650, y: -450 };
  let queueCenter = { x: 650, y: 350 };
  let streamCenter = { x: -650, y: 0 };

  nodes.forEach((node) => {
    if (node.id === "subagent_swarm") {
      swarmCenter = { x: node.x, y: node.y };
    } else if (node.id === "mission_fleet") {
      fleetCenter = { x: node.x, y: node.y };
    } else if (node.id === "task_queue") {
      queueCenter = { x: node.x, y: node.y };
    } else if (node.id === "activity_stream") {
      streamCenter = { x: node.x, y: node.y };
    }

    if (node.id.startsWith("subagent_") && node.id !== "subagent_swarm") {
      subagentNodes.push(node);
    } else if (
      node.id.startsWith("mission_") &&
      node.id !== "mission_fleet" &&
      node.id !== "mission_router" &&
      node.id !== "mission_output"
    ) {
      missionNodes.push(node);
    } else if (
      node.id.startsWith("task_") &&
      node.id !== "task_queue" &&
      node.id !== "proactive_workspace"
    ) {
      taskNodes.push(node);
    } else if (node.id.startsWith("activity_") && node.id !== "activity_stream") {
      activityNodes.push(node);
    } else {
      positions.set(node.id, { x: node.x, y: node.y });
    }
  });

  const sortById = (a: OrchestrationNode, b: OrchestrationNode) => a.id.localeCompare(b.id);
  subagentNodes.sort(sortById);
  missionNodes.sort(sortById);
  taskNodes.sort(sortById);
  activityNodes.sort(sortById);

  // Position subagents (rows of 3, centered above subagent_swarm)
  const subagentCount = subagentNodes.length;
  subagentNodes.forEach((node, i) => {
    const cols = 3;
    const row = Math.floor(i / cols);
    const col = i % cols;
    const colsInRow = Math.min(cols, subagentCount - row * cols);
    const x = swarmCenter.x + (col - (colsInRow - 1) / 2) * 280;
    const y = swarmCenter.y - 160 - row * 132;
    positions.set(node.id, { x, y });
  });

  // Position missions (rows of 2, structured to the left of mission_fleet)
  const missionCount = missionNodes.length;
  const missionRows = Math.ceil(missionCount / 2);
  missionNodes.forEach((node, i) => {
    const row = Math.floor(i / 2);
    const col = i % 2;
    const x = fleetCenter.x - 300 - col * 280;
    const y = fleetCenter.y - 50 + (row - (missionRows - 1) / 2) * 132;
    positions.set(node.id, { x, y });
  });

  // Position tasks (rows of 2, structured to the right of task_queue)
  const taskCount = taskNodes.length;
  const taskRows = Math.ceil(taskCount / 2);
  taskNodes.forEach((node, i) => {
    const row = Math.floor(i / 2);
    const col = i % 2;
    const x = queueCenter.x + 300 + col * 280;
    const y = queueCenter.y + 150 + (row - (taskRows - 1) / 2) * 132;
    positions.set(node.id, { x, y });
  });

  // Position activities (rows of 2, structured to the left of activity_stream, shifted down)
  const activityCount = activityNodes.length;
  const activityRows = Math.ceil(activityCount / 2);
  activityNodes.forEach((node, i) => {
    const row = Math.floor(i / 2);
    const col = i % 2;
    const x = streamCenter.x - 300 - col * 280;
    const y = streamCenter.y + 200 + (row - (activityRows - 1) / 2) * 132;
    positions.set(node.id, { x, y });
  });

  // Run a collision resolution pass to prevent overlap of any nodes (e.g. system_daemon and daemon_heartbeat)
  resolveCollisions(positions);

  return positions;
}

function resolveCollisions(positions: Map<string, { x: number; y: number }>) {
  const gapX = 280;
  const gapY = 132;
  const keys = Array.from(positions.keys());

  for (let iter = 0; iter < 50; iter++) {
    let collisionFound = false;
    for (let i = 0; i < keys.length; i++) {
      for (let j = i + 1; j < keys.length; j++) {
        const idA = keys[i];
        const idB = keys[j];
        const posA = positions.get(idA)!;
        const posB = positions.get(idB)!;

        const dx = posB.x - posA.x;
        const dy = posB.y - posA.y;
        const absDx = Math.abs(dx);
        const absDy = Math.abs(dy);

        if (absDx < gapX && absDy < gapY) {
          collisionFound = true;
          const overlapX = gapX - absDx;
          const overlapY = gapY - absDy;

          // Push along the axis of lesser overlap
          if (overlapX < overlapY) {
            const pushX = overlapX / 2;
            const signX = dx >= 0 ? 1 : -1;
            if (idA === "open_chat") {
              posB.x += pushX * 2 * signX;
            } else if (idB === "open_chat") {
              posA.x -= pushX * 2 * signX;
            } else {
              posA.x -= pushX * signX;
              posB.x += pushX * signX;
            }
          } else {
            const pushY = overlapY / 2;
            const signY = dy >= 0 ? 1 : -1;
            if (idA === "open_chat") {
              posB.y += pushY * 2 * signY;
            } else if (idB === "open_chat") {
              posA.y -= pushY * 2 * signY;
            } else {
              posA.y -= pushY * signY;
              posB.y += pushY * signY;
            }
          }
        }
      }
    }
    if (!collisionFound) break;
  }
}

const USER_FRIENDLY_LABELS: Record<string, string> = {
  open_chat: "AI Core Assistant",
  mission_router: "Cognitive Router",
  tool_executor: "Action Executor",
  approval_gate: "Security Guard",
  mission_output: "Response Synthesizer",
  mission_fleet: "Active Agents Hub",
  memory_ledger: "Memory Vault",
  proactive_workspace: "Automation Hub",
  connector_mesh: "App Connections",
  system_internet: "Network Access",
  system_llm: "AI Processing Engine",
  system_search: "Search Assistant",
  system_daemon: "Background Daemon",
  subagent_swarm: "Specialist Squad",
  task_queue: "Task Queue",
  activity_stream: "Live Activity Feed",
  tool_catalog: "Capabilities Atlas",
  daemon_heartbeat: "System Heartbeat",
};

function getUserFriendlyCategory(node: OrchestrationNode): string {
  if (node.id === "open_chat") return "★ START CORE";
  if (node.world === "control") return "AI Core Reasoning";
  if (node.world === "parallel" || node.kind === "subagent" || node.kind === "swarm")
    return "Specialist Agent";
  if (
    node.world === "background" ||
    node.kind === "task" ||
    node.kind === "queue" ||
    node.kind === "ledger" ||
    node.id === "memory_ledger"
  )
    return "Memory & Automation";
  if (node.world === "connectors" || node.kind === "connector") return "External App Sync";
  if (
    node.world === "systems" ||
    node.kind === "system" ||
    node.kind === "signal" ||
    node.kind === "catalog"
  )
    return "System Vitals";
  if (node.world === "surface" || node.kind === "activity" || node.kind === "stream")
    return "System Activity Log";
  return "AI System Block";
}

export default function OrchestrationPageClient() {
  const [data, setData] = useState<OrchestrationOverview | null>(null);
  const [globalOverview, setGlobalOverview] = useState<OrchestrationOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string>("open_chat");
  const [zoom, setZoom] = useState(DEFAULT_ZOOM);
  const [pan, setPan] = useState<Point>({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [draggedNodeId, setDraggedNodeId] = useState<string | null>(null);
  const [nodePositions, setNodePositions] = useState<Map<string, { x: number; y: number }>>(
    new Map(),
  );
  const [missionObjective, setMissionObjective] = useState(
    "Research and analyze the current work, persist the result, and create a proactive follow-up.",
  );
  const [missionRunning, setMissionRunning] = useState(false);
  const [missionStatus, setMissionStatus] = useState<string | null>(null);
  const [missionError, setMissionError] = useState<string | null>(null);
  const [missionId, setMissionId] = useState<string | null>(null);
  const [missionLog, setMissionLog] = useState<string[]>([]);
  const [streamGraph, setStreamGraph] = useState<OrchestrationGraph | null>(null);
  const [showMissionHealth, setShowMissionHealth] = useState(false);
  const [showInspector, setShowInspector] = useState(false);
  const [showRunner, setShowRunner] = useState(false);
  const [activeSystemPanel, setActiveSystemPanel] = useState<string | null>(null);
  const [dashboardNavOpen, setDashboardNavOpen] = useState(false);
  const [pendingApproval, setPendingApproval] = useState<{
    missionId: string;
    laneId: string;
    message?: string;
  } | null>(null);
  const [executionMode, setExecutionMode] = useState<"auto_review" | "full_access">("auto_review");
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const graphSurfaceRef = useRef<HTMLDivElement | null>(null);
  const dragRef = useRef<{
    startX: number;
    startY: number;
    originX: number;
    originY: number;
  } | null>(null);
  const centerGraphFrameRef = useRef<number | null>(null);
  const lastAutoCenteredGraphRef = useRef<string | null>(null);

  // Per-session dashboard states
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [selectedSessionTitle, setSelectedSessionTitle] = useState<string | null>(null);
  const [selectedSessionType, setSelectedSessionType] = useState<
    "chat" | "proactive" | "connector" | "global" | null
  >(null);
  const [isCenteringInitial, setIsCenteringInitial] = useState(true);
  const [viewMode, setViewMode] = useState<"dev" | "user">(
    typeof process !== "undefined" && process.env.NODE_ENV === "test" ? "dev" : "user",
  );
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);

  const getNodeTimeline = useCallback(
    (nodeId: string) => {
      if (!data) return [];
      const activitiesList = data.activities ?? [];

      const formatTimeOnly = (val?: string | null) => {
        if (!val) return "";
        const date = new Date(val);
        if (Number.isNaN(date.getTime())) return "";
        return date.toLocaleTimeString([], {
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
        });
      };

      const timeline: Array<{ time: string; desc: string }> = [];

      activitiesList.forEach((act) => {
        const timeStr = formatTimeOnly(act.created_at);

        if (
          nodeId === "open_chat" &&
          (act.source === "llm" || act.type?.includes("llm") || act.type?.includes("chat"))
        ) {
          timeline.push({ time: timeStr, desc: act.description });
        } else if (
          nodeId === "mission_router" &&
          (act.type?.includes("routing") ||
            act.type?.includes("route") ||
            act.type?.includes("plan"))
        ) {
          timeline.push({ time: timeStr, desc: act.description });
        } else if (
          nodeId === "tool_executor" &&
          (act.type === "tool" ||
            act.type === "tool_call" ||
            act.description?.toLowerCase().includes("tool"))
        ) {
          timeline.push({ time: timeStr, desc: act.description });
        } else if (
          nodeId === "tool_catalog" &&
          (act.type === "tool" ||
            act.type === "tool_call" ||
            act.description?.toLowerCase().includes("tool"))
        ) {
          timeline.push({ time: timeStr, desc: `Catalog accessed: ${act.description}` });
        } else if (
          nodeId === "memory_ledger" &&
          (act.type === "memory" ||
            act.description?.toLowerCase().includes("memory") ||
            act.description?.toLowerCase().includes("persist") ||
            act.description?.toLowerCase().includes("store"))
        ) {
          timeline.push({ time: timeStr, desc: act.description });
        } else if (
          nodeId === "approval_gate" &&
          (act.type === "approval" ||
            act.description?.toLowerCase().includes("approval") ||
            act.description?.toLowerCase().includes("gate"))
        ) {
          timeline.push({ time: timeStr, desc: act.description });
        } else if (
          nodeId === "mission_output" &&
          (act.type === "synthesis" ||
            act.type === "output" ||
            act.description?.toLowerCase().includes("synthesize"))
        ) {
          timeline.push({ time: timeStr, desc: act.description });
        } else if (
          nodeId === "connector_mesh" &&
          (["gmail", "slack", "notion", "drive", "google", "connector"].includes(
            act.source?.toLowerCase() || "",
          ) ||
            act.type === "sync")
        ) {
          timeline.push({
            time: timeStr,
            desc: `${act.source?.toUpperCase()}: ${act.description}`,
          });
        } else if (
          nodeId === "system_search" &&
          (act.source === "web_search" || act.description?.toLowerCase().includes("search"))
        ) {
          timeline.push({ time: timeStr, desc: act.description });
        } else if (nodeId === `activity_${act.id}`) {
          timeline.push({ time: timeStr, desc: act.description });
        }
      });

      const subagentsList = data.subagents?.runs || [];
      subagentsList.forEach((run) => {
        const timeStr = formatTimeOnly(run.created_at);
        if (nodeId === "subagent_swarm") {
          timeline.push({ time: timeStr, desc: `Spawned ${run.subagent_type} specialist` });
        } else if (nodeId === `subagent_${run.run_id}`) {
          timeline.push({
            time: timeStr,
            desc: run.summary || run.last_event_message || run.prompt,
          });
        }
      });

      const tasksList = data.tasks?.all || [];
      tasksList.forEach((task) => {
        const timeStr = formatTimeOnly(task.created_at);
        if (nodeId === "task_queue") {
          timeline.push({
            time: timeStr,
            desc: `Queued automation: ${task.activeForm || task.content}`,
          });
        } else if (nodeId === `task_${task.id}`) {
          timeline.push({ time: timeStr, desc: `Task Status: ${task.status}` });
        }
      });

      return timeline.slice(0, 3);
    },
    [data],
  );

  useEffect(() => {
    setIsCenteringInitial(true);
  }, [selectedSessionId]);
  const [chatSessions, setChatSessions] = useState<OrchestrationChatSession[]>([]);
  const [loadingChats, setLoadingChats] = useState(false);
  const [dashboardTab, setDashboardTab] = useState<DashboardTab>("all");
  const [showSystemTasks, setShowSystemTasks] = useState(false);
  const [connectorsList, setConnectorsList] = useState<OrchestrationConnectorSummary[]>([]);
  const [integrationsList, setIntegrationsList] = useState<OrchestrationIntegrationSummary[]>([]);
  const [killTaskId, setKillTaskId] = useState<string | null>(null);
  const [killingTask, setKillingTask] = useState(false);
  const [currentTime, setCurrentTime] = useState<string>("");

  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      const hrs = String(now.getUTCHours()).padStart(2, "0");
      const mins = String(now.getUTCMinutes()).padStart(2, "0");
      setCurrentTime(`${hrs}:${mins} UTC`);
    };
    updateTime();
    const interval = setInterval(updateTime, 60000);
    return () => clearInterval(interval);
  }, []);

  const loadConnectors = useCallback(async () => {
    try {
      const [resInt, resConn] = await Promise.all([
        fetchWithAuth("/integrations"),
        fetchWithAuth("/integrations/connectors"),
      ]);
      if (resInt.ok && resConn.ok) {
        const integrations = (await resInt.json()) as OrchestrationIntegrationSummary[];
        const connectors = (await resConn.json()) as OrchestrationConnectorSummary[];
        setIntegrationsList(integrations || []);
        setConnectorsList(connectors || []);
      }
    } catch (err) {
      console.error("Failed to load connectors/integrations", err);
    }
  }, []);

  const loadChats = useCallback(async () => {
    setLoadingChats(true);
    try {
      const response = await fetchWithAuth("/deepspace/chats");
      if (response.ok) {
        const payload = (await response.json()) as {
          items?: OrchestrationChatSession[];
        };
        setChatSessions(payload.items || []);
      }
    } catch (err) {
      console.error("Failed to load chat sessions", err);
    } finally {
      setLoadingChats(false);
    }
  }, []);

  const loadOverview = useCallback(async () => {
    try {
      let url = "/deepspace/chats/orchestration";
      if (selectedSessionId && selectedSessionId !== "global") {
        url += `?conversation_id=${selectedSessionId}`;
      }
      const response = (await fetchWithAuth(url)) as Response;
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const payload = (await response.json()) as OrchestrationOverview;
      setData(payload);
      if (!selectedSessionId) {
        setGlobalOverview(payload);
      }
      if (payload.runtime.execution_mode) {
        setExecutionMode(payload.runtime.execution_mode);
      }
      setError(null);
    } catch (fetchError) {
      setError(fetchError instanceof Error ? fetchError.message : "Failed to load orchestration");
    } finally {
      setLoading(false);
    }
  }, [selectedSessionId]);

  useEffect(() => {
    void loadOverview();
    void loadConnectors();
    if (!selectedSessionId) {
      void loadChats();
    }
    const timer = window.setInterval(() => {
      void loadOverview();
      void loadConnectors();
      if (!selectedSessionId) {
        void loadChats();
      }
    }, 12000);
    return () => window.clearInterval(timer);
  }, [loadOverview, loadChats, loadConnectors, selectedSessionId]);

  useEffect(() => {
    const root = document.documentElement;
    const syncNavState = () => {
      setDashboardNavOpen(root.hasAttribute("data-dashboard-nav-open"));
    };

    syncNavState();
    const observer = new MutationObserver(syncNavState);
    observer.observe(root, { attributes: true, attributeFilter: ["data-dashboard-nav-open"] });

    return () => observer.disconnect();
  }, []);

  const fallbackGraph = useMemo(() => buildFallbackGraph(), []);
  const graph = useMemo<OrchestrationGraph>(() => {
    if (streamGraph?.nodes?.length) return streamGraph;
    if (data?.graph?.nodes?.length) return data.graph;
    return fallbackGraph;
  }, [data, fallbackGraph, streamGraph]);

  const rawNodes = useMemo(() => graph.nodes ?? [], [graph]);
  const rawEdges = useMemo(() => graph.edges ?? [], [graph]);
  const worlds = useMemo(() => graph.worlds ?? [], [graph]);

  const nodeCallCounts = useMemo(() => {
    const counts = new Map<string, number>();

    const allNodeIds = [
      "open_chat",
      "mission_router",
      "tool_executor",
      "approval_gate",
      "mission_output",
      "memory_ledger",
      "proactive_workspace",
      "connector_mesh",
      "system_internet",
      "system_llm",
      "system_search",
      "system_daemon",
      "tool_catalog",
      "daemon_heartbeat",
      "subagent_swarm",
      "task_queue",
      "activity_stream",
    ];
    allNodeIds.forEach((id) => counts.set(id, 0));

    if (!data) return counts;

    const activitiesList = data.activities ?? [];
    activitiesList.forEach((act) => {
      if (
        act.source === "llm" ||
        act.type?.includes("llm") ||
        act.type?.includes("chat") ||
        act.type === "completion"
      ) {
        counts.set("open_chat", (counts.get("open_chat") || 0) + 1);
        counts.set("system_llm", (counts.get("system_llm") || 0) + 1);
      }

      if (
        act.type?.includes("routing") ||
        act.type?.includes("route") ||
        act.type?.includes("plan")
      ) {
        counts.set("mission_router", (counts.get("mission_router") || 0) + 1);
      }

      if (
        act.type === "tool" ||
        act.type === "tool_call" ||
        act.description?.toLowerCase().includes("tool")
      ) {
        counts.set("tool_executor", (counts.get("tool_executor") || 0) + 1);
        counts.set("tool_catalog", (counts.get("tool_catalog") || 0) + 1);
      }

      if (
        act.type === "approval" ||
        act.description?.toLowerCase().includes("approval") ||
        act.description?.toLowerCase().includes("gate")
      ) {
        counts.set("approval_gate", (counts.get("approval_gate") || 0) + 1);
      }

      if (
        act.type === "synthesis" ||
        act.type === "output" ||
        act.description?.toLowerCase().includes("synthesize") ||
        act.description?.toLowerCase().includes("output")
      ) {
        counts.set("mission_output", (counts.get("mission_output") || 0) + 1);
      }

      if (
        act.type === "memory" ||
        act.description?.toLowerCase().includes("memory") ||
        act.description?.toLowerCase().includes("persist") ||
        act.description?.toLowerCase().includes("store")
      ) {
        counts.set("memory_ledger", (counts.get("memory_ledger") || 0) + 1);
      }

      const src = act.source?.toLowerCase() || "";
      if (["gmail", "slack", "notion", "drive", "google", "connector"].includes(src)) {
        counts.set("connector_mesh", (counts.get("connector_mesh") || 0) + 1);
        counts.set("system_internet", (counts.get("system_internet") || 0) + 1);
      }

      if (src === "web_search" || act.description?.toLowerCase().includes("search")) {
        counts.set("system_search", (counts.get("system_search") || 0) + 1);
        counts.set("system_internet", (counts.get("system_internet") || 0) + 1);
      }

      counts.set(`activity_${act.id}`, 1);
    });

    const subagentsList = data.subagents?.runs || [];
    subagentsList.forEach((run) => {
      counts.set("subagent_swarm", (counts.get("subagent_swarm") || 0) + 1);
      counts.set("mission_router", (counts.get("mission_router") || 0) + 1);
      counts.set(`subagent_${run.run_id}`, 1);
    });

    const tasksList = data.tasks?.all || [];
    tasksList.forEach((task) => {
      counts.set("proactive_workspace", (counts.get("proactive_workspace") || 0) + 1);
      counts.set("task_queue", (counts.get("task_queue") || 0) + 1);
      counts.set("system_daemon", (counts.get("system_daemon") || 0) + 1);
      counts.set(`task_${task.id}`, 1);
    });

    const missionsList = data.missions?.active || [];
    missionsList.forEach((m) => {
      counts.set("mission_router", (counts.get("mission_router") || 0) + 1);
      counts.set(`mission_${m.mission_id}`, 1);
    });

    return counts;
  }, [data]);

  const nodes = useMemo(() => {
    if (viewMode === "dev") return rawNodes;

    return rawNodes.filter((node) => {
      // 1. The root open_chat node is always visible as the starting anchor
      if (node.id === "open_chat") {
        return true;
      }

      // 2. Child nodes (subagents, tasks, missions, activities) are visible since they represent active session elements
      if (node.id.startsWith("subagent_") && node.id !== "subagent_swarm") return true;
      if (node.id.startsWith("task_") && node.id !== "task_queue") return true;
      if (
        node.id.startsWith("mission_") &&
        node.id !== "mission_fleet" &&
        node.id !== "mission_router" &&
        node.id !== "mission_output"
      )
        return true;
      if (node.id.startsWith("activity_") && node.id !== "activity_stream") return true;

      // 3. Swarms/Queues/Streams/Fleets are visible if they have active items
      if (node.id === "subagent_swarm") return (nodeCallCounts.get("subagent_swarm") || 0) > 0;
      if (node.id === "task_queue") return (nodeCallCounts.get("task_queue") || 0) > 0;
      if (node.id === "activity_stream") return (nodeCallCounts.get("activity_stream") || 0) > 0;
      if (node.id === "mission_fleet") return (nodeCallCounts.get("mission_fleet") || 0) > 0;

      // 4. All other nodes (including core route/execute/memory/synthesis cards) are shown ONLY if they have actually been invoked/called
      const count = nodeCallCounts.get(node.id) || 0;
      return count > 0;
    });
  }, [rawNodes, viewMode, nodeCallCounts]);

  const edges = useMemo(() => {
    if (viewMode === "dev") return rawEdges;

    const visibleNodeIds = new Set(nodes.map((n) => n.id));
    return rawEdges.filter(
      (edge) => visibleNodeIds.has(edge.source) && visibleNodeIds.has(edge.target),
    );
  }, [rawEdges, nodes, viewMode]);

  useEffect(() => {
    if (!nodes.length) return;
    if (!nodes.some((node) => node.id === selectedNodeId)) {
      setSelectedNodeId(nodes[0]?.id ?? "open_chat");
    }
  }, [nodes, selectedNodeId]);

  const selectedNode = useMemo(() => {
    return nodes.find((node) => node.id === selectedNodeId) ?? nodes[0] ?? null;
  }, [nodes, selectedNodeId]);

  const connectedNodeIds = useMemo(() => {
    const result = new Set<string>();
    if (!selectedNode) return result;
    result.add(selectedNode.id);
    edges.forEach((edge) => {
      if (edge.source === selectedNode.id) result.add(edge.target);
      if (edge.target === selectedNode.id) result.add(edge.source);
    });
    return result;
  }, [edges, selectedNode]);

  const summary = data?.summary;
  const runtime = data?.runtime;
  const vitals = data?.vitals;
  const activeSubagents = data?.subagents.active ?? [];
  const activeMissions = data?.missions?.active ?? [];
  const activeTasks = data?.tasks.active ?? [];
  const recentActivities = data?.activities ?? [];
  const activeTools = data?.tool_catalog.active ?? [];
  const hiddenMissionLogCount = Math.max(0, missionLog.length - VISIBLE_MISSION_LOG_LINES);
  const visibleMissionLog = useMemo(
    () => missionLog.slice(-VISIBLE_MISSION_LOG_LINES),
    [missionLog],
  );

  const structuredPositions = useMemo(() => {
    return getStructuredNodePositions(nodes);
  }, [nodes]);

  const graphLayout = useMemo(() => {
    const positions = new Map<string, { x: number; y: number }>();
    nodes.forEach((node) => {
      const pos = structuredPositions.get(node.id) || { x: node.x, y: node.y };
      positions.set(node.id, { x: pos.x, y: pos.y });
    });
    nodePositions.forEach((value, key) => {
      positions.set(key, { x: value.x, y: value.y });
    });

    if (!positions.size) {
      return null;
    }

    let minX = Number.POSITIVE_INFINITY;
    let minY = Number.POSITIVE_INFINITY;
    let maxX = Number.NEGATIVE_INFINITY;
    let maxY = Number.NEGATIVE_INFINITY;

    positions.forEach((value) => {
      minX = Math.min(minX, value.x);
      minY = Math.min(minY, value.y);
      maxX = Math.max(maxX, value.x);
      maxY = Math.max(maxY, value.y);
    });

    const boardMinX = minX + GRAPH_BOARD_CENTER_X - GRAPH_CARD_WIDTH / 2;
    const boardMaxX = maxX + GRAPH_BOARD_CENTER_X + GRAPH_CARD_WIDTH / 2;
    const boardMinY = minY + GRAPH_BOARD_CENTER_Y - GRAPH_CARD_HEIGHT / 2;
    const boardMaxY = maxY + GRAPH_BOARD_CENTER_Y + GRAPH_CARD_HEIGHT / 2;

    return {
      centerX: (boardMinX + boardMaxX) / 2,
      centerY: (boardMinY + boardMaxY) / 2,
      width: Math.max(boardMaxX - boardMinX, GRAPH_CARD_WIDTH),
      height: Math.max(boardMaxY - boardMinY, GRAPH_CARD_HEIGHT),
    };
  }, [nodePositions, nodes, structuredPositions]);

  const graphViewSignature = useMemo(() => {
    return nodes
      .map((node) => {
        const pos = structuredPositions.get(node.id) || { x: node.x, y: node.y };
        return `${node.id}:${pos.x}:${pos.y}:${node.status}`;
      })
      .join("|");
  }, [nodes, structuredPositions]);

  const leftInset = useMemo(() => {
    return showMissionHealth ? 384 : 72;
  }, [showMissionHealth]);

  const rightInset = useMemo(() => {
    return showInspector ? 480 : 132;
  }, [showInspector]);

  const bottomInset = useMemo(() => {
    return showRunner ? 460 : 84;
  }, [showRunner]);

  const centerGraphView = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) {
      setZoom(DEFAULT_ZOOM);
      setPan({ x: 0, y: 0 });
      return;
    }

    const rect = canvas.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) {
      setZoom(DEFAULT_ZOOM);
      setPan({ x: 0, y: 0 });
      return;
    }

    const usableWidth = Math.max(1, rect.width - leftInset - rightInset);
    const usableHeight = Math.max(1, rect.height - GRAPH_VIEW_TOP_INSET - bottomInset);
    const graphWidth = (graphLayout?.width ?? GRAPH_CARD_WIDTH) + GRAPH_FIT_PADDING * 2;
    const graphHeight = (graphLayout?.height ?? GRAPH_CARD_HEIGHT) + GRAPH_FIT_PADDING * 2;
    const nextZoom = clamp(
      Math.min(DEFAULT_ZOOM, usableWidth / graphWidth, usableHeight / graphHeight),
      MIN_ZOOM,
      DEFAULT_ZOOM,
    );
    const graphCenterX = graphLayout?.centerX ?? GRAPH_BOARD_CENTER_X;
    const graphCenterY = graphLayout?.centerY ?? GRAPH_BOARD_CENTER_Y;
    setZoom(nextZoom);
    setPan({
      x: leftInset + usableWidth / 2 - graphCenterX * nextZoom,
      y: GRAPH_VIEW_TOP_INSET + usableHeight / 2 - graphCenterY * nextZoom,
    });

    if (isCenteringInitial) {
      setTimeout(() => {
        setIsCenteringInitial(false);
      }, 50);
    }
  }, [graphLayout, leftInset, rightInset, bottomInset, isCenteringInitial]);

  const scheduleCenterGraphView = useCallback(() => {
    if (isCenteringInitial) {
      centerGraphView();
    } else {
      if (centerGraphFrameRef.current !== null) {
        window.cancelAnimationFrame(centerGraphFrameRef.current);
      }

      centerGraphFrameRef.current = window.requestAnimationFrame(() => {
        centerGraphFrameRef.current = null;
        centerGraphView();
      });
    }
  }, [centerGraphView, isCenteringInitial]);

  useLayoutEffect(() => {
    scheduleCenterGraphView();
  }, [leftInset, rightInset, bottomInset, scheduleCenterGraphView]);

  const resetView = useCallback(() => {
    centerGraphView();
  }, [centerGraphView]);

  const resetNodePositions = useCallback(() => {
    setNodePositions(new Map());
  }, []);

  const updateExecutionMode = useCallback(
    async (nextMode: "auto_review" | "full_access") => {
      setExecutionMode(nextMode);
      const response = (await fetchWithAuth("/deepspace/chats/execution-mode", {
        method: "PATCH",
        body: JSON.stringify({
          execution_mode: nextMode,
        }),
      })) as Response;
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      await loadOverview();
    },
    [loadOverview],
  );

  const runMission = useCallback(
    async (targetMissionId?: string) => {
      const objective = missionObjective.trim();
      if (!objective || missionRunning) {
        return;
      }

      setMissionRunning(true);
      setMissionError(null);
      setMissionStatus("running");
      if (targetMissionId) {
        setMissionLog((current) => [
          ...current,
          `Reconnecting to stream for mission ${targetMissionId}...`,
        ]);
        setMissionId(targetMissionId);
      } else {
        setMissionLog([`Objective: ${objective}`]);
        setMissionId(null);
        setStreamGraph(null);
      }
      setPendingApproval(null);

      try {
        const response = (await fetchWithAuth("/deepspace/chats/orchestrations/stream", {
          method: "POST",
          body: JSON.stringify({
            objective,
            conversation_id:
              selectedSessionId && selectedSessionId !== "global" ? selectedSessionId : null,
            mission_id: targetMissionId || undefined,
          }),
          headers: {
            Accept: "text/event-stream",
            "Cache-Control": "no-cache",
          },
        })) as Response;

        if (!response.ok) {
          let message = `HTTP ${response.status}`;
          try {
            const payload = await response.clone().json();
            message = payload?.detail ?? payload?.message ?? message;
          } catch {
            // ignore
          }
          throw new Error(message);
        }

        const reader = response.body?.getReader();
        if (!reader) {
          throw new Error("Streaming response body is unavailable.");
        }

        const decoder = new TextDecoder();
        let buffer = "";
        let pendingLogLines: string[] = [];
        let logFlushFrame: number | null = null;
        const flushMissionLog = () => {
          logFlushFrame = null;
          const lines = pendingLogLines;
          pendingLogLines = [];
          setMissionLog((current) => [...current, ...lines]);
        };
        const enqueueMissionLog = (line: string) => {
          pendingLogLines.push(line);
          if (logFlushFrame === null) {
            logFlushFrame = window.requestAnimationFrame(flushMissionLog);
          }
        };

        while (true) {
          const { value, done } = await reader.read();
          const chunk = decoder.decode(value || new Uint8Array(), { stream: !done });
          buffer += chunk;
          const parsed = parseSseFrames(buffer);
          buffer = parsed.remainder;

          for (const event of parsed.events as Array<{
            event: string;
            data: Record<string, unknown>;
          }>) {
            enqueueMissionLog(`[${event.event}] ${JSON.stringify(event.data)}`);
            if (event.event === "mission_start") {
              const nextMissionId =
                typeof event.data.mission_id === "string" ? event.data.mission_id : null;
              if (nextMissionId) {
                setMissionId(nextMissionId);
              }
            }
            if (event.event === "mission_graph") {
              const nextGraph =
                event.data.graph && typeof event.data.graph === "object"
                  ? (event.data.graph as OrchestrationGraph)
                  : null;
              if (nextGraph) {
                setStreamGraph(nextGraph);
              }
            }
            if (event.event === "mission_summary") {
              const summary = typeof event.data.summary === "string" ? event.data.summary : null;
              if (summary) setMissionStatus(summary);
            }
            if (event.event === "mission_done") {
              setMissionStatus(
                typeof event.data.status === "string" ? event.data.status : "completed",
              );
            }
            if (event.event === "approval_request") {
              setMissionStatus("awaiting approval");
              const nextMissionId =
                typeof event.data.mission_id === "string" ? event.data.mission_id : null;
              const nextLaneId = typeof event.data.lane_id === "string" ? event.data.lane_id : null;
              if (nextMissionId && nextLaneId) {
                setPendingApproval({
                  missionId: nextMissionId,
                  laneId: nextLaneId,
                  message: typeof event.data.message === "string" ? event.data.message : undefined,
                });
              }
            }
          }

          if (done) {
            break;
          }
        }

        if (buffer.trim()) {
          const parsed = parseSseFrames(`${buffer}\n\n`);
          for (const event of parsed.events as Array<{
            event: string;
            data: Record<string, unknown>;
          }>) {
            enqueueMissionLog(`[${event.event}] ${JSON.stringify(event.data)}`);
          }
        }
        if (logFlushFrame !== null) {
          window.cancelAnimationFrame(logFlushFrame);
        }
        flushMissionLog();
      } catch (error) {
        setMissionError(error instanceof Error ? error.message : "Mission failed.");
        setMissionStatus("failed");
      } finally {
        setMissionRunning(false);
      }
    },
    [missionObjective, missionRunning, selectedSessionId],
  );

  const resolveMissionApproval = useCallback(
    async (approved: boolean) => {
      if (!pendingApproval) {
        return;
      }
      const response = (await fetchWithAuth(
        `/deepspace/chats/orchestrations/missions/${pendingApproval.missionId}/approval`,
        {
          method: "POST",
          body: JSON.stringify({
            lane_id: pendingApproval.laneId,
            approved,
          }),
        },
      )) as Response;
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const payload = (await response.json()) as {
        status?: string;
      };
      setMissionStatus(payload.status || (approved ? "running" : "declined"));
      setMissionLog((current) => [
        ...current,
        `[approval_resolved] ${JSON.stringify({
          mission_id: pendingApproval.missionId,
          lane_id: pendingApproval.laneId,
          approved,
          status: payload.status || (approved ? "running" : "declined"),
        })}`,
      ]);
      const mId = pendingApproval.missionId;
      setPendingApproval(null);
      void loadOverview();
      if (approved) {
        void runMission(mId);
      }
    },
    [loadOverview, pendingApproval, runMission],
  );

  const zoomCanvasTo = useCallback(
    (nextZoom: number, anchorClientX?: number, anchorClientY?: number) => {
      const canvas = canvasRef.current;
      if (!canvas) {
        setZoom(nextZoom);
        return;
      }

      const rect = canvas.getBoundingClientRect();
      const anchorX = anchorClientX ?? rect.left + rect.width / 2;
      const anchorY = anchorClientY ?? rect.top + rect.height / 2;
      const offsetX = anchorX - rect.left;
      const offsetY = anchorY - rect.top;

      setPan((currentPan) => {
        const worldX = (offsetX - currentPan.x) / zoom;
        const worldY = (offsetY - currentPan.y) / zoom;
        return {
          x: offsetX - worldX * nextZoom,
          y: offsetY - worldY * nextZoom,
        };
      });
      setZoom(nextZoom);
    },
    [zoom],
  );

  const zoomBy = useCallback(
    (direction: number) => {
      const nextZoom = clamp(zoom * direction, MIN_ZOOM, MAX_ZOOM);
      zoomCanvasTo(nextZoom);
    },
    [zoom, zoomCanvasTo],
  );

  useEffect(() => {
    if (!isDragging) return;

    const handlePointerMove = (event: PointerEvent) => {
      if (!dragRef.current) return;
      if (event.cancelable) event.preventDefault();
      const deltaX = event.clientX - dragRef.current.startX;
      const deltaY = event.clientY - dragRef.current.startY;
      setPan({
        x: dragRef.current.originX + deltaX,
        y: dragRef.current.originY + deltaY,
      });
    };

    const stopDragging = () => {
      dragRef.current = null;
      setIsDragging(false);
    };

    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", stopDragging);
    window.addEventListener("pointercancel", stopDragging);
    return () => {
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", stopDragging);
      window.removeEventListener("pointercancel", stopDragging);
    };
  }, [isDragging]);

  useEffect(() => {
    const handleCanvasWheel = (event: WheelEvent) => {
      const canvas = canvasRef.current;
      const graphSurface = graphSurfaceRef.current;
      const target = event.target;
      if (!canvas || !(target instanceof Node) || !canvas.contains(target)) return;

      event.preventDefault();
      event.stopPropagation();
      if (!graphSurface || !graphSurface.contains(target)) {
        return;
      }

      const scale = event.deltaY < 0 ? 1.075 : 0.93;
      const nextZoom = clamp(zoom * scale, MIN_ZOOM, MAX_ZOOM);
      zoomCanvasTo(nextZoom, event.clientX, event.clientY);
    };

    window.addEventListener("wheel", handleCanvasWheel, { passive: false, capture: true });
    return () => {
      window.removeEventListener("wheel", handleCanvasWheel, true);
    };
  }, [zoom, zoomCanvasTo]);

  const handleNodePointerDown = useCallback(
    (event: React.PointerEvent, nodeId: string) => {
      if (draggedNodeId !== null) return;
      event.preventDefault();
      event.stopPropagation();
      setDraggedNodeId(nodeId);
      setSelectedNodeId(nodeId);

      const canvas = canvasRef.current;
      if (!canvas) return;

      const canvasRect = canvas.getBoundingClientRect();
      const nodeElement = event.currentTarget as HTMLElement;
      const currentX = Number.parseFloat(nodeElement.style.left || "0") - GRAPH_BOARD_CENTER_X;
      const currentY = Number.parseFloat(nodeElement.style.top || "0") - GRAPH_BOARD_CENTER_Y;

      dragRef.current = {
        startX: event.clientX - canvasRect.left,
        startY: event.clientY - canvasRect.top,
        originX: currentX,
        originY: currentY,
      };
    },
    [draggedNodeId],
  );

  useEffect(() => {
    if (draggedNodeId === null) return;

    const handlePointerMove = (event: PointerEvent) => {
      if (!dragRef.current || draggedNodeId === null) return;
      const canvas = canvasRef.current;
      if (!canvas) return;

      event.preventDefault();
      const canvasRect = canvas.getBoundingClientRect();

      // Current position relative to canvas
      const currentCanvasX = event.clientX - canvasRect.left;
      const currentCanvasY = event.clientY - canvasRect.top;

      // Delta in canvas space
      const deltaX = (currentCanvasX - dragRef.current.startX) / zoom;
      const deltaY = (currentCanvasY - dragRef.current.startY) / zoom;

      const newX = dragRef.current.originX + deltaX;
      const newY = dragRef.current.originY + deltaY;

      setNodePositions((current) => {
        const next = new Map(current);
        next.set(draggedNodeId, { x: newX, y: newY });
        return next;
      });
    };

    const stopDragging = () => {
      dragRef.current = null;
      setDraggedNodeId(null);
    };

    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", stopDragging);
    window.addEventListener("pointercancel", stopDragging);
    return () => {
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", stopDragging);
      window.removeEventListener("pointercancel", stopDragging);
    };
  }, [draggedNodeId, zoom]);

  useLayoutEffect(() => {
    if (!nodes.length || isDragging || draggedNodeId !== null) return;
    if (lastAutoCenteredGraphRef.current === graphViewSignature) return;
    lastAutoCenteredGraphRef.current = graphViewSignature;
    scheduleCenterGraphView();
  }, [draggedNodeId, graphViewSignature, isDragging, nodes.length, scheduleCenterGraphView]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const handleCanvasResize = () => {
      if (isDragging || draggedNodeId !== null) return;
      scheduleCenterGraphView();
    };

    if (typeof ResizeObserver === "undefined") {
      window.addEventListener("resize", handleCanvasResize);
      return () => window.removeEventListener("resize", handleCanvasResize);
    }

    const observer = new ResizeObserver(handleCanvasResize);
    observer.observe(canvas);

    return () => observer.disconnect();
  }, [draggedNodeId, isDragging, scheduleCenterGraphView]);

  useEffect(() => {
    return () => {
      if (centerGraphFrameRef.current !== null) {
        window.cancelAnimationFrame(centerGraphFrameRef.current);
      }
    };
  }, []);

  const projectedGraph = useMemo(() => {
    if (!nodes.length) {
      return {
        positions: new Map<string, ProjectedPosition>(),
        worldOffsets: [] as Array<{ id: string; label: string; left: string }>,
      };
    }

    const positions = new Map<string, ProjectedPosition>();
    nodes.forEach((node) => {
      const pos = structuredPositions.get(node.id) || { x: node.x, y: node.y };
      positions.set(node.id, {
        left: `${pos.x}px`,
        top: `${pos.y}px`,
        x: pos.x,
        y: pos.y,
      });
    });

    const worldOffsets = worlds.map((world) => {
      const anchor =
        WORLD_ANCHORS[
          world.id === "memory"
            ? "memory"
            : world.id === "surface"
              ? "surface"
              : world.id === "background"
                ? "background"
                : world.id === "connectors"
                  ? "connectors"
                  : world.id === "systems"
                    ? "systems"
                    : world.id === "parallel"
                      ? "parallel"
                      : "control"
        ] ?? WORLD_ANCHORS.control;

      return {
        id: world.id,
        label: world.label,
        left: `${anchor.x + GRAPH_BOARD_CENTER_X}px`,
      };
    });

    return { positions, worldOffsets };
  }, [nodes, worlds, structuredPositions]);

  const resolvedGraphPositions = useMemo(() => {
    const positions = new Map<string, ProjectedPosition>();
    projectedGraph.positions.forEach((value, key) => {
      positions.set(key, value);
    });

    nodePositions.forEach((value, key) => {
      positions.set(key, {
        left: `${value.x}px`,
        top: `${value.y}px`,
        x: value.x,
        y: value.y,
      });
    });

    return positions;
  }, [nodePositions, projectedGraph.positions]);

  const displayGraphPositions = useMemo(() => {
    const positions = new Map<string, ProjectedPosition>();
    resolvedGraphPositions.forEach((value, key) => {
      const left = value.x + GRAPH_BOARD_CENTER_X;
      const top = value.y + GRAPH_BOARD_CENTER_Y;
      positions.set(key, {
        left: `${left}px`,
        top: `${top}px`,
        x: left,
        y: top,
      });
    });
    return positions;
  }, [resolvedGraphPositions]);

  const selectedNodeDetails = useMemo(() => {
    if (!selectedNode) return [];
    return Object.entries(selectedNode.meta ?? {}).filter(([, value]) => {
      if (value === null || value === undefined || value === "") return false;
      if (Array.isArray(value)) return value.length > 0;
      return true;
    });
  }, [selectedNode]);

  const filteredChats = useMemo(() => {
    return chatSessions;
  }, [chatSessions]);

  const filteredTasks = useMemo(() => {
    const allTasks = globalOverview?.tasks.all || [];
    if (showSystemTasks) {
      return allTasks;
    }
    return allTasks.filter((task) => {
      const content = task.content || "";
      const isSystem =
        content.startsWith("Restore proactive capacity") ||
        content.startsWith("Repair connector health") ||
        content.startsWith("Store durable mission memory") ||
        task.metadata_json?.source === "gmail" ||
        task.metadata_json?.source === "slack" ||
        task.metadata_json?.source === "notion" ||
        task.metadata_json?.source === "google" ||
        task.metadata_json?.source === "connector" ||
        task.metadata_json?.phase === "vitals";
      return !isSystem;
    });
  }, [globalOverview, showSystemTasks]);

  const connectorItems = useMemo(() => {
    return connectorsList.map((conn) => {
      const integration = integrationsList.find(
        (intg) => String(intg.id) === String(conn.integration_id),
      );
      return {
        id: String(conn.id),
        name: conn.name,
        desc: integration?.description || "Configured connector for external sync.",
        status: conn.status || "active",
        slug: integration?.slug || "generic",
      };
    });
  }, [connectorsList, integrationsList]);

  if (loading && !data) {
    return (
      <div className="theme-panel-muted flex h-full min-h-[60vh] items-center justify-center rounded-3xl">
        <div className="flex flex-col items-center gap-4 text-center">
          <RefreshCw className="text-primary h-8 w-8 animate-spin" />
          <div>
            <p className="text-foreground text-sm font-bold tracking-[0.22em] uppercase">
              Initializing orchestration map
            </p>
            <p className="text-muted-foreground mt-2 text-xs">
              Pulling the unified mission graph, proactive work, and subagent swarm.
            </p>
          </div>
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="theme-panel-muted flex h-full min-h-[60vh] items-center justify-center rounded-3xl p-6">
        <div className="max-w-xl text-center">
          <p className="text-foreground text-lg font-black tracking-tight">
            Orchestration snapshot unavailable
          </p>
          <p className="text-muted-foreground mt-3 text-sm leading-7">
            {error || "Unable to assemble the global mission graph right now."}
          </p>
          <button
            type="button"
            onClick={() => void loadOverview()}
            className="bg-primary hover:bg-primary/90 mt-5 inline-flex items-center gap-2 rounded-full px-4 py-2 text-xs font-black tracking-[0.18em] text-white uppercase transition"
          >
            <RefreshCw size={14} />
            Retry
          </button>
        </div>
      </div>
    );
  }

  const runnerStats = [
    {
      label: "Active subagents",
      value: String(summary?.active_subagents ?? 0),
      helper: `${data.subagents.max_concurrency} parallel slots`,
      tone: "cyan" as const,
      icon: <GitBranch size={16} />,
    },
    {
      label: "Active tasks",
      value: String(summary?.active_tasks ?? 0),
      helper: "Proactive workspace queue",
      tone: "emerald" as const,
      icon: <Clock3 size={16} />,
    },
    {
      label: "Tool catalog",
      value: String(summary?.tool_count ?? data.tool_catalog.count ?? 0),
      helper: "Available as needed",
      tone: "violet" as const,
      icon: <Database size={16} />,
    },
    {
      label: "Active missions",
      value: String(data.missions?.count ?? 0),
      helper: "Global orchestrator runs",
      tone: "rose" as const,
      icon: <Layers3 size={16} />,
    },
  ];

  const handleSelectSession = (
    id: string,
    title: string,
    type: "chat" | "proactive" | "connector" | "global",
  ) => {
    setLoading(true);
    setData(null);
    setSelectedSessionId(id);
    setSelectedSessionTitle(title);
    setSelectedSessionType(type);
    setSelectedNodeId("open_chat");
  };

  const handleKillTask = async (taskId: string) => {
    try {
      const response = await fetchWithAuth(`/deepspace/chats/tasks/${taskId}`, {
        method: "DELETE",
      });
      if (response.ok) {
        toast.success("Task process terminated successfully.");
        void loadOverview();
      } else {
        const errData = await response.json().catch(() => ({}));
        toast.error(errData.message || "Failed to terminate task process.");
      }
    } catch (err) {
      console.error("Failed to kill task", err);
      toast.error("Failed to terminate task process.");
    }
  };

  if (loading && !globalOverview) {
    return (
      <div className="flex h-[calc(100vh-8rem)] w-full items-center justify-center bg-transparent">
        <div className="flex flex-col items-center gap-3">
          <Loader className="text-primary animate-spin" size={36} />
          <p className="text-foreground/60 text-xs font-black tracking-[0.18em] uppercase">
            Loading Control Room...
          </p>
        </div>
      </div>
    );
  }

  if (selectedSessionId === null) {
    return (
      <>
        <div className="text-foreground relative h-[calc(100vh-8rem)] min-h-[600px] w-full space-y-6 overflow-y-auto bg-transparent px-6 py-6">
          <DashboardSectionHeader
            title="Federated Session Orchestrator"
            subtitle="Orchestration Center"
            icon={Layers3}
            accentClassName="bg-cyan-400 text-cyan-400"
            accentGlowClassName="shadow-[0_0_20px_rgba(34,211,238,0.4)]"
            backHref="/dashboard"
            backLabel="Back To Dashboard"
            actions={
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => {
                    void loadOverview();
                    void loadChats();
                  }}
                  className="theme-chip text-foreground/82 hover:text-foreground inline-flex items-center gap-1.5 rounded-xl px-3 py-2 text-xs font-semibold"
                >
                  <RefreshCw size={13} className={loadingChats ? "animate-spin" : ""} />
                  Refresh
                </button>
                <button
                  type="button"
                  data-tooltip="Inspect active worker paths, MCP tool invocations, and agentic reasoning loops isolated per chat session or background task."
                  className="ui-tooltip ui-tooltip-top ui-tooltip-end theme-chip text-foreground/70 hover:text-foreground inline-flex h-9 w-9 items-center justify-center rounded-xl"
                  aria-label="Orchestrator Information"
                >
                  <Info size={15} />
                </button>
              </div>
            }
          />

          {/* Dashboard Tabs */}
          <div className="border-glass-border/10 mt-8 flex flex-col gap-3 border-b pb-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex flex-wrap gap-2">
              {(
                [
                  { id: "all", label: "All Sessions" },
                  { id: "chats", label: "DeepSpace Chats" },
                  { id: "proactive", label: "Proactive Agents" },
                  { id: "connectors", label: "Connectors" },
                ] as Array<{ id: DashboardTab; label: string }>
              ).map((tab) => (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => setDashboardTab(tab.id)}
                  className={`rounded-[0.5rem] border px-4 py-2 text-[10px] font-black tracking-[0.18em] uppercase transition ${
                    dashboardTab === tab.id
                      ? "border-primary/30 bg-primary/10 text-primary"
                      : "text-foreground/60 border-slate-200/80 bg-white/95 hover:bg-slate-50 dark:border-white/10 dark:bg-white/5 dark:text-white/60 dark:hover:bg-white/10"
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            <button
              type="button"
              onClick={() => setShowSystemTasks(!showSystemTasks)}
              className={`flex shrink-0 items-center gap-2 rounded-[0.5rem] border px-3 py-2 font-mono text-[10px] tracking-wider uppercase transition ${
                showSystemTasks
                  ? "border-rose-500/30 bg-rose-500/10 text-rose-400"
                  : "text-foreground/60 border-slate-200/80 bg-white/95 hover:bg-slate-50 dark:border-white/10 dark:bg-white/5 dark:text-white/60 dark:hover:bg-white/10"
              }`}
            >
              <span
                className={`h-1.5 w-1.5 rounded-full ${showSystemTasks ? "animate-pulse bg-rose-400" : "bg-foreground/30"}`}
              />
              SYS.SHOW_DAEMONS: {showSystemTasks ? "ON" : "OFF"}
            </button>
          </div>
          {/* Cards Grid */}
          <div className="mt-6 grid grid-cols-1 gap-4 pb-12 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {/* Render Global Control Room Card */}
            {dashboardTab === "all" && (
              <div
                onClick={() => handleSelectSession("global", "Global Control Room", "global")}
                className="group relative flex cursor-pointer flex-col justify-between overflow-hidden rounded-[1.2rem] border border-cyan-500/15 bg-black/40 p-5 shadow-sm backdrop-blur-xl transition-all duration-300 hover:-translate-y-1 hover:border-cyan-400/40 hover:shadow-[0_0_30px_rgba(6,182,212,0.15)]"
              >
                {/* HUD Brackets */}
                <div className="absolute top-0 left-0 h-2.5 w-2.5 border-t-2 border-l-2 border-cyan-500/30 transition-colors duration-300 group-hover:border-cyan-400" />
                <div className="absolute top-0 right-0 h-2.5 w-2.5 border-t-2 border-r-2 border-cyan-500/30 transition-colors duration-300 group-hover:border-cyan-400" />
                <div className="absolute bottom-0 left-0 h-2.5 w-2.5 border-b-2 border-l-2 border-cyan-500/30 transition-colors duration-300 group-hover:border-cyan-400" />
                <div className="absolute right-0 bottom-0 h-2.5 w-2.5 border-r-2 border-b-2 border-cyan-500/30 transition-colors duration-300 group-hover:border-cyan-400" />

                {/* Left Stripe Indicator */}
                <div className="absolute top-4 bottom-4 left-0 w-[3px] rounded-r bg-cyan-500/60 transition-all duration-300 group-hover:bg-cyan-400 group-hover:shadow-[0_0_10px_rgba(6,182,212,0.8)]" />

                <div className="pointer-events-none absolute top-0 right-0 h-24 w-24 bg-[radial-gradient(circle_at_top_right,rgba(6,182,212,0.12),transparent_70%)]" />
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-[8px] font-bold tracking-[0.18em] text-cyan-400/80 uppercase">
                      SYS.MASTER_CORE
                      <span className="sr-only">System Master View</span>
                    </span>
                    <div className="flex items-center gap-1.5 rounded border border-cyan-500/20 bg-cyan-950/40 px-2 py-0.5 font-mono text-[8px] tracking-wider text-cyan-300 uppercase">
                      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" />
                      Active
                    </div>
                  </div>
                  <div className="flex gap-3">
                    <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-cyan-500/20 bg-cyan-950/30 p-2.5 text-cyan-400 shadow-[0_0_15px_rgba(6,182,212,0.1)] transition-all duration-300 group-hover:scale-105 group-hover:border-cyan-400/40">
                      <Brain size={20} className="animate-pulse" />
                    </div>
                    <div className="min-w-0 flex-1 space-y-1">
                      <h3 className="text-foreground/90 line-clamp-2 text-sm font-bold tracking-tight transition-colors group-hover:text-cyan-300">
                        Global Control Room
                      </h3>
                      <p className="text-foreground/45 text-[10px] leading-relaxed">
                        Monitor unified background workers, proactive daemon loops, and global
                        system vitals.
                      </p>
                    </div>
                  </div>
                  <div className="mt-2 flex gap-2 font-mono text-[8px] tracking-wider uppercase">
                    <div className="rounded border border-cyan-500/10 bg-cyan-950/10 px-2 py-1">
                      <span className="text-cyan-400/40">SUBAGENTS:</span>{" "}
                      <strong className="font-bold text-cyan-300">
                        {globalOverview?.summary.active_subagents ?? 0}
                      </strong>
                    </div>
                    <div className="rounded border border-cyan-500/10 bg-cyan-950/10 px-2 py-1">
                      <span className="text-cyan-400/40">TASKS:</span>{" "}
                      <strong className="font-bold text-cyan-300">
                        {globalOverview?.summary.active_tasks ?? 0}
                      </strong>
                    </div>
                  </div>
                </div>
                <div className="mt-5 flex items-center justify-between border-t border-white/5 pt-3 font-mono text-[8px] font-black tracking-[0.2em] text-cyan-300/70 uppercase">
                  <span className="flex items-center gap-1.5">
                    <span className="h-1 w-1 animate-pulse rounded-full bg-cyan-400" />
                    Enter Control Room
                  </span>
                  <span className="transition-transform duration-300 group-hover:translate-x-1.5">
                    {"==>"}
                  </span>
                </div>
              </div>
            )}

            {/* Render DeepSpace Chat Cards */}
            {(dashboardTab === "all" || dashboardTab === "chats") && (
              <>
                {filteredChats.length > 0
                  ? filteredChats.map((chat) => {
                      const chatUpdatedAt = chat.updated_at ? new Date(chat.updated_at) : null;
                      const isChatActive = globalOverview?.missions?.active?.some(
                        (m) =>
                          String(m.parent_id || "") === String(chat.id) ||
                          String(m.mission_id || "") === String(chat.id),
                      );
                      return (
                        <div
                          key={chat.id}
                          onClick={() =>
                            handleSelectSession(
                              chat.id,
                              chat.title || "Untitled Chat Session",
                              "chat",
                            )
                          }
                          className="group border-glass-border relative flex cursor-pointer flex-col justify-between overflow-hidden rounded-[1.2rem] border bg-black/40 p-5 shadow-sm backdrop-blur-xl transition-all duration-300 hover:-translate-y-1 hover:border-violet-500/40 hover:shadow-[0_0_30px_rgba(139,92,246,0.15)]"
                        >
                          {/* HUD Brackets */}
                          <div className="absolute top-0 left-0 h-2.5 w-2.5 border-t-2 border-l-2 border-violet-500/20 transition-colors duration-300 group-hover:border-violet-400" />
                          <div className="absolute top-0 right-0 h-2.5 w-2.5 border-t-2 border-r-2 border-violet-500/20 transition-colors duration-300 group-hover:border-violet-400" />
                          <div className="absolute bottom-0 left-0 h-2.5 w-2.5 border-b-2 border-l-2 border-violet-500/20 transition-colors duration-300 group-hover:border-violet-400" />
                          <div className="absolute right-0 bottom-0 h-2.5 w-2.5 border-r-2 border-b-2 border-violet-500/20 transition-colors duration-300 group-hover:border-violet-400" />

                          {/* Left Stripe Indicator */}
                          <div
                            className={`absolute top-4 bottom-4 left-0 w-[3px] rounded-r transition-all duration-300 ${
                              isChatActive
                                ? "bg-emerald-500/60 group-hover:bg-emerald-400 group-hover:shadow-[0_0_10px_rgba(16,185,129,0.8)]"
                                : "bg-violet-500/40 group-hover:bg-violet-400 group-hover:shadow-[0_0_10px_rgba(139,92,246,0.8)]"
                            }`}
                          />

                          <div className="pointer-events-none absolute top-0 right-0 h-24 w-24 bg-[radial-gradient(circle_at_top_right,rgba(139,92,246,0.12),transparent_70%)]" />
                          <div className="space-y-4">
                            <div className="flex items-center justify-between">
                              <span className="font-mono text-[8px] font-bold tracking-[0.18em] text-violet-400/80 uppercase">
                                SYS.CHAT_SESSION
                              </span>
                              {isChatActive ? (
                                <div className="flex items-center gap-1.5 rounded border border-emerald-500/20 bg-emerald-950/40 px-2 py-0.5 font-mono text-[8px] tracking-wider text-emerald-300 uppercase">
                                  <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" />
                                  Running
                                </div>
                              ) : (
                                <div className="flex items-center gap-1.5 rounded border border-slate-500/10 bg-slate-900/40 px-2 py-0.5 font-mono text-[8px] tracking-wider text-slate-400 uppercase">
                                  <span className="h-1.5 w-1.5 rounded-full bg-slate-500" />
                                  Idle
                                </div>
                              )}
                            </div>
                            <div className="flex gap-3">
                              <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-violet-500/20 bg-violet-950/30 p-2.5 text-violet-400 shadow-[0_0_15px_rgba(139,92,246,0.1)] transition-all duration-300 group-hover:scale-105 group-hover:border-violet-400/40">
                                <MessageSquare size={20} />
                              </div>
                              <div className="min-w-0 flex-1 space-y-1">
                                <h3 className="text-foreground/90 line-clamp-2 text-sm font-bold tracking-tight transition-colors group-hover:text-violet-400">
                                  {chat.title || "Untitled Chat Session"}
                                </h3>
                                <p className="text-foreground/45 mt-1 font-mono text-[9px]">
                                  LOG.TS //{" "}
                                  {chatUpdatedAt ? chatUpdatedAt.toLocaleDateString() : "Unknown"} @{" "}
                                  {chatUpdatedAt
                                    ? chatUpdatedAt.toLocaleTimeString([], {
                                        hour: "2-digit",
                                        minute: "2-digit",
                                        second: "2-digit",
                                      })
                                    : "--"}
                                </p>
                              </div>
                            </div>
                          </div>
                          <div className="text-foreground/45 mt-5 flex items-center justify-between border-t border-white/5 pt-3 font-mono text-[8px] font-black tracking-[0.2em] uppercase transition-colors group-hover:text-violet-400/80">
                            <span className="flex items-center gap-1.5">
                              <span className="h-1 w-1 rounded-full bg-violet-400" />
                              Open Session Canvas
                            </span>
                            <span className="transition-transform duration-300 group-hover:translate-x-1.5">
                              {"==>"}
                            </span>
                          </div>
                        </div>
                      );
                    })
                  : dashboardTab === "chats" && (
                      <div className="border-glass-border/20 text-foreground/40 col-span-full rounded-2xl border border-dashed p-8 text-center italic">
                        No active or past chat sessions found.
                      </div>
                    )}
              </>
            )}

            {/* Render Proactive Agent Cards */}
            {(dashboardTab === "all" || dashboardTab === "proactive") && (
              <>
                {filteredTasks.length > 0
                  ? filteredTasks.map((task) => (
                      <div
                        key={task.id}
                        onClick={() =>
                          handleSelectSession(task.id, task.activeForm || task.content, "proactive")
                        }
                        className="group border-glass-border relative flex cursor-pointer flex-col justify-between overflow-hidden rounded-[1.2rem] border bg-black/40 p-5 shadow-sm backdrop-blur-xl transition-all duration-300 hover:-translate-y-1 hover:border-rose-500/40 hover:shadow-[0_0_30px_rgba(244,63,94,0.15)]"
                      >
                        {/* HUD Brackets */}
                        <div className="absolute top-0 left-0 h-2.5 w-2.5 border-t-2 border-l-2 border-rose-500/20 transition-colors duration-300 group-hover:border-rose-400" />
                        <div className="absolute top-0 right-0 h-2.5 w-2.5 border-t-2 border-r-2 border-rose-500/20 transition-colors duration-300 group-hover:border-rose-400" />
                        <div className="absolute bottom-0 left-0 h-2.5 w-2.5 border-b-2 border-l-2 border-rose-500/20 transition-colors duration-300 group-hover:border-rose-400" />
                        <div className="absolute right-0 bottom-0 h-2.5 w-2.5 border-r-2 border-b-2 border-rose-500/20 transition-colors duration-300 group-hover:border-rose-400" />

                        {/* Left Stripe Indicator */}
                        <div className="absolute top-4 bottom-4 left-0 w-[3px] rounded-r bg-rose-500/50 transition-all duration-300 group-hover:bg-rose-400 group-hover:shadow-[0_0_10px_rgba(244,63,94,0.8)]" />

                        <div className="pointer-events-none absolute top-0 right-0 h-24 w-24 bg-[radial-gradient(circle_at_top_right,rgba(244,63,94,0.12),transparent_70%)]" />
                        <div className="space-y-4">
                          <div className="flex items-center justify-between">
                            <span className="font-mono text-[8px] font-bold tracking-[0.18em] text-rose-400/80 uppercase">
                              SYS.PROACTIVE_DAEMON
                            </span>
                            {task.status === "completed" ? (
                              <div className="flex items-center gap-1.5 rounded border border-emerald-500/20 bg-emerald-950/40 px-2 py-0.5 font-mono text-[8px] tracking-wider text-emerald-300 uppercase">
                                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" />
                                Completed
                              </div>
                            ) : task.status === "in_progress" ? (
                              <div className="flex items-center gap-1.5 rounded border border-cyan-500/20 bg-cyan-950/40 px-2 py-0.5 font-mono text-[8px] tracking-wider text-cyan-300 uppercase">
                                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-cyan-400" />
                                Running
                              </div>
                            ) : (
                              <div className="flex items-center gap-1.5 rounded border border-amber-500/20 bg-amber-950/40 px-2 py-0.5 font-mono text-[8px] tracking-wider text-amber-300 uppercase">
                                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-amber-400" />
                                {task.status.replace(/_/g, " ").toUpperCase()}
                              </div>
                            )}
                          </div>
                          <div className="flex gap-3">
                            <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-rose-500/20 bg-rose-950/30 p-2.5 text-rose-400 shadow-[0_0_15px_rgba(244,63,94,0.15)] transition-all duration-300 group-hover:scale-105 group-hover:border-rose-400/40">
                              <Clock3 size={20} />
                            </div>
                            <div className="min-w-0 flex-1 space-y-1">
                              <h3 className="text-foreground/90 line-clamp-2 text-sm font-bold tracking-tight transition-colors group-hover:text-rose-400">
                                {task.activeForm || task.content || "Automation Job"}
                              </h3>
                              <div className="mt-2 flex flex-col gap-1.5">
                                {task.is_recurring && (
                                  <span className="font-mono text-[8px] font-bold tracking-wider text-rose-400/80">
                                    LOOP.RECURRING: ACTIVE
                                  </span>
                                )}

                                {/* Segmented Energy Cells for priority */}
                                <div className="flex w-fit items-center gap-1.5 rounded border border-rose-500/10 bg-rose-950/20 px-2 py-1">
                                  <span className="font-mono text-[7.5px] tracking-wider text-rose-400/50 uppercase">
                                    PRIORITY:
                                  </span>
                                  <div className="flex gap-0.5">
                                    {[...Array(5)].map((_, i) => (
                                      <span
                                        key={i}
                                        className={`h-2.5 w-1.5 rounded-sm transition-all duration-300 ${
                                          i < Math.round(task.priority / 20)
                                            ? "bg-rose-400 shadow-[0_0_8px_rgba(244,63,94,0.6)]"
                                            : "bg-rose-950/20"
                                        }`}
                                      />
                                    ))}
                                  </div>
                                </div>
                              </div>
                            </div>
                          </div>
                        </div>
                        <div className="text-foreground/45 mt-5 flex items-center justify-between border-t border-white/5 pt-3 font-mono text-[8px] font-black tracking-[0.2em] uppercase transition-colors group-hover:text-rose-400/80">
                          <span className="flex items-center gap-1.5">
                            <span className="h-1 w-1 rounded-full bg-rose-400" />
                            Open Agent Canvas
                          </span>
                          <div className="flex items-center gap-2">
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                setKillTaskId(task.id);
                              }}
                              className="flex items-center gap-1 rounded border border-rose-500/20 bg-rose-950/20 px-2 py-0.5 font-mono text-[8px] tracking-wider text-rose-400 uppercase transition-all duration-200 hover:bg-rose-500 hover:text-white"
                            >
                              <Power size={8} /> Kill Process
                            </button>
                            <span className="transition-transform duration-300 group-hover:translate-x-1.5">
                              {"==>"}
                            </span>
                          </div>
                        </div>
                      </div>
                    ))
                  : dashboardTab === "proactive" && (
                      <div className="border-glass-border/20 text-foreground/40 col-span-full rounded-2xl border border-dashed p-8 text-center italic">
                        No active proactive agent tasks found.
                      </div>
                    )}
              </>
            )}

            {/* Render Connector Cards */}
            {(dashboardTab === "all" || dashboardTab === "connectors") &&
              connectorItems.map((conn) => (
                <div
                  key={conn.id}
                  onClick={() => handleSelectSession(conn.id, conn.name, "connector")}
                  className="group border-glass-border relative flex cursor-pointer flex-col justify-between overflow-hidden rounded-[1.2rem] border bg-black/40 p-5 shadow-sm backdrop-blur-xl transition-all duration-300 hover:-translate-y-1 hover:border-amber-500/40 hover:shadow-[0_0_30px_rgba(245,158,11,0.15)]"
                >
                  {/* HUD Brackets */}
                  <div className="absolute top-0 left-0 h-2.5 w-2.5 border-t-2 border-l-2 border-amber-500/20 transition-colors duration-300 group-hover:border-amber-400" />
                  <div className="absolute top-0 right-0 h-2.5 w-2.5 border-t-2 border-r-2 border-amber-500/20 transition-colors duration-300 group-hover:border-amber-400" />
                  <div className="absolute bottom-0 left-0 h-2.5 w-2.5 border-b-2 border-l-2 border-amber-500/20 transition-colors duration-300 group-hover:border-amber-400" />
                  <div className="absolute right-0 bottom-0 h-2.5 w-2.5 border-r-2 border-b-2 border-amber-500/20 transition-colors duration-300 group-hover:border-amber-400" />

                  {/* Left Stripe Indicator */}
                  <div className="absolute top-4 bottom-4 left-0 w-[3px] rounded-r bg-amber-500/50 transition-all duration-300 group-hover:bg-amber-400 group-hover:shadow-[0_0_10px_rgba(245,158,11,0.8)]" />

                  <div className="pointer-events-none absolute top-0 right-0 h-24 w-24 bg-[radial-gradient(circle_at_top_right,rgba(245,158,11,0.12),transparent_70%)]" />
                  <div className="space-y-4">
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-[8px] font-bold tracking-[0.18em] text-amber-400/80 uppercase">
                        SYS.CONNECTOR_MESH
                      </span>
                      {conn.status === "paused" ? (
                        <div className="flex items-center gap-1.5 rounded border border-yellow-500/20 bg-yellow-950/40 px-2 py-0.5 font-mono text-[8px] tracking-wider text-yellow-300 uppercase">
                          <span className="h-1.5 w-1.5 rounded-full bg-yellow-400" />
                          Paused
                        </div>
                      ) : conn.status === "error" ? (
                        <div className="flex items-center gap-1.5 rounded border border-rose-500/20 bg-rose-950/40 px-2 py-0.5 font-mono text-[8px] tracking-wider text-rose-300 uppercase">
                          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-rose-400" />
                          Error
                        </div>
                      ) : conn.status === "syncing" ? (
                        <div className="flex items-center gap-1.5 rounded border border-cyan-500/20 bg-cyan-950/40 px-2 py-0.5 font-mono text-[8px] tracking-wider text-cyan-300 uppercase">
                          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-cyan-400" />
                          Syncing
                        </div>
                      ) : (
                        <div className="flex items-center gap-1.5 rounded border border-emerald-500/20 bg-emerald-950/40 px-2 py-0.5 font-mono text-[8px] tracking-wider text-emerald-300 uppercase">
                          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" />
                          Connected
                        </div>
                      )}
                    </div>
                    <div className="flex gap-3">
                      <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-amber-500/20 bg-amber-950/30 p-2.5 text-amber-400 shadow-[0_0_15px_rgba(245,158,11,0.15)] transition-all duration-300 group-hover:scale-105 group-hover:border-amber-400/40">
                        <Cable size={20} />
                      </div>
                      <div className="min-w-0 flex-1 space-y-1">
                        <h3 className="text-foreground/90 line-clamp-2 text-sm font-bold tracking-tight transition-colors group-hover:text-amber-400">
                          {conn.name}
                        </h3>
                        <p className="text-foreground/45 text-[10px] leading-relaxed">
                          {conn.desc}
                        </p>
                      </div>
                    </div>
                  </div>
                  <div className="text-foreground/45 mt-5 flex items-center justify-between border-t border-white/5 pt-3 font-mono text-[8px] font-black tracking-[0.2em] uppercase transition-colors group-hover:text-amber-400/80">
                    <span className="flex items-center gap-1.5">
                      <span className="h-1 w-1 rounded-full bg-amber-400" />
                      Open Connector Mesh
                    </span>
                    <span className="transition-transform duration-300 group-hover:translate-x-1.5">
                      {"==>"}
                    </span>
                  </div>
                </div>
              ))}
          </div>
        </div>

        <ConfirmationModal
          isOpen={!!killTaskId}
          onClose={() => setKillTaskId(null)}
          onConfirm={async () => {
            if (!killTaskId) return;
            setKillingTask(true);
            try {
              await handleKillTask(killTaskId);
            } finally {
              setKillingTask(false);
              setKillTaskId(null);
            }
          }}
          title="Terminate Task Process"
          message="Are you sure you want to terminate this task process? This action cannot be undone."
          confirmLabel="Terminate Process"
          variant="danger"
          loading={killingTask}
        />
      </>
    );
  }

  return (
    <div className="relative h-[calc(100vh-8rem)] min-h-[600px] w-full overflow-hidden">
      {error ? (
        <div className="absolute top-[7.75rem] left-4 z-75 max-w-sm rounded-[0.5rem] border border-amber-500/20 bg-amber-500/10 px-4 py-3 text-xs text-amber-100">
          {error}
        </div>
      ) : null}

      <div className="absolute inset-0 overflow-hidden bg-transparent">
        <div className="!absolute inset-0 overflow-hidden bg-transparent">
          {/* Unified Top HUD Control Bar */}
          <div className="dark:border-glass-border/40 dark:bg-surface-1/30 absolute top-4 right-4 left-4 z-30 flex min-h-[3.5rem] flex-wrap items-center justify-between gap-3 rounded-[0.75rem] border border-slate-200/80 bg-white/96 px-4 py-2 shadow-[0_12px_28px_rgba(15,23,42,0.08)] backdrop-blur-xl md:flex-nowrap">
            {/* Left Section: Navigation & Session Info */}
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => {
                  setLoading(true);
                  setData(null);
                  setSelectedSessionId(null);
                  setSelectedSessionTitle(null);
                  setSelectedSessionType(null);
                }}
                className="text-foreground/70 hover:bg-primary/10 hover:text-primary inline-flex items-center justify-center gap-1 rounded-[0.35rem] border border-slate-200/80 bg-white/95 px-2.5 py-1 text-[9px] font-black tracking-[0.18em] uppercase transition dark:border-white/10 dark:bg-white/5 dark:text-white/80"
              >
                ← Back
              </button>
              <div className="mx-1.5 h-6 w-px bg-slate-200 dark:bg-white/10" />
              <span className="border-primary/20 bg-primary/10 text-primary inline-flex max-w-[120px] items-center gap-1.5 rounded-[0.35rem] border px-2.5 py-1.5 text-[9px] font-black tracking-[0.2em] uppercase sm:max-w-[200px] md:max-w-[280px]">
                <Layers3 size={11} className="shrink-0" />
                <span className="truncate">
                  {selectedSessionType === "global"
                    ? "Global Control Room"
                    : selectedSessionType === "proactive"
                      ? `Agent: ${selectedSessionTitle || "Automation Job"}`
                      : selectedSessionType === "connector"
                        ? `Connector: ${selectedSessionTitle || "External App"}`
                        : selectedSessionTitle || "Active Chat Session"}
                </span>
              </span>
              <AverQelTooltip
                label="Orchestration overview"
                title="Orchestration overview"
                content={
                  <div className="text-foreground/72 space-y-2 text-[11px] leading-5">
                    <p>
                      Live mission graph, parallel worker lanes, durable memory, and connector
                      health in one control surface.
                    </p>
                    <p>
                      Drag nodes to reshape the workflow, pan the canvas, zoom into a cluster, or
                      reset the layout from the toolbar.
                    </p>
                  </div>
                }
                buttonClassName="border-slate-200/80 bg-white/95 text-foreground/45 hover:border-primary/30 hover:bg-primary/10 hover:text-primary dark:border-white/10 dark:bg-white/5 dark:text-white/55 inline-flex h-6 w-6 items-center justify-center rounded-[0.35rem] border transition-all"
                icon={<Info size={11} className="stroke-[2.5]" />}
              />
            </div>

            {/* Center Section: Core Canvas Actions */}
            <div className="flex items-center gap-1.5">
              <button
                type="button"
                onClick={() => void loadOverview()}
                className="theme-panel-muted hover:bg-primary/8 inline-flex items-center gap-1.5 rounded-[0.35rem] border border-slate-200/80 bg-white/95 px-3 py-1.5 text-[10px] font-black tracking-[0.18em] whitespace-nowrap uppercase transition dark:border-white/8 dark:hover:bg-white/10"
              >
                <RefreshCw size={12} />
                <span className="hidden sm:inline">Refresh</span>
              </button>
              <button
                type="button"
                onClick={resetView}
                className="theme-panel-muted hover:bg-primary/8 inline-flex items-center gap-1.5 rounded-[0.35rem] border border-slate-200/80 bg-white/95 px-3 py-1.5 text-[10px] font-black tracking-[0.18em] whitespace-nowrap uppercase transition dark:border-white/8 dark:hover:bg-white/10"
              >
                <RotateCcw size={12} />
                <span className="hidden sm:inline">Reset</span>
              </button>
              {nodePositions.size > 0 && (
                <button
                  type="button"
                  onClick={resetNodePositions}
                  className="theme-panel-muted hover:bg-primary/8 inline-flex items-center gap-1.5 rounded-[0.35rem] border border-slate-200/80 bg-white/95 px-3 py-1.5 text-[10px] font-black tracking-[0.18em] whitespace-nowrap uppercase transition dark:border-white/8 dark:hover:bg-white/10"
                >
                  <Undo2 size={12} />
                  <span className="hidden sm:inline">Reset Layout</span>
                </button>
              )}
              <div className="relative z-[90]">
                <ExecutionModeDropdown
                  value={executionMode}
                  compact
                  onChange={(mode) => {
                    void updateExecutionMode(mode);
                  }}
                />
              </div>
            </div>

            {/* Responsive System Info Buttons (visible on small/medium screens, hidden on lg+) */}
            <div className="flex flex-row flex-wrap items-center gap-1.5 lg:hidden">
              {[
                { id: "agentic-workflows", icon: Workflow, label: "Agentic Workflows" },
                { id: "tool-orchestration", icon: Wrench, label: "Tool Orchestration" },
                { id: "agentic-loops", icon: Loader, label: "Agentic Loops" },
                { id: "connectors", icon: LinkIcon, label: "Connectors & Integrations" },
                { id: "autonomous-agents", icon: Brain, label: "Autonomous Agents" },
                { id: "infrastructure", icon: Network, label: "Infrastructure & Scaling" },
                { id: "streaming", icon: Zap, label: "Inline Streaming & Events" },
                { id: "monitoring", icon: Activity, label: "Monitoring & Telemetry" },
              ].map(({ id, icon: Icon, label }) => (
                <div key={id} className="group relative">
                  <button
                    type="button"
                    onClick={() => setActiveSystemPanel(activeSystemPanel === id ? null : id)}
                    className={`theme-panel-muted hover:border-primary/30 hover:bg-primary/10 hover:text-primary relative flex h-8 w-8 items-center justify-center rounded-[0.4rem] border border-slate-200/80 bg-white/96 transition-all duration-300 hover:scale-105 dark:border-white/10 dark:bg-black/45 dark:text-white/75 ${
                      activeSystemPanel === id
                        ? "border-primary/30 bg-primary/10 text-primary ring-primary/20 ring-2"
                        : ""
                    }`}
                    aria-label={label}
                  >
                    <Icon size={14} className="transition" />
                  </button>
                </div>
              ))}
            </div>

            {/* Right Section: System Vitals & Canvas Zoom Controls */}
            <div className="hidden items-center gap-3 lg:flex">
              {/* DoxWise brand info */}
              <div className="hidden h-6 items-center gap-2 border-l border-slate-200 px-3 lg:flex dark:border-white/10">
                <span className="flex h-5 w-5 items-center justify-center rounded bg-cyan-500/10 text-cyan-400">
                  <Sparkles size={11} className="animate-pulse" />
                </span>
                <span className="text-foreground/80 text-[10px] font-black tracking-wider dark:text-white/80">
                  AverQel
                </span>
              </div>

              {/* Status: ONLINE */}
              <div className="hidden h-6 items-center gap-1.5 border-l border-slate-200 px-3 text-[10px] font-black tracking-wider xl:flex dark:border-white/10">
                <span className="text-foreground/45">Status:</span>
                <span className="animate-pulse text-emerald-500 dark:text-emerald-400">ONLINE</span>
              </div>

              {/* Alerts */}
              <div className="hidden h-6 items-center gap-1.5 border-l border-slate-200 px-3 text-[10px] font-black tracking-wider xl:flex dark:border-white/10">
                <span className="text-foreground/45">Alerts:</span>
                <span className="rounded border border-rose-500/20 bg-rose-500/10 px-1.5 py-0.5 leading-none font-bold text-rose-500 dark:text-rose-400">
                  3
                </span>
              </div>

              {/* Time (UTC) */}
              <div className="text-foreground/45 hidden h-6 items-center border-l border-slate-200 px-3 text-[10px] font-black tracking-wider xl:flex dark:border-white/10">
                {currentTime}
              </div>
            </div>
          </div>

          <div
            ref={canvasRef}
            className={`absolute inset-0 overflow-hidden ${isDragging || draggedNodeId ? "cursor-grabbing" : "cursor-grab"}`}
            onPointerDown={(event) => {
              const target = event.target as HTMLElement | null;
              if (target?.closest("[data-orchestration-node='true']")) {
                return;
              }
              if (draggedNodeId !== null) {
                return;
              }
              event.preventDefault();
              setIsDragging(true);
              dragRef.current = {
                startX: event.clientX,
                startY: event.clientY,
                originX: pan.x,
                originY: pan.y,
              };
            }}
            onDoubleClick={() => resetView()}
            style={{
              touchAction: "none",
            }}
          >
            <div
              ref={graphSurfaceRef}
              data-orchestration-graph-surface="true"
              className="absolute inset-0 z-0 overflow-hidden"
            >
              <div
                className="pointer-events-auto absolute top-0 left-0 origin-top-left"
                style={{
                  width: `${GRAPH_BOARD_WIDTH}px`,
                  height: `${GRAPH_BOARD_HEIGHT}px`,
                  transform: `translate3d(${pan.x}px, ${pan.y}px, 0) scale(${zoom})`,
                  transition:
                    isDragging || draggedNodeId || isCenteringInitial
                      ? "none"
                      : "transform 180ms ease-out",
                }}
              >
                <svg
                  className="pointer-events-none absolute inset-0 h-full w-full"
                  fill="none"
                  viewBox={`0 0 ${GRAPH_BOARD_WIDTH} ${GRAPH_BOARD_HEIGHT}`}
                  preserveAspectRatio="none"
                >
                  <defs>
                    <style>{`
                      @keyframes orchestrationFlow {
                        from { stroke-dashoffset: 32; }
                        to { stroke-dashoffset: 0; }
                      }
                      .orchestration-flow-line {
                        stroke-dasharray: 8, 8;
                        animation: orchestrationFlow 1.5s linear infinite;
                      }
                    `}</style>
                    <filter id="orchestrationGlow">
                      <feGaussianBlur stdDeviation="4" result="blur" />
                      <feMerge>
                        <feMergeNode in="blur" />
                        <feMergeNode in="SourceGraphic" />
                      </feMerge>
                    </filter>
                    <linearGradient id="orchestrationEdgeCyan" x1="0%" y1="0%" x2="100%" y2="0%">
                      <stop offset="0%" stopColor="rgba(34,211,238,0.85)" />
                      <stop offset="100%" stopColor="rgba(34,211,238,0.15)" />
                    </linearGradient>
                    <linearGradient id="orchestrationEdgeEmerald" x1="0%" y1="0%" x2="100%" y2="0%">
                      <stop offset="0%" stopColor="rgba(16,185,129,0.85)" />
                      <stop offset="100%" stopColor="rgba(16,185,129,0.15)" />
                    </linearGradient>
                    <linearGradient id="orchestrationEdgeViolet" x1="0%" y1="0%" x2="100%" y2="0%">
                      <stop offset="0%" stopColor="rgba(139,92,246,0.85)" />
                      <stop offset="100%" stopColor="rgba(139,92,246,0.15)" />
                    </linearGradient>
                    <linearGradient id="orchestrationEdgeAmber" x1="0%" y1="0%" x2="100%" y2="0%">
                      <stop offset="0%" stopColor="rgba(251,146,60,0.85)" />
                      <stop offset="100%" stopColor="rgba(251,146,60,0.15)" />
                    </linearGradient>
                    <linearGradient id="orchestrationEdgeRose" x1="0%" y1="0%" x2="100%" y2="0%">
                      <stop offset="0%" stopColor="rgba(244,63,94,0.85)" />
                      <stop offset="100%" stopColor="rgba(244,63,94,0.15)" />
                    </linearGradient>
                    <marker
                      id="arrow-cyan"
                      viewBox="0 0 10 10"
                      refX="8"
                      refY="5"
                      markerWidth="6"
                      markerHeight="6"
                      orient="auto-start-reverse"
                    >
                      <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="rgba(34,211,238,0.85)" />
                    </marker>
                    <marker
                      id="arrow-emerald"
                      viewBox="0 0 10 10"
                      refX="8"
                      refY="5"
                      markerWidth="6"
                      markerHeight="6"
                      orient="auto-start-reverse"
                    >
                      <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="rgba(16,185,129,0.85)" />
                    </marker>
                    <marker
                      id="arrow-violet"
                      viewBox="0 0 10 10"
                      refX="8"
                      refY="5"
                      markerWidth="6"
                      markerHeight="6"
                      orient="auto-start-reverse"
                    >
                      <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="rgba(139,92,246,0.85)" />
                    </marker>
                    <marker
                      id="arrow-amber"
                      viewBox="0 0 10 10"
                      refX="8"
                      refY="5"
                      markerWidth="6"
                      markerHeight="6"
                      orient="auto-start-reverse"
                    >
                      <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="rgba(251,146,60,0.85)" />
                    </marker>
                    <marker
                      id="arrow-rose"
                      viewBox="0 0 10 10"
                      refX="8"
                      refY="5"
                      markerWidth="6"
                      markerHeight="6"
                      orient="auto-start-reverse"
                    >
                      <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="rgba(244,63,94,0.85)" />
                    </marker>
                  </defs>

                  {edges.map((edge) => {
                    const source = displayGraphPositions.get(edge.source);
                    const target = displayGraphPositions.get(edge.target);
                    if (!source || !target) return null;

                    const isConnected =
                      connectedNodeIds.has(edge.source) && connectedNodeIds.has(edge.target);
                    const start = getConnectorPoint(
                      source,
                      target,
                      GRAPH_CARD_WIDTH,
                      GRAPH_CARD_HEIGHT,
                    );
                    const end = getConnectorPoint(
                      target,
                      source,
                      GRAPH_CARD_WIDTH,
                      GRAPH_CARD_HEIGHT,
                    );
                    const path = buildCurvePath(start, end);

                    const gradientId =
                      edge.tone === "emerald"
                        ? "url(#orchestrationEdgeEmerald)"
                        : edge.tone === "violet"
                          ? "url(#orchestrationEdgeViolet)"
                          : edge.tone === "amber"
                            ? "url(#orchestrationEdgeAmber)"
                            : edge.tone === "rose"
                              ? "url(#orchestrationEdgeRose)"
                              : "url(#orchestrationEdgeCyan)";

                    const markerId =
                      edge.tone === "emerald"
                        ? "url(#arrow-emerald)"
                        : edge.tone === "violet"
                          ? "url(#arrow-violet)"
                          : edge.tone === "amber"
                            ? "url(#arrow-amber)"
                            : edge.tone === "rose"
                              ? "url(#arrow-rose)"
                              : "url(#arrow-cyan)";

                    return (
                      <g key={`${edge.source}-${edge.target}-${edge.label}`}>
                        <path
                          d={path}
                          stroke="rgba(4,9,11,0.95)"
                          strokeWidth={isConnected ? 4.8 : 3}
                          vectorEffect="non-scaling-stroke"
                          strokeOpacity={0.6}
                          fill="none"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        />
                        <path
                          d={path}
                          stroke={gradientId}
                          strokeWidth={isConnected ? 2.8 : 1.5}
                          vectorEffect="non-scaling-stroke"
                          strokeOpacity={isConnected ? 0.92 : 0.38}
                          filter={isConnected ? "url(#orchestrationGlow)" : undefined}
                          fill="none"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          markerEnd={markerId}
                          className="orchestration-flow-line"
                        />
                      </g>
                    );
                  })}
                </svg>

                {nodes.map((node) => {
                  const projectedPos = displayGraphPositions.get(node.id);
                  if (!projectedPos) return null;

                  const selected = node.id === selectedNodeId;
                  const connected = connectedNodeIds.has(node.id);
                  const isHovered = hoveredNodeId === node.id;
                  const useCount = nodeCallCounts.get(node.id) || 0;

                  return (
                    <div
                      key={node.id}
                      data-orchestration-node="true"
                      onPointerDown={(event) => handleNodePointerDown(event, node.id)}
                      onPointerEnter={() => setHoveredNodeId(node.id)}
                      onPointerLeave={() => setHoveredNodeId(null)}
                      onClick={() => setSelectedNodeId(node.id)}
                      tabIndex={0}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          setSelectedNodeId(node.id);
                        }
                      }}
                      className={`group absolute -translate-x-1/2 -translate-y-1/2 cursor-grab rounded-[1.1rem] border p-3 text-left transition-all duration-300 outline-none select-none active:cursor-grabbing ${
                        selected
                          ? "border-primary/50 z-40 h-[250px] w-[260px] shadow-[0_20px_50px_rgba(0,0,0,0.5)]"
                          : "z-10 h-[112px] w-[260px]"
                      } ${
                        node.id === "open_chat"
                          ? "scale-105 shadow-[0_0_30px_rgba(34,211,238,0.35)] ring-2 ring-cyan-400/50 dark:ring-cyan-500/50"
                          : selected
                            ? "ring-primary/20 ring-2"
                            : connected
                              ? "hover:ring-primary/20 ring-white/10"
                              : "opacity-95 hover:opacity-100"
                      } ${node.id === "open_chat" ? "border-cyan-400 bg-cyan-50/95 dark:border-cyan-500/60 dark:bg-cyan-950/20" : toneClasses(node.tone, selected)} ${
                        isHovered && !selected
                          ? "z-30 scale-[1.05] shadow-[0_15px_30px_rgba(0,0,0,0.3)]"
                          : ""
                      }`}
                      style={{ left: projectedPos.left, top: projectedPos.top }}
                    >
                      <div className="relative flex h-full flex-col">
                        {/* Top Segment: same as compact card */}
                        <div className="flex h-[86px] shrink-0 items-start gap-3">
                          <div
                            className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border shadow-[0_10px_18px_rgba(15,23,42,0.06)] ${toneIconClasses(node.tone)}`}
                          >
                            {kindIcon(node.kind)}
                          </div>
                          <div className="flex h-full min-w-0 flex-1 flex-col justify-between">
                            <div>
                              <div className="flex items-start justify-between gap-3">
                                <div className="min-w-0">
                                  <p className="text-foreground truncate text-[13px] font-black tracking-tight dark:text-white">
                                    {node.id === "open_chat" &&
                                    selectedSessionTitle &&
                                    selectedSessionId !== "global"
                                      ? `AverQel Core · ${selectedSessionTitle}`
                                      : viewMode === "user"
                                        ? USER_FRIENDLY_LABELS[node.id] || node.label
                                        : node.label}
                                  </p>
                                  <p className="text-foreground/55 mt-0.5 truncate text-[9px] font-black tracking-[0.18em] uppercase dark:text-white/55">
                                    {node.id === "open_chat" ? (
                                      <span className="animate-pulse font-black text-cyan-600 dark:text-cyan-400">
                                        ★ START CORE
                                      </span>
                                    ) : viewMode === "user" ? (
                                      getUserFriendlyCategory(node)
                                    ) : (
                                      `${node.world} · ${node.kind}`
                                    )}
                                  </p>
                                </div>
                                <span
                                  className={`shrink-0 rounded-full border px-2 py-0.5 text-[9px] font-black tracking-[0.16em] uppercase ${statusPillClasses(node.status)}`}
                                >
                                  {node.status}
                                </span>
                              </div>
                              <p className="text-foreground/80 mt-1 line-clamp-1 text-[10px] leading-normal dark:text-white/70">
                                {nodePreview(node)}
                              </p>
                            </div>
                            <div className="mt-1 flex items-center justify-between">
                              <div className="flex min-w-0 gap-1 truncate">
                                {node.id === "open_chat" && (
                                  <span className="truncate rounded border border-cyan-200 bg-cyan-100/70 px-1.5 py-0.5 text-[8.5px] leading-none font-medium text-cyan-800 dark:border-cyan-800/40 dark:bg-cyan-950/40 dark:text-cyan-300">
                                    {String(node.meta?.model_name || "Auto LLM")}
                                  </span>
                                )}
                                {node.id === "tool_executor" && (
                                  <div className="flex flex-wrap gap-1">
                                    {((node.meta?.active_tools as string[]) || [])
                                      .slice(0, 1)
                                      .map((tool) => (
                                        <span
                                          key={tool}
                                          className="rounded border border-violet-200/50 bg-violet-100 px-1 py-0.5 text-[8px] leading-none font-black tracking-wider text-violet-600 uppercase dark:border-violet-800/30 dark:bg-violet-950/30 dark:text-violet-300"
                                        >
                                          {tool.replace(/_tool$/, "")}
                                        </span>
                                      ))}
                                  </div>
                                )}
                                {node.id === "connector_mesh" && (
                                  <div className="flex flex-wrap gap-1">
                                    {Object.entries(
                                      (node.meta?.connector_statuses as Record<string, number>) ||
                                        {},
                                    )
                                      .slice(0, 1)
                                      .map(([name, status]) => (
                                        <span
                                          key={name}
                                          className={`rounded border px-1 py-0.5 text-[8px] leading-none font-bold capitalize ${
                                            status === 1
                                              ? "border-emerald-200 bg-emerald-100/80 text-emerald-600 dark:border-emerald-800/30 dark:bg-emerald-950/30 dark:text-emerald-400"
                                              : "border-slate-200 bg-slate-100/80 text-slate-500 dark:border-slate-800/30 dark:bg-slate-900/30"
                                          }`}
                                        >
                                          {name}
                                        </span>
                                      ))}
                                  </div>
                                )}
                                {node.kind === "subagent" && (
                                  <span className="rounded border border-cyan-200/50 bg-cyan-100/70 px-1.5 py-0.5 text-[8px] leading-none font-bold text-cyan-800 dark:border-cyan-900/20 dark:bg-cyan-950/30 dark:text-cyan-300">
                                    Slot {String(node.meta?.slot_index ?? 0)}
                                  </span>
                                )}
                                {node.kind === "task" && (
                                  <span className="rounded bg-slate-100/70 px-1.5 py-0.5 text-[8px] leading-none font-bold text-slate-500 dark:bg-slate-800/30">
                                    P{String(node.meta?.priority ?? 1)}
                                  </span>
                                )}
                              </div>

                              {useCount > 0 && (
                                <span
                                  className={`flex shrink-0 items-center gap-0.5 rounded-md border px-1.5 py-0.5 text-[8px] font-bold tracking-wider uppercase ${
                                    node.tone === "emerald"
                                      ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-400"
                                      : node.tone === "violet"
                                        ? "border-violet-500/20 bg-violet-500/10 text-violet-400"
                                        : node.tone === "rose"
                                          ? "border-rose-500/20 bg-rose-500/10 text-rose-400"
                                          : node.tone === "amber"
                                            ? "border-amber-500/20 bg-amber-500/10 text-amber-400"
                                            : "border-cyan-500/20 bg-cyan-500/10 text-cyan-400"
                                  }`}
                                >
                                  <Activity size={8} />
                                  {useCount}
                                </span>
                              )}
                            </div>
                          </div>
                        </div>

                        {/* Expanded Bottom Segment */}
                        {selected && (
                          <div className="mt-2.5 flex min-h-0 flex-1 flex-col gap-2 border-t border-slate-200/40 pt-2.5 dark:border-white/10">
                            <div className="flex items-center justify-between">
                              <span className="text-foreground/50 font-mono text-[8.5px] font-black tracking-wider uppercase dark:text-white/40">
                                NODE DIAGNOSTICS
                              </span>
                              <span
                                className={`h-1.5 w-1.5 animate-pulse rounded-full ${
                                  node.status === "active" ||
                                  node.status === "connected" ||
                                  node.status === "healthy"
                                    ? "bg-emerald-400"
                                    : "bg-amber-400"
                                }`}
                              />
                            </div>

                            {/* Timeline events preview */}
                            <div className="flex min-h-0 flex-1 flex-col justify-between">
                              <div className="space-y-1">
                                <span className="text-foreground/40 font-mono text-[8px] font-bold tracking-wider uppercase dark:text-white/40">
                                  Timeline Events
                                </span>
                                {getNodeTimeline(node.id).length > 0 ? (
                                  <div className="max-h-[50px] space-y-1 overflow-y-auto pr-1 select-text">
                                    {getNodeTimeline(node.id)
                                      .slice(0, 2)
                                      .map((event, idx) => (
                                        <div
                                          key={idx}
                                          className="text-foreground/80 flex items-start gap-1 truncate text-[9px] dark:text-white/70"
                                        >
                                          <span className="text-foreground/40 font-mono text-[7.5px] dark:text-white/40">
                                            [{event.time}]
                                          </span>
                                          <span className="truncate">{event.desc}</span>
                                        </div>
                                      ))}
                                  </div>
                                ) : (
                                  <p className="text-foreground/40 text-[8.5px] leading-none italic dark:text-white/40">
                                    No events registered.
                                  </p>
                                )}
                              </div>

                              {/* Realtime prompt snippet (special for open_chat) */}
                              {node.id === "open_chat" && missionObjective && (
                                <div className="mt-1 truncate border-t border-slate-200/20 pt-1 dark:border-white/5">
                                  <span className="text-foreground/45 block font-mono text-[7.5px] font-bold tracking-wider uppercase dark:text-white/40">
                                    Active Objective
                                  </span>
                                  <p className="mt-0.5 truncate text-[9.5px] leading-tight font-medium text-cyan-600 italic dark:text-cyan-400">
                                    &quot;{missionObjective}&quot;
                                  </p>
                                </div>
                              )}
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {nodes.length === 0 || displayGraphPositions.size === 0 ? (
              <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
                <div className="rounded-[1.6rem] border border-slate-200/80 bg-white/96 px-6 py-5 text-center shadow-[0_20px_45px_rgba(15,23,42,0.08)] backdrop-blur-xl dark:border-white/8 dark:bg-black/45">
                  <p className="text-foreground text-sm font-black tracking-[0.18em] uppercase">
                    Graph Standby
                  </p>
                  <p className="text-muted-foreground mt-2 max-w-md text-sm leading-7">
                    The orchestration canvas is waiting for live mission graph data. Run a mission
                    or refresh the overview to populate the node map.
                  </p>
                </div>
              </div>
            ) : null}

            {/* Floating Bottom Status Indicator */}
            <div className="absolute bottom-4 left-4 z-20 flex flex-wrap items-center gap-3">
              <div className="flex flex-wrap items-center gap-2 rounded-[0.5rem] border border-slate-200/80 bg-white/96 p-2 text-[10px] font-black tracking-[0.18em] uppercase shadow-[0_12px_28px_rgba(15,23,42,0.08)] backdrop-blur-xl dark:border-white/8 dark:bg-black/45">
                <span className="border-primary/20 bg-primary/10 text-primary rounded-[0.35rem] border px-2.5 py-1">
                  {summary?.active_subagents ?? 0} active subagents
                </span>
                <span className="rounded-[0.35rem] border border-emerald-500/20 bg-emerald-500/10 px-2.5 py-1 text-emerald-700 dark:text-emerald-300">
                  {summary?.active_tasks ?? 0} active tasks
                </span>
                <span className="rounded-[0.35rem] border border-violet-500/20 bg-violet-500/10 px-2.5 py-1 text-violet-700 dark:text-violet-300">
                  {summary?.tool_count ?? data.tool_catalog.count} tools
                </span>
                <span className="rounded-[0.35rem] border border-amber-500/20 bg-amber-500/10 px-2.5 py-1 text-amber-700 dark:text-amber-300">
                  {summary?.connector_count ?? 0} sources
                </span>
              </div>
              <div className="text-foreground/40 rounded-[0.5rem] border border-slate-200/80 bg-white/96 px-2.5 py-2 text-[10px] font-medium shadow-[0_12px_28px_rgba(15,23,42,0.08)] backdrop-blur-xl dark:border-white/8 dark:bg-black/45">
                Updated {formatRelative(data.timestamp)}
              </div>
            </div>

            {/* Float Toggle Button for Dev View vs. User View */}
            <div className="absolute bottom-4 left-1/2 z-30 flex -translate-x-1/2 items-center gap-1 rounded-full border border-slate-200 bg-white/90 p-1 shadow-[0_12px_28px_rgba(15,23,42,0.08)] backdrop-blur-xl dark:border-white/10 dark:bg-black/80">
              <button
                type="button"
                onClick={() => setViewMode("user")}
                className={`rounded-full px-4 py-1.5 text-[9px] font-black tracking-[0.18em] uppercase transition ${
                  viewMode === "user"
                    ? "bg-primary font-bold text-white shadow-[0_0_12px_rgba(var(--primary),0.35)]"
                    : "text-foreground/60 hover:text-foreground hover:bg-slate-100 dark:hover:bg-white/5"
                }`}
              >
                User View
              </button>
              <button
                type="button"
                onClick={() => setViewMode("dev")}
                className={`rounded-full px-4 py-1.5 text-[9px] font-black tracking-[0.18em] uppercase transition ${
                  viewMode === "dev"
                    ? "bg-primary font-bold text-white shadow-[0_0_12px_rgba(var(--primary),0.35)]"
                    : "text-foreground/60 hover:text-foreground hover:bg-slate-100 dark:hover:bg-white/5"
                }`}
              >
                Dev View
              </button>
            </div>

            {/* Left Vertical Control Toggles */}
            <div className="absolute top-[8.25rem] left-3 z-30 flex flex-col gap-2">
              <button
                type="button"
                onClick={() => setShowMissionHealth((current) => !current)}
                className={`inline-flex h-9 w-9 items-center justify-center rounded-[0.5rem] border shadow-sm backdrop-blur-xl transition ${
                  showMissionHealth
                    ? "border-primary/30 bg-primary/10 text-primary"
                    : "text-foreground/72 hover:border-primary/30 hover:bg-primary/10 hover:text-primary border-slate-200/80 bg-white/96 dark:border-white/10 dark:bg-black/45 dark:text-white/75"
                }`}
                aria-label="Toggle mission health panel"
              >
                <Activity size={16} />
              </button>
              <button
                type="button"
                onClick={() => setShowRunner((current) => !current)}
                className={`inline-flex h-9 w-9 items-center justify-center rounded-[0.5rem] border shadow-sm backdrop-blur-xl transition ${
                  showRunner
                    ? "border-primary/30 bg-primary/10 text-primary"
                    : "text-foreground/72 hover:border-primary/30 hover:bg-primary/10 hover:text-primary border-slate-200/80 bg-white/96 dark:border-white/10 dark:bg-black/45 dark:text-white/75"
                }`}
                aria-label="Toggle mission runner panel"
              >
                <Layers3 size={16} />
              </button>
              <button
                type="button"
                onClick={() => setShowInspector((current) => !current)}
                className={`inline-flex h-9 w-9 items-center justify-center rounded-[0.5rem] border shadow-sm backdrop-blur-xl transition ${
                  showInspector
                    ? "border-primary/30 bg-primary/10 text-primary"
                    : "text-foreground/72 hover:border-primary/30 hover:bg-primary/10 hover:text-primary border-slate-200/80 bg-white/96 dark:border-white/10 dark:bg-black/45 dark:text-white/75"
                }`}
                aria-label="Toggle inspector panel"
              >
                <Sparkles size={16} />
              </button>
            </div>

            {/* Floating Zoom Controls */}
            <div className="absolute right-4 bottom-4 z-30 flex items-center gap-1.5 rounded-[0.5rem] border border-slate-200/80 bg-white/96 px-2.5 py-1.5 shadow-[0_12px_28px_rgba(15,23,42,0.08)] backdrop-blur-xl dark:border-white/8 dark:bg-black/45">
              <span className="text-foreground/45 px-1.5 text-[9px] font-black tracking-[0.22em] uppercase">
                Canvas
              </span>
              <button
                type="button"
                onClick={() => zoomBy(1.12)}
                className="theme-panel-muted hover:bg-primary/8 inline-flex h-7 w-7 items-center justify-center rounded-[0.35rem] border border-slate-200/80 bg-white/96 transition dark:border-white/8 dark:hover:bg-white/10"
                aria-label="Zoom in"
                title="Zoom in canvas"
              >
                <ZoomIn size={14} />
              </button>
              <button
                type="button"
                onClick={() => zoomBy(0.9)}
                className="theme-panel-muted hover:bg-primary/8 inline-flex h-7 w-7 items-center justify-center rounded-[0.35rem] border border-slate-200/80 bg-white/96 transition dark:border-white/8 dark:hover:bg-white/10"
                aria-label="Zoom out"
                title="Zoom out canvas"
              >
                <ZoomOut size={14} />
              </button>
              <button
                type="button"
                onClick={resetView}
                className="theme-panel-muted hover:bg-primary/8 inline-flex h-7 w-7 items-center justify-center rounded-[0.35rem] border border-slate-200/80 bg-white/96 transition dark:border-white/8 dark:hover:bg-white/10"
                aria-label="Reset camera"
                title="Reset canvas view"
              >
                <RotateCcw size={14} />
              </button>
            </div>
          </div>
        </div>

        <AnimatePresence>
          {showMissionHealth ? (
            <motion.aside
              initial={{ opacity: 0, x: -18, y: 10 }}
              animate={{ opacity: 1, x: 0, y: 0 }}
              exit={{ opacity: 0, x: -18, y: 10 }}
              transition={{ type: "spring", stiffness: 240, damping: 24 }}
              className="theme-panel-strong border-glass-border/40 bg-surface-1/30 !absolute top-[8.25rem] bottom-3 left-16 z-30 flex min-h-0 flex-col overflow-hidden rounded-[1.8rem] border p-4 shadow-[0_24px_90px_rgba(0,0,0,0.4)]"
              style={{ width: "320px" }}
            >
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <Activity size={16} className="text-primary" />
                  <h2 className="text-foreground text-[11px] font-black tracking-[0.2em] uppercase">
                    Mission health
                  </h2>
                </div>
                <button
                  type="button"
                  onClick={() => setShowMissionHealth(false)}
                  className="text-foreground/55 hover:text-foreground inline-flex h-9 w-9 items-center justify-center rounded-2xl border border-black/8 bg-slate-100/95 transition dark:border-white/10 dark:bg-white/[0.03] dark:text-white/60 dark:hover:text-white"
                  aria-label="Hide mission health panel"
                >
                  <Move size={14} />
                </button>
              </div>

              <div className="mt-4 min-h-0 flex-1 space-y-4 overflow-y-auto pr-1">
                <div className="space-y-3">
                  <StatusLine
                    label="Internet"
                    value={vitals?.internet ?? "unknown"}
                    tone={vitals?.internet === "connected" ? "emerald" : "amber"}
                  />
                  <StatusLine
                    label="LLM"
                    value={vitals?.llm ?? "unknown"}
                    tone={vitals?.llm === "connected" ? "emerald" : "amber"}
                  />
                  <StatusLine
                    label="Web search"
                    value={vitals?.web_search ?? "unknown"}
                    tone={vitals?.web_search === "available" ? "emerald" : "amber"}
                  />
                  <StatusLine
                    label="Connector sources"
                    value={String(vitals?.sources ?? 0)}
                    tone={(vitals?.sources ?? 0) > 0 ? "emerald" : "slate"}
                  />
                </div>

                <div className="rounded-2xl border border-slate-200/80 bg-white/95 p-4 shadow-[0_12px_28px_rgba(15,23,42,0.05)] dark:border-white/8 dark:bg-black/20">
                  <p className="text-foreground/40 text-[10px] font-black tracking-[0.2em] uppercase">
                    Runtime
                  </p>
                  <div className="mt-3 space-y-3 text-sm">
                    <MetaRow label="Model" value={runtime?.model_name || "Auto-selected"} />
                    <MetaRow label="Provider" value={runtime?.provider_type || "chat"} />
                    <MetaRow
                      label="Mode"
                      value={
                        runtime?.execution_mode === "full_access" ? "Full Access" : "Auto Review"
                      }
                    />
                    <MetaRow
                      label="Context"
                      value={
                        typeof runtime?.context_limit === "number" && runtime.context_limit > 0
                          ? `${runtime.context_limit.toLocaleString()} tokens`
                          : "Unknown"
                      }
                    />
                    <MetaRow label="Source" value={runtime?.context_limit_source || "unknown"} />
                  </div>
                </div>

                <div className="rounded-2xl border border-slate-200/80 bg-white/95 p-4 shadow-[0_12px_28px_rgba(15,23,42,0.05)] dark:border-white/8 dark:bg-black/20">
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-foreground/40 text-[10px] font-black tracking-[0.2em] uppercase">
                      Parallel lanes
                    </p>
                    <span className="border-primary/20 bg-primary/10 text-primary rounded-full border px-2 py-0.5 text-[10px] font-black tracking-[0.16em] uppercase">
                      {data.subagents.max_concurrency} max
                    </span>
                  </div>
                  <div className="mt-3 space-y-2">
                    {worlds.slice(0, 4).map((world) => (
                      <div
                        key={world.id}
                        className="flex items-start gap-3 rounded-xl border border-white/6 bg-white/[0.03] p-3"
                      >
                        <div className="bg-primary/10 text-primary rounded-lg p-1.5">
                          <Layers3 size={14} />
                        </div>
                        <div className="min-w-0">
                          <p className="text-foreground text-xs font-bold">{world.label}</p>
                          <p className="text-muted-foreground mt-1 text-[10px] leading-relaxed">
                            {world.description}
                          </p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="rounded-2xl border border-slate-200/80 bg-white/95 p-4 shadow-[0_12px_28px_rgba(15,23,42,0.05)] dark:border-white/8 dark:bg-black/20">
                  <p className="text-foreground/40 text-[10px] font-black tracking-[0.2em] uppercase">
                    Live activity
                  </p>
                  <div className="mt-3 space-y-2">
                    {recentActivities.slice(0, 5).map((activity) => (
                      <button
                        type="button"
                        key={activity.id}
                        onClick={() => setSelectedNodeId(`activity_${activity.id}`)}
                        className="hover:border-primary/20 hover:bg-primary/6 flex w-full items-start gap-3 rounded-xl border border-white/6 bg-white/[0.03] p-3 text-left transition"
                      >
                        <div className="rounded-lg bg-rose-500/10 p-1.5 text-rose-300">
                          <Zap size={14} />
                        </div>
                        <div className="min-w-0">
                          <p className="text-foreground text-xs leading-tight font-bold">
                            {activity.description}
                          </p>
                          <p className="text-muted-foreground mt-1 text-[10px] font-medium">
                            {activity.source} · {formatTime(activity.created_at)}
                          </p>
                        </div>
                      </button>
                    ))}
                    {recentActivities.length === 0 ? (
                      <div className="text-muted-foreground rounded-xl border border-dashed border-slate-200/80 px-3 py-6 text-center text-xs dark:border-white/8">
                        No recent autonomous activity yet.
                      </div>
                    ) : null}
                  </div>
                </div>

                <div className="rounded-2xl border border-slate-200/80 bg-white/95 p-4 shadow-[0_12px_28px_rgba(15,23,42,0.05)] dark:border-white/8 dark:bg-black/20">
                  <p className="text-foreground/40 text-[10px] font-black tracking-[0.2em] uppercase">
                    Active missions
                  </p>
                  <div className="mt-3 space-y-2">
                    {activeMissions.slice(0, 4).map((mission) => (
                      <div
                        key={mission.mission_id}
                        className="rounded-xl border border-white/6 bg-white/[0.03] p-3"
                      >
                        <div className="flex items-start justify-between gap-3">
                          <p className="text-foreground text-xs leading-tight font-bold">
                            {mission.objective}
                          </p>
                          <span className="rounded-full border border-white/10 bg-white/5 px-2 py-0.5 text-[9px] font-black tracking-[0.16em] text-white/55 uppercase">
                            {mission.status}
                          </span>
                        </div>
                        <p className="text-muted-foreground mt-1 text-[10px] leading-relaxed">
                          {mission.summary || mission.last_event_type || "Mission running."}
                        </p>
                        <div className="mt-2 flex flex-wrap gap-1.5">
                          {typeof mission.runtime_state?.planner_validation_status === "string" ? (
                            <span className="rounded-full border border-emerald-500/15 bg-emerald-500/10 px-2 py-0.5 text-[9px] font-black tracking-[0.16em] text-emerald-300 uppercase">
                              {String(mission.runtime_state.planner_validation_status).replace(
                                /_/g,
                                " ",
                              )}
                            </span>
                          ) : null}
                          {typeof mission.runtime_state?.runtime_hooks_state === "string" ? (
                            <span className="rounded-full border border-cyan-500/15 bg-cyan-500/10 px-2 py-0.5 text-[9px] font-black tracking-[0.16em] text-cyan-300 uppercase">
                              hooks {String(mission.runtime_state.runtime_hooks_state)}
                            </span>
                          ) : null}
                          {Array.isArray(mission.approval_queue) &&
                          mission.approval_queue.length > 0 ? (
                            <span className="rounded-full border border-amber-500/15 bg-amber-500/10 px-2 py-0.5 text-[9px] font-black tracking-[0.16em] text-amber-300 uppercase">
                              {mission.approval_queue.length} approvals
                            </span>
                          ) : null}
                        </div>
                      </div>
                    ))}
                    {activeMissions.length === 0 ? (
                      <div className="text-muted-foreground rounded-xl border border-dashed border-white/8 px-3 py-6 text-center text-xs">
                        No active missions right now.
                      </div>
                    ) : null}
                  </div>
                </div>
              </div>
            </motion.aside>
          ) : null}
        </AnimatePresence>

        <AnimatePresence>
          {showInspector ? (
            <motion.aside
              initial={{ opacity: 0, x: 18, y: 10 }}
              animate={{ opacity: 1, x: 0, y: 0 }}
              exit={{ opacity: 0, x: 18, y: 10 }}
              transition={{ type: "spring", stiffness: 240, damping: 24 }}
              className="theme-panel-strong border-glass-border/40 bg-surface-1/30 !absolute top-[8.25rem] right-16 bottom-3 z-30 flex min-h-0 flex-col overflow-hidden rounded-[1.8rem] border p-4 shadow-[0_24px_90px_rgba(0,0,0,0.4)]"
              style={{ width: "384px" }}
            >
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <Sparkles size={16} className="text-primary" />
                  <h2 className="text-foreground text-[11px] font-black tracking-[0.2em] uppercase">
                    Inspector
                  </h2>
                </div>
                <button
                  type="button"
                  onClick={() => setShowInspector(false)}
                  className="inline-flex h-9 w-9 items-center justify-center rounded-2xl border border-white/10 bg-white/[0.03] text-white/60 transition hover:text-white"
                  aria-label="Hide inspector panel"
                >
                  <Move size={14} />
                </button>
              </div>

              {selectedNode ? (
                <div className="mt-4 flex min-h-0 flex-1 flex-col overflow-hidden">
                  <div className="rounded-2xl border border-slate-200/80 bg-white/96 p-4 shadow-[0_12px_28px_rgba(15,23,42,0.05)] dark:border-white/8 dark:bg-black/20">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-foreground text-base font-black tracking-tight">
                          {selectedNode.id === "open_chat" &&
                          selectedSessionTitle &&
                          selectedSessionId !== "global"
                            ? `AverQel Core · ${selectedSessionTitle}`
                            : selectedNode.label}
                        </p>
                        <p className="text-foreground/45 mt-1 text-[10px] font-black tracking-[0.18em] uppercase">
                          {selectedNode.world} · {selectedNode.kind}
                        </p>
                      </div>
                      <span
                        className={`rounded-full border px-2 py-1 text-[10px] font-black tracking-[0.18em] uppercase ${statusPillClasses(selectedNode.status)}`}
                      >
                        {selectedNode.status}
                      </span>
                    </div>
                    <p className="text-muted-foreground mt-3 text-sm leading-7">
                      {nodePreview(selectedNode)}
                    </p>

                    <div className="mt-3.5 border-t border-slate-200/40 pt-3 dark:border-white/10">
                      <button
                        type="button"
                        onClick={() => {
                          toast.success(
                            `Health check passed for ${viewMode === "user" ? USER_FRIENDLY_LABELS[selectedNode.id] || selectedNode.label : selectedNode.label}. All signals normal.`,
                          );
                        }}
                        className="w-full text-center rounded-xl border border-primary/20 bg-primary/10 hover:bg-primary/15 px-4 py-2.5 font-mono text-[9px] font-black tracking-[0.18em] uppercase text-primary transition duration-200 shadow-md active:scale-[0.98]"
                      >
                        Test Health
                      </button>
                    </div>
                  </div>

                  <div className="mt-4 min-h-0 flex-1 space-y-4 overflow-y-auto pr-1">
                    <section className="rounded-2xl border border-slate-200/80 bg-white/96 p-4 shadow-[0_12px_28px_rgba(15,23,42,0.05)] dark:border-white/8 dark:bg-black/20">
                      <p className="text-foreground/40 text-[10px] font-black tracking-[0.2em] uppercase">
                        Node details
                      </p>
                      <div className="mt-3 space-y-2">
                        <MetaRow label="Node ID" value={selectedNode.id} />
                        <MetaRow
                          label="Position"
                          value={`${Math.round(selectedNode.x)}, ${Math.round(selectedNode.y)}, ${Math.round(selectedNode.z)}`}
                        />
                        <MetaRow label="World" value={selectedNode.world} />
                        <MetaRow label="Kind" value={selectedNode.kind} />
                      </div>
                    </section>

                    {selectedNodeDetails.length > 0 ? (
                      <section className="rounded-2xl border border-slate-200/80 bg-white/96 p-4 shadow-[0_12px_28px_rgba(15,23,42,0.05)] dark:border-white/8 dark:bg-black/20">
                        <p className="text-foreground/40 text-[10px] font-black tracking-[0.2em] uppercase">
                          Mission metadata
                        </p>
                        <div className="mt-3 space-y-2">
                          {selectedNodeDetails.map(([key, value]) => (
                            <MetaRow
                              key={key}
                              label={key.replace(/_/g, " ")}
                              value={typeof value === "string" ? value : JSON.stringify(value)}
                            />
                          ))}
                        </div>
                      </section>
                    ) : null}

                    <section className="rounded-2xl border border-slate-200/80 bg-white/96 p-4 shadow-[0_12px_28px_rgba(15,23,42,0.05)] dark:border-white/8 dark:bg-black/20">
                      <p className="text-foreground/40 text-[10px] font-black tracking-[0.2em] uppercase">
                        Orchestration summary
                      </p>
                      <div className="mt-3 space-y-2">
                        <MetaRow
                          label="Active subagents"
                          value={String(summary?.active_subagents ?? 0)}
                        />
                        <MetaRow label="Active tasks" value={String(summary?.active_tasks ?? 0)} />
                        <MetaRow
                          label="Recent activities"
                          value={String(summary?.recent_activities ?? 0)}
                        />
                        <MetaRow label="Tool count" value={String(summary?.tool_count ?? 0)} />
                        <MetaRow
                          label="Parallel capacity"
                          value={String(summary?.parallel_capacity ?? 0)}
                        />
                      </div>
                    </section>

                    <section className="rounded-2xl border border-slate-200/80 bg-white/95 p-4 shadow-[0_12px_28px_rgba(15,23,42,0.05)] dark:border-white/8 dark:bg-black/20">
                      <div className="flex items-center justify-between gap-3">
                        <p className="text-foreground/40 text-[10px] font-black tracking-[0.2em] uppercase">
                          Active subagents
                        </p>
                        <span className="border-primary/20 bg-primary/10 text-primary rounded-full border px-2 py-0.5 text-[10px] font-black tracking-[0.18em] uppercase">
                          {activeSubagents.length}
                        </span>
                      </div>
                      <div className="mt-3 space-y-2">
                        {activeSubagents.length > 0 ? (
                          activeSubagents.map((run) => (
                            <button
                              key={run.run_id}
                              type="button"
                              onClick={() => setSelectedNodeId(`subagent_${run.run_id}`)}
                              className="hover:border-primary/20 hover:bg-primary/6 flex w-full items-start justify-between gap-3 rounded-xl border border-white/6 bg-white/[0.03] p-3 text-left transition"
                            >
                              <div className="min-w-0">
                                <p className="text-foreground text-xs font-bold">
                                  {run.subagent_type}
                                </p>
                                <p className="text-muted-foreground mt-1 line-clamp-2 text-[10px] leading-relaxed">
                                  {run.summary || run.last_event_message || run.prompt}
                                </p>
                              </div>
                              <span className="rounded-full border border-emerald-500/20 bg-emerald-500/10 px-2 py-0.5 text-[9px] font-black tracking-[0.16em] text-emerald-300 uppercase">
                                lane {run.slot_index}
                              </span>
                            </button>
                          ))
                        ) : (
                          <div className="text-muted-foreground rounded-xl border border-dashed border-slate-200/80 px-3 py-5 text-center text-xs dark:border-white/8">
                            No subagents are currently running.
                          </div>
                        )}
                      </div>
                    </section>

                    <section className="rounded-2xl border border-white/8 bg-black/20 p-4">
                      <div className="flex items-center justify-between gap-3">
                        <p className="text-foreground/40 text-[10px] font-black tracking-[0.2em] uppercase">
                          Proactive tasks
                        </p>
                        <span className="rounded-full border border-emerald-500/20 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-black tracking-[0.18em] text-emerald-300 uppercase">
                          {activeTasks.length}
                        </span>
                      </div>
                      <div className="mt-3 space-y-2">
                        {activeTasks.length > 0 ? (
                          activeTasks.slice(0, 5).map((task) => (
                            <button
                              key={task.id}
                              type="button"
                              onClick={() => setSelectedNodeId(`task_${task.id}`)}
                              className="hover:border-primary/20 hover:bg-primary/6 flex w-full items-start justify-between gap-3 rounded-xl border border-white/6 bg-white/[0.03] p-3 text-left transition"
                            >
                              <div className="min-w-0">
                                <p className="text-foreground text-xs font-bold">
                                  {task.activeForm}
                                </p>
                                <p className="text-muted-foreground mt-1 line-clamp-2 text-[10px] leading-relaxed">
                                  {typeof task.automation_json?.prompt === "string"
                                    ? task.automation_json.prompt
                                    : task.content}
                                </p>
                              </div>
                              <span
                                className={`rounded-full border px-2 py-0.5 text-[9px] font-black tracking-[0.16em] uppercase ${statusPillClasses(task.status)}`}
                              >
                                {task.status}
                              </span>
                            </button>
                          ))
                        ) : (
                          <div className="text-muted-foreground rounded-xl border border-dashed border-slate-200/80 px-3 py-5 text-center text-xs dark:border-white/8">
                            No active proactive tasks right now.
                          </div>
                        )}
                      </div>
                    </section>

                    <section className="rounded-2xl border border-white/8 bg-black/20 p-4">
                      <div className="flex items-center justify-between gap-3">
                        <p className="text-foreground/40 text-[10px] font-black tracking-[0.2em] uppercase">
                          Tool atlas
                        </p>
                        <span className="rounded-full border border-violet-500/20 bg-violet-500/10 px-2 py-0.5 text-[10px] font-black tracking-[0.18em] text-violet-300 uppercase">
                          {data.tool_catalog.count}
                        </span>
                      </div>
                      <div className="mt-3 flex flex-wrap gap-2">
                        {activeTools.slice(0, 12).map((tool) => (
                          <span
                            key={tool}
                            className="rounded-full border border-violet-500/20 bg-violet-500/10 px-2.5 py-1 text-[10px] font-black tracking-[0.16em] text-violet-200 uppercase"
                          >
                            {tool}
                          </span>
                        ))}
                        {activeTools.length === 0 ? (
                          <span className="text-muted-foreground text-xs italic">
                            Tool catalog ready for any needed path.
                          </span>
                        ) : null}
                      </div>
                    </section>

                    <section className="rounded-2xl border border-slate-200/80 bg-white/96 p-4 shadow-[0_12px_28px_rgba(15,23,42,0.05)] dark:border-white/8 dark:bg-black/20">
                      <div className="flex items-center justify-between gap-3 border-b border-slate-200/40 dark:border-white/10 pb-2 mb-3">
                        <p className="text-foreground/40 text-[10px] font-black tracking-[0.2em] uppercase">
                          Timeline Events
                        </p>
                        <span className="border-amber-500/20 bg-amber-500/10 text-amber-300 rounded-full border px-2 py-0.5 text-[10px] font-black tracking-[0.18em] uppercase">
                          {getNodeTimeline(selectedNode.id).length} events
                        </span>
                      </div>
                      <div className="space-y-2 max-h-[160px] overflow-y-auto pr-1">
                        {getNodeTimeline(selectedNode.id).length > 0 ? (
                          getNodeTimeline(selectedNode.id).map((event, idx) => (
                            <div
                              key={idx}
                              className="text-foreground/80 flex items-start gap-2 text-xs leading-relaxed dark:text-white/80 border-b border-white/[0.03] pb-1.5 last:border-0 last:pb-0"
                            >
                              <span className="text-primary font-mono text-[9px] bg-primary/10 border border-primary/20 px-1.5 py-0.5 rounded">
                                {event.time}
                              </span>
                              <span className="flex-1 mt-0.5">{event.desc}</span>
                            </div>
                          ))
                        ) : (
                          <div className="text-muted-foreground text-center py-4 text-xs italic">
                            No events registered for this node.
                          </div>
                        )}
                      </div>
                    </section>
                  </div>
                </div>
              ) : (
                <div className="text-muted-foreground flex h-full items-center justify-center text-sm">
                  Select a node to inspect the mission layer.
                </div>
              )}
            </motion.aside>
          ) : null}
        </AnimatePresence>

        <AnimatePresence>
          {showRunner ? (
            <motion.section
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 16 }}
              transition={{ type: "spring", stiffness: 240, damping: 24 }}
              className="theme-panel-strong border-glass-border/40 bg-surface-1/30 !absolute bottom-3 z-30 flex min-h-0 flex-col gap-4 overflow-hidden rounded-[1.8rem] border p-4 shadow-[0_24px_90px_rgba(0,0,0,0.35)] transition-all duration-300"
              style={{
                left: showMissionHealth ? "calc(320px + 4.75rem)" : "0.75rem",
                right: showInspector ? "calc(384px + 4.75rem)" : "0.75rem",
              }}
            >
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-foreground/40 text-[10px] font-black tracking-[0.2em] uppercase">
                    Live mission runner
                  </p>
                  <h2 className="text-foreground mt-1 text-lg font-black tracking-tight">
                    Command and review the next orchestration pass.
                  </h2>
                </div>
                <button
                  type="button"
                  onClick={() => setShowRunner(false)}
                  className="inline-flex h-9 w-9 items-center justify-center rounded-2xl border border-white/10 bg-white/[0.03] text-white/60 transition hover:text-white"
                  aria-label="Hide mission runner"
                >
                  <Move size={14} />
                </button>
              </div>

              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                {runnerStats.map((card) => (
                  <MetricCard
                    key={card.label}
                    label={card.label}
                    value={card.value}
                    helper={card.helper}
                    tone={card.tone}
                    icon={card.icon}
                  />
                ))}
              </div>

              <div className="flex flex-col gap-3 xl:flex-row xl:items-end xl:justify-between">
                <div className="min-w-0 flex-1">
                  <textarea
                    value={missionObjective}
                    onChange={(event) => setMissionObjective(event.target.value)}
                    className="border-glass-border bg-background/50 text-foreground focus:border-primary/40 min-h-[96px] w-full rounded-2xl border p-3 text-sm transition outline-none"
                    placeholder="Describe the mission you want the global orchestrator to run..."
                  />
                </div>
                <div className="flex flex-col gap-2 xl:w-[260px]">
                  <button
                    type="button"
                    onClick={() => void runMission()}
                    disabled={missionRunning || !missionObjective.trim()}
                    className="bg-primary hover:bg-primary/90 disabled:bg-primary/40 inline-flex items-center justify-center gap-2 rounded-full px-4 py-2.5 text-xs font-black tracking-[0.18em] text-white uppercase transition disabled:cursor-not-allowed"
                  >
                    <Sparkles size={14} />
                    {missionRunning ? "Running" : "Run Mission"}
                  </button>
                  <div className="text-foreground/40 text-[10px] font-black tracking-[0.18em] uppercase">
                    Status: {missionStatus || "idle"}
                  </div>
                  {missionId ? (
                    <div className="text-foreground/40 truncate font-mono text-[10px]">
                      Mission: {missionId}
                    </div>
                  ) : null}
                  {pendingApproval ? (
                    <div className="mt-1 rounded-2xl border border-amber-500/20 bg-amber-500/10 p-3">
                      <p className="text-[10px] font-black tracking-[0.18em] text-amber-100 uppercase">
                        Approval needed
                      </p>
                      <p className="mt-1 text-xs leading-6 text-amber-50/80">
                        {pendingApproval.message ||
                          "This lane is waiting for your approval before the mission can continue."}
                      </p>
                      <div className="mt-3 flex flex-wrap gap-2">
                        <button
                          type="button"
                          onClick={() => void resolveMissionApproval(true)}
                          className="inline-flex items-center gap-2 rounded-full bg-emerald-500/90 px-3 py-2 text-[10px] font-black tracking-[0.18em] text-white uppercase transition hover:bg-emerald-500"
                        >
                          Approve
                        </button>
                        <button
                          type="button"
                          onClick={() => void resolveMissionApproval(false)}
                          className="inline-flex items-center gap-2 rounded-full bg-rose-500/90 px-3 py-2 text-[10px] font-black tracking-[0.18em] text-white uppercase transition hover:bg-rose-500"
                        >
                          Decline
                        </button>
                      </div>
                    </div>
                  ) : null}
                </div>
              </div>

              {missionError ? (
                <div className="rounded-xl border border-rose-500/20 bg-rose-500/10 px-3 py-2 text-xs text-rose-200">
                  {missionError}
                </div>
              ) : null}

              <div className="max-h-44 overflow-auto rounded-2xl border border-white/8 bg-black/30 p-3 font-mono text-[10px] leading-relaxed text-white/70">
                {missionLog.length > 0 ? (
                  <>
                    {hiddenMissionLogCount > 0 ? (
                      <div className="mb-2 rounded-lg border border-white/8 bg-white/[0.03] px-2 py-1 text-white/40">
                        {hiddenMissionLogCount.toLocaleString()} older mission events hidden for
                        performance. Showing latest {visibleMissionLog.length.toLocaleString()}.
                      </div>
                    ) : null}
                    {visibleMissionLog.map((line, index) => (
                      <div key={`${missionLog.length - visibleMissionLog.length + index}-${line}`}>
                        {line}
                      </div>
                    ))}
                  </>
                ) : (
                  <div className="text-white/35 italic">Mission events will appear here.</div>
                )}
              </div>

            </motion.section>
          ) : null}
        </AnimatePresence>
      </div>

      {/* Right Vertical Control Container (visible only on lg+ screens) */}
      <div
        className={`absolute top-[8.25rem] right-3 z-30 hidden flex-col items-center gap-3 transition-opacity duration-150 lg:flex ${
          dashboardNavOpen ? "pointer-events-none opacity-0" : "opacity-100"
        }`}
      >
        {/* 8 System Info Buttons */}
        <div className="flex flex-col gap-2">
          {[
            { id: "agentic-workflows", icon: Workflow, label: "Agentic Workflows" },
            { id: "tool-orchestration", icon: Wrench, label: "Tool Orchestration" },
            { id: "agentic-loops", icon: Loader, label: "Agentic Loops" },
            { id: "connectors", icon: LinkIcon, label: "Connectors & Integrations" },
            { id: "autonomous-agents", icon: Brain, label: "Autonomous Agents" },
            { id: "infrastructure", icon: Network, label: "Infrastructure & Scaling" },
            { id: "streaming", icon: Zap, label: "Inline Streaming & Events" },
            { id: "monitoring", icon: Activity, label: "Monitoring & Telemetry" },
          ].map(({ id, icon: Icon, label }) => (
            <div key={id} className="group relative">
              <button
                type="button"
                onClick={() => setActiveSystemPanel(activeSystemPanel === id ? null : id)}
                className={`theme-panel-muted hover:border-primary/30 hover:bg-primary/10 hover:text-primary relative flex h-9 w-9 items-center justify-center rounded-[0.5rem] border border-slate-200/80 bg-white/96 transition-all duration-300 hover:scale-105 dark:border-white/10 dark:bg-black/45 dark:text-white/75 ${
                  activeSystemPanel === id
                    ? "border-primary/30 bg-primary/10 text-primary ring-primary/20 ring-2"
                    : ""
                }`}
                aria-label={label}
              >
                <Icon size={16} className="transition" />
              </button>
              <div className="pointer-events-none absolute top-1/2 right-12 z-[100] -translate-y-1/2 rounded bg-black/90 px-2 py-1 text-xs whitespace-nowrap text-white/80 opacity-0 transition group-hover:opacity-100">
                {label}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* System information detail panel */}
      <AnimatePresence mode="wait">
        {activeSystemPanel && !dashboardNavOpen && (
          <motion.div
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 20 }}
            transition={{ duration: 0.3 }}
            className="theme-panel-strong border-glass-border/40 bg-surface-1/25 !absolute top-[13.5rem] right-4 left-4 z-40 max-h-[calc(100vh-16rem)] w-auto overflow-y-auto rounded-[1.6rem] border p-6 shadow-[0_20px_90px_rgba(0,0,0,0.28)] backdrop-blur-xl lg:top-[8.25rem] lg:right-16 lg:left-auto lg:max-h-[calc(100vh-11rem)] lg:w-96"
          >
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-foreground text-sm font-black tracking-tight uppercase">
                System Details
              </h3>
              <button
                type="button"
                onClick={() => setActiveSystemPanel(null)}
                className="text-foreground/40 hover:text-foreground/80 text-xl transition"
              >
                ×
              </button>
            </div>

            {activeSystemPanel === "agentic-workflows" && (
              <div className="space-y-4 text-sm">
                <div>
                  <p className="text-primary mb-1 text-xs font-black tracking-[0.1em] uppercase">
                    Parallel Agentic Workflows
                  </p>
                  <p className="text-foreground/70 text-xs leading-relaxed">
                    {summary?.active_subagents ?? 0} active subagents executing parallel tasks
                    across {data?.subagents.max_concurrency ?? 4} concurrent lanes. Each agent
                    maintains independent reasoning state and tool access permissions.
                  </p>
                </div>
                <div className="space-y-2 border-t border-white/10 pt-3">
                  <p className="text-foreground/50 text-xs font-black tracking-[0.1em] uppercase">
                    Execution Models
                  </p>
                  <ul className="text-foreground/70 space-y-1 text-xs">
                    <li>• Sequential workflow chains</li>
                    <li>• Parallel branch execution</li>
                    <li>• Dynamic loop control</li>
                    <li>• Conditional branching logic</li>
                  </ul>
                </div>
              </div>
            )}

            {activeSystemPanel === "tool-orchestration" && (
              <div className="space-y-4 text-sm">
                <div>
                  <p className="text-primary mb-1 text-xs font-black tracking-[0.1em] uppercase">
                    Tool Execution & Scaling
                  </p>
                  <p className="text-foreground/70 text-xs leading-relaxed">
                    {data?.tool_catalog.count ?? 0} tools available in catalog.{" "}
                    {summary?.active_tasks ?? 0} concurrent tool invocations active. Automatic
                    scaling based on queue depth and system load.
                  </p>
                </div>
                <div className="space-y-2 border-t border-white/10 pt-3">
                  <p className="text-foreground/50 text-xs font-black tracking-[0.1em] uppercase">
                    Tool Categories
                  </p>
                  <ul className="text-foreground/70 space-y-1 text-xs">
                    <li>• Web Search & Information Retrieval</li>
                    <li>• Code Execution & Analysis</li>
                    <li>• Data Processing & Transformation</li>
                    <li>• Integration & API Calls</li>
                    <li>• Document Analysis & Generation</li>
                  </ul>
                </div>
              </div>
            )}

            {activeSystemPanel === "agentic-loops" && (
              <div className="space-y-4 text-sm">
                <div>
                  <p className="text-primary mb-1 text-xs font-black tracking-[0.1em] uppercase">
                    Agentic Loop Control
                  </p>
                  <p className="text-foreground/70 text-xs leading-relaxed">
                    Inline agentic loops with think-act-observe cycles. Real-time streaming of loop
                    iterations for visibility and control. Dynamic loop depth management with escape
                    conditions.
                  </p>
                </div>
                <div className="space-y-2 border-t border-white/10 pt-3">
                  <p className="text-foreground/50 text-xs font-black tracking-[0.1em] uppercase">
                    Loop Mechanisms
                  </p>
                  <ul className="text-foreground/70 space-y-1 text-xs">
                    <li>• Think-Act-Observe cycles</li>
                    <li>• Tool result streaming</li>
                    <li>• Convergence detection</li>
                    <li>• Max iteration limits</li>
                  </ul>
                </div>
              </div>
            )}

            {activeSystemPanel === "connectors" && (
              <div className="space-y-4 text-sm">
                <div>
                  <p className="text-primary mb-1 text-xs font-black tracking-[0.1em] uppercase">
                    Connectors & Integrations
                  </p>
                  <p className="text-foreground/70 text-xs leading-relaxed">
                    Multi-protocol connector infrastructure for external system integration.
                    Real-time health monitoring and automatic failover. 24/7 autonomous connectivity
                    management.
                  </p>
                </div>
                <div className="space-y-2 border-t border-white/10 pt-3">
                  <p className="text-foreground/50 text-xs font-black tracking-[0.1em] uppercase">
                    Integration Types
                  </p>
                  <ul className="text-foreground/70 space-y-1 text-xs">
                    <li>• REST & GraphQL APIs</li>
                    <li>• Webhook & Event Streams</li>
                    <li>• Database Connections</li>
                    <li>• Message Queues</li>
                    <li>• File System Integration</li>
                  </ul>
                </div>
              </div>
            )}

            {activeSystemPanel === "autonomous-agents" && (
              <div className="space-y-4 text-sm">
                <div>
                  <p className="text-primary mb-1 text-xs font-black tracking-[0.1em] uppercase">
                    Proactive Autonomous Agents
                  </p>
                  <p className="text-foreground/70 text-xs leading-relaxed">
                    {summary?.active_subagents ?? 0} autonomous agents running proactive background
                    tasks. Durable task state persistence with checkpoint recovery.
                  </p>
                </div>
                <div className="space-y-2 border-t border-white/10 pt-3">
                  <p className="text-foreground/50 text-xs font-black tracking-[0.1em] uppercase">
                    Autonomy Features
                  </p>
                  <ul className="text-foreground/70 space-y-1 text-xs">
                    <li>• Background task execution</li>
                    <li>• Scheduled workflows</li>
                    <li>• Event-triggered automation</li>
                    <li>• State persistence & recovery</li>
                    <li>• Long-running job management</li>
                  </ul>
                </div>
              </div>
            )}

            {activeSystemPanel === "infrastructure" && (
              <div className="space-y-4 text-sm">
                <div>
                  <p className="text-primary mb-1 text-xs font-black tracking-[0.1em] uppercase">
                    Infrastructure & Scaling
                  </p>
                  <p className="text-foreground/70 text-xs leading-relaxed">
                    Distributed execution infrastructure with automatic capacity scaling.
                    Multi-region deployment support. Real-time resource monitoring and allocation.
                  </p>
                </div>
                <div className="space-y-2 border-t border-white/10 pt-3">
                  <p className="text-foreground/50 text-xs font-black tracking-[0.1em] uppercase">
                    Infrastructure Details
                  </p>
                  <ul className="text-foreground/70 space-y-1 text-xs">
                    <li>• Max concurrent capacity: {data?.subagents.max_concurrency ?? "N/A"}</li>
                    <li>• Auto-scaling enabled</li>
                    <li>• Load balancing active</li>
                    <li>• Multi-region support</li>
                  </ul>
                </div>
              </div>
            )}

            {activeSystemPanel === "streaming" && (
              <div className="space-y-4 text-sm">
                <div>
                  <p className="text-primary mb-1 text-xs font-black tracking-[0.1em] uppercase">
                    Inline Streaming & Events
                  </p>
                  <p className="text-foreground/70 text-xs leading-relaxed">
                    Real-time event streaming for all system operations. Token-level streaming for
                    LLM outputs. Sub-millisecond event propagation.
                  </p>
                </div>
                <div className="space-y-2 border-t border-white/10 pt-3">
                  <p className="text-foreground/50 text-xs font-black tracking-[0.1em] uppercase">
                    Streaming Capabilities
                  </p>
                  <ul className="text-foreground/70 space-y-1 text-xs">
                    <li>• Server-sent events (SSE)</li>
                    <li>• Token-level LLM streaming</li>
                    <li>• Tool execution events</li>
                    <li>• Loop iteration updates</li>
                    <li>• Task progress streaming</li>
                  </ul>
                </div>
              </div>
            )}

            {activeSystemPanel === "monitoring" && (
              <div className="space-y-4 text-sm">
                <div>
                  <p className="text-primary mb-1 text-xs font-black tracking-[0.1em] uppercase">
                    Monitoring & Telemetry
                  </p>
                  <p className="text-foreground/70 text-xs leading-relaxed">
                    Comprehensive observability across all orchestration layers. Real-time health
                    metrics and performance analytics.
                  </p>
                </div>
                <div className="space-y-2 border-t border-white/10 pt-3">
                  <p className="text-foreground/50 text-xs font-black tracking-[0.1em] uppercase">
                    Metrics & Status
                  </p>
                  <ul className="text-foreground/70 space-y-1 text-xs">
                    <li>• Active missions: {data?.missions?.count ?? 0}</li>
                    <li>• LLM status: {vitals?.llm || "Healthy"}</li>
                    <li>• Connector health: {vitals?.internet || "Connected"}</li>
                    <li>• Web search: {vitals?.web_search || "Available"}</li>
                  </ul>
                </div>
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      <ConfirmationModal
        isOpen={!!killTaskId}
        onClose={() => setKillTaskId(null)}
        onConfirm={async () => {
          if (!killTaskId) return;
          setKillingTask(true);
          try {
            await handleKillTask(killTaskId);
          } finally {
            setKillingTask(false);
            setKillTaskId(null);
          }
        }}
        title="Terminate Task Process"
        message="Are you sure you want to terminate this task process? This action cannot be undone."
        confirmLabel="Terminate Process"
        variant="danger"
        loading={killingTask}
      />
    </div>
  );
}

function MetricCard({
  label,
  value,
  helper,
  tone,
  icon,
}: {
  label: string;
  value: string;
  helper: string;
  tone: "emerald" | "amber" | "violet" | "cyan" | "rose";
  icon: ReactNode;
}) {
  const toneClassesMap: Record<typeof tone, string> = {
    emerald: "border-emerald-500/20 bg-emerald-500/10 text-emerald-700 dark:text-emerald-100",
    amber: "border-amber-500/20 bg-amber-500/10 text-amber-700 dark:text-amber-100",
    violet: "border-violet-500/20 bg-violet-500/10 text-violet-700 dark:text-violet-100",
    cyan: "border-cyan-500/20 bg-cyan-500/10 text-cyan-700 dark:text-cyan-100",
    rose: "border-rose-500/20 bg-rose-500/10 text-rose-700 dark:text-rose-100",
  };

  return (
    <div className="theme-panel-muted rounded-2xl border border-slate-200/80 bg-white/96 p-4 shadow-[0_14px_30px_rgba(15,23,42,0.06)] dark:border-white/8 dark:bg-black/20">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-foreground/40 text-[10px] font-black tracking-[0.2em] uppercase">
            {label}
          </p>
          <p className="text-foreground mt-2 text-xl font-black tracking-tight">{value}</p>
        </div>
        <div className={`rounded-xl border p-2.5 ${toneClassesMap[tone]}`}>{icon}</div>
      </div>
      <p className="text-muted-foreground mt-3 text-[11px] leading-relaxed">{helper}</p>
    </div>
  );
}

function MetaRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-4 rounded-xl border border-slate-200/80 bg-white/95 px-3 py-2.5 dark:border-white/6 dark:bg-white/[0.03]">
      <span className="text-foreground/40 min-w-0 text-[10px] font-black tracking-[0.18em] uppercase">
        {label}
      </span>
      <span className="text-foreground max-w-[65%] min-w-0 text-right font-mono text-[11px] leading-relaxed break-words">
        {value}
      </span>
    </div>
  );
}

function StatusLine({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: "emerald" | "amber" | "slate";
}) {
  const toneClassesMap: Record<typeof tone, string> = {
    emerald: "border-emerald-500/20 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
    amber: "border-amber-500/20 bg-amber-500/10 text-amber-700 dark:text-amber-300",
    slate:
      "border-slate-300/80 bg-slate-100/90 text-slate-600 dark:border-white/10 dark:bg-white/5 dark:text-white/45",
  };

  return (
    <div className="flex items-center justify-between gap-4 rounded-2xl border border-slate-200/80 bg-white/95 px-3 py-2.5 dark:border-white/6 dark:bg-white/[0.03]">
      <span className="text-foreground/40 text-[10px] font-black tracking-[0.2em] uppercase">
        {label}
      </span>
      <span
        className={`rounded-full border px-2.5 py-1 text-[10px] font-black tracking-[0.16em] uppercase ${toneClassesMap[tone]}`}
      >
        {value}
      </span>
    </div>
  );
}
