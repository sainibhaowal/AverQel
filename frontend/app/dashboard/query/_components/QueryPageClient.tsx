"use client";

import { useCallback, useEffect, useMemo, useReducer, useRef, useState, type ReactNode } from "react";
import { AlertCircle, History, Settings2, Check, ChevronDown, X, Sparkles, Brain, Hash, Compass, Folder } from "lucide-react";
import { useSearchParams } from "next/navigation";
import toast from "react-hot-toast";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "framer-motion";

import ChatSidebar from "@/app/components/dashboard/ChatSidebar";
import PDFPreviewModal from "@/app/components/query/PDFPreviewModal";
import ConfirmationModal from "@/app/components/ui/ConfirmationModal";
import { fetchWithAuth } from "@/lib/api";
import {
  listProviders,
  listProviderModels,
  listAssignments,
  createAssignment,
  updateAssignment,
} from "@/lib/providers-api";

import { useQueryStream } from "../_hooks/useQueryStream";
import { initialQueryThreadState, queryThreadReducer } from "../_lib/query-thread-reducer";
import { resolveLatestEditableMessageId } from "../_lib/edit-target";
import { estimateTokens, type QueryHistoryMessage } from "../_lib/stream-protocol";

import MessageThread from "./MessageThread";
import QueryComposer from "./QueryComposer";
import DeepSpaceScrollTracker from "./DeepSpaceScrollTracker";

const DEFAULT_QUERY_TOP_K = 5;

interface DashboardOverview {
  stats?: Record<string, number>;
  document_breakdown?: Record<string, number>;
  provider_runtimes?: Array<Record<string, unknown>>;
}

function IconTooltipButton({
  label,
  active,
  icon,
  onClick,
}: {
  label: string;
  active: boolean;
  icon: ReactNode;
  onClick: () => void;
}) {
  const [open, setOpen] = useState(false);
  const pressTimerRef = useRef<number | null>(null);

  useEffect(
    () => () => {
      if (pressTimerRef.current) window.clearTimeout(pressTimerRef.current);
    },
    [],
  );

  const hide = () => {
    setOpen(false);
    if (pressTimerRef.current) {
      window.clearTimeout(pressTimerRef.current);
      pressTimerRef.current = null;
    }
  };

  return (
    <button
      type="button"
      aria-label={label}
      onClick={onClick}
      onPointerEnter={(event) => {
        if (event.pointerType === "mouse") setOpen(true);
      }}
      onPointerLeave={hide}
      onFocus={() => setOpen(true)}
      onBlur={hide}
      onPointerDown={(event) => {
        if (event.pointerType === "touch" || event.pointerType === "pen") {
          pressTimerRef.current = window.setTimeout(() => setOpen(true), 450);
        }
      }}
      onPointerUp={hide}
      onPointerCancel={hide}
      className={`group relative inline-flex h-8 w-8 sm:h-10 sm:w-10 items-center justify-center rounded-full transition-all ${
        active
          ? "bg-primary text-primary-foreground shadow-[0_0_15px_rgba(var(--primary),0.3)]"
          : "text-foreground/70 hover:bg-surface-2 hover:text-primary"
      }`}
    >
      {icon}
      <span
        className={`pointer-events-none absolute top-full left-1/2 z-40 mt-2 -translate-x-1/2 rounded-full border border-white/10 bg-black/85 px-3 py-1 text-[10px] font-semibold tracking-[0.22em] whitespace-nowrap text-white uppercase shadow-[0_12px_30px_rgba(0,0,0,0.35)] transition ${
          open ? "translate-y-0 opacity-100" : "translate-y-1 opacity-0"
        }`}
      >
        {label}
      </span>
    </button>
  );
}

interface CollectionScopeItem {
  id: string;
  name: string;
}

interface CollectionDocumentItem {
  document_id: string;
}

interface QueryPageClientProps {
  mode?: "query" | "deepspace";
  onInsertLatestAnswer?: (content: string) => void;
}

interface QueryRuntimeMetrics {
  contextLimit: number | null;
  contextLimitSource: string | null;
  modelName: string | null;
  providerType: string | null;
}

export default function QueryPageClient({
  mode = "query",
  onInsertLatestAnswer,
}: QueryPageClientProps) {
  const [state, dispatch] = useReducer(queryThreadReducer, initialQueryThreadState);
  const [query, setQuery] = useState("");
  const [searchMode, setSearchMode] = useState<"hybrid" | "semantic" | "keyword">("hybrid");
  const [supportsThinking, setSupportsThinking] = useState(false);
  const [thinkingEnabled, setThinkingEnabled] = useState(false);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [scopeMenuOpen, setScopeMenuOpen] = useState(false);
  const [collectionOptions, setCollectionOptions] = useState<CollectionScopeItem[]>([]);
  const [selectedCollectionId, setSelectedCollectionId] = useState("");
  const [selectedCollectionDocumentIds, setSelectedCollectionDocumentIds] = useState<
    string[] | null
  >(null);
  const [collectionScopeLoading, setCollectionScopeLoading] = useState(false);
  const [selectedCitationDocument, setSelectedCitationDocument] = useState<{
    id: string;
    name: string;
    page?: number;
  } | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    setMounted(true);
  }, []);
  const [deleteAssistantMessageId, setDeleteAssistantMessageId] = useState<string | null>(null);
  const [deleteAssistantBusy, setDeleteAssistantBusy] = useState(false);
  const [runtimeMetrics, setRuntimeMetrics] = useState<QueryRuntimeMetrics>({
    contextLimit: null,
    contextLimitSource: null,
    modelName: null,
    providerType: null,
  });

  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const scrollContainerRef = useRef<HTMLDivElement | null>(null);
  const autoFollowRef = useRef(true);
  const scrollRafRef = useRef<number | null>(null);
  const streamingRef = useRef(state.isStreaming);
  const pendingHistorySyncRef = useRef(false);
  const searchParams = useSearchParams();
  const docId = searchParams.get("docId");
  const selectedCollectionName = useMemo(
    () => collectionOptions.find((item) => item.id === selectedCollectionId)?.name ?? null,
    [collectionOptions, selectedCollectionId],
  );
  const isEmbedded = mode === "deepspace";
  const chatEndpointBase = isEmbedded ? "/deepspace/chats" : "/chats";
  const streamEndpoint = isEmbedded ? "/deepspace/chats/stream" : "/queries/stream";
  const conversationKind = isEmbedded ? "deepspace" : "query";

  const stream = useQueryStream(
    useMemo(
      () => ({
        onEvent: (event) => dispatch({ type: "stream_event", event }),
        onTransportError: (error) => dispatch({ type: "stream_failed", error }),
        onUserCancel: () => dispatch({ type: "stream_interrupted" }),
        onFinally: () => dispatch({ type: "stream_finished" }),
      }),
      [dispatch],
    ),
  );

  const scrollAnchor = useMemo(() => {
    const lastMessage = state.messages[state.messages.length - 1];
    if (!lastMessage) {
      return "empty";
    }
    const activeVersion = lastMessage.versions.find(
      (version) => version.id === lastMessage.activeVersionId,
    );
    return [
      lastMessage.id,
      lastMessage.content.length,
      lastMessage.blocks.length,
      lastMessage.status,
      activeVersion?.rawContent?.length ?? lastMessage.rawContent?.length ?? 0,
      state.isStreaming ? "streaming" : "idle",
    ].join(":");
  }, [state.isStreaming, state.messages]);

  const totalUsedTokens = useMemo(() => {
    const historyTokens = state.messages.reduce((acc, msg) => {
      return (
        acc +
        estimateTokens(msg.content) +
        (msg.thinkingContent ? estimateTokens(msg.thinkingContent) : 0)
      );
    }, 0);
    return historyTokens + estimateTokens(query);
  }, [state.messages, query]);

  const totalContext = runtimeMetrics.contextLimit;

  useEffect(() => {
    let cancelled = false;
    const loadRuntime = async () => {
      try {
        const response = (await fetchWithAuth("/deepspace/chats/runtime")) as Response;
        if (!response.ok) return;
        const runtime = (await response.json()) as {
          context_limit?: number | null;
          context_limit_source?: string | null;
          model_name?: string | null;
          provider_type?: string | null;
        };
        if (cancelled) return;
        setRuntimeMetrics({
          contextLimit:
            typeof runtime.context_limit === "number" && runtime.context_limit > 0
              ? runtime.context_limit
              : null,
          contextLimitSource:
            typeof runtime.context_limit_source === "string" ? runtime.context_limit_source : null,
          modelName:
            typeof runtime.model_name === "string" && runtime.model_name.trim()
              ? runtime.model_name
              : null,
          providerType:
            typeof runtime.provider_type === "string" && runtime.provider_type.trim()
              ? runtime.provider_type
              : null,
        });
      } catch (error) {
        console.error("Failed to fetch embedded runtime", error);
      }
    };
    void loadRuntime();
    return () => {
      cancelled = true;
    };
  }, []);

  const [availableModels, setAvailableModels] = useState<
    Array<{ providerId: string; modelName: string; displayName: string }>
  >([]);

  useEffect(() => {
    let active = true;
    const fetchModels = async () => {
      try {
        const [providersList] = await Promise.all([
          listProviders(),
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
        console.error("Failed to load models", err);
      }
    };

    void fetchModels();
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

      const response = await fetchWithAuth("/deepspace/chats/runtime");
      if (response && response.ok) {
        const runtime = await response.json();
        setRuntimeMetrics({
          contextLimit:
            typeof runtime.context_limit === "number" && runtime.context_limit > 0
              ? runtime.context_limit
              : null,
          contextLimitSource:
            typeof runtime.context_limit_source === "string" ? runtime.context_limit_source : null,
          modelName:
            typeof runtime.model_name === "string" && runtime.model_name.trim()
              ? runtime.model_name
              : null,
          providerType:
            typeof runtime.provider_type === "string" && runtime.provider_type.trim()
              ? runtime.provider_type
              : null,
        });
      }
    } catch (err) {
      console.error("Failed to switch model", err);
      toast.error("Failed to switch model", { id: toastId });
    }
  }, []);

  const isNearBottom = useCallback((element: HTMLDivElement) => {
    const remaining = element.scrollHeight - element.scrollTop - element.clientHeight;
    return remaining <= 120;
  }, []);

  const cancelAutoFollow = useCallback(() => {
    if (scrollRafRef.current !== null) {
      window.cancelAnimationFrame(scrollRafRef.current);
      scrollRafRef.current = null;
    }
  }, []);

  const stepAutoFollow = useCallback(() => {
    const container = scrollContainerRef.current;
    if (!container || !autoFollowRef.current) {
      cancelAutoFollow();
      return;
    }

    const target = Math.max(0, container.scrollHeight - container.clientHeight);
    const delta = target - container.scrollTop;
    const isStreaming = streamingRef.current;
    const ease = isStreaming ? 0.22 : 0.16;
    const snapThreshold = isStreaming ? 1 : 2;

    if (Math.abs(delta) <= snapThreshold) {
      container.scrollTop = target;
      cancelAutoFollow();
      return;
    }

    container.scrollTop += delta * ease;
    scrollRafRef.current = window.requestAnimationFrame(stepAutoFollow);
  }, [cancelAutoFollow]);

  useEffect(() => {
    streamingRef.current = state.isStreaming;
  }, [state.isStreaming]);

  useEffect(() => {
    const container = scrollContainerRef.current;
    if (!container || !autoFollowRef.current) {
      return;
    }

    if (!state.isStreaming) {
      container.scrollTop = Math.max(0, container.scrollHeight - container.clientHeight);
      cancelAutoFollow();
      return;
    }

    if (scrollRafRef.current === null) {
      scrollRafRef.current = window.requestAnimationFrame(stepAutoFollow);
    }

    return () => {
      if (!state.isStreaming) {
        cancelAutoFollow();
      }
    };
  }, [cancelAutoFollow, scrollAnchor, state.activeAssistantId, state.isStreaming, stepAutoFollow]);

  const loadConversation = useCallback(
    async (conversationId: string) => {
      const response = (await fetchWithAuth(
        `${chatEndpointBase}/${conversationId}/messages`,
      )) as Response;
      if (!response.ok) {
        if (response.status === 404) {
          dispatch({ type: "reset_thread" });
        }
        return;
      }
      const payload = (await response.json()) as { messages: QueryHistoryMessage[] };
      dispatch({ type: "load_history", conversationId, messages: payload.messages });
    },
    [chatEndpointBase],
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

  useEffect(() => {
    let active = true;
    const loadCapabilities = async () => {
      const response = (await fetchWithAuth("/queries/capabilities/chat")) as Response;
      if (!response.ok || !active) {
        return;
      }
      const payload = (await response.json()) as {
        context_limit?: number | null;
        context_limit_source?: string | null;
        model_name?: string | null;
        provider_type?: string | null;
        supports_thinking?: boolean;
        supports_thinking_toggle?: boolean;
      };
      const supported = Boolean(payload.supports_thinking_toggle ?? payload.supports_thinking);
      setSupportsThinking(supported);
      setThinkingEnabled(supported);
      if (
        typeof payload.context_limit === "number" &&
        payload.context_limit > 0 &&
        typeof payload.model_name === "string" &&
        payload.model_name.trim()
      ) {
        setRuntimeMetrics({
          contextLimit: payload.context_limit,
          contextLimitSource:
            typeof payload.context_limit_source === "string" ? payload.context_limit_source : null,
          modelName: payload.model_name,
          providerType:
            typeof payload.provider_type === "string" && payload.provider_type.trim()
              ? payload.provider_type
              : null,
        });
      }
      if (!supported) {
        setThinkingEnabled(false);
      }
    };
    void loadCapabilities();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    const loadCollections = async () => {
      try {
        const response = (await fetchWithAuth("/collections")) as Response;
        if (!response.ok || !active) {
          return;
        }
        const payload = (await response.json()) as Array<{ id: string; name: string }>;
        if (!active) {
          return;
        }
        setCollectionOptions(payload.map((item) => ({ id: item.id, name: item.name })));
      } catch (error) {
        console.error("Failed to load collection query scope", error);
      }
    };
    void loadCollections();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    if (!selectedCollectionId) {
      setSelectedCollectionDocumentIds(null);
      setCollectionScopeLoading(false);
      return;
    }

    const loadCollectionDocuments = async () => {
      setCollectionScopeLoading(true);
      try {
        const response = (await fetchWithAuth(
          `/collections/${selectedCollectionId}/documents`,
        )) as Response;
        if (!response.ok) {
          throw new Error("Failed to load collection documents.");
        }
        const payload = (await response.json()) as CollectionDocumentItem[];
        if (!active) {
          return;
        }
        setSelectedCollectionDocumentIds(payload.map((item) => item.document_id));
      } catch (error) {
        console.error(error);
        if (active) {
          setSelectedCollectionDocumentIds([]);
          toast.error("Failed to load shared collection documents for query scope.");
        }
      } finally {
        if (active) {
          setCollectionScopeLoading(false);
        }
      }
    };

    void loadCollectionDocuments();
    return () => {
      active = false;
    };
  }, [selectedCollectionId]);

  const [dashboardOverview, setDashboardOverview] = useState<DashboardOverview | null>(null);

  useEffect(() => {
    let active = true;
    const loadOverview = async () => {
      try {
        const response = (await fetchWithAuth("/dashboard/overview")) as Response;
        if (response && response.ok && active) {
          const data = (await response.json()) as DashboardOverview;
          setDashboardOverview(data);
        }
      } catch (err) {
        console.error("Failed to load dashboard overview stats", err);
      }
    };
    void loadOverview();
    const interval = setInterval(loadOverview, 20000);
    return () => {
      active = false;
      clearInterval(interval);
    };
  }, []);

  const realTimeStats = useMemo(() => {
    if (!dashboardOverview) return null;
    const stats = dashboardOverview.stats || {};
    const breakdown = dashboardOverview.document_breakdown || {};
    const runtimes = dashboardOverview.provider_runtimes || [];

    const totalDocs =
      (breakdown.indexed || 0) +
      (breakdown.failed || 0) +
      (breakdown.processing || 0) +
      (breakdown.queued || 0);
    const indexHealth = totalDocs > 0 ? ((breakdown.indexed || 0) / totalDocs) * 100 : 100;

    const embeddingRuntime = runtimes.find((r) => r.feature_scope === "embeddings");
    const chatRuntime = runtimes.find((r) => r.feature_scope === "chat");
    const latencyMs = Number(embeddingRuntime?.latency_ms || chatRuntime?.latency_ms || 32);

    return {
      totalDocuments: stats.total_documents || 0,
      totalQueries: stats.total_queries || 0,
      activeJobs: stats.active_jobs || 0,
      storageBytes: stats.storage_used_bytes || 0,
      indexHealth,
      latencyMs,
    };
  }, [dashboardOverview]);

  const scopedDocumentIds = useMemo(() => {
    if (docId) {
      if (selectedCollectionDocumentIds) {
        return selectedCollectionDocumentIds.includes(docId) ? [docId] : [];
      }
      return [docId];
    }
    return selectedCollectionDocumentIds;
  }, [docId, selectedCollectionDocumentIds]);

  const emptyPrompts = useMemo(() => {
    if (isEmbedded) {
      return [
        "Help me think through this idea clearly.",
        "Draft a concise message I can send to my team.",
        "Turn these rough thoughts into a cleaner note.",
        "Explain this topic simply, then improve the wording.",
      ];
    }

    if (selectedCollectionName) {
      return [
        `What are the most important findings in ${selectedCollectionName}?`,
        `Compare the documents in ${selectedCollectionName} and show the differences that matter.`,
        `Which files in ${selectedCollectionName} support the strongest answer for this topic?`,
        `Answer only from ${selectedCollectionName} and cite the supporting evidence.`,
      ];
    }

    if (docId) {
      return [
        "Summarize the selected document with grounded citations.",
        "What are the key claims, risks, and action points in this document?",
        "Show the strongest evidence from this document only.",
        "Turn this document into a short evidence-based brief.",
      ];
    }

    return [
      "What are the most important findings across my indexed documents?",
      "Compare related documents and highlight the differences that actually matter.",
      "Which files contain the strongest evidence for this topic?",
      "Answer only from grounded evidence and show the supporting citations.",
    ];
  }, [docId, isEmbedded, selectedCollectionName]);

  const submitQuery = useCallback(
    async (nextQuery?: string) => {
      const effectiveQuery = (nextQuery ?? query).trim();
      if (!effectiveQuery || state.isStreaming) {
        return;
      }

      setQuery("");
      autoFollowRef.current = true;
      dispatch({ type: "submit_query", query: effectiveQuery });
      pendingHistorySyncRef.current = true;

      await stream.start({
        endpoint: streamEndpoint,
        body: {
          query: effectiveQuery,
          top_k: DEFAULT_QUERY_TOP_K,
          conversation_id: state.currentConversationId,
          conversation_kind: conversationKind,
          search_mode: searchMode,
          thinking_enabled: supportsThinking && thinkingEnabled,
          filters: scopedDocumentIds ? { document_ids: scopedDocumentIds } : {},
        },
      });
    },
    [
      query,
      searchMode,
      scopedDocumentIds,
      state.currentConversationId,
      state.isStreaming,
      stream,
      streamEndpoint,
      supportsThinking,
      thinkingEnabled,
      conversationKind,
    ],
  );

  const startNewChat = useCallback(() => {
    stream.cancel();
    setQuery("");
    autoFollowRef.current = true;
    dispatch({ type: "reset_thread" });
  }, [stream]);

  const stopStreaming = useCallback(() => {
    stream.cancel();
  }, [stream]);

  const regenerateMessage = useCallback(
    async (assistantMessageId: string) => {
      if (!state.currentConversationId || state.isStreaming) {
        return;
      }
      autoFollowRef.current = true;
      dispatch({ type: "start_regenerate", assistantMessageId });
      pendingHistorySyncRef.current = true;
      await stream.start({
        endpoint: `${chatEndpointBase}/${state.currentConversationId}/messages/${assistantMessageId}/regenerate/stream`,
        body: {
          top_k: DEFAULT_QUERY_TOP_K,
          search_mode: searchMode,
          document_id: scopedDocumentIds?.length === 1 ? scopedDocumentIds[0] : docId,
          filters: scopedDocumentIds ? { document_ids: scopedDocumentIds } : {},
          thinking_enabled: supportsThinking && thinkingEnabled,
        },
      });
    },
    [
      chatEndpointBase,
      docId,
      searchMode,
      scopedDocumentIds,
      state.currentConversationId,
      state.isStreaming,
      stream,
      supportsThinking,
      thinkingEnabled,
    ],
  );

  const saveEditedMessage = useCallback(
    async (messageId: string, content: string) => {
      if (!state.currentConversationId || state.isStreaming) {
        return;
      }
      const trimmed = content.trim();
      if (!trimmed) {
        return;
      }
      autoFollowRef.current = true;
      const userIndex = state.messages.findIndex((message) => message.id === messageId);
      const assistantMessageId =
        userIndex >= 0
          ? state.messages[userIndex + 1]?.role === "assistant"
            ? state.messages[userIndex + 1]?.id
            : null
          : null;
      dispatch({ type: "commit_user_edit", messageId, content: trimmed });
      if (assistantMessageId) {
        dispatch({ type: "start_regenerate", assistantMessageId });
      }
      pendingHistorySyncRef.current = true;

      const editableMessageId = await resolveLatestEditableMessageId({
        fetcher: fetchWithAuth,
        endpointBase: chatEndpointBase,
        conversationId: state.currentConversationId,
        fallbackMessageId: messageId,
      });

      await stream.start({
        endpoint: `${chatEndpointBase}/${state.currentConversationId}/messages/${editableMessageId}/edit-and-regenerate/stream`,
        body: {
          content: trimmed,
          top_k: DEFAULT_QUERY_TOP_K,
          search_mode: searchMode,
          document_id: scopedDocumentIds?.length === 1 ? scopedDocumentIds[0] : docId,
          filters: scopedDocumentIds ? { document_ids: scopedDocumentIds } : {},
          thinking_enabled: supportsThinking && thinkingEnabled,
        },
      });
    },
    [
      chatEndpointBase,
      docId,
      searchMode,
      scopedDocumentIds,
      state.currentConversationId,
      state.isStreaming,
      state.messages,
      stream,
      supportsThinking,
      thinkingEnabled,
    ],
  );

  const activateVersion = useCallback(
    async (messageId: string, versionId: string) => {
      if (!state.currentConversationId) {
        return;
      }
      dispatch({ type: "activate_version", messageId, versionId });
      const response = (await fetchWithAuth(
        `${chatEndpointBase}/${state.currentConversationId}/messages/${messageId}/versions/${versionId}/activate`,
        { method: "PATCH" },
      )) as Response;
      if (!response.ok) {
        void loadConversation(state.currentConversationId);
      }
    },
    [chatEndpointBase, loadConversation, state.currentConversationId],
  );

  const deleteAssistantMessage = useCallback(
    async (messageId: string) => {
      if (!state.currentConversationId || state.isStreaming) {
        return;
      }
      setDeleteAssistantMessageId(messageId);
    },
    [state.currentConversationId, state.isStreaming],
  );

  const confirmDeleteAssistantMessage = useCallback(async () => {
    if (!state.currentConversationId || !deleteAssistantMessageId || deleteAssistantBusy) {
      return;
    }

    setDeleteAssistantBusy(true);
    try {
      const response = (await fetchWithAuth(
        `${chatEndpointBase}/${state.currentConversationId}/messages/${deleteAssistantMessageId}`,
        { method: "DELETE" },
      )) as Response;
      if (!response.ok) {
        return;
      }
      dispatch({ type: "delete_message_local", messageId: deleteAssistantMessageId });
      setDeleteAssistantMessageId(null);
    } catch (error) {
      console.error("Delete assistant message failed", error);
    } finally {
      setDeleteAssistantBusy(false);
    }
  }, [
    chatEndpointBase,
    deleteAssistantBusy,
    deleteAssistantMessageId,
    state.currentConversationId,
    dispatch,
  ]);
  const activeError = state.streamError;
  return (
    <div className="flex h-full min-h-0 w-full overflow-hidden bg-transparent">
      {(() => {
        const portalTarget =
          typeof document !== "undefined"
            ? document.getElementById("header-layout-controls")
            : null;
        const shouldRenderPortal = !isEmbedded && mounted && portalTarget;

        if (shouldRenderPortal) {
          return createPortal(
            <div className="border-glass-border bg-surface-0/90 pointer-events-auto flex items-center gap-0.5 sm:gap-1 rounded-full border p-0.5 sm:p-1 shadow-xl backdrop-blur-md">
              <IconTooltipButton
                label="Controls"
                active={filtersOpen}
                icon={<Settings2 size={16} />}
                onClick={() => setFiltersOpen(!filtersOpen)}
              />
              <IconTooltipButton
                label="History"
                active={historyOpen}
                icon={<History size={16} />}
                onClick={() => setHistoryOpen(!historyOpen)}
              />
            </div>,
            portalTarget,
          );
        }
        return null;
      })()}
      <div className="relative min-w-0 flex-1 overflow-hidden">
        <div className="flex h-full min-h-0 min-w-0 flex-col">
          {isEmbedded ? (
            <>
              <button
                type="button"
                aria-label="Open conversation history"
                title="Open conversation history"
                onClick={() => setHistoryOpen(true)}
                className={`border-primary/25 bg-surface-0/80 text-foreground hover:border-primary/40 hover:bg-surface-1 absolute top-4 right-4 z-20 inline-flex h-11 items-center gap-2 rounded-full border px-4 shadow-xl backdrop-blur-md transition ${
                  historyOpen ? "pointer-events-none opacity-0" : ""
                }`}
              >
                <History size={17} className="text-primary" />
                <span className="text-sm font-medium">History</span>
              </button>
              <DeepSpaceScrollTracker
                messages={state.messages}
                scrollContainerRef={scrollContainerRef}
                onInsertActiveAnswer={onInsertLatestAnswer}
              />
            </>
          ) : null}
          <div
            ref={scrollContainerRef}
            onScroll={(event) => {
              autoFollowRef.current = isNearBottom(event.currentTarget);
              if (!autoFollowRef.current) {
                cancelAutoFollow();
              }
            }}
            className={`custom-scrollbar scrollbar-hide min-h-0 flex-1 overflow-y-auto ${isEmbedded ? "pt-16 pr-12 pl-4" : "pr-12 pl-6"}`}
          >
            {activeError ? (
              <div className="border-danger/20 bg-danger/5 text-danger mx-auto mt-6 flex max-w-5xl items-start gap-3 rounded-2xl border px-4 py-3 text-sm">
                <AlertCircle size={16} className="mt-0.5 shrink-0" />
                <div>
                  <div className="font-semibold">{activeError.message}</div>
                  <div className="text-muted-foreground mt-1 text-xs">{activeError.code}</div>
                </div>
              </div>
            ) : null}

            <MessageThread
              mode={mode}
              messages={state.messages}
              emptyPrompts={emptyPrompts}
              activeAssistantId={state.activeAssistantId}
              onRegenerate={regenerateMessage}
              onStartEdit={(messageId) => dispatch({ type: "start_edit", messageId })}
              onCancelEdit={(messageId) => dispatch({ type: "cancel_edit", messageId })}
              onEditDraftChange={(messageId, value) =>
                dispatch({ type: "update_edit_draft", messageId, value })
              }
              onSaveEdit={saveEditedMessage}
              onActivateVersion={activateVersion}
              onDeleteAssistant={deleteAssistantMessage}
              onPreviewDocument={setSelectedCitationDocument}
              onFollowupSelect={(suggestion) => {
                setQuery(suggestion);
                void submitQuery(suggestion);
              }}
              realTimeStats={realTimeStats}
            />
            <div ref={messagesEndRef} />
          </div>

          <div className="shrink-0">
            <QueryComposer
              mode={mode}
              query={query}
              searchMode={searchMode}
              selectedCollectionId={selectedCollectionId}
              collectionOptions={collectionOptions}
              collectionScopeLoading={collectionScopeLoading}
              isStreaming={state.isStreaming}
              filtersOpen={filtersOpen}
              supportsThinking={supportsThinking}
              thinkingEnabled={thinkingEnabled}
              onQueryChange={setQuery}
              onSearchModeChange={setSearchMode}
              onCollectionChange={setSelectedCollectionId}
              onToggleFilters={() => setFiltersOpen((value) => !value)}
              onThinkingChange={setThinkingEnabled}
              onSubmit={() => void submitQuery()}
              onStop={stopStreaming}
              usedTokens={totalUsedTokens}
              totalContext={totalContext}
              modelName={state.lastModelName ?? runtimeMetrics.modelName}
              availableModels={availableModels}
              onModelSelect={handleModelSelect}
            />
          </div>
        </div>
      </div>

      <AnimatePresence>
        {filtersOpen && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 z-40 bg-black/35 backdrop-blur-[1.5px]"
              onClick={() => setFiltersOpen(false)}
            />
            <motion.aside
              initial={{ x: 420, opacity: 0 }}
              animate={{ x: 0, opacity: 1 }}
              exit={{ x: 420, opacity: 0 }}
              transition={{ type: "spring", damping: 25, stiffness: 200 }}
              className="fixed top-4 right-4 bottom-4 z-50 flex w-[320px] sm:w-[400px] flex-col rounded-[2.5rem] border border-white/10 bg-black/85 p-6 shadow-[0_25px_60px_-15px_rgba(0,0,0,0.7)] backdrop-blur-3xl overflow-y-auto"
            >
              <div className="flex items-center justify-between border-b border-white/10 pb-4 mb-6">
                <div className="flex items-center gap-2.5">
                  <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-primary/10 text-primary border border-primary/20 shadow-[0_0_15px_rgba(var(--primary),0.15)]">
                    <Settings2 size={16} />
                  </div>
                  <div>
                    <h2 className="text-sm font-bold tracking-widest uppercase text-white">Search Engine</h2>
                    <p className="text-[10px] text-foreground/40 font-medium mt-0.5 uppercase tracking-wider">Configure Workspace RAG</p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setFiltersOpen(false)}
                  className="rounded-full p-2 text-foreground/40 hover:bg-white/10 hover:text-white transition-all active:scale-90"
                >
                  <X size={15} />
                </button>
              </div>

              <div className="space-y-6">
                {/* Search Strategy */}
                <div className="space-y-3">
                  <label className="text-foreground/40 block text-[10px] font-bold tracking-[0.2em] uppercase">
                    Search Strategy
                  </label>
                  <div className="grid grid-cols-1 gap-2.5">
                    {[
                      {
                        id: "hybrid" as const,
                        name: "Hybrid Engine",
                        desc: "Combines semantic context with keyword match rules.",
                        icon: <Sparkles size={14} className="text-primary" />,
                      },
                      {
                        id: "semantic" as const,
                        name: "Semantic Search",
                        desc: "Deep neural matching based on conceptual meaning.",
                        icon: <Brain size={14} className="text-purple-400" />,
                      },
                      {
                        id: "keyword" as const,
                        name: "Keyword Match",
                        desc: "Strict term-by-term matching for precise words.",
                        icon: <Hash size={14} className="text-amber-400" />,
                      },
                    ].map((mode) => {
                      const isActive = searchMode === mode.id;
                      return (
                        <button
                          key={mode.id}
                          type="button"
                          onClick={() => setSearchMode(mode.id)}
                          className={`w-full rounded-2xl border p-4 text-left transition-all duration-200 flex items-start gap-3 relative overflow-hidden group ${
                            isActive
                              ? "border-primary/40 bg-gradient-to-br from-primary/15 to-primary/5 text-foreground shadow-[0_4px_20px_rgba(var(--primary),0.08)]"
                              : "border-white/5 bg-white/[0.02] text-foreground/70 hover:bg-white/[0.05] hover:border-white/10"
                          }`}
                        >
                          <div className={`mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border transition-colors ${
                            isActive ? "border-primary/30 bg-primary/10 text-primary" : "border-white/10 bg-white/5"
                          }`}>
                            {mode.icon}
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center justify-between">
                              <span className="text-xs font-bold tracking-wide">{mode.name}</span>
                              {isActive && (
                                <span className="flex h-4 w-4 items-center justify-center rounded-full bg-primary/20 text-primary border border-primary/30 shadow-[0_0_10px_rgba(var(--primary),0.2)]">
                                  <Check size={10} className="stroke-[3]" />
                                </span>
                              )}
                            </div>
                            <p className="text-[10px] text-foreground/40 mt-1 leading-relaxed">{mode.desc}</p>
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </div>

                {/* Retrieval Depth */}
                <div className="space-y-3">
                  <label className="text-foreground/40 block text-[10px] font-bold tracking-[0.2em] uppercase">
                    Retrieval Depth
                  </label>
                  <div className="rounded-2xl border border-white/5 bg-gradient-to-br from-white/[0.03] to-transparent p-4 flex gap-3 items-start">
                    <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-white/10 bg-white/5 text-foreground/60">
                      <Compass size={14} className="text-foreground/50 animate-pulse" />
                    </div>
                    <div className="space-y-1">
                      <h4 className="text-xs font-bold text-foreground/80 uppercase tracking-wider">Adaptive Depth</h4>
                      <p className="text-[10px] text-foreground/45 leading-relaxed">
                        AVERQEL automatically calibrates retrieval parameters for each query, executing deep reranking to prioritize the strongest grounded evidence.
                      </p>
                    </div>
                  </div>
                </div>

                {/* Collection Scope */}
                <div className="space-y-3">
                  <label className="text-foreground/40 block text-[10px] font-bold tracking-[0.2em] uppercase">
                    Collection Scope
                  </label>
                  <div className="relative">
                    <button
                      type="button"
                      onClick={() => {
                        if (!state.isStreaming && !collectionScopeLoading) {
                          setScopeMenuOpen((current) => !current);
                        }
                      }}
                      disabled={state.isStreaming || collectionScopeLoading}
                      className="border-white/10 bg-white/[0.02] text-foreground hover:border-primary/40 hover:bg-primary/[0.04] flex w-full items-center justify-between rounded-2xl border p-4 text-left text-xs transition-all outline-none disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-white/10 bg-white/5 text-primary">
                          <Folder size={14} />
                        </div>
                        <div className="min-w-0">
                          <p className="truncate font-semibold text-xs text-foreground/90">
                            {collectionOptions.find((item) => item.id === selectedCollectionId)?.name ?? "All accessible documents"}
                          </p>
                          <p className="text-foreground/40 mt-0.5 text-[9px] tracking-[0.18em] uppercase">
                            {selectedCollectionId ? "Connected bridge scope" : "Workspace-wide scope"}
                          </p>
                        </div>
                      </div>
                      <ChevronDown
                        size={14}
                        className={`text-foreground/40 ml-3 shrink-0 transition-transform ${scopeMenuOpen ? "rotate-180" : ""}`}
                      />
                    </button>

                    <AnimatePresence>
                      {scopeMenuOpen && (
                        <motion.div
                          initial={{ opacity: 0, y: 8, scale: 0.98 }}
                          animate={{ opacity: 1, y: 0, scale: 1 }}
                          exit={{ opacity: 0, y: 6, scale: 0.98 }}
                          transition={{ duration: 0.16, ease: "easeOut" }}
                          className="border-white/10 bg-black/95 absolute left-0 right-0 z-30 mt-2 max-h-64 overflow-y-auto rounded-2xl border p-2 shadow-2xl backdrop-blur-xl"
                        >
                          <button
                            type="button"
                            onClick={() => {
                              setSelectedCollectionId("");
                              setScopeMenuOpen(false);
                            }}
                            className={`flex w-full items-center justify-between rounded-xl px-3 py-3 text-left text-xs transition-all ${
                              !selectedCollectionId
                                ? "bg-primary/15 text-primary font-bold shadow-sm"
                                : "text-foreground/78 hover:bg-white/5"
                            }`}
                          >
                            <div className="flex items-center gap-2.5">
                              <div className={`flex h-6 w-6 items-center justify-center rounded-md border ${
                                !selectedCollectionId ? "border-primary/30 bg-primary/10 text-primary" : "border-white/10 bg-white/5"
                              }`}>
                                <Folder size={12} />
                              </div>
                              <div>
                                <p className="font-semibold text-xs">All accessible documents</p>
                                <p className="text-foreground/42 mt-0.5 text-[9px] tracking-[0.18em] uppercase">
                                  Full workspace scope
                                </p>
                              </div>
                            </div>
                            {!selectedCollectionId ? (
                              <Check size={13} className="text-primary shrink-0 stroke-[3.5]" />
                            ) : null}
                          </button>

                          {collectionOptions.map((collection) => {
                            const selected = selectedCollectionId === collection.id;
                            return (
                              <button
                                key={collection.id}
                                type="button"
                                onClick={() => {
                                  setSelectedCollectionId(collection.id);
                                  setScopeMenuOpen(false);
                                }}
                                className={`mt-1 flex w-full items-center justify-between rounded-xl px-3 py-3 text-left text-xs transition-all ${
                                  selected
                                    ? "bg-primary/15 text-primary font-bold shadow-sm"
                                    : "text-foreground/78 hover:bg-white/5"
                                }`}
                              >
                                <div className="flex items-center gap-2.5">
                                  <div className={`flex h-6 w-6 items-center justify-center rounded-md border ${
                                    selected ? "border-primary/30 bg-primary/10 text-primary" : "border-white/10 bg-white/5"
                                  }`}>
                                    <Folder size={12} />
                                  </div>
                                  <div>
                                    <p className="font-semibold text-xs">{collection.name}</p>
                                    <p className="text-foreground/42 mt-0.5 text-[9px] tracking-[0.18em] uppercase">
                                      Shared bridge collection
                                    </p>
                                  </div>
                                </div>
                                {selected ? (
                                  <Check size={13} className="text-primary ml-3 shrink-0 stroke-[3.5]" />
                                ) : null}
                              </button>
                            );
                          })}
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </div>
                  <p className="text-foreground/40 mt-2.5 text-[10px] leading-relaxed">
                    Narrow search boundaries to a specific connection bridge when focusing queries on isolated data silos.
                  </p>
                </div>
              </div>
            </motion.aside>
          </>
        )}
        {historyOpen && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 z-40 bg-black/35 backdrop-blur-[1.5px]"
              onClick={() => setHistoryOpen(false)}
            />
            <motion.aside
              initial={{ x: 420, opacity: 0 }}
              animate={{ x: 0, opacity: 1 }}
              exit={{ x: 420, opacity: 0 }}
              transition={{ type: "spring", damping: 25, stiffness: 200 }}
              className="fixed top-4 right-4 bottom-4 z-50 flex w-[280px] sm:w-[320px] overflow-hidden rounded-[2rem] border border-white/10 bg-black/72 shadow-2xl backdrop-blur-2xl"
            >
              <ChatSidebar
                endpointBase={chatEndpointBase}
                variant="floating"
                currentConversationId={state.currentConversationId}
                onSelectConversation={(id) => {
                  void loadConversation(id);
                  setHistoryOpen(false);
                }}
                onNewChat={() => {
                  startNewChat();
                  setHistoryOpen(false);
                }}
                onClose={() => setHistoryOpen(false)}
              />
            </motion.aside>
          </>
        )}
      </AnimatePresence>
      <ConfirmationModal
        isOpen={deleteAssistantMessageId !== null}
        onClose={() => {
          if (deleteAssistantBusy) return;
          setDeleteAssistantMessageId(null);
        }}
        onConfirm={() => void confirmDeleteAssistantMessage()}
        title="Delete AI output?"
        message="This removes the saved answer and all of its generations from the current conversation."
        confirmLabel="Delete Output"
        loading={deleteAssistantBusy}
      />
      {selectedCitationDocument ? (
        <PDFPreviewModal
          isOpen={Boolean(selectedCitationDocument)}
          documentId={selectedCitationDocument.id}
          documentName={selectedCitationDocument.name}
          pageNumber={selectedCitationDocument.page}
          onClose={() => setSelectedCitationDocument(null)}
        />
      ) : null}
    </div>
  );
}
