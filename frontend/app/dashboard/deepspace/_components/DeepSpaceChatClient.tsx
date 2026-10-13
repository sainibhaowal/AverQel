"use client";

/* LiveKit's browser event surface is intentionally dynamic; its event payloads
 * are validated by the runtime before entering the DeepSpace reducer. */
/* eslint-disable @typescript-eslint/no-explicit-any */

import { AnimatePresence, motion } from "framer-motion";
import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useReducer,
  useRef,
  useState,
} from "react";
import toast from "react-hot-toast";
import { useAuth } from "@/app/context/AuthContext";
import { hasAdminRole } from "@/lib/roles";

import ChatSidebar from "@/app/components/dashboard/ChatSidebar";
import { fetchWithAuth } from "@/lib/api";
import { useRealtimeEvents } from "@/lib/realtime";
import { saveMCPActiveContext } from "@/lib/mcp-context";
import {
  listProviders,
  listProviderModels,
  refreshProviderModels,
  listAssignments,
  createAssignment,
  updateAssignment,
} from "@/lib/providers-api";
import type { ProviderConfig } from "@/lib/providers-api";

import { useDeepSpaceStream } from "../_hooks/useDeepSpaceStream";
import {
  findPendingUserQuestion,
  initialDeepSpaceThreadState,
  deepSpaceThreadReducer,
} from "../_lib/deepspace-thread";
import {
  isValidReasoningEffort,
  normalizeReasoningEffortForModel,
  shouldRefreshModelMetadata,
} from "../_lib/reasoning-options";
import type { ReasoningEffort } from "../_lib/reasoning-options";
import type {
  DeepSpaceHistoryMessage,
  DeepSpaceHistoryVersion,
  DeepSpaceStreamEvent,
} from "../_lib/deepspace-stream";

import DeepSpaceComposer, { type DeepSpaceRuntimePhase } from "./DeepSpaceComposer";
import type { DeepSpaceAgentNotePreview } from "./DeepSpaceEditor";
import DeepSpaceThread from "./DeepSpaceThread";
import DeepSpaceScrollTracker from "./DeepSpaceScrollTracker";
import DeepSpaceOperationalSummary, {
  type OperationalSummary,
} from "./DeepSpaceOperationalSummary";

function customProviderReasoningOptions(provider: ProviderConfig | undefined) {
  if (provider?.provider_type !== "custom") {
    return {
      supportedReasoningEfforts: [] as string[],
      reasoningCapabilitiesKnown: false,
      reasoningToggleOnly: false,
      reasoningAlwaysOn: false,
    };
  }

  const metadata = provider.metadata_json;
  const compatible = metadata.openai_compatible;
  const endpointSettings =
    compatible && typeof compatible === "object" && !Array.isArray(compatible)
      ? (compatible as Record<string, unknown>)
      : {};
  const reasoning =
    endpointSettings.reasoning &&
    typeof endpointSettings.reasoning === "object" &&
    !Array.isArray(endpointSettings.reasoning)
      ? (endpointSettings.reasoning as Record<string, unknown>)
      : {};
  const rootEfforts = metadata.supported_reasoning_efforts;
  const nestedEfforts = reasoning.supported_efforts;
  const configuredEfforts =
    Array.isArray(rootEfforts) && rootEfforts.length > 0 ? rootEfforts : nestedEfforts;
  const supportedReasoningEfforts = Array.isArray(configuredEfforts)
    ? configuredEfforts.filter(isValidReasoningEffort)
    : [];

  return {
    supportedReasoningEfforts,
    // Custom endpoint capability is explicit. An empty list means the
    // endpoint has no advertised reasoning controls; it must not fall back to
    // generic-provider guesses in the composer.
    reasoningCapabilitiesKnown: true,
    reasoningToggleOnly:
      Boolean(reasoning.toggle_parameter) && supportedReasoningEfforts.length === 0,
    reasoningAlwaysOn:
      supportedReasoningEfforts.length > 0 &&
      !Boolean(reasoning.toggle_parameter) &&
      reasoning.effort_off_value === undefined,
  };
}

function readPartialJsonStringValue(input: string, key: string): string | null {
  const keyStart = input.indexOf(`"${key}"`);
  if (keyStart < 0) return null;
  const colon = input.indexOf(":", keyStart + key.length + 2);
  if (colon < 0) return null;
  const openingQuote = input.indexOf('"', colon + 1);
  if (openingQuote < 0) return null;

  let value = "";
  for (let index = openingQuote + 1; index < input.length; index += 1) {
    const character = input[index]!;
    if (character === '"') return value;
    if (character !== "\\") {
      value += character;
      continue;
    }
    const escaped = input[index + 1];
    if (!escaped) break;
    if (escaped === "u") {
      const code = input.slice(index + 2, index + 6);
      if (code.length < 4 || !/^[0-9a-f]{4}$/i.test(code)) break;
      value += String.fromCharCode(Number.parseInt(code, 16));
      index += 5;
      continue;
    }
    const escapes: Record<string, string> = {
      '"': '"',
      "\\": "\\",
      "/": "/",
      b: "\b",
      f: "\f",
      n: "\n",
      r: "\r",
      t: "\t",
    };
    if (!(escaped in escapes)) break;
    value += escapes[escaped]!;
    index += 1;
  }
  return value;
}

function readWritePreview(input: string): { markdown: string; mode: "replace" | "append" } | null {
  const markdown = readPartialJsonStringValue(input, "markdown");
  if (markdown === null) return null;
  return {
    markdown,
    mode: readPartialJsonStringValue(input, "mode") === "append" ? "append" : "replace",
  };
}
const buildInitialPrompt = (messages: any[], currentContent?: string): string => {
  const wordsSet = new Set<string>([
    "AverQel",
    "DeepSpace",
    "LiveKit",
    "Docker",
    "Next.js",
    "TypeScript",
    "Minio",
    "Postgres",
    "Redis",
    "compose",
    "git",
    "status",
    "workspace",
    "orchestrator",
    "agent",
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
  onAgentNotePreview?: (preview: DeepSpaceAgentNotePreview & { conversationId: string }) => void;
  onAgentNoteCommitted?: (update: { conversationId: string; contentHtml: string }) => void;
  onSelectNote?: (noteId: string) => void;
  onNewNote?: () => Promise<unknown> | void;
  onConversationRenamed?: (note: {
    id: string;
    title: string;
    updated_at: string;
    content_html?: string | null;
  }) => void;
  activeConversationId: string | null;
  currentContent?: string;
  isMobileStacked?: boolean;
  panelMode?: "split" | "notes" | "chat" | "memory";
  onSetPanelMode?: (mode: "split" | "notes" | "chat" | "memory") => void;
  isHistoryOpen?: boolean;
  onSetHistoryOpen?: (open: boolean) => void;
}

type QueuedTurn = {
  clientRequestId: string;
  regenerateMessageId?: string | null;
  prompt: string;
  priority: number;
  sequence: number;
  status: "queued" | "running" | "cancelling" | "awaiting_user" | "awaiting_approval" | "failed";
  error?: string | null;
};

type EditingQueuedTurn = {
  clientRequestId: string;
  originalPrompt: string;
};

type QueueState = {
  paused: boolean;
  reason: string | null;
  failedRequestId: string | null;
  activeRequestId: string | null;
  pausedAt: string | null;
};

type ProviderOperationalSummary = OperationalSummary["providers"][number];

function isNonNegativeInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
}

function isFailureRate(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 1;
}

function isLatency(value: unknown): value is number | null {
  return value === null || (typeof value === "number" && Number.isFinite(value) && value >= 0);
}

function isProviderOperationalSummary(value: unknown): value is ProviderOperationalSummary {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const metric = value as Record<string, unknown>;
  return (
    typeof metric.provider === "string" &&
    metric.provider.length > 0 &&
    isNonNegativeInteger(metric.sample_size) &&
    isFailureRate(metric.failure_rate) &&
    isLatency(metric.p50_latency_ms) &&
    isLatency(metric.p95_latency_ms)
  );
}

function parseOperationalSummary(value: unknown): OperationalSummary | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const summary = value as Record<string, unknown>;
  if (
    !isNonNegativeInteger(summary.sample_size) ||
    !isFailureRate(summary.failure_rate) ||
    !isLatency(summary.p50_latency_ms) ||
    !isLatency(summary.p95_latency_ms) ||
    !Array.isArray(summary.providers)
  ) {
    return null;
  }
  const providers = summary.providers;
  if (!providers.every(isProviderOperationalSummary)) return null;
  return {
    sample_size: summary.sample_size,
    failure_rate: summary.failure_rate,
    p50_latency_ms: summary.p50_latency_ms,
    p95_latency_ms: summary.p95_latency_ms,
    providers,
  };
}

const EMPTY_PROMPTS = [
  "Help me think through this idea clearly.",
  "Draft a concise message I can send to my team.",
  "Turn these rough thoughts into a cleaner note.",
  "Explain this topic simply, then improve the wording.",
];
export default function DeepSpaceChatClient({
  onInsertLatestAnswer,
  onAgentNotePreview,
  onAgentNoteCommitted,
  onSelectNote,
  onNewNote,
  onConversationRenamed,
  activeConversationId,
  currentContent,
  isMobileStacked,
  isHistoryOpen,
  onSetHistoryOpen,
}: DeepSpaceChatClientProps) {
  const { user } = useAuth();
  const [state, dispatch] = useReducer(deepSpaceThreadReducer, initialDeepSpaceThreadState);
  const [query, setQuery] = useState("");
  const [queuedTurns, setQueuedTurns] = useState<QueuedTurn[]>([]);
  const [editingQueuedTurn, setEditingQueuedTurn] = useState<EditingQueuedTurn | null>(null);
  const [activeRequestId, setActiveRequestId] = useState<string | null>(null);
  const [queueAction, setQueueAction] = useState<string | null>(null);
  const [queueState, setQueueState] = useState<QueueState>({
    paused: false,
    reason: null,
    failedRequestId: null,
    activeRequestId: null,
    pausedAt: null,
  });
  const [operationalSummary, setOperationalSummary] = useState<OperationalSummary | null>(null);
  const [creatingNewChat, setCreatingNewChat] = useState(false);
  const [historyLoadErrorId, setHistoryLoadErrorId] = useState<string | null>(null);
  const [completionPulse, setCompletionPulse] = useState(false);
  const completionPulseTimeoutRef = useRef<number | null>(null);
  const [localHistoryOpen, setLocalHistoryOpen] = useState(false);
  const historyOpen = isHistoryOpen !== undefined ? isHistoryOpen : localHistoryOpen;
  const setHistoryOpen = onSetHistoryOpen !== undefined ? onSetHistoryOpen : setLocalHistoryOpen;
  const [reasoningEffort, setReasoningEffort] = useState<ReasoningEffort | null>("medium");
  const [threadScrollMetrics, setThreadScrollMetrics] = useState<{
    scrollTop: number;
    viewportHeight: number;
  } | null>(null);

  useEffect(() => {
    let active = true;
    const loadSummary = async () => {
      try {
        const response = await fetchWithAuth("/deepspace/chats/operational-summary");
        if (!response.ok) return;
        const summary = parseOperationalSummary(await response.json());
        if (active) setOperationalSummary(summary);
      } catch {
        // Operational visibility is optional; chat must remain usable if it is unavailable.
      }
    };
    void loadSummary();
    return () => {
      active = false;
    };
  }, []);

  useRealtimeEvents(() => {
    void fetchWithAuth("/deepspace/chats/operational-summary")
      .then(async (response) => {
        if (!response.ok) return;
        const summary = parseOperationalSummary(await response.json());
        if (summary) setOperationalSummary(summary);
      })
      .catch(() => {
        // The last known operational snapshot remains visible during a
        // transient gateway or API reconnect.
      });
  }, ["deepspace", "queues"]);

  const [availableModels, setAvailableModels] = useState<
    Array<{
      providerId: string;
      providerName: string;
      providerType: string;
      supportsModelListing?: boolean;
      modelName: string;
      displayName: string;
      quantization?: string | null;
      contextWindow?: number | null;
      contextWindowSource?: string | null;
      lastSeenAt?: string | null;
      supportedReasoningEfforts?: string[];
      reasoningCapabilitiesKnown?: boolean;
      reasoningToggleOnly?: boolean;
      reasoningAlwaysOn?: boolean;
    }>
  >([]);
  const [selectedProviderOverride, setSelectedProviderOverride] = useState<string | null>(null);
  const [selectedModelOverride, setSelectedModelOverride] = useState<string | null>(null);
  const effectiveModelName = selectedModelOverride ?? state.lastModelName ?? null;
  const selectedModel =
    availableModels.find(
      (model) =>
        model.modelName === effectiveModelName &&
        (!selectedProviderOverride || model.providerId === selectedProviderOverride),
    ) ?? availableModels.find((model) => model.modelName === effectiveModelName);
  const activeReasoningEffort = normalizeReasoningEffortForModel(reasoningEffort, selectedModel);
  const thinkingEnabled = activeReasoningEffort !== null;
  const modelSwitchRef = useRef<Promise<void> | null>(null);
  const modelSelectionVersionRef = useRef(0);
  const submissionInFlightRef = useRef(false);

  const modelFromProvider = useCallback(
    (
      providerId: string,
      model: {
        model_name: string;
        display_name?: string | null;
        context_window?: number | null;
        last_seen_at?: string | null;
        capabilities_json?: Record<string, unknown>;
      },
      providerName = providerId,
      providerType = "unknown",
      supportsModelListing = false,
    ) => {
      const capabilities = model.capabilities_json ?? {};
      const efforts = Array.isArray(capabilities.supported_reasoning_efforts)
        ? capabilities.supported_reasoning_efforts.filter(isValidReasoningEffort)
        : [];
      return {
        providerId,
        providerName,
        providerType,
        supportsModelListing,
        modelName: model.model_name,
        displayName: model.display_name || model.model_name,
        quantization:
          typeof capabilities.quantization === "string" ? capabilities.quantization : null,
        contextWindow: model.context_window,
        lastSeenAt: model.last_seen_at ?? null,
        contextWindowSource:
          typeof capabilities.context_window_source === "string"
            ? capabilities.context_window_source
            : null,
        supportedReasoningEfforts: efforts,
        reasoningCapabilitiesKnown:
          typeof capabilities.reasoning_capabilities_known === "boolean"
            ? capabilities.reasoning_capabilities_known
            : capabilities.supports_reasoning === true ||
              efforts.length > 0 ||
              capabilities.supports_thinking_toggle === true,
        reasoningToggleOnly: capabilities.supports_thinking_toggle === true && efforts.length === 0,
        reasoningAlwaysOn:
          capabilities.supports_reasoning === true &&
          capabilities.supports_thinking_toggle !== true &&
          (!Array.isArray(capabilities.request_controls_off) ||
            capabilities.request_controls_off.length === 0),
      };
    },
    [],
  );

  const [sttActive, setSttActive] = useState(false);
  const [ttsActive, setTtsActive] = useState(false);
  const [voiceState, setVoiceState] = useState<"idle" | "listening" | "thinking" | "speaking">(
    "idle",
  );
  const [voiceLabel, setVoiceLabel] = useState<string>("");
  const roomRef = useRef<any>(null);
  const queryRef = useRef(query);
  const baseQueryRef = useRef("");
  const typingQueueRef = useRef<string[]>([]);
  const typingIntervalRef = useRef<any>(null);
  const lastTtsMessageRef = useRef<string | null>(null);
  const messagesRef = useRef(state.messages);
  const currentContentRef = useRef(currentContent);
  const activeConversationIdRef = useRef(activeConversationId);
  const notePreviewCallbackRef = useRef(onAgentNotePreview);
  const noteCommitCallbackRef = useRef(onAgentNoteCommitted);
  const noteArgumentBuffersRef = useRef(new Map<string, string>());
  const streamConversationIdRef = useRef<string | null>(null);
  const streamDetachRef = useRef<() => void>(() => {});
  const versionActivationQueuesRef = useRef(new Map<string, Promise<DeepSpaceHistoryVersion>>());
  const versionActivationSequenceRef = useRef(new Map<string, number>());
  const resumedRunRef = useRef<{ conversationId: string; requestId: string } | null>(null);
  const queueReconnectRef = useRef<{ conversationId: string; requestId: string } | null>(null);
  const activeRequestIdRef = useRef<string | null>(null);
  const historyRequestVersionRef = useRef(0);
  const queueRequestVersionRef = useRef(0);
  const queueEditDraftRef = useRef<string | null>(null);
  const editingQueuedTurnRef = useRef<EditingQueuedTurn | null>(null);
  const queueEditSaveInProgressRef = useRef(false);
  const loadConversationRef = useRef<(conversationId: string) => void>(() => {});
  const selectedConversationIdRef = useRef(activeConversationId ?? state.currentConversationId);
  const currentConversationIdRef = useRef(state.currentConversationId);

  useLayoutEffect(() => {
    selectedConversationIdRef.current = activeConversationId ?? state.currentConversationId;
    currentConversationIdRef.current = state.currentConversationId;
    activeConversationIdRef.current = activeConversationId ?? state.currentConversationId;
  }, [activeConversationId, state.currentConversationId]);
  const getReadyConversationId = useCallback(() => {
    const selectedConversationId = selectedConversationIdRef.current;
    return selectedConversationId && currentConversationIdRef.current === selectedConversationId
      ? selectedConversationId
      : null;
  }, []);

  const loadQueuedTurns = useCallback(async (conversationId: string) => {
    const requestVersion = ++queueRequestVersionRef.current;
    try {
      const response = (await fetchWithAuth(
        `/deepspace/chats/${conversationId}/queue`,
      )) as Response;
      if (!response.ok) return;
      const payload = (await response.json()) as Array<{
        client_request_id: string;
        regenerate_message_id?: string | null;
        prompt: string;
        priority: number;
        sequence: number;
        status:
          | "queued"
          | "running"
          | "cancelling"
          | "awaiting_user"
          | "awaiting_approval"
          | "failed";
        error?: string | null;
      }>;
      if (
        requestVersion !== queueRequestVersionRef.current ||
        activeConversationIdRef.current !== conversationId
      ) {
        return;
      }
      const nextTurns = payload
        .filter(
          (turn) =>
            turn.status === "queued" ||
            turn.status === "awaiting_user" ||
            turn.status === "awaiting_approval" ||
            turn.status === "failed",
        )
        .map((turn) => ({
          clientRequestId: turn.client_request_id,
          regenerateMessageId: turn.regenerate_message_id ?? null,
          prompt: turn.prompt,
          priority: turn.priority,
          sequence: turn.sequence,
          status: turn.status,
          error: turn.error ?? null,
        }))
        .sort(
          (left, right) =>
            Number(left.status === "failed") - Number(right.status === "failed") ||
            right.priority - left.priority ||
            left.sequence - right.sequence,
        );
      const edit = editingQueuedTurnRef.current;
      if (
        edit &&
        !queueEditSaveInProgressRef.current &&
        !nextTurns.some(
          (turn) => turn.clientRequestId === edit.clientRequestId && turn.status === "queued",
        )
      ) {
        editingQueuedTurnRef.current = null;
        setEditingQueuedTurn(null);
        queueEditDraftRef.current = null;
        toast.error(
          "This prompt started or left the queue. Your edited text is still in the composer.",
        );
      }
      setQueuedTurns(nextTurns);
    } catch {
      // The active response remains usable if a background queue refresh fails.
    }
  }, []);

  const loadQueueState = useCallback(async (conversationId: string) => {
    try {
      const response = (await fetchWithAuth(
        `/deepspace/chats/${conversationId}/queue/state`,
      )) as Response;
      if (!response.ok || activeConversationIdRef.current !== conversationId) return null;
      const payload = (await response.json()) as {
        paused?: boolean;
        reason?: string | null;
        failed_request_id?: string | null;
        active_request_id?: string | null;
        paused_at?: string | null;
      };
      const nextState = {
        paused: Boolean(payload.paused),
        reason: payload.reason ?? null,
        failedRequestId: payload.failed_request_id ?? null,
        activeRequestId: payload.active_request_id ?? null,
        pausedAt: payload.paused_at ?? null,
      };
      setQueueState(nextState);
      return nextState;
    } catch {
      // Queue state is supplementary; the active chat remains usable if it is unavailable.
      return null;
    }
  }, []);

  useRealtimeEvents(
    (event) => {
      const conversationId = event.data?.conversation_id;
      const currentConversationId = activeConversationId ?? state.currentConversationId;
      if (currentConversationId && conversationId === currentConversationId) {
        void loadQueuedTurns(currentConversationId);
        void loadQueueState(currentConversationId);
      }
    },
    ["queues"],
  );

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
    noteArgumentBuffersRef.current.clear();
    resumedRunRef.current = null;
    queueReconnectRef.current = null;
  }, [activeConversationId]);

  useEffect(() => {
    notePreviewCallbackRef.current = onAgentNotePreview;
    noteCommitCallbackRef.current = onAgentNoteCommitted;
  }, [onAgentNoteCommitted, onAgentNotePreview]);

  useEffect(() => {
    return () => {
      if (typingIntervalRef.current) {
        clearInterval(typingIntervalRef.current);
      }
      if (completionPulseTimeoutRef.current !== null) {
        window.clearTimeout(completionPulseTimeoutRef.current);
        completionPulseTimeoutRef.current = null;
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

  const queueText = useCallback(
    (targetText: string) => {
      const currentText = queryRef.current;

      if (targetText.startsWith(currentText)) {
        const suffix = targetText.slice(currentText.length);
        typingQueueRef.current = suffix.split("");
      } else {
        let i = 0;
        while (
          i < currentText.length &&
          i < targetText.length &&
          currentText[i] === targetText[i]
        ) {
          i++;
        }
        const commonPrefix = currentText.slice(0, i);
        const suffix = targetText.slice(commonPrefix.length);

        setQuery(commonPrefix);
        typingQueueRef.current = suffix.split("");
      }

      startTypingLoop();
    },
    [startTypingLoop],
  );

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
      try {
        const [providersList, assignmentsList] = await Promise.all([
          listProviders(),
          listAssignments().catch(() => []),
        ]);
        if (!active) return;

        const chatAssignment = assignmentsList.find(
          (assignment) => assignment.feature_scope === "chat" && assignment.enabled,
        );
        const chatProviders = providersList.filter((p) => p.enabled && p.supports_chat);
        const allChatModels: Array<{
          providerId: string;
          providerName: string;
          providerType: string;
          supportsModelListing?: boolean;
          modelName: string;
          displayName: string;
          contextWindow?: number | null;
          contextWindowSource?: string | null;
          lastSeenAt?: string | null;
          supportedReasoningEfforts?: string[];
          reasoningCapabilitiesKnown?: boolean;
          reasoningToggleOnly?: boolean;
          reasoningAlwaysOn?: boolean;
        }> = [];

        await Promise.all(
          chatProviders.map(async (provider) => {
            try {
              const models = await listProviderModels(provider.id);
              const chatOnly = models.filter(
                (m) => m.model_kind === "chat" && m.is_available !== false,
              );
              if (active) {
                allChatModels.push(
                  ...chatOnly.map((m) =>
                    modelFromProvider(
                      provider.id,
                      m,
                      provider.display_name,
                      provider.provider_type,
                      provider.supports_model_listing,
                    ),
                  ),
                );
              }
            } catch (err) {
              console.error(`Failed to list models for provider ${provider.id}`, err);
            }
          }),
        );

        if (active) {
          const fallbackModels = chatProviders.flatMap((provider) => {
            const modelName = provider.default_chat_model?.trim();
            return modelName
              ? [
                  {
                    providerId: provider.id,
                    providerName: provider.display_name,
                    providerType: provider.provider_type,
                    supportsModelListing: provider.supports_model_listing,
                    modelName,
                    displayName: modelName,
                    contextWindow: null,
                    contextWindowSource: "provider_default",
                    lastSeenAt: null,
                    ...customProviderReasoningOptions(provider),
                  },
                ]
              : [];
          });
          if (chatAssignment?.model_name && chatAssignment.provider_config_id) {
            const assignedProvider = chatProviders.find(
              (provider) => provider.id === chatAssignment.provider_config_id,
            );
            fallbackModels.push({
              providerId: chatAssignment.provider_config_id,
              providerName: assignedProvider?.display_name ?? chatAssignment.provider_config_id,
              providerType: assignedProvider?.provider_type ?? "unknown",
              supportsModelListing: assignedProvider?.supports_model_listing ?? false,
              modelName: chatAssignment.model_name,
              displayName: chatAssignment.model_name,
              contextWindow: null,
              contextWindowSource: "assignment",
              lastSeenAt: null,
              ...customProviderReasoningOptions(assignedProvider),
            });
          }
          // Keep authoritative model discovery metadata (especially the
          // context window) when a provider default describes the same model.
          // The previous spread order let a null-metadata fallback overwrite
          // the discovered row and forced the composer to guess its limit.
          const merged = new Map<string, (typeof allChatModels)[number]>(
            fallbackModels.map((model) => [`${model.providerId}:${model.modelName}`, model]),
          );
          for (const model of allChatModels) {
            merged.set(`${model.providerId}:${model.modelName}`, model);
          }
          setAvailableModels([...merged.values()]);

          // A provider-level default is a real chat selection even when the
          // operator has not created a separate feature assignment. Previously
          // it appeared in the picker but was never selected, leaving a new
          // conversation without a model name or context-window denominator
          // until the user selected that same model again. Do not overwrite a
          // manual selection that happened while this async load was in flight.
          const preferredModel =
            chatAssignment?.model_name && chatAssignment.provider_config_id
              ? {
                  providerId: chatAssignment.provider_config_id,
                  modelName: chatAssignment.model_name,
                }
              : fallbackModels[0]
                ? {
                    providerId: fallbackModels[0].providerId,
                    modelName: fallbackModels[0].modelName,
                  }
                : null;
          if (preferredModel && modelSelectionVersionRef.current === 0) {
            setSelectedModelOverride((current) => current ?? preferredModel.modelName);
            setSelectedProviderOverride((current) => current ?? preferredModel.providerId);
          }

          // Render cached models immediately, then refresh incomplete metadata
          // for the active model in the background. This keeps slow provider
          // catalogs from delaying the composer or the rest of the model list.
          const preferredProvider = preferredModel
            ? chatProviders.find((provider) => provider.id === preferredModel.providerId)
            : undefined;
          const cachedPreferredModel = preferredModel
            ? allChatModels.find(
                (model) =>
                  model.providerId === preferredModel.providerId &&
                  model.modelName === preferredModel.modelName,
              )
            : undefined;
          if (
            preferredProvider?.supports_model_listing &&
            shouldRefreshModelMetadata(cachedPreferredModel)
          ) {
            void refreshProviderModels(preferredProvider.id)
              .then((refreshedModels) => {
                if (!active) return;
                const refreshedChatModels = refreshedModels
                  .filter((model) => model.model_kind === "chat" && model.is_available !== false)
                  .map((model) =>
                    modelFromProvider(
                      preferredProvider.id,
                      model,
                      preferredProvider.display_name,
                      preferredProvider.provider_type,
                      preferredProvider.supports_model_listing,
                    ),
                  );
                if (!refreshedChatModels.length) return;
                setAvailableModels((current) => {
                  const merged = new Map(
                    current.map((model) => [`${model.providerId}:${model.modelName}`, model]),
                  );
                  for (const model of refreshedChatModels) {
                    merged.set(`${model.providerId}:${model.modelName}`, model);
                  }
                  return [...merged.values()];
                });
              })
              .catch((refreshError) => {
                console.warn("Failed to refresh active model metadata", refreshError);
              });
          }
        }
      } catch (err) {
        console.error("Failed to load models", err);
      }
    };

    void fetchModelsAndAssignments();
    return () => {
      active = false;
    };
  }, [modelFromProvider]);

  const handleModelSelect = useCallback(
    (providerId: string, modelName: string) => {
      const previousModel = selectedModelOverride;
      const previousProvider = selectedProviderOverride;
      const selectionVersion = ++modelSelectionVersionRef.current;

      // Update the visible model and its context window before the network round trip.
      setSelectedModelOverride(modelName);
      setSelectedProviderOverride(providerId);

      const waitForPrevious = modelSwitchRef.current ?? Promise.resolve();
      const operation = waitForPrevious
        .catch(() => undefined)
        .then(async () => {
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

            // Refresh the selected provider after the assignment is saved. This
            // picks up newly-added models and authoritative per-model metadata
            // (especially context windows) without resetting the conversation.
            const selectedModelMetadata = availableModels.find(
              (model) => model.providerId === providerId && model.modelName === modelName,
            );
            if (
              selectedModelMetadata?.supportsModelListing &&
              shouldRefreshModelMetadata(selectedModelMetadata)
            ) {
              try {
                const refreshedModels = await refreshProviderModels(providerId);
                const selectedProvider = availableModels.find(
                  (model) => model.providerId === providerId,
                );
                const refreshedChatModels = refreshedModels
                  .filter((model) => model.model_kind === "chat" && model.is_available !== false)
                  .map((model) =>
                    modelFromProvider(
                      providerId,
                      model,
                      selectedProvider?.providerName ?? providerId,
                      selectedProvider?.providerType ?? "unknown",
                      selectedProvider?.supportsModelListing ?? false,
                    ),
                  );
                if (
                  refreshedChatModels.length > 0 &&
                  selectionVersion === modelSelectionVersionRef.current
                ) {
                  setAvailableModels((current) => {
                    const merged = new Map(
                      current.map((model) => [`${model.providerId}:${model.modelName}`, model]),
                    );
                    for (const model of refreshedChatModels) {
                      merged.set(`${model.providerId}:${model.modelName}`, model);
                    }
                    return [...merged.values()];
                  });
                }
              } catch (refreshError) {
                // Assignment success must not be rolled back merely because a
                // metadata refresh is unavailable. The backend still supplies
                // verified fallbacks for known model families.
                console.warn("Failed to refresh selected model metadata", refreshError);
              }
            }

            toast.success(`Switched model to ${modelName}`, { id: toastId });
          } catch (err) {
            console.error("Failed to switch model", err);
            if (selectionVersion === modelSelectionVersionRef.current) {
              setSelectedModelOverride(previousModel);
              setSelectedProviderOverride(previousProvider);
            }
            toast.error("Failed to switch model", { id: toastId });
          }
        });

      modelSwitchRef.current = operation;
      void operation.finally(() => {
        if (modelSwitchRef.current === operation) modelSwitchRef.current = null;
      });
      return operation;
    },
    [availableModels, modelFromProvider, selectedModelOverride, selectedProviderOverride],
  );

  const scrollContainerRef = useRef<HTMLDivElement | null>(null);
  const autoFollowRef = useRef(true);
  const pendingHistorySyncRef = useRef(false);
  const scrollMetricsRafRef = useRef<number | null>(null);
  const pendingScrollMetricsRef = useRef<{ scrollTop: number; viewportHeight: number } | null>(
    null,
  );
  const lastScrollMetricsRef = useRef<{ scrollTop: number; viewportHeight: number } | null>(null);
  const autoScrollRafRef = useRef<number | null>(null);

  const syncThreadScrollMetrics = useCallback((element: HTMLDivElement) => {
    pendingScrollMetricsRef.current = {
      scrollTop: element.scrollTop,
      viewportHeight: element.clientHeight,
    };
    if (scrollMetricsRafRef.current !== null) return;
    scrollMetricsRafRef.current = window.requestAnimationFrame(() => {
      const next = pendingScrollMetricsRef.current;
      const previous = lastScrollMetricsRef.current;
      if (
        next &&
        (!previous ||
          Math.abs(next.scrollTop - previous.scrollTop) > 1 ||
          next.viewportHeight !== previous.viewportHeight)
      ) {
        lastScrollMetricsRef.current = next;
        setThreadScrollMetrics(next);
      }
      scrollMetricsRafRef.current = null;
    });
  }, []);

  const scrollToBottomIfFollowing = useCallback(() => {
    const container = scrollContainerRef.current;
    if (!container || !autoFollowRef.current) return;

    const target = Math.max(0, container.scrollHeight - container.clientHeight);
    if (Math.abs(container.scrollTop - target) > 1) {
      container.scrollTop = target;
    }
    syncThreadScrollMetrics(container);
  }, [syncThreadScrollMetrics]);

  const scheduleScrollToBottom = useCallback(() => {
    if (autoScrollRafRef.current !== null) return;
    autoScrollRafRef.current = window.requestAnimationFrame(() => {
      autoScrollRafRef.current = null;
      scrollToBottomIfFollowing();
    });
  }, [scrollToBottomIfFollowing]);

  const publishNotePreview = useCallback(
    (callKey: string, status: DeepSpaceAgentNotePreview["status"] = "streaming") => {
      const conversationId = activeConversationIdRef.current;
      const rawArguments = noteArgumentBuffersRef.current.get(callKey);
      if (!conversationId || !rawArguments) return;
      const preview = readWritePreview(rawArguments);
      if (!preview?.markdown) return;
      notePreviewCallbackRef.current?.({ ...preview, status, conversationId });
    },
    [],
  );

  const markLiveNoteDraftsFailed = useCallback(() => {
    for (const callKey of noteArgumentBuffersRef.current.keys()) {
      publishNotePreview(callKey, "failed");
    }
  }, [publishNotePreview]);

  const consumeNoteEvents = useCallback(
    (events: Array<{ event: string; data: Record<string, unknown> }>) => {
      for (const event of events) {
        if (event.event === "memory_candidate") {
          window.dispatchEvent(new CustomEvent("deepspace:memory-updated", { detail: event.data }));
        }
        const toolName = String(event.data.tool_name ?? "");
        const callKey = String(event.data.step_id ?? event.data.tool_id ?? "");
        if (event.event === "tool_delta" && toolName === "write" && callKey) {
          const fragment = String(event.data.text ?? "");
          if (!fragment) continue;
          noteArgumentBuffersRef.current.set(
            callKey,
            `${noteArgumentBuffersRef.current.get(callKey) ?? ""}${fragment}`,
          );
          publishNotePreview(callKey);
          continue;
        }
        if (event.event === "tool_error" && toolName === "write" && callKey) {
          publishNotePreview(callKey, "failed");
          continue;
        }
        if (event.event === "tool_result" && toolName === "write" && callKey) {
          try {
            const payload = JSON.parse(String(event.data.output ?? "{}")) as Record<
              string,
              unknown
            >;
            if (payload.destination === "library" || payload.workspace_file_id || payload.file_id) {
              window.dispatchEvent(
                new CustomEvent("deepspace-library-changed", { detail: payload }),
              );
            }
            const contentHtml = payload.content_html;
            const conversationId = activeConversationIdRef.current;
            if (conversationId && typeof contentHtml === "string") {
              noteCommitCallbackRef.current?.({ conversationId, contentHtml });
            }
          } catch {
            // The normal tool timeline still displays any malformed result safely.
          } finally {
            noteArgumentBuffersRef.current.delete(callKey);
          }
          continue;
        }
        if (event.event === "tool_result" && toolName === "artifact_create") {
          window.dispatchEvent(
            new CustomEvent("deepspace-library-changed", { detail: event.data }),
          );
          continue;
        }
        if (event.event === "error") markLiveNoteDraftsFailed();
      }
    },
    [markLiveNoteDraftsFailed, publishNotePreview],
  );

  const refreshQueueForStartedConversation = useCallback(
    (conversationId: string) => {
      const selectedConversationId = activeConversationId ?? state.currentConversationId;
      if (selectedConversationId && selectedConversationId !== conversationId) return;
      // The first stream event creates the conversation before the parent
      // selection prop necessarily changes. Keep queue response guards aligned
      // with that newly authoritative id immediately.
      activeConversationIdRef.current = conversationId;
      if (!selectedConversationIdRef.current && !currentConversationIdRef.current) {
        selectedConversationIdRef.current = conversationId;
        currentConversationIdRef.current = conversationId;
      }
      if (activeRequestIdRef.current) {
        resumedRunRef.current = {
          conversationId,
          requestId: activeRequestIdRef.current,
        };
      }
      void loadQueuedTurns(conversationId);
    },
    [activeConversationId, loadQueuedTurns, state.currentConversationId],
  );

  const acceptCurrentStreamEvents = useCallback((events: DeepSpaceStreamEvent[] = []) => {
    const startEvent = events.findLast(
      (event) => event.event === "start" && typeof event.data.conversation_id === "string",
    );
    if (startEvent && typeof startEvent.data.conversation_id === "string") {
      const startedConversationId = startEvent.data.conversation_id;
      const existingStreamConversationId = streamConversationIdRef.current;
      if (existingStreamConversationId && existingStreamConversationId !== startedConversationId) {
        streamDetachRef.current();
        streamConversationIdRef.current = null;
        return false;
      }
      // A new chat has no ID until its first start event. Adopt that ID only
      // when no conversation was selected, so later events are scoped too.
      if (!existingStreamConversationId && !selectedConversationIdRef.current) {
        selectedConversationIdRef.current = startedConversationId;
        currentConversationIdRef.current = startedConversationId;
        activeConversationIdRef.current = startedConversationId;
      }
      streamConversationIdRef.current = startedConversationId;
    }
    const streamConversationId = streamConversationIdRef.current;
    const selectedConversationId = selectedConversationIdRef.current;
    const isCurrentConversation =
      !streamConversationId || streamConversationId === selectedConversationId;
    if (!isCurrentConversation) {
      // Closing the stale browser reader prevents it from lingering while a
      // different chat is open. The durable worker continues on the server.
      streamDetachRef.current();
      streamConversationIdRef.current = null;
    }
    return isCurrentConversation;
  }, []);

  const stream = useDeepSpaceStream(
    useMemo(
      () => ({
        onEvent: (event) => {
          if (!acceptCurrentStreamEvents([event])) return;
          consumeNoteEvents([event]);
          dispatch({ type: "stream_event", event });
          if (event.event === "start" && typeof event.data.conversation_id === "string") {
            refreshQueueForStartedConversation(event.data.conversation_id);
          }
        },
        onEvents: (events) => {
          if (!acceptCurrentStreamEvents(events)) return;
          consumeNoteEvents(events);
          dispatch({ type: "stream_events", events });
          for (const event of events) {
            if (event.event === "start" && typeof event.data.conversation_id === "string") {
              refreshQueueForStartedConversation(event.data.conversation_id);
            }
          }
        },
        onTransportError: (error) => {
          if (!acceptCurrentStreamEvents()) return;
          markLiveNoteDraftsFailed();
          // A detached worker can persist a terminal provider error just
          // before the browser-side SSE reader closes. Treat a no-terminal
          // transport close as an interrupted live connection first, then
          // rehydrate the durable record below. Reporting it immediately as
          // STREAM_INCOMPLETE produced a second, misleading system-fault card
          // beside the real provider error.
          if (error.code === "STREAM_INCOMPLETE") {
            pendingHistorySyncRef.current = true;
            dispatch({ type: "stream_interrupted" });
            return;
          }
          dispatch({ type: "stream_failed", error });
        },
        onUserCancel: () => {
          const streamConversationId = streamConversationIdRef.current;
          if (streamConversationId && streamConversationId !== selectedConversationIdRef.current) {
            return;
          }
          streamConversationIdRef.current = null;
          markLiveNoteDraftsFailed();
          dispatch({ type: "stream_interrupted" });
        },
        onFinally: () => {
          if (!acceptCurrentStreamEvents()) return;
          const streamConversationId = streamConversationIdRef.current;
          setCompletionPulse(true);
          if (completionPulseTimeoutRef.current !== null) {
            window.clearTimeout(completionPulseTimeoutRef.current);
          }
          completionPulseTimeoutRef.current = window.setTimeout(() => {
            completionPulseTimeoutRef.current = null;
            setCompletionPulse(false);
          }, 950);
          dispatch({ type: "stream_finished" });
          const conversationId = streamConversationId ?? getReadyConversationId();
          if (conversationId) {
            void loadQueuedTurns(conversationId);
            void loadQueueState(conversationId);
          }
          queueReconnectRef.current = null;
          streamConversationIdRef.current = null;
        },
      }),
      [
        acceptCurrentStreamEvents,
        consumeNoteEvents,
        getReadyConversationId,
        loadQueuedTurns,
        markLiveNoteDraftsFailed,
        loadQueueState,
        refreshQueueForStartedConversation,
      ],
    ),
  );
  const { cancel: cancelStream, detach: detachStream, start: startStream } = stream;
  useLayoutEffect(() => {
    streamDetachRef.current = detachStream;
  }, [detachStream]);
  const startScopedStream = useCallback(
    (args: Parameters<typeof startStream>[0]) => {
      // start() detaches the prior browser reader synchronously. Resolve the
      // scope from the request body or message endpoint before reading events.
      const operation = startStream(args);
      const endpointConversationId = args.endpoint?.match(
        /^\/deepspace\/chats\/([^/?]+)\/messages\//,
      )?.[1];
      streamConversationIdRef.current =
        (typeof args.body.conversation_id === "string" && args.body.conversation_id) ||
        (endpointConversationId ? decodeURIComponent(endpointConversationId) : null) ||
        selectedConversationIdRef.current;
      return operation;
    },
    [startStream],
  );
  const streamStartRef = useRef(startScopedStream);
  useEffect(() => {
    streamStartRef.current = startScopedStream;
  }, [startScopedStream]);

  useEffect(() => {
    const selectedConversationId = selectedConversationIdRef.current;
    const streamConversationId = streamConversationIdRef.current;
    if (streamConversationId && streamConversationId !== selectedConversationId) {
      detachStream();
      streamConversationIdRef.current = null;
    }
  }, [activeConversationId, state.currentConversationId, detachStream]);

  const requestServerCancellation = useCallback(() => {
    const selectedConversationId = selectedConversationIdRef.current;
    const conversationId = getReadyConversationId();
    const requestId = activeRequestIdRef.current;
    if (selectedConversationId && !conversationId) return Promise.resolve(null);
    if (conversationId) {
      return fetchWithAuth(`/deepspace/chats/${conversationId}/cancel`, {
        method: "POST",
        body: JSON.stringify({ client_request_id: requestId }),
      });
    }
    if (requestId) {
      return fetchWithAuth(`/deepspace/chats/queued/${encodeURIComponent(requestId)}/cancel`, {
        method: "POST",
      });
    }
    return Promise.resolve(null);
  }, [getReadyConversationId]);

  const enqueueTurn = useCallback(
    async (
      nextQuery: string,
      steer = false,
      attachmentFileIds: string[] = [],
      regenerateMessageId?: string,
      clientRequestId?: string,
    ): Promise<boolean> => {
      const prompt = nextQuery.trim();
      const conversationId = getReadyConversationId();
      if ((!prompt && !attachmentFileIds.length && !regenerateMessageId) || !conversationId) {
        return false;
      }
      const requestId = clientRequestId ?? crypto.randomUUID();
      try {
        const response = (await fetchWithAuth(`/deepspace/chats/${conversationId}/queue`, {
          method: "POST",
          body: JSON.stringify({
            message: prompt,
            client_request_id: requestId,
            regenerate_message_id: regenerateMessageId,
            thinking_enabled: thinkingEnabled,
            reasoning_effort: activeReasoningEffort,
            steer,
            attachment_file_ids: attachmentFileIds,
          }),
        })) as Response;
        if (!response.ok) {
          throw new Error("DeepSpace could not queue this message.");
        }
        const turn = (await response.json()) as {
          client_request_id: string;
          regenerate_message_id?: string | null;
          prompt: string;
          priority: number;
          sequence: number;
          status:
            | "queued"
            | "running"
            | "cancelling"
            | "awaiting_user"
            | "awaiting_approval"
            | "failed";
          error?: string | null;
        };
        const isStillSelected = getReadyConversationId() === conversationId;
        if (isStillSelected && activeConversationIdRef.current === conversationId) {
          setQueuedTurns((current) =>
            [
              ...current.filter((item) => item.clientRequestId !== turn.client_request_id),
              {
                clientRequestId: turn.client_request_id,
                regenerateMessageId: turn.regenerate_message_id ?? null,
                prompt: turn.prompt,
                priority: turn.priority,
                sequence: turn.sequence,
                status: turn.status,
                error: turn.error ?? null,
              },
            ].sort(
              (left, right) =>
                Number(left.status === "failed") - Number(right.status === "failed") ||
                right.priority - left.priority ||
                left.sequence - right.sequence,
            ),
          );
        }
        if (isStillSelected && !regenerateMessageId) setQuery("");
        if (steer && isStillSelected) {
          void requestServerCancellation().catch(() => {
            toast.error(
              "The steering request was saved, but cancelling the active response failed.",
            );
          });
          cancelStream();
        }
        return true;
      } catch {
        toast.error("Unable to queue this message. Your draft is still available.");
        return false;
      }
    },
    [
      requestServerCancellation,
      cancelStream,
      getReadyConversationId,
      thinkingEnabled,
      activeReasoningEffort,
    ],
  );

  const pauseQueue = useCallback(async () => {
    const conversationId = getReadyConversationId();
    if (!conversationId) return;
    try {
      const response = (await fetchWithAuth(`/deepspace/chats/${conversationId}/queue/pause`, {
        method: "POST",
      })) as Response;
      if (!response.ok) throw new Error("Unable to pause queue");
      if (getReadyConversationId() !== conversationId) return;
      await loadQueueState(conversationId);
      await loadQueuedTurns(conversationId);
      queueReconnectRef.current = null;
      cancelStream();
    } catch {
      toast.error("Unable to pause the DeepSpace queue.");
    }
  }, [cancelStream, getReadyConversationId, loadQueueState, loadQueuedTurns]);

  const reconnectToQueuedRun = useCallback(
    (conversationId: string, clientRequestId: string | null | undefined) => {
      if (!clientRequestId || activeConversationIdRef.current !== conversationId) return;
      if (
        queueReconnectRef.current?.conversationId === conversationId &&
        queueReconnectRef.current.requestId === clientRequestId
      ) {
        return;
      }
      // Queue-control endpoints dispatch work outside the original browser
      // SSE request. Attach immediately to the durable event stream so retry,
      // resume, and steer are live actions rather than requiring a reload.
      queueReconnectRef.current = { conversationId, requestId: clientRequestId };
      activeRequestIdRef.current = clientRequestId;
      setActiveRequestId(clientRequestId);
      resumedRunRef.current = { conversationId, requestId: clientRequestId };
      pendingHistorySyncRef.current = true;
      void startScopedStream({
        endpoint: "/deepspace/chats/stream",
        body: {
          // Reconnect never enqueues or displays this placeholder; the API
          // only needs a non-empty message to validate the stream request.
          message: "Reconnecting to queued DeepSpace response.",
          conversation_id: conversationId,
          client_request_id: clientRequestId,
          reconnect: true,
          thinking_enabled: thinkingEnabled,
          reasoning_effort: activeReasoningEffort,
        },
      });
      // A queue worker may create its durable assistant record just after the
      // endpoint returns. Rehydrate twice to bridge that short race safely.
      window.setTimeout(() => void loadConversationRef.current(conversationId), 150);
      window.setTimeout(() => void loadConversationRef.current(conversationId), 750);
    },
    [activeReasoningEffort, startScopedStream, thinkingEnabled],
  );

  useEffect(() => {
    const conversationId = getReadyConversationId();
    const requestId = queueState.activeRequestId;
    if (!conversationId || !requestId || state.isStreaming) return;
    if (
      resumedRunRef.current?.conversationId === conversationId &&
      resumedRunRef.current.requestId === requestId
    ) {
      return;
    }
    reconnectToQueuedRun(conversationId, requestId);
  }, [
    activeConversationId,
    queueState.activeRequestId,
    reconnectToQueuedRun,
    getReadyConversationId,
    state.currentConversationId,
    state.isStreaming,
  ]);

  const resumeQueue = useCallback(async () => {
    const conversationId = getReadyConversationId();
    if (!conversationId || queueAction) return;
    setQueueAction("resume");
    try {
      const response = (await fetchWithAuth(`/deepspace/chats/${conversationId}/queue/resume`, {
        method: "POST",
      })) as Response;
      if (!response.ok) throw new Error("Unable to resume queue");
      if (getReadyConversationId() !== conversationId) return;
      const payload = (await response.json()) as { active_request_id?: string | null };
      const nextState = await loadQueueState(conversationId);
      await loadQueuedTurns(conversationId);
      const requestId = nextState?.activeRequestId ?? payload.active_request_id;
      if (requestId && !state.isStreaming) reconnectToQueuedRun(conversationId, requestId);
    } catch {
      toast.error("Unable to resume the DeepSpace queue.");
    } finally {
      setQueueAction(null);
    }
  }, [
    loadQueueState,
    loadQueuedTurns,
    getReadyConversationId,
    queueAction,
    reconnectToQueuedRun,
    state.isStreaming,
  ]);

  const startQueuedTurnEdit = useCallback(
    (clientRequestId: string) => {
      if (editingQueuedTurn || queueAction) return;
      const turn = queuedTurns.find((item) => item.clientRequestId === clientRequestId);
      if (!turn || turn.status !== "queued") return;
      queueEditDraftRef.current = query;
      setQuery(turn.prompt);
      const edit = {
        clientRequestId: turn.clientRequestId,
        originalPrompt: turn.prompt,
      };
      editingQueuedTurnRef.current = edit;
      setEditingQueuedTurn(edit);
    },
    [editingQueuedTurn, query, queueAction, queuedTurns],
  );

  const cancelQueuedTurnEdit = useCallback(() => {
    if (queueAction) return;
    editingQueuedTurnRef.current = null;
    setEditingQueuedTurn(null);
    setQuery(queueEditDraftRef.current ?? "");
    queueEditDraftRef.current = null;
  }, [queueAction]);

  const saveQueuedTurnEdit = useCallback(
    async (clientRequestId: string, message: string): Promise<boolean> => {
      const conversationId = getReadyConversationId();
      const edit = editingQueuedTurn;
      const prompt = message.trim();
      if (
        !conversationId ||
        !edit ||
        edit.clientRequestId !== clientRequestId ||
        !prompt ||
        queueAction
      ) {
        return false;
      }

      queueEditSaveInProgressRef.current = true;
      setQueueAction(`edit:${clientRequestId}`);
      try {
        const response = (await fetchWithAuth(
          `/deepspace/chats/${conversationId}/queue/${encodeURIComponent(clientRequestId)}`,
          {
            method: "PATCH",
            body: JSON.stringify({ message: prompt, expected_prompt: edit.originalPrompt }),
          },
        )) as Response;
        if (!response.ok) {
          let messageFromServer = "Unable to update this queued prompt.";
          let errorCode: string | undefined;
          try {
            const payload = (await response.json()) as {
              error?: { code?: string; message?: string };
              detail?: { code?: string; message?: string } | string;
              code?: string;
              message?: string;
            };
            const detail = payload.detail;
            errorCode =
              (typeof detail === "object" ? detail.code : undefined) ??
              payload.error?.code ??
              payload.code;
            messageFromServer =
              (typeof detail === "string" ? detail : detail?.message) ??
              payload.error?.message ??
              payload.message ??
              messageFromServer;
          } catch {
            // Keep the actionable fallback when the server did not return JSON.
          }

          if (response.status === 409 || response.status === 404) {
            await loadQueuedTurns(conversationId);
            editingQueuedTurnRef.current = null;
            setEditingQueuedTurn(null);
            queueEditDraftRef.current = null;
            toast.error(
              errorCode === "QUEUE_TURN_EDIT_CONFLICT"
                ? "This prompt changed in another tab. Your text is still in the composer; reopen the latest queue item to apply it."
                : "This prompt already started or was removed. Your edited text is still in the composer.",
            );
            return false;
          }
          throw new Error(messageFromServer);
        }
        if (getReadyConversationId() !== conversationId) return true;

        const updated = (await response.json()) as {
          client_request_id: string;
          prompt: string;
        };
        if (activeConversationIdRef.current === conversationId) {
          setQueuedTurns((current) =>
            current.map((turn) =>
              turn.clientRequestId === updated.client_request_id
                ? { ...turn, prompt: updated.prompt }
                : turn,
            ),
          );
        }
        editingQueuedTurnRef.current = null;
        setEditingQueuedTurn(null);
        setQuery(queueEditDraftRef.current ?? "");
        queueEditDraftRef.current = null;
        toast.success("Queued prompt updated in the same position.");
        return true;
      } catch (error) {
        toast.error(
          error instanceof Error ? error.message : "Unable to update this queued prompt.",
        );
        return false;
      } finally {
        queueEditSaveInProgressRef.current = false;
        setQueueAction(null);
      }
    },
    [editingQueuedTurn, getReadyConversationId, loadQueuedTurns, queueAction],
  );

  const cancelQueuedTurn = useCallback(
    async (clientRequestId: string) => {
      try {
        const response = (await fetchWithAuth(
          `/deepspace/chats/queued/${encodeURIComponent(clientRequestId)}/cancel`,
          { method: "POST" },
        )) as Response;
        if (!response.ok) throw new Error("Unable to cancel queued message");
        if (editingQueuedTurn?.clientRequestId === clientRequestId) {
          editingQueuedTurnRef.current = null;
          setEditingQueuedTurn(null);
          queueEditDraftRef.current = null;
        }
        setQueuedTurns((current) =>
          current.filter((turn) => turn.clientRequestId !== clientRequestId),
        );
      } catch {
        toast.error("Unable to remove the queued message.");
      }
    },
    [editingQueuedTurn],
  );

  const clearQueue = useCallback(async () => {
    const conversationId = getReadyConversationId();
    if (!conversationId) return;
    try {
      const response = (await fetchWithAuth(`/deepspace/chats/${conversationId}/queue/clear`, {
        method: "POST",
      })) as Response;
      if (!response.ok) throw new Error("Unable to clear queue");
      if (getReadyConversationId() !== conversationId) return;
      setQueuedTurns([]);
      if (editingQueuedTurn) {
        editingQueuedTurnRef.current = null;
        setEditingQueuedTurn(null);
        queueEditDraftRef.current = null;
      }
      await loadQueueState(conversationId);
      await loadQueuedTurns(conversationId);
      toast.success("Pending queue cleared. Chat history was kept.");
    } catch {
      toast.error("Unable to clear the DeepSpace queue.");
    }
  }, [editingQueuedTurn, getReadyConversationId, loadQueueState, loadQueuedTurns]);

  const retryFailedTurn = useCallback(
    async (clientRequestId: string) => {
      const conversationId = getReadyConversationId();
      if (!conversationId || queueAction) return;
      const retryRequestId = crypto.randomUUID();
      setQueueAction(clientRequestId);
      try {
        const response = (await fetchWithAuth(
          `/deepspace/chats/${conversationId}/queue/${encodeURIComponent(clientRequestId)}/retry`,
          {
            method: "POST",
            body: JSON.stringify({ client_request_id: retryRequestId }),
          },
        )) as Response;
        if (!response.ok) {
          let message = "Unable to retry this prompt.";
          try {
            const payload = (await response.json()) as {
              detail?: { message?: string } | string;
              message?: string;
            };
            message =
              (typeof payload.detail === "string" ? payload.detail : payload.detail?.message) ??
              payload.message ??
              message;
          } catch {
            // Keep the actionable fallback if the server did not return JSON.
          }
          throw new Error(message);
        }
        if (getReadyConversationId() !== conversationId) return;
        const retry = (await response.json()) as {
          client_request_id?: string | null;
          status?: string;
        };
        const nextState = await loadQueueState(conversationId);
        await loadQueuedTurns(conversationId);
        const requestId = retry.client_request_id;
        if (
          requestId &&
          !nextState?.paused &&
          (!nextState?.activeRequestId || nextState.activeRequestId === requestId) &&
          !state.isStreaming
        ) {
          reconnectToQueuedRun(conversationId, requestId);
        } else if (requestId) {
          toast.success(
            nextState?.paused
              ? "Retry added. Resume the queue when you are ready."
              : "Retry added to the queue. It will start when the active turn clears.",
          );
        }
      } catch (error) {
        toast.error(error instanceof Error ? error.message : "Unable to retry this prompt.");
      } finally {
        setQueueAction(null);
      }
    },
    [
      loadQueueState,
      loadQueuedTurns,
      getReadyConversationId,
      queueAction,
      reconnectToQueuedRun,
      state.isStreaming,
    ],
  );

  const steerQueuedTurn = useCallback(
    async (clientRequestId: string) => {
      const conversationId = getReadyConversationId();
      if (!conversationId) return;
      try {
        const response = (await fetchWithAuth(
          `/deepspace/chats/${conversationId}/queue/${encodeURIComponent(clientRequestId)}/steer`,
          { method: "POST" },
        )) as Response;
        if (!response.ok) throw new Error("Unable to steer queued message");
        if (getReadyConversationId() !== conversationId) return;
        const turn = (await response.json()) as QueuedTurn & { client_request_id?: string };
        if (activeConversationIdRef.current === conversationId) {
          setQueuedTurns((current) =>
            current
              .map((item) =>
                item.clientRequestId === clientRequestId
                  ? { ...item, priority: turn.priority, status: turn.status }
                  : item,
              )
              .sort(
                (left, right) =>
                  Number(left.status === "failed") - Number(right.status === "failed") ||
                  right.priority - left.priority ||
                  left.sequence - right.sequence,
              ),
          );
        }
        await loadQueueState(conversationId);
        void requestServerCancellation().catch(() => {
          toast.error(
            "The queued message was promoted, but cancelling the active response failed.",
          );
        });
        queueReconnectRef.current = null;
        cancelStream();
        reconnectToQueuedRun(conversationId, turn.client_request_id);
      } catch {
        toast.error("Unable to steer the queued message.");
      }
    },
    [
      cancelStream,
      loadQueueState,
      reconnectToQueuedRun,
      getReadyConversationId,
      requestServerCancellation,
    ],
  );

  const resolveMCPApproval = useCallback(
    async (approvalId: string, decision: "approved" | "denied") => {
      const conversationId = getReadyConversationId();
      if (!conversationId || !approvalId) return;
      const response = (await fetchWithAuth(
        `/deepspace/chats/${conversationId}/approvals/${encodeURIComponent(approvalId)}`,
        {
          method: "POST",
          body: JSON.stringify({ decision }),
        },
      )) as Response;
      if (!response.ok) {
        toast.error("Unable to resolve the MCP approval request.");
        return;
      }
      if (getReadyConversationId() !== conversationId) return;
      pendingHistorySyncRef.current = true;
      await startScopedStream({
        endpoint: "/deepspace/chats/stream",
        body: {
          conversation_id: conversationId,
          resume_approval_id: approvalId,
          thinking_enabled: thinkingEnabled,
          reasoning_effort: activeReasoningEffort,
        },
      });
    },
    [getReadyConversationId, startScopedStream, thinkingEnabled, activeReasoningEffort],
  );

  const loadConversation = useCallback(
    async (conversationId: string) => {
      // History is requested from several effects (mount, queue refresh, and
      // post-stream reconciliation). Only the newest request may replace the
      // thread; an older response can otherwise erase a newer local timeline
      // after a quick navigation or reload.
      const requestVersion = ++historyRequestVersionRef.current;
      const isCurrentRequest = () =>
        requestVersion === historyRequestVersionRef.current &&
        selectedConversationIdRef.current === conversationId;
      if (isCurrentRequest()) {
        queueMicrotask(() => {
          if (isCurrentRequest()) setHistoryLoadErrorId(null);
        });
      }
      // A page transition can race the API request. Retry short transient
      // failures and keep the current thread visible instead of replacing it
      // with an empty reducer state.
      for (let attempt = 0; attempt < 3; attempt += 1) {
        if (!isCurrentRequest()) return;
        try {
          const response = (await fetchWithAuth(
            `/deepspace/chats/${conversationId}/messages`,
          )) as Response;
          if (response.ok) {
            const payload = (await response.json()) as { messages: DeepSpaceHistoryMessage[] };
            if (!isCurrentRequest()) return;
            dispatch({ type: "load_history", conversationId, messages: payload.messages });
            setHistoryLoadErrorId(null);
            // Reattach to a still-running worker after navigation or refresh.
            // The reconnect flag is read-only: it never starts a second run.
            const messages = payload.messages;
            const activeAssistant = [...messages]
              .map((message, index) => ({ message, index }))
              .reverse()
              .find(
                ({ message }) =>
                  message.role === "assistant" &&
                  message.metadata_json?.status === "streaming" &&
                  message.metadata_json?.runtime_active !== false &&
                  typeof message.metadata_json?.client_request_id === "string",
              );
            if (activeAssistant) {
              const requestId = String(
                activeAssistant.message.metadata_json?.client_request_id ?? "",
              );
              const source = [...messages.slice(0, activeAssistant.index)]
                .reverse()
                .find((message) => message.role === "user");
              const alreadyAttached =
                resumedRunRef.current?.conversationId === conversationId &&
                resumedRunRef.current?.requestId === requestId;
              activeRequestIdRef.current = requestId || null;
              setActiveRequestId(requestId || null);
              if (requestId && source && !alreadyAttached) {
                // A user can switch to another chat and return while this
                // worker is still active. Scope the reconnect cache to both
                // conversation and request; a request id alone prevented the
                // second visit from restoring its live stream.
                resumedRunRef.current = { conversationId, requestId };
                activeRequestIdRef.current = requestId;
                void streamStartRef.current({
                  endpoint: "/deepspace/chats/stream",
                  body: {
                    message: source.content,
                    conversation_id: conversationId,
                    client_request_id: requestId,
                    reconnect: true,
                    thinking_enabled: thinkingEnabled,
                    reasoning_effort: activeReasoningEffort,
                  },
                });
              }
            } else {
              activeRequestIdRef.current = null;
              setActiveRequestId(null);
            }
            return;
          }
          if (response.status === 404) {
            if (!isCurrentRequest()) return;
            setHistoryLoadErrorId(conversationId);
            return;
          }
        } catch (error) {
          if (attempt === 2) {
            console.error("Failed to load DeepSpace conversation history", error);
          }
        }
        await new Promise((resolve) => window.setTimeout(resolve, 250 * (attempt + 1)));
      }
      if (isCurrentRequest()) setHistoryLoadErrorId(conversationId);
    },
    [thinkingEnabled, activeReasoningEffort],
  );

  useEffect(() => {
    loadConversationRef.current = loadConversation;
  }, [loadConversation]);

  useEffect(() => {
    if (queueEditDraftRef.current !== null) {
      editingQueuedTurnRef.current = null;
      setEditingQueuedTurn(null);
      setQuery(queueEditDraftRef.current);
      queueEditDraftRef.current = null;
    }
    saveMCPActiveContext({ conversation_id: activeConversationId });
    if (activeConversationId) {
      if (state.currentConversationId !== activeConversationId) {
        activeRequestIdRef.current = null;
        queueReconnectRef.current = null;
        resumedRunRef.current = null;
        queueMicrotask(() => {
          if (selectedConversationIdRef.current !== activeConversationId) return;
          setActiveRequestId(null);
          setQueueAction(null);
          setQueuedTurns([]);
          setQueueState({
            paused: false,
            reason: null,
            failedRequestId: null,
            activeRequestId: null,
            pausedAt: null,
          });
        });
      }
      queueMicrotask(() => void loadConversation(activeConversationId));
      queueMicrotask(() => void loadQueuedTurns(activeConversationId));
      queueMicrotask(() => void loadQueueState(activeConversationId));
    } else {
      historyRequestVersionRef.current += 1;
      queueRequestVersionRef.current += 1;
      setHistoryLoadErrorId(null);
      activeRequestIdRef.current = null;
      setActiveRequestId(null);
      dispatch({ type: "reset_thread" });
      queueMicrotask(() => {
        setQueuedTurns([]);
        setQueueState({
          paused: false,
          reason: null,
          failedRequestId: null,
          activeRequestId: null,
          pausedAt: null,
        });
      });
    }
  }, [
    activeConversationId,
    loadConversation,
    loadQueueState,
    loadQueuedTurns,
    state.currentConversationId,
  ]);

  useEffect(() => {
    if (
      !state.isStreaming &&
      activeConversationId &&
      queuedTurns.some((turn) => turn.status === "running")
    ) {
      queueMicrotask(() => void loadConversation(activeConversationId));
    }
  }, [activeConversationId, loadConversation, queuedTurns, state.isStreaming]);

  useEffect(
    () => () => {
      if (scrollMetricsRafRef.current !== null) {
        window.cancelAnimationFrame(scrollMetricsRafRef.current);
      }
      if (autoScrollRafRef.current !== null) {
        window.cancelAnimationFrame(autoScrollRafRef.current);
      }
    },
    [],
  );

  useEffect(() => {
    if (!state.isStreaming && pendingHistorySyncRef.current && state.currentConversationId) {
      pendingHistorySyncRef.current = false;
      const transportInterrupted =
        state.streamError?.code === "STREAM_INCOMPLETE" ||
        state.streamError?.code === "STREAM_TRANSPORT_ERROR" ||
        state.streamError?.code === "STREAM_HTTP_ERROR";
      if (state.streamError && !transportInterrupted) {
        return;
      }
      // A broken browser connection is not a cancelled run. Reload the
      // durable history so loadConversation can reattach to its worker.
      const conversationId = state.currentConversationId;
      queueMicrotask(() => void loadConversation(conversationId));
    }
  }, [loadConversation, state.currentConversationId, state.isStreaming, state.streamError]);

  const submitQuery = useCallback(
    async (
      nextQuery?: string,
      resumeUserQuestion?: { messageId: string; questionId: string },
      attachmentFileIds: string[] = [],
    ) => {
      const conversationId = selectedConversationIdRef.current;
      if (conversationId && currentConversationIdRef.current !== conversationId) return;
      const effectiveQuery = (nextQuery ?? query).trim();
      if (
        (!effectiveQuery && !attachmentFileIds.length) ||
        creatingNewChat ||
        submissionInFlightRef.current
      )
        return;

      // A composer message is always a new turn.  In particular, it must
      // never be guessed to be the answer to an older ask_user card: that
      // would turn a fresh request such as "hello" into stale task input.
      // Only an explicit action from that card supplies a question id.
      const answeringUserQuestion = Boolean(resumeUserQuestion);
      // Pausing controls dispatch, not composition. New messages remain
      // available in the composer and are stored as pending queue work until
      // the user resumes the queue.
      if ((queueState.paused || state.isStreaming) && !answeringUserQuestion) {
        await enqueueTurn(effectiveQuery, false, attachmentFileIds);
        return;
      }

      submissionInFlightRef.current = true;
      try {
        await modelSwitchRef.current;
        if (getReadyConversationId() !== conversationId) return;

        const requestId = crypto.randomUUID();
        if (completionPulseTimeoutRef.current !== null) {
          window.clearTimeout(completionPulseTimeoutRef.current);
          completionPulseTimeoutRef.current = null;
        }
        setCompletionPulse(false);
        setQuery("");
        autoFollowRef.current = true;
        if (resumeUserQuestion) {
          dispatch({
            type: "resume_user_question",
            messageId: resumeUserQuestion.messageId,
            query: effectiveQuery,
          });
        } else {
          dispatch({
            type: "submit_query",
            query: effectiveQuery || "Attached Library file(s)",
            clientRequestId: requestId,
          });
        }
        pendingHistorySyncRef.current = true;
        activeRequestIdRef.current = requestId;
        setActiveRequestId(requestId);
        if (conversationId) {
          resumedRunRef.current = { conversationId, requestId };
        }

        await startScopedStream({
          endpoint: "/deepspace/chats/stream",
          body: {
            message: effectiveQuery,
            conversation_id: conversationId,
            client_request_id: requestId,
            thinking_enabled: thinkingEnabled,
            reasoning_effort: activeReasoningEffort,
            attachment_file_ids: attachmentFileIds,
            ...(resumeUserQuestion
              ? { resume_user_question_id: resumeUserQuestion.questionId }
              : {}),
          },
        });
      } finally {
        submissionInFlightRef.current = false;
      }
    },
    [
      query,
      state.isStreaming,
      creatingNewChat,
      enqueueTurn,
      startScopedStream,
      getReadyConversationId,
      thinkingEnabled,
      activeReasoningEffort,
      queueState.paused,
    ],
  );

  const submitUserQuestionAnswer = useCallback(
    async (answer: string) => {
      const pending = findPendingUserQuestion(state.messages);
      // The card may have become stale after a live update. Do not submit the
      // answer as an unrelated new request in that case.
      if (!pending) return;
      await submitQuery(answer, pending);
    },
    [state.messages, submitQuery],
  );

  const startNewChat = useCallback(async () => {
    queueReconnectRef.current = null;
    detachStream();
    streamConversationIdRef.current = null;
    activeRequestIdRef.current = null;
    setActiveRequestId(null);
    editingQueuedTurnRef.current = null;
    setEditingQueuedTurn(null);
    queueEditDraftRef.current = null;
    setQuery("");
    pendingHistorySyncRef.current = false;
    dispatch({ type: "reset_thread" });
    if (!onNewNote) return;
    setCreatingNewChat(true);
    try {
      await onNewNote();
    } finally {
      setCreatingNewChat(false);
    }
  }, [detachStream, onNewNote]);

  const stopStreaming = useCallback(() => {
    // Cancellation is durable server state. The browser reader closes right
    // away for responsiveness, while the worker receives the authoritative
    // cancellation flag and advances the conversation queue only on terminal state.
    void requestServerCancellation().catch(() => {
      toast.error("Stop was requested locally, but the server could not confirm it yet.");
    });
    queueReconnectRef.current = null;
    cancelStream();
  }, [cancelStream, requestServerCancellation]);

  const syncVoiceSession = useCallback(
    async (nextStt: boolean, nextTts: boolean) => {
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
          const identity = user?.id ? `user-${user.id}` : "";
          const tokenRes = await fetchWithAuth(
            `/voice/token?room=${encodeURIComponent(uniqueRoom)}&identity=${encodeURIComponent(identity)}`,
          );
          if (!tokenRes.ok) {
            throw new Error(`Voice token request failed (${tokenRes.status})`);
          }
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

          const livekitUrl =
            process.env.NEXT_PUBLIC_LIVEKIT_URL ||
            (window.location.protocol === "https:"
              ? `wss://${window.location.host}/livekit`
              : `ws://${window.location.hostname}:7880`);
          await room.connect(livekitUrl, token);
        }

        const microphoneOperation = room.localParticipant.setMicrophoneEnabled(nextStt, {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        });
        void microphoneOperation.catch((error: unknown) => {
          console.error("Voice microphone setup failed", error);
          if (nextStt && roomRef.current === room) {
            setSttActive(false);
            setVoiceState("idle");
            setVoiceLabel("Microphone unavailable.");
          }
        });

        const initialPrompt = buildInitialPrompt(messagesRef.current, currentContentRef.current);
        const modePayload = JSON.stringify({
          type: "set-mode",
          stt: nextStt,
          tts: nextTts,
          initial_prompt: initialPrompt,
        });
        const encodedModePayload = new TextEncoder().encode(modePayload);
        const publishVoiceMode = () => {
          void room.localParticipant
            .publishData(encodedModePayload, {
              reliable: true,
              topic: "voice-control",
            })
            .catch((error: unknown) => {
              // The agent can reconnect independently from the browser. A
              // later ParticipantConnected event retries the same mode packet;
              // the room itself remains usable while that handshake settles.
              console.warn("Voice mode synchronization failed", error);
            });
        };

        // LiveKit may resolve room.connect before the voice agent has joined.
        // Send once now and once when the agent appears so the mode is never
        // lost during that normal startup race.
        publishVoiceMode();
        const agentAlreadyConnected = Array.from(room.remoteParticipants.values()).some(
          (participant: any) => String(participant.identity).startsWith("agent-"),
        );
        if (!agentAlreadyConnected) {
          const onAgentConnected = (participant: any) => {
            if (!String(participant.identity).startsWith("agent-")) return;
            room.off(RoomEvent.ParticipantConnected, onAgentConnected);
            publishVoiceMode();
          };
          room.on(RoomEvent.ParticipantConnected, onAgentConnected);
        }

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
    },
    [submitQuery, queueText, user],
  );

  const handleSttToggle = useCallback(() => {
    void syncVoiceSession(!sttActive, ttsActive);
  }, [sttActive, ttsActive, syncVoiceSession]);

  const handleTtsToggle = useCallback(() => {
    void syncVoiceSession(sttActive, !ttsActive);
  }, [sttActive, ttsActive, syncVoiceSession]);

  const handleRegenerate = useCallback(
    async (messageId: string) => {
      const conversationId = getReadyConversationId();
      if (!conversationId) return;
      pendingHistorySyncRef.current = true;
      const requestId = crypto.randomUUID();
      const queued = await enqueueTurn("", false, [], messageId, requestId);
      if (!queued || state.isStreaming) return;
      const nextState = await loadQueueState(conversationId);
      await loadQueuedTurns(conversationId);
      if (
        nextState?.activeRequestId === requestId &&
        !nextState.paused &&
        getReadyConversationId() === conversationId
      ) {
        reconnectToQueuedRun(conversationId, requestId);
      }
    },
    [
      getReadyConversationId,
      enqueueTurn,
      state.isStreaming,
      loadQueueState,
      loadQueuedTurns,
      reconnectToQueuedRun,
    ],
  );

  const handleSaveEdit = useCallback(
    async (messageId: string, content: string) => {
      const conversationId = getReadyConversationId();
      if (state.isStreaming || !conversationId) return;

      dispatch({ type: "cancel_edit", messageId });
      // Keep the edited prompt in its original timeline position immediately.
      // The API still validates that this is the latest editable user turn;
      // using the clicked id prevents an edit from silently jumping to a
      // different turn when history contains multiple message versions.
      dispatch({
        type: "update_message",
        messageId,
        data: {
          content,
          rawContent: content,
          draftContent: null,
          isEditing: false,
        },
      });
      pendingHistorySyncRef.current = true;

      await startScopedStream({
        endpoint: `/deepspace/chats/${conversationId}/messages/${messageId}/edit-and-regenerate/stream`,
        body: {
          client_request_id: crypto.randomUUID(),
          content,
          thinking_enabled: thinkingEnabled,
          reasoning_effort: activeReasoningEffort,
        },
      });
    },
    [
      getReadyConversationId,
      state.isStreaming,
      startScopedStream,
      thinkingEnabled,
      activeReasoningEffort,
    ],
  );

  const handleActivateVersion = useCallback(async (messageId: string, versionId: string) => {
    const conversationId = selectedConversationIdRef.current;
    if (!conversationId || currentConversationIdRef.current !== conversationId) {
      return;
    }
    const message = messagesRef.current.find((item) => item.id === messageId);
    const version = message?.versions?.find((item) => item.id === versionId);
    if (!message || message.status === "streaming" || !version) return;
    if (message.activeVersionId === versionId) return;

    // Render from the immutable version already in history immediately. The
    // serialized PATCHes below persist each rapid arrow press in its order.
    dispatch({ type: "activate_version", messageId, version });

    const queueKey = JSON.stringify([conversationId, messageId]);
    const sequence = (versionActivationSequenceRef.current.get(queueKey) ?? 0) + 1;
    versionActivationSequenceRef.current.set(queueKey, sequence);
    const previousOperation = versionActivationQueuesRef.current.get(queueKey);
    const operation = (previousOperation ?? Promise.resolve())
      .catch(() => undefined)
      .then(async () => {
        const response = (await fetchWithAuth(
          `/deepspace/chats/${conversationId}/messages/${messageId}/versions/${versionId}/activate`,
          { method: "PATCH" },
        )) as Response;
        if (!response.ok) throw new Error("Version activation failed");
        const updatedMessage = (await response.json()) as {
          versions?: DeepSpaceHistoryMessage["versions"];
        };
        const savedVersion = updatedMessage.versions?.find((item) => item.id === versionId);
        if (!savedVersion) throw new Error("The selected version was not returned");
        return savedVersion;
      });
    versionActivationQueuesRef.current.set(queueKey, operation);

    try {
      const savedVersion = await operation;
      if (
        versionActivationSequenceRef.current.get(queueKey) === sequence &&
        selectedConversationIdRef.current === conversationId &&
        currentConversationIdRef.current === conversationId
      ) {
        dispatch({ type: "activate_version", messageId, version: savedVersion });
      }
    } catch {
      if (
        versionActivationSequenceRef.current.get(queueKey) === sequence &&
        selectedConversationIdRef.current === conversationId &&
        currentConversationIdRef.current === conversationId
      ) {
        toast.error("Could not save that response version. Restoring the saved version.");
        void loadConversationRef.current(conversationId);
      }
    } finally {
      if (versionActivationQueuesRef.current.get(queueKey) === operation) {
        versionActivationQueuesRef.current.delete(queueKey);
      }
      if (versionActivationSequenceRef.current.get(queueKey) === sequence) {
        versionActivationSequenceRef.current.delete(queueKey);
      }
    }
  }, []);

  const latestAssistantContent = (() => {
    for (let index = state.messages.length - 1; index >= 0; index -= 1) {
      const message = state.messages[index];
      if (message?.role === "assistant") {
        return message.content.trim();
      }
    }
    return "";
  })();

  const activeAssistantMessage = state.messages.find(
    (message) => message.id === state.activeAssistantId,
  );
  const retryableFailedRequestIds = useMemo(
    () =>
      new Set(
        queuedTurns.filter((turn) => turn.status === "failed").map((turn) => turn.clientRequestId),
      ),
    [queuedTurns],
  );
  const retryingFailedRequestId =
    queueAction && retryableFailedRequestIds.has(queueAction) ? queueAction : null;
  const activeRequestIdForDisplay = activeAssistantMessage?.clientRequestId ?? activeRequestId;
  const activeRequestIsQueued =
    state.isStreaming &&
    queuedTurns.some(
      (turn) => turn.clientRequestId === activeRequestIdForDisplay && turn.status === "queued",
    );
  const visibleQueuedTurns = activeRequestIsQueued
    ? queuedTurns.filter((turn) => turn.clientRequestId !== activeRequestIdForDisplay)
    : queuedTurns;
  const latestAssistant = [...state.messages]
    .reverse()
    .find(
      (message) =>
        message.role === "assistant" &&
        (message.content.trim() ||
          message.rawContent?.trim() ||
          message.thinkingContent?.trim() ||
          message.error ||
          message.blocks?.length ||
          message.agentSteps?.length ||
          message.status === "streaming"),
    );

  useEffect(() => {
    // TTS commentary is driven by the completed chat answer, not by the
    // internal thinking/tool stream. Publish once per assistant message and
    // let the voice agent synthesize it through the active LiveKit room.
    if (!ttsActive || state.isStreaming || !roomRef.current || !latestAssistant?.content?.trim()) {
      return;
    }
    const messageKey = latestAssistant.id || latestAssistant.content;
    if (lastTtsMessageRef.current === messageKey) return;
    lastTtsMessageRef.current = messageKey;
    void roomRef.current.localParticipant.publishData(
      new TextEncoder().encode(
        JSON.stringify({ type: "test-tts", text: latestAssistant.content.trim() }),
      ),
    );
  }, [latestAssistant?.content, latestAssistant?.id, state.isStreaming, ttsActive]);
  const pendingUserQuestion = findPendingUserQuestion(state.messages);
  const showActiveResponseControls = Boolean(
    state.isStreaming &&
    !pendingUserQuestion &&
    !creatingNewChat &&
    activeAssistantMessage?.role === "assistant" &&
    activeAssistantMessage.status === "streaming" &&
    (!state.currentConversationId || state.currentConversationId === activeConversationId),
  );
  const changedFiles = useMemo(() => {
    const files = new Map<string, { path: string; additions: number; deletions: number }>();
    for (const step of latestAssistant?.agentSteps ?? []) {
      const diff = step.diffStats;
      if (!diff?.path) continue;
      const current = files.get(diff.path) ?? { path: diff.path, additions: 0, deletions: 0 };
      current.additions += diff.additions;
      current.deletions += diff.deletions;
      files.set(diff.path, current);
    }
    return [...files.values()];
  }, [latestAssistant?.agentSteps]);
  const runtimeActivity = useMemo(() => {
    const hasError = Boolean(state.streamError || latestAssistant?.error);
    const activeSteps = (latestAssistant?.agentSteps ?? []).filter(
      (step) => step.status === "running" || step.status === "awaiting_approval",
    );
    const activeTool = activeSteps.find(
      (step) =>
        step.type === "tool_start" ||
        step.type === "observing" ||
        step.type === "tool_result" ||
        step.type === "tool_error",
    );
    const activeTimelineTool = (latestAssistant?.timeline ?? []).find(
      (step) =>
        step.status === "running" && (step.type === "tool_call" || step.type === "observation"),
    );

    let phase: DeepSpaceRuntimePhase = "idle";
    if (hasError) {
      phase = "error";
    } else if (completionPulse) {
      phase = "completed";
    } else if (
      state.isStreaming &&
      !latestAssistant?.rawContent?.trim() &&
      !latestAssistant?.thinkingContent?.trim() &&
      !(latestAssistant?.agentSteps?.length ?? 0) &&
      !(latestAssistant?.timeline?.length ?? 0)
    ) {
      phase = "submitting";
    } else if (state.isStreaming && (activeTool || activeTimelineTool)) {
      phase = "tool_calling";
    } else if (state.isStreaming && latestAssistant?.thinkingContent?.trim()) {
      phase = "thinking";
    } else if (state.isStreaming) {
      phase = "receiving";
    }

    return {
      phase,
      activeToolName: activeTool?.toolName ?? activeTimelineTool?.toolName ?? null,
      hasError,
    };
  }, [completionPulse, latestAssistant, state.isStreaming, state.streamError]);
  const renderableMessages = useMemo(
    () =>
      state.messages.filter(
        (message) =>
          message.role === "user" ||
          Boolean(
            message.content.trim() ||
            message.rawContent?.trim() ||
            message.thinkingContent?.trim() ||
            message.error ||
            message.blocks?.length ||
            message.agentSteps?.length ||
            message.status === "streaming",
          ),
      ),
    [state.messages],
  );
  const isConversationSwitching = Boolean(
    activeConversationId && state.currentConversationId !== activeConversationId,
  );
  const selectedConversationLoadFailed = Boolean(
    isConversationSwitching && historyLoadErrorId === activeConversationId,
  );
  const contextUsedTokens = latestAssistant?.metrics?.contextUsedTokens ?? null;
  // Show the request budget live: while typing, include the unsent prompt; while
  // streaming, include the assistant tokens arriving in the current turn. The
  // persisted backend metric remains the exact serialized request estimate.
  const draftTokens = query.trim() ? query.trim().split(/\s+/).length : 0;
  // `totalTokens` is a display-oriented word count, not provider tokens.
  // Use the backend's request output estimate after completion and a matching
  // serialized-text estimate while a response is streaming.
  const streamedOutputTokens = state.isStreaming
    ? Math.max(0, Math.ceil((latestAssistant?.content?.length ?? 0) / 4))
    : (latestAssistant?.metrics?.requestOutputTokens ?? 0);
  const liveContextUsedTokens =
    contextUsedTokens === null
      ? draftTokens || null
      : contextUsedTokens + (state.isStreaming ? 0 : draftTokens);
  const userVisibleInputTokens = latestAssistant?.metrics?.userVisibleInputTokens ?? 0;
  const userVisibleOutputTokens = latestAssistant?.metrics?.userVisibleOutputTokens ?? 0;
  const conversationVisibleTokens = latestAssistant?.metrics?.conversationVisibleTokens ?? 0;
  const verifiedClientContextLimit = (modelName: string | null): number | null => {
    const normalized = (modelName ?? "").toLowerCase().replace(/[^a-z0-9]/g, "");
    if (normalized.includes("nemotron3ultra") || normalized.includes("nemotron3super")) {
      return 1_048_576;
    }
    if (normalized.startsWith("minimaxm2")) return 204_800;
    if (normalized.startsWith("qwen3coder480b") || normalized.startsWith("qwen25coder")) {
      return 256_000;
    }
    if (normalized.startsWith("qwen3") || normalized.startsWith("qwen25")) return 128_000;
    if (normalized.startsWith("deepseekflash") || normalized.startsWith("deepseekv4")) {
      return 1_048_576;
    }
    if (normalized.startsWith("deepseekr1") || normalized.startsWith("deepseekv3")) {
      return 64_000;
    }
    return null;
  };
  const contextLimit =
    selectedModel?.contextWindow ??
    latestAssistant?.metrics?.contextLimit ??
    state.lastContextLimit ??
    verifiedClientContextLimit(effectiveModelName);
  const contextRemainingTokens = latestAssistant?.metrics?.contextRemainingTokens ?? null;
  const safeRemainingTokens = latestAssistant?.metrics?.safeRemainingTokens ?? null;
  const sessionInputTokens = latestAssistant?.metrics?.sessionInputTokens ?? null;
  const sessionOutputTokens = latestAssistant?.metrics?.sessionOutputTokens ?? null;
  const sessionTotalTokens = latestAssistant?.metrics?.sessionTotalTokens ?? null;
  const requestInputTokens = latestAssistant?.metrics?.requestInputTokens ?? null;
  const requestOutputTokens = latestAssistant?.metrics?.requestOutputTokens ?? null;
  const reservedOutputTokens = latestAssistant?.metrics?.reservedOutputTokens ?? null;
  const maxOutputTokens = latestAssistant?.metrics?.maxOutputTokens ?? null;
  const liveSessionOutputTokens =
    sessionOutputTokens === null ? null : sessionOutputTokens + streamedOutputTokens;
  const liveSessionTotalTokens =
    sessionTotalTokens === null ? null : sessionTotalTokens + streamedOutputTokens;
  const liveSafeRemainingTokens =
    contextLimit && liveContextUsedTokens !== null
      ? Math.max(
          0,
          contextLimit - liveContextUsedTokens - (reservedOutputTokens ?? maxOutputTokens ?? 0),
        )
      : safeRemainingTokens;
  const contextStatus = latestAssistant?.metrics?.contextStatus ?? null;
  const contextCompacted = latestAssistant?.metrics?.contextCompacted ?? false;
  const contextEpoch = latestAssistant?.metrics?.contextEpoch ?? null;
  const contextEpochReason = latestAssistant?.metrics?.contextEpochReason ?? null;
  const contextSourceUpdates = latestAssistant?.metrics?.contextSourceUpdates ?? [];
  const promptCacheStatus = latestAssistant?.metrics?.promptCacheStatus ?? null;
  const systemContextTokens = latestAssistant?.metrics?.systemContextTokens ?? null;
  const toolSchemaTokens = latestAssistant?.metrics?.toolSchemaTokens ?? null;
  const toolResultTokens = latestAssistant?.metrics?.toolResultTokens ?? null;
  const adaptiveHistoryBudgetTokens = latestAssistant?.metrics?.adaptiveHistoryBudgetTokens ?? null;
  const adaptiveToolResultBudgetTokens =
    latestAssistant?.metrics?.adaptiveToolResultBudgetTokens ?? null;
  const cachedInputTokens = latestAssistant?.metrics?.cachedInputTokens ?? null;
  const uncachedInputTokens = latestAssistant?.metrics?.uncachedInputTokens ?? null;
  const providerUsage = latestAssistant?.metrics?.providerUsage ?? null;
  const tokenCategorySource = latestAssistant?.metrics?.tokenCategorySource ?? null;

  const handlePromptSelect = useCallback(
    (prompt: string) => {
      setQuery(prompt);
      void submitQuery(prompt);
    },
    [submitQuery],
  );

  useEffect(() => {
    scheduleScrollToBottom();
  }, [scheduleScrollToBottom, state.messages, state.isStreaming]);

  useEffect(() => {
    const container = scrollContainerRef.current;
    if (!container || typeof ResizeObserver === "undefined") return;

    const threadRoot = container.querySelector<HTMLElement>("[data-deepspace-thread-root]");
    if (!threadRoot) return;

    const observer = new ResizeObserver(() => {
      // A growing streamed answer should follow the bottom only while the
      // reader is already following it. Never pull the viewport back while
      // the user is inspecting an earlier thinking/tool step.
      if (autoFollowRef.current) scheduleScrollToBottom();
    });
    observer.observe(threadRoot);

    return () => observer.disconnect();
  }, [state.isStreaming, scheduleScrollToBottom]);

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

  // The thinking details panel is an independent scroll surface. Capture its
  // scroll events so the outer auto-follow loop does not pull the conversation
  // back to the bottom while the reader is inspecting internal activity.
  const handleScrollCapture = useCallback((e: React.UIEvent<HTMLDivElement>) => {
    const target = e.target as HTMLElement | null;
    if (
      target &&
      typeof target.closest === "function" &&
      target.closest("[data-thinking-scroll='true']")
    ) {
      autoFollowRef.current = false;
    }
  }, []);

  return (
    <div className="flex h-full min-h-0 w-full overflow-hidden bg-transparent">
      <div className="relative min-w-0 flex-1 overflow-hidden bg-transparent">
        <div className="flex h-full min-h-0 min-w-0 flex-col bg-transparent">
          <DeepSpaceScrollTracker
            messages={renderableMessages}
            scrollContainerRef={scrollContainerRef}
            onInsertActiveAnswer={onInsertLatestAnswer}
            disabled={isConversationSwitching}
          />

          <div
            ref={scrollContainerRef}
            onScroll={handleUserScroll}
            onScrollCapture={handleScrollCapture}
            aria-busy={isConversationSwitching}
            style={{ overflowAnchor: "none" }}
            className={`custom-scrollbar scrollbar-hide min-h-0 flex-1 overflow-y-auto pt-16 pr-12 pl-3 ${
              isMobileStacked ? "pb-24 sm:pr-12 sm:pl-4" : "sm:pr-12 sm:pl-4"
            }`}
          >
            {isConversationSwitching ? (
              <div
                className="sticky top-2 z-30 mx-auto mb-3 flex w-fit max-w-[min(36rem,100%)] items-center gap-3 rounded-xl border border-cyan-200/70 bg-white/95 px-4 py-2 text-sm text-slate-700 shadow-lg dark:border-cyan-900 dark:bg-slate-950/95 dark:text-slate-200"
                role={selectedConversationLoadFailed ? "alert" : "status"}
              >
                {selectedConversationLoadFailed ? (
                  <>
                    <span>Could not load this conversation. Your other chats are still saved.</span>
                    <button
                      type="button"
                      className="shrink-0 font-semibold text-cyan-800 underline underline-offset-2 dark:text-cyan-200"
                      onClick={() => {
                        if (activeConversationId) void loadConversation(activeConversationId);
                      }}
                    >
                      Try again
                    </button>
                  </>
                ) : (
                  <span>Loading selected conversation…</span>
                )}
              </div>
            ) : null}
            {operationalSummary && !isConversationSwitching && (
              <DeepSpaceOperationalSummary
                summary={operationalSummary}
                conversationId={activeConversationId ?? state.currentConversationId}
              />
            )}
            <div
              aria-hidden={isConversationSwitching}
              inert={isConversationSwitching}
              className={`transition-opacity duration-200 ${isConversationSwitching ? "pointer-events-none opacity-45" : "opacity-100"}`}
            >
              <DeepSpaceThread
                messages={renderableMessages}
                emptyPrompts={EMPTY_PROMPTS}
                userName={user?.email}
                queuedAssistantId={activeRequestIsQueued ? state.activeAssistantId : null}
                retryableRequestIds={retryableFailedRequestIds}
                retryingRequestId={retryingFailedRequestId}
                retryActionDisabled={queueAction !== null}
                scrollMetrics={threadScrollMetrics}
                onPromptSelect={handlePromptSelect}
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
                onResolveApproval={resolveMCPApproval}
                onSubmitUserQuestion={submitUserQuestionAnswer}
                onRetryFailedTurn={retryFailedTurn}
              />
            </div>
          </div>

          <div
            aria-busy={isConversationSwitching}
            aria-hidden={isConversationSwitching}
            inert={isConversationSwitching}
            className={`flex w-full shrink-0 flex-col items-center transition-opacity duration-200 ${isConversationSwitching ? "pointer-events-none opacity-45" : "opacity-100"}`}
          >
            <DeepSpaceComposer
              conversationId={activeConversationId ?? state.currentConversationId}
              query={query}
              isStreaming={state.isStreaming && !pendingUserQuestion}
              showActiveResponseControls={showActiveResponseControls}
              modelName={effectiveModelName}
              selectedProviderId={selectedProviderOverride ?? selectedModel?.providerId}
              onQueryChange={setQuery}
              editingQueuedTurnId={editingQueuedTurn?.clientRequestId ?? null}
              onEditQueuedTurn={startQueuedTurnEdit}
              onCancelQueueEdit={cancelQueuedTurnEdit}
              onSaveQueueEdit={saveQueuedTurnEdit}
              onSubmit={(attachmentFileIds) =>
                void submitQuery(undefined, undefined, attachmentFileIds)
              }
              onStop={stopStreaming}
              onSteer={() => void enqueueTurn(query, true)}
              queuedTurns={visibleQueuedTurns}
              queuePaused={queueState.paused}
              queuePauseReason={queueState.reason}
              queueFailedRequestId={queueState.failedRequestId}
              queueAction={queueAction}
              onPauseQueue={() => void pauseQueue()}
              onResumeQueue={() => void resumeQueue()}
              onClearQueue={() => void clearQueue()}
              onCancelQueuedTurn={(requestId) => void cancelQueuedTurn(requestId)}
              onRetryFailedTurn={(requestId) => void retryFailedTurn(requestId)}
              onSteerQueuedTurn={(requestId) => void steerQueuedTurn(requestId)}
              changedFiles={changedFiles}
              availableModels={availableModels}
              onModelSelect={handleModelSelect}
              reasoningEffort={activeReasoningEffort}
              onReasoningEffortChange={setReasoningEffort}
              voiceState={voiceState}
              contextUsedTokens={liveContextUsedTokens}
              contextLimit={contextLimit}
              contextRemainingTokens={contextRemainingTokens}
              safeRemainingTokens={liveSafeRemainingTokens}
              sessionInputTokens={sessionInputTokens}
              sessionOutputTokens={liveSessionOutputTokens}
              sessionTotalTokens={liveSessionTotalTokens}
              requestInputTokens={requestInputTokens}
              requestOutputTokens={
                requestOutputTokens === null
                  ? state.isStreaming
                    ? streamedOutputTokens
                    : null
                  : requestOutputTokens + (state.isStreaming ? streamedOutputTokens : 0)
              }
              reservedOutputTokens={reservedOutputTokens}
              maxOutputTokens={maxOutputTokens}
              contextStatus={contextStatus}
              contextCompacted={contextCompacted}
              contextEpoch={contextEpoch}
              contextEpochReason={contextEpochReason}
              contextSourceUpdates={contextSourceUpdates}
              userVisibleInputTokens={userVisibleInputTokens + draftTokens}
              userVisibleOutputTokens={userVisibleOutputTokens + streamedOutputTokens}
              conversationVisibleTokens={
                conversationVisibleTokens + draftTokens + streamedOutputTokens
              }
              promptCacheMode={latestAssistant?.metrics?.promptCacheMode ?? null}
              promptCacheEligible={latestAssistant?.metrics?.promptCacheEligible ?? false}
              promptCacheStatus={promptCacheStatus}
              systemContextTokens={systemContextTokens}
              toolSchemaTokens={toolSchemaTokens}
              toolResultTokens={toolResultTokens}
              adaptiveHistoryBudgetTokens={adaptiveHistoryBudgetTokens}
              adaptiveToolResultBudgetTokens={adaptiveToolResultBudgetTokens}
              cachedInputTokens={cachedInputTokens}
              uncachedInputTokens={uncachedInputTokens}
              providerUsage={providerUsage}
              tokenCategorySource={tokenCategorySource}
              sttActive={sttActive}
              ttsActive={ttsActive}
              onSttToggle={handleSttToggle}
              onTtsToggle={handleTtsToggle}
              voiceLabel={voiceLabel}
              runtimePhase={runtimeActivity.phase}
              activeToolName={runtimeActivity.activeToolName}
              hasRuntimeError={runtimeActivity.hasError}
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
              className="fixed top-4 right-4 bottom-4 z-[110] flex w-[280px] overflow-hidden rounded-[2rem] border border-white/10 bg-black/72 shadow-2xl backdrop-blur-2xl sm:w-[320px]"
            >
              <ChatSidebar
                endpointBase="/deepspace/chats"
                enableArchived
                enableRetentionControls
                isTenantAdmin={hasAdminRole(user?.roles)}
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
              ></ChatSidebar>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}
