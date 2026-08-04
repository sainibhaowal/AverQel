import {
  createClientMessageId,
  type AgentStep,
  type DeepSpaceHistoryMessage,
  type DeepSpaceHistoryVersion,
  type MissionCanvasEvent,
  type MissionCanvasState,
  type MissionLaneEvent,
  type MissionLaneStatus,
  type MissionLaneVisual,
  type MissionRuntimeState,
  type DeepSpaceMessage,
  type DeepSpaceMediaArtifact,
  type DeepSpaceStreamEvent,
  type TimelineStep,
  type AgentPhase,
  type ConversationCompactionState,
  type DurableMissionRuntimeState,
} from "./deepspace-stream";
import {
  estimateTokens,
  type MessageMetrics,
  type StructuredAnswerShape,
  type StructuredBlock,
} from "./deepspace-stream";
import { normalizeMarkdown } from "./markdown";
import { TOOL_LABELS } from "./constants";

function nowIso(): string {
  return new Date().toISOString();
}

function computeStepDurationMs(
  step: Pick<AgentStep, "startedAt" | "completedAt" | "durationMs">,
  completedAt: string,
): number | undefined {
  if (
    typeof step.durationMs === "number" &&
    Number.isFinite(step.durationMs) &&
    step.durationMs >= 0
  ) {
    return step.durationMs;
  }

  const startedAt = Date.parse(step.startedAt);
  const endedAt = Date.parse(completedAt);
  if (!Number.isFinite(startedAt) || !Number.isFinite(endedAt) || endedAt < startedAt) {
    return undefined;
  }

  return Math.max(0, endedAt - startedAt);
}

function finalizeAgentStep(
  step: AgentStep,
  completedAt: string,
  status: "completed" | "failed",
): AgentStep {
  return {
    ...step,
    status,
    completedAt: step.completedAt ?? completedAt,
    durationMs: computeStepDurationMs(step, step.completedAt ?? completedAt),
  };
}

function readStringList(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map((item) => (typeof item === "string" ? item.trim() : String(item ?? "").trim()))
    .filter(Boolean);
}

function readMissionStatus(value: unknown): MissionCanvasState["status"] {
  const normalized = typeof value === "string" ? value.trim().toLowerCase() : "";
  if (
    normalized === "planning" ||
    normalized === "running" ||
    normalized === "awaiting_approval" ||
    normalized === "completed" ||
    normalized === "failed" ||
    normalized === "cancelled"
  ) {
    return normalized;
  }
  return "running";
}

function readLaneStatus(value: unknown): MissionLaneStatus {
  const normalized = typeof value === "string" ? value.trim().toLowerCase() : "";
  if (
    normalized === "planned" ||
    normalized === "running" ||
    normalized === "awaiting_approval" ||
    normalized === "completed" ||
    normalized === "failed" ||
    normalized === "cancelled" ||
    normalized === "blocked"
  ) {
    return normalized;
  }
  return "planned";
}

function ensureMissionGlobalEvent(
  globalEvents: MissionCanvasEvent[],
  event: MissionCanvasEvent,
): MissionCanvasEvent[] {
  if (
    globalEvents.some(
      (existing) =>
        existing.kind === event.kind &&
        existing.laneId === event.laneId &&
        existing.message === event.message,
    )
  ) {
    return globalEvents;
  }
  return [...globalEvents, event];
}

function ensureLaneEvent(events: MissionLaneEvent[], event: MissionLaneEvent): MissionLaneEvent[] {
  if (
    events.some(
      (existing) =>
        existing.kind === event.kind &&
        existing.message === event.message &&
        existing.status === event.status,
    )
  ) {
    return events;
  }
  return [...events, event];
}

function laneLayerRank(laneType: string, metadata?: Record<string, unknown>): number {
  if (laneType === "main_chat") {
    return 0;
  }
  if (laneType === "support" || metadata?.role === "support") {
    return 1;
  }
  if (
    laneType === "research" ||
    laneType === "analysis" ||
    laneType === "planner" ||
    laneType === "file"
  ) {
    return 2;
  }
  if (laneType === "writer" || laneType === "executor") {
    return 3;
  }
  return 4;
}

function sortMissionLanes(lanes: MissionLaneVisual[]): MissionLaneVisual[] {
  return [...lanes].sort((a, b) => {
    const layerDiff = laneLayerRank(a.laneType, a.metadata) - laneLayerRank(b.laneType, b.metadata);
    if (layerDiff !== 0) {
      return layerDiff;
    }
    if (a.priority !== b.priority) {
      return b.priority - a.priority;
    }
    return a.laneId.localeCompare(b.laneId);
  });
}

function buildLaneFromBlueprint(blueprint: Record<string, unknown>): MissionLaneVisual | null {
  const laneId = String(blueprint.lane_id ?? blueprint.ref ?? "").trim();
  if (!laneId) {
    return null;
  }
  return {
    laneId,
    laneType: String(blueprint.lane_type ?? "task"),
    title: String(blueprint.title ?? laneId),
    prompt: String(blueprint.prompt ?? ""),
    priority: typeof blueprint.priority === "number" ? blueprint.priority : 0,
    status: readLaneStatus(blueprint.status ?? "planned"),
    dependsOn: readStringList(blueprint.depends_on),
    blockedBy: readStringList(blueprint.blocked_by),
    subagentType:
      blueprint.subagent_type === null || blueprint.subagent_type === undefined
        ? null
        : String(blueprint.subagent_type),
    metadata:
      blueprint.metadata &&
      typeof blueprint.metadata === "object" &&
      !Array.isArray(blueprint.metadata)
        ? (blueprint.metadata as Record<string, unknown>)
        : undefined,
    summary: typeof blueprint.summary === "string" ? blueprint.summary : undefined,
    output: typeof blueprint.output === "string" ? blueprint.output : undefined,
    events: [],
  };
}

function readMissionRuntimeState(value: unknown): MissionRuntimeState | undefined {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return undefined;
  }
  const runtime = value as Record<string, unknown>;
  const diagnostics =
    runtime.diagnostics &&
    typeof runtime.diagnostics === "object" &&
    !Array.isArray(runtime.diagnostics)
      ? (runtime.diagnostics as Record<string, unknown>)
      : null;
  return {
    plannerMode: typeof runtime.planner_mode === "string" ? runtime.planner_mode : undefined,
    plannerValidationStatus:
      typeof runtime.planner_validation_status === "string"
        ? (runtime.planner_validation_status as MissionRuntimeState["plannerValidationStatus"])
        : undefined,
    runtimeHooksState:
      typeof runtime.runtime_hooks_state === "string"
        ? (runtime.runtime_hooks_state as MissionRuntimeState["runtimeHooksState"])
        : undefined,
    subagentProfile:
      typeof runtime.subagent_profile === "string" ? runtime.subagent_profile : undefined,
    subagentProfileClassification:
      typeof runtime.subagent_profile_classification === "string"
        ? (runtime.subagent_profile_classification as MissionRuntimeState["subagentProfileClassification"])
        : undefined,
    diagnostics: diagnostics
      ? {
          planner:
            diagnostics.planner &&
            typeof diagnostics.planner === "object" &&
            !Array.isArray(diagnostics.planner)
              ? {
                  source:
                    typeof (diagnostics.planner as Record<string, unknown>).source === "string"
                      ? String((diagnostics.planner as Record<string, unknown>).source)
                      : undefined,
                  mode:
                    typeof (diagnostics.planner as Record<string, unknown>).mode === "string"
                      ? String((diagnostics.planner as Record<string, unknown>).mode)
                      : undefined,
                  laneCount:
                    typeof (diagnostics.planner as Record<string, unknown>).lane_count === "number"
                      ? Number((diagnostics.planner as Record<string, unknown>).lane_count)
                      : typeof (diagnostics.planner as Record<string, unknown>).laneCount ===
                          "number"
                        ? Number((diagnostics.planner as Record<string, unknown>).laneCount)
                        : undefined,
                  parallelLimit:
                    typeof (diagnostics.planner as Record<string, unknown>).parallel_limit ===
                    "number"
                      ? Number((diagnostics.planner as Record<string, unknown>).parallel_limit)
                      : typeof (diagnostics.planner as Record<string, unknown>).parallelLimit ===
                          "number"
                        ? Number((diagnostics.planner as Record<string, unknown>).parallelLimit)
                        : undefined,
                  gatedActionsDetected:
                    typeof (diagnostics.planner as Record<string, unknown>)
                      .gated_actions_detected === "boolean"
                      ? Boolean(
                          (diagnostics.planner as Record<string, unknown>).gated_actions_detected,
                        )
                      : typeof (diagnostics.planner as Record<string, unknown>)
                            .gatedActionsDetected === "boolean"
                        ? Boolean(
                            (diagnostics.planner as Record<string, unknown>).gatedActionsDetected,
                          )
                        : undefined,
                  dynamicFanout:
                    typeof (diagnostics.planner as Record<string, unknown>).dynamic_fanout ===
                    "number"
                      ? Number((diagnostics.planner as Record<string, unknown>).dynamic_fanout)
                      : typeof (diagnostics.planner as Record<string, unknown>).dynamicFanout ===
                          "number"
                        ? Number((diagnostics.planner as Record<string, unknown>).dynamicFanout)
                        : undefined,
                }
              : undefined,
          hooks:
            diagnostics.hooks &&
            typeof diagnostics.hooks === "object" &&
            !Array.isArray(diagnostics.hooks)
              ? {
                  active:
                    typeof (diagnostics.hooks as Record<string, unknown>).active === "boolean"
                      ? Boolean((diagnostics.hooks as Record<string, unknown>).active)
                      : undefined,
                  counts:
                    (diagnostics.hooks as Record<string, unknown>).counts &&
                    typeof (diagnostics.hooks as Record<string, unknown>).counts === "object" &&
                    !Array.isArray((diagnostics.hooks as Record<string, unknown>).counts)
                      ? ((diagnostics.hooks as Record<string, unknown>).counts as Record<
                          string,
                          number
                        >)
                      : undefined,
                  recent: Array.isArray((diagnostics.hooks as Record<string, unknown>).recent)
                    ? (
                        (diagnostics.hooks as Record<string, unknown>).recent as Array<
                          Record<string, unknown>
                        >
                      ).map((item) => ({
                        phase: typeof item.phase === "string" ? item.phase : undefined,
                        hook: typeof item.hook === "string" ? item.hook : undefined,
                        status: typeof item.status === "string" ? item.status : undefined,
                        changedFields: readStringList(item.changed_fields ?? item.changedFields),
                        toolName:
                          typeof item.tool_name === "string"
                            ? item.tool_name
                            : typeof item.toolName === "string"
                              ? item.toolName
                              : undefined,
                      }))
                    : undefined,
                }
              : undefined,
          policy:
            diagnostics.policy &&
            typeof diagnostics.policy === "object" &&
            !Array.isArray(diagnostics.policy)
              ? {
                  counts:
                    (diagnostics.policy as Record<string, unknown>).counts &&
                    typeof (diagnostics.policy as Record<string, unknown>).counts === "object" &&
                    !Array.isArray((diagnostics.policy as Record<string, unknown>).counts)
                      ? {
                          allow: Number(
                            (
                              (diagnostics.policy as Record<string, unknown>).counts as Record<
                                string,
                                unknown
                              >
                            ).allow ?? 0,
                          ),
                          approval: Number(
                            (
                              (diagnostics.policy as Record<string, unknown>).counts as Record<
                                string,
                                unknown
                              >
                            ).approval ?? 0,
                          ),
                          block: Number(
                            (
                              (diagnostics.policy as Record<string, unknown>).counts as Record<
                                string,
                                unknown
                              >
                            ).block ?? 0,
                          ),
                        }
                      : undefined,
                  recent: Array.isArray((diagnostics.policy as Record<string, unknown>).recent)
                    ? (
                        (diagnostics.policy as Record<string, unknown>).recent as Array<
                          Record<string, unknown>
                        >
                      ).map((item) => ({
                        toolName:
                          typeof item.tool_name === "string"
                            ? item.tool_name
                            : typeof item.toolName === "string"
                              ? item.toolName
                              : undefined,
                        decision: typeof item.decision === "string" ? item.decision : undefined,
                        reason: typeof item.reason === "string" ? item.reason : undefined,
                        tier: typeof item.tier === "number" ? item.tier : undefined,
                        mode: typeof item.mode === "string" ? item.mode : undefined,
                        argKeys: readStringList(item.arg_keys ?? item.argKeys),
                      }))
                    : undefined,
                }
              : undefined,
          memory:
            diagnostics.memory &&
            typeof diagnostics.memory === "object" &&
            !Array.isArray(diagnostics.memory)
              ? {
                  recent: Array.isArray((diagnostics.memory as Record<string, unknown>).recent)
                    ? (
                        (diagnostics.memory as Record<string, unknown>).recent as Array<
                          Record<string, unknown>
                        >
                      ).map((item) => ({
                        kind: typeof item.kind === "string" ? item.kind : undefined,
                        count: typeof item.count === "number" ? item.count : undefined,
                        fastBootstrap:
                          typeof item.fast_bootstrap === "boolean"
                            ? item.fast_bootstrap
                            : typeof item.fastBootstrap === "boolean"
                              ? item.fastBootstrap
                              : undefined,
                      }))
                    : undefined,
                }
              : undefined,
          compaction:
            diagnostics.compaction &&
            typeof diagnostics.compaction === "object" &&
            !Array.isArray(diagnostics.compaction)
              ? {
                  latest:
                    (diagnostics.compaction as Record<string, unknown>).latest &&
                    typeof (diagnostics.compaction as Record<string, unknown>).latest ===
                      "object" &&
                    !Array.isArray((diagnostics.compaction as Record<string, unknown>).latest)
                      ? ((diagnostics.compaction as Record<string, unknown>).latest as Record<
                          string,
                          unknown
                        >)
                      : null,
                  recent: Array.isArray((diagnostics.compaction as Record<string, unknown>).recent)
                    ? ((diagnostics.compaction as Record<string, unknown>).recent as Array<
                        Record<string, unknown>
                      >)
                    : undefined,
                }
              : undefined,
          toolDensity:
            diagnostics.tool_density &&
            typeof diagnostics.tool_density === "object" &&
            !Array.isArray(diagnostics.tool_density)
              ? {
                  started: Number(
                    (diagnostics.tool_density as Record<string, unknown>).started ?? 0,
                  ),
                  completed: Number(
                    (diagnostics.tool_density as Record<string, unknown>).completed ?? 0,
                  ),
                  failed: Number((diagnostics.tool_density as Record<string, unknown>).failed ?? 0),
                  blocked: Number(
                    (diagnostics.tool_density as Record<string, unknown>).blocked ?? 0,
                  ),
                  awaitingApproval: Number(
                    (diagnostics.tool_density as Record<string, unknown>).awaiting_approval ??
                      (diagnostics.tool_density as Record<string, unknown>).awaitingApproval ??
                      0,
                  ),
                }
              : undefined,
        }
      : undefined,
  };
}

function mergeMissionRuntimeState(
  current: MissionRuntimeState | undefined,
  incoming: MissionRuntimeState | undefined,
): MissionRuntimeState | undefined {
  if (!current) {
    return incoming;
  }
  if (!incoming) {
    return current;
  }
  return {
    plannerMode: incoming.plannerMode ?? current.plannerMode,
    plannerValidationStatus: incoming.plannerValidationStatus ?? current.plannerValidationStatus,
    runtimeHooksState: incoming.runtimeHooksState ?? current.runtimeHooksState,
    subagentProfile: incoming.subagentProfile ?? current.subagentProfile,
    subagentProfileClassification:
      incoming.subagentProfileClassification ?? current.subagentProfileClassification,
    diagnostics: {
      ...(current.diagnostics ?? {}),
      ...(incoming.diagnostics ?? {}),
      planner: {
        ...(current.diagnostics?.planner ?? {}),
        ...(incoming.diagnostics?.planner ?? {}),
      },
      hooks: {
        ...(current.diagnostics?.hooks ?? {}),
        ...(incoming.diagnostics?.hooks ?? {}),
      },
      policy: {
        ...(current.diagnostics?.policy ?? {}),
        ...(incoming.diagnostics?.policy ?? {}),
      },
      memory: {
        ...(current.diagnostics?.memory ?? {}),
        ...(incoming.diagnostics?.memory ?? {}),
      },
      compaction: {
        ...(current.diagnostics?.compaction ?? {}),
        ...(incoming.diagnostics?.compaction ?? {}),
      },
      toolDensity: {
        ...(current.diagnostics?.toolDensity ?? {}),
        ...(incoming.diagnostics?.toolDensity ?? {}),
      },
    },
  };
}

function readConversationCompactionState(value: unknown): ConversationCompactionState | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  const raw = value as Record<string, unknown>;
  const compactedAt =
    typeof raw.compacted_at === "string"
      ? raw.compacted_at
      : typeof raw.compactedAt === "string"
        ? raw.compactedAt
        : "";
  if (!compactedAt) {
    return null;
  }
  return {
    version: typeof raw.version === "number" ? raw.version : 1,
    trigger:
      typeof raw.trigger === "string" && raw.trigger.trim().length > 0 ? raw.trigger : "manual",
    compactedAt,
    anchorMessageId:
      typeof raw.anchor_message_id === "string"
        ? raw.anchor_message_id
        : typeof raw.anchorMessageId === "string"
          ? raw.anchorMessageId
          : null,
    summary: typeof raw.summary === "string" ? raw.summary : "",
    summarizedCount:
      typeof raw.summarized_count === "number"
        ? raw.summarized_count
        : typeof raw.summarizedCount === "number"
          ? raw.summarizedCount
          : 0,
    keptRecentCount:
      typeof raw.kept_recent_count === "number"
        ? raw.kept_recent_count
        : typeof raw.keptRecentCount === "number"
          ? raw.keptRecentCount
          : 0,
    beforeTokens:
      typeof raw.before_tokens === "number"
        ? raw.before_tokens
        : typeof raw.beforeTokens === "number"
          ? raw.beforeTokens
          : 0,
    afterTokens:
      typeof raw.after_tokens === "number"
        ? raw.after_tokens
        : typeof raw.afterTokens === "number"
          ? raw.afterTokens
          : 0,
    savedTokens:
      typeof raw.saved_tokens === "number"
        ? raw.saved_tokens
        : typeof raw.savedTokens === "number"
          ? raw.savedTokens
          : 0,
  };
}

function upsertMissionLane(
  mission: MissionCanvasState,
  laneId: string,
  updater: (lane: MissionLaneVisual | null) => MissionLaneVisual,
): MissionCanvasState {
  const existingLane = mission.lanes.find((lane) => lane.laneId === laneId) ?? null;
  const nextLane = updater(existingLane);
  const nextLanes = existingLane
    ? mission.lanes.map((lane) => (lane.laneId === laneId ? nextLane : lane))
    : [...mission.lanes, nextLane];
  return {
    ...mission,
    lanes: sortMissionLanes(nextLanes),
  };
}

function createMissionEvent(
  kind: MissionCanvasEvent["kind"],
  message: string,
  data: Record<string, unknown>,
): MissionCanvasEvent {
  const at = typeof data.timestamp === "string" ? data.timestamp : nowIso();
  return {
    id: `${kind}_${data.mission_id ?? "mission"}_${data.lane_id ?? "global"}_${at}`,
    kind,
    message,
    at,
    laneId: typeof data.lane_id === "string" ? data.lane_id : undefined,
  };
}

function createLaneEvent(
  kind: MissionLaneEvent["kind"],
  message: string,
  data: Record<string, unknown>,
  status?: MissionLaneStatus,
): MissionLaneEvent {
  const at = typeof data.timestamp === "string" ? data.timestamp : nowIso();
  return {
    id: `${kind}_${data.lane_id ?? "lane"}_${at}_${message.slice(0, 24)}`,
    kind,
    message,
    at,
    status,
    toolName: typeof data.tool_name === "string" ? data.tool_name : undefined,
  };
}

function updateDurableMissionRuntime(
  current: DurableMissionRuntimeState | undefined,
  event: DeepSpaceStreamEvent,
): DurableMissionRuntimeState | undefined {
  const data = event.data;
  const durableEventType =
    typeof data.durable_event_type === "string" ? data.durable_event_type : "";
  const runId = typeof data.durable_run_id === "string" ? data.durable_run_id : current?.runId;
  if (!runId && !current) return undefined;
  const sequence = typeof data.sequence === "number" ? data.sequence : (current?.lastSequence ?? 0);
  const transportState =
    typeof data.durable_transport_state === "string" ? data.durable_transport_state : "connected";
  const approvalDelta =
    durableEventType === "approval_requested" || durableEventType === "run_paused_for_approval"
      ? 1
      : durableEventType === "approval_resolved"
        ? -1
        : 0;
  return {
    runId: runId ?? "",
    status:
      typeof data.status === "string"
        ? data.status
        : durableEventType === "run_completed"
          ? "completed"
          : durableEventType === "run_failed"
            ? "failed"
            : durableEventType === "run_cancelled"
              ? "cancelled"
              : current?.status,
    lastSequence: Math.max(current?.lastSequence ?? 0, sequence),
    checkpointSequence:
      typeof data.checkpoint_sequence === "number"
        ? Math.max(current?.checkpointSequence ?? 0, data.checkpoint_sequence)
        : current?.checkpointSequence,
    continuationEpoch:
      typeof data.continuation_epoch === "number"
        ? Math.max(current?.continuationEpoch ?? 0, data.continuation_epoch)
        : current?.continuationEpoch,
    recoveryCount:
      typeof data.recovery_count === "number"
        ? Math.max(current?.recoveryCount ?? 0, data.recovery_count)
        : current?.recoveryCount,
    pendingApprovals: Math.max(0, (current?.pendingApprovals ?? 0) + approvalDelta),
    reconnectState:
      transportState === "reconnecting" || transportState === "interrupted"
        ? transportState
        : "connected",
    budgetUsage:
      data.budget_usage && typeof data.budget_usage === "object"
        ? (data.budget_usage as Record<string, number>)
        : current?.budgetUsage,
    budgetLimits:
      data.budget_limits && typeof data.budget_limits === "object"
        ? (data.budget_limits as Record<string, number>)
        : current?.budgetLimits,
    supervisorDecision:
      typeof data.supervisor_decision === "string"
        ? data.supervisor_decision
        : current?.supervisorDecision,
    replayReadOnly: true,
  };
}

function updateMissionCanvas(
  mission: MissionCanvasState | null | undefined,
  event: DeepSpaceStreamEvent,
): MissionCanvasState | null | undefined {
  const data = event.data;

  if (event.event === "mission_start") {
    const startedAt = typeof data.started_at === "string" ? data.started_at : nowIso();
    return {
      missionId: String(data.mission_id ?? ""),
      objective: String(data.objective ?? ""),
      status: "planning",
      phase: "planning",
      executionMode: typeof data.execution_mode === "string" ? data.execution_mode : undefined,
      plannerSource: typeof data.planner_source === "string" ? data.planner_source : undefined,
      summary: "Mission initializing.",
      startedAt,
      lastUpdatedAt: startedAt,
      runtimeState: readMissionRuntimeState(data.runtime_state),
      durableRuntime:
        typeof data.durable_run_id === "string"
          ? {
              runId: data.durable_run_id,
              status: typeof data.status === "string" ? data.status : "planning",
              lastSequence: typeof data.sequence === "number" ? data.sequence : 0,
              reconnectState: "connected",
              replayReadOnly: true,
            }
          : undefined,
      approvalQueue: [],
      lanes: [],
      globalEvents: [
        createMissionEvent("mission_start", String(data.objective ?? "Mission started."), data),
      ],
    };
  }

  if (!mission) {
    return mission;
  }

  const stamp = typeof data.timestamp === "string" ? data.timestamp : nowIso();
  const nextBase: MissionCanvasState = {
    ...mission,
    lastUpdatedAt: stamp,
    durableRuntime: updateDurableMissionRuntime(mission.durableRuntime, event),
  };

  if (event.event === "mission_planning") {
    return {
      ...nextBase,
      status: readMissionStatus(data.status ?? "planning"),
      phase: "planning",
      summary: String(data.message ?? "Building mission plan."),
      executionMode:
        typeof data.execution_mode === "string" ? data.execution_mode : nextBase.executionMode,
      runtimeState: mergeMissionRuntimeState(
        nextBase.runtimeState,
        readMissionRuntimeState(data.runtime_state),
      ),
      globalEvents: ensureMissionGlobalEvent(
        nextBase.globalEvents,
        createMissionEvent(
          "mission_planning",
          String(data.message ?? "Building mission plan."),
          data,
        ),
      ),
    };
  }

  if (event.event === "mission_plan") {
    const rawPlan =
      data.plan && typeof data.plan === "object" && !Array.isArray(data.plan)
        ? (data.plan as Record<string, unknown>)
        : {};
    const planLanes = Array.isArray(rawPlan.lanes)
      ? rawPlan.lanes
          .map((lane) =>
            lane && typeof lane === "object"
              ? buildLaneFromBlueprint(lane as Record<string, unknown>)
              : null,
          )
          .filter((lane): lane is MissionLaneVisual => lane !== null)
      : nextBase.lanes;
    return {
      ...nextBase,
      status: "running",
      phase: "graph_ready",
      plannerSource:
        typeof data.planner_source === "string"
          ? data.planner_source
          : typeof rawPlan.planner_source === "string"
            ? rawPlan.planner_source
            : nextBase.plannerSource,
      summary: typeof rawPlan.summary === "string" ? rawPlan.summary : "Mission plan materialized.",
      signals:
        rawPlan.signals && typeof rawPlan.signals === "object"
          ? (rawPlan.signals as Record<string, unknown>)
          : nextBase.signals,
      runtimeState: mergeMissionRuntimeState(
        nextBase.runtimeState,
        readMissionRuntimeState(data.runtime_state ?? rawPlan.runtime_state),
      ),
      approvalQueue: Array.isArray(rawPlan.approval_queue)
        ? (rawPlan.approval_queue as Array<Record<string, unknown>>)
        : nextBase.approvalQueue,
      graph:
        rawPlan.graph && typeof rawPlan.graph === "object"
          ? (rawPlan.graph as MissionCanvasState["graph"])
          : nextBase.graph,
      lanes: sortMissionLanes(planLanes),
      globalEvents: ensureMissionGlobalEvent(
        nextBase.globalEvents,
        createMissionEvent(
          "mission_plan",
          typeof rawPlan.summary === "string" ? rawPlan.summary : "Mission plan created.",
          data,
        ),
      ),
    };
  }

  if (event.event === "mission_graph") {
    return {
      ...nextBase,
      phase: "executing",
      graph:
        data.graph && typeof data.graph === "object"
          ? (data.graph as MissionCanvasState["graph"])
          : nextBase.graph,
      signals:
        data.signals && typeof data.signals === "object"
          ? (data.signals as Record<string, unknown>)
          : nextBase.signals,
      runtimeState: mergeMissionRuntimeState(
        nextBase.runtimeState,
        readMissionRuntimeState(data.runtime_state),
      ),
      globalEvents: ensureMissionGlobalEvent(
        nextBase.globalEvents,
        createMissionEvent("mission_graph", "Mission graph published.", data),
      ),
    };
  }

  if (event.event === "mission_summary") {
    return {
      ...nextBase,
      status: readMissionStatus(data.status ?? nextBase.status),
      phase:
        data.status === "cancelled"
          ? "cancelled"
          : data.status === "failed"
            ? "failed"
            : data.status === "completed"
              ? "completed"
              : nextBase.phase,
      summary: String(data.summary ?? data.message ?? nextBase.summary ?? ""),
      runtimeState: mergeMissionRuntimeState(
        nextBase.runtimeState,
        readMissionRuntimeState(data.runtime_state),
      ),
      globalEvents: ensureMissionGlobalEvent(
        nextBase.globalEvents,
        createMissionEvent(
          "mission_summary",
          String(data.summary ?? data.message ?? "Mission summary updated."),
          data,
        ),
      ),
    };
  }

  if (event.event === "mission_done") {
    return {
      ...nextBase,
      status: readMissionStatus(data.status ?? "completed"),
      phase:
        data.status === "cancelled"
          ? "cancelled"
          : data.status === "failed"
            ? "failed"
            : "completed",
      completedAt: stamp,
      summary: String(data.summary ?? nextBase.summary ?? "Mission complete."),
      runtimeState: mergeMissionRuntimeState(
        nextBase.runtimeState,
        readMissionRuntimeState(data.runtime_state),
      ),
      globalEvents: ensureMissionGlobalEvent(
        nextBase.globalEvents,
        createMissionEvent(
          "mission_done",
          String(data.summary ?? data.message ?? "Mission complete."),
          data,
        ),
      ),
    };
  }

  if (event.event === "approval_request") {
    const laneId = String(data.lane_id ?? "");
    const updatedMission = laneId
      ? upsertMissionLane(nextBase, laneId, (lane) => {
          const baseLane =
            lane ??
            ({
              laneId,
              laneType: String(data.lane_type ?? "task"),
              title: String(data.lane_type ?? laneId),
              prompt: "",
              priority: 0,
              status: "awaiting_approval" as MissionLaneStatus,
              dependsOn: [],
              blockedBy: [],
              events: [],
            } satisfies MissionLaneVisual);
          return {
            ...baseLane,
            status: "awaiting_approval",
            events: ensureLaneEvent(
              baseLane.events,
              createLaneEvent(
                "approval_request",
                String(data.message ?? "Approval required."),
                data,
                "awaiting_approval",
              ),
            ),
          };
        })
      : nextBase;
    return {
      ...updatedMission,
      status: "awaiting_approval",
      phase: "awaiting_approval",
      approvalQueue: [
        ...((updatedMission.approvalQueue ?? []).filter(
          (item) => String(item.lane_id ?? "") !== laneId,
        ) as Array<Record<string, unknown>>),
        data,
      ],
      globalEvents: ensureMissionGlobalEvent(
        updatedMission.globalEvents,
        createMissionEvent("approval_request", String(data.message ?? "Approval required."), data),
      ),
    };
  }

  const laneId = String(data.lane_id ?? "");
  if (!laneId) {
    return nextBase;
  }

  const currentStatus = (() => {
    switch (event.event) {
      case "lane_start":
      case "lane_delta":
      case "lane_thinking":
      case "lane_agent_thinking":
      case "lane_step_summary":
      case "lane_observation":
        return "running" as const;
      case "lane_result":
        return readLaneStatus(data.status ?? "completed");
      case "lane_error":
        return "failed" as const;
      case "lane_blocked":
        return "blocked" as const;
      default:
        return "planned" as const;
    }
  })();

  return upsertMissionLane(nextBase, laneId, (lane) => {
    const baseLane =
      lane ??
      ({
        laneId,
        laneType: String(data.lane_type ?? "task"),
        title: String(data.title ?? laneId),
        prompt: String(data.prompt ?? ""),
        priority: 0,
        status: currentStatus,
        dependsOn: [],
        blockedBy: [],
        subagentType: typeof data.subagent_type === "string" ? data.subagent_type : null,
        events: [],
      } satisfies MissionLaneVisual);

    const message =
      String(
        data.message ??
          data.summary ??
          data.output ??
          data.text ??
          data.error ??
          `${baseLane.title} updated.`,
      ).trim() || `${baseLane.title} updated.`;

    return {
      ...baseLane,
      laneType: String(data.lane_type ?? baseLane.laneType),
      title: String(data.title ?? baseLane.title),
      prompt: String(data.prompt ?? baseLane.prompt),
      subagentType:
        data.subagent_type === undefined
          ? typeof (data.metadata as Record<string, unknown> | undefined)
              ?.resolved_subagent_type === "string"
            ? String((data.metadata as Record<string, unknown>).resolved_subagent_type)
            : baseLane.subagentType
          : data.subagent_type === null
            ? null
            : String(data.subagent_type),
      metadata:
        data.metadata && typeof data.metadata === "object" && !Array.isArray(data.metadata)
          ? {
              ...(baseLane.metadata ?? {}),
              ...(data.metadata as Record<string, unknown>),
            }
          : baseLane.metadata,
      status: currentStatus,
      summary:
        typeof data.summary === "string" && data.summary.trim()
          ? data.summary
          : event.event === "lane_result"
            ? message
            : baseLane.summary,
      output: typeof data.output === "string" && data.output.trim() ? data.output : baseLane.output,
      latestText:
        typeof data.text === "string" && data.text.trim()
          ? data.text
          : typeof data.message === "string" && data.message.trim()
            ? data.message
            : baseLane.latestText,
      error:
        typeof data.error === "string" && data.error.trim()
          ? data.error
          : event.event === "lane_error"
            ? message
            : baseLane.error,
      startedAt: event.event === "lane_start" ? stamp : (baseLane.startedAt ?? stamp),
      completedAt:
        event.event === "lane_result" ||
        event.event === "lane_error" ||
        event.event === "lane_blocked"
          ? stamp
          : baseLane.completedAt,
      events: ensureLaneEvent(
        baseLane.events,
        createLaneEvent(event.event as MissionLaneEvent["kind"], message, data, currentStatus),
      ),
    };
  });
}

function upsertTimelineStep(timeline: TimelineStep[], incoming: TimelineStep): TimelineStep[] {
  // A thinking entry is an ordered stream segment, not one message-wide
  // bucket. Only append to the immediately preceding active segment; a tool,
  // plan, observation, or verification event deliberately starts the next
  // thinking segment so users can see the real execution chain.
  const lastIndex = timeline.length - 1;
  const last = timeline[lastIndex];
  const index =
    incoming.type === "thinking"
      ? last &&
        last.type === "thinking" &&
        last.status === "running" &&
        last.turnIndex === incoming.turnIndex
        ? lastIndex
        : -1
      : timeline.findIndex(
          (step) =>
            step.type === incoming.type &&
            (step.stepId === incoming.stepId ||
              (step.toolId && incoming.toolId && step.toolId === incoming.toolId)),
        );

  let nextTimeline = [...timeline];

  if (index === -1) {
    // Any non-thinking event closes the preceding thought segment while a
    // tool is prepared or executed. This preserves the visible order without
    // incorrectly ending a running tool when a status update arrives.
    if (incoming.type !== "thinking") {
      nextTimeline = nextTimeline.map((step) =>
        step.type === "thinking" && step.status === "running"
          ? { ...step, status: "completed" as const, completedAt: incoming.startedAt }
          : step,
      );
    }
    return [...nextTimeline, incoming];
  }

  const existing = nextTimeline[index]!;

  nextTimeline[index] = {
    ...existing,
    ...incoming,
    startedAt: existing.startedAt || incoming.startedAt,
    status:
      incoming.status === "running" &&
      (existing.status === "completed" || existing.status === "failed")
        ? existing.status
        : incoming.status,
    toolOutput: incoming.toolOutput
      ? appendStreamingText(existing.toolOutput, incoming.toolOutput)
      : existing.toolOutput,
    toolInputStream: incoming.toolInputStream
      ? appendStreamingText(existing.toolInputStream, incoming.toolInputStream)
      : existing.toolInputStream,
    details:
      incoming.type === "thinking"
        ? appendStreamingText(existing.details, incoming.details ?? "")
        : (incoming.details ?? existing.details),
    durationMs: incoming.durationMs ?? existing.durationMs,
    completedAt: incoming.completedAt ?? existing.completedAt,
    success: incoming.success ?? existing.success,
  };

  return nextTimeline;
}

let timelineFallbackSequence = 0;

function mapEventToTimelineStep(event: DeepSpaceStreamEvent): TimelineStep | null {
  const data = event.data;
  const turnIndex = typeof data.turn_index === "number" ? data.turn_index : 0;
  // Status/observation events do not all have a backend step id. A monotonic
  // client fallback prevents two adjacent events received in the same
  // millisecond from being merged into one timeline row.
  const stepId = String(
    data.step_id ?? data.stepNumber ?? `${event.event}_${++timelineFallbackSequence}`,
  );
  const phase = (data.phase as AgentPhase) || "exploring";
  const timestamp = String(data.timestamp || new Date().toISOString());

  switch (event.event) {
    case "agent_plan":
      return {
        id: `plan_${stepId}`,
        stepId,
        turnIndex,
        phase: "planning",
        type: "plan",
        title: String(data.title ?? data.message ?? "Strategic Plan"),
        status: "completed",
        startedAt: timestamp,
        completedAt: timestamp,
        details: String(data.plan ?? ""),
      };
    case "tool_start":
    case "tool_delta": {
      const toolName = String(data.tool_name ?? "");
      const title =
        data.message && data.message !== "Execution step started."
          ? String(data.message)
          : toolName
            ? (TOOL_LABELS[toolName] ?? toolName.replace(/_/g, " "))
            : "Executing Tool";
      return {
        id: `tool_${data.tool_id ?? stepId}`,
        stepId,
        turnIndex,
        phase,
        type: "tool_call",
        title,
        status: "running",
        startedAt: timestamp,
        toolName,
        toolInput: (data.tool_input as Record<string, unknown>) ?? {},
        toolId: String(data.tool_id ?? ""),
        toolInputStream: event.event === "tool_delta" ? String(data.text ?? "") : undefined,
      };
    }
    case "tool_result": {
      const toolName = String(data.tool_name ?? "");
      const title =
        data.message && data.message !== "Execution step started."
          ? String(data.message)
          : toolName
            ? (TOOL_LABELS[toolName] ?? toolName.replace(/_/g, " "))
            : "Tool Result";
      return {
        id: `tool_${data.tool_id ?? stepId}`,
        stepId,
        turnIndex,
        phase,
        type: "tool_call",
        title,
        status: data.success ? "completed" : "failed",
        startedAt: timestamp,
        completedAt: String(data.completed_at || timestamp),
        durationMs: typeof data.duration_ms === "number" ? data.duration_ms : undefined,
        toolName,
        toolInput: (data.tool_input as Record<string, unknown>) ?? {},
        toolOutput: String(data.output ?? ""),
        toolId: String(data.tool_id ?? ""),
        success: Boolean(data.success),
      };
    }
    case "thinking":
    case "lane_thinking":
    case "lane_agent_thinking":
    case "agent_thinking":
      return {
        id: `think_${stepId}`,
        stepId,
        turnIndex,
        phase: "thinking",
        type: "thinking",
        title: "Internal Thought",
        status: data.status === "completed" ? "completed" : "running",
        startedAt: timestamp,
        completedAt: data.status === "completed" ? timestamp : undefined,
        details: String(data.text ?? ""),
        durationMs: typeof data.duration_ms === "number" ? data.duration_ms : undefined,
      };
    // These legacy server events contain fixed descriptive text, not a model
    // function call or a real tool result. Keep them out of the agent timeline.
    case "agent_status":
    case "observing":
      return null;
    case "permission_request":
    case "ask_user_question":
      return {
        id: `perm_${data.tool_id ?? stepId}`,
        stepId,
        turnIndex,
        phase,
        type: "permission",
        title: event.event === "ask_user_question" ? "Clarification Needed" : "Clearance Required",
        status: "awaiting_approval",
        startedAt: timestamp,
        toolName: String(data.tool_name ?? ""),
        toolInput: (data.tool_input as Record<string, unknown>) ?? {},
        toolId: String(data.tool_id ?? ""),
        details: String(data.message ?? ""),
        data: event.data,
      };
    case "permission_granted":
    case "permission_denied":
      return {
        id: `perm_${data.tool_id ?? stepId}`,
        stepId,
        turnIndex,
        phase,
        type: "permission",
        title: event.event === "permission_granted" ? "Approval granted" : "Approval denied",
        status: event.event === "permission_granted" ? "running" : "failed",
        startedAt: timestamp,
        completedAt: event.event === "permission_denied" ? timestamp : undefined,
        toolName: String(data.tool_name ?? ""),
        toolId: String(data.tool_id ?? ""),
        details: String(data.message ?? ""),
        data: event.data,
      };
    case "agent_testing":
    case "agent_verifying":
    case "agent_self_correct":
      return {
        id: `test_${data.tool_id ?? stepId}`,
        stepId,
        turnIndex,
        phase: "testing",
        type: "testing",
        title:
          event.event === "agent_testing"
            ? "Testing Changes"
            : event.event === "agent_verifying"
              ? "Verifying Fix"
              : "Self-Correcting",
        status:
          event.event === "agent_self_correct"
            ? "failed"
            : typeof data.status === "string" &&
                (data.status === "running" ||
                  data.status === "completed" ||
                  data.status === "failed" ||
                  data.status === "awaiting_approval")
              ? data.status
              : "completed",
        startedAt: timestamp,
        completedAt: String(data.completed_at || timestamp),
        durationMs: typeof data.duration_ms === "number" ? data.duration_ms : undefined,
        toolName: String(data.tool_name ?? ""),
        toolOutput: String(data.output ?? ""),
        toolId: String(data.tool_id ?? ""),
        success: Boolean(data.success),
      };
    case "tool_error":
      return {
        id: `tool_${data.tool_id ?? stepId}`,
        stepId,
        turnIndex,
        phase,
        type: "tool_call",
        title: "Execution Error",
        status: "failed",
        startedAt: timestamp,
        completedAt: timestamp,
        toolName: String(data.tool_name ?? ""),
        toolOutput: String(data.error ?? "Unknown error"),
        toolId: String(data.tool_id ?? ""),
      };
    case "error":
      return {
        id: `error_${stepId}`,
        stepId,
        turnIndex,
        phase: "exploring",
        type: "error",
        title: "Execution fault",
        status: "failed",
        startedAt: timestamp,
        completedAt: timestamp,
        details: String(data.message ?? data.code ?? "DeepSpace could not complete this step."),
        data: event.data,
      };
    case "done":
      // Stream completion is transport state, not model reasoning or a tool
      // execution. The real final tool call and answer remain visible.
      return null;
    default:
      return null;
  }
}

function extractThinking(content: string): { text: string; thinking: string } {
  const gemmaMatch = content.match(/<\|channel>thought\n?([\s\S]*?)<channel\|>\n?/);
  if (gemmaMatch) {
    const thinking = gemmaMatch[1]?.trim() ?? "";
    const text = content.replace(gemmaMatch[0], "").trim();
    return { text, thinking };
  }

  let text = "";
  let thinking = "";
  let i = 0;
  let inThink = false;
  const thinkOpen = "<think>";
  const thinkClose = "</think>";

  while (i < content.length) {
    if (!inThink) {
      const start = content.indexOf(thinkOpen, i);
      if (start === -1) {
        text += content.slice(i);
        break;
      }
      text += content.slice(i, start);
      inThink = true;
      i = start + thinkOpen.length;
    } else {
      const end = content.indexOf(thinkClose, i);
      if (end === -1) {
        thinking += content.slice(i);
        break;
      }
      thinking += content.slice(i, end);
      thinking += "\n\n";
      inThink = false;
      i = end + thinkClose.length;
    }
  }
  return { text: text.trim(), thinking: thinking.trim() };
}

function mergeUniqueBlocks(
  existing: StructuredBlock[],
  incoming: StructuredBlock,
): StructuredBlock[] {
  const index = existing.findIndex(
    (block) => block.id === incoming.id && block.type === incoming.type,
  );
  if (index === -1) {
    return [...existing, incoming];
  }
  const current = existing[index];
  if (JSON.stringify(current) === JSON.stringify(incoming)) {
    return existing;
  }
  const next = [...existing];
  next[index] = incoming;
  return next;
}

function normalizeIncomingBlock(incoming: StructuredBlock): StructuredBlock {
  if (incoming.type !== "diagram") {
    return incoming;
  }

  return {
    ...incoming,
    diagram_type: incoming.diagram_type ?? "mermaid_flowchart",
    source: incoming.source ?? "mermaid",
    syntax: incoming.syntax ?? "",
    description: incoming.description ?? "",
  };
}

function readPositiveInteger(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) && value > 0
    ? Math.trunc(value)
    : null;
}

function readContextLimitSource(metadata: Record<string, unknown>): string | null {
  const directSource = metadata.context_limit_source;
  if (typeof directSource === "string" && directSource.trim()) {
    return directSource.trim();
  }

  const provider = metadata.provider;
  if (provider && typeof provider === "object" && !Array.isArray(provider)) {
    const providerSource = (provider as Record<string, unknown>).context_limit_source;
    if (typeof providerSource === "string" && providerSource.trim()) {
      return providerSource.trim();
    }
  }

  return null;
}

function isVerifiedContextLimitSource(source: string | null): boolean {
  if (!source) {
    return false;
  }
  const normalized = source.trim().toLowerCase();
  return (
    normalized.includes("live") ||
    normalized.includes("verified") ||
    normalized.includes("runtime") ||
    normalized.includes("discovered") ||
    normalized.includes("official_docs") ||
    normalized.includes("officialdocs")
  );
}

function readContextLimit(metadata: Record<string, unknown>): number | null {
  if (!isVerifiedContextLimitSource(readContextLimitSource(metadata))) {
    return null;
  }

  const directLimit = readPositiveInteger(metadata.context_limit);
  if (directLimit !== null) {
    return directLimit;
  }

  const provider = metadata.provider;
  if (provider && typeof provider === "object" && !Array.isArray(provider)) {
    const providerLimit = readPositiveInteger((provider as Record<string, unknown>).context_window);
    if (providerLimit !== null) {
      return providerLimit;
    }
  }

  const limitFromModel = readPositiveInteger(metadata.context_window);
  return limitFromModel;
}

function readProviderType(metadata: Record<string, unknown>): string | null {
  const provider = metadata.provider;
  if (provider && typeof provider === "object" && !Array.isArray(provider)) {
    const providerType = (provider as Record<string, unknown>).type;
    if (typeof providerType === "string" && providerType.trim()) {
      return providerType;
    }
  }

  const directType = metadata.provider_type;
  return typeof directType === "string" && directType.trim() ? directType : null;
}

function readModelName(metadata: Record<string, unknown>): string | null {
  const directModel = metadata.model_name;
  if (typeof directModel === "string" && directModel.trim()) {
    return directModel;
  }

  const provider = metadata.provider;
  if (provider && typeof provider === "object" && !Array.isArray(provider)) {
    const providerModel = (provider as Record<string, unknown>).model;
    if (typeof providerModel === "string" && providerModel.trim()) {
      return providerModel;
    }
  }

  return null;
}

function normalizeHistoryAgentStep(step: Record<string, unknown>): AgentStep | null {
  const existingType = step.type;
  const existingStatus = step.status;
  if (
    existingType === "step_start" ||
    existingType === "step_finish" ||
    existingType === "step_summary" ||
    step.message === "Execution step started." ||
    step.message === "Task complete."
  ) {
    return null;
  }
  if (typeof existingType === "string" && typeof existingStatus === "string") {
    return {
      id:
        typeof step.id === "string" && step.id.trim()
          ? step.id
          : `step_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
      type: existingType === "observing" ? "tool_result" : (existingType as AgentStep["type"]),
      stepId:
        typeof step.stepId === "string"
          ? step.stepId
          : typeof step.step_id === "string"
            ? step.step_id
            : undefined,
      toolName:
        typeof step.toolName === "string"
          ? step.toolName
          : typeof step.tool_name === "string"
            ? step.tool_name
            : undefined,
      toolInput:
        step.toolInput && typeof step.toolInput === "object" && !Array.isArray(step.toolInput)
          ? (step.toolInput as Record<string, unknown>)
          : step.tool_input &&
              typeof step.tool_input === "object" &&
              !Array.isArray(step.tool_input)
            ? (step.tool_input as Record<string, unknown>)
            : undefined,
      toolOutput:
        typeof step.toolOutput === "string"
          ? existingType === "observing"
            ? `[system] ${step.toolOutput}`
            : step.toolOutput
          : typeof step.output === "string"
            ? step.output
            : typeof step.summary === "string"
              ? existingType === "observing"
                ? `[system] ${step.summary}`
                : step.summary
              : typeof step.message === "string"
                ? existingType === "observing"
                  ? `[system] ${step.message}`
                  : step.message
                : undefined,
      success: typeof step.success === "boolean" ? step.success : undefined,
      durationMs: typeof step.durationMs === "number" ? step.durationMs : undefined,
      permissionLevel:
        typeof step.permissionLevel === "string"
          ? step.permissionLevel
          : typeof step.permission_level === "string"
            ? step.permission_level
            : undefined,
      plan:
        typeof step.plan === "string"
          ? step.plan
          : typeof step.message === "string"
            ? step.message
            : undefined,
      tools: Array.isArray(step.tools)
        ? (step.tools as string[])
        : Array.isArray(step.tool_names)
          ? (step.tool_names as string[])
          : undefined,
      stepNumber: typeof step.stepNumber === "number" ? step.stepNumber : undefined,
      status: existingStatus as AgentStep["status"],
      startedAt:
        typeof step.startedAt === "string"
          ? step.startedAt
          : typeof step.started_at === "string"
            ? step.started_at
            : new Date().toISOString(),
      completedAt:
        typeof step.completedAt === "string"
          ? step.completedAt
          : typeof step.completed_at === "string"
            ? step.completed_at
            : undefined,
      data: step,
      step_id:
        typeof step.step_id === "string"
          ? step.step_id
          : typeof step.stepId === "string"
            ? step.stepId
            : undefined,
      tool_id:
        typeof step.tool_id === "string"
          ? step.tool_id
          : typeof step.toolId === "string"
            ? step.toolId
            : undefined,
      turnIndex:
        typeof step.turn_index === "number"
          ? step.turn_index
          : typeof step.turnIndex === "number"
            ? step.turnIndex
            : undefined,
    };
  }

  const toolName =
    typeof step.tool_name === "string"
      ? step.tool_name
      : typeof step.toolName === "string"
        ? step.toolName
        : undefined;
  const toolInput =
    step.tool_input && typeof step.tool_input === "object" && !Array.isArray(step.tool_input)
      ? (step.tool_input as Record<string, unknown>)
      : step.toolInput && typeof step.toolInput === "object" && !Array.isArray(step.toolInput)
        ? (step.toolInput as Record<string, unknown>)
        : undefined;
  const startedAt =
    typeof step.started_at === "string"
      ? step.started_at
      : typeof step.startedAt === "string"
        ? step.startedAt
        : new Date().toISOString();
  const stepId =
    typeof step.step_id === "string"
      ? step.step_id
      : typeof step.stepId === "string"
        ? step.stepId
        : undefined;
  const toolId =
    typeof step.tool_id === "string"
      ? step.tool_id
      : typeof step.toolId === "string"
        ? step.toolId
        : undefined;

  if (toolName && toolInput && !("output" in step) && !("toolOutput" in step)) {
    return {
      id: `step_${stepId ?? toolId ?? startedAt}`,
      type: "permission_request",
      stepId,
      toolName,
      toolInput,
      permissionLevel:
        typeof step.permission_level === "string"
          ? step.permission_level
          : typeof step.permissionLevel === "string"
            ? step.permissionLevel
            : undefined,
      status: "awaiting_approval",
      startedAt,
      data: step,
      step_id: stepId,
      tool_id: toolId,
      turnIndex:
        typeof step.turn_index === "number"
          ? step.turn_index
          : typeof step.turnIndex === "number"
            ? step.turnIndex
            : undefined,
    };
  }

  if (toolName && ("output" in step || "toolOutput" in step)) {
    const toolOutput =
      typeof step.output === "string"
        ? step.output
        : typeof step.toolOutput === "string"
          ? step.toolOutput
          : "";
    const success = typeof step.success === "boolean" ? step.success : true;
    return {
      id: `step_${stepId ?? toolId ?? startedAt}`,
      type: success ? "tool_result" : "tool_error",
      stepId,
      toolName,
      toolInput,
      toolOutput,
      success,
      durationMs:
        typeof step.duration_ms === "number"
          ? step.duration_ms
          : typeof step.durationMs === "number"
            ? step.durationMs
            : undefined,
      status: success ? "completed" : "failed",
      startedAt,
      completedAt:
        typeof step.completed_at === "string"
          ? step.completed_at
          : typeof step.completedAt === "string"
            ? step.completedAt
            : undefined,
      data: step,
      step_id: stepId,
      tool_id: toolId,
      turnIndex:
        typeof step.turn_index === "number"
          ? step.turn_index
          : typeof step.turnIndex === "number"
            ? step.turnIndex
            : undefined,
    };
  }

  if (
    toolName &&
    (typeof step.summary === "string" ||
      typeof step.message === "string" ||
      typeof step.observed_at === "string" ||
      typeof step.observedAt === "string")
  ) {
    const observedAt =
      typeof step.observed_at === "string"
        ? step.observed_at
        : typeof step.observedAt === "string"
          ? step.observedAt
          : startedAt;
    return {
      id: `step_${stepId ?? toolId ?? observedAt}`,
      type: "tool_result",
      stepId,
      toolName,
      toolInput,
      toolOutput:
        typeof step.summary === "string"
          ? `[system] ${step.summary}`
          : typeof step.message === "string"
            ? `[system] ${step.message}`
            : undefined,
      success: typeof step.success === "boolean" ? step.success : true,
      status: "completed",
      startedAt: observedAt,
      completedAt: observedAt,
      data: step,
      step_id: stepId,
      tool_id: toolId,
      turnIndex:
        typeof step.turn_index === "number"
          ? step.turn_index
          : typeof step.turnIndex === "number"
            ? step.turnIndex
            : undefined,
    };
  }

  if (typeof step.error === "string") {
    return {
      id: `step_${stepId ?? startedAt}`,
      type: "tool_error",
      stepId,
      toolName: toolName || "Agent Execution",
      toolInput,
      toolOutput: String(step.error),
      success: false,
      status: "failed",
      startedAt,
      completedAt: startedAt,
      data: step,
      step_id: stepId,
      tool_id: toolId,
      turnIndex:
        typeof step.turn_index === "number"
          ? step.turn_index
          : typeof step.turnIndex === "number"
            ? step.turnIndex
            : undefined,
    };
  }

  if (typeof step.plan === "string" || typeof step.message === "string") {
    return {
      id: `step_${stepId ?? startedAt}`,
      type: "plan",
      stepId,
      plan: typeof step.plan === "string" ? step.plan : String(step.message ?? ""),
      status: "completed",
      startedAt,
      data: step,
      step_id: stepId,
      tool_id: toolId,
      turnIndex:
        typeof step.turn_index === "number"
          ? step.turn_index
          : typeof step.turnIndex === "number"
            ? step.turnIndex
            : undefined,
    };
  }

  return null;
}

function normalizeHistoryAgentSteps(raw: unknown): AgentStep[] | undefined {
  if (!Array.isArray(raw)) {
    return undefined;
  }

  const steps = compactAgentSteps(
    raw
      .filter(
        (item) =>
          !(
            item &&
            typeof item === "object" &&
            (item as Record<string, unknown>).type === "observing"
          ),
      )
      .map((item) =>
        item && typeof item === "object"
          ? normalizeHistoryAgentStep(item as Record<string, unknown>)
          : null,
      )
      .filter((item): item is AgentStep => item !== null && item.type !== "observing"),
  );

  // Older persisted turns stored every provider thinking delta as a separate
  // step. Collapse those legacy rows when rehydrating history as well.
  const consolidated: AgentStep[] = [];
  let thought: AgentStep | undefined;
  for (const step of steps) {
    if (step.type !== "thinking") {
      consolidated.push(step);
      continue;
    }
    if (!thought) {
      thought = { ...step };
      consolidated.push(thought);
    } else {
      thought.plan = appendStreamingText(thought.plan, step.plan ?? "");
      thought.toolOutput = appendStreamingText(thought.toolOutput, step.toolOutput ?? "");
      thought.completedAt = step.completedAt ?? thought.completedAt;
      thought.durationMs = step.durationMs ?? thought.durationMs;
    }
  }

  return consolidated.length > 0 ? consolidated : undefined;
}

function formatToolDeltaChunk(text: string, stream: unknown): string {
  const streamName = typeof stream === "string" ? stream.trim().toLowerCase() : "";
  if (!text) {
    return "";
  }
  if (!streamName || streamName === "stdout") {
    return text;
  }
  if (text.startsWith(`[${streamName}]`)) {
    return text;
  }
  return `[${streamName}] ${text}`;
}

function appendStreamingText(existingText: string | undefined, incomingText: string): string {
  const existing = existingText ?? "";
  if (!existing) {
    return incomingText;
  }
  if (!incomingText) {
    return existing;
  }
  if (incomingText.startsWith(existing)) {
    return incomingText;
  }
  if (existing.startsWith(incomingText)) {
    return existing;
  }

  const maxOverlap = Math.min(existing.length, incomingText.length);
  for (let size = maxOverlap; size > 0; size -= 1) {
    if (existing.endsWith(incomingText.slice(0, size))) {
      return `${existing}${incomingText.slice(size)}`;
    }
  }

  return `${existing}${incomingText}`;
}

function getStreamingSuffix(existingText: string | undefined, incomingText: string): string {
  const existing = existingText ?? "";
  if (!incomingText || existing.startsWith(incomingText)) {
    return "";
  }
  if (!existing) {
    return incomingText;
  }
  if (incomingText.startsWith(existing)) {
    return incomingText.slice(existing.length);
  }

  const merged = appendStreamingText(existing, incomingText);
  return merged.slice(existing.length);
}

function mergeToolOutput(existingOutput: string | undefined, incomingOutput: string): string {
  return appendStreamingText(existingOutput, incomingOutput);
}

function getAgentStepIdentity(step: {
  id?: string;
  stepId?: string;
  step_id?: string;
  tool_id?: string;
  toolId?: string;
  toolName?: string;
}): string | null {
  const toolId = step.tool_id ?? step.toolId;
  if (typeof toolId === "string" && toolId.trim()) {
    return `tool:${toolId.trim()}`;
  }

  const stepId = step.step_id ?? step.stepId;
  if (typeof stepId === "string" && stepId.trim()) {
    return `step:${stepId.trim()}`;
  }

  const toolName = step.toolName;
  if (typeof toolName === "string" && toolName.trim()) {
    return `tool-name:${toolName.trim()}`;
  }

  const id = step.id;
  if (typeof id === "string" && id.trim()) {
    return `id:${id.trim()}`;
  }

  return null;
}

function mergeAgentStep(existing: AgentStep, incoming: AgentStep): AgentStep {
  const mergedData =
    existing.data || incoming.data
      ? {
          ...(existing.data ?? {}),
          ...(incoming.data ?? {}),
        }
      : undefined;

  const base: AgentStep = {
    ...existing,
    ...incoming,
    data: mergedData,
    id: existing.id || incoming.id,
    stepId: incoming.stepId ?? existing.stepId,
    step_id: incoming.step_id ?? existing.step_id,
    toolName: incoming.toolName ?? existing.toolName,
    toolInput: incoming.toolInput ?? existing.toolInput,
    permissionLevel: incoming.permissionLevel ?? existing.permissionLevel,
    plan: incoming.plan ?? existing.plan,
    tools: incoming.tools ?? existing.tools,
    stepNumber: incoming.stepNumber ?? existing.stepNumber,
    startedAt: existing.startedAt || incoming.startedAt,
    completedAt: incoming.completedAt ?? existing.completedAt,
    success: incoming.success ?? existing.success,
    durationMs: incoming.durationMs ?? existing.durationMs,
    toolOutput: incoming.toolOutput ?? existing.toolOutput,
    tool_id: incoming.tool_id ?? existing.tool_id,
    turnIndex: incoming.turnIndex ?? existing.turnIndex,
  };

  if (incoming.type === "permission_request") {
    return {
      ...base,
      type: "permission_request",
      status: "awaiting_approval",
      completedAt: undefined,
    };
  }

  if (incoming.type === "tool_start") {
    return {
      ...base,
      type: "tool_start",
      status: "running",
      toolOutput: mergeToolOutput(existing.toolOutput, incoming.toolOutput ?? ""),
      completedAt: undefined,
    };
  }

  if (incoming.type === "tool_result") {
    return {
      ...base,
      type: "tool_result",
      status: incoming.success === false ? "failed" : "completed",
      toolOutput: mergeToolOutput(existing.toolOutput, incoming.toolOutput ?? ""),
      completedAt: incoming.completedAt ?? existing.completedAt,
    };
  }

  if (incoming.type === "tool_error") {
    return {
      ...base,
      type: "tool_error",
      status: "failed",
      toolOutput: mergeToolOutput(existing.toolOutput, incoming.toolOutput ?? ""),
      completedAt: incoming.completedAt ?? existing.completedAt,
    };
  }

  if (incoming.type === "observing") {
    const observationText = incoming.toolOutput?.trim()
      ? `[system] ${incoming.toolOutput.trim()}`
      : "";
    return {
      ...base,
      type: "tool_result",
      status: incoming.success === false ? "failed" : "completed",
      toolOutput: mergeToolOutput(existing.toolOutput, observationText),
      success: incoming.success ?? existing.success ?? true,
      completedAt: incoming.completedAt ?? existing.completedAt ?? incoming.startedAt,
    };
  }

  if (
    incoming.type === "agent_testing" ||
    incoming.type === "agent_verifying" ||
    incoming.type === "agent_self_correct"
  ) {
    return {
      ...base,
      type: incoming.type,
      status:
        incoming.type === "agent_self_correct"
          ? "failed"
          : incoming.success === false
            ? "failed"
            : "completed",
      toolOutput: mergeToolOutput(existing.toolOutput, incoming.toolOutput ?? ""),
      success: incoming.success ?? existing.success,
      durationMs: incoming.durationMs ?? existing.durationMs,
      completedAt: incoming.completedAt ?? existing.completedAt,
    };
  }

  if (incoming.type === "plan") {
    return {
      ...base,
      type: "plan",
      status: "completed",
    };
  }

  return base;
}

function upsertAgentStep(steps: AgentStep[], incoming: AgentStep): AgentStep[] {
  const identity = getAgentStepIdentity(incoming);
  if (!identity) {
    return [...steps, incoming];
  }

  const index = [...steps]
    .map((step, stepIndex) => ({ step, stepIndex }))
    .reverse()
    .find(({ step }) => getAgentStepIdentity(step) === identity)?.stepIndex;

  if (index === undefined) {
    if (incoming.type === "observing") {
      return [
        ...steps,
        mergeAgentStep(
          {
            ...incoming,
            type: "tool_result",
            status: incoming.success === false ? "failed" : "completed",
            toolOutput: undefined,
          },
          incoming,
        ),
      ];
    }
    return [...steps, incoming];
  }

  const next = [...steps];
  next[index] = mergeAgentStep(next[index]!, incoming);
  return next;
}

interface DiffLine {
  type: "added" | "removed" | "unchanged";
  text: string;
}

function computeLineDiff(oldText: string, newText: string) {
  const oldLines = oldText ? oldText.split("\n") : [];
  const newLines = newText ? newText.split("\n") : [];

  let commonPrefixCount = 0;
  while (
    commonPrefixCount < oldLines.length &&
    commonPrefixCount < newLines.length &&
    oldLines[commonPrefixCount] === newLines[commonPrefixCount]
  ) {
    commonPrefixCount++;
  }

  let commonSuffixCount = 0;
  while (
    commonSuffixCount < oldLines.length - commonPrefixCount &&
    commonSuffixCount < newLines.length - commonPrefixCount &&
    oldLines[oldLines.length - 1 - commonSuffixCount] ===
      newLines[newLines.length - 1 - commonSuffixCount]
  ) {
    commonSuffixCount++;
  }

  const prefixLines = oldLines.slice(0, commonPrefixCount);
  const suffixLines = oldLines.slice(oldLines.length - commonSuffixCount);

  const middleOld = oldLines.slice(commonPrefixCount, oldLines.length - commonSuffixCount);
  const middleNew = newLines.slice(commonPrefixCount, newLines.length - commonSuffixCount);

  const dp: number[][] = Array.from({ length: middleOld.length + 1 }, () =>
    new Array(middleNew.length + 1).fill(0),
  );

  for (let i = 1; i <= middleOld.length; i++) {
    for (let j = 1; j <= middleNew.length; j++) {
      if (middleOld[i - 1] === middleNew[j - 1]) {
        dp[i][j] = dp[i - 1][j - 1] + 1;
      } else {
        dp[i][j] = Math.max(dp[i - 1][j], dp[i][j - 1]);
      }
    }
  }

  const middleDiff: DiffLine[] = [];
  let i = middleOld.length;
  let j = middleNew.length;
  let additions = 0;
  let deletions = 0;

  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && middleOld[i - 1] === middleNew[j - 1]) {
      middleDiff.unshift({ type: "unchanged", text: middleOld[i - 1] });
      i--;
      j--;
    } else if (j > 0 && (i === 0 || dp[i][j - 1] >= dp[i - 1][j])) {
      middleDiff.unshift({ type: "added", text: middleNew[j - 1] });
      additions++;
      j--;
    } else {
      middleDiff.unshift({ type: "removed", text: middleOld[i - 1] });
      deletions++;
      i--;
    }
  }

  const diffLines: DiffLine[] = [
    ...prefixLines.map((line) => ({ type: "unchanged" as const, text: line })),
    ...middleDiff,
    ...suffixLines.map((line) => ({ type: "unchanged" as const, text: line })),
  ];

  return { additions, deletions, diffLines };
}

function promoteTurnTextToThinking(
  message: DeepSpaceMessage,
  turnIndex: number | undefined,
): DeepSpaceMessage {
  const currentTurnText = message.currentTurnText ?? "";
  if (!currentTurnText) {
    return message;
  }

  let rawContent = message.rawContent;
  if (rawContent.endsWith(currentTurnText)) {
    rawContent = rawContent.slice(0, rawContent.length - currentTurnText.length);
  }

  const nextSteps = [...(message.agentSteps ?? [])];
  const thinkingStepIdx = nextSteps.findIndex(
    (s) => s.type === "thinking" && s.turnIndex === turnIndex,
  );

  if (thinkingStepIdx !== -1) {
    const existing = nextSteps[thinkingStepIdx]!;
    nextSteps[thinkingStepIdx] = {
      ...existing,
      plan: `${existing.plan ?? ""}${currentTurnText}`,
      toolOutput: `${existing.toolOutput ?? ""}${currentTurnText}`,
    };
  } else {
    nextSteps.push({
      id: `thinking_${turnIndex ?? Date.now()}`,
      type: "thinking",
      status: "completed",
      startedAt: new Date().toISOString(),
      plan: currentTurnText,
      toolOutput: currentTurnText,
      turnIndex,
    });
  }

  return {
    ...message,
    rawContent,
    content: normalizeMarkdown(rawContent),
    currentTurnText: "",
    agentSteps: nextSteps,
  };
}

function compactAgentSteps(rawSteps: AgentStep[]): AgentStep[] {
  return rawSteps.reduce<AgentStep[]>((acc, step) => upsertAgentStep(acc, step), []);
}

export interface DeepSpaceThreadState {
  messages: DeepSpaceMessage[];
  currentConversationId: string | null;
  activeAssistantId: string | null;
  isStreaming: boolean;
  isAgentMode: boolean;
  streamError: { code: string; message: string } | null;
  lastModelName: string | null;
  lastProviderType: string | null;
  lastContextLimit: number | null;
  durableRun: DurableMissionRuntimeState | null;
}

export type DeepSpaceThreadAction =
  | { type: "load_history"; conversationId: string; messages: DeepSpaceHistoryMessage[] }
  | { type: "reset_thread" }
  | { type: "submit_query"; query: string }
  | { type: "stream_interrupted" }
  | { type: "stream_finished" }
  | { type: "stream_failed"; error: { code: string; message: string } }
  | { type: "stream_event"; event: DeepSpaceStreamEvent }
  | { type: "stream_events"; events: DeepSpaceStreamEvent[] }
  | { type: "delete_message_local"; messageId: string }
  | { type: "start_edit"; messageId: string }
  | { type: "cancel_edit"; messageId: string }
  | { type: "update_draft"; messageId: string; content: string }
  | { type: "activate_version"; messageId: string; version: DeepSpaceHistoryVersion }
  | { type: "update_message"; messageId: string; data: Partial<DeepSpaceMessage> }
  | { type: "resume_query"; messageId: string };

export const initialDeepSpaceThreadState: DeepSpaceThreadState = {
  messages: [],
  currentConversationId: null,
  activeAssistantId: null,
  isStreaming: false,
  isAgentMode: false,
  streamError: null,
  lastModelName: null,
  lastProviderType: null,
  lastContextLimit: null,
  durableRun: null,
};

function rehydrateMetricsFromHistory(
  metadata: Record<string, unknown>,
  createdAt: string,
): MessageMetrics | undefined {
  // The backend persists `latency_timeline` (list of {label, atMs, detail?})
  // and `started_at` alongside the message. We re-derive the metric chips
  // the UI shows at the end of every assistant message so the bar remains
  // visible after a history reload (or refresh), matching what was seen
  // during streaming.
  const rawTimeline = metadata.latency_timeline;
  if (!Array.isArray(rawTimeline) || rawTimeline.length === 0) {
    return undefined;
  }
  const timeline: MessageMetrics["latencyTimeline"] = rawTimeline
    .filter(
      (entry): entry is { label: string; atMs: number; detail?: string } =>
        entry !== null &&
        typeof entry === "object" &&
        typeof (entry as Record<string, unknown>).label === "string" &&
        typeof (entry as { atMs?: unknown }).atMs === "number",
    )
    .map((entry) => ({
      label: entry.label,
      atMs: entry.atMs,
      ...(typeof entry.detail === "string" ? { detail: entry.detail } : {}),
    }));
  if (timeline.length === 0) {
    return undefined;
  }

  const provider =
    metadata.provider && typeof metadata.provider === "object"
      ? (metadata.provider as Record<string, unknown>)
      : null;
  const modelName =
    (typeof provider?.model === "string" && provider.model) ||
    (typeof metadata.model_name === "string" ? (metadata.model_name as string) : undefined) ||
    undefined;
  const providerType =
    (typeof provider?.type === "string" && provider.type) ||
    (typeof metadata.provider_type === "string" ? (metadata.provider_type as string) : undefined) ||
    undefined;

  const contextLimit =
    typeof metadata.context_limit === "number"
      ? (metadata.context_limit as number)
      : typeof provider?.context_window === "number"
        ? (provider.context_window as number)
        : undefined;

  // Pick the first non-turn_started entry as the "first activity" phase.
  const firstActivity = timeline.find((entry) => entry.label !== "turn_started");
  const lastEntry = timeline[timeline.length - 1];
  const phase = firstActivity?.label ?? lastEntry?.label;
  const ttftEntry = timeline.find((entry) => entry.label === "first_activity");
  const ttftMs = ttftEntry?.atMs;

  // Tokens are not persisted server-side; we only rehydrate timing.
  // The streaming view already shows the live values, and on history
  // reload we surface a stable timing chip set rather than 0s.
  return {
    modelName,
    providerType,
    contextLimit,
    phase,
    latencyTimeline: timeline,
    ...(typeof ttftMs === "number" ? { ttftMs } : {}),
    startedAt: createdAt,
  };
}

function fromHistoryMessage(message: DeepSpaceHistoryMessage): DeepSpaceMessage {
  const metadata = (message.metadata_json ?? {}) as Record<string, unknown>;
  const thinking =
    metadata.thinking && typeof metadata.thinking === "object"
      ? String((metadata.thinking as Record<string, unknown>).content ?? "")
      : "";
  const structured =
    metadata.structured_answer && typeof metadata.structured_answer === "object"
      ? (metadata.structured_answer as StructuredAnswerShape)
      : null;
  const content = normalizeMarkdown(message.content);
  const persistedStatus = String(metadata.status ?? "");
  const persistedError =
    persistedStatus === "error" || (persistedStatus === "streaming" && !content.trim())
      ? {
          code: String(metadata.error_code ?? "STREAM_INCOMPLETE"),
          message: content.trim()
            ? content
            : "This DeepSpace response ended before a usable answer was saved.",
        }
      : null;
  const metrics = rehydrateMetricsFromHistory(metadata, message.created_at);
  const agentSteps = normalizeHistoryAgentSteps(metadata.agent_steps);
  const compaction = readConversationCompactionState(metadata.conversation_compaction);
  const memoryMetadata = metadata.memory;
  const rawMemoryUsed =
    memoryMetadata &&
    typeof memoryMetadata === "object" &&
    Array.isArray((memoryMetadata as Record<string, unknown>).used)
      ? ((memoryMetadata as Record<string, unknown>).used as unknown[])
      : null;
  const memoryUsed = rawMemoryUsed
    ? rawMemoryUsed
        .filter(
          (item): item is Record<string, unknown> => Boolean(item) && typeof item === "object",
        )
        .map((item) => ({
          id: String(item.id ?? ""),
          key: String(item.key ?? "memory"),
          ...(typeof item.source === "string" ? { source: item.source } : {}),
        }))
        .filter((item) => item.id)
    : undefined;
  const artifacts = Array.isArray(metadata.artifacts)
    ? metadata.artifacts
        .filter(
          (item): item is Record<string, unknown> => Boolean(item) && typeof item === "object",
        )
        .map(
          (item): DeepSpaceMediaArtifact => ({
            id: String(item.id ?? ""),
            kind: item.kind === "video" || item.kind === "audio" ? item.kind : "image",
            status: item.status === "pending" || item.status === "failed" ? item.status : "ready",
            title: String(item.title ?? "Generated media"),
            content_type: String(item.content_type ?? "application/octet-stream"),
            size_bytes: typeof item.size_bytes === "number" ? item.size_bytes : 0,
            url: String(item.url ?? ""),
          }),
        )
        .filter((item) => item.id && item.url)
    : undefined;
  // Rehydrate timeline from agentSteps if timeline is not explicitly persisted
  let timeline: TimelineStep[] = [];
  if (agentSteps) {
    for (const step of agentSteps) {
      const mapped: TimelineStep = {
        id: step.id,
        stepId: step.stepId ?? step.id,
        turnIndex: step.turnIndex ?? 0,
        phase: (step.data?.phase as AgentPhase) || "exploring",
        type:
          step.type === "plan"
            ? "plan"
            : step.type === "thinking"
              ? "thinking"
              : step.type === "permission_request" || step.type === "ask_user_question"
                ? "permission"
                : step.type === "agent_testing" ||
                    step.type === "agent_verifying" ||
                    step.type === "agent_self_correct"
                  ? "testing"
                  : ("tool_call" as const),
        title: (() => {
          if (step.type === "plan") {
            return (step.data?.title || step.data?.message || "Strategic Plan") as string;
          }
          if (step.type === "thinking") {
            return "Internal Thought";
          }
          if (step.type === "permission_request") {
            return "Clearance Required";
          }
          if (step.type === "ask_user_question") {
            return "Clarification Needed";
          }
          if (step.type === "agent_testing") {
            return "Testing Changes";
          }
          if (step.type === "agent_verifying") {
            return "Verifying Fix";
          }
          if (step.type === "agent_self_correct") {
            return "Self-Correcting";
          }
          if (step.type === "tool_error") {
            return "Execution Error";
          }
          const toolName = step.toolName;
          if (toolName) {
            return (TOOL_LABELS[toolName] ?? toolName.replace(/_/g, " ")) as string;
          }
          return "Executing Tool";
        })(),
        status: step.status,
        startedAt: step.startedAt,
        completedAt: step.completedAt,
        durationMs: step.durationMs,
        toolName: step.toolName,
        toolInput: step.toolInput,
        toolOutput: step.toolOutput,
        toolId: step.tool_id,
        success: step.success,
        diffStats: step.diffStats,
        details: step.plan,
        data: step.data,
      };
      timeline = upsertTimelineStep(timeline, mapped);
    }
  }

  return {
    id: message.id,
    role: message.role,
    content,
    rawContent: message.content,
    createdAt: message.created_at,
    status: persistedError ? "error" : "ready",
    blocks: Array.isArray(metadata.blocks) ? (metadata.blocks as StructuredBlock[]) : [],
    structured,
    thinkingContent: thinking || undefined,
    activeVersionId: message.active_version_id,
    activeVersionIndex: message.active_version_index,
    versionCount: message.version_count,
    versions: message.versions,
    agentSteps,
    timeline,
    metrics,
    compaction,
    memoryUsed,
    artifacts,
    error: persistedError,
  };
}

function reduceDeepSpaceThread(
  state: DeepSpaceThreadState,
  action: DeepSpaceThreadAction,
): DeepSpaceThreadState {
  switch (action.type) {
    case "load_history": {
      const incomingMessages = action.messages.map(fromHistoryMessage);
      const localMessagesById = new Map(state.messages.map((message) => [message.id, message]));
      const messages = incomingMessages.map((message) => {
        const local = localMessagesById.get(message.id);
        // The server persists the final answer, while the browser has the
        // exact ordered SSE trajectory for the just-finished turn. Preserve
        // that local trajectory during the automatic post-stream refresh so
        // the timeline does not collapse into a single thought block.
        if (message.role !== "assistant" || !local?.timeline?.length) return message;
        return {
          ...message,
          timeline: local.timeline,
          agentSteps: local.agentSteps?.length ? local.agentSteps : message.agentSteps,
          thinkingContent: local.thinkingContent ?? message.thinkingContent,
        };
      });
      return {
        ...state,
        messages,
        currentConversationId: action.conversationId,
        activeAssistantId: null,
        isStreaming: false,
        streamError: null,
        lastModelName:
          readModelName(
            (action.messages.findLast((m) => m.role === "assistant")?.metadata_json ??
              {}) as Record<string, unknown>,
          ) || null,
        lastProviderType:
          readProviderType(
            (action.messages.findLast((m) => m.role === "assistant")?.metadata_json ??
              {}) as Record<string, unknown>,
          ) || null,
        lastContextLimit:
          readContextLimit(
            (action.messages.findLast((m) => m.role === "assistant")?.metadata_json ??
              {}) as Record<string, unknown>,
          ) || null,
      };
    }
    case "reset_thread":
      return initialDeepSpaceThreadState;
    case "submit_query": {
      const tempAssistantId = createClientMessageId("assistant");
      return {
        ...state,
        messages: [
          ...state.messages,
          {
            id: createClientMessageId("user"),
            role: "user",
            content: action.query,
            rawContent: action.query,
            createdAt: new Date().toISOString(),
            status: "ready",
            blocks: [],
            structured: null,
            error: null,
          },
          {
            id: tempAssistantId,
            role: "assistant",
            content: "",
            rawContent: "",
            createdAt: new Date().toISOString(),
            status: "streaming",
            blocks: [],
            structured: null,
            error: null,
            agentSteps: [],
            thinkingContent: "",
            mission: null,
          },
        ],
        activeAssistantId: tempAssistantId,
        isStreaming: true,
        streamError: null,
      };
    }
    case "stream_interrupted":
    case "stream_finished": {
      const activeId = state.activeAssistantId;
      const finishedAt = nowIso();
      return {
        ...state,
        activeAssistantId: null,
        isStreaming: false,
        messages: state.messages.map((m) => {
          if (m.id === activeId || (activeId === null && m.status === "streaming")) {
            const nextSteps = (m.agentSteps ?? []).map((s) => {
              if (s.status === "running" || s.status === "awaiting_approval") {
                return finalizeAgentStep(s, finishedAt, "completed");
              }
              return s;
            });
            return {
              ...m,
              status:
                action.type === "stream_interrupted"
                  ? "ready"
                  : m.rawContent.trim() || m.thinkingContent?.trim()
                    ? "ready"
                    : "error",
              error:
                action.type === "stream_interrupted"
                  ? null
                  : m.rawContent.trim() || m.thinkingContent?.trim()
                    ? m.error
                    : {
                        code: "STREAM_INCOMPLETE",
                        message: "The chat stream ended before DeepSpace returned a response.",
                      },
              agentSteps: nextSteps,
            };
          }
          return m;
        }),
      };
    }
    case "resume_query":
      return {
        ...state,
        activeAssistantId: action.messageId,
        isStreaming: true,
        streamError: null,
      };
    case "stream_failed": {
      const activeId = state.activeAssistantId;
      const failedAt = nowIso();
      return {
        ...state,
        activeAssistantId: null,
        isStreaming: false,
        streamError: action.error,
        messages: state.messages.map((m) => {
          if (m.id === activeId || (activeId === null && m.status === "streaming")) {
            const nextSteps = (m.agentSteps ?? []).map((s) => {
              if (s.status === "running" || s.status === "awaiting_approval") {
                return finalizeAgentStep(s, failedAt, "failed");
              }
              return s;
            });
            return {
              ...m,
              status: "error",
              error: action.error,
              agentSteps: nextSteps,
            };
          }
          return m;
        }),
      };
    }
    case "stream_events":
      return action.events.reduce<DeepSpaceThreadState>(
        (nextState, event) => deepSpaceThreadReducer(nextState, { type: "stream_event", event }),
        state,
      );
    case "delete_message_local":
      return {
        ...state,
        messages: state.messages.filter((message) => message.id !== action.messageId),
      };
    case "start_edit":
      return {
        ...state,
        messages: state.messages.map((m) =>
          m.id === action.messageId ? { ...m, isEditing: true, draftContent: m.rawContent } : m,
        ),
      };
    case "cancel_edit":
      return {
        ...state,
        messages: state.messages.map((m) =>
          m.id === action.messageId ? { ...m, isEditing: false, draftContent: null } : m,
        ),
      };
    case "update_draft":
      return {
        ...state,
        messages: state.messages.map((m) =>
          m.id === action.messageId ? { ...m, draftContent: action.content } : m,
        ),
      };
    case "activate_version": {
      const { messageId, version } = action;
      const metadata = (version.metadata_json ?? {}) as Record<string, unknown>;
      const thinking =
        metadata.thinking && typeof metadata.thinking === "object"
          ? String((metadata.thinking as Record<string, unknown>).content ?? "")
          : "";
      const structured =
        metadata.structured_answer && typeof metadata.structured_answer === "object"
          ? (metadata.structured_answer as StructuredAnswerShape)
          : null;
      const content = normalizeMarkdown(version.content);
      const compaction = readConversationCompactionState(metadata.conversation_compaction);

      return {
        ...state,
        messages: state.messages.map((m) =>
          m.id === messageId
            ? {
                ...m,
                content,
                rawContent: version.content,
                activeVersionId: version.id,
                activeVersionIndex: version.version_index,
                blocks: Array.isArray(metadata.blocks)
                  ? (metadata.blocks as StructuredBlock[])
                  : [],
                structured,
                thinkingContent: thinking || undefined,
                compaction,
              }
            : m,
        ),
      };
    }
    case "update_message":
      return {
        ...state,
        messages: state.messages.map((m) =>
          m.id === action.messageId ? { ...m, ...action.data } : m,
        ),
      };
    case "stream_event": {
      const event = action.event;
      if (event.event === "start") {
        const messageId = String(event.data.message_id ?? createClientMessageId("assistant"));
        const nextMessages = [...state.messages];

        // Find if there's a temporary client-created assistant message
        const tempIndex = nextMessages.findIndex(
          (m) => m.role === "assistant" && m.id.startsWith("assistant_") && !m.rawContent,
        );
        if (tempIndex !== -1) {
          nextMessages[tempIndex] = {
            ...nextMessages[tempIndex],
            id: messageId,
            createdAt:
              typeof event.data.started_at === "string"
                ? event.data.started_at
                : nextMessages[tempIndex].createdAt,
          };
        }

        const existingIndex = nextMessages.findIndex((message) => message.id === messageId);
        if (existingIndex !== -1) {
          const existing = nextMessages[existingIndex]!;
          nextMessages[existingIndex] = {
            ...existing,
            status: "streaming",
            error: null,
          };
          return {
            ...state,
            currentConversationId:
              typeof event.data.conversation_id === "string"
                ? event.data.conversation_id
                : state.currentConversationId,
            activeAssistantId: messageId,
            isStreaming: true,
            messages: nextMessages,
          };
        }
        return {
          ...state,
          currentConversationId:
            typeof event.data.conversation_id === "string"
              ? event.data.conversation_id
              : state.currentConversationId,
          activeAssistantId: messageId,
          isStreaming: true,
          messages: [
            ...nextMessages,
            {
              id: messageId,
              role: "assistant",
              content: "",
              rawContent: "",
              createdAt:
                typeof event.data.started_at === "string"
                  ? event.data.started_at
                  : new Date().toISOString(),
              status: "streaming",
              blocks: [],
              structured: null,
              error: null,
              mission: null,
            },
          ],
        };
      }

      const assistantId = state.activeAssistantId;
      if (!assistantId) {
        return state;
      }
      const index = state.messages.findIndex((message) => message.id === assistantId);
      if (index === -1) return state;

      const current = state.messages[index]!;
      const nextMessages = [...state.messages];
      const nextMission = updateMissionCanvas(current.mission, event);
      const compactionFromEvent = readConversationCompactionState(
        (event.data as Record<string, unknown>).compaction_state,
      );
      const nextCompaction = compactionFromEvent ?? current.compaction ?? null;

      // Build or Update Timeline
      const timelineStep = mapEventToTimelineStep(event);
      let nextTimeline = [...(current.timeline ?? [])];
      if (timelineStep) {
        nextTimeline = upsertTimelineStep(nextTimeline, timelineStep);
      }

      if (
        event.event === "delta" ||
        (event.event === "lane_delta" &&
          (event.data.lane_type === "main_chat" || !state.activeAssistantId))
      ) {
        const rawChunk = String(event.data.text ?? "");
        const rawContent = appendStreamingText(current.rawContent, rawChunk);
        const chunk = rawContent.slice((current.rawContent ?? "").length);

        // Metrics calculation
        const now = Date.now();
        const metrics = { ...(current.metrics || {}) };

        if (!metrics.firstTokenAt && chunk.trim()) {
          metrics.firstTokenAt = new Date(now).toISOString();
          if (current.createdAt) {
            metrics.ttftMs = now - new Date(current.createdAt).getTime();
          }
        }

        const totalTokens =
          estimateTokens(rawContent) + estimateTokens(current.thinkingContent ?? "");
        metrics.totalTokens = totalTokens;

        if (metrics.firstTokenAt) {
          const durationSec = (now - new Date(metrics.firstTokenAt).getTime()) / 1000;
          if (durationSec > 0.1) {
            metrics.tokensPerSec = Math.round((totalTokens / durationSec) * 10) / 10;
          }
        }

        const currentTurnText = appendStreamingText(current.currentTurnText, chunk);
        const extracted = extractThinking(rawContent);

        const nextAgentSteps = [...(current.agentSteps ?? [])];

        // Find the last active step if it's a thinking/monologue step
        const lastStep = nextAgentSteps[nextAgentSteps.length - 1];
        const thinkingText = extracted.thinking || currentTurnText;

        if (lastStep && lastStep.type === "thinking" && lastStep.status === "running") {
          // Update the existing active thinking step
          nextAgentSteps[nextAgentSteps.length - 1] = {
            ...lastStep,
            plan: thinkingText,
            toolOutput: thinkingText,
          };
        } else if (thinkingText.trim()) {
          // Create a new thinking step if the last one was closed or didn't exist
          nextAgentSteps.push({
            id: `monologue_${Date.now()}`,
            type: "thinking",
            status: "running",
            startedAt: new Date().toISOString(),
            plan: thinkingText,
            toolOutput: thinkingText,
          });
        }

        nextMessages[index] = {
          ...current,
          rawContent,
          thinkingContent: extracted.thinking || current.thinkingContent,
          content: normalizeMarkdown(extracted.text),
          currentTurnText,
          status: "streaming",
          metrics,
          agentSteps: nextAgentSteps,
          timeline: nextTimeline,
          mission: nextMission,
          compaction: nextCompaction,
        };
      } else if (event.event === "replace") {
        const content = String(event.data.content ?? "");
        const extracted = extractThinking(content);
        nextMessages[index] = {
          ...current,
          rawContent: content,
          thinkingContent: extracted.thinking || current.thinkingContent,
          content: normalizeMarkdown(extracted.text),
          structured: (event.data.structured as StructuredAnswerShape | null | undefined) ?? null,
          status: state.isStreaming ? "streaming" : "ready",
          timeline: nextTimeline,
          mission: nextMission,
          compaction: nextCompaction,
        };
      } else if (event.event === "artifact") {
        const rawArtifact =
          event.data.artifact && typeof event.data.artifact === "object"
            ? (event.data.artifact as Record<string, unknown>)
            : null;
        if (!rawArtifact) return state;
        const artifact: DeepSpaceMediaArtifact = {
          id: String(rawArtifact.id ?? ""),
          kind:
            rawArtifact.kind === "video" || rawArtifact.kind === "audio"
              ? rawArtifact.kind
              : "image",
          status:
            rawArtifact.status === "pending" || rawArtifact.status === "failed"
              ? rawArtifact.status
              : "ready",
          title: String(rawArtifact.title ?? "Generated media"),
          content_type: String(rawArtifact.content_type ?? "application/octet-stream"),
          size_bytes: typeof rawArtifact.size_bytes === "number" ? rawArtifact.size_bytes : 0,
          url: String(rawArtifact.url ?? ""),
        };
        if (!artifact.id || !artifact.url) return state;
        nextMessages[index] = {
          ...current,
          artifacts: [
            ...(current.artifacts ?? []).filter((item) => item.id !== artifact.id),
            artifact,
          ],
          timeline: nextTimeline,
          mission: nextMission,
          compaction: nextCompaction,
        };
      } else if (
        event.event === "table" ||
        event.event === "chart" ||
        event.event === "card" ||
        event.event === "diagram"
      ) {
        nextMessages[index] = {
          ...current,
          blocks: mergeUniqueBlocks(
            current.blocks ?? [],
            normalizeIncomingBlock({
              ...(event.data as Omit<StructuredBlock, "type">),
              type: event.event,
            } as StructuredBlock),
          ),
          timeline: nextTimeline,
          mission: nextMission,
          compaction: nextCompaction,
        };
      } else if (
        event.event === "thinking" ||
        ((event.event === "lane_thinking" || event.event === "lane_agent_thinking") &&
          (event.data.lane_type === "main_chat" || !state.activeAssistantId))
      ) {
        const rawChunk = String(event.data.text ?? "");
        const chunk = getStreamingSuffix(current.thinkingContent, rawChunk);
        if (!chunk) return state;
        const turnIndex =
          typeof event.data.turn_index === "number" ? event.data.turn_index : undefined;
        const stepId = String(event.data.step_id ?? "");
        const nextSteps = [...(current.agentSteps ?? [])];

        // Find the most recent thinking step for this turn to append to
        // This allows multiple thinking steps per turn (one per step_id)
        // Thinking is streamed in many tiny provider chunks. Keep one
        // consolidated thought for the turn instead of rendering one row
        // per token/chunk (which produced dozens of "Thought for 1ms" rows).
        const thinkingStepIdx = nextSteps.findIndex((s) => s.type === "thinking");

        if (thinkingStepIdx !== -1) {
          const existingThinkingStep = nextSteps[thinkingStepIdx]!;
          nextSteps[thinkingStepIdx] = {
            ...existingThinkingStep,
            plan: appendStreamingText(existingThinkingStep.plan, chunk),
            toolOutput: appendStreamingText(existingThinkingStep.toolOutput, chunk),
          };
        } else {
          nextSteps.push({
            id: `thinking_${stepId || Date.now()}`,
            stepId,
            type: "thinking",
            status: "running",
            startedAt: new Date().toISOString(),
            plan: chunk,
            toolOutput: chunk,
            turnIndex,
          });
        }

        // Metrics calculation
        const now = Date.now();
        const metrics = { ...(current.metrics || {}) };

        if (!metrics.firstTokenAt && chunk.trim()) {
          metrics.firstTokenAt = new Date(now).toISOString();
          if (current.createdAt) {
            metrics.ttftMs = now - new Date(current.createdAt).getTime();
          }
        }

        const nextThinkingContent = appendStreamingText(current.thinkingContent, chunk);
        const totalTokens =
          estimateTokens(current.rawContent ?? "") + estimateTokens(nextThinkingContent);
        metrics.totalTokens = totalTokens;

        if (metrics.firstTokenAt) {
          const durationSec = (now - new Date(metrics.firstTokenAt).getTime()) / 1000;
          if (durationSec > 0.1) {
            metrics.tokensPerSec = Math.round((totalTokens / durationSec) * 10) / 10;
          }
        }

        nextMessages[index] = {
          ...current,
          thinkingContent: nextThinkingContent,
          agentSteps: nextSteps,
          timeline: nextTimeline,
          metrics,
          mission: nextMission,
          compaction: nextCompaction,
        };
      } else if (event.event === "error") {
        const nextSteps = (current.agentSteps ?? []).map((s) => {
          if (s.status === "running" || s.status === "awaiting_approval") {
            return { ...s, status: "failed" as const };
          }
          return s;
        });
        nextTimeline = nextTimeline.map((step) =>
          step.status === "running" || step.status === "awaiting_approval"
            ? { ...step, status: "failed" as const, completedAt: nowIso() }
            : step,
        );
        nextMessages[index] = {
          ...current,
          status: "error",
          error: {
            code: String(event.data.code ?? "STREAM_ERROR"),
            message: String(event.data.message ?? "The assistant failed to answer."),
          },
          agentSteps: nextSteps,
          timeline: nextTimeline,
          mission: nextMission,
          compaction: nextCompaction,
        };
        return {
          ...state,
          messages: nextMessages,
          activeAssistantId: null,
          isStreaming: false,
          streamError: {
            code: String(event.data.code ?? "STREAM_ERROR"),
            message: String(event.data.message ?? "The assistant failed to answer."),
          },
        };
      } else if (event.event === "done") {
        const finishedAt = nowIso();
        const nextSteps = (current.agentSteps ?? []).map((s) => {
          if (s.status === "running" || s.status === "awaiting_approval") {
            return finalizeAgentStep(s, finishedAt, "completed");
          }
          return s;
        });
        nextTimeline = nextTimeline.map((step) =>
          step.status === "running"
            ? { ...step, status: "completed" as const, completedAt: finishedAt }
            : step,
        );
        nextMessages[index] = {
          ...current,
          status: "ready",
          agentSteps: nextSteps,
          timeline: nextTimeline,
          mission: nextMission,
          compaction: nextCompaction,
        };
        return {
          ...state,
          messages: nextMessages,
          activeAssistantId: null,
          isStreaming: false,
        };
      } else if (event.event === "meta") {
        const meta = event.data as Record<string, unknown>;
        const modelName = typeof meta.model_name === "string" ? meta.model_name : undefined;
        const providerType =
          typeof meta.provider_type === "string" ? meta.provider_type : undefined;
        const contextLimit = readContextLimit(meta);
        nextMessages[index] = {
          ...current,
          metrics: {
            ...current.metrics,
            modelName,
            providerType,
            contextLimit: contextLimit ?? undefined,
          },
          timeline: nextTimeline,
          mission: nextMission,
          compaction: nextCompaction,
        };
        return {
          ...state,
          messages: nextMessages,
          currentConversationId:
            typeof meta.conversation_id === "string"
              ? meta.conversation_id
              : state.currentConversationId,
          lastModelName: modelName || state.lastModelName,
          lastProviderType: providerType || state.lastProviderType,
          lastContextLimit: contextLimit ?? null,
        };
      } else if (event.event === "metrics") {
        nextMessages[index] = {
          ...current,
          metrics: {
            ...current.metrics,
            ...(event.data as MessageMetrics),
          },
          timeline: nextTimeline,
          mission: nextMission,
          compaction: nextCompaction,
        };
      } else if (event.event === "agent_status") {
        // Legacy backend status strings are not execution evidence. Real tool
        // calls/results, provider thinking, approvals, and errors have their
        // own event types and remain visible in the timeline.
        return state;
      } else if (event.event === "agent_plan") {
        const step: AgentStep = {
          id: `step_${Date.now()}`,
          type: "plan",
          stepId: String(event.data.step_id ?? ""),
          plan: String(event.data.plan ?? ""),
          tools: (event.data.tools as string[]) ?? [],
          stepNumber: Number(event.data.step_number ?? 0),
          status: "completed",
          startedAt: new Date().toISOString(),
          turnIndex: typeof event.data.turn_index === "number" ? event.data.turn_index : undefined,
        };
        nextMessages[index] = {
          ...current,
          agentSteps: [...(current.agentSteps ?? []), step],
          timeline: nextTimeline,
          mission: nextMission,
          compaction: nextCompaction,
        };
        return { ...state, messages: nextMessages, isAgentMode: true };
      } else if (event.event === "tool_start") {
        const turnIndex =
          typeof event.data.turn_index === "number" ? event.data.turn_index : undefined;
        const toolName = String(event.data.tool_name ?? "");
        const toolInput = (event.data.tool_input as Record<string, unknown>) ?? {};
        const path = typeof toolInput.path === "string" ? toolInput.path : "";
        const oldContent = path ? (current.readFilesContents?.[path] ?? "") : "";
        let previewDiffStats: AgentStep["diffStats"] = undefined;

        if (path && (toolName === "write_file" || toolName === "file_write")) {
          const newContent = typeof toolInput.content === "string" ? toolInput.content : "";
          if (newContent) {
            const diffResult = computeLineDiff(oldContent, newContent);
            previewDiffStats = {
              path,
              additions: diffResult.additions,
              deletions: diffResult.deletions,
              diffLines: diffResult.diffLines,
            };
          }
        } else if (path && (toolName === "edit_file" || toolName === "file_edit")) {
          const oldString = typeof toolInput.old_string === "string" ? toolInput.old_string : "";
          const newString = typeof toolInput.new_string === "string" ? toolInput.new_string : "";
          const previewBase = oldContent || oldString;
          const newContent =
            oldContent && oldString && oldContent.includes(oldString)
              ? oldContent.replace(oldString, newString)
              : newString;
          if (previewBase || newContent) {
            const diffResult = computeLineDiff(previewBase, newContent);
            previewDiffStats = {
              path,
              additions: diffResult.additions,
              deletions: diffResult.deletions,
              diffLines: diffResult.diffLines,
            };
          }
        }

        const step: AgentStep = {
          id: `step_${Date.now()}`,
          type: "tool_start",
          stepId: String(event.data.step_id ?? ""),
          toolName,
          toolInput,
          permissionLevel: String(event.data.permission_level ?? "auto"),
          status: "running",
          startedAt: String(event.data.started_at ?? new Date().toISOString()),
          step_id: String(event.data.step_id ?? ""),
          tool_id: String(event.data.tool_id ?? ""),
          turnIndex,
          diffStats: previewDiffStats,
        };
        const promoted = promoteTurnTextToThinking(current, turnIndex);
        nextMessages[index] = {
          ...promoted,
          agentSteps: upsertAgentStep(promoted.agentSteps ?? [], step),
          timeline: nextTimeline,
          mission: nextMission,
          compaction: nextCompaction,
        };
      } else if (event.event === "tool_delta") {
        const toolName = String(event.data.tool_name ?? "");
        const toolId = String(event.data.tool_id ?? "");
        const stepId = String(event.data.step_id ?? "");
        const toolInput = (event.data.tool_input as Record<string, unknown>) ?? {};
        const text = formatToolDeltaChunk(String(event.data.text ?? ""), event.data.stream);
        const turnIndex =
          typeof event.data.turn_index === "number" ? event.data.turn_index : undefined;
        const step: AgentStep = {
          id: `step_${Date.now()}`,
          type: "tool_start",
          stepId,
          toolName,
          toolInput,
          toolOutput: text,
          status: "running",
          startedAt: new Date().toISOString(),
          step_id: stepId,
          tool_id: toolId,
          turnIndex,
        };
        const promoted = promoteTurnTextToThinking(current, turnIndex);
        nextMessages[index] = {
          ...promoted,
          agentSteps: upsertAgentStep(promoted.agentSteps ?? [], step),
          timeline: nextTimeline,
          mission: nextMission,
          compaction: nextCompaction,
        };
      } else if (
        event.event === "agent_testing" ||
        event.event === "agent_verifying" ||
        event.event === "agent_self_correct"
      ) {
        const step: AgentStep = {
          id: `step_${Date.now()}`,
          type: event.event,
          stepId: String(event.data.step_id ?? ""),
          toolName: String(event.data.tool_name ?? ""),
          toolInput: (event.data.tool_input as Record<string, unknown>) ?? {},
          toolOutput: String(event.data.output ?? ""),
          success: typeof event.data.success === "boolean" ? event.data.success : undefined,
          durationMs:
            typeof event.data.duration_ms === "number" ? event.data.duration_ms : undefined,
          status: event.event === "agent_self_correct" ? "failed" : "completed",
          startedAt: String(event.data.started_at ?? new Date().toISOString()),
          completedAt: String(event.data.completed_at ?? new Date().toISOString()),
          step_id: String(event.data.step_id ?? ""),
          tool_id: String(event.data.tool_id ?? ""),
          turnIndex: typeof event.data.turn_index === "number" ? event.data.turn_index : undefined,
        };
        nextMessages[index] = {
          ...current,
          agentSteps: upsertAgentStep(current.agentSteps ?? [], step),
          timeline: nextTimeline,
          mission: nextMission,
          compaction: nextCompaction,
        };
      } else if (event.event === "tool_result") {
        const toolName = String(event.data.tool_name ?? "");
        const toolId = String(event.data.tool_id ?? "");
        const stepId = String(event.data.step_id ?? "");
        const toolInput = (event.data.tool_input as Record<string, unknown>) ?? {};
        const success = Boolean(event.data.success);
        const output = String(event.data.output ?? "");

        const readFilesContents = { ...(current.readFilesContents ?? {}) };
        let diffStats: AgentStep["diffStats"] = undefined;

        const path = typeof toolInput.path === "string" ? toolInput.path : "";

        if (success && path) {
          if (toolName === "read_file" || toolName === "file_read") {
            const headerMatch = output.match(/^READ .*?:\s*\n\n/);
            const content = headerMatch ? output.slice(headerMatch[0].length) : output;
            readFilesContents[path] = content;
          } else if (toolName === "write_file" || toolName === "file_write") {
            const newContent = typeof toolInput.content === "string" ? toolInput.content : "";
            const oldContent = readFilesContents[path] || "";
            const diffResult = computeLineDiff(oldContent, newContent);
            diffStats = {
              path,
              additions: diffResult.additions,
              deletions: diffResult.deletions,
              diffLines: diffResult.diffLines,
            };
          } else if (toolName === "edit_file" || toolName === "file_edit") {
            const oldString = typeof toolInput.old_string === "string" ? toolInput.old_string : "";
            const newString = typeof toolInput.new_string === "string" ? toolInput.new_string : "";
            const oldContent = readFilesContents[path] || "";
            let newContent = "";
            if (oldContent && oldContent.includes(oldString)) {
              newContent = oldContent.replace(oldString, newString);
            } else {
              newContent = newString;
            }
            const diffResult = computeLineDiff(oldContent || oldString, newContent);
            diffStats = {
              path,
              additions: diffResult.additions,
              deletions: diffResult.deletions,
              diffLines: diffResult.diffLines,
            };
            if (newContent) {
              readFilesContents[path] = newContent;
            }
          }
        }

        const step: AgentStep = {
          id: `step_${Date.now()}`,
          type: "tool_result",
          stepId,
          toolName,
          toolInput,
          toolOutput: output,
          success,
          durationMs: Number(event.data.duration_ms ?? 0),
          status: success ? "completed" : "failed",
          startedAt: new Date().toISOString(),
          completedAt: String(event.data.completed_at ?? new Date().toISOString()),
          step_id: stepId,
          tool_id: toolId,
          turnIndex: typeof event.data.turn_index === "number" ? event.data.turn_index : undefined,
          diffStats,
        };
        nextMessages[index] = {
          ...current,
          readFilesContents,
          agentSteps: upsertAgentStep(current.agentSteps ?? [], step),
          timeline: nextTimeline,
          mission: nextMission,
          compaction: nextCompaction,
        };
      } else if (event.event === "observing") {
        // `observing` was a descriptive companion event for a different tool,
        // not a call to the real `observe` function. Ignore it entirely.
        return state;
      } else if (event.event === "tool_error") {
        const step: AgentStep = {
          id: `step_${Date.now()}`,
          type: "tool_error",
          stepId: String(event.data.step_id ?? ""),
          toolOutput: String(event.data.error ?? ""),
          status: "failed",
          startedAt: new Date().toISOString(),
          turnIndex: typeof event.data.turn_index === "number" ? event.data.turn_index : undefined,
        };
        nextMessages[index] = {
          ...current,
          agentSteps: upsertAgentStep(current.agentSteps ?? [], step),
          timeline: nextTimeline,
          mission: nextMission,
          compaction: nextCompaction,
        };
      } else if (event.event === "permission_granted" || event.event === "permission_denied") {
        const approvalId = String(event.data.approval_id ?? "");
        const toolId = String(event.data.tool_id ?? "");
        const nextSteps: AgentStep[] = (current.agentSteps ?? []).map((step) => {
          const matchesApproval = approvalId && String(step.data?.approval_id ?? "") === approvalId;
          const matchesTool = toolId && String(step.tool_id ?? step.toolId ?? "") === toolId;
          if (!matchesApproval && !matchesTool) return step;
          return {
            ...step,
            status: (event.event === "permission_granted"
              ? "running"
              : "failed") as AgentStep["status"],
            completedAt: event.event === "permission_denied" ? new Date().toISOString() : undefined,
          };
        });
        nextMessages[index] = {
          ...current,
          agentSteps: nextSteps,
          timeline: nextTimeline,
          mission: nextMission,
          compaction: nextCompaction,
        };
      } else if (event.event === "permission_request" || event.event === "approval_request") {
        const turnIndex =
          typeof event.data.turn_index === "number" ? event.data.turn_index : undefined;
        const step: AgentStep = {
          id: `step_${Date.now()}`,
          type: "permission_request",
          stepId: String(event.data.step_id ?? event.data.lane_id ?? ""),
          toolName: String(event.data.tool_name ?? ""),
          toolInput: (event.data.tool_input as Record<string, unknown>) ?? {},
          permissionLevel: String(event.data.permission_level ?? "approval"),
          status: "awaiting_approval",
          startedAt: new Date().toISOString(),
          step_id: String(event.data.step_id ?? event.data.lane_id ?? ""),
          tool_id: String(event.data.tool_id ?? event.data.mission_id ?? ""),
          data: event.data,
          turnIndex,
        };
        const promoted = promoteTurnTextToThinking(current, turnIndex);
        nextMessages[index] = {
          ...promoted,
          agentSteps: upsertAgentStep(promoted.agentSteps ?? [], step),
          timeline: nextTimeline,
          mission: nextMission,
          compaction: nextCompaction,
        };
      } else if (event.event === "ask_user_question") {
        const turnIndex =
          typeof event.data.turn_index === "number" ? event.data.turn_index : undefined;
        const step: AgentStep = {
          id: `step_${Date.now()}`,
          type: "ask_user_question",
          stepId: String(event.data.step_id ?? ""),
          toolName: String(event.data.tool_name ?? "ask_user_question"),
          toolInput: (event.data.tool_input as Record<string, unknown>) ?? {},
          permissionLevel: String(event.data.permission_level ?? "clarification"),
          status: "awaiting_approval",
          startedAt: new Date().toISOString(),
          step_id: String(event.data.step_id ?? ""),
          tool_id: String(event.data.tool_id ?? ""),
          data: event.data,
          turnIndex,
        };
        const promoted = promoteTurnTextToThinking(current, turnIndex);
        nextMessages[index] = {
          ...promoted,
          agentSteps: upsertAgentStep(promoted.agentSteps ?? [], step),
          timeline: nextTimeline,
          mission: nextMission,
          compaction: nextCompaction,
        };
      } else if (event.event === "step_summary") {
        const step: AgentStep = {
          id: `step_${Date.now()}`,
          type: "plan",
          plan: String(event.data.message ?? ""),
          status: "completed",
          startedAt: new Date().toISOString(),
          turnIndex: typeof event.data.turn_index === "number" ? event.data.turn_index : undefined,
        };
        nextMessages[index] = {
          ...current,
          agentSteps: [...(current.agentSteps ?? []), step],
          timeline: nextTimeline,
          mission: nextMission,
          compaction: nextCompaction,
        };
      } else if (nextMission !== current.mission) {
        nextMessages[index] = {
          ...current,
          mission: nextMission,
          timeline: nextTimeline,
          compaction: nextCompaction,
        };
      }

      return {
        ...state,
        messages: nextMessages,
      };
    }
    default:
      return state;
  }
}

function parseDurableNumber(value: unknown): number | undefined {
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : undefined;
}

function durableStateFromHistory(
  messages: DeepSpaceHistoryMessage[],
): DurableMissionRuntimeState | null {
  for (const message of [...messages].reverse()) {
    const metadata = message.metadata_json;
    if (!metadata || typeof metadata.durable_run_id !== "string") continue;
    const runId = metadata.durable_run_id;
    return {
      runId,
      status:
        typeof metadata.durable_run_status === "string" ? metadata.durable_run_status : undefined,
      lastSequence: parseDurableNumber(metadata.durable_sequence) ?? 0,
      checkpointSequence: parseDurableNumber(metadata.durable_checkpoint_sequence) ?? null,
      continuationEpoch: parseDurableNumber(metadata.durable_continuation_epoch),
      recoveryCount: parseDurableNumber(metadata.durable_recovery_count),
      reconnectState: "reconnecting",
      replayReadOnly: true,
    };
  }
  return null;
}

function syncDurableRuntimeState(
  state: DeepSpaceThreadState,
  action: DeepSpaceThreadAction,
): DeepSpaceThreadState {
  if (action.type === "reset_thread") {
    return { ...state, durableRun: null };
  }

  if (action.type === "load_history") {
    return { ...state, durableRun: durableStateFromHistory(action.messages) };
  }

  if (action.type === "stream_interrupted") {
    return state.durableRun
      ? { ...state, durableRun: { ...state.durableRun, reconnectState: "interrupted" } }
      : state;
  }

  if (action.type === "stream_finished") {
    return state.durableRun
      ? { ...state, durableRun: { ...state.durableRun, reconnectState: "connected" } }
      : state;
  }

  if (action.type !== "stream_event") {
    return state;
  }

  const data = action.event.data;
  const runId =
    typeof data.durable_run_id === "string"
      ? data.durable_run_id
      : typeof data.run_id === "string"
        ? data.run_id
        : action.event.event === "mission_start" && typeof data.mission_id === "string"
          ? data.mission_id
          : state.durableRun?.runId;
  const sequence = parseDurableNumber(data.sequence);
  const durableEventType =
    typeof data.durable_event_type === "string" ? data.durable_event_type : "";
  const isDurableEvent = Boolean(
    data.durable_run_id || data.durable_event_type || sequence !== undefined,
  );
  if (!isDurableEvent || !runId) {
    return state;
  }

  const current = state.durableRun;
  // PostgreSQL replay and SSE reconnects may deliver an already acknowledged
  // event again. The cursor is the durable identity, so do not let a replay
  // append duplicate timeline/tool steps or move runtime state backwards.
  if (sequence !== undefined && current?.runId === runId && sequence <= current.lastSequence) {
    return state;
  }
  const status =
    typeof data.status === "string"
      ? data.status
      : durableEventType === "run_completed"
        ? "completed"
        : durableEventType === "run_failed"
          ? "failed"
          : durableEventType === "run_cancelled"
            ? "cancelled"
            : current?.status;
  const approvalDelta =
    durableEventType === "approval_requested" || durableEventType === "run_paused_for_approval"
      ? 1
      : durableEventType === "approval_resolved"
        ? -1
        : 0;
  const next: DurableMissionRuntimeState = {
    runId,
    status,
    lastSequence: Math.max(current?.lastSequence ?? 0, sequence ?? 0),
    checkpointSequence:
      parseDurableNumber(data.checkpoint_sequence) !== undefined
        ? Math.max(
            current?.checkpointSequence ?? 0,
            parseDurableNumber(data.checkpoint_sequence) ?? 0,
          )
        : (current?.checkpointSequence ?? null),
    continuationEpoch:
      parseDurableNumber(data.continuation_epoch) !== undefined
        ? Math.max(
            current?.continuationEpoch ?? 0,
            parseDurableNumber(data.continuation_epoch) ?? 0,
          )
        : current?.continuationEpoch,
    recoveryCount:
      parseDurableNumber(data.recovery_count) !== undefined
        ? Math.max(current?.recoveryCount ?? 0, parseDurableNumber(data.recovery_count) ?? 0)
        : current?.recoveryCount,
    pendingApprovals: Math.max(0, (current?.pendingApprovals ?? 0) + approvalDelta),
    reconnectState:
      data.durable_transport_state === "reconnecting" ||
      data.durable_transport_state === "interrupted"
        ? data.durable_transport_state
        : "connected",
    budgetUsage:
      data.budget_usage && typeof data.budget_usage === "object"
        ? (data.budget_usage as Record<string, number>)
        : current?.budgetUsage,
    budgetLimits:
      data.budget_limits && typeof data.budget_limits === "object"
        ? (data.budget_limits as Record<string, number>)
        : current?.budgetLimits,
    supervisorDecision:
      typeof data.supervisor_decision === "string"
        ? data.supervisor_decision
        : current?.supervisorDecision,
    replayReadOnly: true,
  };
  return { ...state, durableRun: next };
}

export function deepSpaceThreadReducer(
  state: DeepSpaceThreadState,
  action: DeepSpaceThreadAction,
): DeepSpaceThreadState {
  if (action.type === "stream_event") {
    const data = action.event.data;
    const sequence = parseDurableNumber(data.sequence);
    const runId = typeof data.durable_run_id === "string" ? data.durable_run_id : undefined;
    if (
      sequence !== undefined &&
      runId &&
      state.durableRun?.runId === runId &&
      sequence <= state.durableRun.lastSequence
    ) {
      return state;
    }
  }
  return syncDurableRuntimeState(reduceDeepSpaceThread(state, action), action);
}
