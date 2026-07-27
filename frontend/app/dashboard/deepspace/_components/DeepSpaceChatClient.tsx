"use client";

/* LiveKit's browser event surface is intentionally dynamic; its event payloads
 * are validated by the runtime before entering the DeepSpace reducer. */
/* eslint-disable @typescript-eslint/no-explicit-any */

import { AnimatePresence, motion } from "framer-motion";
import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import { AlertCircle } from "lucide-react";
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
import type { DeepSpaceHistoryMessage } from "../_lib/deepspace-stream";
import { resolveLatestEditableMessageId } from "../_lib/edit-target";

import DeepSpaceComposer, { type DeepSpaceRuntimePhase } from "./DeepSpaceComposer";
import DeepSpaceThread from "./DeepSpaceThread";
import DeepSpaceScrollTracker from "./DeepSpaceScrollTracker";
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
  onSelectNote?: (noteId: string) => void;
  onNewNote?: () => void;
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

const EMPTY_PROMPTS = [
  "Help me think through this idea clearly.",
  "Draft a concise message I can send to my team.",
  "Turn these rough thoughts into a cleaner note.",
  "Explain this topic simply, then improve the wording.",
];
export default function DeepSpaceChatClient({
  onInsertLatestAnswer,
  onSelectNote,
  onNewNote,
  onConversationRenamed,
  activeConversationId,
  currentContent,
  isMobileStacked,
  isHistoryOpen,
  onSetHistoryOpen,
}: DeepSpaceChatClientProps) {
  const [state, dispatch] = useReducer(deepSpaceThreadReducer, initialDeepSpaceThreadState);
  const [query, setQuery] = useState("");
  const [completionPulse, setCompletionPulse] = useState(false);
  const [localHistoryOpen, setLocalHistoryOpen] = useState(false);
  const historyOpen = isHistoryOpen !== undefined ? isHistoryOpen : localHistoryOpen;
  const setHistoryOpen = onSetHistoryOpen !== undefined ? onSetHistoryOpen : setLocalHistoryOpen;
  const thinkingEnabled = true;
  const [threadScrollMetrics, setThreadScrollMetrics] = useState<{
    scrollTop: number;
    viewportHeight: number;
  } | null>(null);

  const [availableModels, setAvailableModels] = useState<
    Array<{
      providerId: string;
      modelName: string;
      displayName: string;
      contextWindow?: number | null;
      contextWindowSource?: string | null;
    }>
  >([]);
  const [selectedProviderOverride, setSelectedProviderOverride] = useState<string | null>(null);
  const [selectedModelOverride, setSelectedModelOverride] = useState<string | null>(null);
  const modelSwitchRef = useRef<Promise<void> | null>(null);
  const modelSelectionVersionRef = useRef(0);
  const submissionInFlightRef = useRef(false);

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
        if (chatAssignment?.model_name) {
          setSelectedModelOverride(chatAssignment.model_name);
          setSelectedProviderOverride(chatAssignment.provider_config_id);
        }

        const chatProviders = providersList.filter((p) => p.enabled && p.supports_chat);
        const allChatModels: Array<{
          providerId: string;
          modelName: string;
          displayName: string;
          contextWindow?: number | null;
          contextWindowSource?: string | null;
        }> = [];

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
                    contextWindow: m.context_window,
                    contextWindowSource:
                      typeof m.capabilities_json.context_window_source === "string"
                        ? m.capabilities_json.context_window_source
                        : null,
                  })),
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
                    modelName,
                    displayName: modelName,
                    contextWindow: null,
                    contextWindowSource: "provider_default",
                  },
                ]
              : [];
          });
          if (chatAssignment?.model_name && chatAssignment.provider_config_id) {
            fallbackModels.push({
              providerId: chatAssignment.provider_config_id,
              modelName: chatAssignment.model_name,
              displayName: chatAssignment.model_name,
              contextWindow: null,
              contextWindowSource: "assignment",
            });
          }
          const merged = new Map(
            [...allChatModels, ...fallbackModels].map((model) => [
              `${model.providerId}:${model.modelName}`,
              model,
            ]),
          );
          setAvailableModels([...merged.values()]);
        }
      } catch (err) {
        console.error("Failed to load models", err);
      }
    };

    void fetchModelsAndAssignments();
    return () => {
      active = false;
    };
  }, []);

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
    [selectedModelOverride, selectedProviderOverride],
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

  const stream = useDeepSpaceStream(
    useMemo(
      () => ({
        onEvent: (event) => {
          dispatch({ type: "stream_event", event });
        },
        onEvents: (events) => {
          dispatch({ type: "stream_events", events });
        },
        onTransportError: (error) => dispatch({ type: "stream_failed", error }),
        onUserCancel: () => dispatch({ type: "stream_interrupted" }),
        onFinally: () => {
          setCompletionPulse(true);
          window.setTimeout(() => setCompletionPulse(false), 950);
          dispatch({ type: "stream_finished" });
        },
      }),
      [],
    ),
  );

  const resolveMCPApproval = useCallback(
    async (approvalId: string, decision: "approved" | "denied") => {
      if (!activeConversationId || !approvalId) return;
      const response = (await fetchWithAuth(
        `/deepspace/chats/${activeConversationId}/approvals/${encodeURIComponent(approvalId)}`,
        {
          method: "POST",
          body: JSON.stringify({ decision }),
        },
      )) as Response;
      if (!response.ok) {
        toast.error("Unable to resolve the MCP approval request.");
        return;
      }
      pendingHistorySyncRef.current = true;
      await stream.start({
        endpoint: "/deepspace/chats/stream",
        body: {
          conversation_id: activeConversationId,
          resume_approval_id: approvalId,
          thinking_enabled: thinkingEnabled,
        },
      });
    },
    [activeConversationId, stream, thinkingEnabled],
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
      if (autoScrollRafRef.current !== null) {
        window.cancelAnimationFrame(autoScrollRafRef.current);
      }
    },
    [],
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
      if (!effectiveQuery || state.isStreaming || submissionInFlightRef.current) return;

      submissionInFlightRef.current = true;
      try {
        await modelSwitchRef.current;

        setCompletionPulse(false);
        setQuery("");
        autoFollowRef.current = true;
        dispatch({ type: "submit_query", query: effectiveQuery });
        pendingHistorySyncRef.current = true;

        await stream.start({
          endpoint: "/deepspace/chats/stream",
          body: {
            message: effectiveQuery,
            conversation_id: state.currentConversationId,
            client_request_id: crypto.randomUUID(),
            thinking_enabled: thinkingEnabled,
          },
        });
      } finally {
        submissionInFlightRef.current = false;
      }
    },
    [query, state.currentConversationId, state.isStreaming, stream, thinkingEnabled],
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
          const tokenRes = await fetch(
            `/api/v1/voice/token?room=${uniqueRoom}&identity=user-${Math.random().toString(36).slice(2, 6)}`,
          );
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
    },
    [submitQuery, queueText],
  );

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
        },
      });
    },
    [activeConversationId, state.isStreaming, stream, thinkingEnabled],
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
        },
      });
    },
    [activeConversationId, state.isStreaming, stream, thinkingEnabled],
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

  const effectiveModelName = selectedModelOverride ?? state.lastModelName ?? null;
  const selectedModel =
    availableModels.find(
      (model) =>
        model.modelName === effectiveModelName &&
        (!selectedProviderOverride || model.providerId === selectedProviderOverride),
    ) ?? availableModels.find((model) => model.modelName === effectiveModelName);
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
        step.status === "running" &&
        (step.type === "tool_call" || step.type === "observation"),
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
      streamActivity:
        (latestAssistant?.rawContent?.length ?? 0) +
        (latestAssistant?.thinkingContent?.length ?? 0) +
        (latestAssistant?.agentSteps?.length ?? 0),
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
  const contextUsedTokens =
    latestAssistant?.metrics?.contextUsedTokens ?? latestAssistant?.metrics?.totalTokens ?? null;
  const contextLimit =
    selectedModel?.contextWindow ??
    latestAssistant?.metrics?.contextLimit ??
    state.lastContextLimit;

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
      scheduleScrollToBottom();
    });
    observer.observe(threadRoot);

    return () => observer.disconnect();
  }, [scheduleScrollToBottom]);

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
            messages={renderableMessages}
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
              messages={renderableMessages}
              emptyPrompts={EMPTY_PROMPTS}
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
            />
          </div>

          <div className="flex w-full shrink-0 flex-col items-center">
            <DeepSpaceComposer
              query={query}
              isStreaming={state.isStreaming}
              modelName={effectiveModelName}
              onQueryChange={setQuery}
              onSubmit={() => void submitQuery()}
              onStop={stopStreaming}
              availableModels={availableModels}
              onModelSelect={handleModelSelect}
              voiceState={voiceState}
              contextUsedTokens={contextUsedTokens}
              contextLimit={contextLimit}
              sttActive={sttActive}
              ttsActive={ttsActive}
              onSttToggle={handleSttToggle}
              onTtsToggle={handleTtsToggle}
              voiceLabel={voiceLabel}
              runtimePhase={runtimeActivity.phase}
              activeToolName={runtimeActivity.activeToolName}
              streamActivity={runtimeActivity.streamActivity}
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
