export function estimateTokens(text: string): number {
  const trimmed = text.trim();
  return trimmed ? trimmed.split(/\s+/).length : 0;
}

export interface MessageMetrics {
  tokensPerSec?: number;
  totalTokens?: number;
  ttftMs?: number;
  modelName?: string;
  providerType?: string;
  startedAt?: string;
  firstTokenAt?: string;
  contextLimit?: number;
  contextLimitSource?: string | null;
  contextUsedTokens?: number;
  contextRemainingTokens?: number;
  contextUsage?: number;
  contextUsageSource?: string | null;
  reservedOutputTokens?: number;
  safeRemainingTokens?: number | null;
  sessionInputTokens?: number;
  sessionOutputTokens?: number;
  sessionTotalTokens?: number;
  maxOutputTokens?: number;
  contextStatus?:
    | "normal"
    | "watch"
    | "compact_soon"
    | "auto_compact"
    | "emergency"
    | "compacted"
    | "unknown";
  contextCompacted?: boolean;
  phase?: string;
  activeTools?: string[];
  latencyTimeline?: Array<{ label: string; atMs: number; detail?: string }>;
}

export interface StructuredAnswerShape {
  key_findings: string[];
  detailed_analysis: string;
  limitations: string;
  conclusion: string;
  confidence_score: number;
  follow_up_suggestions: string[];
}

export interface StreamTableBlock {
  id: string;
  type: "table";
  title?: string | null;
  headers: string[];
  rows: string[][];
}

export interface StreamChartBlock {
  id: string;
  type: "chart";
  title?: string | null;
  chart_type: "line" | "bar" | "pie" | "area" | "scatter";
  series: Array<{ label: string; value: number }>;
  raw_payload?: string | null;
  x_key?: string;
  y_key?: string;
  z_key?: string;
}

export interface StreamDiagramBlock {
  id: string;
  type: "diagram";
  title?: string | null;
  diagram_type: string;
  source: "mermaid" | "graph_json";
  syntax: string;
  description?: string;
}

export type StructuredBlock = StreamTableBlock | StreamChartBlock | StreamDiagramBlock;

export interface DeepSpaceStreamEvent {
  event:
    | "meta"
    | "start"
    | "thinking"
    | "delta"
    | "replace"
    | "table"
    | "chart"
    | "card"
    | "diagram"
    | "artifact"
    | "media_status"
    | "followups"
    | "metrics"
    | "done"
    | "error"
    // Agent events
    | "agent_plan"
    | "tool_start"
    | "tool_delta"
    | "tool_result"
    | "tool_error"
    | "observing"
    | "permission_request"
    | "permission_granted"
    | "permission_denied"
    | "agent_thinking"
    | "agent_testing"
    | "agent_verifying"
    | "agent_self_correct"
    | "step_start"
    | "step_finish"
    | "agent_status"
    | "step_summary"
    | "ask_user_question"
    // Orchestration / Mission events
    | "mission_start"
    | "mission_planning"
    | "mission_plan"
    | "mission_graph"
    | "mission_summary"
    | "mission_done"
    | "lane_start"
    | "lane_delta"
    | "lane_thinking"
    | "lane_agent_thinking"
    | "lane_result"
    | "lane_error"
    | "lane_step_summary"
    | "lane_observation"
    | "lane_blocked"
    | "approval_request";
  data: Record<string, unknown>;
  sequence?: number;
}

export interface DeepSpaceHistoryVersion {
  id: string;
  version_index: number;
  content: string;
  metadata_json?: Record<string, unknown>;
  source_type: string;
  created_at: string;
}

export interface DeepSpaceHistoryMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  metadata_json?: Record<string, unknown>;
  created_at: string;
  active_version_id?: string | null;
  active_version_index?: number;
  version_count?: number;
  versions?: DeepSpaceHistoryVersion[];
}

export type AgentPhase =
  | "exploring"
  | "planning"
  | "modifying"
  | "verifying"
  | "testing"
  | "completed"
  | "thinking";

export type MissionLaneStatus =
  | "planned"
  | "running"
  | "awaiting_approval"
  | "completed"
  | "failed"
  | "cancelled"
  | "blocked";

export interface MissionLaneEvent {
  id: string;
  kind:
    | "lane_start"
    | "lane_delta"
    | "lane_thinking"
    | "lane_agent_thinking"
    | "lane_step_summary"
    | "lane_observation"
    | "lane_result"
    | "lane_error"
    | "lane_blocked"
    | "approval_request";
  message: string;
  at: string;
  status?: MissionLaneStatus;
  toolName?: string;
}

export interface MissionLaneVisual {
  laneId: string;
  laneType: string;
  title: string;
  prompt: string;
  priority: number;
  status: MissionLaneStatus;
  dependsOn: string[];
  blockedBy: string[];
  subagentType?: string | null;
  metadata?: Record<string, unknown>;
  summary?: string;
  output?: string;
  latestText?: string;
  error?: string;
  startedAt?: string;
  completedAt?: string;
  events: MissionLaneEvent[];
}

export interface MissionRuntimeState {
  plannerMode?: string;
  plannerValidationStatus?: "pending" | "validated" | "policy_fallback" | "system_support";
  runtimeHooksState?: "active" | "disabled";
  subagentProfile?: string;
  subagentProfileClassification?: "adaptive" | "preferred_profile";
  diagnostics?: MissionRuntimeDiagnostics;
}

export interface MissionRuntimeDiagnostics {
  planner?: {
    source?: string;
    mode?: string;
    laneCount?: number;
    parallelLimit?: number;
    gatedActionsDetected?: boolean;
    dynamicFanout?: number;
  };
  hooks?: {
    active?: boolean;
    counts?: Record<string, number>;
    recent?: Array<{
      phase?: string;
      hook?: string;
      status?: string;
      changedFields?: string[];
      toolName?: string | null;
    }>;
  };
  policy?: {
    counts?: {
      allow?: number;
      approval?: number;
      block?: number;
    };
    recent?: Array<{
      toolName?: string;
      decision?: string;
      reason?: string;
      tier?: number;
      mode?: string;
      argKeys?: string[];
    }>;
  };
  memory?: {
    recent?: Array<{
      kind?: string;
      count?: number;
      fastBootstrap?: boolean;
    }>;
  };
  compaction?: {
    latest?: Record<string, unknown> | null;
    recent?: Array<Record<string, unknown>>;
  };
  toolDensity?: {
    started?: number;
    completed?: number;
    failed?: number;
    blocked?: number;
    awaitingApproval?: number;
  };
}

export type DurableReconnectState = "idle" | "connected" | "reconnecting" | "interrupted";

export interface DurableMissionRuntimeState {
  runId: string;
  status?: string;
  lastSequence: number;
  checkpointSequence?: number | null;
  continuationEpoch?: number;
  recoveryCount?: number;
  pendingApprovals?: number;
  reconnectState: DurableReconnectState;
  budgetUsage?: Record<string, number>;
  budgetLimits?: Record<string, number>;
  supervisorDecision?: string | null;
  replayReadOnly: true;
}

export interface ConversationCompactionState {
  version: number;
  trigger: "manual" | "automatic" | string;
  compactedAt: string;
  anchorMessageId?: string | null;
  summary: string;
  summarizedCount: number;
  keptRecentCount: number;
  beforeTokens: number;
  afterTokens: number;
  savedTokens: number;
}

export interface MissionCanvasEvent {
  id: string;
  kind:
    | "mission_start"
    | "mission_planning"
    | "mission_plan"
    | "mission_graph"
    | "mission_summary"
    | "mission_done"
    | "approval_request";
  message: string;
  at: string;
  laneId?: string;
}

export interface MissionCanvasState {
  missionId: string;
  objective: string;
  status: "planning" | "running" | "awaiting_approval" | "completed" | "failed" | "cancelled";
  phase:
    | "planning"
    | "graph_ready"
    | "executing"
    | "awaiting_approval"
    | "completed"
    | "failed"
    | "cancelled";
  executionMode?: string;
  plannerSource?: string;
  summary?: string;
  startedAt: string;
  completedAt?: string;
  lastUpdatedAt: string;
  signals?: Record<string, unknown>;
  runtimeState?: MissionRuntimeState;
  durableRuntime?: DurableMissionRuntimeState;
  graph?: {
    nodes?: Array<Record<string, unknown>>;
    edges?: Array<Record<string, unknown>>;
  };
  approvalQueue?: Array<Record<string, unknown>>;
  lanes: MissionLaneVisual[];
  globalEvents: MissionCanvasEvent[];
}

export interface TimelineStep {
  id: string;
  stepId: string;
  turnIndex: number;
  phase: AgentPhase;
  type:
    | "plan"
    | "tool_call"
    | "tool_output"
    | "observation"
    | "thinking"
    | "permission"
    | "testing"
    | "error";
  title: string;
  status: "running" | "completed" | "failed" | "awaiting_approval";
  startedAt: string;
  completedAt?: string;
  durationMs?: number;
  toolName?: string;
  toolInput?: Record<string, unknown>;
  /** Incremental provider-emitted function arguments, kept separate from the result. */
  toolInputStream?: string;
  toolOutput?: string;
  toolId?: string;
  success?: boolean;
  diffStats?: {
    path: string;
    additions: number;
    deletions: number;
    diffLines?: Array<{ type: "added" | "removed" | "unchanged"; text: string }>;
  };
  details?: string;
  data?: Record<string, unknown>;
}

export interface DeepSpaceMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  rawContent: string;
  createdAt: string;
  status: "ready" | "streaming" | "error";
  blocks?: StructuredBlock[];
  structured?: StructuredAnswerShape | null;
  thinkingContent?: string;
  error?: {
    code: string;
    message: string;
    category?: "provider" | "tool" | "runtime" | "ui";
  } | null;

  // Versioning & Editing
  activeVersionId?: string | null;
  activeVersionIndex?: number;
  versionCount?: number;
  versions?: DeepSpaceHistoryVersion[];
  isEditing?: boolean;
  draftContent?: string | null;
  metrics?: MessageMetrics;
  agentSteps?: AgentStep[];
  timeline?: TimelineStep[];
  mission?: MissionCanvasState | null;
  compaction?: ConversationCompactionState | null;
  currentTurnText?: string;
  /** Answer submitted to an inline ask_user question, kept in the same run. */
  userQuestionAnswer?: string;
  /** The question text, used to remove a transient prompt from final content. */
  userQuestionPrompt?: string;
  readFilesContents?: Record<string, string>;
  memoryUsed?: Array<{ id: string; key: string; source?: string }>;
  artifacts?: DeepSpaceMediaArtifact[];
  mediaStatus?: DeepSpaceMediaStatus;
}

export interface DeepSpaceMediaArtifact {
  id: string;
  kind: "image" | "video" | "audio";
  status: "ready" | "pending" | "failed";
  title: string;
  content_type: string;
  size_bytes: number;
  url: string;
}

export interface DeepSpaceMediaStatus {
  phase: "queued" | "generating" | "uploading" | "ready" | "failed";
  message: string;
  artifactId?: string;
}

export interface AgentStep {
  id: string;
  type:
    | "plan"
    | "tool_start"
    | "tool_result"
    | "tool_error"
    | "observing"
    | "permission_request"
    | "thinking"
    | "agent_testing"
    | "agent_verifying"
    | "agent_self_correct"
    | "step_start"
    | "step_finish"
    | "ask_user_question";
  stepId?: string;
  toolName?: string;
  toolInput?: Record<string, unknown>;
  toolOutput?: string;
  toolId?: string;
  success?: boolean;
  durationMs?: number;
  permissionLevel?: string;
  plan?: string;
  tools?: string[];
  stepNumber?: number;
  status: "running" | "completed" | "failed" | "awaiting_approval";
  startedAt: string;
  completedAt?: string;
  data?: Record<string, unknown>;
  step_id?: string;
  tool_id?: string;
  turnIndex?: number;
  diffStats?: {
    path: string;
    additions: number;
    deletions: number;
    diffLines?: Array<{ type: "added" | "removed" | "unchanged"; text: string }>;
  };
}

export function createClientMessageId(prefix: "user" | "assistant"): string {
  const randomPart = Math.random().toString(36).slice(2, 10);
  return `${prefix}_${Date.now()}_${randomPart}`;
}

export function parseSseFrames(buffer: string): {
  events: DeepSpaceStreamEvent[];
  remainder: string;
} {
  const frames = buffer.split(/\n\n/);
  const remainder = frames.pop() ?? "";
  const events: DeepSpaceStreamEvent[] = [];

  for (const frame of frames) {
    const trimmed = frame.trim();
    if (!trimmed) continue;

    let eventName = "message";
    let eventSequence: number | undefined;
    const dataLines: string[] = [];

    for (const line of trimmed.split(/\n/)) {
      if (line.startsWith("event:")) {
        eventName = line.slice(6).trim();
      } else if (line.startsWith("id:")) {
        const parsedId = Number(line.slice(3).trim());
        if (Number.isFinite(parsedId) && parsedId >= 0) {
          eventSequence = parsedId;
        }
      } else if (line.startsWith("data:")) {
        dataLines.push(line.slice(5).trim());
      }
    }

    if (dataLines.length === 0) continue;

    try {
      const data = JSON.parse(dataLines.join("\n")) as Record<string, unknown>;
      if (eventSequence !== undefined && data.sequence === undefined) {
        data.sequence = eventSequence;
      }
      events.push({
        event: eventName as DeepSpaceStreamEvent["event"],
        data,
        sequence: eventSequence,
      });
    } catch {
      events.push({
        event: "error",
        data: {
          code: "STREAM_PARSE_ERROR",
          message: "Failed to parse stream frame.",
        },
      });
    }
  }

  return { events, remainder };
}
