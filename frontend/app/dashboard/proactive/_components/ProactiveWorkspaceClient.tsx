"use client";

import { AnimatePresence, motion } from "framer-motion";
import {
  ArrowLeft,
  BarChart2,
  Bell,
  BrainCircuit,
  Calendar,
  Check,
  CheckSquare,
  ChevronRight,
  ClipboardCopy,
  Clock,
  Cpu,
  Database,
  ExternalLink,
  FileText,
  GitBranch,
  Inbox,
  ListChecks,
  Mail,
  MessageSquare,
  Network,
  Play,
  RefreshCw,
  Search,
  ShieldCheck,
  Sparkles,
  Terminal,
  Workflow,
  X,
  Zap,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { fetchWithAuth } from "@/lib/api";

interface RuntimeInfo {
  model_name?: string | null;
  provider_type?: string | null;
  context_limit?: number | null;
  context_limit_source?: string | null;
}

interface VitalsInfo {
  internet: string;
  llm: string;
  web_search: string;
  sources: number;
}

interface ProactiveActivity {
  id: string;
  type: string;
  description: string;
  source: string;
  created_at: string;
  metadata?: Record<string, unknown> | null;
}

interface WorkspaceNotification {
  id: string;
  collection_id: string | null;
  collection_name: string;
  event_type: string;
  message: string;
  created_at: string;
  read_at: string | null;
}

interface ConnectorSummary {
  id: string;
  name: string;
  status: string;
  last_sync_at: string | null;
  integration_id: string;
}

interface ConnectorFleetSummary {
  total_connectors: number;
  active_count: number;
  syncing_count: number;
  paused_count: number;
  error_count: number;
  healthy_count: number;
  stale_count: number;
  retryable_count: number;
  due_sync_count: number;
  recent_audit_count: number;
  status_breakdown: Record<string, number>;
  integration_breakdown: Record<string, number>;
  error_domain_breakdown: Record<string, number>;
  health_status_breakdown: Record<string, number>;
  retry_state_breakdown: Record<string, number>;
  attention_connectors: Array<{
    id: string;
    name: string;
    integration_slug: string;
    status: string;
    live_status: string;
    retry_state: string;
    retryable: boolean | null;
    retry_after_at: string | null;
    retry_after_seconds: number | null;
    health_age_seconds: number | null;
    sync_checkpoint_age_seconds: number | null;
    error_domain: string | null;
  }>;
  daemon_heartbeat?: {
    phase: string;
    timestamp?: string | null;
    interval_seconds?: number | null;
  } | null;
}

interface MemoryLifecycleSummary {
  memory_count: number;
  embedded_count: number;
  pgvector_count: number;
  embedding_coverage: number;
  duplicate_count: number;
  scope_breakdown: Record<string, number>;
  retention_breakdown: Record<string, number>;
  stale_count: number;
  average_decay_score: number;
  sample_queries: Array<{ query: string; matches: number; top_score: number }>;
  retention_policy: {
    session_retention_days: number;
    decay_half_life_days: number;
  };
  session_retention_days: number;
  stale_memory_ids: string[];
  stale_preview_count: number;
  attention_memories: Array<{
    id: string;
    key: string;
    value: string;
    scope: string;
    tags: string[];
    importance_score: number;
    access_count: number;
    last_accessed_at: string | null;
    metadata: Record<string, unknown>;
    embedding_provider: string | null;
    embedding_model: string | null;
    embedding_version: string | null;
    pgvector_ready: boolean | null;
    decay_score: number | null;
    created_at: string | null;
    updated_at: string | null;
    retention_state: string;
  }>;
}

interface ProactiveTask {
  id: string;
  content: string;
  status: "pending" | "in_progress" | "completed" | string;
  activeForm: string;
  priority: number;
  thread_id?: string | null;
  metadata_json?: Record<string, unknown> | null;
  automation_json?: Record<string, unknown> | null;
  is_recurring?: boolean;
  enabled?: boolean;
  next_run_at?: string | null;
  last_run_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

interface ProactiveTaskSummary {
  total: number;
  pending: number;
  in_progress: number;
  completed: number;
  recurring: number;
  enabled: number;
  paused: number;
  due: number;
  approval_required: number;
  source_breakdown: Record<string, number>;
  recent_activity_count: number;
  recent_error_count: number;
  recent_cycle_count: number;
  recent_cycle_failure_count: number;
  gmail_scan_failure_count: number;
  gmail_message_failure_count: number;
  last_cycle_at: string | null;
  last_cycle_status: string | null;
}

interface InsertedDraft {
  id: string;
  title: string;
  content: string;
  created_at: string;
}

type RuleScheduleType = "manual" | "daily" | "weekly" | "interval";
type RuleActionType = "agent_prompt" | "connector_sync";

interface RuleEditorState {
  content: string;
  active_form: string;
  status: "pending" | "in_progress" | "completed";
  priority: number;
  thread_id: string;
  is_recurring: boolean;
  enabled: boolean;
  schedule_type: RuleScheduleType;
  interval_minutes: number;
  next_run_at: string;
  action_type: RuleActionType;
  prompt: string;
  note_content: string;
  connector_id: string;
  requires_approval: boolean;
  thinking_enabled: boolean;
  web_search_enabled: boolean;
  source: string;
  phase: string;
}

const TERMINAL_ICON_MAP: Record<string, ReactNode> = {
  gmail: <Mail size={13} />,
  "google-calendar": <Calendar size={13} />,
  calendar: <Calendar size={13} />,
  slack: <MessageSquare size={13} />,
  github: <Workflow size={13} />,
  notion: <FileText size={13} />,
  "google-drive": <Database size={13} />,
  "web-crawler": <Search size={13} />,
  heartbeat: <Zap size={13} />,
  scan: <Search size={13} />,
  match: <Cpu size={13} />,
  draft: <Sparkles size={13} />,
  sync: <RefreshCw size={13} />,
};

function getStepLabel(activityType: string): string {
  switch (activityType) {
    case "heartbeat":
      return "SCAN";
    case "sync":
      return "SYNC";
    case "match":
      return "MATCH";
    case "draft":
      return "DRAFT";
    case "notification":
      return "NOTICE";
    case "error":
      return "ERROR";
    default:
      return activityType.toUpperCase();
  }
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function formatConnectorSource(source: string): string {
  return source.replace(/-/g, " ");
}

function readDraftBody(activity: ProactiveActivity): string | null {
  const metadata = activity.metadata ?? {};
  const keys = ["draft_body", "draft_html", "summary", "message"] as const;
  for (const key of keys) {
    const value = metadata[key];
    if (typeof value === "string" && value.trim()) {
      return value.trim();
    }
  }
  return null;
}

function readDraftTitle(activity: ProactiveActivity): string | null {
  const metadata = activity.metadata ?? {};
  const keys = ["draft_title", "title", "subject"] as const;
  for (const key of keys) {
    const value = metadata[key];
    if (typeof value === "string" && value.trim()) {
      return value.trim();
    }
  }
  return null;
}

function readTaskSource(task: ProactiveTask): string | null {
  const metadata = task.metadata_json ?? {};
  const keys = ["source", "integration_slug", "connector_name"] as const;
  for (const key of keys) {
    const value = metadata[key];
    if (typeof value === "string" && value.trim()) {
      return value.trim();
    }
  }
  return null;
}

function readAutomationValue(task: ProactiveTask, key: string): string | null {
  const automation = task.automation_json ?? {};
  const value = automation[key];
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function formatTaskSchedule(task: ProactiveTask): string | null {
  const automation = task.automation_json ?? {};
  const scheduleType = readAutomationValue(task, "schedule_type") ?? "manual";
  if (!task.is_recurring) {
    return scheduleType === "manual" ? "One-time" : scheduleType;
  }
  if (scheduleType === "interval") {
    const minutes = automation.interval_minutes;
    return typeof minutes === "number" && minutes > 0
      ? `Every ${minutes} min`
      : "Recurring interval";
  }
  if (scheduleType === "weekly") return "Weekly";
  if (scheduleType === "daily") return "Daily";
  return scheduleType;
}

function taskStatusLabel(status: ProactiveTask["status"]): string {
  switch (status) {
    case "completed":
      return "DONE";
    case "in_progress":
      return "ACTIVE";
    case "pending":
      return "QUEUED";
    default:
      return String(status || "queued").toUpperCase();
  }
}

function taskStatusClass(status: ProactiveTask["status"]): string {
  switch (status) {
    case "completed":
      return "border-emerald-500/20 bg-emerald-500/10 text-emerald-300";
    case "in_progress":
      return "border-cyan-500/20 bg-cyan-500/10 text-cyan-300";
    case "pending":
      return "border-amber-500/20 bg-amber-500/10 text-amber-300";
    default:
      return "border-white/10 bg-white/5 text-foreground/60";
  }
}

export function getDraftQueueLabel(date = new Date()): string {
  const hour = date.getHours();
  if (hour >= 5 && hour < 11) return "Morning drafts";
  if (hour >= 11 && hour < 16) return "Midday drafts";
  if (hour >= 16 && hour < 20) return "Evening drafts";
  return "Overnight drafts";
}

export function getDraftQueueDescription(date = new Date()): string {
  const hour = date.getHours();
  if (hour >= 5 && hour < 11) {
    return "Briefings, follow-ups, and ready-to-review work from the early cycle.";
  }
  if (hour >= 11 && hour < 16) {
    return "Active midday work, connector updates, and drafts that need attention.";
  }
  if (hour >= 16 && hour < 20) {
    return "Wrap-up notes, handoff drafts, and tasks queued for the next cycle.";
  }
  return "Late-cycle work, async follow-ups, and overnight tasks awaiting review.";
}

function getSourceIcon(source: string): ReactNode {
  return TERMINAL_ICON_MAP[source] ?? <Terminal size={13} />;
}

function stripHtml(html: string): string {
  return html
    .replace(/<style[\s\S]*?<\/style>/gi, " ")
    .replace(/<script[\s\S]*?<\/script>/gi, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/gi, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function toDateTimeLocal(value?: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const offsetMinutes = date.getTimezoneOffset();
  const localDate = new Date(date.getTime() - offsetMinutes * 60_000);
  return localDate.toISOString().slice(0, 16);
}

function fromDateTimeLocal(value: string): string | null {
  if (!value.trim()) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date.toISOString();
}

function createDefaultRuleState(): RuleEditorState {
  const nextRun = new Date(Date.now() + 24 * 60 * 60 * 1000);
  nextRun.setMinutes(0, 0, 0);
  return {
    content: "",
    active_form: "",
    status: "pending",
    priority: 50,
    thread_id: "",
    is_recurring: true,
    enabled: true,
    schedule_type: "daily",
    interval_minutes: 1440,
    next_run_at: toDateTimeLocal(nextRun.toISOString()),
    action_type: "agent_prompt",
    prompt: "",
    note_content: "",
    connector_id: "",
    requires_approval: false,
    thinking_enabled: true,
    web_search_enabled: true,
    source: "proactive",
    phase: "schedule",
  };
}

function ruleFromTask(task: ProactiveTask): RuleEditorState {
  const automation = task.automation_json ?? {};
  const metadata = task.metadata_json ?? {};
  const scheduleTypeRaw = automation.schedule_type;
  const schedule_type =
    scheduleTypeRaw === "interval" || scheduleTypeRaw === "weekly" || scheduleTypeRaw === "daily"
      ? scheduleTypeRaw
      : "manual";
  return {
    content: task.content,
    active_form: task.activeForm,
    status: task.status === "in_progress" || task.status === "completed" ? task.status : "pending",
    priority: task.priority ?? 0,
    thread_id: task.thread_id ?? "",
    is_recurring: Boolean(task.is_recurring),
    enabled: task.enabled !== false,
    schedule_type,
    interval_minutes:
      typeof automation.interval_minutes === "number" && automation.interval_minutes > 0
        ? automation.interval_minutes
        : 1440,
    next_run_at: toDateTimeLocal(task.next_run_at),
    action_type: automation.action_type === "connector_sync" ? "connector_sync" : "agent_prompt",
    prompt:
      typeof automation.prompt === "string" && automation.prompt.trim()
        ? automation.prompt
        : task.activeForm,
    note_content:
      typeof automation.note_content === "string" && automation.note_content.trim()
        ? automation.note_content
        : "",
    connector_id:
      typeof automation.connector_id === "string" && automation.connector_id.trim()
        ? automation.connector_id
        : "",
    requires_approval: Boolean(automation.requires_approval),
    thinking_enabled:
      typeof automation.thinking_enabled === "boolean" ? automation.thinking_enabled : true,
    web_search_enabled:
      typeof automation.web_search_enabled === "boolean" ? automation.web_search_enabled : true,
    source:
      typeof metadata.source === "string" && metadata.source.trim() ? metadata.source : "proactive",
    phase:
      typeof metadata.phase === "string" && metadata.phase.trim() ? metadata.phase : "schedule",
  };
}

// ─── orchestration graph types ───────────────────────────────────────────────
interface OrchestraNode {
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
interface OrchestraEdge {
  source: string;
  target: string;
  label: string;
  tone: string;
  kind: string;
}
interface OrchestraGraph {
  nodes: OrchestraNode[];
  edges: OrchestraEdge[];
}
interface OrchestrationOverviewPayload {
  graph: OrchestraGraph;
  summary?: {
    active_subagents?: number;
    active_tasks?: number;
    tool_count?: number;
    connector_count?: number;
    daemon_healthy?: boolean;
  };
  missions?: { count?: number; execution_mode?: string };
  runtime?: { model_name?: string; provider_type?: string };
}

// ─── agent studio types ───────────────────────────────────────────────────────
interface AgentStudioState {
  objective: string;
  executionMode: "auto_review" | "full_access";
  subagentProfile: string;
  connectorId: string;
  noteContent: string;
  thinkingEnabled: boolean;
  webSearchEnabled: boolean;
}

function createDefaultStudioState(): AgentStudioState {
  return {
    objective: "",
    executionMode: "auto_review",
    subagentProfile: "default",
    connectorId: "",
    noteContent: "",
    thinkingEnabled: true,
    webSearchEnabled: true,
  };
}

function nodeToneColor(tone: string, opacity = 1): string {
  switch (tone) {
    case "emerald": return `rgba(52,211,153,${opacity})`;
    case "cyan":    return `rgba(34,211,238,${opacity})`;
    case "amber":   return `rgba(251,191,36,${opacity})`;
    case "rose":    return `rgba(244,63,94,${opacity})`;
    case "violet":  return `rgba(167,139,250,${opacity})`;
    case "primary": return `rgba(52,211,153,${opacity})`;
    default:        return `rgba(148,163,184,${opacity})`;
  }
}

function nodeStatusClass(status: string): string {
  const s = status.toLowerCase();
  if (["running","active","connected","available","healthy"].includes(s)) return "emerald";
  if (["pending","paused","waiting","scheduled"].includes(s)) return "amber";
  if (["error","failed","degraded","stale","terminating"].includes(s)) return "rose";
  return "slate";
}

const USER_FRIENDLY_LABELS: Record<string, string> = {
  open_chat: "Mission Core",
  mission_router: "Mission Router",
  tool_executor: "Tool Executor",
  approval_gate: "Approval Gate",
  mission_output: "Output",
  memory_ledger: "Memory Ledger",
  proactive_workspace: "Proactive Workspace",
  connector_mesh: "Connector Mesh",
  system_internet: "Internet",
  system_llm: "LLM Runtime",
  system_search: "Web Search",
  system_daemon: "Proactive Daemon",
  mission_fleet: "Mission Fleet",
  subagent_swarm: "Subagent Swarm",
  task_queue: "Task Queue",
};

export default function ProactiveWorkspaceClient() {
  const [runtime, setRuntime] = useState<RuntimeInfo | null>(null);
  const [vitals, setVitals] = useState<VitalsInfo | null>(null);
  const [activities, setActivities] = useState<ProactiveActivity[]>([]);
  const [notifications, setNotifications] = useState<WorkspaceNotification[]>([]);
  const [connectors, setConnectors] = useState<ConnectorSummary[]>([]);
  const [connectorFleetSummary, setConnectorFleetSummary] = useState<ConnectorFleetSummary | null>(
    null,
  );
  const [memoryLifecycleSummary, setMemoryLifecycleSummary] =
    useState<MemoryLifecycleSummary | null>(null);
  const [tasks, setTasks] = useState<ProactiveTask[]>([]);
  const [taskSummaryApi, setTaskSummaryApi] = useState<ProactiveTaskSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedDraftId, setSelectedDraftId] = useState<string | null>(null);
  const [insertedDrafts, setInsertedDrafts] = useState<Record<string, InsertedDraft>>({});
  const [showRuleModal, setShowRuleModal] = useState(false);
  const [editingRuleId, setEditingRuleId] = useState<string | null>(null);
  const [ruleDraft, setRuleDraft] = useState<RuleEditorState>(createDefaultRuleState);
  const [savingRule, setSavingRule] = useState(false);
  const terminalRef = useRef<HTMLDivElement | null>(null);

  // ─── Agent Studio state ────────────────────────────────────────────────────

  const [agentStudioOpen, setAgentStudioOpen] = useState(false);

  const [studioForm, setStudioForm] = useState<AgentStudioState>(createDefaultStudioState);

  const [missionRunning, setMissionRunning] = useState(false);

  const [missionLog, setMissionLog] = useState<string[]>([]);

  const [missionError, setMissionError] = useState<string | null>(null);
  const missionLogRef = useRef<HTMLDivElement | null>(null);

  const [orchGraph, setOrchGraph] = useState<OrchestraGraph | null>(null);

  const [orchOverview, setOrchOverview] = useState<OrchestrationOverviewPayload | null>(null);

  const [orchLoading, setOrchLoading] = useState(false);

  const [selectedNode, setSelectedNode] = useState<OrchestraNode | null>(null);
  const orchAbortRef = useRef<AbortController | null>(null);
  // graph view state

  const [graphZoom, setGraphZoom] = useState(0.85);

  const [graphPan, setGraphPan] = useState({ x: 0, y: 0 });

  const [showLegend, setShowLegend] = useState(true);

  const [studioDropdown, setStudioDropdown] = useState<string | null>(null);
  const graphContainerRef = useRef<HTMLDivElement | null>(null);
  const isPanningRef = useRef(false);
  const panStartRef = useRef({ x: 0, y: 0, panX: 0, panY: 0 });

  const loadWorkspace = useCallback(async () => {
    try {
      const [
        runtimeRes,
        vitalsRes,
        activityRes,
        connectorsRes,
        connectorFleetRes,
        memoryLifecycleRes,
        tasksRes,
        taskSummaryRes,
        notificationsRes,
      ] = await Promise.all([
        fetchWithAuth("/deepspace/chats/runtime"),
        fetchWithAuth("/deepspace/chats/vitals"),
        fetchWithAuth("/deepspace/chats/activity?limit=100"),
        fetchWithAuth("/integrations/connectors"),
        fetchWithAuth("/integrations/connectors/summary"),
        fetchWithAuth("/deepspace/chats/memory/lifecycle"),
        fetchWithAuth("/deepspace/chats/tasks"),
        fetchWithAuth("/deepspace/chats/tasks/summary"),
        fetchWithAuth("/collections/notifications"),
      ]);

      if (runtimeRes.ok) setRuntime((await runtimeRes.json()) as RuntimeInfo);
      if (vitalsRes.ok) setVitals((await vitalsRes.json()) as VitalsInfo);
      if (activityRes.ok) {
        const payload = await activityRes.json();
        const items = (payload.items ?? payload) as ProactiveActivity[];
        setActivities(items);
      }
      if (connectorsRes.ok) {
        setConnectors((await connectorsRes.json()) as ConnectorSummary[]);
      }
      if (connectorFleetRes.ok) {
        setConnectorFleetSummary((await connectorFleetRes.json()) as ConnectorFleetSummary);
      }
      if (memoryLifecycleRes.ok) {
        setMemoryLifecycleSummary((await memoryLifecycleRes.json()) as MemoryLifecycleSummary);
      }
      if (tasksRes.ok) {
        setTasks((await tasksRes.json()) as ProactiveTask[]);
      }
      if (taskSummaryRes.ok) {
        setTaskSummaryApi((await taskSummaryRes.json()) as ProactiveTaskSummary);
      }
      if (notificationsRes.ok) {
        setNotifications((await notificationsRes.json()) as WorkspaceNotification[]);
      }
    } catch (error) {
      console.error("Failed to load proactive workspace", error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadWorkspace();
    const interval = window.setInterval(loadWorkspace, 20000);
    return () => window.clearInterval(interval);
  }, [loadWorkspace]);

  // ─── orchestration graph polling (only when studio is open) ───────────────

  const loadOrchGraph = useCallback(async (signal?: AbortSignal) => {
    try {
      const res = await fetchWithAuth("/deepspace/chats/orchestration", { signal } as RequestInit);
      if (res.ok) {
        const data = (await res.json()) as OrchestrationOverviewPayload;
        setOrchOverview(data);
        if (data.graph) setOrchGraph(data.graph);
      }
    } catch {
      // AbortError is expected on unmount/close
    }
  }, []);


  useEffect(() => {
    if (!agentStudioOpen) {
      setOrchGraph(null);
      setOrchOverview(null);
      return;
    }
    setOrchLoading(true);
    const ctrl = new AbortController();
    orchAbortRef.current = ctrl;
    void loadOrchGraph(ctrl.signal).finally(() => setOrchLoading(false));
    const interval = window.setInterval(() => void loadOrchGraph(ctrl.signal), 5000);
    return () => {
      ctrl.abort();
      window.clearInterval(interval);
    };
  }, [agentStudioOpen, loadOrchGraph]);

  // auto-scroll mission log

  useEffect(() => {
    const el = missionLogRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [missionLog]);

  useEffect(() => {
    if (!selectedDraftId && activities.length > 0) {
      const firstDraft = activities.find((activity) => Boolean(readDraftBody(activity)));
      if (firstDraft) {
        setSelectedDraftId(firstDraft.id);
      }
    }
  }, [activities, selectedDraftId]);

  useEffect(() => {
    const container = terminalRef.current;
    if (!container) return;
    container.scrollTop = container.scrollHeight;
  }, [activities]);

  const draftActivities = useMemo(
    () =>
      activities.filter((activity) => {
        const body = readDraftBody(activity);
        return activity.type === "draft" || activity.type === "notification" || Boolean(body);
      }),
    [activities],
  );

  const selectedDraft = useMemo(
    () =>
      draftActivities.find((activity) => activity.id === selectedDraftId) ??
      draftActivities[0] ??
      null,
    [draftActivities, selectedDraftId],
  );

  const activeConnectorCount = useMemo(
    () => connectors.filter((connector) => connector.status.toUpperCase() === "ACTIVE").length,
    [connectors],
  );

  const connectorFleetConnectorCount = connectorFleetSummary?.total_connectors ?? connectors.length;
  const connectorFleetActiveCount = connectorFleetSummary?.active_count ?? activeConnectorCount;
  const memoryCount = memoryLifecycleSummary?.memory_count ?? 0;
  const staleMemoryCount = memoryLifecycleSummary?.stale_count ?? 0;
  const memoryDecayScore = memoryLifecycleSummary?.average_decay_score ?? 0;

  const activeConnectors = useMemo(
    () => connectors.filter((connector) => connector.status.toUpperCase() === "ACTIVE"),
    [connectors],
  );

  const taskSummary = useMemo(
    () =>
      taskSummaryApi ?? {
        total: tasks.length,
        pending: tasks.filter((task) => task.status === "pending").length,
        in_progress: tasks.filter((task) => task.status === "in_progress").length,
        completed: tasks.filter((task) => task.status === "completed").length,
        recurring: tasks.filter((task) => task.is_recurring).length,
        enabled: tasks.filter((task) => task.enabled !== false).length,
        paused: tasks.filter((task) => task.enabled === false).length,
        due: tasks.filter((task) => {
          if (!task.is_recurring || !task.next_run_at || task.enabled === false) {
            return false;
          }
          return new Date(task.next_run_at).getTime() <= Date.now();
        }).length,
        approval_required: tasks.filter((task) => Boolean(task.automation_json?.requires_approval))
          .length,
        source_breakdown: tasks.reduce<Record<string, number>>((acc, task) => {
          const source = readTaskSource(task);
          if (!source) return acc;
          acc[source] = (acc[source] ?? 0) + 1;
          return acc;
        }, {}),
        recent_activity_count: 0,
        recent_error_count: 0,
        recent_cycle_count: 0,
        recent_cycle_failure_count: 0,
        gmail_scan_failure_count: 0,
        gmail_message_failure_count: 0,
        last_cycle_at: null,
        last_cycle_status: null,
      },
    [tasks, taskSummaryApi],
  );

  const draftQueueLabel = getDraftQueueLabel();
  const draftQueueDescription = getDraftQueueDescription();

  const unreadNotifications = useMemo(
    () => notifications.filter((item) => item.read_at === null),
    [notifications],
  );

  const recentNotifications = useMemo(() => notifications.slice(0, 6), [notifications]);

  const contextLimit =
    typeof runtime?.context_limit === "number" && runtime.context_limit > 0
      ? runtime.context_limit
      : null;
  const workspaceFootprintTokens = useMemo(() => {
    const text = [
      ...activities.map((activity) => activity.description),
      ...draftActivities.flatMap((activity) => [readDraftTitle(activity), readDraftBody(activity)]),
    ]
      .filter((value): value is string => Boolean(value))
      .join(" ");
    return text.trim() ? text.trim().split(/\s+/).length : 0;
  }, [activities, draftActivities]);
  const contextUsage =
    typeof contextLimit === "number" && contextLimit > 0
      ? Math.min(1, workspaceFootprintTokens / contextLimit)
      : 0;

  const handleInsertDraft = useCallback(async (activity: ProactiveActivity) => {
    const title = readDraftTitle(activity) ?? `${activity.source} draft`;
    const body = readDraftBody(activity) ?? activity.description;
    const contentHtml = `<article><h2>${title}</h2><p>${stripHtml(body)}</p></article>`;
    const response = (await fetchWithAuth("/deepspace/chats", {
      method: "POST",
      body: JSON.stringify({
        title,
        content_html: contentHtml,
      }),
    })) as Response;
    if (response.ok) {
      const created = (await response.json()) as {
        id: string;
        title: string;
        content_html?: string;
      };
      setInsertedDrafts((prev) => ({
        ...prev,
        [activity.id]: {
          id: created.id,
          title: created.title,
          content: contentHtml,
          created_at: new Date().toISOString(),
        },
      }));
      window.location.href = "/dashboard/deepspace";
    }
  }, []);

  const handleToggleTaskEnabled = useCallback(
    async (task: ProactiveTask) => {
      try {
        const response = await fetchWithAuth(`/deepspace/chats/tasks/${task.id}`, {
          method: "PATCH",
          body: JSON.stringify({
            enabled: !task.enabled,
          }),
        });
        if (response.ok) {
          await loadWorkspace();
        }
      } catch (error) {
        console.error("Failed to toggle proactive task", error);
      }
    },
    [loadWorkspace],
  );

  const handleRunTaskNow = useCallback(
    async (task: ProactiveTask) => {
      try {
        const response = (await fetchWithAuth(`/deepspace/chats/tasks/${task.id}/run-now`, {
          method: "POST",
        })) as Response;
        if (response.ok) {
          await loadWorkspace();
        }
      } catch (error) {
        console.error("Failed to run proactive task immediately", error);
      }
    },
    [loadWorkspace],
  );

  const openNewRule = useCallback(() => {
    setEditingRuleId(null);
    setRuleDraft(createDefaultRuleState());
    setShowRuleModal(true);
  }, []);

  const openEditRule = useCallback((task: ProactiveTask) => {
    setEditingRuleId(task.id);
    setRuleDraft(ruleFromTask(task));
    setShowRuleModal(true);
  }, []);

  const saveRule = useCallback(async () => {
    setSavingRule(true);
    try {
      const nextRunAt = fromDateTimeLocal(ruleDraft.next_run_at);
      const automation_json: Record<string, unknown> = {
        action_type: ruleDraft.action_type,
        schedule_type: ruleDraft.is_recurring ? ruleDraft.schedule_type : "manual",
        interval_minutes: ruleDraft.interval_minutes,
        prompt: ruleDraft.prompt || ruleDraft.active_form,
        note_content: ruleDraft.note_content || undefined,
        connector_id: ruleDraft.connector_id || undefined,
        requires_approval: ruleDraft.requires_approval,
        thinking_enabled: ruleDraft.thinking_enabled,
        web_search_enabled: ruleDraft.web_search_enabled,
        source: ruleDraft.source || "proactive",
        phase: ruleDraft.phase || "schedule",
      };
      const payload = {
        content: ruleDraft.content,
        activeForm: ruleDraft.active_form,
        status: ruleDraft.status,
        priority: ruleDraft.priority,
        thread_id: ruleDraft.thread_id || undefined,
        metadata_json: {
          source: ruleDraft.source || "proactive",
          phase: ruleDraft.phase || "schedule",
          connector_id: ruleDraft.connector_id || undefined,
        },
        automation_json,
        is_recurring: ruleDraft.is_recurring,
        enabled: ruleDraft.enabled,
        next_run_at: nextRunAt,
      };

      const response = (await fetchWithAuth(
        editingRuleId ? `/deepspace/chats/tasks/${editingRuleId}` : "/deepspace/chats/tasks",
        {
          method: editingRuleId ? "PATCH" : "POST",
          body: JSON.stringify(payload),
        },
      )) as Response;

      if (!response.ok) {
        throw new Error(`Failed to save proactive rule (${response.status})`);
      }

      setShowRuleModal(false);
      setEditingRuleId(null);
      setRuleDraft(createDefaultRuleState());
      await loadWorkspace();
    } catch (error) {
      console.error("Failed to save proactive rule", error);
    } finally {
      setSavingRule(false);
    }
  }, [editingRuleId, loadWorkspace, ruleDraft]);

  // ─── mission runner ────────────────────────────────────────────────────────
  const handleRunMission = useCallback(async () => {
    if (!studioForm.objective.trim()) return;
    setMissionRunning(true);
    setMissionLog([]);
    setMissionError(null);
    try {
      const res = await fetchWithAuth("/deepspace/chats/orchestrations/stream", {
        method: "POST",
        body: JSON.stringify({
          objective: studioForm.objective,
          note_content: studioForm.noteContent || undefined,
        }),
      });
      if (!res.ok || !res.body) {
        setMissionError(`Request failed (${res.status})`);
        return;
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop() ?? "";
        for (const part of parts) {
          const dataLine = part.split("\n").find((l) => l.startsWith("data:"));
          if (!dataLine) continue;
          try {
            const payload = JSON.parse(dataLine.slice(5).trim()) as Record<string, unknown>;
            const evt = String(payload.event ?? "");
            const data = payload.data as Record<string, unknown> | undefined;
            if (evt === "error") {
              setMissionError(String(data?.message ?? "Unknown error"));
              break;
            }
            const content = String(
              (data as Record<string, unknown>)?.content ??
              (data as Record<string, unknown>)?.message ??
              (data as Record<string, unknown>)?.summary ??
              ""
            );
            if (content.trim()) {
              setMissionLog((prev) => [...prev, content].slice(-200));
            }
          } catch {
            // non-JSON line, skip
          }
        }
      }
    } catch (err) {
      setMissionError(String(err));
    } finally {
      setMissionRunning(false);
      void loadOrchGraph();
    }
  }, [studioForm, loadOrchGraph]);

  // ─── drawer state ───────────────────────────────────────────────────────────

  const [leftDrawer, setLeftDrawer] = useState<string | null>(null);

  const [rightDrawer, setRightDrawer] = useState<string | null>(null);
  const globeCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const animFrameRef = useRef<number>(0);

  // ─── neoparticle 3D globe ─────────────────────────────────────────────────────

  useEffect(() => {
    const canvas = globeCanvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let w = 0;
    let h = 0;
    const BASE_RADIUS = 155;
    const FOV = 420;

    // smooth animation states
    let currentR = BASE_RADIUS;
    let currentSpeed = 0.006;
    let currentGlowR = 82;
    let scaleProgress = 0.08;
    let currentCy = 0;

    // independent rotation angles for layered shells
    let rotY0 = 0;
    let rotY1 = 0;
    let rotY2 = 0;

    interface Particle3D {
      theta: number; // polar
      phi: number;   // azimuthal
      layer: number; // 0=inner, 1=middle, 2=outer
      // projected 2D
      sx: number;
      sy: number;
      z3: number;    // depth for sorting
      scale: number;
      baseR: number; // dot radius
      alpha: number;
    }

    const particles: Particle3D[] = [];

    function resize() {
      if (!canvas) return;
      w = canvas.offsetWidth;
      h = canvas.offsetHeight;
      canvas.width = w * window.devicePixelRatio;
      canvas.height = h * window.devicePixelRatio;
      ctx!.scale(window.devicePixelRatio, window.devicePixelRatio);
    }

    function initParticles() {
      particles.length = 0;
      const goldenAngle = Math.PI * (1 + Math.sqrt(5));
      const TOTAL_COUNT = 450; // Increased count for layered shells

      for (let i = 0; i < TOTAL_COUNT; i++) {
        const theta = Math.acos(1 - (2 * (i + 0.5)) / TOTAL_COUNT);
        const phi = goldenAngle * i;

        let layer = 1; // default middle shell
        if (i < 120) {
          layer = 0; // inner shell
        } else if (i > 320) {
          layer = 2; // outer shell
        }

        particles.push({
          theta,
          phi,
          layer,
          sx: 0, sy: 0, z3: 0, scale: 1,
          baseR: layer === 0 ? 0.75 + Math.random() * 0.9 : layer === 1 ? 1.1 + Math.random() * 1.3 : 1.5 + Math.random() * 1.5,
          alpha: layer === 0 ? 0.35 + Math.random() * 0.45 : layer === 1 ? 0.5 + Math.random() * 0.45 : 0.2 + Math.random() * 0.3,
        });
      }
    }

    // Rotate a 3D point by rotX (X-axis) then rotY (Y-axis)
    function rotate3D(
      ox: number, oy: number, oz: number,
      rx: number, ry: number,
    ): [number, number, number] {
      // Y-axis rotation
      const cosY = Math.cos(ry), sinY = Math.sin(ry);
      const x1 =  ox * cosY + oz * sinY;
      const z1 = -ox * sinY + oz * cosY;
      // X-axis rotation
      const cosX = Math.cos(rx), sinX = Math.sin(rx);
      const y2 = oy * cosX - z1 * sinX;
      const z2 = oy * sinX + z1 * cosX;
      return [x1, y2, z2];
    }

    function getColor(state: string, alpha: number): string {
      switch (state) {
        case "listening": return `rgba(52,211,153,${alpha})`;
        case "thinking":  return `rgba(251,191,36,${alpha})`;
        case "speaking":  return `rgba(56,189,248,${alpha})`;
        default:          return `rgba(52,211,153,${alpha * 0.65})`;
      }
    }

    function draw() {
      if (!ctx || !canvas) return;
      const state = "idle" as string;
      ctx.clearRect(0, 0, w, h);

      const cx = w / 2;
      const targetCy = state === "idle" ? h / 2 : 110;
      if (currentCy === 0) currentCy = h / 2;
      currentCy += (targetCy - currentCy) * 0.08;
      const cy = currentCy;

      // target values per state
      const targetSpeed =
        state === "thinking"  ? 0.024 :
        state === "listening" ? 0.014 :
        state === "speaking"  ? 0.018 :
        0.006;

      const targetR =
        state === "speaking"  ? BASE_RADIUS * 1.25 :
        state === "listening" ? BASE_RADIUS * 0.78 :
        BASE_RADIUS;

      const targetGlowR = state === "speaking" ? 115 : state === "listening" ? 90 : 82;
      const targetScaleProgress = state === "idle" ? 0.08 : 1.0;

      // smooth interpolation (lerping)
      currentSpeed += (targetSpeed - currentSpeed) * 0.08;
      currentR += (targetR - currentR) * 0.08;
      currentGlowR += (targetGlowR - currentGlowR) * 0.08;
      scaleProgress += (targetScaleProgress - scaleProgress) * 0.08;

      // spin layers independently in counter directions
      rotY0 -= currentSpeed * 1.5; // inner spins backward fast
      rotY1 += currentSpeed;       // middle spins forward normal
      rotY2 -= currentSpeed * 0.4; // outer spins backward slow

      // distinct X-axis wobbles for organic layering
      const rotX0 = 0.28 + Math.sin(rotY1 * 0.27) * 0.18;
      const rotX1 = 0.15 + Math.cos(rotY1 * 0.18) * 0.12;
      const rotX2 = -0.22 + Math.sin(rotY1 * 0.32) * 0.22;

      // ── project all particles ──
      for (const p of particles) {
        // radius depends on layer multiplier and scale progress
        const layerScale = p.layer === 0 ? 0.62 : p.layer === 1 ? 1.0 : 1.38;
        const R_layer = currentR * layerScale * scaleProgress;

        const ox = R_layer * Math.sin(p.theta) * Math.cos(p.phi);
        const oy = R_layer * Math.cos(p.theta);
        const oz = R_layer * Math.sin(p.theta) * Math.sin(p.phi);

        let rx = rotX1, ry = rotY1;
        if (p.layer === 0) {
          rx = rotX0;
          ry = rotY0;
        } else if (p.layer === 2) {
          rx = rotX2;
          ry = rotY2;
        }

        const [x3, y3, z3] = rotate3D(ox, oy, oz, rx, ry);
        p.z3 = z3;

        // perspective divide (uniform depth offset to keep spheres perfectly round)
        const perspective = FOV / (FOV + z3 + 220);
        p.sx = cx + x3 * perspective;
        p.sy = cy + y3 * perspective;
        p.scale = perspective;
      }

      // sort back→front for depth layering
      particles.sort((a, b) => a.z3 - b.z3);

      // ── glow core ──
      const glowA = state === "idle" ? 0.07 : 0.16;
      const grd = ctx.createRadialGradient(cx - 8, cy - 8, 0, cx, cy, currentGlowR * scaleProgress);
      grd.addColorStop(0,   getColor(state, glowA * 5 * scaleProgress));
      grd.addColorStop(0.3, getColor(state, glowA * 2 * scaleProgress));
      grd.addColorStop(0.7, getColor(state, glowA * scaleProgress));
      grd.addColorStop(1,   "rgba(0,0,0,0)");
      ctx.beginPath();
      ctx.arc(cx, cy, currentGlowR * scaleProgress, 0, Math.PI * 2);
      ctx.fillStyle = grd;
      ctx.fill();

      // ── connection lines (crystalline structures within layers) ──
      for (let i = 0; i < particles.length; i++) {
        const p = particles[i];
        const layerScale = p.layer === 0 ? 0.62 : p.layer === 1 ? 1.0 : 1.38;
        const R_layer = currentR * layerScale * scaleProgress;
        const depthFactor = (p.z3 + R_layer) / (2 * R_layer);
        if (depthFactor < 0.28) continue; // skip back hemisphere

        // limit connection distance shrinks when sphere collapses
        const limitDist = (p.layer === 0 ? 30 : p.layer === 1 ? 42 : 55) * scaleProgress;

        for (let j = i + 1; j < particles.length; j++) {
          const q = particles[j];
          if (p.layer !== q.layer) continue; // only connect same shell layer

          const dx = p.sx - q.sx;
          const dy = p.sy - q.sy;
          const dist = Math.sqrt(dx * dx + dy * dy);

          if (dist < limitDist) {
            ctx.beginPath();
            ctx.moveTo(p.sx, p.sy);
            ctx.lineTo(q.sx, q.sy);
            ctx.strokeStyle = getColor(state, (1 - dist / limitDist) * depthFactor * 0.18);
            ctx.lineWidth = p.layer === 0 ? 0.38 : p.layer === 1 ? 0.48 : 0.58;
            ctx.stroke();
          }
        }
      }

      // ── particles (depth-scaled size + brightness) ──
      for (const p of particles) {
        const layerScale = p.layer === 0 ? 0.62 : p.layer === 1 ? 1.0 : 1.38;
        const R_layer = currentR * layerScale * scaleProgress;
        const depthFactor = (p.z3 + R_layer) / (2 * R_layer);
        const r = Math.max(0.3, p.baseR * p.scale * 2.2 * (0.5 + 0.5 * scaleProgress));
        const a = p.alpha * (0.15 + depthFactor * 0.85) * (0.2 + 0.8 * scaleProgress);
        ctx.beginPath();
        ctx.arc(p.sx, p.sy, r, 0, Math.PI * 2);
        ctx.fillStyle = getColor(state, a);
        ctx.fill();
      }

      animFrameRef.current = requestAnimationFrame(draw);
    }

    resize();
    initParticles();
    draw();

    const ro = new ResizeObserver(() => { resize(); });
    ro.observe(canvas);

    return () => {
      cancelAnimationFrame(animFrameRef.current);
      ro.disconnect();
    };

  }, []);

  function toggleLeft(id: string) {
    setLeftDrawer((prev) => (prev === id ? null : id));
  }
  function toggleRight(id: string) {
    setRightDrawer((prev) => (prev === id ? null : id));
  }



  function handleCenterClick() {
    setLeftDrawer(null);
    setRightDrawer(null);
  }

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <div className="relative">
            <div className="h-20 w-20 rounded-full border border-emerald-500/20 bg-emerald-500/5" />
            <RefreshCw
              size={22}
              className="absolute inset-0 m-auto animate-spin text-emerald-300"
            />
          </div>
          <p className="text-[11px] font-black tracking-[0.28em] text-emerald-300/70 uppercase">
            Initialising workspace
          </p>
        </div>
      </div>
    );
  }

  // ─── left drawer panels ──────────────────────────────────────────────────────
  const LeftTerminalPanel = (
    <div className="flex h-full flex-col">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <p className="text-[10px] font-black tracking-[0.24em] text-emerald-300/60 uppercase">
            Persistent Terminal
          </p>
          <h2 className="mt-1 text-xl font-black text-white">Heartbeat Log</h2>
        </div>
        <div className="flex items-center gap-2">
          <span className="h-2.5 w-2.5 rounded-full bg-red-500" />
          <span className="h-2.5 w-2.5 rounded-full bg-amber-500" />
          <span className="h-2.5 w-2.5 rounded-full bg-emerald-500" />
        </div>
      </div>
      <div
        ref={terminalRef}
        className="custom-scrollbar flex-1 overflow-y-auto rounded-2xl border border-white/5 bg-black/40 p-4 font-mono text-[12px] leading-7"
      >
        {activities.length === 0 ? (
          <p className="text-white/30">Waiting for background work…</p>
        ) : (
          <div className="space-y-3">
            {activities.map((activity) => {
              const tag = getStepLabel(activity.type);
              const meta = activity.metadata ?? {};
              const connector =
                typeof meta.connector_name === "string" ? meta.connector_name : null;
              return (
                <motion.div
                  key={activity.id}
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  className="grid grid-cols-[52px_72px_1fr] gap-3"
                >
                  <span className="text-white/30 tabular-nums">{formatTime(activity.created_at)}</span>
                  <span className="text-emerald-300">{tag}</span>
                  <span className="truncate text-white/75">
                    {activity.description}
                    {connector ? (
                      <span className="ml-2 text-[10px] tracking-widest text-white/30 uppercase">
                        {connector}
                      </span>
                    ) : null}
                  </span>
                </motion.div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );

  const LeftWorkLedgerPanel = (
    <div className="flex h-full flex-col">
      <div className="mb-5 flex items-center justify-between">
        <div>
          <p className="text-[10px] font-black tracking-[0.24em] text-emerald-300/60 uppercase">
            Work Ledger
          </p>
          <h2 className="mt-1 text-xl font-black text-white">Active Tasks</h2>
        </div>
        <span className="rounded-xl border border-emerald-500/20 bg-emerald-500/10 px-2.5 py-1 text-[10px] font-black text-emerald-300">
          {taskSummary.total} tracked
        </span>
      </div>
      <div className="grid grid-cols-2 gap-3">
        {[
          { label: "Pending", value: taskSummary.pending },
          { label: "In Progress", value: taskSummary.in_progress },
          { label: "Completed", value: taskSummary.completed },
          { label: "Sources", value: Object.keys(taskSummary.source_breakdown).length },
          { label: "Recurring", value: taskSummary.recurring },
          { label: "Paused", value: taskSummary.paused },
          { label: "Due Now", value: taskSummary.due },
          { label: "Cycles", value: taskSummary.recent_cycle_count },
        ].map(({ label, value }) => (
          <div
            key={label}
            className="rounded-2xl border border-white/5 bg-white/[0.03] p-3"
          >
            <p className="text-[10px] font-black tracking-[0.18em] text-white/35 uppercase">
              {label}
            </p>
            <p className="mt-2 text-2xl font-black text-white">{value}</p>
          </div>
        ))}
      </div>
    </div>
  );

  const LeftTasksPanel = (
    <div className="flex h-full flex-col">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <p className="text-[10px] font-black tracking-[0.24em] text-emerald-300/60 uppercase">
            Task Timeline
          </p>
          <h2 className="mt-1 text-xl font-black text-white">Proactive Tasks</h2>
        </div>
        <button
          type="button"
          onClick={openNewRule}
          className="flex items-center gap-1.5 rounded-xl border border-emerald-500/20 bg-emerald-500/10 px-3 py-1.5 text-[10px] font-black text-emerald-300 transition hover:bg-emerald-500/20"
        >
          <Sparkles size={11} />
          New Rule
        </button>
      </div>
      <div className="custom-scrollbar flex-1 space-y-3 overflow-y-auto pr-1">
        {tasks.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-white/10 p-6 text-center">
            <p className="text-sm text-white/40">No tasks yet. Create a rule to get started.</p>
          </div>
        ) : (
          tasks.map((task) => {
            const source = readTaskSource(task);
            const scheduleType = formatTaskSchedule(task);
            return (
              <div
                key={task.id}
                className="rounded-2xl border border-white/5 bg-white/[0.02] p-4"
              >
                <div className="flex items-start justify-between gap-3">
                  <p className="truncate text-sm font-black text-white">{task.content}</p>
                  <span
                    className={`shrink-0 rounded-lg border px-2 py-0.5 text-[9px] font-black ${taskStatusClass(task.status)}`}
                  >
                    {taskStatusLabel(task.status)}
                  </span>
                </div>
                <p className="mt-1 text-[11px] tracking-[0.16em] text-white/40 uppercase">
                  {source ? `${formatConnectorSource(source)} • ` : ""}
                  {task.activeForm}
                </p>
                <div className="mt-3 flex flex-wrap items-center gap-1.5">
                  {scheduleType ? (
                    <span className="rounded-lg border border-white/10 bg-black/20 px-2 py-0.5 text-[9px] font-semibold text-white/55">
                      {scheduleType}
                    </span>
                  ) : null}
                  {task.is_recurring ? (
                    <span className="rounded-lg border border-emerald-500/20 bg-emerald-500/10 px-2 py-0.5 text-[9px] font-semibold text-emerald-300">
                      Recurring
                    </span>
                  ) : null}
                </div>
                <div className="mt-3 flex gap-2 border-t border-white/5 pt-3">
                  <button
                    type="button"
                    onClick={() => void handleRunTaskNow(task)}
                    className="rounded-xl border border-cyan-500/20 bg-cyan-500/10 px-2.5 py-1 text-[10px] font-black text-cyan-300 transition hover:bg-cyan-500/20"
                  >
                    Run now
                  </button>
                  <button
                    type="button"
                    onClick={() => openEditRule(task)}
                    className="rounded-xl border border-white/10 bg-white/5 px-2.5 py-1 text-[10px] font-black text-white/60 transition hover:text-white"
                  >
                    Edit
                  </button>
                  {task.is_recurring ? (
                    <button
                      type="button"
                      onClick={() => void handleToggleTaskEnabled(task)}
                      className="rounded-xl border border-white/10 bg-white/5 px-2.5 py-1 text-[10px] font-black text-white/60 transition hover:text-white"
                    >
                      {task.enabled ? "Pause" : "Resume"}
                    </button>
                  ) : null}
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );

  const LeftNotificationsPanel = (
    <div className="flex h-full flex-col">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <p className="text-[10px] font-black tracking-[0.24em] text-emerald-300/60 uppercase">
            Notifications
          </p>
          <h2 className="mt-1 text-xl font-black text-white">Persisted Updates</h2>
        </div>
        <span className="rounded-xl border border-emerald-500/20 bg-emerald-500/10 px-2.5 py-1 text-[10px] font-black text-emerald-300">
          {unreadNotifications.length} unread
        </span>
      </div>
      <div className="custom-scrollbar flex-1 space-y-3 overflow-y-auto pr-1">
        {recentNotifications.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-white/10 p-6 text-center">
            <p className="text-sm text-white/40">No notifications yet.</p>
          </div>
        ) : (
          recentNotifications.map((item) => {
            const unread = item.read_at === null;
            return (
              <div
                key={item.id}
                className={`rounded-2xl border p-3 ${
                  unread ? "border-emerald-500/25 bg-emerald-500/10" : "border-white/5 bg-white/[0.02]"
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <p className="truncate text-sm font-black text-white">{item.collection_name}</p>
                  <span className="text-[10px] tabular-nums text-white/35">
                    {formatTime(item.created_at)}
                  </span>
                </div>
                <p className="mt-0.5 text-[11px] tracking-widest text-white/40 uppercase">
                  {item.event_type.replace(/_/g, " ")}
                </p>
                <p className="mt-2 text-[12px] leading-5 text-white/65">{item.message}</p>
              </div>
            );
          })
        )}
      </div>
    </div>
  );

  // ─── right drawer panels ─────────────────────────────────────────────────────
  const RightTimelinePanel = (
    <div className="flex h-full flex-col">
      <div className="mb-4">
        <p className="text-[10px] font-black tracking-[0.24em] text-emerald-300/60 uppercase">
          Timeline
        </p>
        <h2 className="mt-1 text-xl font-black text-white">Task Activity</h2>
      </div>
      <div className="mb-3 flex flex-wrap gap-2">
        <span className="rounded-xl border border-white/10 bg-white/[0.03] px-2.5 py-1 text-[10px] font-semibold text-white/55">
          {taskSummary.gmail_scan_failure_count} Gmail scan failures
        </span>
        <span className="rounded-xl border border-white/10 bg-white/[0.03] px-2.5 py-1 text-[10px] font-semibold text-white/55">
          {taskSummary.last_cycle_status ?? "unknown"} cycle
        </span>
        <span className="rounded-xl border border-white/10 bg-white/[0.03] px-2.5 py-1 text-[10px] font-semibold text-white/55">
          {activeConnectorCount}/{connectors.length} connectors active
        </span>
      </div>
      <div className="custom-scrollbar flex-1 space-y-3 overflow-y-auto pr-1">
        {tasks.length === 0 ? (
          <p className="text-sm text-white/35">No task timeline data.</p>
        ) : (
          tasks.map((task) => (
            <div
              key={task.id}
              className="flex items-center gap-4 rounded-2xl border border-white/5 bg-white/[0.02] p-3"
            >
              <span
                className={`h-2 w-2 shrink-0 rounded-full ${
                  task.status === "completed"
                    ? "bg-emerald-400"
                    : task.status === "in_progress"
                      ? "bg-cyan-400"
                      : "bg-amber-400"
                }`}
              />
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold text-white">{task.content}</p>
                {task.last_run_at ? (
                  <p className="text-[10px] text-white/35">
                    {new Date(task.last_run_at).toLocaleString([], {
                      month: "short",
                      day: "numeric",
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </p>
                ) : (
                  <p className="text-[10px] text-white/25">Not run yet</p>
                )}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );

  const RightDraftQueuePanel = (
    <div className="flex h-full flex-col">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <p className="text-[10px] font-black tracking-[0.24em] text-emerald-300/60 uppercase">
            Draft Queue
          </p>
          <h2 className="mt-1 text-xl font-black text-white">{draftQueueLabel}</h2>
          <p className="mt-1 text-[11px] text-white/40">{draftQueueDescription}</p>
        </div>
        <span className="rounded-xl border border-emerald-500/20 bg-emerald-500/10 px-2.5 py-1 text-[10px] font-black text-emerald-300">
          {draftActivities.length} ready
        </span>
      </div>
      <div className="custom-scrollbar flex-1 space-y-3 overflow-y-auto pr-1">
        {draftActivities.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-white/10 p-6 text-center">
            <p className="text-sm text-white/40">No drafts yet.</p>
          </div>
        ) : (
          draftActivities.map((activity) => {
            const isSelected = selectedDraft?.id === activity.id;
            const inserted = insertedDrafts[activity.id];
            return (
              <button
                type="button"
                key={activity.id}
                onClick={() => setSelectedDraftId(activity.id)}
                className={`w-full rounded-2xl border p-4 text-left transition ${
                  isSelected
                    ? "border-emerald-500/30 bg-emerald-500/10"
                    : "border-white/5 bg-white/[0.02] hover:border-emerald-500/20"
                }`}
              >
                <div className="flex items-center justify-between gap-3">
                  <p className="truncate text-sm font-black text-white">
                    {readDraftTitle(activity) ?? activity.description}
                  </p>
                  <span className="text-[10px] tabular-nums text-white/35">
                    {formatTime(activity.created_at)}
                  </span>
                </div>
                {readDraftBody(activity) ? (
                  <p className="mt-2 line-clamp-2 text-[12px] leading-5 text-white/55">
                    {readDraftBody(activity)}
                  </p>
                ) : null}
                <div className="mt-3 flex gap-2">
                  {inserted ? (
                    <span className="flex items-center gap-1 rounded-lg border border-emerald-500/20 bg-emerald-500/10 px-2 py-0.5 text-[9px] font-black text-emerald-300">
                      <Check size={9} />
                      Inserted
                    </span>
                  ) : null}
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      void handleInsertDraft(activity);
                    }}
                    className="flex items-center gap-1 rounded-lg border border-emerald-500/20 bg-emerald-500/10 px-2 py-0.5 text-[9px] font-black text-emerald-300 transition hover:bg-emerald-500/20"
                  >
                    <ExternalLink size={9} />
                    Insert to Notes
                  </button>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      const content = readDraftBody(activity) ?? activity.description;
                      void navigator.clipboard.writeText(content);
                    }}
                    className="flex items-center gap-1 rounded-lg border border-white/10 bg-white/5 px-2 py-0.5 text-[9px] font-black text-white/55 transition hover:text-white"
                  >
                    <ClipboardCopy size={9} />
                    Copy
                  </button>
                </div>
              </button>
            );
          })
        )}
      </div>
    </div>
  );

  const RightConnectorFleetPanel = (
    <div className="flex h-full flex-col">
      <div className="mb-4">
        <p className="text-[10px] font-black tracking-[0.24em] text-emerald-300/60 uppercase">
          Connector Fleet
        </p>
        <h2 className="mt-1 text-xl font-black text-white">System Sources</h2>
      </div>
      <div className="grid grid-cols-2 gap-3">
        {[
          { label: "Total", value: connectorFleetConnectorCount },
          { label: "Active", value: connectorFleetActiveCount },
          { label: "Healthy", value: connectorFleetSummary?.health_status_breakdown?.healthy ?? 0 },
          { label: "Stale", value: connectorFleetSummary?.health_status_breakdown?.stale ?? 0 },
          { label: "Retryable", value: connectorFleetSummary?.retryable_count ?? 0 },
          { label: "Due Syncs", value: connectorFleetSummary?.due_sync_count ?? 0 },
          { label: "Memories", value: memoryCount },
          {
            label: "Vitals",
            value: vitals?.llm === "connected" ? "OK" : "WAIT",
          },
        ].map(({ label, value }) => (
          <div
            key={label}
            className="rounded-2xl border border-white/5 bg-white/[0.03] p-3"
          >
            <p className="text-[10px] font-black tracking-[0.18em] text-white/35 uppercase">
              {label}
            </p>
            <p
              className={`mt-2 text-xl font-black ${
                value === "OK" ? "text-emerald-300" : value === "WAIT" ? "text-amber-300" : "text-white"
              }`}
            >
              {value}
            </p>
          </div>
        ))}
      </div>
      <div className="mt-4 flex-1 overflow-y-auto">
        <p className="mb-2 text-[10px] font-black tracking-widest text-white/35 uppercase">
          Connector Status
        </p>
        <div className="space-y-2">
          {connectors.slice(0, 12).map((c) => (
            <div
              key={c.id}
              className="flex items-center justify-between rounded-xl border border-white/5 bg-white/[0.02] px-3 py-2"
            >
              <span className="truncate text-sm text-white/75">{c.name}</span>
              <span
                className={`ml-2 shrink-0 rounded-lg px-2 py-0.5 text-[9px] font-black ${
                  c.status.toUpperCase() === "ACTIVE"
                    ? "bg-emerald-500/10 text-emerald-300"
                    : "bg-white/5 text-white/40"
                }`}
              >
                {c.status.toUpperCase()}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );

  const RightAgentQueuePanel = (
    <div className="flex h-full flex-col">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <p className="text-[10px] font-black tracking-[0.24em] text-emerald-300/60 uppercase">
            Agent Queue
          </p>
          <h2 className="mt-1 text-xl font-black text-white">Rule Engine</h2>
        </div>
        <button
          type="button"
          onClick={openNewRule}
          className="flex items-center gap-1.5 rounded-xl border border-emerald-500/20 bg-emerald-500/10 px-3 py-1.5 text-[10px] font-black text-emerald-300 transition hover:bg-emerald-500/20"
        >
          <Sparkles size={11} />
          New Rule
        </button>
      </div>
      <div className="mb-3 grid grid-cols-3 gap-2">
        <div className="rounded-xl border border-white/5 bg-white/[0.03] p-2.5 text-center">
          <p className="text-[9px] font-black tracking-widest text-white/35 uppercase">Pending</p>
          <p className="mt-1 text-lg font-black text-white">{taskSummary.pending}</p>
        </div>
        <div className="rounded-xl border border-white/5 bg-white/[0.03] p-2.5 text-center">
          <p className="text-[9px] font-black tracking-widest text-white/35 uppercase">Running</p>
          <p className="mt-1 text-lg font-black text-cyan-300">{taskSummary.in_progress}</p>
        </div>
        <div className="rounded-xl border border-white/5 bg-white/[0.03] p-2.5 text-center">
          <p className="text-[9px] font-black tracking-widest text-white/35 uppercase">Done</p>
          <p className="mt-1 text-lg font-black text-emerald-300">{taskSummary.completed}</p>
        </div>
      </div>
      <div className="custom-scrollbar flex-1 space-y-2 overflow-y-auto pr-1">
        {tasks.length === 0 ? (
          <p className="text-sm text-white/35">No agents queued.</p>
        ) : (
          tasks.map((task) => (
            <div
              key={task.id}
              className="flex items-center justify-between gap-3 rounded-xl border border-white/5 bg-white/[0.02] px-3 py-2.5"
            >
              <div className="min-w-0">
                <p className="truncate text-[12px] font-semibold text-white/85">{task.content}</p>
                <p className="text-[10px] text-white/35">
                  Priority {task.priority} •{" "}
                  {task.is_recurring ? "Recurring" : "One-time"}
                </p>
              </div>
              <div className="flex shrink-0 gap-1.5">
                <button
                  type="button"
                  onClick={() => void handleRunTaskNow(task)}
                  className="rounded-lg border border-emerald-500/20 bg-emerald-500/10 px-2 py-1 text-[9px] font-black text-emerald-300 transition hover:bg-emerald-500/20"
                >
                  Run
                </button>
                <button
                  type="button"
                  onClick={() => openEditRule(task)}
                  className="rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-[9px] font-black text-white/55"
                >
                  Edit
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );

  // ─── left & right button definitions ────────────────────────────────────────
  const leftButtons = [
    { id: "terminal", icon: <Terminal size={17} />, label: "Terminal", panel: LeftTerminalPanel },
    { id: "ledger", icon: <BarChart2 size={17} />, label: "Work Ledger", panel: LeftWorkLedgerPanel },
    { id: "tasks", icon: <ListChecks size={17} />, label: "Tasks", panel: LeftTasksPanel },
    { id: "notifications", icon: <Bell size={17} />, label: "Notifications", panel: LeftNotificationsPanel },
  ];
  const rightButtons = [
    { id: "timeline", icon: <Clock size={17} />, label: "Timeline", panel: RightTimelinePanel },
    { id: "drafts", icon: <Inbox size={17} />, label: "Draft Queue", panel: RightDraftQueuePanel },
    { id: "fleet", icon: <GitBranch size={17} />, label: "Fleet", panel: RightConnectorFleetPanel },
    { id: "queue", icon: <Cpu size={17} />, label: "Agent Queue", panel: RightAgentQueuePanel },
  ];

  const activeLeftPanel = leftButtons.find((b) => b.id === leftDrawer);
  const activeRightPanel = rightButtons.find((b) => b.id === rightDrawer);

  return (
    <div
      style={{ position: "relative", width: "100%", height: "100%", overflow: "hidden" }}
    >
      {/* ── top bar ─────────────────────────────────────────────────────────── */}
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          right: 0,
          zIndex: 30,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "14px 20px",
          background: "transparent",
          pointerEvents: "none",
        }}
      >
        <Link
          href="/dashboard/connectors"
          style={{ pointerEvents: "auto" }}
          className="flex items-center gap-1.5 rounded-xl border border-white/10 bg-white/5 px-3 py-1.5 text-[11px] font-black text-white/60 transition hover:text-emerald-300"
        >
          <ArrowLeft size={12} />
          Connectors
        </Link>
        <div style={{ pointerEvents: "auto" }} className="flex items-center gap-2">
          <button
            id="proactive-agent-studio-btn"
            type="button"
            onClick={() => setAgentStudioOpen((v) => !v)}
            className={`flex items-center gap-1.5 rounded-xl border px-3 py-1.5 text-[10px] font-black transition ${
              agentStudioOpen
                ? "border-emerald-400/40 bg-emerald-500/15 text-emerald-300 shadow-[0_0_18px_rgba(52,211,153,0.25)]"
                : "border-white/10 bg-white/5 text-white/60 hover:border-emerald-500/30 hover:text-emerald-300"
            }`}
          >
            <BrainCircuit size={11} />
            Agent Studio
          </button>
          <span className="flex items-center gap-1.5 rounded-xl border border-emerald-500/20 bg-emerald-500/10 px-3 py-1.5 text-[10px] font-black text-emerald-300">
            <ShieldCheck size={11} />
            Live Heartbeat
          </span>
          <span className="flex items-center gap-1.5 rounded-xl border border-white/10 bg-white/5 px-3 py-1.5 text-[10px] font-black text-white/50">
            <Cpu size={11} />
            {runtime?.provider_type ?? "provider"} • {runtime?.model_name ?? "auto"}
          </span>
        </div>
      </div>

      {/* ── center canvas (clickable to close drawers) ───────────────────────── */}
      <div
        onClick={handleCenterClick}
        style={{
          position: "absolute",
          inset: 0,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          cursor: leftDrawer ?? rightDrawer ? "pointer" : "default",
        }}
      >
        {/* neoparticle canvas */}
        <canvas
          ref={globeCanvasRef}
          style={{ width: "100%", height: "100%", position: "absolute", inset: 0 }}
          onClick={(e) => e.stopPropagation()}
        />

        {/* system status pills overlay */}
        <div
          style={{
            position: "absolute",
            top: "50%",
            transform: "translateY(-50%)",
            zIndex: 5,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 12,
          }}
          onClick={(e) => e.stopPropagation()}
        >
          {/* system status pills */}
          <div className="flex items-center gap-2">
            <span className="rounded-xl border border-white/10 bg-black/40 px-3 py-1 text-[10px] font-semibold text-white/35">
              {memoryCount} memories
            </span>
            <span className="rounded-xl border border-white/10 bg-black/40 px-3 py-1 text-[10px] font-semibold text-white/35">
              {connectorFleetActiveCount} connectors live
            </span>
            <span className="rounded-xl border border-white/10 bg-black/40 px-3 py-1 text-[10px] font-semibold text-white/35">
              {connectorFleetActiveCount}/{connectorFleetConnectorCount} active
            </span>
            <span className="rounded-xl border border-white/10 bg-black/40 px-3 py-1 text-[10px] font-semibold text-white/35">
              {connectorFleetSummary?.retryable_count ?? 0} retryable
            </span>
            <span className="rounded-xl border border-white/10 bg-black/40 px-3 py-1 text-[10px] font-semibold text-white/35">
              {connectorFleetSummary?.due_sync_count ?? 0} due syncs
            </span>
            <span className="rounded-xl border border-white/10 bg-black/40 px-3 py-1 text-[10px] font-semibold text-white/35">
              {connectorFleetSummary?.retryable_count ?? 0} retry queue
            </span>
            <span className="rounded-xl border border-white/10 bg-black/40 px-3 py-1 text-[10px] font-semibold text-white/35">
              {connectorFleetSummary?.health_status_breakdown?.healthy ?? 0} healthy
            </span>
            <span className="rounded-xl border border-white/10 bg-black/40 px-3 py-1 text-[10px] font-semibold text-white/35">
              {taskSummary.gmail_scan_failure_count} Gmail scan failures
            </span>
            <span className="rounded-xl border border-white/10 bg-black/40 px-3 py-1 text-[10px] font-semibold text-white/35">
              {taskSummary.last_cycle_status ?? "unknown"} cycle
            </span>
            <span className="rounded-xl border border-white/10 bg-black/40 px-3 py-1 text-[10px] font-semibold text-white/35">
              {memoryCount} memories
            </span>
            <span className="rounded-xl border border-white/10 bg-black/40 px-3 py-1 text-[10px] font-semibold text-white/35">
              {staleMemoryCount} stale
            </span>
            <span className="rounded-xl border border-white/10 bg-black/40 px-3 py-1 text-[10px] font-semibold text-white/35">
              Proactive Cycles
            </span>
            <span
              className={`rounded-xl border px-3 py-1 text-[10px] font-semibold ${
                vitals?.llm === "connected"
                  ? "border-emerald-500/25 bg-emerald-500/10 text-emerald-300"
                  : "border-amber-500/25 bg-amber-500/10 text-amber-300"
              }`}
            >
              LLM {vitals?.llm ?? "checking…"}
            </span>
          </div>
        </div>

      </div>

      {/* ── left floating buttons ────────────────────────────────────────────── */}
      <div
        style={{
          position: "absolute",
          left: leftDrawer ? 394 : 14,
          top: "50%",
          transform: "translateY(-50%)",
          zIndex: 25,
          display: "flex",
          flexDirection: "column",
          gap: 10,
          transition: "left 0.35s cubic-bezier(0.32,0,0.67,0)",
        }}
      >
        {leftButtons.map((btn) => (
          <button
            key={btn.id}
            id={`proactive-left-btn-${btn.id}`}
            type="button"
            onClick={() => toggleLeft(btn.id)}
            className={`group relative flex h-11 w-11 flex-col items-center justify-center rounded-2xl border transition-all duration-200 ${
              leftDrawer === btn.id
                ? "border-emerald-500/40 bg-emerald-500/15 text-emerald-300 shadow-[0_0_20px_rgba(52,211,153,0.2)]"
                : "border-white/10 bg-white/[0.04] text-white/50 hover:border-emerald-500/30 hover:bg-emerald-500/10 hover:text-emerald-300"
            }`}
          >
            {btn.icon}
            {/* custom tooltip — slides right */}
            <span className="pointer-events-none absolute left-[52px] top-1/2 -translate-y-1/2 whitespace-nowrap rounded-xl border border-emerald-500/25 bg-black/80 px-2.5 py-1 text-[10px] font-black tracking-[0.18em] text-emerald-300 opacity-0 shadow-[0_4px_20px_rgba(0,0,0,0.5)] backdrop-blur-md transition-all duration-150 group-hover:opacity-100 uppercase">
              {btn.label}
            </span>
          </button>
        ))}
      </div>

      {/* ── right floating buttons ───────────────────────────────────────────── */}
      <div
        style={{
          position: "absolute",
          right: rightDrawer ? 394 : 14,
          top: "50%",
          transform: "translateY(-50%)",
          zIndex: 25,
          display: "flex",
          flexDirection: "column",
          gap: 10,
          transition: "right 0.35s cubic-bezier(0.32,0,0.67,0)",
        }}
      >
        {rightButtons.map((btn) => (
          <button
            key={btn.id}
            id={`proactive-right-btn-${btn.id}`}
            type="button"
            onClick={() => toggleRight(btn.id)}
            className={`group relative flex h-11 w-11 flex-col items-center justify-center rounded-2xl border transition-all duration-200 ${
              rightDrawer === btn.id
                ? "border-emerald-500/40 bg-emerald-500/15 text-emerald-300 shadow-[0_0_20px_rgba(52,211,153,0.2)]"
                : "border-white/10 bg-white/[0.04] text-white/50 hover:border-emerald-500/30 hover:bg-emerald-500/10 hover:text-emerald-300"
            }`}
          >
            {btn.icon}
            {/* custom tooltip — slides left */}
            <span className="pointer-events-none absolute right-[52px] top-1/2 -translate-y-1/2 whitespace-nowrap rounded-xl border border-emerald-500/25 bg-black/80 px-2.5 py-1 text-[10px] font-black tracking-[0.18em] text-emerald-300 opacity-0 shadow-[0_4px_20px_rgba(0,0,0,0.5)] backdrop-blur-md transition-all duration-150 group-hover:opacity-100 uppercase">
              {btn.label}
            </span>
          </button>
        ))}
      </div>

      {/* ── left drawer (slides right) ───────────────────────────────────────── */}
      <AnimatePresence>
        {activeLeftPanel ? (
          <motion.div
            key={activeLeftPanel.id}
            initial={{ x: "-100%", opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: "-100%", opacity: 0 }}
            transition={{ type: "spring", stiffness: 320, damping: 32 }}
            style={{
              position: "absolute",
              top: 0,
              bottom: 0,
              left: 0,
              width: 380,
              zIndex: 35,
              background: "transparent",
              backdropFilter: "blur(24px)",
              borderRight: "1px solid rgba(255,255,255,0.08)",
              borderTop: "1px solid rgba(255,255,255,0.08)",
              borderBottom: "1px solid rgba(255,255,255,0.08)",
              borderRadius: "0 24px 24px 0",
              display: "flex",
              flexDirection: "column",
              padding: "64px 20px 20px",
            }}
          >
            <button
              type="button"
              aria-label="Close drawer"
              onClick={() => setLeftDrawer(null)}
              style={{ position: "absolute", top: 16, right: 16 }}
              className="flex h-7 w-7 items-center justify-center rounded-xl border border-white/10 bg-white/5 text-white/40 transition hover:text-white"
            >
              <X size={13} />
            </button>
            <div className="flex-1 overflow-hidden">{activeLeftPanel.panel}</div>
          </motion.div>
        ) : null}
      </AnimatePresence>

      {/* ── right drawer (slides left) ───────────────────────────────────────── */}
      <AnimatePresence>
        {activeRightPanel ? (
          <motion.div
            key={activeRightPanel.id}
            initial={{ x: "100%", opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: "100%", opacity: 0 }}
            transition={{ type: "spring", stiffness: 320, damping: 32 }}
            style={{
              position: "absolute",
              top: 0,
              bottom: 0,
              right: 0,
              width: 380,
              zIndex: 35,
              background: "transparent",
              backdropFilter: "blur(24px)",
              borderLeft: "1px solid rgba(255,255,255,0.08)",
              borderTop: "1px solid rgba(255,255,255,0.08)",
              borderBottom: "1px solid rgba(255,255,255,0.08)",
              borderRadius: "24px 0 0 24px",
              display: "flex",
              flexDirection: "column",
              padding: "64px 20px 20px",
            }}
          >
            <button
              type="button"
              aria-label="Close drawer"
              onClick={() => setRightDrawer(null)}
              style={{ position: "absolute", top: 16, left: 16 }}
              className="flex h-7 w-7 items-center justify-center rounded-xl border border-white/10 bg-white/5 text-white/40 transition hover:text-white"
            >
              <X size={13} />
            </button>
            <div className="flex-1 overflow-hidden">{activeRightPanel.panel}</div>
          </motion.div>
        ) : null}
      </AnimatePresence>

      {/* ── rule modal ───────────────────────────────────────────────────────── */}
      <AnimatePresence>
        {showRuleModal ? (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-[120] flex items-center justify-center p-4"
          >
            <button
              type="button"
              aria-label="Close rule editor"
              className="absolute inset-0 bg-black/70 backdrop-blur-sm"
              onClick={() => setShowRuleModal(false)}
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.96, y: 18 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.96, y: 18 }}
              className="theme-panel border-glass-border/60 relative z-[121] w-full max-w-5xl overflow-hidden rounded-[2rem] p-6 shadow-[0_40px_120px_rgba(0,0,0,0.55)]"
            >
              <div className="mb-5 flex items-start justify-between gap-4">
                <div>
                  <p className="text-foreground/40 text-[10px] font-black tracking-[0.24em] uppercase">
                    Proactive Rule Editor
                  </p>
                  <h3 className="text-foreground mt-2 text-3xl font-black">
                    {editingRuleId ? "Edit recurring rule" : "Create recurring rule"}
                  </h3>
                  <p className="text-foreground/55 mt-2 max-w-2xl text-sm leading-6">
                    Define what AverQel should watch, when it should run, which connector it
                    should use, and whether the action needs approval before it executes.
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setShowRuleModal(false)}
                    className="theme-pill text-foreground/60 hover:text-foreground border-white/10 bg-white/5"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    disabled={savingRule}
                    onClick={() => void saveRule()}
                    className="theme-pill border-emerald-500/20 bg-emerald-500/10 text-emerald-300 hover:bg-emerald-500/15 disabled:opacity-50"
                  >
                    {savingRule ? "Saving..." : "Save Rule"}
                  </button>
                </div>
              </div>

              <div className="custom-scrollbar max-h-[70vh] overflow-y-auto pr-1">
                <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
                  <label className="space-y-2">
                    <span className="text-foreground/40 text-[10px] font-black tracking-[0.22em] uppercase">
                      Rule Name
                    </span>
                    <input
                      value={ruleDraft.content}
                      onChange={(event) =>
                        setRuleDraft((current) => ({
                          ...current,
                          content: event.target.value,
                          active_form: current.active_form || event.target.value,
                        }))
                      }
                      placeholder="Daily Gmail summary"
                      className="focus:ring-primary/50 w-full rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3 text-sm transition outline-none focus:ring-2"
                    />
                  </label>
                  <label className="space-y-2">
                    <span className="text-foreground/40 text-[10px] font-black tracking-[0.22em] uppercase">
                      Visible Draft Label
                    </span>
                    <input
                      value={ruleDraft.active_form}
                      onChange={(event) =>
                        setRuleDraft((current) => ({
                          ...current,
                          active_form: event.target.value,
                        }))
                      }
                      placeholder="Review daily Gmail summary"
                      className="focus:ring-primary/50 w-full rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3 text-sm transition outline-none focus:ring-2"
                    />
                  </label>
                  <label className="space-y-2">
                    <span className="text-foreground/40 text-[10px] font-black tracking-[0.22em] uppercase">
                      Action Type
                    </span>
                    <select
                      value={ruleDraft.action_type}
                      onChange={(event) =>
                        setRuleDraft((current) => ({
                          ...current,
                          action_type: event.target.value as RuleActionType,
                        }))
                      }
                      className="focus:ring-primary/50 w-full rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3 text-sm transition outline-none focus:ring-2"
                    >
                      <option value="agent_prompt">Agent Prompt</option>
                      <option value="connector_sync">Connector Sync</option>
                    </select>
                  </label>
                  <label className="space-y-2">
                    <span className="text-foreground/40 text-[10px] font-black tracking-[0.22em] uppercase">
                      Source Connector
                    </span>
                    <select
                      value={ruleDraft.connector_id}
                      onChange={(event) =>
                        setRuleDraft((current) => ({
                          ...current,
                          connector_id: event.target.value,
                        }))
                      }
                      className="focus:ring-primary/50 w-full rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3 text-sm transition outline-none focus:ring-2"
                    >
                      <option value="">No connector</option>
                      {activeConnectors.map((connector) => (
                        <option key={connector.id} value={connector.id}>
                          {connector.name}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="space-y-2">
                    <span className="text-foreground/40 text-[10px] font-black tracking-[0.22em] uppercase">
                      Schedule
                    </span>
                    <select
                      value={ruleDraft.schedule_type}
                      onChange={(event) =>
                        setRuleDraft((current) => ({
                          ...current,
                          schedule_type: event.target.value as RuleScheduleType,
                          is_recurring: event.target.value !== "manual",
                        }))
                      }
                      className="focus:ring-primary/50 w-full rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3 text-sm transition outline-none focus:ring-2"
                    >
                      <option value="manual">One-time</option>
                      <option value="daily">Daily</option>
                      <option value="weekly">Weekly</option>
                      <option value="interval">Every N minutes</option>
                    </select>
                  </label>
                  <label className="space-y-2">
                    <span className="text-foreground/40 text-[10px] font-black tracking-[0.22em] uppercase">
                      Next Run
                    </span>
                    <input
                      type="datetime-local"
                      value={ruleDraft.next_run_at}
                      onChange={(event) =>
                        setRuleDraft((current) => ({
                          ...current,
                          next_run_at: event.target.value,
                        }))
                      }
                      className="focus:ring-primary/50 w-full rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3 text-sm transition outline-none focus:ring-2"
                    />
                  </label>
                  <label className="space-y-2">
                    <span className="text-foreground/40 text-[10px] font-black tracking-[0.22em] uppercase">
                      Interval Minutes
                    </span>
                    <input
                      type="number"
                      min={1}
                      value={ruleDraft.interval_minutes}
                      onChange={(event) =>
                        setRuleDraft((current) => ({
                          ...current,
                          interval_minutes: Math.max(1, Number(event.target.value) || 1),
                        }))
                      }
                      className="focus:ring-primary/50 w-full rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3 text-sm transition outline-none focus:ring-2"
                    />
                  </label>
                  <label className="space-y-2 xl:col-span-2">
                    <span className="text-foreground/40 text-[10px] font-black tracking-[0.22em] uppercase">
                      Prompt / Instruction
                    </span>
                    <textarea
                      value={ruleDraft.prompt}
                      onChange={(event) =>
                        setRuleDraft((current) => ({
                          ...current,
                          prompt: event.target.value,
                        }))
                      }
                      rows={4}
                      placeholder="Summarize Gmail every morning and draft replies for urgent mail."
                      className="focus:ring-primary/50 w-full rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3 text-sm transition outline-none focus:ring-2"
                    />
                  </label>
                  <label className="space-y-2 xl:col-span-2">
                    <span className="text-foreground/40 text-[10px] font-black tracking-[0.22em] uppercase">
                      Notes / Workspace Context
                    </span>
                    <textarea
                      value={ruleDraft.note_content}
                      onChange={(event) =>
                        setRuleDraft((current) => ({
                          ...current,
                          note_content: event.target.value,
                        }))
                      }
                      rows={3}
                      placeholder="Optional context to attach when the rule runs."
                      className="focus:ring-primary/50 w-full rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3 text-sm transition outline-none focus:ring-2"
                    />
                  </label>

                  <div className="grid grid-cols-1 gap-4 xl:col-span-2 xl:grid-cols-4">
                    <label className="flex items-center gap-3 rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3">
                      <input
                        type="checkbox"
                        checked={ruleDraft.is_recurring}
                        onChange={(event) =>
                          setRuleDraft((current) => ({
                            ...current,
                            is_recurring: event.target.checked,
                          }))
                        }
                      />
                      <span className="text-foreground/80 text-sm font-semibold">Recurring</span>
                    </label>
                    <label className="flex items-center gap-3 rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3">
                      <input
                        type="checkbox"
                        checked={ruleDraft.enabled}
                        onChange={(event) =>
                          setRuleDraft((current) => ({
                            ...current,
                            enabled: event.target.checked,
                          }))
                        }
                      />
                      <span className="text-foreground/80 text-sm font-semibold">Enabled</span>
                    </label>
                    <label className="flex items-center gap-3 rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3">
                      <input
                        type="checkbox"
                        checked={ruleDraft.requires_approval}
                        onChange={(event) =>
                          setRuleDraft((current) => ({
                            ...current,
                            requires_approval: event.target.checked,
                          }))
                        }
                      />
                      <span className="text-foreground/80 text-sm font-semibold">
                        Requires approval
                      </span>
                    </label>
                    <label className="flex items-center gap-3 rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3">
                      <input
                        type="checkbox"
                        checked={ruleDraft.web_search_enabled}
                        onChange={(event) =>
                          setRuleDraft((current) => ({
                            ...current,
                            web_search_enabled: event.target.checked,
                          }))
                        }
                      />
                      <span className="text-foreground/80 text-sm font-semibold">Web search</span>
                    </label>
                  </div>

                  <div className="grid grid-cols-1 gap-4 xl:col-span-2 xl:grid-cols-3">
                    <label className="space-y-2">
                      <span className="text-foreground/40 text-[10px] font-black tracking-[0.22em] uppercase">
                        Priority
                      </span>
                      <input
                        type="number"
                        min={0}
                        max={100}
                        value={ruleDraft.priority}
                        onChange={(event) =>
                          setRuleDraft((current) => ({
                            ...current,
                            priority: Math.max(0, Number(event.target.value) || 0),
                          }))
                        }
                        className="focus:ring-primary/50 w-full rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3 text-sm transition outline-none focus:ring-2"
                      />
                    </label>
                    <label className="space-y-2">
                      <span className="text-foreground/40 text-[10px] font-black tracking-[0.22em] uppercase">
                        Source
                      </span>
                      <input
                        value={ruleDraft.source}
                        onChange={(event) =>
                          setRuleDraft((current) => ({
                            ...current,
                            source: event.target.value,
                          }))
                        }
                        className="focus:ring-primary/50 w-full rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3 text-sm transition outline-none focus:ring-2"
                      />
                    </label>
                    <label className="space-y-2">
                      <span className="text-foreground/40 text-[10px] font-black tracking-[0.22em] uppercase">
                        Phase
                      </span>
                      <input
                        value={ruleDraft.phase}
                        onChange={(event) =>
                          setRuleDraft((current) => ({
                            ...current,
                            phase: event.target.value,
                          }))
                        }
                        className="focus:ring-primary/50 w-full rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3 text-sm transition outline-none focus:ring-2"
                      />
                    </label>
                  </div>
                </div>
              </div>
            </motion.div>
          </motion.div>
        ) : null}
      </AnimatePresence>

      {/* ── Agent Studio + Live Execution Graph overlay ───────────────────────── */}
      <AnimatePresence>
        {agentStudioOpen ? (
          <motion.div
            key="agent-studio"
            initial={{ opacity: 0, scale: 0.97 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.97 }}
            transition={{ type: "spring", stiffness: 300, damping: 32 }}
            style={{
              position: "absolute",
              inset: 0,
              zIndex: 50,
              display: "flex",
              flexDirection: "column",
              background: "rgba(4,10,8,0.5)",
              backdropFilter: "blur(16px)",
              borderRadius: 24,
              overflow: "hidden",
              border: "1px solid rgba(255,255,255,0.08)",
            }}
            onClick={() => studioDropdown && setStudioDropdown(null)}
          >
            {/* ── Studio top bar ── */}
            <div style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              padding: "10px 20px",
              borderBottom: "1px solid rgba(255,255,255,0.06)",
              flexShrink: 0,
              background: "rgba(4,8,12,0.4)",
              backdropFilter: "blur(12px)",
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <BrainCircuit size={15} style={{ color: "rgba(52,211,153,0.9)" }} />
                <span style={{ fontSize: 11, fontWeight: 900, letterSpacing: "0.24em", color: "rgba(52,211,153,0.9)", textTransform: "uppercase" }}>Agent Studio</span>
                {orchOverview?.summary && (
                  <div style={{ display: "flex", gap: 5, marginLeft: 8 }}>
                    {[
                      { v: orchOverview.summary.active_subagents ?? 0, label: "agents", c: "rgba(52,211,153,0.8)" },
                      { v: orchOverview.summary.active_tasks ?? 0, label: "tasks", c: "rgba(251,191,36,0.8)" },
                      { v: orchOverview.summary.tool_count ?? 0, label: "tools", c: "rgba(167,139,250,0.8)" },
                    ].map(({ v, label, c }) => (
                      <span key={label} style={{ fontSize: 10, fontWeight: 700, color: c, background: "rgba(255,255,255,0.04)", border: `1px solid ${c.replace("0.8", "0.2")}`, borderRadius: 8, padding: "2px 9px" }}>
                        {v} {label}
                      </span>
                    ))}
                  </div>
                )}
              </div>

              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                {/* Live Graph Controls (shifted to top header) */}
                {agentStudioOpen && (
                  <div style={{ display: "flex", alignItems: "center", gap: 6, borderRight: "1px solid rgba(255,255,255,0.08)", paddingRight: 12 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 5, marginRight: 8 }}>
                      <Network size={11} style={{ color: "rgba(52,211,153,0.65)" }} />
                      <span style={{ fontSize: 8.5, fontWeight: 800, letterSpacing: "0.14em", color: "rgba(255,255,255,0.3)", textTransform: "uppercase" }}>Graph</span>
                      {orchLoading && orchGraph && <RefreshCw size={9} style={{ color: "rgba(52,211,153,0.4)", animation: "spin 1.2s linear infinite" }} />}
                    </div>

                    {orchGraph && <span style={{ fontSize: 9, color: "rgba(255,255,255,0.2)", marginRight: 6 }}>{orchGraph.nodes.length}N · {orchGraph.edges.length}E · {Math.round(graphZoom * 100)}%</span>}

                    {/* Deselect button */}
                    {selectedNode && (
                      <button type="button" onClick={() => setSelectedNode(null)}
                        style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 4, height: 26, borderRadius: 8, border: "1px solid rgba(255,255,255,0.15)", background: "rgba(255,255,255,0.06)", color: "rgba(255,255,255,0.6)", cursor: "pointer", padding: "0 8px", fontSize: 9, fontWeight: 800, letterSpacing: "0.12em", textTransform: "uppercase", transition: "all 0.14s" }}>
                        <X size={9} /> Deselect
                      </button>
                    )}

                    {/* Zoom controls */}
                    {([
                      { id: "zoom-in", label: "+", action: () => setGraphZoom((z) => Math.min(3, +(z + 0.15).toFixed(2))), title: "Zoom In" },
                      { id: "zoom-out", label: "−", action: () => setGraphZoom((z) => Math.max(0.25, +(z - 0.15).toFixed(2))), title: "Zoom Out" },
                    ] as const).map(({ id, label, action, title }) => (
                      <button key={id} id={`graph-${id}`} type="button" title={title} onClick={action}
                        style={{ display: "flex", alignItems: "center", justifyContent: "center", width: 26, height: 26, borderRadius: 8, border: "1px solid rgba(255,255,255,0.1)", background: "rgba(255,255,255,0.04)", color: "rgba(255,255,255,0.65)", cursor: "pointer", fontSize: 13, fontWeight: 700, transition: "all 0.14s", lineHeight: 1 }}>
                        {label}
                      </button>
                    ))}

                    {/* Fit/centre button */}
                    <button id="graph-fit" type="button" title="Fit to view" onClick={() => { setGraphZoom(0.85); setGraphPan({ x: 0, y: 0 }); }}
                      style={{ display: "flex", alignItems: "center", justifyContent: "center", width: 26, height: 26, borderRadius: 8, border: "1px solid rgba(255,255,255,0.1)", background: "rgba(255,255,255,0.04)", color: "rgba(255,255,255,0.65)", cursor: "pointer", fontSize: 10, fontWeight: 900, transition: "all 0.14s" }}>
                      ⊡
                    </button>

                    {/* Refresh */}
                    <button id="graph-refresh" type="button" title="Refresh graph" onClick={() => void loadOrchGraph()}
                      style={{ display: "flex", alignItems: "center", justifyContent: "center", width: 26, height: 26, borderRadius: 8, border: "1px solid rgba(255,255,255,0.1)", background: "rgba(255,255,255,0.04)", color: "rgba(255,255,255,0.65)", cursor: "pointer", transition: "all 0.14s" }}>
                      <RefreshCw size={11} style={orchLoading ? { animation: "spin 1s linear infinite" } : {}} />
                    </button>

                    {/* Legend toggle */}
                    <button id="graph-legend" type="button" title="Toggle legend" onClick={() => setShowLegend((v) => !v)}
                      style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 4, height: 26, borderRadius: 8, border: `1px solid ${showLegend ? "rgba(52,211,153,0.3)" : "rgba(255,255,255,0.1)"}`, background: showLegend ? "rgba(52,211,153,0.08)" : "rgba(255,255,255,0.04)", color: showLegend ? "rgba(52,211,153,0.85)" : "rgba(255,255,255,0.65)", cursor: "pointer", padding: "0 9px", fontSize: 9, fontWeight: 800, letterSpacing: "0.14em", textTransform: "uppercase", transition: "all 0.14s" }}>
                      Legend
                    </button>
                  </div>
                )}

                <button type="button" id="agent-studio-close-btn" aria-label="Close Agent Studio"
                  onClick={() => { setAgentStudioOpen(false); setSelectedNode(null); setStudioDropdown(null); }}
                  style={{ display: "flex", alignItems: "center", justifyContent: "center", width: 28, height: 28, borderRadius: 10, border: "1px solid rgba(255,255,255,0.1)", background: "rgba(255,255,255,0.04)", color: "rgba(255,255,255,0.45)", cursor: "pointer", transition: "all 0.15s" }}
                >
                  <X size={13} />
                </button>
              </div>
            </div>

            {/* ── Studio body ── */}
            <div style={{ flex: 1, display: "flex", overflow: "hidden", minHeight: 0 }}>

              {/* ══ LEFT: Agent Studio form ══ */}
              <div style={{ width: 368, flexShrink: 0, borderRight: "1px solid rgba(255,255,255,0.06)", display: "flex", flexDirection: "column", padding: "18px 16px", gap: 14, overflowY: "auto" }} className="custom-scrollbar">

                {/* Objective */}
                <div>
                  <p style={{ fontSize: 9, fontWeight: 900, letterSpacing: "0.24em", color: "rgba(52,211,153,0.55)", textTransform: "uppercase", marginBottom: 7 }}>Mission Objective</p>
                  <textarea
                    id="agent-studio-objective"
                    value={studioForm.objective}
                    onChange={(e) => setStudioForm((s) => ({ ...s, objective: e.target.value }))}
                    rows={5}
                    placeholder={"Describe what agents should do autonomously…\n\nExamples:\n• Summarise Gmail inbox, draft replies\n• Research latest AI papers → summary doc\n• Check all connectors, report sync failures"}
                    style={{ width: "100%", background: "rgba(255,255,255,0.035)", border: "1px solid rgba(255,255,255,0.09)", borderRadius: 16, padding: "11px 14px", fontSize: 13, color: "rgba(255,255,255,0.88)", resize: "vertical", outline: "none", lineHeight: 1.65, minHeight: 120, transition: "border-color 0.15s" }}
                  />
                </div>

                {/* Execution Mode + Agent Profile — custom dropdowns */}
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                  {/* Execution Mode */}
                  <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    <span style={{ fontSize: 9, fontWeight: 900, letterSpacing: "0.22em", color: "rgba(255,255,255,0.32)", textTransform: "uppercase" }}>Execution Mode</span>
                    <div style={{ position: "relative" }} onClick={(e) => e.stopPropagation()}>
                      <button type="button" id="dd-exec" onClick={() => setStudioDropdown((v) => v === "exec" ? null : "exec")}
                        style={{ width: "100%", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 6, background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 12, padding: "9px 12px", fontSize: 12, fontWeight: 600, color: "rgba(255,255,255,0.85)", cursor: "pointer", transition: "all 0.15s" }}>
                        <span>{studioForm.executionMode === "auto_review" ? "Auto Review" : "Full Access"}</span>
                        <ChevronRight size={12} style={{ transform: studioDropdown === "exec" ? "rotate(90deg)" : "rotate(0deg)", transition: "transform 0.2s", color: "rgba(255,255,255,0.4)" }} />
                      </button>
                      <AnimatePresence>
                        {studioDropdown === "exec" && (
                          <motion.div key="dd-exec-list" initial={{ opacity: 0, y: -6, scaleY: 0.92 }} animate={{ opacity: 1, y: 0, scaleY: 1 }} exit={{ opacity: 0, y: -4, scaleY: 0.94 }} transition={{ duration: 0.15 }}
                            style={{ position: "absolute", top: "calc(100% + 4px)", left: 0, right: 0, zIndex: 200, background: "rgba(10,14,20,0.97)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 12, overflow: "hidden", backdropFilter: "blur(20px)", boxShadow: "0 8px 32px rgba(0,0,0,0.6)" }}>
                            {(["auto_review", "full_access"] as const).map((val) => (
                              <button key={val} type="button"
                                onClick={() => { setStudioForm((s) => ({ ...s, executionMode: val })); setStudioDropdown(null); }}
                                style={{ display: "flex", alignItems: "center", justifyContent: "space-between", width: "100%", padding: "10px 14px", fontSize: 12, fontWeight: 600, color: studioForm.executionMode === val ? "rgba(52,211,153,0.95)" : "rgba(255,255,255,0.7)", background: studioForm.executionMode === val ? "rgba(52,211,153,0.08)" : "transparent", border: "none", cursor: "pointer", transition: "background 0.12s", textAlign: "left" }}>
                                {val === "auto_review" ? "Auto Review" : "Full Access"}
                                {studioForm.executionMode === val && <Check size={11} style={{ color: "rgba(52,211,153,0.8)" }} />}
                              </button>
                            ))}
                          </motion.div>
                        )}
                      </AnimatePresence>
                    </div>
                  </div>

                  {/* Agent Profile */}
                  <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    <span style={{ fontSize: 9, fontWeight: 900, letterSpacing: "0.22em", color: "rgba(255,255,255,0.32)", textTransform: "uppercase" }}>Agent Profile</span>
                    <div style={{ position: "relative" }} onClick={(e) => e.stopPropagation()}>
                      <button type="button" id="dd-profile" onClick={() => setStudioDropdown((v) => v === "profile" ? null : "profile")}
                        style={{ width: "100%", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 6, background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 12, padding: "9px 12px", fontSize: 12, fontWeight: 600, color: "rgba(255,255,255,0.85)", cursor: "pointer", transition: "all 0.15s" }}>
                        <span>{studioForm.subagentProfile.charAt(0).toUpperCase() + studioForm.subagentProfile.slice(1)}</span>
                        <ChevronRight size={12} style={{ transform: studioDropdown === "profile" ? "rotate(90deg)" : "rotate(0deg)", transition: "transform 0.2s", color: "rgba(255,255,255,0.4)" }} />
                      </button>
                      <AnimatePresence>
                        {studioDropdown === "profile" && (
                          <motion.div key="dd-profile-list" initial={{ opacity: 0, y: -6, scaleY: 0.92 }} animate={{ opacity: 1, y: 0, scaleY: 1 }} exit={{ opacity: 0, y: -4, scaleY: 0.94 }} transition={{ duration: 0.15 }}
                            style={{ position: "absolute", top: "calc(100% + 4px)", left: 0, right: 0, zIndex: 200, background: "rgba(10,14,20,0.97)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 12, overflow: "hidden", backdropFilter: "blur(20px)", boxShadow: "0 8px 32px rgba(0,0,0,0.6)" }}>
                            {["default","research","analysis","writer","executor","planner","support","file"].map((p) => (
                              <button key={p} type="button"
                                onClick={() => { setStudioForm((s) => ({ ...s, subagentProfile: p })); setStudioDropdown(null); }}
                                style={{ display: "flex", alignItems: "center", justifyContent: "space-between", width: "100%", padding: "9px 14px", fontSize: 12, fontWeight: 600, color: studioForm.subagentProfile === p ? "rgba(52,211,153,0.95)" : "rgba(255,255,255,0.7)", background: studioForm.subagentProfile === p ? "rgba(52,211,153,0.08)" : "transparent", border: "none", cursor: "pointer", transition: "background 0.12s", textAlign: "left" }}>
                                {p.charAt(0).toUpperCase() + p.slice(1)}
                                {studioForm.subagentProfile === p && <Check size={11} style={{ color: "rgba(52,211,153,0.8)" }} />}
                              </button>
                            ))}
                          </motion.div>
                        )}
                      </AnimatePresence>
                    </div>
                  </div>
                </div>

                {/* Source Connector */}
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  <span style={{ fontSize: 9, fontWeight: 900, letterSpacing: "0.22em", color: "rgba(255,255,255,0.32)", textTransform: "uppercase" }}>Source Connector (optional)</span>
                  <div style={{ position: "relative" }} onClick={(e) => e.stopPropagation()}>
                    <button type="button" id="dd-connector" onClick={() => setStudioDropdown((v) => v === "connector" ? null : "connector")}
                      style={{ width: "100%", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 6, background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 12, padding: "9px 12px", fontSize: 12, fontWeight: 600, color: "rgba(255,255,255,0.85)", cursor: "pointer", transition: "all 0.15s" }}>
                      <span>{studioForm.connectorId ? (activeConnectors.find((c) => c.id === studioForm.connectorId)?.name ?? studioForm.connectorId) : "No connector"}</span>
                      <ChevronRight size={12} style={{ transform: studioDropdown === "connector" ? "rotate(90deg)" : "rotate(0deg)", transition: "transform 0.2s", color: "rgba(255,255,255,0.4)" }} />
                    </button>
                    <AnimatePresence>
                      {studioDropdown === "connector" && (
                        <motion.div key="dd-connector-list" initial={{ opacity: 0, y: -6, scaleY: 0.92 }} animate={{ opacity: 1, y: 0, scaleY: 1 }} exit={{ opacity: 0, y: -4, scaleY: 0.94 }} transition={{ duration: 0.15 }}
                          style={{ position: "absolute", top: "calc(100% + 4px)", left: 0, right: 0, zIndex: 200, background: "rgba(10,14,20,0.97)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 12, overflow: "hidden", backdropFilter: "blur(20px)", boxShadow: "0 8px 32px rgba(0,0,0,0.6)", maxHeight: 200, overflowY: "auto" }}>
                          {[
                            { id: "", name: "No connector" },
                            ...activeConnectors,
                          ].map((c) => (
                            <button key={c.id} type="button"
                              onClick={() => { setStudioForm((s) => ({ ...s, connectorId: c.id })); setStudioDropdown(null); }}
                              style={{ display: "flex", alignItems: "center", justifyContent: "space-between", width: "100%", padding: "9px 14px", fontSize: 12, fontWeight: 600, color: studioForm.connectorId === c.id ? "rgba(52,211,153,0.95)" : "rgba(255,255,255,0.7)", background: studioForm.connectorId === c.id ? "rgba(52,211,153,0.08)" : "transparent", border: "none", cursor: "pointer", transition: "background 0.12s", textAlign: "left" }}>
                              {c.name}
                              {studioForm.connectorId === c.id && <Check size={11} style={{ color: "rgba(52,211,153,0.8)" }} />}
                            </button>
                          ))}
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </div>
                </div>

                {/* Notes */}
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  <span style={{ fontSize: 9, fontWeight: 900, letterSpacing: "0.22em", color: "rgba(255,255,255,0.32)", textTransform: "uppercase" }}>Workspace Context (optional)</span>
                  <textarea id="agent-studio-note" value={studioForm.noteContent} onChange={(e) => setStudioForm((s) => ({ ...s, noteContent: e.target.value }))} rows={2}
                    placeholder="Optional notes or context to pass to the agent…"
                    style={{ width: "100%", background: "rgba(255,255,255,0.035)", border: "1px solid rgba(255,255,255,0.09)", borderRadius: 12, padding: "8px 12px", fontSize: 12, color: "rgba(255,255,255,0.82)", resize: "vertical", outline: "none", lineHeight: 1.6 }}
                  />
                </div>

                {/* Toggles */}
                <div style={{ display: "flex", gap: 8 }}>
                  {([{ key: "thinkingEnabled" as const, label: "Deep Think" }, { key: "webSearchEnabled" as const, label: "Web Search" }]).map(({ key, label }) => (
                    <label key={key} style={{ display: "flex", alignItems: "center", gap: 7, fontSize: 11, fontWeight: 700, color: studioForm[key] ? "rgba(52,211,153,0.95)" : "rgba(255,255,255,0.4)", cursor: "pointer", background: studioForm[key] ? "rgba(52,211,153,0.09)" : "rgba(255,255,255,0.03)", border: `1px solid ${studioForm[key] ? "rgba(52,211,153,0.22)" : "rgba(255,255,255,0.07)"}`, borderRadius: 12, padding: "7px 12px", flex: 1, justifyContent: "center", transition: "all 0.18s", userSelect: "none" }}>
                      <input type="checkbox" checked={studioForm[key]} onChange={(e) => setStudioForm((s) => ({ ...s, [key]: e.target.checked }))} style={{ accentColor: "#34d399", width: 13, height: 13 }} />
                      {label}
                    </label>
                  ))}
                </div>

                {/* Launch button */}
                <button id="agent-studio-run-btn" type="button"
                  disabled={missionRunning || !studioForm.objective.trim()}
                  onClick={() => void handleRunMission()}
                  style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 8, padding: "13px 20px", borderRadius: 16, border: "1px solid rgba(52,211,153,0.35)", background: missionRunning ? "rgba(52,211,153,0.06)" : "linear-gradient(135deg,rgba(52,211,153,0.16),rgba(52,211,153,0.08))", color: "rgba(52,211,153,0.95)", fontSize: 11, fontWeight: 900, letterSpacing: "0.2em", textTransform: "uppercase", cursor: missionRunning || !studioForm.objective.trim() ? "not-allowed" : "pointer", opacity: missionRunning || !studioForm.objective.trim() ? 0.45 : 1, transition: "all 0.18s", boxShadow: missionRunning ? "none" : "0 0 24px rgba(52,211,153,0.12), inset 0 1px 0 rgba(255,255,255,0.05)" }}
                >
                  {missionRunning ? <RefreshCw size={13} style={{ animation: "spin 1s linear infinite" }} /> : <Play size={13} />}
                  {missionRunning ? "Mission Running…" : "Launch Mission"}
                </button>

                {/* Live stream log */}
                {(missionLog.length > 0 || missionError || missionRunning) && (
                  <div style={{ display: "flex", flexDirection: "column", gap: 7, minHeight: 0 }}>
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                      <p style={{ fontSize: 9, fontWeight: 900, letterSpacing: "0.22em", color: "rgba(52,211,153,0.55)", textTransform: "uppercase" }}>Live Output</p>
                      {missionLog.length > 0 && <button type="button" onClick={() => setMissionLog([])} style={{ fontSize: 10, color: "rgba(255,255,255,0.25)", cursor: "pointer", background: "none", border: "none" }}>Clear</button>}
                    </div>
                    {missionError && <div style={{ borderRadius: 10, border: "1px solid rgba(244,63,94,0.3)", background: "rgba(244,63,94,0.07)", padding: "9px 12px", fontSize: 11, color: "rgba(244,63,94,0.9)" }}>{missionError}</div>}
                    <div ref={missionLogRef} className="custom-scrollbar" style={{ overflowY: "auto", background: "rgba(0,0,0,0.45)", borderRadius: 12, border: "1px solid rgba(255,255,255,0.05)", padding: "11px 12px", fontFamily: "monospace", fontSize: 11, lineHeight: 1.75, color: "rgba(255,255,255,0.7)", maxHeight: 240 }}>
                      {missionRunning && missionLog.length === 0 && <span style={{ color: "rgba(52,211,153,0.5)" }}>● Connecting to orchestration stream…</span>}
                      {missionLog.map((line, i) => (
                        <div key={i} style={{ marginBottom: 3 }}>
                          <span style={{ color: "rgba(52,211,153,0.4)", marginRight: 6 }}>›</span>{line}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* ══ RIGHT: Live Execution Graph ══ */}
              <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0, overflow: "hidden", position: "relative" }}>

                {/* Graph canvas + sidebar row (merged toolbar style) */}
                <div style={{ flex: 1, display: "flex", overflow: "hidden", minHeight: 0, position: "relative" }}>

                  {/* ── SVG graph with zoom/pan ── */}
                  <div
                    ref={graphContainerRef}
                    style={{ flex: 1, overflow: "hidden", position: "relative", cursor: "grab" }}
                    onMouseDown={(e) => {
                      if (e.button !== 0) return;
                      isPanningRef.current = true;
                      panStartRef.current = { x: e.clientX, y: e.clientY, panX: graphPan.x, panY: graphPan.y };
                      (e.currentTarget as HTMLDivElement).style.cursor = "grabbing";
                    }}
                    onMouseMove={(e) => {
                      if (!isPanningRef.current) return;
                      const dx = e.clientX - panStartRef.current.x;
                      const dy = e.clientY - panStartRef.current.y;
                      setGraphPan({ x: panStartRef.current.panX + dx, y: panStartRef.current.panY + dy });
                    }}
                    onMouseUp={(e) => { isPanningRef.current = false; (e.currentTarget as HTMLDivElement).style.cursor = "grab"; }}
                    onMouseLeave={() => { isPanningRef.current = false; }}
                    onWheel={(e) => {
                      e.preventDefault();
                      const delta = -e.deltaY * 0.001;
                      setGraphZoom((z) => Math.max(0.25, Math.min(3, +(z + delta).toFixed(3))));
                    }}
                  >
                    {/* Loading state */}
                    {!orchGraph && orchLoading && (
                      <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", flexDirection: "column", gap: 14 }}>
                        <div style={{ width: 48, height: 48, borderRadius: "50%", border: "2px solid rgba(52,211,153,0.12)", borderTopColor: "rgba(52,211,153,0.75)", animation: "spin 0.85s linear infinite" }} />
                        <p style={{ fontSize: 11, fontWeight: 700, color: "rgba(255,255,255,0.28)", letterSpacing: "0.22em", textTransform: "uppercase" }}>Loading graph…</p>
                      </div>
                    )}
                    {!orchGraph && !orchLoading && (
                      <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", flexDirection: "column", gap: 12 }}>
                        <Network size={34} style={{ color: "rgba(255,255,255,0.08)" }} />
                        <p style={{ fontSize: 11, color: "rgba(255,255,255,0.28)", letterSpacing: "0.14em" }}>No orchestration data yet</p>
                        <button type="button" onClick={() => void loadOrchGraph()} style={{ fontSize: 10, fontWeight: 700, color: "rgba(52,211,153,0.7)", background: "rgba(52,211,153,0.08)", border: "1px solid rgba(52,211,153,0.2)", borderRadius: 10, padding: "6px 14px", cursor: "pointer" }}>Refresh</button>
                      </div>
                    )}

                    {orchGraph && (() => {
                      const nodes = orchGraph.nodes.slice(0, 28);
                      const edges = orchGraph.edges;
                      const xs = nodes.map((n) => n.x);
                      const ys = nodes.map((n) => n.y);
                      const PAD = 200;
                      const minX = Math.min(...xs) - PAD;
                      const maxX = Math.max(...xs) + PAD;
                      const minY = Math.min(...ys) - PAD;
                      const maxY = Math.max(...ys) + PAD;
                      const W = Math.max(1100, maxX - minX);
                      const H = Math.max(700, maxY - minY);
                      const nx = (n: OrchestraNode) => n.x - minX;
                      const ny = (n: OrchestraNode) => n.y - minY;
                      const nodeMap = new Map(nodes.map((n) => [n.id, n]));
                      const CARD_W = 162;
                      const CARD_H = 62;
                      const CARD_R = 14;

                      // Compute smooth S-curve cubic bezier path between card edges
                      function smartPath(x1: number, y1: number, x2: number, y2: number): string {
                        const dx = x2 - x1;
                        const dy = y2 - y1;
                        const absD = Math.sqrt(dx * dx + dy * dy);
                        const tension = Math.max(absD * 0.45, 80);
                        // mostly vertical connection
                        if (Math.abs(dy) >= Math.abs(dx) * 0.7) {
                          const cp1x = x1; const cp1y = y1 + tension;
                          const cp2x = x2; const cp2y = y2 - tension;
                          return `M ${x1} ${y1} C ${cp1x} ${cp1y}, ${cp2x} ${cp2y}, ${x2} ${y2}`;
                        }
                        // mostly horizontal
                        const cp1x = x1 + tension; const cp1y = y1;
                        const cp2x = x2 - tension; const cp2y = y2;
                        return `M ${x1} ${y1} C ${cp1x} ${cp1y}, ${cp2x} ${cp2y}, ${x2} ${y2}`;
                      }

                      return (
                        <svg
                          width="100%"
                          height="100%"
                          style={{ display: "block", userSelect: "none" }}
                        >
                          <defs>
                            {/* Glow filters per tone */}
                            {(["emerald","cyan","amber","rose","violet","slate"] as const).map((tone) => (
                              <filter key={tone} id={`glow-${tone}`} x="-40%" y="-40%" width="180%" height="180%">
                                <feGaussianBlur stdDeviation="3" result="blur" />
                                <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
                              </filter>
                            ))}
                            {/* Arrow markers — tone-coloured */}
                            {(["emerald","cyan","amber","rose","violet","slate"] as const).map((tone) => (
                              <marker key={tone} id={`arr-${tone}`} markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto" markerUnits="strokeWidth">
                                <path d="M0,0 L0,6 L7,3 z" fill={nodeToneColor(tone, 0.65)} />
                              </marker>
                            ))}
                            {/* Gradient defs for node cards */}
                            {(["emerald","cyan","amber","rose","violet","slate"] as const).map((tone) => (
                              <linearGradient key={tone} id={`card-grad-${tone}`} x1="0" y1="0" x2="0" y2="1">
                                <stop offset="0%" stopColor={nodeToneColor(tone, 0.18)} />
                                <stop offset="100%" stopColor={nodeToneColor(tone, 0.06)} />
                              </linearGradient>
                            ))}
                          </defs>

                          <g style={{ transform: `translate(${graphPan.x}px, ${graphPan.y}px) scale(${graphZoom})`, transformOrigin: "0 0", transition: "transform 0.08s ease-out" }}>
                            {/* ── EDGES: smooth cubic S-curves ── */}
                            {edges.map((edge, i) => {
                              const src = nodeMap.get(edge.source);
                              const tgt = nodeMap.get(edge.target);
                              if (!src || !tgt) return null;
                              // connect from bottom-centre of src to top-centre of tgt (or side if horizontal)
                              const sx = nx(src); const sy = ny(src);
                              const tx = nx(tgt); const ty = ny(tgt);
                              const dx = tx - sx; const dy = ty - sy;
                              let x1 = sx; let y1 = sy; let x2 = tx; let y2 = ty;
                              if (Math.abs(dy) >= Math.abs(dx) * 0.7) {
                                // vertical: connect bottom of src → top of tgt
                                x1 = sx; y1 = sy + CARD_H / 2;
                                x2 = tx; y2 = ty - CARD_H / 2;
                              } else {
                                // horizontal: right of src → left of tgt
                                x1 = sx + (dx > 0 ? CARD_W / 2 : -CARD_W / 2); y1 = sy;
                                x2 = tx + (dx > 0 ? -CARD_W / 2 : CARD_W / 2); y2 = ty;
                              }
                              const edgeTone = nodeStatusClass(src.status);
                              const edgeColor = nodeToneColor(edgeTone, 0.5);
                              const glowColor = nodeToneColor(edgeTone, 0.18);
                              const midT = 0.5;
                              // midpoint on cubic for label placement — approximate
                              const pathStr = smartPath(x1, y1, x2, y2);
                              const lx = (x1 + x2) / 2;
                              const ly = (y1 + y2) / 2 - 10;
                              const animDur = (1.8 + (i % 5) * 0.4).toFixed(1);
                              return (
                                <g key={`edge-${i}`}>
                                  {/* Glow halo */}
                                  <path d={pathStr} fill="none" stroke={glowColor} strokeWidth={5} strokeLinecap="round" />
                                  {/* Main edge line */}
                                  <path
                                    d={pathStr}
                                    fill="none"
                                    stroke={edgeColor}
                                    strokeWidth={1.8}
                                    strokeLinecap="round"
                                    markerEnd={`url(#arr-${edgeTone})`}
                                    style={{ animation: `edgeFlow ${animDur}s linear infinite`, strokeDasharray: "8 6" }}
                                  />
                                  {/* Edge label */}
                                  <text x={lx} y={ly} textAnchor="middle" fontSize={8} fontWeight={800} fill={nodeToneColor(edgeTone, 0.6)} letterSpacing="0.14em" style={{ textTransform: "uppercase", paintOrder: "stroke", stroke: "rgba(4,8,12,0.8)", strokeWidth: 3 }}>
                                    {edge.label}
                                  </text>
                                </g>
                              );
                            })}

                            {/* ── NODES: rounded-square glassmorphic cards ── */}
                            {nodes.map((node) => {
                              const x = nx(node);
                              const y = ny(node);
                              const tone = nodeStatusClass(node.status);
                              const mainColor = nodeToneColor(tone, 1);
                              const borderColor = nodeToneColor(tone, selectedNode?.id === node.id ? 0.9 : 0.45);
                              const isSelected = selectedNode?.id === node.id;
                              const isActive = ["running","active","connected","healthy"].includes(node.status.toLowerCase());
                              const friendlyLabel = USER_FRIENDLY_LABELS[node.id] ?? node.label;
                              return (
                                <g
                                  key={node.id}
                                  transform={`translate(${x - CARD_W / 2},${y - CARD_H / 2})`}
                                  style={{ cursor: "pointer", filter: isSelected ? `drop-shadow(0 0 12px ${nodeToneColor(tone, 0.55)})` : isActive ? `drop-shadow(0 0 6px ${nodeToneColor(tone, 0.25)})` : "none" }}
                                  onClick={() => setSelectedNode((prev) => prev?.id === node.id ? null : node)}
                                >
                                  {/* Card shadow */}
                                  <rect width={CARD_W} height={CARD_H} rx={CARD_R} fill="rgba(0,0,0,0.55)" transform="translate(1,2)" />
                                  {/* Card body gradient */}
                                  <rect width={CARD_W} height={CARD_H} rx={CARD_R} fill={`url(#card-grad-${tone})`} />
                                  {/* Card border */}
                                  <rect width={CARD_W} height={CARD_H} rx={CARD_R} fill="none" stroke={borderColor} strokeWidth={isSelected ? 1.8 : 1.1} />
                                  {/* Selected accent top bar */}
                                  {isSelected && <rect width={CARD_W} height={3} rx={CARD_R} fill={mainColor} opacity={0.6} />}
                                  {/* Status indicator dot */}
                                  <circle cx={14} cy={16} r={4.5} fill={mainColor} opacity={0.9}
                                    style={{ animation: isActive ? "nodePulse 2.2s ease-in-out infinite" : "none" }}
                                  />
                                  {isActive && <circle cx={14} cy={16} r={4.5} fill={mainColor} opacity={0.25}
                                    style={{ animation: "nodeRing 2.2s ease-in-out infinite" }}
                                  />}
                                  {/* Node label */}
                                  <text x={26} y={15} fontSize={10.5} fontWeight={800} fill={mainColor} dominantBaseline="middle" style={{ paintOrder: "stroke" }}>
                                    {friendlyLabel.length > 17 ? friendlyLabel.slice(0, 16) + "…" : friendlyLabel}
                                  </text>
                                  {/* Kind · status row */}
                                  <text x={14} y={38} fontSize={8.5} fontWeight={600} fill={nodeToneColor(tone, 0.55)} letterSpacing="0.1em" style={{ textTransform: "uppercase" }}>
                                    {node.kind} · {node.status}
                                  </text>
                                </g>
                              );
                            })}
                          </g>
                        </svg>
                      );
                    })()}

                    {/* ── Legend overlay ── */}
                    <AnimatePresence>
                      {showLegend && orchGraph && (
                        <motion.div
                          key="legend"
                          initial={{ opacity: 0, y: 8 }}
                          animate={{ opacity: 1, y: 0 }}
                          exit={{ opacity: 0, y: 8 }}
                          transition={{ duration: 0.18 }}
                          style={{ position: "absolute", bottom: 14, left: 14, zIndex: 10, background: "rgba(4,8,12,0.88)", backdropFilter: "blur(16px)", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 14, padding: "12px 14px", minWidth: 180 }}
                        >
                          <p style={{ fontSize: 9, fontWeight: 900, letterSpacing: "0.22em", color: "rgba(255,255,255,0.3)", textTransform: "uppercase", marginBottom: 10 }}>Legend</p>
                          <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
                            {([
                              { color: "rgba(52,211,153,1)", label: "Active / Running / Healthy" },
                              { color: "rgba(251,191,36,1)", label: "Pending / Waiting" },
                              { color: "rgba(244,63,94,1)", label: "Error / Failed / Stale" },
                              { color: "rgba(167,139,250,1)", label: "Executor / Connector" },
                              { color: "rgba(34,211,238,1)", label: "Control / Router / Signal" },
                              { color: "rgba(148,163,184,1)", label: "Inactive / Unknown" },
                            ]).map(({ color, label }) => (
                              <div key={label} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                                <span style={{ width: 9, height: 9, borderRadius: 3, background: color, flexShrink: 0, boxShadow: `0 0 6px ${color}55` }} />
                                <span style={{ fontSize: 10, fontWeight: 600, color: "rgba(255,255,255,0.6)" }}>{label}</span>
                              </div>
                            ))}
                            <div style={{ borderTop: "1px solid rgba(255,255,255,0.07)", paddingTop: 8, marginTop: 2 }}>
                              {[
                                { symbol: "→ ──", label: "Curved edge = data flow" },
                                { symbol: "◉", label: "Pulsing dot = live active" },
                                { symbol: "[ ]", label: "Click node = inspect" },
                                { symbol: "⊡", label: "Fit button = re-centre" },
                              ].map(({ symbol, label }) => (
                                <div key={label} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 5 }}>
                                  <span style={{ fontSize: 10, fontFamily: "monospace", color: "rgba(52,211,153,0.55)", minWidth: 24 }}>{symbol}</span>
                                  <span style={{ fontSize: 10, color: "rgba(255,255,255,0.4)" }}>{label}</span>
                                </div>
                              ))}
                            </div>
                          </div>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </div>

                  {/* ── Node detail sidebar ── */}
                  <AnimatePresence mode="wait">
                    {selectedNode ? (
                      <motion.div
                        key={selectedNode.id}
                        initial={{ x: 56, opacity: 0 }}
                        animate={{ x: 0, opacity: 1 }}
                        exit={{ x: 56, opacity: 0 }}
                        transition={{ type: "spring", stiffness: 360, damping: 32 }}
                        style={{ width: 272, flexShrink: 0, borderLeft: "1px solid rgba(255,255,255,0.07)", padding: "14px 14px", overflowY: "auto", display: "flex", flexDirection: "column", gap: 12, background: "rgba(4,8,12,0.6)", backdropFilter: "blur(8px)" }}
                        className="custom-scrollbar"
                      >
                        {/* Header */}
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                          <div>
                            <p style={{ fontSize: 8, fontWeight: 900, letterSpacing: "0.24em", color: nodeToneColor(nodeStatusClass(selectedNode.status), 0.7), textTransform: "uppercase", marginBottom: 5 }}>{selectedNode.kind} · {selectedNode.world}</p>
                            <p style={{ fontSize: 13, fontWeight: 800, color: "rgba(255,255,255,0.92)", lineHeight: 1.35 }}>{USER_FRIENDLY_LABELS[selectedNode.id] ?? selectedNode.label}</p>
                          </div>
                          <button type="button" onClick={() => setSelectedNode(null)} style={{ background: "none", border: "none", color: "rgba(255,255,255,0.28)", cursor: "pointer", padding: 4 }}><X size={12} /></button>
                        </div>

                        {/* Status badges */}
                        <div style={{ display: "flex", gap: 5, flexWrap: "wrap" }}>
                          {[{ text: selectedNode.status, color: nodeStatusClass(selectedNode.status) }, { text: selectedNode.world, color: "slate" }].map(({ text, color }) => (
                            <span key={text} style={{ fontSize: 9, fontWeight: 700, letterSpacing: "0.14em", color: nodeToneColor(color, 0.9), background: nodeToneColor(color, 0.1), border: `1px solid ${nodeToneColor(color, 0.22)}`, borderRadius: 8, padding: "3px 9px", textTransform: "uppercase" }}>{text}</span>
                          ))}
                        </div>

                        {/* Meta fields */}
                        {selectedNode.meta && Object.keys(selectedNode.meta).length > 0 && (
                          <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
                            <p style={{ fontSize: 8, fontWeight: 900, letterSpacing: "0.22em", color: "rgba(255,255,255,0.22)", textTransform: "uppercase" }}>Node Data</p>
                            {Object.entries(selectedNode.meta).slice(0, 10).map(([k, v]) => {
                              const display = typeof v === "object" ? JSON.stringify(v).slice(0, 80) : String(v ?? "").slice(0, 120);
                              if (!display || display === "null" || display === "undefined") return null;
                              return (
                                <div key={k} style={{ background: "rgba(255,255,255,0.025)", borderRadius: 9, padding: "7px 9px", border: "1px solid rgba(255,255,255,0.05)" }}>
                                  <p style={{ fontSize: 8, fontWeight: 700, color: "rgba(255,255,255,0.28)", textTransform: "uppercase", letterSpacing: "0.14em", marginBottom: 3 }}>{k.replace(/_/g, " ")}</p>
                                  <p style={{ fontSize: 11, color: "rgba(255,255,255,0.72)", wordBreak: "break-word", lineHeight: 1.4 }}>{display}</p>
                                </div>
                              );
                            })}
                          </div>
                        )}

                        {/* Connections */}
                        {orchGraph && (
                          <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                            <p style={{ fontSize: 8, fontWeight: 900, letterSpacing: "0.22em", color: "rgba(255,255,255,0.22)", textTransform: "uppercase" }}>Connections</p>
                            {orchGraph.edges.filter((e) => e.source === selectedNode.id || e.target === selectedNode.id).slice(0, 8).map((e, i) => {
                              const isOut = e.source === selectedNode.id;
                              const otherId = isOut ? e.target : e.source;
                              const other = orchGraph.nodes.find((n) => n.id === otherId);
                              return (
                                <div key={i} style={{ display: "flex", alignItems: "center", gap: 6, background: "rgba(255,255,255,0.025)", borderRadius: 8, padding: "6px 9px", border: "1px solid rgba(255,255,255,0.05)" }}>
                                  <ChevronRight size={9} style={{ transform: isOut ? "none" : "rotate(180deg)", color: nodeToneColor(nodeStatusClass(e.tone), 0.7), flexShrink: 0 }} />
                                  <span style={{ color: nodeToneColor(nodeStatusClass(e.tone), 0.7), fontWeight: 800, textTransform: "uppercase", letterSpacing: "0.12em", fontSize: 8, minWidth: 36 }}>{e.label}</span>
                                  <span style={{ fontSize: 10, color: "rgba(255,255,255,0.55)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{USER_FRIENDLY_LABELS[otherId] ?? (other?.label ?? otherId)}</span>
                                </div>
                              );
                            })}
                          </div>
                        )}
                      </motion.div>
                    ) : null}
                  </AnimatePresence>
                </div>
              </div>
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>

      {/* ── keyframe styles ───────────────────────────────────────────────────── */}
      <style>{`
        @keyframes bounce {
          from { transform: scaleY(0.5); opacity: 0.6; }
          to   { transform: scaleY(1.0); opacity: 1;   }
        }
        @keyframes ping {
          75%, 100% { transform: scale(1.8); opacity: 0; }
        }
        @keyframes spin {
          from { transform: rotate(0deg); }
          to   { transform: rotate(360deg); }
        }
        @keyframes edgeFlow {
          from { stroke-dashoffset: 0; }
          to   { stroke-dashoffset: -28; }
        }
        @keyframes nodePulse {
          0%, 100% { opacity: 0.9; }
          50% { opacity: 0.55; }
        }
        @keyframes nodeRing {
          0% { r: 4.5; opacity: 0.35; }
          70% { r: 11; opacity: 0; }
          100% { r: 11; opacity: 0; }
        }
        #agent-studio-objective:focus,
        #agent-studio-note:focus {
          border-color: rgba(52,211,153,0.35) !important;
          box-shadow: 0 0 0 3px rgba(52,211,153,0.07);
        }
        #dd-exec:hover, #dd-profile:hover, #dd-connector:hover {
          border-color: rgba(255,255,255,0.18) !important;
          background: rgba(255,255,255,0.07) !important;
        }
        #graph-zoom-in:hover, #graph-zoom-out:hover, #graph-fit:hover,
        #graph-refresh:hover, #graph-legend:hover {
          background: rgba(255,255,255,0.1) !important;
          border-color: rgba(255,255,255,0.18) !important;
          color: rgba(255,255,255,0.9) !important;
        }
      `}</style>
    </div>
  );
}

function HeartPulseIcon() {
  return (
    <div className="h-3 w-3 rounded-full bg-emerald-400 shadow-[0_0_12px_rgba(16,185,129,0.55)]" />
  );
}
