"use client";

/* LiveKit's browser event surface is intentionally dynamic; its event payloads
 * are validated by the runtime before entering the DeepSpace reducer. */
/* eslint-disable @typescript-eslint/no-explicit-any */

import { AnimatePresence, motion } from "framer-motion";
import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import {
  AlertCircle,
  History,
  Columns2,
  PanelLeftClose,
  PanelRightClose,
  CircleStop,
  RotateCcw,
  Download,
  Sparkles,
} from "lucide-react";
import toast from "react-hot-toast";

import ChatSidebar from "@/app/components/dashboard/ChatSidebar";
import { fetchWithAuth } from "@/lib/api";
import { saveMCPActiveContext } from "@/lib/mcp-context";
import {
  listProviders,
  listProviderModels,
  listAssignments,
  createAssignment,
  updateAssignment,
} from "@/lib/providers-api";

import { useDeepSpaceStream } from "../_hooks/useDeepSpaceStream";
import { initialDeepSpaceThreadState, deepSpaceThreadReducer } from "../_lib/deepspace-thread";
import type {
  DeepSpaceHistoryMessage,
  AgentStep,
  ConversationCompactionState,
} from "../_lib/deepspace-stream";
import { resolveLatestEditableMessageId } from "../../query/_lib/edit-target";
import { estimateTokens } from "../../query/_lib/stream-protocol";

import DeepSpaceComposer from "./DeepSpaceComposer";
import DeepSpaceThread from "./DeepSpaceThread";
import DeepSpaceScrollTracker from "@/app/dashboard/query/_components/DeepSpaceScrollTracker";
import AgentCapabilities from "./AgentCapabilities";
import ExecutionModeDropdown from "./ExecutionModeDropdown";
import RuntimePreferencesDropdown, {
  type RuntimePreferencesValue,
} from "./RuntimePreferencesDropdown";

export interface DeepSpaceRuntimeMetrics {
  usage: number;
  tokens: number;
  tools: string[];
  contextLimit: number | null;
  contextLimitSource?: string | null;
  contextUsedTokens: number;
  contextRemainingTokens: number | null;
  modelName?: string | null;
  providerType?: string | null;
  phase?: string | null;
  compaction?: ConversationCompactionState | null;
  latencyTimeline?: Array<{
    label: string;
    atMs: number;
    detail?: string;
  }>;
  agentSteps?: AgentStep[];
}

const DEFAULT_RUNTIME_PREFERENCES: RuntimePreferencesValue = {
  planner_mode: "default",
  subagent_profile: "default",
  runtime_hooks_enabled: true,
  workspace_mode_enabled: true,
  full_autonomy_enabled: false,
};

type RuntimeTimelineEntry = {
  label: string;
  atMs: number;
  detail: string | undefined;
};

function readRuntimeMetricsEvent(
  event: DeepSpaceHistoryMessage | { event: string; data: Record<string, unknown> },
): DeepSpaceRuntimeMetrics | null {
  if ("event" in event && event.event !== "agent_status" && event.event !== "metrics") {
    return null;
  }
  const data = "event" in event ? event.data : {};
  const timeline = Array.isArray(data.latencyTimeline)
    ? (data.latencyTimeline
        .map((item) =>
          item && typeof item === "object"
            ? ({
                label: String((item as Record<string, unknown>).label ?? ""),
                atMs: Number((item as Record<string, unknown>).atMs ?? 0),
                detail:
                  typeof (item as Record<string, unknown>).detail === "string"
                    ? String((item as Record<string, unknown>).detail)
                    : undefined,
              } satisfies RuntimeTimelineEntry)
            : null,
        )
        .filter((item): item is RuntimeTimelineEntry =>
          Boolean(item && item.label),
        ) as RuntimeTimelineEntry[])
    : [];
  return {
    usage: Number(data.context_usage || 0),
    tokens: Number(data.context_used_tokens || data.token_count || 0),
    tools: (data.active_tools as string[]) || [],
    contextLimit:
      typeof data.context_limit === "number" && data.context_limit > 0 ? data.context_limit : null,
    contextLimitSource:
      typeof data.context_limit_source === "string" ? data.context_limit_source : null,
    contextUsedTokens: Number(data.context_used_tokens || 0),
    contextRemainingTokens:
      typeof data.context_remaining_tokens === "number" ? data.context_remaining_tokens : null,
    modelName: typeof data.model_name === "string" ? data.model_name : null,
    providerType: typeof data.provider_type === "string" ? data.provider_type : null,
    phase: typeof data.phase === "string" ? data.phase : null,
    compaction:
      data.compaction_state && typeof data.compaction_state === "object"
        ? ({
            version: Number((data.compaction_state as Record<string, unknown>).version ?? 1),
            trigger: String((data.compaction_state as Record<string, unknown>).trigger ?? "manual"),
            compactedAt: String(
              (data.compaction_state as Record<string, unknown>).compacted_at ?? "",
            ),
            anchorMessageId: String(
              (data.compaction_state as Record<string, unknown>).anchor_message_id ?? "",
            ),
            summary: String((data.compaction_state as Record<string, unknown>).summary ?? ""),
            summarizedCount: Number(
              (data.compaction_state as Record<string, unknown>).summarized_count ?? 0,
            ),
            keptRecentCount: Number(
              (data.compaction_state as Record<string, unknown>).kept_recent_count ?? 0,
            ),
            beforeTokens: Number(
              (data.compaction_state as Record<string, unknown>).before_tokens ?? 0,
            ),
            afterTokens: Number(
              (data.compaction_state as Record<string, unknown>).after_tokens ?? 0,
            ),
            savedTokens: Number(
              (data.compaction_state as Record<string, unknown>).saved_tokens ?? 0,
            ),
          } satisfies ConversationCompactionState)
        : null,
    latencyTimeline: timeline,
    agentSteps: undefined, // Handled primarily by the message sync useEffect
  };
}

const buildInitialPrompt = (messages: any[], currentContent?: string): string => {
  const wordsSet = new Set<string>([
    "AverQel", "DeepSpace", "LiveKit", "Docker", "Next.js",
    "TypeScript", "Minio", "Postgres", "Redis", "compose",
    "git", "status", "workspace", "orchestrator", "agent"
  ]);

  const recentMessages = messages.slice(-3);
  for (const msg of recentMessages) {
    const text = msg.content || msg.text || "";
    const cleanText = text.replace(/[^\w\s-]/g, " ");
    const words = cleanText.split(/\s+/);
    for (const w of words) {
      if (w.length > 3 && !/^\d+$/.test(w)) {
        wordsSet.add(w);
      }
    }
  }

  if (currentContent) {
    const textSnippet = currentContent.slice(0, 1000);
    const cleanSnippet = textSnippet.replace(/<[^>]*>/g, " ").replace(/[^\w\s-]/g, " ");
    const words = cleanSnippet.split(/\s+/);
    for (const w of words) {
      if (w.length > 3 && !/^\d+$/.test(w) && wordsSet.size < 100) {
        wordsSet.add(w);
      }
    }
  }

  return Array.from(wordsSet).join(" ");
};

interface DeepSpaceChatClientProps {
  onInsertLatestAnswer?: (content: string) => void;
  onSelectNote?: (noteId: string) => void;
  onNewNote?: () => void;
  onConversationRenamed?: (note: {
    id: string;
    title: string;
    updated_at: string;
    content_html?: string | null;
  }) => void;
  onMetricsUpdate?: (metrics: DeepSpaceRuntimeMetrics) => void;
  activeConversationId: string | null;
  currentContent?: string;
  runtimeContextLimit?: number | null;
  runtimeModelName?: string | null;
  runtimeProviderType?: string | null;
  isMobileStacked?: boolean;
  showCollapseControls?: boolean;
  panelMode?: "split" | "notes" | "chat";
  onSetPanelMode?: (mode: "split" | "notes" | "chat") => void;
  isHistoryOpen?: boolean;
  onSetHistoryOpen?: (open: boolean) => void;
}

const EMPTY_PROMPTS = [
  "Help me think through this idea clearly.",
  "Draft a concise message I can send to my team.",
  "Turn these rough thoughts into a cleaner note.",
  "Explain this topic simply, then improve the wording.",
];
const TOKEN_ESTIMATE_HISTORY_WINDOW = 64;

export default function DeepSpaceChatClient({
  onInsertLatestAnswer,
  onSelectNote,
  onNewNote,
  onConversationRenamed,
  onMetricsUpdate,
  activeConversationId,
  currentContent,
  runtimeContextLimit,
  runtimeModelName,
  runtimeProviderType,
  isMobileStacked,
  showCollapseControls = true,
  onSetPanelMode,
  isHistoryOpen,
  onSetHistoryOpen,
}: DeepSpaceChatClientProps) {
  const [state, dispatch] = useReducer(deepSpaceThreadReducer, initialDeepSpaceThreadState);
  const [query, setQuery] = useState("");
  const [localHistoryOpen, setLocalHistoryOpen] = useState(false);
  const historyOpen = isHistoryOpen !== undefined ? isHistoryOpen : localHistoryOpen;
  const setHistoryOpen = onSetHistoryOpen !== undefined ? onSetHistoryOpen : setLocalHistoryOpen;
  const [executionMode, setExecutionMode] = useState<"auto_review" | "full_access">("auto_review");
  const [runtimePreferences, setRuntimePreferences] = useState<RuntimePreferencesValue>(
    DEFAULT_RUNTIME_PREFERENCES,
  );
  const [isSavingRuntimePreferences, setIsSavingRuntimePreferences] = useState(false);
  const [isAgenticWork, setIsAgenticWork] = useState(true);
  const [fullAutonomyEnabled, setFullAutonomyEnabled] = useState(false);
  const thinkingEnabled = true;
  const webSearchEnabled = true;
  const [threadScrollMetrics, setThreadScrollMetrics] = useState<{
    scrollTop: number;
    viewportHeight: number;
  } | null>(null);
  const runtimeIndicatorState = useMemo(
    () => ({
      executionMode: executionMode,
      plannerMode: runtimePreferences.planner_mode,
      subagentProfile: runtimePreferences.subagent_profile,
      runtimeHooksEnabled: runtimePreferences.runtime_hooks_enabled,
      workspaceModeEnabled: runtimePreferences.workspace_mode_enabled,
    }),
    [executionMode, runtimePreferences],
  );


  const [availableModels, setAvailableModels] = useState<
    Array<{ providerId: string; modelName: string; displayName: string }>
  >([]);
  const [isLoadingModels, setIsLoadingModels] = useState(false);
  const [selectedModelOverride, setSelectedModelOverride] = useState<string | null>(null);

  const [sttActive, setSttActive] = useState(false);
  const [ttsActive, setTtsActive] = useState(false);
  const [voiceState, setVoiceState] = useState<"idle" | "listening" | "thinking" | "speaking">("idle");
  const [voiceLabel, setVoiceLabel] = useState<string>("");
  const roomRef = useRef<any>(null);
  const queryRef = useRef(query);
  const baseQueryRef = useRef("");
  const typingQueueRef = useRef<string[]>([]);
  const typingIntervalRef = useRef<any>(null);
  const messagesRef = useRef(state.messages);
  const currentContentRef = useRef(currentContent);

  useEffect(() => {
    queryRef.current = query;
  }, [query]);

  useEffect(() => {
    messagesRef.current = state.messages;
  }, [state.messages]);

  useEffect(() => {
    currentContentRef.current = currentContent;
  }, [currentContent]);

  useEffect(() => {
    return () => {
      if (typingIntervalRef.current) {
        clearInterval(typingIntervalRef.current);
      }
    };
  }, []);

  const startTypingLoop = useCallback(() => {
    if (typingIntervalRef.current) return;

    typingIntervalRef.current = setInterval(() => {
      if (typingQueueRef.current.length > 0) {
        const nextChar = typingQueueRef.current.shift();
        if (nextChar !== undefined) {
          setQuery((prev) => prev + nextChar);
        }
      } else {
        if (typingIntervalRef.current) {
          clearInterval(typingIntervalRef.current);
          typingIntervalRef.current = null;
        }
      }
    }, 15);
  }, []);

  const queueText = useCallback((targetText: string) => {
    const currentText = queryRef.current;

    if (targetText.startsWith(currentText)) {
      const suffix = targetText.slice(currentText.length);
      typingQueueRef.current = suffix.split("");
    } else {
      let i = 0;
      while (i < currentText.length && i < targetText.length && currentText[i] === targetText[i]) {
        i++;
      }
      const commonPrefix = currentText.slice(0, i);
      const suffix = targetText.slice(commonPrefix.length);

      setQuery(commonPrefix);
      typingQueueRef.current = suffix.split("");
    }

    startTypingLoop();
  }, [startTypingLoop]);

  useEffect(() => {
    return () => {
      if (roomRef.current) {
        roomRef.current.disconnect();
        roomRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    let active = true;
    const fetchModelsAndAssignments = async () => {
      setIsLoadingModels(true);
      try {
        const [providersList, assignmentsList] = await Promise.all([
          listProviders(),
          listAssignments(),
        ]);
        if (!active) return;

        const chatProviders = providersList.filter((p) => p.enabled && p.supports_chat);
        const allChatModels: Array<{ providerId: string; modelName: string; displayName: string }> =
          [];

        await Promise.all(
          chatProviders.map(async (provider) => {
            try {
              const models = await listProviderModels(provider.id);
              const chatOnly = models.filter((m) => m.model_kind === "chat");
              if (active) {
                allChatModels.push(
                  ...chatOnly.map((m) => ({
                    providerId: provider.id,
                    modelName: m.model_name,
                    displayName: m.display_name || m.model_name,
                  })),
                );
              }
            } catch (err) {
              console.error(`Failed to list models for provider ${provider.id}`, err);
            }
          }),
        );

        if (active) {
          setAvailableModels(allChatModels);
        }
      } catch (err) {
        console.error("Failed to load models/assignments", err);
      } finally {
        if (active) setIsLoadingModels(false);
      }
    };

    void fetchModelsAndAssignments();
    return () => {
      active = false;
    };
  }, []);

  const handleModelSelect = useCallback(async (providerId: string, modelName: string) => {
    const toastId = toast.loading("Switching model...");
    try {
      const assignmentsList = await listAssignments();
      const chatAssignment = assignmentsList.find((a) => a.feature_scope === "chat");

      if (chatAssignment) {
        await updateAssignment(chatAssignment.id, {
          provider_config_id: providerId,
          model_name: modelName,
          enabled: true,
        });
      } else {
        await createAssignment({
          feature_scope: "chat",
          provider_config_id: providerId,
          model_name: modelName,
          enabled: true,
        });
      }

      toast.success(`Switched model to ${modelName}`, { id: toastId });
      setSelectedModelOverride(modelName);

      void fetchWithAuth("/deepspace/chats/runtime");
    } catch (err) {
      console.error("Failed to switch model", err);
      toast.error("Failed to switch model", { id: toastId });
    }
  }, []);

  const scrollContainerRef = useRef<HTMLDivElement | null>(null);
  const autoFollowRef = useRef(true);
  const pendingHistorySyncRef = useRef(false);
  const scrollMetricsRafRef = useRef<number | null>(null);

  const syncThreadScrollMetrics = useCallback((element: HTMLDivElement) => {
    if (scrollMetricsRafRef.current !== null) {
      window.cancelAnimationFrame(scrollMetricsRafRef.current);
    }
    scrollMetricsRafRef.current = window.requestAnimationFrame(() => {
      setThreadScrollMetrics({
        scrollTop: element.scrollTop,
        viewportHeight: element.clientHeight,
      });
      scrollMetricsRafRef.current = null;
    });
  }, []);

  const stream = useDeepSpaceStream(
    useMemo(
      () => ({
        onEvent: (event) => {
          const runtimeMetrics = readRuntimeMetricsEvent(event);
          if (runtimeMetrics) {
            onMetricsUpdate?.(runtimeMetrics);
          }
          if (roomRef.current && ttsActive) {
            const eventPayload = JSON.stringify({
              type: "agentic-step",
              event: event.event,
              data: event.data,
            });
            roomRef.current.localParticipant.publishData(new TextEncoder().encode(eventPayload)).catch((err: any) => {
              console.warn("Failed to publish agentic-step event to voice room:", err);
            });
          }
          dispatch({ type: "stream_event", event });
        },
        onEvents: (events) => {
          for (const event of events) {
            const runtimeMetrics = readRuntimeMetricsEvent(event);
            if (runtimeMetrics) {
              onMetricsUpdate?.(runtimeMetrics);
            }
            if (roomRef.current && ttsActive) {
              const eventPayload = JSON.stringify({
                type: "agentic-step",
                event: event.event,
                data: event.data,
              });
              roomRef.current.localParticipant.publishData(new TextEncoder().encode(eventPayload)).catch((err: any) => {
                console.warn("Failed to publish agentic-step event to voice room:", err);
              });
            }
          }
          dispatch({ type: "stream_events", events });
        },
        onTransportError: (error) => dispatch({ type: "stream_failed", error }),
        onUserCancel: () => dispatch({ type: "stream_interrupted" }),
        onFinally: () => dispatch({ type: "stream_finished" }),
      }),
      [onMetricsUpdate, ttsActive],
    ),
  );

  const loadConversation = useCallback(async (conversationId: string) => {
    // A page transition can race the API request. Retry short transient
    // failures and keep the current thread visible instead of replacing it
    // with an empty reducer state.
    for (let attempt = 0; attempt < 3; attempt += 1) {
      try {
        const response = (await fetchWithAuth(
          `/deepspace/chats/${conversationId}/messages`,
        )) as Response;
        if (response.ok) {
          const payload = (await response.json()) as { messages: DeepSpaceHistoryMessage[] };
          dispatch({ type: "load_history", conversationId, messages: payload.messages });
          return;
        }
        if (response.status === 404) {
          dispatch({ type: "reset_thread" });
          return;
        }
      } catch (error) {
        if (attempt === 2) {
          console.error("Failed to load DeepSpace conversation history", error);
        }
      }
      await new Promise((resolve) => window.setTimeout(resolve, 250 * (attempt + 1)));
    }
  }, []);

  useEffect(() => {
    saveMCPActiveContext({ conversation_id: activeConversationId });
    if (activeConversationId) {
      void loadConversation(activeConversationId);
    } else {
      dispatch({ type: "reset_thread" });
    }
  }, [activeConversationId, loadConversation]);

  useEffect(
    () => () => {
      if (scrollMetricsRafRef.current !== null) {
        window.cancelAnimationFrame(scrollMetricsRafRef.current);
      }
    },
    [],
  );

  useEffect(() => {
    let cancelled = false;
    const loadRuntimePreferences = async () => {
      const query = activeConversationId
        ? `?conversation_id=${encodeURIComponent(activeConversationId)}`
        : "";
      const response = (await fetchWithAuth(
        `/deepspace/chats/runtime-preferences${query}`,
      )) as Response;
      if (!response.ok) {
        return;
      }
      const payload = (await response.json()) as {
        execution_mode?: "auto_review" | "full_access";
      } & Partial<RuntimePreferencesValue>;
      if (cancelled) {
        return;
      }
      if (payload.execution_mode) {
        setExecutionMode(payload.execution_mode);
      }
      setRuntimePreferences({
        planner_mode: payload.planner_mode ?? DEFAULT_RUNTIME_PREFERENCES.planner_mode,
        subagent_profile: payload.subagent_profile ?? DEFAULT_RUNTIME_PREFERENCES.subagent_profile,
        runtime_hooks_enabled:
          payload.runtime_hooks_enabled ?? DEFAULT_RUNTIME_PREFERENCES.runtime_hooks_enabled,
        workspace_mode_enabled:
          payload.workspace_mode_enabled ?? DEFAULT_RUNTIME_PREFERENCES.workspace_mode_enabled,
        full_autonomy_enabled:
          payload.full_autonomy_enabled ?? DEFAULT_RUNTIME_PREFERENCES.full_autonomy_enabled,
      });
      setFullAutonomyEnabled(
        payload.full_autonomy_enabled ?? DEFAULT_RUNTIME_PREFERENCES.full_autonomy_enabled ?? false,
      );
    };
    void loadRuntimePreferences();
    return () => {
      cancelled = true;
    };
  }, [activeConversationId]);

  const updateExecutionMode = useCallback(
    async (nextMode: "auto_review" | "full_access") => {
      const previousMode = executionMode;
      setExecutionMode(nextMode);
      try {
        const response = (await fetchWithAuth("/deepspace/chats/runtime-preferences", {
          method: "PATCH",
          body: JSON.stringify({
            execution_mode: nextMode,
            conversation_id: activeConversationId,
          }),
        })) as Response;
        if (!response.ok) {
          setExecutionMode(previousMode);
          toast.error("Unable to update execution mode.");
          return;
        }
        const payload = (await response.json()) as {
          execution_mode?: "auto_review" | "full_access";
        } & Partial<RuntimePreferencesValue>;
        setExecutionMode(payload.execution_mode ?? nextMode);
        setRuntimePreferences((current) => ({
          ...current,
          planner_mode: payload.planner_mode ?? current.planner_mode,
          subagent_profile: payload.subagent_profile ?? current.subagent_profile,
          runtime_hooks_enabled: payload.runtime_hooks_enabled ?? current.runtime_hooks_enabled,
          workspace_mode_enabled: payload.workspace_mode_enabled ?? current.workspace_mode_enabled,
          full_autonomy_enabled:
            payload.full_autonomy_enabled ?? current.full_autonomy_enabled,
        }));
        if (typeof payload.full_autonomy_enabled === "boolean") {
          setFullAutonomyEnabled(payload.full_autonomy_enabled);
        }
      } catch (error) {
        console.error("Failed to update execution mode", error);
        setExecutionMode(previousMode);
        toast.error("Unable to update execution mode.");
      }
    },
    [activeConversationId, executionMode],
  );

  const updateRuntimePreferences = useCallback(
    async (changes: Partial<RuntimePreferencesValue>) => {
      const previous = runtimePreferences;
      const optimistic = {
        ...runtimePreferences,
        ...changes,
      };
      setRuntimePreferences(optimistic);
      setIsSavingRuntimePreferences(true);
      try {
        const response = (await fetchWithAuth("/deepspace/chats/runtime-preferences", {
          method: "PATCH",
          body: JSON.stringify({
            conversation_id: activeConversationId,
            ...changes,
          }),
        })) as Response;
        if (!response.ok) {
          setRuntimePreferences(previous);
          toast.error("Unable to save runtime controls.");
          return;
        }
        const payload = (await response.json()) as {
          execution_mode?: "auto_review" | "full_access";
        } & Partial<RuntimePreferencesValue>;
        setExecutionMode(payload.execution_mode ?? executionMode);
        setRuntimePreferences({
          planner_mode: payload.planner_mode ?? previous.planner_mode,
          subagent_profile: payload.subagent_profile ?? previous.subagent_profile,
          runtime_hooks_enabled: payload.runtime_hooks_enabled ?? previous.runtime_hooks_enabled,
          workspace_mode_enabled: payload.workspace_mode_enabled ?? previous.workspace_mode_enabled,
          full_autonomy_enabled:
            payload.full_autonomy_enabled ?? previous.full_autonomy_enabled,
        });
        setFullAutonomyEnabled(
          payload.full_autonomy_enabled ?? previous.full_autonomy_enabled ?? false,
        );
      } catch (error) {
        console.error("Failed to save runtime controls", error);
        setRuntimePreferences(previous);
        toast.error("Unable to save runtime controls.");
      } finally {
        setIsSavingRuntimePreferences(false);
      }
    },
    [activeConversationId, executionMode, runtimePreferences],
  );

  useEffect(() => {
    if (!state.isStreaming && pendingHistorySyncRef.current && state.currentConversationId) {
      pendingHistorySyncRef.current = false;
      if (state.streamError) {
        return;
      }
      void loadConversation(state.currentConversationId);
    }
  }, [loadConversation, state.currentConversationId, state.isStreaming, state.streamError]);

  const submitQuery = useCallback(
    async (nextQuery?: string) => {
      const effectiveQuery = (nextQuery ?? query).trim();
      if (!effectiveQuery || state.isStreaming) return;

      setQuery("");
      autoFollowRef.current = true;
      dispatch({ type: "submit_query", query: effectiveQuery });
      pendingHistorySyncRef.current = true;

      await stream.start({
        endpoint: "/deepspace/chats/stream",
        body: {
          query: effectiveQuery,
          conversation_id: state.currentConversationId,
          note_content: currentContent,
          thinking_enabled: thinkingEnabled,
          web_search_enabled: webSearchEnabled,
          agentic_mode: isAgenticWork,
        },
      });
    },
    [
      query,
      state.currentConversationId,
      state.isStreaming,
      stream,
      currentContent,
      thinkingEnabled,
      webSearchEnabled,
      isAgenticWork,
    ],
  );

  const startNewChat = useCallback(() => {
    stream.cancel();
    setQuery("");
    pendingHistorySyncRef.current = false;
    dispatch({ type: "reset_thread" });
    onNewNote?.();
  }, [stream, onNewNote]);

  const stopStreaming = useCallback(() => {
    stream.cancel();
    if (state.currentConversationId) {
      fetchWithAuth(`/deepspace/chats/${state.currentConversationId}/cancel`, {
        method: "POST",
      }).catch((err) => console.error("Failed to cancel active mission:", err));
    }
  }, [stream, state.currentConversationId]);

  const syncVoiceSession = useCallback(async (nextStt: boolean, nextTts: boolean) => {
    setSttActive(nextStt);
    setTtsActive(nextTts);

    if (!nextStt && !nextTts) {
      if (roomRef.current) {
        roomRef.current.disconnect();
        roomRef.current = null;
      }
      if (typingIntervalRef.current) {
        clearInterval(typingIntervalRef.current);
        typingIntervalRef.current = null;
      }
      if (typingQueueRef.current.length > 0) {
        const remaining = typingQueueRef.current.join("");
        setQuery((prev) => prev + remaining);
        typingQueueRef.current = [];
      }
      setVoiceState("idle");
      setVoiceLabel("");
      return;
    }

    setVoiceState("listening");
    setVoiceLabel("Connecting voice room...");

    try {
      const { Room, RoomEvent } = await import("livekit-client");

      let room = roomRef.current;
      if (!room) {
        room = new Room();
        roomRef.current = room;

        try {
          await room.startAudio();
          console.log("LiveKit audio context resumed.");
        } catch (e) {
          console.warn("Failed to resume audio context", e);
        }

        const uniqueRoom = `deepspace-room-${Math.random().toString(36).slice(2, 8)}`;
        const tokenRes = await fetch(`/api/v1/voice/token?room=${uniqueRoom}&identity=user-${Math.random().toString(36).slice(2, 6)}`);
        const { token } = await tokenRes.json();

        room.on(RoomEvent.DataReceived, (payload: Uint8Array) => {
          try {
            const data = JSON.parse(new TextDecoder().decode(payload));
            if (data.state) {
              setVoiceState(data.state);
              if (data.state === "listening") {
                setVoiceLabel(data.text ? `Transcript: "${data.text}"` : "Speak now...");
                if (data.text === "...") {
                  if (typingIntervalRef.current) {
                    clearInterval(typingIntervalRef.current);
                    typingIntervalRef.current = null;
                  }
                  typingQueueRef.current = [];
                  baseQueryRef.current = queryRef.current;
                } else if (data.text) {
                  const base = baseQueryRef.current;
                  queueText(base ? `${base} ${data.text}` : data.text);
                }
              } else if (data.state === "thinking") {
                setVoiceLabel(data.text ? `You said: "${data.text}"` : "Processing...");
              } else if (data.state === "speaking") {
                setVoiceLabel(data.text ? `Agent: "${data.text}"` : "Agent speaking...");
              }
            }
            if (data.type === "dictation-result" && data.text) {
              const base = baseQueryRef.current;
              const targetText = base ? `${base} ${data.text}` : data.text;
              queueText(targetText);
              baseQueryRef.current = targetText;
            } else if (data.type === "user-command" && data.text) {
              void submitQuery(data.text);
            }
          } catch (err) {
            console.error("Failed to parse LiveKit data message", err);
          }
        });

        room.on(RoomEvent.TrackSubscribed, (track: any) => {
          if (track.kind === "audio") {
            const element = track.attach();
            element.autoplay = true;
            element.play().catch((err: any) => {
              console.error("Autoplay blocked for track:", track.sid, err);
            });
            document.body.appendChild(element);
          }
        });

        room.on(RoomEvent.TrackUnsubscribed, (track: any) => {
          track.detach().forEach((el: any) => el.remove());
        });

        await room.connect("ws://localhost:7880", token);
      }

      await room.localParticipant.setMicrophoneEnabled(nextStt, {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      });

      const initialPrompt = buildInitialPrompt(messagesRef.current, currentContentRef.current);
      const modePayload = JSON.stringify({
        type: "set-mode",
        stt: nextStt,
        tts: nextTts,
        initial_prompt: initialPrompt,
      });
      await room.localParticipant.publishData(new TextEncoder().encode(modePayload));

      if (nextStt && nextTts) {
        setVoiceLabel("Voice & Dictation active");
      } else if (nextStt) {
        setVoiceLabel("Dictation active");
      } else {
        setVoiceLabel("TTS Commentary active");
      }
    } catch (err) {
      console.error("Voice connection failed", err);
      setSttActive(false);
      setTtsActive(false);
      setVoiceState("idle");
      setVoiceLabel("Voice server unreachable.");
    }
  }, [submitQuery, queueText]);

  const handleSttToggle = useCallback(() => {
    void syncVoiceSession(!sttActive, ttsActive);
  }, [sttActive, ttsActive, syncVoiceSession]);

  const handleTtsToggle = useCallback(() => {
    void syncVoiceSession(sttActive, !ttsActive);
  }, [sttActive, ttsActive, syncVoiceSession]);

  const handleRegenerate = useCallback(
    async (messageId: string) => {
      if (state.isStreaming || !activeConversationId) return;

      dispatch({
        type: "update_message",
        messageId,
        data: { status: "streaming", content: "", rawContent: "", blocks: [] },
      });
      pendingHistorySyncRef.current = true;

      await stream.start({
        endpoint: `/deepspace/chats/${activeConversationId}/messages/${messageId}/regenerate/stream`,
        body: {
          thinking_enabled: thinkingEnabled,
          agentic_mode: isAgenticWork,
        },
      });
    },
    [activeConversationId, state.isStreaming, stream, thinkingEnabled, isAgenticWork],
  );

  const handleSaveEdit = useCallback(
    async (messageId: string, content: string) => {
      if (state.isStreaming || !activeConversationId) return;

      dispatch({ type: "cancel_edit", messageId });
      pendingHistorySyncRef.current = true;

      const editableMessageId = await resolveLatestEditableMessageId({
        fetcher: fetchWithAuth,
        endpointBase: "/deepspace/chats",
        conversationId: activeConversationId,
        fallbackMessageId: messageId,
      });

      await stream.start({
        endpoint: `/deepspace/chats/${activeConversationId}/messages/${editableMessageId}/edit-and-regenerate/stream`,
        body: {
          content,
          thinking_enabled: thinkingEnabled,
          agentic_mode: isAgenticWork,
        },
      });
    },
    [activeConversationId, state.isStreaming, stream, thinkingEnabled, isAgenticWork],
  );

  const handleActivateVersion = useCallback(
    async (messageId: string, versionId: string) => {
      if (state.isStreaming || !activeConversationId) return;

      const response = (await fetchWithAuth(
        `/deepspace/chats/${activeConversationId}/messages/${messageId}/versions/${versionId}/activate`,
        { method: "PATCH" },
      )) as Response;

      if (response.ok) {
        const updatedMessage = (await response.json()) as {
          versions: DeepSpaceHistoryMessage["versions"];
        };
        const version = updatedMessage.versions?.find((v) => v.id === versionId);
        if (version) {
          dispatch({ type: "activate_version", messageId, version });
        }
      }
    },
    [activeConversationId, state.isStreaming],
  );

  const latestAssistantContent = (() => {
    for (let index = state.messages.length - 1; index >= 0; index -= 1) {
      const message = state.messages[index];
      if (message?.role === "assistant") {
        return message.content.trim();
      }
    }
    return "";
  })();

  const totalUsedTokens = useMemo(() => {
    const lastAssistantMessage = state.messages.findLast((message) => message.role === "assistant");
    const compactedTokens = lastAssistantMessage?.compaction?.afterTokens ?? null;
    if (typeof compactedTokens === "number" && compactedTokens > 0) {
      const noteTokens = currentContent ? estimateTokens(currentContent) : 0;
      return compactedTokens + noteTokens + estimateTokens(query);
    }
    const historySlice =
      state.messages.length > TOKEN_ESTIMATE_HISTORY_WINDOW
        ? state.messages.slice(-TOKEN_ESTIMATE_HISTORY_WINDOW)
        : state.messages;
    const historyTokens = historySlice.reduce((acc, msg) => {
      return (
        acc +
        estimateTokens(msg.content) +
        (msg.thinkingContent ? estimateTokens(msg.thinkingContent) : 0)
      );
    }, 0);
    const noteTokens = currentContent ? estimateTokens(currentContent) : 0;
    return historyTokens + noteTokens + estimateTokens(query);
  }, [state.messages, currentContent, query]);

  const totalContext = useMemo(() => {
    if (runtimeContextLimit && runtimeContextLimit > 0) {
      return runtimeContextLimit;
    }
    if (state.lastContextLimit && state.lastContextLimit > 0) {
      return state.lastContextLimit;
    }
    return null;
  }, [runtimeContextLimit, state.lastContextLimit]);

  const effectiveModelName =
    selectedModelOverride ?? state.lastModelName ?? runtimeModelName ?? null;
  const effectiveProviderType = state.lastProviderType ?? runtimeProviderType ?? null;

  const handlePromptSelect = useCallback(
    (prompt: string) => {
      setQuery(prompt);
      void submitQuery(prompt);
    },
    [submitQuery],
  );

  useEffect(() => {
    if (!onMetricsUpdate) return;
    const lastAssistantMessage = state.messages.findLast((m) => m.role === "assistant");
    onMetricsUpdate({
      usage: totalContext && totalContext > 0 ? totalUsedTokens / totalContext : 0,
      tokens: totalUsedTokens,
      tools: lastAssistantMessage?.metrics?.activeTools ?? [],
      contextLimit: totalContext,
      contextLimitSource: lastAssistantMessage?.metrics?.contextLimitSource ?? null,
      contextUsedTokens: totalUsedTokens,
      contextRemainingTokens: totalContext ? Math.max(totalContext - totalUsedTokens, 0) : null,
      modelName: effectiveModelName,
      providerType: effectiveProviderType,
      phase: lastAssistantMessage?.metrics?.phase ?? null,
      compaction: lastAssistantMessage?.compaction ?? null,
      latencyTimeline: lastAssistantMessage?.metrics?.latencyTimeline ?? [],
      agentSteps: lastAssistantMessage?.agentSteps,
    });
  }, [
    onMetricsUpdate,
    totalContext,
    totalUsedTokens,
    effectiveModelName,
    effectiveProviderType,
    state.messages,
  ]);

  useEffect(() => {
    const container = scrollContainerRef.current;
    if (!container || !autoFollowRef.current) return;

    let rafId: number;
    const smoothScrollToBottom = () => {
      if (!container || !autoFollowRef.current) return;
      const target = Math.max(0, container.scrollHeight - container.clientHeight);

      // If we're close enough or it's a huge jump (e.g. initial load), just snap
      if (
        Math.abs(container.scrollTop - target) < 2 ||
        Math.abs(container.scrollTop - target) > 1000
      ) {
        container.scrollTop = target;
        syncThreadScrollMetrics(container);
      } else {
        // Smooth interpolation
        container.scrollTop += (target - container.scrollTop) * 0.15;
        syncThreadScrollMetrics(container);
        rafId = requestAnimationFrame(smoothScrollToBottom);
      }
    };

    rafId = requestAnimationFrame(smoothScrollToBottom);

    return () => {
      cancelAnimationFrame(rafId);
    };
  }, [state.messages, state.isStreaming, syncThreadScrollMetrics]);

  const handleUserScroll = useCallback(
    (e: React.UIEvent<HTMLDivElement>) => {
      const container = e.currentTarget;
      if (!container) return;

      const isAtBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 50;

      // Stop auto-follow if user scrolls up, resume if they scroll to bottom
      if (!isAtBottom && autoFollowRef.current) {
        autoFollowRef.current = false;
      } else if (isAtBottom && !autoFollowRef.current) {
        autoFollowRef.current = true;
      }

      syncThreadScrollMetrics(container);
    },
    [syncThreadScrollMetrics],
  );

  return (
    <div className="flex h-full min-h-0 w-full overflow-hidden bg-transparent">
      <div className="relative min-w-0 flex-1 overflow-hidden bg-transparent">
        <div className="flex h-full min-h-0 min-w-0 flex-col bg-transparent">




          <DeepSpaceScrollTracker
            messages={state.messages}
            scrollContainerRef={scrollContainerRef}
            onInsertActiveAnswer={onInsertLatestAnswer}
          />

          <div
            ref={scrollContainerRef}
            onScroll={handleUserScroll}
            style={{ overflowAnchor: "none" }}
            className={`custom-scrollbar scrollbar-hide min-h-0 flex-1 overflow-y-auto pt-16 pr-12 pl-3 ${
              isMobileStacked ? "pb-24 sm:pr-12 sm:pl-4" : "sm:pr-12 sm:pl-4"
            }`}
          >
            {state.streamError ? (
              <div className="border-danger/20 bg-danger/5 text-danger mx-auto mt-6 flex max-w-5xl items-start gap-3 rounded-2xl border px-4 py-3 text-sm">
                <AlertCircle size={16} className="mt-0.5 shrink-0" />
                <div>
                  <div className="font-semibold">{state.streamError.message}</div>
                  <div className="text-muted-foreground mt-1 text-xs">{state.streamError.code}</div>
                </div>
              </div>
            ) : null}

            <DeepSpaceThread
              messages={state.messages}
              emptyPrompts={EMPTY_PROMPTS}
              scrollMetrics={threadScrollMetrics}
              onPromptSelect={handlePromptSelect}
              onClarifyAnswer={handlePromptSelect}
              onInsertLatestAnswer={() => {
                if (latestAssistantContent) {
                  onInsertLatestAnswer?.(latestAssistantContent);
                }
              }}
              onRegenerate={handleRegenerate}
              onStartEdit={(id) => dispatch({ type: "start_edit", messageId: id })}
              onCancelEdit={(id) => dispatch({ type: "cancel_edit", messageId: id })}
              onUpdateDraft={(id, content) =>
                dispatch({ type: "update_draft", messageId: id, content })
              }
              onSaveEdit={handleSaveEdit}
              onActivateVersion={handleActivateVersion}
              onResumePermission={(stepId, toolId, approved) => {
                const targetMessage = state.messages.find((m) =>
                  m.agentSteps?.some(
                    (s) =>
                      String(s.step_id || s.stepId || "") === stepId &&
                      String(s.tool_id || s.tool_id || "") === toolId,
                  ),
                );

                const targetStep = targetMessage?.agentSteps?.find(
                  (s) =>
                    String(s.step_id || s.stepId || "") === stepId &&
                    String(s.tool_id || s.tool_id || "") === toolId,
                );

                const missionId = targetStep?.data?.mission_id;
                const laneId = targetStep?.data?.lane_id;
                const durableRunId = targetStep?.data?.durable_run_id;
                const approvalId = targetStep?.data?.approval_id;

                if (targetMessage && targetStep) {
                  const optimisticSteps = (targetMessage.agentSteps ?? []).map((step) => {
                    const matchesStep =
                      String(step.step_id || step.stepId || "") === stepId &&
                      String(step.tool_id || step.toolId || "") === toolId;
                    if (!matchesStep) {
                      return step;
                    }
                    if (approved) {
                      return {
                        ...step,
                        type: "tool_start" as const,
                        status: "running" as const,
                        permissionLevel: "approved",
                      };
                    }
                    return {
                      ...step,
                      type: "tool_error" as const,
                      status: "failed" as const,
                      toolOutput: step.toolOutput || "Approval denied.",
                    };
                  });
                  dispatch({
                    type: "update_message",
                    messageId: targetMessage.id,
                    data: { agentSteps: optimisticSteps },
                  });
                }

                if (targetMessage) {
                  dispatch({ type: "resume_query", messageId: targetMessage.id });
                }

                if (missionId && laneId) {
                  fetch(`/api/v1/deepspace/orchestrations/missions/${missionId}/approval`, {
                    method: "POST",
                    body: JSON.stringify({ lane_id: laneId, approved }),
                    headers: { "Content-Type": "application/json" },
                  })
                    .then(() => {
                      if (state.currentConversationId) {
                        pendingHistorySyncRef.current = true;
                        void stream.resume({
                          conversationId: state.currentConversationId,
                          stepId,
                          toolId,
                          approved,
                          durableRunId: typeof durableRunId === "string" ? durableRunId : undefined,
                          approvalId: typeof approvalId === "string" ? approvalId : undefined,
                        });
                      }
                    })
                    .catch(console.error);
                  return;
                }

                if (state.currentConversationId) {
                  pendingHistorySyncRef.current = true;
                  void stream.resume({
                    conversationId: state.currentConversationId,
                    stepId,
                    toolId,
                    approved,
                    durableRunId: typeof durableRunId === "string" ? durableRunId : undefined,
                    approvalId: typeof approvalId === "string" ? approvalId : undefined,
                  });
                }
              }}
              runtimeIndicators={runtimeIndicatorState}
            />
          </div>

          <div className="flex w-full shrink-0 flex-col items-center">
            <DeepSpaceComposer
              query={query}
              isStreaming={state.isStreaming}
              variant={isAgenticWork ? "deepspace" : "default"}
              modelName={effectiveModelName}
              onQueryChange={setQuery}
              onSubmit={() => void submitQuery()}
              onStop={stopStreaming}
              usedTokens={totalUsedTokens}
              totalContext={totalContext}
              isAgentic={isAgenticWork}
              onAgenticChange={setIsAgenticWork}
              availableModels={availableModels}
              onModelSelect={handleModelSelect}
              executionMode={executionMode}
              onExecutionModeChange={updateExecutionMode}
              runtimePreferences={runtimePreferences}
              isSavingRuntimePreferences={isSavingRuntimePreferences}
              activeConversationId={activeConversationId}
              onRuntimePreferencesChange={updateRuntimePreferences}
              fullAutonomyEnabled={fullAutonomyEnabled}
              onFullAutonomyChange={(enabled) => {
                setFullAutonomyEnabled(enabled);
                void updateRuntimePreferences({ full_autonomy_enabled: enabled });
              }}
              voiceState={voiceState}
              sttActive={sttActive}
              ttsActive={ttsActive}
              onSttToggle={handleSttToggle}
              onTtsToggle={handleTtsToggle}
              voiceLabel={voiceLabel}
            />
          </div>
        </div>
      </div>

      <AnimatePresence>
        {historyOpen && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setHistoryOpen(false)}
              className="fixed inset-0 z-[100] bg-black/35 backdrop-blur-[1.5px]"
            />
            <motion.div
              initial={{ x: 420, opacity: 0 }}
              animate={{ x: 0, opacity: 1 }}
              exit={{ x: 420, opacity: 0 }}
              transition={{ type: "spring", damping: 25, stiffness: 200 }}
              className="fixed top-4 right-4 bottom-4 z-[110] flex w-[280px] sm:w-[320px] overflow-hidden rounded-[2rem] border border-white/10 bg-black/72 shadow-2xl backdrop-blur-2xl"
            >
              <ChatSidebar
                endpointBase="/deepspace/chats"
                variant="floating"
                currentConversationId={state.currentConversationId}
                onConversationRenamed={onConversationRenamed}
                onSelectConversation={(id) => {
                  onSelectNote?.(id);
                  setHistoryOpen(false);
                }}
                onNewChat={() => {
                  startNewChat();
                  setHistoryOpen(false);
                }}
                onClose={() => setHistoryOpen(false)}
              >
                <AgentCapabilities runtimeIndicators={runtimeIndicatorState} />
              </ChatSidebar>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}
